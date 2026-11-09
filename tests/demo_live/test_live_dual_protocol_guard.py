"""No-network protocol and rollback checks on disposable queues/releases."""
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from demo_staging.live.contracts import LiveGateError
from demo_staging.live.dual_worker import (
    LIVE_DUAL_FLAG, live_dual_lease, live_dual_profile, live_dual_worker_ready,
)
from demo_staging.live.queue import LIVE_DUAL_PROTOCOL, LiveQueue
from demo_staging.live_safety import LiveNotAuthorized
from scripts import bp18_b5_release_prestart as guard
from tests.demo_live.test_bp18_b5_release_prestart import clone, NEW, OLD
from tests.demo_live.test_bp18_live_launch import (
    root as launch_root, launch, SHA, write_policy,
)

SOURCE_ROOT = Path(__file__).resolve().parents[2]


def dual_environment(monkeypatch):
    for key in (LIVE_DUAL_FLAG, "IT_TEM_TAILNET_AUTH_ENABLED", "IT_TEM_TAILNET_SSO_ONLY",
                "IT_TEM_BP18_F09_REQUIRED", "IT_TEM_BP18_F11_ENABLED"):
        monkeypatch.setenv(key, "YES")
    monkeypatch.setenv("IT_TEM_TAILNET_EXPECTED_HOST", launch.HOST)
    monkeypatch.setenv("IT_TEM_BP18_LIVE_RELEASE_SHA", "a" * 40)
    monkeypatch.setenv("IT_TEM_BP18_LIVE_POLICY_SHA", "b" * 64)
    monkeypatch.setenv("IT_TEM_TEXT_MODEL", "mock-no-network-model")


def dual_contract(root, sha):
    sources = {}
    for name in guard.DUAL_SOURCE_FILES:
        raw = (SOURCE_ROOT / name).read_bytes()
        destination = root / "releases" / sha / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
        sources[name] = hashlib.sha256(raw).hexdigest()
    contract = root / guard.DUAL_CONTRACT_FILE
    contract.write_text(json.dumps({
        "version": 1, "required_mode": LIVE_DUAL_PROTOCOL,
        "verified_sources": {sha: sources},
    }))
    contract.chmod(0o600)
    return contract


def test_legacy_worker_never_claims_dual_and_unknown_survives_restart(tmp_path):
    queue = LiveQueue(tmp_path / "queue.sqlite")
    task, new = queue.enqueue(actor="alice", job_id="a" * 32,
        stage="image", context_sha="1" * 64, mode=LIVE_DUAL_PROTOCOL)
    assert new
    assert queue.claim("LIVE") is None
    assert queue.read(task["id"])["state"] == "QUEUED"
    with pytest.raises(LiveGateError, match="QUEUE_IDENTITY_MISMATCH"):
        queue.enqueue(actor="alice", job_id=task["job_id"],
                      stage="image", context_sha=task["context_sha"], mode="LIVE")
    assert queue.claim("LIVE", include_dual=True)["id"] == task["id"]
    queue.interrupt(task["id"], "MOCK_SEND_UNKNOWN")
    sibling, _ = queue.enqueue(actor="alice", job_id="b" * 32,
        stage="image", context_sha="2" * 64, mode=LIVE_DUAL_PROTOCOL)
    restarted = LiveQueue(queue.file)
    assert restarted.dual_billing_unknown()
    assert restarted.claim("LIVE", include_dual=True) is None
    assert restarted.read(sibling["id"])["state"] == "QUEUED"


def test_handshake_requires_held_lease_and_exact_runtime_profile(tmp_path, monkeypatch):
    dual_environment(monkeypatch)
    (tmp_path / "live").mkdir()
    assert not live_dual_worker_ready(tmp_path)
    with live_dual_lease(tmp_path) as profile:
        assert profile == live_dual_profile()
        assert live_dual_worker_ready(tmp_path)
        with pytest.raises(LiveNotAuthorized, match="LIVE_DUAL_WORKER_ALREADY_RUNNING"):
            with live_dual_lease(tmp_path):
                pytest.fail("a second Worker acquired the protocol lease")
        monkeypatch.setenv("IT_TEM_BP18_LIVE_RELEASE_SHA", "c" * 40)
        assert not live_dual_worker_ready(tmp_path)
    assert not live_dual_worker_ready(tmp_path)


