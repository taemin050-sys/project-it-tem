#!/usr/bin/env bash
# Executed exclusively through ittem-bp18-b.service after ExecStartPre.
set -euo pipefail
umask 077
ROOT=/home/macstudio/ittem-bp18-product-completion-20261111
# Protect against two mutually independent web executors even across
# systemd manager restarts; lock held through exec/entire server lifetime.
exec 9> "$ROOT/config/.b5_single_web.lock"
flock -n 9 || { echo "BP18_WEB_EXEC_SECOND_INSTANCE_DENIED" >&2;exit 78; }
test "$(readlink "$ROOT/repo")" = "releases/$(cat "$ROOT/repo/SOURCE_SHA.txt")"
echo "$$" > "$ROOT/web.pid"
export IT_TEM_DEMO_CODE_SHA="$(cat "$ROOT/repo/SOURCE_SHA.txt")"
exec /home/macstudio/ittem-a-template-ui-test-20261102/.venv/bin/python \
    -m uvicorn demo_staging.serve:app --app-dir "$ROOT/repo" \
    --host 127.0.0.1 --port 18100 --workers 1 --no-use-colors
