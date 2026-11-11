"""Full local protected workflow over actual existing offline Job contracts."""
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

import pytest

from demo_staging.live.contracts import LiveGateError
from demo_staging.live.derived_approval import DerivedAuthority
from demo_staging.live.derived_service import DerivedService
from demo_staging.live.derived_store import migrate_derived_schema
from demo_staging.live.derived_worker import run_once
from tests.demo_live.test_derived_approval import approved_fixture, policy_file


REPO = Path(__file__).resolve().parents[2]
FONT = REPO / "app/node_modules/pretendard/dist/public/variable/PretendardVariable.ttf"
LICENSE = REPO / "app/node_modules/pretendard/dist/LICENSE.txt"


@pytest.fixture
def service(approved_fixture, tmp_path, monkeypatch):
    flow, job_id, _ = approved_fixture
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY", "CREDENTIALS_DIRECTORY"):
        monkeypatch.delenv(name, raising=False)
    migrate_derived_schema(flow.state.filename)
    owns = lambda actor, job: actor == "alice" and job == job_id
    value = DerivedService(flow.state, flow.jobs, owns, root=tmp_path/"protected",
        authority=DerivedAuthority(policy_file(tmp_path)), font_path=FONT, license_path=LICENSE,
        source_tree_sha="1"*40)
    return value, job_id


def enqueue(value, job_id):
    snapshot = value.snapshot("alice", "admin", job_id)
    proposal = snapshot["proposals"][0]
    admission = value.admit("alice", "admin", job_id, {
        "proposal_id": proposal["proposal_id"], "expected_recipe_sha": proposal["recipe_sha"],
        "expected_context_sha": snapshot["context_sha"], "expected_revision": snapshot["revision"],
        "acknowledge_source": True})
    body = {"admission_sha": admission["admission_sha"], "expected_recipe_sha": admission["recipe_sha"],
            "expected_context_sha": admission["context_sha"], "idempotency_key": "a"*64}
    return value.prepare("alice", "admin", job_id, body), body


def decide_body(value, job_id, row, *, truth=True):
    copy = json.loads(value.state.get("alice", job_id)["copy_json"])["ad_copy"]
    checks = {name: True for name in ("source_pixels_preserved", "edges_acceptable", "no_duplicate_product",
        "no_ghost_product", "no_copy_occlusion", "cta_policy_matches", "mobile_readable")}
    checks.update(label_ground_truth_confirmed=truth, observed_copy=copy)
    return {"expected_revision": row["revision"], "expected_preview_sha": row["preview_sha"],
            "expected_recipe_sha": row["recipe_sha"], "expected_context_sha": row["context_sha"],
            "approve": True, "visual_review": checks}


def completed_review(value, job_id):
    row, _ = enqueue(value, job_id)
    result = run_once(value, worker_id="test-worker")
    assert result["state"] == "REVIEW_REQUIRED", result
    current = value.snapshot("alice", "admin", job_id)["renders"][0]
    return value.decide("alice", "admin", job_id, row["derived_id"], decide_body(value, job_id, current))


def test_full_local_prepare_review_finalize_has_exact_preview_and_no_billing(service):
    value, job_id = service
    raw_before = value.state.get("alice", job_id)
    with sqlite3.connect(value.state.filename.parent/"cost.sqlite") as c:
        before = c.execute("SELECT * FROM attempts").fetchall()
    reviewed = completed_review(value, job_id)
    result = value.finalize("alice", "admin", job_id, reviewed["derived_id"], {
        "expected_revision": reviewed["revision"], "expected_approval_sha": reviewed["approval_sha"],
        "expected_preview_sha": reviewed["preview_sha"]})
    assert result["state"] == "COMPLETED"
    assert result["final_sha"] == result["preview_sha"]
    saved = value.store.get_render("alice", job_id, result["derived_id"])
    png = value.read_artifact("alice", job_id, saved, "final")
    assert sha256(png).hexdigest() == result["preview_sha"]
    receipt = json.loads(value.read_artifact("alice", job_id, saved, "receipt"))
    assert receipt["provider_calls"] == 0
    assert receipt["raw_provider_reference"]["mode"] == "OFFLINE_FIXTURE"
    assert value.state.get("alice", job_id) == raw_before
    with sqlite3.connect(value.state.filename.parent/"cost.sqlite") as c:
        assert c.execute("SELECT * FROM attempts").fetchall() == before