@pytest.mark.parametrize("history", ["group", "queue"])
def test_dual_history_requires_exact_compatible_release_before_rollback(tmp_path, history):
    root = clone(tmp_path)
    with sqlite3.connect(root / "runtime/live/live.sqlite") as database:
        database.execute("CREATE TABLE live_paid_dual_groups(parent_job_id TEXT)")
        if history == "group":
            database.execute("INSERT INTO live_paid_dual_groups VALUES(?)", ("a" * 32,))
    if history == "queue":
        with sqlite3.connect(root / "runtime/live/queue.sqlite") as database:
            database.execute("ALTER TABLE queued_ops ADD COLUMN mode TEXT")
            database.execute("INSERT INTO queued_ops VALUES('QUEUED',?)", (LIVE_DUAL_PROTOCOL,))
    with pytest.raises(guard.ReleaseUnsafe, match="LIVE_DUAL_REQUIRED_CONTRACT_INVALID"):
        guard.validate(root, mode="web", port=0)
    dual_contract(root, NEW)
    assert guard.validate(root, mode="web", port=0)["required_dual"] == LIVE_DUAL_PROTOCOL
    (root / "config/epoch_capable_shas.txt").write_text(NEW + "\n" + OLD + "\n")
    before = (root / "runtime/live/live.sqlite").read_bytes()
    with pytest.raises(guard.ReleaseUnsafe, match="LIVE_DUAL_INCOMPATIBLE_RELEASE_DENIED"):
        guard.validate(root, mode="web", port=0, target_override=OLD)
    assert (root / "runtime/live/live.sqlite").read_bytes() == before
    assert (root / "repo").readlink() == Path("releases") / NEW


def test_dual_contract_cannot_whitelist_missing_protocol_or_altered_source(tmp_path):
    root = clone(tmp_path)
    contract = dual_contract(root, NEW)
    source = root / "releases" / NEW / "demo_staging/live/dual_worker.py"
    source.write_text("# old Worker")
    with pytest.raises(guard.ReleaseUnsafe, match="LIVE_DUAL_SOURCE_PROVENANCE_INVALID"):
        guard.validate(root, mode="web", port=0)
    document = json.loads(contract.read_text())
    document["verified_sources"][NEW]["demo_staging/live/dual_worker.py"] = hashlib.sha256(
        source.read_bytes()).hexdigest()
    contract.write_text(json.dumps(document))
    with pytest.raises(guard.ReleaseUnsafe, match="LIVE_DUAL_REQUIRED_PROTOCOL_CODE_MISSING"):
        guard.validate(root, mode="web", port=0)


def test_launcher_defaults_dual_off_and_requires_reviewed_opt_in(launch_root, monkeypatch):
    monkeypatch.setenv(LIVE_DUAL_FLAG, "YES")
    assert launch.configure(launch_root, worker=False) is None
    assert launch.os.environ[LIVE_DUAL_FLAG] == "NO"
    write_policy(launch_root, **{LIVE_DUAL_FLAG: "YES"})
    with pytest.raises(guard.ReleaseUnsafe, match="LIVE_DUAL_REQUIRED_CONTRACT_INVALID"):
        launch.configure(launch_root, worker=False)
    assert launch.os.environ[LIVE_DUAL_FLAG] == "NO"
    dual_contract(launch_root, SHA)
    web = launch.configure(launch_root, worker=False)
    assert launch.os.environ[LIVE_DUAL_FLAG] == "YES"
    assert "OPENAI_API_KEY" not in launch.os.environ
    assert launch.configure(launch_root, worker=True) == web
