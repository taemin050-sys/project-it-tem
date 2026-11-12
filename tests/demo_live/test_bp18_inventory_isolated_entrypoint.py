"""Trusted inventory guards must start before any candidate Python code runs."""
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

import pytest

from test_bp18_b5_dual_contract import (
    SOURCE_ROOT, _control_harness, _install_dual_contract,
    _install_synthetic_auth_and_review_contracts, _runtime_digests,
    _seed_runtime, staged_pair,
)
from scripts import bp18_b5_release_prestart as guard


def _trusted_entrypoints(root):
    control = root / "isolated-control"
    control.mkdir()
    prestart = control / "bp18_b5_release_prestart.py"
    prestart.write_text((SOURCE_ROOT / "scripts/bp18_b5_release_prestart.py").read_text()
                        .replace(str(guard.PRODUCTION_ROOT), str(root)))
    cli = control / "bp18_b5_dual_contract.py"
    shutil.copyfile(SOURCE_ROOT / "scripts/bp18_b5_dual_contract.py", cli)
    return prestart, cli


def _poisoned_environment(release):
    env = {name: value for name, value in os.environ.items() if not name.startswith("OPENAI_")}
    env["PYTHONPATH"] = str(release)
    return env


def _inject_startup_exit(release, marker):
    # Startup imports this before even parsing the trusted script or its arguments.
    (release / "sitecustomize.py").write_text(
        "import os\nfrom pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('candidate startup code ran')\n"
        "os._exit(0)\n")


def _assert_unsafe_invocation_is_bypassed(script, arguments, env, release, marker):
    result = subprocess.run([sys.executable, str(script), *arguments], env=env,
                            cwd=release, capture_output=True, text=True)
    assert result.returncode == 0
    assert not result.stdout and not result.stderr
    assert marker.read_text() == "candidate startup code ran"
    marker.unlink()


def test_isolated_prestart_denies_startup_injection_before_candidate_code(staged_pair, capsys):
    root, args, approval, forward, rollback, _ = staged_pair
    _install_dual_contract(root, args, approval, capsys)
    _install_synthetic_auth_and_review_contracts(root, (forward, rollback))
    _seed_runtime(root)
    before = _runtime_digests(root)
    prestart, _ = _trusted_entrypoints(root)
    release = root / "releases" / forward
    env = _poisoned_environment(release)
    arguments = ["--mode", "web", "--port", "0", "--target", forward]
    command = [sys.executable, "-I", "-S", str(prestart), *arguments]

    baseline = subprocess.run(command, env=env, cwd=release, capture_output=True, text=True)
    assert baseline.returncode == 0, baseline.stdout + baseline.stderr
    assert "BP18_RELEASE_PRESTART_PASS" in baseline.stdout
    marker = root.parent / "prestart-startup-ran"
    _inject_startup_exit(release, marker)
    _assert_unsafe_invocation_is_bypassed(prestart, arguments, env, release, marker)

    result = subprocess.run(command, env=env, cwd=release, capture_output=True, text=True)
    assert result.returncode == guard.EXIT_DENY, result.stdout + result.stderr
    assert "BP18_RELEASE_PRESTART_DENIED:" in result.stdout
    assert not marker.exists()
    assert env["PYTHONPATH"] == str(release)
    assert _runtime_digests(root) == before


def test_isolated_standalone_cli_denies_startup_injection(staged_pair, capsys):
    root, args, _, forward, rollback, _ = staged_pair
    _, cli = _trusted_entrypoints(root)
    release = root / "releases" / forward
    env = _poisoned_environment(release)
    arguments = [*args, "inspect", "--forward", forward, "--rollback", rollback]
    command = [sys.executable, "-I", "-S", str(cli), *arguments]
    baseline = subprocess.run(command, env=env, cwd=release, capture_output=True, text=True)
    assert baseline.returncode == 0, baseline.stdout + baseline.stderr
    assert json.loads(baseline.stdout)["version"] == 2
    marker = root.parent / "cli-startup-ran"
    _inject_startup_exit(release, marker)
    _assert_unsafe_invocation_is_bypassed(cli, arguments, env, release, marker)

    result = subprocess.run(command, env=env, cwd=release, capture_output=True, text=True)
    assert result.returncode == guard.EXIT_DENY, result.stdout + result.stderr
    assert "DUAL_STAGED_UNEXPECTED_FILES" in result.stderr
    assert not result.stdout and not marker.exists()


def test_shell_control_ignores_startup_injection_and_preserves_running_release(staged_pair, capsys):
    root, args, approval, forward, rollback, _ = staged_pair
    _install_dual_contract(root, args, approval, capsys)
    _install_synthetic_auth_and_review_contracts(root, (forward, rollback))
    _seed_runtime(root)
    before = _runtime_digests(root)
    entry, env = _control_harness(root, forward)
    # The fixture emulates native flock/systemctl with Python; keep its own
    # interpreter startup isolated so only the real control commands are tested.
    shim = root / "test-commands/shim.py"
    shim.write_text(shim.read_text().replace("#!/usr/bin/env python3\n",
                                            "#!/usr/bin/env -S python3 -I -S\n", 1))
    release = root / "releases" / forward
    marker = root.parent / "control-startup-ran"
    _inject_startup_exit(release, marker)
    env["PYTHONPATH"] = str(release)
    result = subprocess.run(["bash", str(entry), forward], env=env, cwd=release,
                            capture_output=True, text=True)
    assert result.returncode == guard.EXIT_DENY, result.stdout + result.stderr
    assert "BP18_RELEASE_PRESTART_DENIED:" in result.stdout
    assert not marker.exists()
    assert (root / "unit-state").read_text() == "active\n"
    assert (root / "repo").readlink() == Path("releases") / rollback
    assert "systemctl --user stop" not in (root / "control-calls").read_text()
    assert not (root / "backups").exists()
    assert _runtime_digests(root) == before


def test_shell_control_starts_every_trusted_python_process_with_isolation():
    source = (SOURCE_ROOT / "deploy/systemd/bp18_release_control.sh").read_text()
    calls = [shlex.split(re.sub(r"^\s*if\s+", "", line.strip()))
             for line in source.splitlines() if re.match(r"^\s*(?:if\s+)?python3\s+", line)]
    assert len(calls) >= 4
    assert all(call[:3] == ["python3", "-I", "-S"] for call in calls)
    assert any("bp18_backup_runtime.py" in call[3] for call in calls)
    assert any("bp18_release_prestart.py" in call[3] for call in calls)


@pytest.mark.parametrize(("filename", "mode", "port"), [
    ("ittem-bp18-b.service", "web", "18100"),
    ("ittem-bp18-b-worker.service", "worker", "0"),
])
def test_systemd_prestart_isolates_python_before_loading_guard(filename, mode, port):
    source = (SOURCE_ROOT / "deploy/systemd" / filename).read_text()
    prestarts = [shlex.split(line.partition("=")[2]) for line in source.splitlines()
                if line.startswith("ExecStartPre=")]
    assert prestarts == [["/usr/bin/python3", "-I", "-S",
                          str(guard.PRODUCTION_ROOT / "control/bp18_release_prestart.py"),
                          "--mode", mode, "--port", port]]
