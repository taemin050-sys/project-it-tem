#!/usr/bin/env bash
set -euo pipefail
BASE="$IT_TEM_DEMO_ROOT"
BIN="$BASE/bin/cloudflared"
ALLOWLIST="$BASE/config/allowed-mails.txt"
test -x "$BIN" || {echo OFFICIAL_CLOUDFLARED_BINARY_REQUIRED;exit 3;}
test -f "$ALLOWLIST" || {echo EXACT_ALLOWED_MAILS_REQUIRED_NO_PUBLIC_TUNNEL;exit 3;}
test ! -e "$BASE/runtime/cloudflared.pid" || {echo TUNNEL_ALREADY_RUNNING;exit 3;}
test "$(stat -c %a "$ALLOWLIST")" = 600 || {echo ALLOWLIST_MUST_BE_0600;exit 4;}
set --
while IFS= read -r line || test -n "$line"; do
  line="$(printf '%s' "$line" | tr -d '\r')"
  test -n "$line" || continue
  case "$line" in *'*'*|*','*)echo WILDCARD_OR_COMMA_NOT_ALLOWED;exit 5;;esac
  if ! printf '%s\n' "$line" | grep -Eq '^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[A-Za-z]{2,}$';then
     echo INVALID_EMAIL;exit 5
  fi
  set -- "$@" --allowed-mail "$line"
done <"$ALLOWLIST"
test "$#" -ge 2 || {echo NO_EMAIL_ALLOWLIST;exit 6;}
if ! "$BIN" tunnel --help 2>&1 | grep -q -- '--allowed-mail';then echo CANNOT_VERIFY_PROTECTED_FLAG;exit 7;fi
curl -fsS --max-time 5 'http://127.0.0.1:18080/health' >/dev/null || {echo STAGING_UNHEALTHY;exit 8;}
umask 077
nohup "$BIN" tunnel --url http://127.0.0.1:18080 "$@" \
  >"$BASE/logs/cloudflared.log" 2>&1 </dev/null &
echo "$!" >"$BASE/runtime/cloudflared.pid"
echo PROTECTED_TUNNEL_START_ATTEMPTED_VERIFY_OTP_BEFORE_SHARE
