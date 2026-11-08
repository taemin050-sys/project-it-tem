#!/usr/bin/env bash
# Sole sanctioned B promotion/rollback entrypoint after systemd conversion.
# Never use the older ad-hoc nohup deploy scripts against the policy-epoch DB.
set -euo pipefail
umask 077
ROOT=/home/macstudio/ittem-bp18-product-completion-20261111
CONTROL="$ROOT/control"
UNIT=ittem-bp18-b.service
TARGET="${1:-}"
case "$TARGET" in
  *[!a-f0-9]*|"") echo "DENY_TARGET_SHA_INVALID" >&2;exit 78;;
esac
test "${#TARGET}" -eq 40 || exit 78
exec 8>"$ROOT/config/.b5_operator_control.lock"
flock -n 8 || { echo "DENY_ANOTHER_RELEASE_OPERATION";exit 78; }
CURRENT="$(readlink "$ROOT/repo")"
case "$CURRENT" in releases/*) ;; *) echo "DENY_BAD_SOURCE_SYMLINK";exit 78;; esac
FROM="${CURRENT#releases/}"
test "$FROM" != "$TARGET" || { echo "NOOP_CURRENT_RELEASE";exit 0; }
test -f "$ROOT/releases/$TARGET/SOURCE_SHA.txt"
test "$(cat "$ROOT/releases/$TARGET/SOURCE_SHA.txt")" = "$TARGET"

# Both candidate AND fallback must be epoch compatible with the *current* DB.
# Runs BEFORE stopping the live service. Port 0 skips active current port.
python3 "$CONTROL/bp18_release_prestart.py" --mode web --port 0 --target "$TARGET"
python3 "$CONTROL/bp18_release_prestart.py" --mode web --port 0 --target "$FROM"

test "$(systemctl --user is-active "$UNIT")" = active || {
 echo "DENY_CURRENT_UNIT_NOT_ACTIVE";exit 78;
}
PID="$(systemctl --user show "$UNIT" -p MainPID --value)"
case "$PID" in ''|0) echo "DENY_MISSING_MAIN_PID";exit 78;; esac
case "$(ps -p "$PID" -o args=)" in
  *"$ROOT/repo"*"--port 18100"*) ;;
  *) echo "DENY_UNEXPECTED_ACTIVE_PROCESS_OWNER";exit 78;;
esac
test "$(cat "$ROOT/web.pid")" = "$PID"

# Immutable six-database online backup before any stop/symlink change.
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
python3 "$CONTROL/bp18_backup_runtime.py" "$STAMP"

systemctl --user stop "$UNIT"
for i in 1 2 3 4 5 6 7 8 9;do
 if ! ss -lnt |grep -q '127.0.0.1:18100 ';then break;fi
 sleep .5
done
if ss -lnt|grep -q '127.0.0.1:18100 ';then
 echo "DENY_CURRENT_PROCESS_STILL_LISTENING" >&2
 systemctl --user start "$UNIT" || true
 exit 78
fi

restore(){
 # Only trusted fallback: its explicit epoch guard must permit restoration.
 ln -s "releases/$FROM" "$ROOT/.b5-restore-$FROM"
 mv -Tf "$ROOT/.b5-restore-$FROM" "$ROOT/repo"
 if python3 "$CONTROL/bp18_release_prestart.py" --mode web --port 18100;then
  systemctl --user start "$UNIT"
  echo "ROLLBACK_TO_VERIFIED_OLD_RELEASE=$FROM"
 else
  echo "CRITICAL_FALLBACK_DENIED_RELEASE_STAYS_STOPPED" >&2
  exit 91
 fi
}
ln -s "releases/$TARGET" "$ROOT/.b5-next-$TARGET"
mv -Tf "$ROOT/.b5-next-$TARGET" "$ROOT/repo"
if ! systemctl --user start "$UNIT";then
 echo "TARGET_START_FAILED_FALLBACK_REQUIRED" >&2
 restore
 exit 93
fi
# systemd Type=simple reports "active" before ASGI lifespan startup.
# Wait for a bounded ready check before deciding rollback; no provider I/O.
READY=NO
for i in 1 2 3 4 5 6 7 8 9 10 11 12;do
 if curl -fsS --max-time 2 http://127.0.0.1:18100/health >/dev/null 2>&1;then
  READY=YES
  break
 fi
 sleep .5
done
if [ "$READY" != YES ];then
 echo "TARGET_HEALTH_FAILED_FALLBACK_REQUIRED" >&2
 systemctl --user stop "$UNIT"
 restore
 exit 94
fi
test "$(cat "$ROOT/repo/SOURCE_SHA.txt")" = "$TARGET"
test "$(systemctl --user is-active "$UNIT")" = active
echo "BP18_B5_CONTROLLED_PROMOTION_PASS from=$FROM to=$TARGET"
echo "WORKER_NOT_ENABLED_BY_THIS_SCRIPT"
