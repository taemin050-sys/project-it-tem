#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
PYTHON="$IT_TEM_PYTHON"
T="$ROOT/.runtime/b0_browser_harness"
mkdir -p "$T"
BACK_PID=""
FRONT_PID=""

cleanup() {
  if [[ -n "$FRONT_PID" ]]; then kill "$FRONT_PID" 2>/dev/null || true; wait "$FRONT_PID" 2>/dev/null || true; fi
  if [[ -n "$BACK_PID" ]]; then kill "$BACK_PID" 2>/dev/null || true; wait "$BACK_PID" 2>/dev/null || true; fi
}
trap cleanup EXIT
export T

"$PYTHON" - <<'PY'
from pathlib import Path
from os import environ
from PIL import Image, ImageDraw
t=Path(environ['T'])
for suffix,dx in [('a',0),('b',11)]:
    im=Image.new('RGB',(280,350),(239,232,226))
    d=ImageDraw.Draw(im)
    d.rectangle((90+dx,65,190+dx,305),fill=(211,231,222),outline=(89,122,108),width=3)
    d.rectangle((112+dx,40,168+dx,69),fill=(120,148,134))
    d.rectangle((99+dx,170,181+dx,241),fill=(252,249,244))
    d.text((114+dx,192),'RAUM',fill=(28,66,54))
    im.save(t/f'product-{suffix}.png')
(t/'ittem_test_server.py').write_text(
    'from pathlib import Path\nfrom src.serving.main import create_app\napp=create_app(Path('+repr(str(t/'jobs'))+'))\n')
PY

cd "$ROOT"
PYTHONPATH="$T:$ROOT" "$PYTHON" -m uvicorn ittem_test_server:app --host 127.0.0.1 --port 18766 >"$T/backend.log" 2>&1 &
BACK_PID=$!
cd "$HERE"
npm run dev >"$T/vite.log" 2>&1 &
FRONT_PID=$!

for svc in http://127.0.0.1:18766/health http://127.0.0.1:4173; do
  i=0
  until curl -fsS "$svc" >/dev/null 2>&1; do
    i=$((i+1))
    if [[ "$i" -ge 80 ]]; then echo "SERVICE_START_FAILED $svc"; tail -60 "$T/backend.log" "$T/vite.log"; exit 1; fi
    sleep 0.2
  done
done

B0_TEST_IMAGE_A="$T/product-a.png" \
B0_TEST_IMAGE_B="$T/product-b.png" \
B0_EVIDENCE_DIR="$T" npm run browser:test

# Verify actual backend process restart recovers file-backed Job and artifact.
JOB_ID="$("$PYTHON" -c 'import json,sys; print(json.load(open(sys.argv[1]))["job_id"])' "$T/browser_network_trace.json")"
kill "$BACK_PID"
wait "$BACK_PID" 2>/dev/null || true
BACK_PID=""
i=0
while curl -fsS http://127.0.0.1:18766/health >/dev/null 2>&1; do
  i=$((i+1))
  if [[ "$i" -ge 40 ]]; then echo "BACKEND_DID_NOT_STOP";exit 1;fi
  sleep 0.1
done
cd "$ROOT"
PYTHONPATH="$T:$ROOT" "$PYTHON" -m uvicorn ittem_test_server:app --host 127.0.0.1 --port 18766 >>"$T/backend.log" 2>&1 &
BACK_PID=$!
i=0
until curl -fsS http://127.0.0.1:18766/health >/dev/null 2>&1; do
  i=$((i+1))
  if [[ "$i" -ge 60 ]]; then echo "BACKEND_RESTART_FAILED"; exit 1;fi
  sleep 0.1
done
curl -fsS "http://127.0.0.1:18766/api/v1/jobs/$JOB_ID" > "$T/post_restart_job.json"
curl -fsS "http://127.0.0.1:18766/api/v1/jobs/$JOB_ID/artifacts/final" -o "$T/post_restart_final.png"
"$PYTHON" - <<'PY'
import json,os
from pathlib import Path
from PIL import Image
t=Path(os.environ["T"])
assert json.loads((t/"post_restart_job.json").read_text())["status"] == "COMPLETED"
assert Image.open(t/"post_restart_final.png").size == (1080,1350)
print("PASS actual backend process restart restores Job and PNG")
PY
echo "B0_HARNESS_PASS ($T)"
