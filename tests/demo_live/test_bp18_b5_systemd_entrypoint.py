"""Static authority test: both B web entrypoints must invoke prestart guard."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
UNIT=ROOT/"deploy/systemd/ittem-bp18-b.service"
WEB=ROOT/"deploy/systemd/bp18_web_exec.sh"
CONTROL=ROOT/"deploy/systemd/bp18_release_control.sh"
BACKUP=ROOT/"deploy/systemd/bp18_backup_runtime.py"


def test_b_systemd_uses_independent_prestart_and_nonbillable_web():
    data=UNIT.read_text()
    assert data.count("ExecStartPre=")==1
    assert "control/bp18_release_prestart.py --mode web --port 18100" in data
    assert "control/bp18_web_exec.sh" in data
    assert "IT_TEM_QA_FIXTURE_ENABLED=NO" in data
    assert "IT_TEM_LIVE_ENABLED=NO" in data
    assert "IT_TEM_LIVE_EXECUTION_APPROVED=NO" in data
    assert "IT_TEM_LIVE_WEB_QUEUE_ENABLED=NO" in data
    assert "IT_TEM_PROVIDER_READINESS_CONFIRMED=NO" in data
    assert "EnvironmentFile=" not in data
    assert "OPENAI_API_KEY" not in data


def test_web_executor_single_process_lock_and_loopback_only():
    s=WEB.read_text()
    assert "flock -n 9" in s
    assert 'echo "$$" > "$ROOT/web.pid"' in s
    assert "exec /home/macstudio/ittem-a-template-ui-test-20261102/.venv/bin/python" in s
    assert "--host 127.0.0.1 --port 18100" in s
    assert "0.0.0.0" not in s


def test_control_prechecks_both_target_and_fallback_before_stopping():
    s=CONTROL.read_text()
    token="bp18_release_prestart.py"
    assert s.count(token)==3
    a=s.index('--target "$TARGET"')
    b=s.index('--target "$FROM"')
    c=s.index('systemctl --user stop "$UNIT"')
    assert a<b<c
    assert "bp18_backup_runtime.py" in s
    assert s.index('bp18_backup_runtime.py')<c
    assert "systemctl --user start" in s
    assert "ROLLBACK_TO_VERIFIED_OLD_RELEASE" in s


def test_sqlite_backup_never_overwrites_and_has_integrity_check():
    s=BACKUP.read_text()
    assert "exist_ok=False" in s
    assert "origin.backup(saved)" in s
    assert "PRAGMA integrity_check" in s
    assert 'live/cost.sqlite' in s and 'live/queue.sqlite' in s
