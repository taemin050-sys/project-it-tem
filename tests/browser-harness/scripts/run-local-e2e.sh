#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
PYTHON="$(printenv IT_TEM_PYTHON || true)"
FONT="$(printenv IT_TEM_KOREAN_FONT || true)"
CHROME="$(printenv CHROME_BIN || echo /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome)"
test -n "$PYTHON" && test -x "$PYTHON" || { echo "Set IT_TEM_PYTHON to executable Python venv path" >&2; exit 2; }
test -n "$FONT" && test -f "$FONT" || { echo "Set IT_TEM_KOREAN_FONT to an installed Korean font file" >&2; exit 2; }
test -x "$CHROME" || { echo "Set CHROME_BIN to an installed Chromium/Chrome executable" >&2; exit 2; }
for exe in node npm curl; do command -v "$exe" >/dev/null || { echo "Missing executable: $exe" >&2; exit 2; }; done

# Fail before creating any files when someone else already owns either port.
"$PYTHON" - <<'PY'
import socket
for port in (18766, 4173):
    with socket.socket() as sock:
        if sock.connect_ex(("127.0.0.1",port)) == 0:
            raise SystemExit(f"Port {port} is occupied. Do not reuse or stop another process.")
print("PASS localhost ports 18766/4173 available")
PY
mkdir -p "$ROOT/.runtime"
T="$(mktemp -d "$ROOT/.runtime/b0-XXXXXXXX")"
export T
BACK_PID=""
FRONT_PID=""
cleanup() {
  if [[ -n "$FRONT_PID" ]]; then kill "$FRONT_PID" 2>/dev/null || true; wait "$FRONT_PID" 2>/dev/null || true; fi
  if [[ -n "$BACK_PID" ]]; then kill "$BACK_PID" 2>/dev/null || true; wait "$BACK_PID" 2>/dev/null || true; fi
  if [[ "$(printenv B0_KEEP_TEST_DATA || echo 0)" != "1" ]]; then
    rm -rf -- "$T/jobs"
    rm -f -- "$T/product-a.png" "$T/product-b.png" "$T/ittem_test_server.py"
  fi
  echo "EVIDENCE_DIR=$T"
}
trap cleanup EXIT

{
  echo "timestamp=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  echo "git_source=$(git -C "$ROOT" rev-parse HEAD)"
  echo "python=$("$PYTHON" --version)"
  echo "node=$(node --version)"
  echo "npm=$(npm --version)"
  echo "chrome=$("$CHROME" --version)"
  echo "font=$(basename "$FONT")"
  echo "mode=MOCK_ONLY; localhost backend=18766; vite=4173"
} >"$T/environment.txt"

"$PYTHON" - <<'PY'
from pathlib import Path
from os import environ
from PIL import Image, ImageDraw
t=Path(environ["T"])
for suffix,dx in (("a",0),("b",11)):
    im=Image.new("RGB",(280,350),(239,232,226))
    d=ImageDraw.Draw(im)
    d.rectangle((90+dx,65,190+dx,305),fill=(211,231,222),outline=(89,122,108),width=3)
    d.rectangle((112+dx,40,168+dx,69),fill=(120,148,134))
    d.rectangle((99+dx,170,181+dx,241),fill=(252,249,244))
    d.text((114+dx,192),"RAUM",fill=(28,66,54))
    im.save(t/("product-"+suffix+".png"))
(t/"ittem_test_server.py").write_text(
    "from pathlib import Path\nfrom src.serving.main import create_app\napp=create_app(Path("+repr(str(t/"jobs"))+"))\n")
PY

cd "$ROOT"
PYTHONPATH="$T:$ROOT" IT_TEM_KOREAN_FONT="$FONT" "$PYTHON" -m uvicorn ittem_test_server:app --host 127.0.0.1 --port 18766 >"$T/backend.log" 2>&1 &
BACK_PID=$!
cd "$HERE"
npm run dev >"$T/vite.log" 2>&1 &
FRONT_PID=$!
for svc in http://127.0.0.1:18766/health http://127.0.0.1:4173; do
  i=0
  until curl --max-time 2 -fsS "$svc" >/dev/null 2>&1; do
    i=$((i+1))
    if [[ "$i" -ge 80 ]]; then echo "SERVICE_START_FAILED $svc" >&2; tail -60 "$T/backend.log" "$T/vite.log"; exit 1; fi
    sleep 0.2
  done
done

B0_TEST_IMAGE_A="$T/product-a.png" B0_TEST_IMAGE_B="$T/product-b.png" \
B0_EVIDENCE_DIR="$T" CHROME_BIN="$CHROME" npm run browser:test

JOB_ID="$("$PYTHON" -c 'import json,sys; print(json.load(open(sys.argv[1]))["job_id"])' "$T/browser_network_trace.json")"
kill "$BACK_PID"
wait "$BACK_PID" 2>/dev/null || true
BACK_PID=""
i=0
while curl --max-time 1 -fsS http://127.0.0.1:18766/health >/dev/null 2>&1; do
  i=$((i+1))
  if [[ "$i" -ge 40 ]]; then echo "BACKEND_DID_NOT_STOP" >&2; exit 1; fi
  sleep 0.1
done

cd "$ROOT"
PYTHONPATH="$T:$ROOT" IT_TEM_KOREAN_FONT="$FONT" "$PYTHON" -m uvicorn ittem_test_server:app --host 127.0.0.1 --port 18766 >>"$T/backend.log" 2>&1 &
BACK_PID=$!
i=0
until curl --max-time 2 -fsS http://127.0.0.1:18766/health >/dev/null 2>&1; do
  i=$((i+1))
  if [[ "$i" -ge 60 ]]; then echo "BACKEND_RESTART_FAILED" >&2; exit 1; fi
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
print("PASS curl recovery after backend process restart")
PY

cd "$HERE"
B0_RECOVERY_JOB_ID="$JOB_ID" B0_EVIDENCE_DIR="$T" CHROME_BIN="$CHROME" npm run browser:recovery
echo "B0_S3B2_HARNESS_PASS"
