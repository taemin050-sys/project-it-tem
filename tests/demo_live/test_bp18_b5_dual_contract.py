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
    (repo / "app/package-lock.json").write_text('{"name":"synthetic-frontend","lockfileVersion":3}\n')
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
with (root / "control-calls").open("a") as calls:
    calls.write(command + " " + " ".join(args) + "\\n")
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


def _install_dual_contract(root, args, approval, capsys):
    assert contract.main([*args, "prepare", "--approval", str(approval)]) == 0
    raw = capsys.readouterr().out
    path = root / guard.DUAL_CONTRACT_FILE
    path.write_text(raw)
    path.chmod(0o600)
    return json.loads(raw)


INVENTORY_MUTATIONS = (
    "extra_python", "extra_native", "extra_pth", "executable_script",
    "symlink_file", "symlink_directory", "unknown_frontend_js", "deleted_file",
    "chmod_user_execute", "chmod_group_execute", "chmod_other_execute",
)


def _mutate_release(release, mutation):
    if mutation in {"extra_python", "extra_native", "extra_pth", "executable_script"}:
        relative, raw = {
            "extra_python": ("sitecustomize.py", b"raise RuntimeError('unexpected code')\n"),
            "extra_native": ("injected.so", b"synthetic native library\n"),
            "extra_pth": ("injected.pth", b"import injected\n"),
            "executable_script": ("injected-helper", b"#!/bin/sh\nexit 1\n"),
        }[mutation]
        target = release / relative
        target.write_bytes(raw)
        if mutation == "executable_script":
            target.chmod(0o755)
    elif mutation == "symlink_file":
        (release / "injected.py").symlink_to("README.md")
    elif mutation == "symlink_directory":
        (release / "injected-directory").symlink_to("demo_staging", target_is_directory=True)
    elif mutation == "unknown_frontend_js":
        target = release / "app/dist/assets/unreviewed.js"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("window.unreviewed = true;\n")
    elif mutation == "deleted_file":
        (release / "README.md").unlink()
    else:
        execute = {"chmod_user_execute": 0o100, "chmod_group_execute": 0o010,
                   "chmod_other_execute": 0o001}[mutation]
        (release / "README.md").chmod(0o644 | execute)


@pytest.mark.parametrize("mutation", INVENTORY_MUTATIONS)
def test_complete_inventory_rejects_unreviewed_release_changes_at_every_gate(
        staged_pair, capsys, mutation):
    root, args, approval, forward, rollback, _ = staged_pair
    document = _install_dual_contract(root, args, approval, capsys)
    assert document["version"] == 2
    assert set(document["release_inventories"]) == {forward, rollback}
    _install_synthetic_auth_and_review_contracts(root, (forward, rollback))
    _seed_runtime(root)
    before = _runtime_digests(root)
    _mutate_release(root / "releases" / forward, mutation)

    for command in (
        ["inspect", "--forward", forward, "--rollback", rollback],
        ["prepare", "--approval", str(approval)],
        ["verify", "--approval", str(approval)],
    ):
        assert contract.main([*args, *command]) == guard.EXIT_DENY
        result = capsys.readouterr()
        assert not result.out
        assert "BP18_DUAL_CONTRACT_DENIED:" in result.err
    with pytest.raises(guard.ReleaseUnsafe):
        guard.validate(root, mode="web", port=0, target_override=forward)
    assert _runtime_digests(root) == before


def _record_frontend(root, args, sha, capsys, *, private=False):
    release = root / "releases" / sha
    for relative, raw in {
        "app/dist/index.html": '<script src="/assets/index.js"></script>\n',
        "app/dist/assets/index.js": "window.syntheticBuild = true;\n",
        "app/dist/assets/index.css": "body { color: black; }\n",
    }.items():
        destination = release / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(raw)
        destination.chmod(0o600 if private else 0o644)
    assert contract.main([*args, "record-frontend", "--release", sha,
                          "--build-reference", "SYNTHETIC_LOCAL_BUILD_LOG"]) == 0
    raw = capsys.readouterr().out
    path = root.parent / ("frontend-build-" + sha + ".json")
    path.write_text(raw)
    path.chmod(0o600)
    return path


