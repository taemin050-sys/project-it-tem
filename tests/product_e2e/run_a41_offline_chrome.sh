#!/usr/bin/env bash
# Actual official React 4:5 Composed Chrome E2E, paid calls disabled.
# Must never target GCP/Live18088/QA18095/B18100 or use customer assets.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
A="$(cd "$HERE/../.." && pwd)"
cd "$A"
[[ "$(uname -s)" == "Darwin" ]] || { echo 'A41_MACOS_TEST_ONLY'; exit 2; }
[[ -f "$A41_PLAYWRIGHT_CORE_MODULE/package.json" ]] || { echo 'A41_SET_LOCAL_PLAYWRIGHT_CORE_MODULE'; exit 2; }
[[ -x "$A41_PYTHON" ]] || { echo 'A41_SET_A41_PYTHON'; exit 2; }
for key in OPENAI_API_KEY GOOGLE_API_KEY GEMINI_API_KEY ANTHROPIC_API_KEY;do
 if [[ -n "$(printenv "$key")" ]];then echo "A41_PAID_KEY_REFUSED_$key";exit 2;fi
done
A41_SOURCE_SHA="$(git rev-parse HEAD)"
export A41_SOURCE_SHA
[[ "$A41_SOURCE_SHA" =~ ^[a-f0-9]{40}$ ]] || exit 2
[[ "$A41_PORT" =~ ^[0-9]+$ ]] && ((A41_PORT>=1025 && A41_PORT<=65535)) || exit 2
case "$A41_PORT" in 18082|18088|18095|18096|18100) echo 'A41_PROTECTED_PORT_REFUSED';exit 2;;esac
if lsof -tiTCP:"$A41_PORT" -sTCP:LISTEN >/dev/null 2>&1;then echo 'A41_PORT_IN_USE';exit 2;fi
T="$(mktemp -d /private/tmp/ittem-a41-product-XXXXXXXX)"
chmod 700 "$T"
echo "$T" > /private/tmp/IT_TEM_A41_LAST_RUN_PATH
A41_TEST_ROOT="$T"
A41_BASE_URL="http://127.0.0.1:$A41_PORT"
A41_EVIDENCE_DIR="$T/evidence"
A41_INVITE_FILE="$T/invite_token.private"
A41_PHOTO_1="$T/product1.png"
A41_PHOTO_2="$T/product2.png"
export A41_TEST_ROOT A41_BASE_URL A41_EVIDENCE_DIR A41_INVITE_FILE A41_PHOTO_1 A41_PHOTO_2
export PYTHONPATH="$A" PYTHONDONTWRITEBYTECODE=1
export IT_TEM_QA_FIXTURE_ENABLED=YES IT_TEM_LIVE_ENABLED=NO IT_TEM_LIVE_EXECUTION_APPROVED=NO
export IT_TEM_LIVE_WEB_QUEUE_ENABLED=NO IT_TEM_DEMO_SECURE_COOKIE=NO
export IT_TEM_QA_ALLOWED_ACTORS=alice IT_TEM_ENABLE_BILLABLE_TEXT_CALLS=NO
export IT_TEM_LIVE_KOREAN_FONT="$A41_FONT"
export IT_TEM_KOREAN_FONT="$A41_FONT"
export VITE_QA_OFFLINE_FIXTURE=YES VITE_USE_MOCK=false
export VITE_IT_TEM_TRACK_ID=BASELINE VITE_IT_TEM_CODE_SHA="$A41_SOURCE_SHA"
[[ -f "$IT_TEM_LIVE_KOREAN_FONT" ]] || { echo 'A41_FONT_UNAVAILABLE';exit 2; }
npm --prefix app run build >"$T/build.log" 2>&1
cp -R app/dist "$T/frontend"
"$A41_PYTHON" -B -m uvicorn a41_fixture_server:app --app-dir "$HERE" \
  --host 127.0.0.1 --port "$A41_PORT" --no-access-log >"$T/server.log" 2>&1 &
server_pid=$!
cleanup() {
 if kill -0 "$server_pid" 2>/dev/null;then kill "$server_pid" 2>/dev/null || :;wait "$server_pid" 2>/dev/null || :;fi
}
trap cleanup EXIT
live=0
for _ in $(seq 1 35);do
 if curl -fsS --max-time 2 "$A41_BASE_URL/health" >/dev/null 2>&1;then live=1;break;fi
 kill -0 "$server_pid" 2>/dev/null || break
 sleep 1
done
if ((live!=1));then echo A41_SERVER_NOT_STARTED;tail -15 "$T/server.log";exit 3;fi
node "$HERE/a41_official_react_chrome.cjs" >"$T/browser.log" 2>&1
"$A41_PYTHON" -B "$HERE/a41_verify_offline_evidence.py" \
  --runtime-root "$T/isolated" --evidence-dir "$A41_EVIDENCE_DIR" \
  --output "$A41_EVIDENCE_DIR/ledger_artifact_verification.json" >"$T/verify.log" 2>&1
cp "$T/build.log" "$T/browser.log" "$T/verify.log" "$A41_EVIDENCE_DIR/"
(
 cd "$A41_EVIDENCE_DIR"
 shasum -a 256 -- *.png *.txt *.json *.log > SHA256_MANIFEST.txt
 shasum -a 256 -c SHA256_MANIFEST.txt > SHA256_CHECK.log
)
echo 'A41_FUNCTIONAL_CHROME_E2E_PASS'
cat "$T/verify.log"
echo "A41_EVIDENCE_DIR=$A41_EVIDENCE_DIR"
echo 'A41_PRODUCT_CTA_HOLD A41-PRODUCT-CTA-01'
echo 'A41_GCP_DEPLOYMENT_HOLD / PAID_WORKER_HOLD'
