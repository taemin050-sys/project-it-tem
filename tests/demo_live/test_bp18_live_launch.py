"""B launcher tests use only temporary files and a synthetic credential."""
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest


LAUNCHER_PATH = Path(__file__).resolve().parents[2] / "deploy/systemd/bp18_live_launch.py"
SPEC = importlib.util.spec_from_file_location("bp18_live_launch", LAUNCHER_PATH)
launch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launch)
SHA = "a" * 40
FAKE_KEY = "fixture-only-provider-key-never-used"


def private_file(path, contents):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    path.write_text(contents)
    path.chmod(0o600)
    return path


@pytest.fixture
def root(tmp_path, monkeypatch):
    root = tmp_path / "b"
    root.mkdir(mode=0o700)
    release = root / "releases" / SHA
    release.mkdir(parents=True)
    (release / "SOURCE_SHA.txt").write_text(SHA)
    (root / "repo").symlink_to("releases/" + SHA)
    private_file(root / "config/bp18_tailnet_roles.json", json.dumps({
        "bp18_b_exobiz7": "admin", "bp18_b_taemin": "evaluator",
    }))
    monkeypatch.setattr(os, "environ", {
        "IT_TEM_TAILNET_AUTH_ENABLED": "YES",
        "IT_TEM_TAILNET_SSO_ONLY": "YES",
        "IT_TEM_TAILNET_EXPECTED_HOST": launch.HOST,
    })
    return root


def write_policy(root, **changes):
    policy = {
        "IT_TEM_BP18_LIVE_RELEASE_SHA": SHA,
        "IT_TEM_LIVE_APPROVED_ACTORS": "bp18_b_exobiz7,bp18_b_taemin",
        "IT_TEM_TEXT_MODEL": "gpt-6-luna",
        "IT_TEM_VISION_MODEL": "gpt-6-luna",
        "IT_TEM_IMAGE_MODEL": "gpt-image-2.6-sunburst",
        "IT_TEM_IMAGE_QUALITY": "medium",
        "IT_TEM_IMAGE_COMPLEXITY": "high",
    }
    policy.update(changes)
    if policy["IT_TEM_BP18_LIVE_RELEASE_SHA"] == SHA:
        from scripts.bp18_b5_release_prestart import REVIEW_SOURCE_FILES
        release = root / "releases" / SHA
        source_root = LAUNCHER_PATH.parents[2]
        hashes = {}
        for name in REVIEW_SOURCE_FILES:
            data = (source_root / name).read_bytes()
            target = release / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            hashes[name] = hashlib.sha256(data).hexdigest()
        private_file(root / "config/bp18_required_review_contract.json", json.dumps({
            "version": 1, "required_mode": "RULES_AND_LLM", "model": "gpt-6-luna",
            "verified_sources": {SHA: hashes},
        }))
    return private_file(root / "config/bp18_b_live.env",
                        "\n".join(f"{key}={value}" for key, value in policy.items()))


def test_missing_or_stale_policy_keeps_web_disabled_and_worker_denied(root):
    os.environ.update(OPENAI_API_KEY=FAKE_KEY, OPENAI_BASE_URL="https://unapproved.invalid",
                      IT_TEM_BP18_F09_REQUIRED="YES")
    assert launch.configure(root, worker=False) is None
    assert "OPENAI_API_KEY" not in os.environ
    assert "OPENAI_BASE_URL" not in os.environ
    assert os.environ["IT_TEM_LIVE_ENABLED"] == "NO"
    assert os.environ["IT_TEM_BP18_F09_REQUIRED"] == "NO"
    with pytest.raises(launch.LaunchDenied, match="LIVE_POLICY_FOR_CURRENT_RELEASE_REQUIRED"):
        launch.configure(root, worker=True)
    write_policy(root, IT_TEM_BP18_LIVE_RELEASE_SHA="b" * 40)
    assert launch.configure(root, worker=False) is None


def test_web_and_worker_pin_same_actor_model_policy_without_web_key(root):
    write_policy(root)
    web_fingerprint = launch.configure(root, worker=False)
    assert "OPENAI_API_KEY" not in os.environ
    assert os.environ["IT_TEM_ENABLE_BILLABLE_TEXT_CALLS"] == "NO"
    assert os.environ["IT_TEM_BP18_REVIEW_POLICY_ID"] == "bp18-f09-two-stage-policy-v2"
    assert os.environ["IT_TEM_BP18_F11_ENABLED"] == "YES"
    assert os.environ["IT_TEM_BP18_F09_REQUIRED"] == "YES"
    assert os.environ["OPENAI_MODEL_TEXT"] == os.environ["IT_TEM_TEXT_MODEL"]
    assert launch.configure(root, worker=True) == web_fingerprint
    assert os.environ["IT_TEM_ENABLE_BILLABLE_TEXT_CALLS"] == "YES"


