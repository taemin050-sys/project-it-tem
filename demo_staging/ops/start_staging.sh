#!/usr/bin/env bash
set -euo pipefail
BASE="$IT_TEM_DEMO_ROOT"
test -f "$BASE/config/invites.sha256.json" || { echo INVITES_REQUIRED; exit 3; }
test ! -e "$BASE/runtime/uvicorn.pid" || { echo ALREADY_STARTED; exit 3; }
if ss -ltn | grep -q '127.0.0.1:18080 '; then echo PORT_OCCUPIED; exit 5; fi
cd "$BASE/repo"
umask 077
nohup env PYTHONPATH="$BASE/repo" IT_TEM_DEMO_ROOT="$BASE" \
    IT_TEM_DEMO_SECURE_COOKIE=YES IT_TEM_DEMO_CODE_SHA="$(cat "$BASE/config/source.sha")" \
    IT_TEM_KOREAN_FONT=/usr/share/fonts/truetype/nanum/NanumGothic.ttf \
    "$BASE/.venv/bin/python" -m uvicorn demo_staging.serve:app --host 127.0.0.1 --port 18080 \
    --workers 1 --no-use-colors >>"$BASE/logs/staging.log" 2>&1 </dev/null &
echo "$!" > "$BASE/runtime/uvicorn.pid"
echo STAGING_STARTED_LOOPBACK_ONLY