def _approve_frontend(root, args, approval, forward, rollback, record, capsys):
    build_args = [*args, "--frontend-build", str(record)]
    assert contract.main([*build_args, "inspect", "--forward", forward,
                          "--rollback", rollback]) == 0
    evidence = json.loads(capsys.readouterr().out)
    assert evidence.pop("evidence_only") is True
    approval.write_text(json.dumps({**evidence, "approval_reference": "SYNTHETIC_BUILD_REVIEW"}))
    return build_args, _install_dual_contract(root, build_args, approval, capsys)


@pytest.mark.parametrize("private", [False, True], ids=["public-assets", "private-assets"])
def test_frontend_build_requires_external_record_and_pins_exact_inventory(
        staged_pair, capsys, private):
    root, args, approval, forward, rollback, _ = staged_pair
    record = _record_frontend(root, args, forward, capsys, private=private)
    assert record.is_relative_to(root.parent) and not record.is_relative_to(root / "releases")
    build = json.loads(record.read_text())
    assert "approval_reference" not in build and "evidence_only" not in build
    assert build["command"] == "npm run build"
    assert contract.main([*args, "inspect", "--forward", forward,
                          "--rollback", rollback]) == guard.EXIT_DENY
    assert "DUAL_STAGED_UNEXPECTED_FILES" in capsys.readouterr().err
    build_args, document = _approve_frontend(root, args, approval, forward, rollback,
                                             record, capsys)
    inventory = document["release_inventories"][forward]
    assert inventory["frontend_build"] == build
    assert inventory["files"] == guard.release_inventory(root / "releases" / forward)
    assert json.loads(approval.read_text())["forward"]["inventory_sha256"] == guard.canonical_sha(inventory)
    assert contract.main([*build_args, "verify", "--approval", str(approval)]) == 0
    capsys.readouterr()
    _install_synthetic_auth_and_review_contracts(root, (forward, rollback))
    _seed_runtime(root)
    assert guard.validate(root, mode="web", port=0, target_override=forward)["required_dual"] == guard.DUAL_PROTOCOL


def test_frontend_record_requires_a_tracked_package_lock(staged_pair, capsys):
    root, args, _, forward, _, _ = staged_pair
    repo = Path(args[1])
    git(repo, "rm", "app/package-lock.json")
    git(repo, "-c", "user.name=B5 test", "-c", "user.email=b5-test@example.invalid",
        "commit", "-qm", "Frontend without tracked dependency lock")
    sha = git(repo, "rev-parse", "HEAD")
    release = root / "releases" / sha
    shutil.copytree(root / "releases" / forward, release)
    (release / "app/package-lock.json").unlink()
    (release / "SOURCE_SHA.txt").write_text(sha + "\n")
    (release / "app/dist").mkdir()
    (release / "app/dist/index.html").write_text("synthetic build\n")
    for untracked_lock in (False, True):
        if untracked_lock:
            (release / "app/package-lock.json").write_text('{"lockfileVersion":3}\n')
        assert contract.main([*args, "record-frontend", "--release", sha,
                              "--build-reference", "SYNTHETIC_BUILD"]) == guard.EXIT_DENY
        assert not capsys.readouterr().out


@pytest.mark.parametrize("mutation", ["extra_python", "extra_native", "extra_pth",
                                     "executable_script", "symlink_file", "symlink_directory",
                                     "frontend_native", "frontend_executable"])
def test_frontend_record_cannot_authorize_runtime_code(staged_pair, capsys, mutation):
    root, args, _, forward, _, _ = staged_pair
    _record_frontend(root, args, forward, capsys)
    release = root / "releases" / forward
    if mutation == "frontend_native":
        (release / "app/dist/assets/native.so").write_bytes(b"synthetic native library\n")
    elif mutation == "frontend_executable":
        (release / "app/dist/assets/index.js").chmod(0o755)
    else:
        _mutate_release(release, mutation)
    assert contract.main([*args, "record-frontend", "--release", forward,
                          "--build-reference", "SYNTHETIC_BUILD"]) == guard.EXIT_DENY
    result = capsys.readouterr()
    assert not result.out and "BP18_DUAL_CONTRACT_DENIED:" in result.err


