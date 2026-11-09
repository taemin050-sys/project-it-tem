"""B launcher tests use only temporary files and a synthetic credential."""
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
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