def test_live_policy_alone_cannot_activate_two_stage_epoch(root):
    write_policy(root)
    (root / "config/bp18_required_review_contract.json").unlink()
    for worker in (False, True):
        with pytest.raises(launch.LaunchDenied, match="LIVE_POLICY_REVIEW_CONTRACT_REQUIRED"):
            launch.configure(root, worker=worker)
        assert os.environ["IT_TEM_BP18_F09_REQUIRED"] == "NO"


@pytest.mark.parametrize("change,code", [
    ({"IT_TEM_LIVE_APPROVED_ACTORS": "*"}, "ACTORS_INVALID"),
    ({"IT_TEM_LIVE_APPROVED_ACTORS": "bp18_a_admin"}, "ACTORS_INVALID"),
    ({"IT_TEM_LIVE_APPROVED_ACTORS": "bp18_b_unknown"}, "ACTOR_NOT_REGISTERED"),
    ({"IT_TEM_IMAGE_COMPLEXITY": ""}, "EXPLICIT_COMPLEXITY_REQUIRED"),
    ({"OPENAI_API_KEY": FAKE_KEY}, "KEYS_INVALID"),
])
def test_operator_policy_rejects_invalid_actor_model_and_secret_fields(root, change, code):
    write_policy(root, **change)
    with pytest.raises(launch.LaunchDenied, match=code):
        launch.configure(root, worker=True)
    assert "OPENAI_API_KEY" not in os.environ
    assert os.environ["IT_TEM_LIVE_ENABLED"] == "NO"


def test_policy_requires_real_signed_b_auth_and_private_operator_file(root):
    policy = write_policy(root)
    os.environ["IT_TEM_TAILNET_SSO_ONLY"] = "NO"
    with pytest.raises(launch.LaunchDenied, match="SIGNED_B_SSO_REQUIRED"):
        launch.configure(root, worker=True)
    os.environ["IT_TEM_TAILNET_SSO_ONLY"] = "YES"
    policy.chmod(0o644)
    with pytest.raises(launch.LaunchDenied, match="PRIVATE_FILE_REQUIRED"):
        launch.configure(root, worker=True)


def test_ephemeral_credential_only_loads_key_and_approved_api_origin(root, tmp_path):
    directory = tmp_path / "credentials"
    credential = private_file(directory / "bp18-openai.env",
                              f"OPENAI_API_KEY={FAKE_KEY}\nOPENAI_MODEL_TEXT=ignored-malicious-model\n")
    credential.chmod(0o400)
    os.environ["CREDENTIALS_DIRECTORY"] = str(directory)
    launch.load_credential()
    assert os.environ["OPENAI_API_KEY"] == FAKE_KEY
    assert os.environ["OPENAI_BASE_URL"] == "https://api.openai.com/v1"
    assert "OPENAI_MODEL_TEXT" not in os.environ
    credential.chmod(0o644)
    with pytest.raises(launch.LaunchDenied, match="PRIVATE_FILE_REQUIRED"):
        launch.load_credential()


def test_worker_requires_matching_live_web_and_no_web_secret(root, tmp_path):
    write_policy(root)
    fingerprint = launch.configure(root, worker=True)
    private_file(root / "web.pid", "1234")
    proc = tmp_path / "proc"
    environment = proc / "1234/environ"
    environment.parent.mkdir(parents=True)
    values = {
        "IT_TEM_BP18_LIVE_POLICY_SHA": fingerprint,
        "IT_TEM_DEMO_CODE_SHA": SHA,
    }
    environment.write_bytes(b"\0".join(f"{key}={value}".encode() for key, value in values.items()))
    launch.require_web_policy(root, fingerprint, proc=proc)
    environment.write_bytes(environment.read_bytes() + b"\0OPENAI_API_KEY=" + FAKE_KEY.encode())
    with pytest.raises(launch.LaunchDenied, match="B_WEB_WORKER_POLICY_MISMATCH"):
        launch.require_web_policy(root, fingerprint, proc=proc)


