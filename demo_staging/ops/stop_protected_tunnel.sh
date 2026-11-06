#!/usr/bin/env bash
set -euo pipefail
BASE="$IT_TEM_DEMO_ROOT"
FILE="$BASE/runtime/cloudflared.pid"
test -s "$FILE" || { echo NO_TUNNEL; exit 0; }
PID="$(cat "$FILE")"
CMD="$(tr '\0' ' ' </proc/"$PID"/cmdline 2>/dev/null || true)"
case "$CMD" in *"$BASE/bin/cloudflared tunnel --url http://127.0.0.1:18080"*"--allowed-mail"*)kill "$PID";rm "$FILE";echo PROTECTED_TUNNEL_STOPPED_URL_EXPIRED;;*)echo PID_OWNERSHIP_UNKNOWN_NOT_TOUCHED; exit 4;;esac
