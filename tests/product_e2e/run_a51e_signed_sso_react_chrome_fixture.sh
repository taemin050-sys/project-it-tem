#!/usr/bin/env bash
# Strict localhost synthetic fake-signing-proxy HMAC/Signed SSO E2E.
# No actual Tailscale Serve, GCP writes, Provider, team URL or paid worker.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
A="$(cd "$HERE/../.." && pwd)"
cd "$A"
[[ "$(uname -s)" == Darwin ]] || { echo A51E_MAC_ONLY;exit 3; }
[[ -n "$A41_PYTHON" && -x "$A41_PYTHON" ]] || exit 3
[[ -n "$A41_PLAYWRIGHT_CORE_MODULE" ]] || exit 3
[[ -f "$A41_PLAYWRIGHT_CORE_MODULE/package.json" ]] || exit 3
[[ -n "$A41_FONT" && -f "$A41_FONT" ]] || exit 3
[[ "$A51E_PORT" =~ ^[0-9]{4,5}$ ]] || exit 3
case "$A51E_PORT" in
  10443|10500|18082|18088|18095|18096|18100)echo PROTECTED_PORT;exit 3;;
esac
for key in OPENAI_API_KEY GOOGLE_API_KEY GEMINI_API_KEY ANTHROPIC_API_KEY; do
 if [[ -n "$(printenv "$key" || true)" ]];then echo PROVIDER_CREDENTIAL_REFUSED;exit 3;fi
done
if lsof -tiTCP:"$A51E_PORT" -sTCP:LISTEN >/dev/null 2>&1;then
 echo LOOPBACK_PORT_BUSY;exit 3
fi
T="$(mktemp -d /private/tmp/ittem-a51e-XXXXXXXX)"
chmod 700 "$T"
export A51E_TEST_ROOT="$T" A51E_BASE_URL="http://127.0.0.1:$A51E_PORT"
export A51E_SOURCE_SHA="$(git rev-parse HEAD)"
export A51E_EVIDENCE_DIR="$T/evidence"
export A51E_PHOTO_1="$T/first.png" A51E_PHOTO_2="$T/second.png"
export A51E_MPO="$T/disguised-mpo.jpg"
export PYTHONPATH="$A" PYTHONDONTWRITEBYTECODE=1
export IT_TEM_A51E_SIGNED_BETA_INTAKE=YES
export IT_TEM_A51E_NONBILLABLE_CANDIDATE=YES
export IT_TEM_A51E_MPO_POLICY_STATE=PENDING_REJECT
export IT_TEM_A51D_SIGNED_BETA_RUNTIME=YES
export IT_TEM_A51C_HARD_CAP_ENABLE=YES IT_TEM_LIVE_COST_POLICY=HARD_CAP
export IT_TEM_TAILNET_SSO_ONLY=YES IT_TEM_TAILNET_AUTH_ENABLED=YES
export IT_TEM_TAILNET_EXPECTED_HOST=macstudio-integration.ts.net:10443
export IT_TEM_QA_FIXTURE_ENABLED=YES IT_TEM_QA_ALLOWED_ACTORS=alice
export IT_TEM_DEMO_SECURE_COOKIE=YES
export IT_TEM_LIVE_ENABLED=NO IT_TEM_LIVE_EXECUTION_APPROVED=NO
export IT_TEM_LIVE_WEB_QUEUE_ENABLED=NO
export IT_TEM_ENABLE_BILLABLE_TEXT_CALLS=NO
export IT_TEM_A51D_MPO_FIXTURE_BRIDGE=NO
export IT_TEM_LIVE_KOREAN_FONT="$A41_FONT" IT_TEM_KOREAN_FONT="$A41_FONT"
export VITE_QA_OFFLINE_FIXTURE=YES VITE_USE_MOCK=false
export VITE_IT_TEM_SSO_ONLY=YES VITE_A51E_SIGNED_BETA_CANDIDATE=YES
export VITE_IT_TEM_TRACK_ID=BASELINE VITE_IT_TEM_CODE_SHA="$A51E_SOURCE_SHA"
"$A41_PYTHON" -B - <<'PY'
from PIL import Image
from pathlib import Path
import os
Image.new("RGB",(480,640),(130,170,200)).save(os.environ["A51E_PHOTO_1"])
Image.new("RGB",(480,640),(170,185,200)).save(os.environ["A51E_PHOTO_2"])
a=Image.new("RGB",(450,600),(142,53,91))
b=Image.new("RGB",(450,600),(73,151,119))
a.save(os.environ["A51E_MPO"],format="MPO",save_all=True,
       append_images=[b],quality=94)
