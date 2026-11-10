"""Local-only review and B5 control rehearsals with throwaway releases and ledgers."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

import pytest

from scripts import bp18_b5_dual_contract as contract
from scripts import bp18_b5_release_prestart as guard


SOURCE_ROOT = Path(__file__).resolve().parents[2]


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True).stdout.decode().strip()


@pytest.fixture
def staged_pair(tmp_path, capsys):
    repo = tmp_path / "isolated-source"
    repo.mkdir()
    git(repo, "init", "-q")
    (repo / "README.md").write_text("Review this exact release\n")
    git(repo, "add", "README.md")
    identity = ("-c", "user.name=B5 test", "-c", "user.email=b5-test@example.invalid")
    git(repo, *identity, "commit", "-qm", "Pre-Dual test release")
    legacy = git(repo, "rev-parse", "HEAD")
    for name in sorted(set(guard.DUAL_SOURCE_FILES + guard.SSO_SOURCE_FILES + guard.REVIEW_SOURCE_FILES)):
        destination = repo / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE_ROOT / name, destination)
    git(repo, "add", ".")
    git(repo, *identity, "commit", "-qm", "Compatible fallback fixture")
    rollback = git(repo, "rev-parse", "HEAD")
    (repo / "README.md").write_text("Review the forward release\n")
    git(repo, "add", "README.md")
    git(repo, *identity, "commit", "-qm", "Compatible forward fixture")
    forward = git(repo, "rev-parse", "HEAD")

    root = tmp_path / "isolated-b5"
    (root / "config").mkdir(parents=True)
    for sha in (legacy, rollback, forward):
        release = root / "releases" / sha
        release.mkdir(parents=True)
        names = git(repo, "ls-tree", "-r", "--name-only", sha).splitlines()
        for name in names:
            staged = release / name
            staged.parent.mkdir(parents=True, exist_ok=True)
            staged.write_bytes(subprocess.check_output(["git", "-C", str(repo), "show", f"{sha}:{name}"]))
        (release / "SOURCE_SHA.txt").write_text(sha + "\n")
    (root / "repo").symlink_to("releases/" + rollback)
    (root / "config/epoch_capable_shas.txt").write_text(f"{forward}\n{rollback}\n{legacy}\n")

    args = ["--git-repo", str(repo), "--staging-root", str(root)]
    assert contract.main([*args, "inspect", "--forward", forward, "--rollback", rollback]) == 0
    evidence = json.loads(capsys.readouterr().out)
    assert evidence.pop("evidence_only") is True
    approval = tmp_path / "synthetic-operator-approval.json"
    approval.write_text(json.dumps({**evidence, "approval_reference": "SYNTHETIC_B5_TEST_ONLY"}))
    approval.chmod(0o600)
    return root, args, approval, forward, rollback, legacy


def test_prepared_contract_verifies_both_approved_releases(staged_pair, capsys):
    root, args, approval, forward, rollback, _ = staged_pair
    path = root / guard.DUAL_CONTRACT_FILE
    assert contract.main([*args, "prepare", "--approval", str(approval)]) == 0
    prepared = capsys.readouterr().out
    assert not path.exists()
    path.write_text(prepared)
    path.chmod(0o600)
    assert contract.main([*args, "verify", "--approval", str(approval)]) == 0
    assert capsys.readouterr().out.startswith("BP18_DUAL_CONTRACT_VERIFIED")
    for sha in (forward, rollback):
        assert guard.required_dual_contract(root, sha, activating=True)["required_mode"] == guard.DUAL_PROTOCOL
    document = json.loads(prepared)
    document["verified_sources"].pop(rollback)
    path.write_text(json.dumps(document))
    assert contract.main([*args, "verify", "--approval", str(approval)]) == guard.EXIT_DENY
    assert "DUAL_CONTRACT_VERIFICATION_MISMATCH" in capsys.readouterr().err


@pytest.mark.parametrize(("mutation", "error"), [
    ("nonprotocol", "DUAL_STAGED_TREE_MISMATCH"),
    ("source_marker", "DUAL_STAGED_RELEASE_SHA_MISMATCH"),
    ("source_symlink", "DUAL_STAGED_DIRECTORY_INVALID"),
    ("protocol_fingerprint", "DUAL_APPROVED_SOURCE_EVIDENCE_MISMATCH"),
    ("evidence_only", "DUAL_OPERATOR_APPROVAL_INVALID"),
    ("duplicate_key", "DUAL_OPERATOR_FILE_DUPLICATE_KEYS"),
    ("approval_permissions", "RELEASE_METADATA_PERMISSIONS_INVALID"),
    ("same_release", "DUAL_FORWARD_AND_ROLLBACK_MUST_BE_DISTINCT"),
    ("legacy", "LIVE_DUAL_REQUIRED_PROTOCOL_CODE_MISSING"),
])
def test_malformed_unreviewed_or_legacy_sources_fail_closed(staged_pair, capsys, mutation, error):
    root, args, approval, forward, _, legacy = staged_pair
    release = root / "releases" / forward
    record = json.loads(approval.read_text())
    if mutation == "nonprotocol":
        (release / "README.md").write_text("Changed outside the protocol file set")
    elif mutation == "source_marker":
        (release / "SOURCE_SHA.txt").write_text(legacy)
    elif mutation == "source_symlink":
        source = release / "demo_staging"
        saved = source.rename(release / "outside")
        source.symlink_to(saved)
    elif mutation == "protocol_fingerprint":
        record["forward"]["protocol_sha256"] = "0" * 64
    elif mutation == "evidence_only":
        record.pop("approval_reference")
        record["evidence_only"] = True
    elif mutation == "approval_permissions":
        approval.chmod(0o666)
    elif mutation == "same_release":
        record["rollback"] = record["forward"]
    elif mutation == "legacy":
        record["rollback"]["release_sha"] = legacy
    raw = json.dumps(record)
    if mutation == "duplicate_key":
        raw = '{"approval_reference":"ambiguous",' + raw[1:]
    approval.write_text(raw)
    assert contract.main([*args, "prepare", "--approval", str(approval)]) == guard.EXIT_DENY
    output = capsys.readouterr()
    assert error in output.err and not output.out
    assert not (root / guard.DUAL_CONTRACT_FILE).exists()


def _seed_runtime(root):
    files = {
        "demo.sqlite3": "CREATE TABLE jobs(id TEXT); INSERT INTO jobs VALUES('protected-job');",
        "live/live.sqlite": "CREATE TABLE live_policy_activation(singleton INT, epoch INT, policy_version TEXT, policy_sha TEXT);"
        f"INSERT INTO live_policy_activation VALUES(1,1,'bp18-f09-fixture','{'e' * 64}');"
        "CREATE TABLE live_paid_dual_groups(parent_job_id TEXT);"
        "INSERT INTO live_paid_dual_groups VALUES('protected-job');",
        "live/queue.sqlite": "CREATE TABLE queued_ops(state TEXT, mode TEXT);"
        "INSERT INTO queued_ops VALUES('BILLING_UNKNOWN','LIVE_DUAL_V1');",
        "live/cost.sqlite": "CREATE TABLE attempts(state TEXT); INSERT INTO attempts VALUES('BILLING_UNKNOWN');",
        "live/shares.sqlite": "CREATE TABLE shares(id TEXT); INSERT INTO shares VALUES('protected-share');",
        "live/text_checkpoints.sqlite": "CREATE TABLE checkpoints(id TEXT); INSERT INTO checkpoints VALUES('protected-checkpoint');",
    }
    for name, script in files.items():
        target = root / "runtime" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(target) as cx:
            cx.executescript(script)
    artifacts = root / "runtime/live/artifacts"
    artifacts.mkdir()
    (artifacts / "protected-caption.txt").write_text("protected approved caption")


def _runtime_digests(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (root / "runtime").rglob("*") if path.is_file()}


def _install_synthetic_auth_and_review_contracts(root, shas):
    for filename, mode, names, detail in (
        (guard.AUTH_CONTRACT_FILE, "TAILNET_SSO_ONLY", guard.SSO_SOURCE_FILES,
         {"expected_host": "macstudio-macstudio.tail17dfff.ts.net:10500"}),
        (guard.REVIEW_CONTRACT_FILE, "RULES_AND_LLM", guard.REVIEW_SOURCE_FILES,
         {"model": "synthetic-review-model"}),
    ):
        verified = {sha: {name: hashlib.sha256((root / "releases" / sha / name).read_bytes()).hexdigest()
                          for name in names} for sha in shas}
        target = root / filename
        target.write_text(json.dumps({"version": 1, "required_mode": mode,
                                      "verified_sources": verified, **detail}))
        target.chmod(0o600)


def _control_harness(root, candidate):
    control = root / "control"
    control.mkdir()
    entry = control / "bp18_release_control.sh"
    sources = (
        ("deploy/systemd/bp18_release_control.sh", entry),
        ("deploy/systemd/bp18_backup_runtime.py", control / "bp18_backup_runtime.py"),
        ("scripts/bp18_b5_release_prestart.py", control / "bp18_release_prestart.py"),
    )
    for source, destination in sources:
        raw = (SOURCE_ROOT / source).read_text()
        destination.write_text(raw.replace(str(guard.PRODUCTION_ROOT), str(root)))
    (root / "web.pid").write_text("4242\n")
    (root / "unit-state").write_text("active\n")
    commands = root / "test-commands"
    commands.mkdir()
    shim = commands / "shim.py"
    shim.write_text("#!/usr/bin/env python3\n" + f"ROOT = {str(root)!r}\n" + f"CANDIDATE = {candidate!r}\n" + '''
import fcntl
import os
from pathlib import Path
import sys

root = Path(ROOT)
command = Path(sys.argv[0]).name
args = sys.argv[1:]
state = root / "unit-state"
if command == "systemctl":
    action = args[1]
    if action == "is-active":
        print(state.read_text().strip())
    elif action == "show":
        print(4242)
    elif action == "stop":
        state.write_text("inactive\\n")
    elif action == "start":
        if ((root / "fail-forward").exists()
                and (root / "repo").readlink().name == CANDIDATE):
            sys.exit(1)
        state.write_text("active\\n")
    else:
        sys.exit(2)
elif command == "ps":
    print(root / "repo", "--port 18100")
elif command == "curl":
    sys.exit(0 if state.read_text().strip() == "active" else 1)
elif command == "flock":
    fcntl.flock(int(args[-1]), fcntl.LOCK_EX | fcntl.LOCK_NB)
elif command == "mv":
    os.replace(args[-2], args[-1])
elif command != "ss":
    sys.exit(2)
''')
    shim.chmod(0o700)
    for name in ("systemctl", "ps", "curl", "flock", "mv", "ss"):
        (commands / name).symlink_to(shim)
    (commands / "python3").symlink_to(sys.executable)
    env = {name: value for name, value in os.environ.items() if not name.startswith("OPENAI_")}
    env["PATH"] = os.pathsep.join((str(commands), "/usr/bin", "/bin"))
    return entry, env


@pytest.mark.parametrize("fails_forward", [False, True], ids=["promote", "rollback"])
def test_b5_control_preserves_protected_runtime_across_approved_swap(staged_pair, capsys, fails_forward):
    root, args, approval, forward, rollback, _ = staged_pair
    assert contract.main([*args, "prepare", "--approval", str(approval)]) == 0
    installed = root / guard.DUAL_CONTRACT_FILE
    installed.write_text(capsys.readouterr().out)
    installed.chmod(0o600)
    _install_synthetic_auth_and_review_contracts(root, (forward, rollback))
    _seed_runtime(root)
    before = _runtime_digests(root)
    entry, env = _control_harness(root, forward)
    if fails_forward:
        (root / "fail-forward").touch()
    result = subprocess.run(["bash", str(entry), forward], env=env, capture_output=True, text=True)
    assert result.returncode == (93 if fails_forward else 0), result.stdout + result.stderr
    expected = rollback if fails_forward else forward
    assert (root / "repo").readlink() == Path("releases") / expected
    assert (root / "unit-state").read_text() == "active\n"
    assert "BP18_B5_SQLITE_SIX_BACKUPS_VERIFIED" in result.stdout
    assert ("ROLLBACK_TO_VERIFIED_OLD_RELEASE=" if fails_forward
            else "BP18_B5_CONTROLLED_PROMOTION_PASS") in result.stdout
    assert _runtime_digests(root) == before
    backup, = (root / "backups").iterdir()
    manifest = json.loads((backup / "MANIFEST_SHA256.json").read_text())
    assert len(manifest["dbs"]) == 6
    for saved in manifest["dbs"]:
        path = backup / saved["db"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == saved["sha256"]
        with sqlite3.connect(path) as cx:
            assert cx.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