@pytest.mark.parametrize("mutation", ["tree_sha", "package_lock_sha256", "command",
                                     "file_sha256", "file_mode", "duplicate_key"])
def test_frontend_build_provenance_tampering_is_denied(staged_pair, capsys, mutation):
    root, args, approval, forward, rollback, _ = staged_pair
    record = _record_frontend(root, args, forward, capsys)
    build_args, _ = _approve_frontend(root, args, approval, forward, rollback, record, capsys)
    build = json.loads(record.read_text())
    if mutation in {"tree_sha", "package_lock_sha256"}:
        build[mutation] = "0" * (40 if mutation == "tree_sha" else 64)
    elif mutation == "command":
        build["command"] = "npm run unreviewed-command"
    elif mutation == "file_sha256":
        build["files"]["app/dist/assets/index.js"]["sha256"] = "0" * 64
    elif mutation == "file_mode":
        build["files"]["app/dist/assets/index.js"]["mode"] = "0755"
    raw = json.dumps(build)
    if mutation == "duplicate_key":
        raw = '{"version":1,' + raw[1:]
    record.write_text(raw)
    for command in (["inspect", "--forward", forward, "--rollback", rollback],
                    ["prepare", "--approval", str(approval)],
                    ["verify", "--approval", str(approval)]):
        assert contract.main([*build_args, *command]) == guard.EXIT_DENY
        result = capsys.readouterr()
        assert not result.out and "BP18_DUAL_CONTRACT_DENIED:" in result.err


@pytest.mark.parametrize("mutation", ["bytes", "new_file", "deleted_file", "build_reference"])
def test_frontend_changes_need_new_inventory_approval(staged_pair, capsys, mutation):
    root, args, approval, forward, rollback, _ = staged_pair
    record = _record_frontend(root, args, forward, capsys)
    build_args, _ = _approve_frontend(root, args, approval, forward, rollback, record, capsys)
    release = root / "releases" / forward
    build = json.loads(record.read_text())
    if mutation == "bytes":
        (release / "app/dist/assets/index.js").write_text("window.changedAfterReview = true;\n")
    elif mutation == "new_file":
        (release / "app/dist/assets/unreviewed.js").write_text("window.unreviewed = true;\n")
    elif mutation == "deleted_file":
        (release / "app/dist/assets/index.css").unlink()
    else:
        build["build_reference"] = "DIFFERENT_BUILD_ENVIRONMENT"
    # Even a freshly generated, internally matching record cannot replace approval.
    build["files"] = {name: metadata for name, metadata in guard.release_inventory(release).items()
                      if name.startswith("app/dist/")}
    record.write_text(json.dumps(build))
    for command in (["prepare", "--approval", str(approval)],
                    ["verify", "--approval", str(approval)]):
        assert contract.main([*build_args, *command]) == guard.EXIT_DENY
        assert "DUAL_APPROVED_SOURCE_EVIDENCE_MISMATCH" in capsys.readouterr().err
    if mutation != "build_reference":
        with pytest.raises(guard.ReleaseUnsafe):
            guard.required_dual_contract(root, forward, activating=True)


@pytest.mark.parametrize("mutation", ["command", "release_sha", "package_lock_sha256", "files"])
def test_prestart_rejects_malformed_installed_frontend_provenance(staged_pair, capsys, mutation):
    root, args, approval, forward, rollback, _ = staged_pair
    record = _record_frontend(root, args, forward, capsys)
    _, document = _approve_frontend(root, args, approval, forward, rollback, record, capsys)
    build = document["release_inventories"][forward]["frontend_build"]
    if mutation == "command":
        build["command"] = "npm run unreviewed-command"
    elif mutation == "release_sha":
        build["release_sha"] = rollback
    elif mutation == "package_lock_sha256":
        build["package_lock_sha256"] = "0" * 64
    else:
        build["files"]["app/dist/assets/index.js"]["sha256"] = "0" * 64
    (root / guard.DUAL_CONTRACT_FILE).write_text(json.dumps(document))
    with pytest.raises(guard.ReleaseUnsafe):
        guard.required_dual_contract(root, forward, activating=True)


