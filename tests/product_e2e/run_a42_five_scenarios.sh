#!/usr/bin/env bash
# A4-2 five actual Chrome OFFLINE_FIXTURE E2E journeys, 1 candidate/job.
# NOT A5-1 approved typography; NOT real provider/production deployment.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
A="$(cd "$HERE/../.." && pwd)"
cd "$A"
[[ "$(uname -s)" == "Darwin" ]] || { echo A42_MAC_ONLY;exit 2; }
[[ -f "$A41_PLAYWRIGHT_CORE_MODULE/package.json" ]] || { echo A42_PLAYWRIGHT_REQUIRED;exit 2; }
[[ -x "$A41_PYTHON" ]] || { echo A42_PYTHON_REQUIRED;exit 2; }
for key in OPENAI_API_KEY GOOGLE_API_KEY GEMINI_API_KEY ANTHROPIC_API_KEY;do
 if [[ -n "$(printenv "$key" || true)" ]];then echo "A42_PAID_KEY_REFUSED_$key";exit 2;fi
done
A41_SOURCE_SHA="$(git rev-parse HEAD)";export A41_SOURCE_SHA
[[ "$A41_SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]] || exit 2
[[ "$A42_PORT" =~ ^[0-9]{4,5}$ ]] || exit 2
case "$A42_PORT" in 18082|18088|18095|18096|18100)echo A42_PROTECTED_PORT;exit 2;;esac
if lsof -tiTCP:"$A42_PORT" -sTCP:LISTEN >/dev/null 2>&1;then echo A42_PORT_BUSY;exit 2;fi
T="$(mktemp -d /private/tmp/ittem-a41-product-a42-XXXXXXXX)"
chmod 700 "$T"
printf "%s\n" "$T" >/private/tmp/IT_TEM_A42_LAST_RUN_PATH
A41_TEST_ROOT="$T"
A41_BASE_URL="http://127.0.0.1:$A42_PORT"
A42_OUT="$T/evidence_five"
A41_INVITE_FILE="$T/invite_token.private"
A41_PHOTO_1="$T/product1.png"
A41_PHOTO_2="$T/product2.png"
export A41_TEST_ROOT A41_BASE_URL A41_INVITE_FILE A41_PHOTO_1 A41_PHOTO_2
export PYTHONPATH="$A" PYTHONDONTWRITEBYTECODE=1
export IT_TEM_QA_FIXTURE_ENABLED=YES IT_TEM_LIVE_ENABLED=NO
export IT_TEM_LIVE_EXECUTION_APPROVED=NO IT_TEM_LIVE_WEB_QUEUE_ENABLED=NO
export IT_TEM_DEMO_SECURE_COOKIE=NO IT_TEM_QA_ALLOWED_ACTORS=alice
export IT_TEM_ENABLE_BILLABLE_TEXT_CALLS=NO
export IT_TEM_LIVE_KOREAN_FONT="$A41_FONT" IT_TEM_KOREAN_FONT="$A41_FONT"
export VITE_QA_OFFLINE_FIXTURE=YES VITE_USE_MOCK=false VITE_IT_TEM_TRACK_ID=BASELINE
export VITE_IT_TEM_CODE_SHA="$A41_SOURCE_SHA"
[[ -f "$IT_TEM_LIVE_KOREAN_FONT" ]] || exit 2
npm --prefix app run build > "$T/build.log" 2>&1
cp -R app/dist "$T/frontend"
"$A41_PYTHON" -B -m uvicorn a41_fixture_server:app --app-dir "$HERE" \
 --host 127.0.0.1 --port "$A42_PORT" --no-access-log > "$T/server.log" 2>&1 &
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
if ((live!=1));then echo A42_LOOPBACK_SERVER_FAILED;tail -10 "$T/server.log";exit 3;fi
mkdir -p "$A42_OUT"
cp "$T/build.log" "$A42_OUT/A42_BUILD.log"
for pair in composed_3:4 composed_9:16 freeform_4:5 freeform_3:4 freeform_9:16;do
 A42_MODE="$(echo "$pair" | cut -d_ -f1)"
 A42_RATIO="$(echo "$pair" | cut -d_ -f2)"
 export A42_MODE A42_RATIO
 label="$(echo "$pair" | tr ':' 'x')"
 A41_EVIDENCE_DIR="$A42_OUT/$label"
 export A41_EVIDENCE_DIR
 mkdir -p "$A41_EVIDENCE_DIR"
 node "$HERE/a42_official_react_chrome.cjs" > "$A41_EVIDENCE_DIR/browser.log" 2>&1
 "$A41_PYTHON" -B "$HERE/a42_verify_offline_evidence.py" \
   --runtime-root "$T/isolated" --evidence-dir "$A41_EVIDENCE_DIR" \
   --output "$A41_EVIDENCE_DIR/ledger_artifact_verification.json" > "$A41_EVIDENCE_DIR/verify.log" 2>&1
 (
  cd "$A41_EVIDENCE_DIR"
  shasum -a 256 -- *.png *.txt *.json *.log > SHA256_MANIFEST.txt
  shasum -a 256 -c SHA256_MANIFEST.txt > SHA256_CHECK.log
 )
 echo "A42_SCENARIO_PASS_$label"
 tail -7 "$A41_EVIDENCE_DIR/verify.log"
done
echo "A42_ALL_FIVE_CHROME_FIXTURE_SCENARIOS_PASS"
echo "A42_EVIDENCE_DIR=$A42_OUT"
echo "A42_PROVIDER_AND_GCP_HOLD / CTA_9X16_PENDING"