def test_worker_lease_excludes_promotion_until_drain(root):
    lock = root / "config/.b5_operator_control.lock"
    with launch.worker_release_lease(root):
        with lock.open("rb") as operator:
            with pytest.raises(BlockingIOError):
                fcntl.flock(operator, fcntl.LOCK_EX | fcntl.LOCK_NB)
    with lock.open("rb") as operator:
        fcntl.flock(operator, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(launch.LaunchDenied, match="B_RELEASE_OPERATION_ACTIVE"):
            with launch.worker_release_lease(root):
                pytest.fail("worker acquired lease during promotion")


def test_worker_clears_credential_after_hold_and_never_restarts(root, monkeypatch):
    from demo_staging.live import worker
    write_policy(root)
    monkeypatch.setattr(launch, "require_web_policy", lambda *args: None)
    monkeypatch.setattr(launch.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0))
    handlers = {}
    monkeypatch.setattr(launch.signal, "signal", lambda sig, handler: handlers.setdefault(sig, handler))
    monkeypatch.setattr(launch, "load_credential", lambda: os.environ.update(OPENAI_API_KEY=FAKE_KEY))
    def serve(runtime, *, stop_requested):
        assert runtime == root / "runtime"
        assert os.environ["OPENAI_API_KEY"] == FAKE_KEY
        assert not stop_requested.is_set()
        handlers[launch.signal.SIGTERM]()
        assert stop_requested.is_set()
        return "LIVE_STAGE_HELD_FOR_RECONCILIATION"
    monkeypatch.setattr(worker, "serve_loop", serve)
    assert launch.launch_worker(root) == 78
    assert "OPENAI_API_KEY" not in os.environ


@pytest.mark.parametrize("kind,code", [
    ("missing", "LIVE_RELEASE_POLICY_FILE_REQUIRED"),
    ("wrong_sha", "LIVE_RELEASE_POLICY_SHA_MISMATCH"),
    ("public_file", "PRIVATE_FILE_REQUIRED"),
    ("public_directory", "PRIVATE_DIRECTORY_REQUIRED"),
    ("linked_file", "LIVE_RELEASE_POLICY_FILE_INVALID"),
    ("linked_directory", "PRIVATE_DIRECTORY_REQUIRED"),
    ("linked_config", "PRIVATE_DIRECTORY_REQUIRED"),
])
def test_release_policy_namespace_never_uses_legacy_on_invalid_selection(root, kind, code):
    global_policy = write_policy(root)
    per_release = root / "config" / launch.RELEASE_POLICY_DIRECTORY
    policy = private_file(per_release / f"{SHA}.env", global_policy.read_text())
    if kind == "missing":
        policy.unlink()
    elif kind == "wrong_sha":
        policy.write_text(global_policy.read_text().replace(SHA, "b" * 40))
    elif kind == "public_file":
        policy.chmod(0o644)
    elif kind == "public_directory":
        per_release.chmod(0o755)
    elif kind == "linked_file":
        policy.unlink()
        policy.symlink_to(global_policy)
    elif kind == "linked_directory":
        moved = per_release.with_name("relocated")
        per_release.rename(moved)
        per_release.symlink_to(moved)
    elif kind == "linked_config":
        config = root / "config"
        moved = root / "relocated"
        config.rename(moved)
        config.symlink_to(moved)
    for worker in (False, True):
        with pytest.raises(launch.LaunchDenied, match=code):
            launch.configure(root, worker=worker)
        assert os.environ["IT_TEM_LIVE_ENABLED"] == "NO"
        assert os.environ[launch.DUAL_FLAG] == "NO"
        assert "OPENAI_API_KEY" not in os.environ