def test_prestart_and_verifier_reject_duplicate_installed_contract_keys(staged_pair, capsys):
    root, args, approval, forward, _, _ = staged_pair
    _install_dual_contract(root, args, approval, capsys)
    path = root / guard.DUAL_CONTRACT_FILE
    path.write_text('{"version":2,' + path.read_text()[1:])
    assert contract.main([*args, "verify", "--approval", str(approval)]) == guard.EXIT_DENY
    assert "DUAL_OPERATOR_FILE_DUPLICATE_KEYS" in capsys.readouterr().err
    with pytest.raises(guard.ReleaseUnsafe):
        guard.required_dual_contract(root, forward, activating=True)


@pytest.mark.parametrize("ancestor", ["releases", "release"])
def test_inventory_verification_rejects_symlinked_release_ancestors(staged_pair, capsys, ancestor):
    root, args, approval, forward, rollback, _ = staged_pair
    _install_dual_contract(root, args, approval, capsys)
    source = root / "releases" if ancestor == "releases" else root / "releases" / forward
    saved = root.parent / ("saved-" + ancestor)
    source.rename(saved)
    source.symlink_to(saved, target_is_directory=True)
    for command in (["inspect", "--forward", forward, "--rollback", rollback],
                    ["prepare", "--approval", str(approval)],
                    ["verify", "--approval", str(approval)]):
        assert contract.main([*args, *command]) == guard.EXIT_DENY
        assert "DUAL_STAGED_DIRECTORY_INVALID" in capsys.readouterr().err
    with pytest.raises(guard.ReleaseUnsafe, match="DUAL_STAGED_DIRECTORY_INVALID"):
        guard.required_dual_contract(root, forward, activating=True)


@pytest.mark.parametrize("mutation", ["version_one", "sources_list", "inventories_list"])
def test_prestart_requires_version_two_full_inventory_contract(staged_pair, capsys, mutation):
    root, args, approval, forward, _, _ = staged_pair
    document = _install_dual_contract(root, args, approval, capsys)
    if mutation == "version_one":
        document["version"] = 1
        document.pop("release_inventories")
    elif mutation == "sources_list":
        document["verified_sources"] = []
    else:
        document["release_inventories"] = []
    (root / guard.DUAL_CONTRACT_FILE).write_text(json.dumps(document))
    with pytest.raises(guard.ReleaseUnsafe):
        guard.required_dual_contract(root, forward, activating=True)


@pytest.mark.parametrize("role", ["forward", "rollback"])
@pytest.mark.parametrize("mutation", ["extra_python", "extra_native", "extra_pth",
                                     "executable_script", "symlink_file", "symlink_directory",
                                     "unknown_frontend_js", "deleted_file", "chmod_user_execute"])
def test_control_rejects_changed_candidate_or_fallback_before_stop(
        staged_pair, capsys, role, mutation):
    root, args, approval, forward, rollback, _ = staged_pair
    _install_dual_contract(root, args, approval, capsys)
    _install_synthetic_auth_and_review_contracts(root, (forward, rollback))
    _seed_runtime(root)
    before = _runtime_digests(root)
    entry, env = _control_harness(root, forward)
    target = forward if role == "forward" else rollback
    _mutate_release(root / "releases" / target, mutation)
    result = subprocess.run(["bash", str(entry), forward], env=env, capture_output=True, text=True)
    assert result.returncode == guard.EXIT_DENY, result.stdout + result.stderr
    assert "BP18_RELEASE_PRESTART_DENIED:" in result.stdout
    assert (root / "repo").readlink() == Path("releases") / rollback
    assert (root / "unit-state").read_text() == "active\n"
    assert "systemctl --user stop" not in (root / "control-calls").read_text()
    assert "BP18_B5_SQLITE_SIX_BACKUPS_VERIFIED" not in result.stdout
    assert _runtime_digests(root) == before
    assert not (root / "backups").exists()
