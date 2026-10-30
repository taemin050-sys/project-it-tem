#!/usr/bin/env bash
set -euo pipefail
BASE="$IT_TEM_DEMO_ROOT"
FILE="$BASE/runtime/uvicorn.pid"
test -s "$FILE" || { echo NO_OWN_STAGING_PID; exit 0; }
PID="$(cat "$FILE")"
CMD="$(tr '\0' ' ' </proc/"$PID"/cmdline 2>/dev/null || true)"
case "$CMD" in *"$BASE/.venv/bin/python -m uvicorn demo_staging.serve:app"*) kill "$PID";rm "$FILE";echo STOPPED_OWN_STAGING_ONLY;;*) echo PID_OWNERSHIP_UNKNOWN_NOT_TOUCHED;exit 4;;esac