def test_duplicate_prepare_returns_same_intent(service):
    value, job_id = service
    first, body = enqueue(value, job_id)
    assert value.prepare("alice", "admin", job_id, body)["derived_id"] == first["derived_id"]
    assert len(value.store.list_renders("alice", job_id)) == 1


def test_label_truth_false_never_approves(service):
    value, job_id = service
    row, _ = enqueue(value, job_id)
    run_once(value, worker_id="test-worker")
    current = value.snapshot("alice", "admin", job_id)["renders"][0]
    with pytest.raises(LiveGateError, match="DERIVED_VISUAL_REVIEW_REQUIRED"):
        value.decide("alice", "admin", job_id, row["derived_id"], decide_body(value, job_id, current, truth=False))
    assert value.store.get_render("alice", job_id, row["derived_id"])["state"] == "REVIEW_REQUIRED"


def test_policy_revision_changed_after_queue_stops_before_render(service):
    value, job_id = service
    row, _ = enqueue(value, job_id)
    path = value.authority.policy_file
    policy = json.loads(path.read_text())
    policy["revision"] += 1
    path.write_text(json.dumps(policy))
    result = run_once(value, worker_id="test-worker")
    assert result["state"] == "HOLD"
    assert result["error_code"] == "DERIVED_CONTEXT_STALE"
    assert result["preview_sha"] is None


def test_existing_source_bytes_changed_before_worker_fails_closed(service):
    value, job_id = service
    row, _ = enqueue(value, job_id)
    source_id = value.jobs.get_job(job_id)["assets"][0]["asset_id"]
    path, _ = value.jobs.get_asset(job_id, source_id)
    path.write_bytes(b"tampered")
    result = run_once(value, worker_id="test-worker")
    assert result["state"] == "HOLD"
    assert result["error_code"] == "DERIVED_ORIGINAL_ASSET_CHANGED"


def test_crash_after_files_then_reclaim_has_same_bytes(service):
    value, job_id = service
    row, _ = enqueue(value, job_id)
    class Crash(BaseException):
        pass
    def crash(phase, _):
        assert phase == "files_published"
        raise Crash
    with pytest.raises(Crash):
        run_once(value, worker_id="crashed", phase_hook=crash)
    pending = value.store.get_render("alice", job_id, row["derived_id"])
    assert pending["state"] == "RENDERING" and pending["preview_sha"] is None
    files = {p.name: p.read_bytes() for p in (value.registry.root/job_id).glob("*.blob")}
    with value.store.transaction() as c:
        c.execute("UPDATE live_derived_renders SET lease_expires_at=0 WHERE derived_id=?", (row["derived_id"],))
    result = run_once(value, worker_id="recovered")
    assert result["state"] == "REVIEW_REQUIRED"
    for name, raw in files.items():
        assert (value.registry.root/job_id/name).read_bytes() == raw


def test_missing_approved_artifact_does_not_rerender_or_finalize(service):
    value, job_id = service
    row = completed_review(value, job_id)
    path = value.registry.root/job_id/(row["preview_sha"]+".blob")
    path.unlink()
    with pytest.raises(LiveGateError, match="DERIVED_ASSET_INTEGRITY"):
        value.finalize("alice", "admin", job_id, row["derived_id"], {
            "expected_revision": row["revision"], "expected_approval_sha": row["approval_sha"],
            "expected_preview_sha": row["preview_sha"]})
    assert run_once(value, worker_id="no-paid-recovery") is None