assert Path(os.environ["A51E_MPO"]).read_bytes()[:2]==b"\xff\xd8"
PY
npm --prefix app run build > "$T/build.log" 2>&1
cp -R app/dist "$T/frontend"
"$A41_PYTHON" -B -m uvicorn a51e_signed_sso_nonbillable_fixture_server:app \
 --app-dir "$HERE" --host 127.0.0.1 --port "$A51E_PORT" --no-access-log \
 > "$T/server.log" 2>&1 &
server_pid=$!
cleanup(){
 if kill -0 "$server_pid" 2>/dev/null;then
   kill "$server_pid" || :;wait "$server_pid" 2>/dev/null || :
 fi
}
trap cleanup EXIT
live=0
for _ in $(seq 1 30);do
 if curl -fsS --max-time 1 "$A51E_BASE_URL/health" >/dev/null 2>&1;then
   live=1;break
 fi
 kill -0 "$server_pid" 2>/dev/null || break
 sleep 1
done
if ((live!=1));then echo SIGNED_SIMULATED_SERVER_FAIL;tail -55 "$T/server.log";exit 4;fi
mkdir -p "$A51E_EVIDENCE_DIR"
cp "$T/build.log" "$A51E_EVIDENCE_DIR/a51e_build.log"
node "$HERE/a51e_signed_sso_react_chrome.cjs" > "$A51E_EVIDENCE_DIR/a51e_browser.log" 2>&1 || {
 tail -70 "$A51E_EVIDENCE_DIR/a51e_browser.log"
 echo A51E_BROWSER_FAIL;exit 5
}
"$A41_PYTHON" -B - <<'PY'
from pathlib import Path
import json,os,hashlib
root=Path(os.environ["A51E_EVIDENCE_DIR"])
d=json.loads((root/"a51e_signed_chrome_trace.json").read_text())
assert d["code_sha"]==os.environ["A51E_SOURCE_SHA"]
assert d["status"]=="PASS_FAKE_SIGNED_ASSERTION_OFFLINE_FIXTURE_NOT_REAL_TAILSCALE"
assert len(d["downloads"])==2
assert len(d["screenshots"])==4
assert d["errors"]==d["external"]==[]
assert sum(1 for x in d["http"] if x["method"]=="POST"
           and x["path"]=="/demo/api/a51e/beta/jobs")==1
assert hashlib.sha256((root/"a51e_signed_fixture_ad.png").read_bytes()).hexdigest()==d["png_sha"]
assert hashlib.sha256((root/"a51e_signed_fixture_caption.txt").read_bytes()).hexdigest()==d["caption_sha"]
PY
(cd "$A51E_EVIDENCE_DIR" && shasum -a 256 *.json *.png *.txt *.log > SHA256_MANIFEST.txt && shasum -a 256 -c SHA256_MANIFEST.txt > SHA_CHECK.log)
echo A51E_LOCAL_FAKE_SIGNED_SSO_OFFICIAL_REACT_CHROME_COMPLETE_E2E_PASS
echo A51E_REAL_TAILSCALE_SSO_NOT_TESTED
echo A51E_PAID_EXTERNAL_PROVIDER_CALLS_0
echo A51E_TEAM_BETA_UAT_NOT_READY
echo A51E_EVIDENCE_ROOT="$A51E_EVIDENCE_DIR"