def test_b5_forward_and_rollback_select_their_own_reviewed_policy(root):
    from scripts import bp18_b5_release_prestart as guard

    forward_sha = "b" * 40
    release_shas = (SHA, forward_sha)
    source_root = LAUNCHER_PATH.parents[2]
    global_policy = write_policy(root)
    global_bytes = global_policy.read_bytes()
    policy_dir = root / "config" / launch.RELEASE_POLICY_DIRECTORY
    source_files = set(guard.SSO_SOURCE_FILES) | set(guard.REVIEW_SOURCE_FILES) | set(guard.DUAL_SOURCE_FILES)
    source_files.add("deploy/systemd/bp18_live_launch.py")
    staged_hashes = {}
    policy_bytes = {}
    for sha, dual in ((SHA, "NO"), (forward_sha, "YES")):
        release = root / "releases" / sha
        hashes = {}
        for name in sorted(source_files):
            data = (source_root / name).read_bytes()
            path = release / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            hashes[name] = hashlib.sha256(data).hexdigest()
        (release / "SOURCE_SHA.txt").write_text(sha)
        staged_hashes[sha] = hashes
        policy = private_file(policy_dir / f"{sha}.env",
            global_bytes.decode().replace(SHA, sha) + f"\n{launch.DUAL_FLAG}={dual}\n")
        policy_bytes[policy] = policy.read_bytes()

    def contract(path, files, **fields):
        private_file(root / path, json.dumps({
            "version": 1, **fields,
            "verified_sources": {sha: {name: staged_hashes[sha][name] for name in files}
                                 for sha in release_shas},
        }))

    contract(guard.AUTH_CONTRACT_FILE, guard.SSO_SOURCE_FILES,
             required_mode="TAILNET_SSO_ONLY", expected_host=launch.HOST)
    contract(guard.REVIEW_CONTRACT_FILE, guard.REVIEW_SOURCE_FILES,
             required_mode="RULES_AND_LLM", model="gpt-6-luna")
    contract(guard.DUAL_CONTRACT_FILE, guard.DUAL_SOURCE_FILES,
             required_mode=guard.DUAL_PROTOCOL)
    private_file(root / "config/epoch_capable_shas.txt", "\n".join(release_shas) + "\n")

    live = root / "runtime/live"
    live.mkdir(parents=True)
    records = {
        "live.sqlite": "CREATE TABLE live_policy_activation(singleton INTEGER,epoch INTEGER,"
                       "policy_version TEXT,policy_sha TEXT);"
                       "INSERT INTO live_policy_activation VALUES(1,2,'bp18-f09-two-stage-policy-v2','"
                       + "c" * 64 + "');"
                       "CREATE TABLE live_paid_dual_groups(parent_job_id TEXT);"
                       "INSERT INTO live_paid_dual_groups VALUES('protected-parent');",
        "queue.sqlite": "CREATE TABLE queued_ops(state TEXT,mode TEXT);"
                        "INSERT INTO queued_ops VALUES('SUCCEEDED','LIVE_DUAL_V1');"
                        "INSERT INTO queued_ops VALUES('BILLING_UNKNOWN','LIVE_DUAL_V1');",
        "cost.sqlite": "CREATE TABLE attempts(status TEXT,receipt TEXT);"
                       "INSERT INTO attempts VALUES('BILLING_UNKNOWN','protected-receipt');",
    }
    for name, schema in records.items():
        with sqlite3.connect(live / name) as db:
            db.executescript(schema)
    artifact = live / "outputs" / "protected-parent" / "final.png"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"synthetic protected artifact")
    protected = {path: path.read_bytes() for path in
                 (*[live / name for name in records], artifact)}

    fingerprints = {}
    for sha in (SHA, forward_sha, SHA):
        # Match the precheck order and atomic symlink swap in the B5 control.
        current = (root / "repo").readlink().name
        for candidate in (current, sha):
            assert guard.validate(root, mode="web", port=0, target_override=candidate)["release"] == candidate
        replacement = root / "repo-next"
        replacement.symlink_to("releases/" + sha)
        os.replace(replacement, root / "repo")
        for mode in ("web", "worker"):
            result = guard.validate(root, mode=mode, port=0)
            assert result["release"] == sha
            assert result["required_auth"] == "TAILNET_SSO_ONLY"
            assert result["required_review"] == "RULES_AND_LLM"
            assert result["required_dual"] == guard.DUAL_PROTOCOL

        spec = importlib.util.spec_from_file_location(f"isolated_launcher_{sha}",
            root / "repo/deploy/systemd/bp18_live_launch.py")
        selected = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(selected)
        fingerprint = selected.configure(root, worker=False)
        assert selected.configure(root, worker=True) == fingerprint
        assert fingerprint == fingerprints.setdefault(sha, fingerprint)
        assert os.environ["IT_TEM_BP18_LIVE_RELEASE_SHA"] == sha
        assert os.environ["IT_TEM_BP18_F09_REQUIRED"] == "YES"
        assert os.environ[launch.DUAL_FLAG] == ("YES" if sha == forward_sha else "NO")
        assert "OPENAI_API_KEY" not in os.environ

    assert fingerprints[SHA] != fingerprints[forward_sha]
    assert global_policy.read_bytes() == global_bytes
    assert all(path.read_bytes() == data for path, data in policy_bytes.items())
    assert all(path.read_bytes() == data for path, data in protected.items())
