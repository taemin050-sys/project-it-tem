#!/usr/bin/env bash
# Real official React Chrome/fastAPI, synthetic MPO + second same-SKU photo;
# no real product bytes and NO provider, paid secret, GCP writes or operations.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
A="$(cd "$HERE/../.." && pwd)"
cd "$A"
[[ "$(uname -s)" == Darwin ]] || { echo A51D_MAC_REQUIRED;exit 2; }
[[ -x "$A41_PYTHON" ]] || { echo A41_PYTHON_REQUIRED;exit 2; }
[[ -f "$A41_PLAYWRIGHT_CORE_MODULE/package.json" ]] || { echo A41_PLAYWRIGHT_REQUIRED;exit 2; }
[[ -f "$A41_FONT" ]] || { echo A41_FONT_REQUIRED;exit 2; }
[[ "$A51D_PORT" =~ ^[0-9]{4,5}$ ]] || exit 2
case "$A51D_PORT" in 18082|18088|18095|18096|18100)echo PROTECTED_PORT;exit 2;;esac
for k in OPENAI_API_KEY GOOGLE_API_KEY GEMINI_API_KEY ANTHROPIC_API_KEY;do
 if [[ -n "$(printenv "$k" || true)" ]];then echo PAID_CREDENTIAL_REFUSED;exit 2;fi
done
if lsof -tiTCP:"$A51D_PORT" -sTCP:LISTEN >/dev/null 2>&1;then echo PORT_BUSY;exit 2;fi
T="$(mktemp -d /private/tmp/ittem-a41-a51d-XXXXXXXX)"
chmod 700 "$T"
export A41_TEST_ROOT="$T" A41_BASE_URL="http://127.0.0.1:$A51D_PORT"
export A41_SOURCE_SHA="$(git rev-parse HEAD)" A41_INVITE_FILE="$T/invite_token.private"
export A41_PHOTO_1="$T/hidden-mpo.jpg" A41_PHOTO_2="$T/product2.png"
export A41_EVIDENCE_DIR="$T/evidence"
export PYTHONPATH="$A" PYTHONDONTWRITEBYTECODE=1
export IT_TEM_QA_FIXTURE_ENABLED=YES IT_TEM_LIVE_ENABLED=NO
export IT_TEM_LIVE_EXECUTION_APPROVED=NO IT_TEM_LIVE_WEB_QUEUE_ENABLED=NO
export IT_TEM_DEMO_SECURE_COOKIE=NO IT_TEM_QA_ALLOWED_ACTORS=alice
export IT_TEM_ENABLE_BILLABLE_TEXT_CALLS=NO
export IT_TEM_A51D_MPO_FIXTURE_BRIDGE=YES IT_TEM_A51D_NONDEPLOYABLE_TEST_ONLY=YES
export IT_TEM_A51C_HARD_CAP_ENABLE=NO IT_TEM_TAILNET_AUTH_ENABLED=NO IT_TEM_TAILNET_SSO_ONLY=NO
export IT_TEM_LIVE_KOREAN_FONT="$A41_FONT" IT_TEM_KOREAN_FONT="$A41_FONT"
export VITE_QA_OFFLINE_FIXTURE=YES VITE_USE_MOCK=false VITE_IT_TEM_TRACK_ID=BASELINE
export VITE_IT_TEM_CODE_SHA="$A41_SOURCE_SHA" VITE_A51D_MPO_FIXTURE_BRIDGE=YES
"$A41_PYTHON" -B - <<'PY'
from PIL import Image
from pathlib import Path
import os
p=Path(os.environ['A41_PHOTO_1'])
a=Image.new('RGB',(480,640),(140,50,90))
b=Image.new('RGB',(460,620),(100,165,120))
a.save(p,format='MPO',save_all=True,append_images=[b],quality=94)
assert p.read_bytes()[:2]==b'\xff\xd8'
Image.new('RGB',(480,640),(180,195,205)).save(os.environ['A41_PHOTO_2'])
PY
npm --prefix app run build > "$T/build.log" 2>&1
cp -R app/dist "$T/frontend"
"$A41_PYTHON" -B -m uvicorn a41_fixture_server:app --app-dir "$HERE" \
  --host 127.0.0.1 --port "$A51D_PORT" --no-access-log > "$T/server.log" 2>&1 &
server_pid=$!
cleanup(){
 if kill -0 "$server_pid" 2>/dev/null;then kill "$server_pid" || :;wait "$server_pid" 2>/dev/null || :;fi
}
trap cleanup EXIT
live=0
for _ in $(seq 1 30);do
 if curl -fsS --max-time 1 "$A41_BASE_URL/health" >/dev/null 2>&1;then live=1;break;fi
 kill -0 "$server_pid" 2>/dev/null || break
 sleep 1
done
if ((live!=1));then echo FIXTURE_SERVER_FAIL;tail -45 "$T/server.log";exit 3;fi
mkdir -p "$A41_EVIDENCE_DIR"
cp "$T/build.log" "$A41_EVIDENCE_DIR/build.log"
node "$HERE/a51d_mpo_official_react_chrome.cjs" > "$A41_EVIDENCE_DIR/browser.log" 2>&1 || {
  tail -60 "$A41_EVIDENCE_DIR/browser.log";echo FIXTURE_CHROME_FAIL;exit 4;
}
"$A41_PYTHON" -B - <<'PY'
from pathlib import Path
import json,os
root=Path(os.environ['A41_EVIDENCE_DIR'])
d=json.loads((root/'browser_trace.json').read_text())
assert d['status']=='PASS_OFFLINE_FIXTURE_ONLY'
assert d['actor_job_acl']=='ALICE_200_UNAUTHORIZED_CONTEXT_401'
assert d['browser_confirmed_mpo_frame_index']==1
assert not d['browser_errors']
assert not d['external_requests']
assert len(d['screenshots'])==6
assert len([x for x in d['http'] if x['method']=='POST' and x['path']=='/demo/api/a51d/mpo/jobs'])==1
assert len([x for x in d['http'] if x['method']=='POST' and x['path']=='/demo/api/a51d/mpo/confirm'])==1
assert all(len(x['sha256'])==64 for x in d['screenshots'])
assert d['output_size']=={'width':1080,'height':1350}
from hashlib import sha256
assert sha256((root/'ad_1080x1350.png').read_bytes()).hexdigest()==d['final_sha']
assert sha256((root/'caption.txt').read_bytes()).hexdigest()==d['caption_sha']
assert d['image_attempt_version']==1
PY
(cd "$A41_EVIDENCE_DIR" && shasum -a 256 *.json *.png *.log *.txt > SHA256_MANIFEST.txt && shasum -a 256 -c SHA256_MANIFEST.txt > SHA256_CHECK.log)
echo A51D_ACTUAL_OWNER_REACT_CHROME_B0_AUTHENTICATED_MPO_E2E_PASS
echo A51D_REAL_PAID_PROVIDER_CALLS_0
echo A51D_NO_REAL_OWNER_MPO_POLICY_OR_GCP
echo A51D_EVIDENCE_ROOT="$A41_EVIDENCE_DIR"
