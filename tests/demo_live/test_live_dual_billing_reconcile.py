"""Review or quarantine uncertain MockTransport work without replay."""
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from shutil import copyfile
import sqlite3
from uuid import uuid4, uuid5

import httpx
import pytest
from fastapi.testclient import TestClient

from demo_staging.live.contracts import LiveGateError, digest
from demo_staging.live.dual_billing import RECOVERY_SOURCE_FILES, _lock, apply_disposition, inspect_incident
from demo_staging.live.dual_worker import live_dual_profile
from demo_staging.live.queue import LIVE_DUAL_PROTOCOL, LiveQueue
from tests.demo_live.test_live_dual_mock_transport import (
    ACTOR, RELEASE_SHA, TEXT_MODEL, MockOwnerImage, attempts, dual_runtime, install_images,
    prepare_direct, run_stage, upload, visual_approval,
)
from tests.demo_live.test_live_contracts import sample_input
from tests.demo_staging.test_bp18_ux_p1_sso_only import env as signed_env


OPERATOR = "bp18_b_mock_ops"
EVALUATOR = "bp18_b_mock_eval"
RECEIPT = "RECEIPT_MATCHED_UNPRICED"
QUARANTINE = "QUARANTINED_UNRESOLVED"


def write_private(path, data):
    path.write_text(json.dumps(data) if isinstance(data, dict) else data)
    path.chmod(0o600)
    return path


def reviewed_files(deployment, plan, disposition=QUARANTINE, *, operator=OPERATOR):
    config = deployment / "config"
    evidence = write_private(config / "evidence.txt", "MOCK incident review, terminal quarantine authorized")
    approval = write_private(config / "approval.json", {
        "version": 1, "operator": operator, "approval_reference": "MOCK-INC-101",
        "plan_sha": plan["plan_sha"], "evidence_sha": sha256(evidence.read_bytes()).hexdigest(),
        "disposition": disposition, "acknowledge_no_replay": True,
    })
    return approval, evidence


def uncertain_task(queue):
    with queue.db() as db:
        items = db.execute("SELECT id FROM queued_ops WHERE state='BILLING_UNKNOWN'").fetchall()
    assert len(items) == 1
    return items[0]["id"]


@pytest.fixture
def held_case(dual_runtime, monkeypatch):
    root, queue, flow, job, group, calls = prepare_direct(dual_runtime, monkeypatch)
    assert run_stage(root) == "LIVE_STAGE_COMMITTED"
    deployment = root.parent
    (deployment / "config").mkdir(mode=0o700)
    write_private(deployment / "config/bp18_tailnet_roles.json",
                  {OPERATOR: "admin", EVALUATOR: "evaluator"})
    release = deployment / "releases" / RELEASE_SHA
    release.mkdir(parents=True)
    (release / "SOURCE_SHA.txt").write_text(RELEASE_SHA)
    source = Path(__file__).resolve().parents[2]
    for name in RECOVERY_SOURCE_FILES:
        (release / name).parent.mkdir(parents=True, exist_ok=True)
        copyfile(source / name, release / name)
    (deployment / "repo").symlink_to("releases/" + RELEASE_SHA)
    return root, queue, flow, job, group, calls


def lose_response(case, monkeypatch):
    root, queue, flow, job, group, calls = case

    def lost(request, count):
        raise httpx.ReadTimeout("test lost response", request=request)

    install_images(monkeypatch, flow, calls, outcome=lost)
    assert run_stage(root) == "LIVE_STAGE_HELD_FOR_RECONCILIATION"
    return uncertain_task(queue)


def test_quarantine_keeps_original_ledger_and_resumes_only_unrelated_work(
        held_case, dual_runtime, monkeypatch):
    root, queue, flow, job, group, calls = held_case
    task_id = lose_response(held_case, monkeypatch)
    plan = inspect_incident(root.parent, task_id)
    assert plan["image_receipt"] is None
    assert plan["attempts"][0]["status"] == "BILLING_UNKNOWN"
    original_task, original_cost = queue.read(task_id), attempts(flow)
    _, host, key, app, _, _ = dual_runtime
    with TestClient(app, base_url=f"https://{host}") as client:
        unrelated = upload(client, host, key)
    prepared = flow.prepare(ACTOR, unrelated, sample_input())
    pending, _ = queue.enqueue(actor=ACTOR, job_id=unrelated, stage="analysis",
                               context_sha=prepared["input_sha"])
    assert queue.claim("LIVE", include_dual=True) is None
    approval, evidence = reviewed_files(root.parent, plan)
    result = apply_disposition(root.parent, task_id, approval, evidence)
    assert result == apply_disposition(root.parent, task_id, approval, evidence)
    assert result["global_queue_held"] is False
    assert result["actual_usd"] is None
    assert original_task == queue.read(task_id)
    assert original_cost == attempts(flow)
    assert flow.state.live_dual_group(ACTOR, job)["hold_code"]
    assert run_stage(root) == "LIVE_STAGE_COMMITTED"
    assert queue.read(pending["id"])["state"] == "SUCCEEDED"
    assert run_stage(root) == "NO_LIVE_TASK"
    assert len(calls) == 1
    sibling = group["child_job_id"] if original_task["job_id"] == job else job
    with queue.db() as db:
        assert db.execute("SELECT state FROM queued_ops WHERE job_id=? AND stage='image'",
                          (sibling,)).fetchone()["state"] == "QUEUED"
    with pytest.raises(LiveGateError, match="LIVE_DUAL_GROUP_QUARANTINED"):
        queue.enqueue(actor=ACTOR, job_id=sibling, stage="image",
                      context_sha="a"*64, mode=LIVE_DUAL_PROTOCOL)
    prior, new = queue.enqueue(actor=ACTOR, job_id=original_task["job_id"], stage="image",
                               context_sha=original_task["context_sha"], mode=LIVE_DUAL_PROTOCOL)
    assert not new and prior["state"] == "BILLING_UNKNOWN"


@pytest.mark.parametrize("held_mode,wrong_project", [("composed",False),("freeform",False),("composed",True)])
def test_native_receipt_match_keeps_billing_unknown_source_and_successful_sibling(
        held_case, monkeypatch, held_mode, wrong_project):
    from demo_staging.live.dual_worker import project_intents

    root, queue, flow, job, group, calls = held_case
    held_id = job if held_mode == "composed" else group["child_job_id"]
    project_intents(flow, queue)
    with queue.db() as db:
        db.execute("UPDATE queued_ops SET created_at='9999-01-01' WHERE job_id=? AND stage='image'",
                   (held_id,))
    assert run_stage(root) == "LIVE_STAGE_COMMITTED"
    completed_id = next(variant for variant in (job, group["child_job_id"])
                        if flow.state.get(ACTOR, variant)["state"] == "IMAGE_REVIEW_REQUIRED")
    completed = visual_approval(flow, completed_id)
    directory = flow.root / "outputs" / completed_id
    before = {file.name: file.read_bytes() for file in directory.iterdir()}
    original = MockOwnerImage.generate

    def lost_receipt(self, *args, **kwargs):
        return replace(original(self, *args, **kwargs), receipt={})

    monkeypatch.setattr(MockOwnerImage, "generate", lost_receipt)
    assert run_stage(root) == "LIVE_STAGE_HELD_FOR_RECONCILIATION"
    task_id = uncertain_task(queue)
    plan = inspect_incident(root.parent, task_id)
    assert plan["task"]["job_id"] == held_id
    assert plan["image_receipt"]["provider_request_id"] == "ittem-dual-mock-image-2"
    assert plan["image_receipt"]["usage"]["total_tokens"] == 20
    assert plan["image_receipt"]["actual_usd"] is None
    if wrong_project:
        native = flow.root / "owner_image"
        project = uuid4()
        wrong_job = uuid5(project, "beautyai/backend/image/v1/" + held_id)
        with sqlite3.connect(native / "image_bindings.sqlite") as db:
            db.execute("UPDATE backend_image_bindings SET project_id=? WHERE service_job_id=?",
                       (str(project), held_id))
        with sqlite3.connect(native / "image_attempts.sqlite") as db:
            db.execute("UPDATE provider_attempts SET project_id=?,job_id=? WHERE attempt_id=?",
                       (str(project), str(wrong_job), plan["image_receipt"]["owner_attempt_id"]))
        plan = inspect_incident(root.parent, task_id)
        assert plan["image_receipt"] is None
        approval, evidence = reviewed_files(root.parent, plan, RECEIPT)
        with pytest.raises(LiveGateError, match="LIVE_DUAL_RECONCILE_RECEIPT_REQUIRED"):
            apply_disposition(root.parent, task_id, approval, evidence)
        assert queue.dual_billing_unknown()
        return
    approval, evidence = reviewed_files(root.parent, plan, RECEIPT)
    original_cost = attempts(flow)
    result = apply_disposition(root.parent, task_id, approval, evidence)
    assert not result["global_queue_held"]
    assert result["disposition"] == RECEIPT
    assert attempts(flow) == original_cost
    assert run_stage(root) == "NO_LIVE_TASK" and len(calls) == 2
    assert flow.validate_final_artifacts(ACTOR, completed_id)["final_sha"] == completed["final_sha"]
    assert {file.name: file.read_bytes() for file in directory.iterdir()} == before


@pytest.mark.parametrize("failure", ["no_receipt","wrong_actor","changed_evidence","stale_plan",
                                     "active_release","active_worker","unsettled_dispatch","old_source",
                                     "duplicate_approval_field"])
def test_invalid_approval_never_releases_latch(held_case, monkeypatch, failure):
    root, queue, flow, job, group, calls = held_case
    task_id = lose_response(held_case, monkeypatch)
    plan = inspect_incident(root.parent, task_id)
    if failure == "unsettled_dispatch":
        with flow.cost.connect() as db:
            db.execute("UPDATE attempts SET status='DISPATCHED' WHERE id=?", (plan["attempts"][0]["id"],))
        plan = inspect_incident(root.parent, task_id)
    approval, evidence = reviewed_files(root.parent, plan, RECEIPT if failure == "no_receipt" else QUARANTINE,
                                       operator=EVALUATOR if failure == "wrong_actor" else OPERATOR)
    if failure == "changed_evidence":
        evidence.write_text("different evidence")
    if failure == "stale_plan":
        with queue.db() as db:
            db.execute("UPDATE queued_ops SET error_code='TEST_CHANGED' WHERE id=?", (task_id,))
    if failure == "old_source":
        (root.parent / "repo/demo_staging/live/queue.py").write_text("legacy queue source")
    if failure == "duplicate_approval_field":
        approval.write_text(approval.read_text()[:-1] + ',"acknowledge_no_replay":true}')
    if failure in ("active_release","active_worker"):
        lock = (root.parent / "config/.b5_operator_control.lock"
                if failure == "active_release" else root / "live/worker.lock")
        with _lock(lock), pytest.raises(LiveGateError, match="LIVE_DUAL_RECONCILE_LOCK_BUSY"):
            apply_disposition(root.parent, task_id, approval, evidence)
    else:
        with pytest.raises(LiveGateError):
            apply_disposition(root.parent, task_id, approval, evidence)
    assert queue.dual_billing_unknown()
    assert len(calls) == 1


def test_partial_write_and_conflicting_replay_preserve_latch_or_existing_record(held_case, monkeypatch):
    root, queue, flow, job, group, calls = held_case
    task_id = lose_response(held_case, monkeypatch)
    plan = inspect_incident(root.parent, task_id)
    approval, evidence = reviewed_files(root.parent, plan)
    original = LiveQueue.record_dual_billing_resolution

    def interrupted(*args):
        raise OSError("test interruption after Store quarantine")

    monkeypatch.setattr(LiveQueue, "record_dual_billing_resolution", interrupted)
    with pytest.raises(OSError):
        apply_disposition(root.parent, task_id, approval, evidence)
    assert queue.dual_billing_unknown()
    assert inspect_incident(root.parent, task_id) == plan
    monkeypatch.setattr(LiveQueue, "record_dual_billing_resolution", original)
    result = apply_disposition(root.parent, task_id, approval, evidence)
    assert not result["global_queue_held"]
    changed = json.loads(approval.read_text())
    changed["approval_reference"] = "MOCK-INC-CONFLICT"
    write_private(approval, changed)
    with pytest.raises(LiveGateError, match="LIVE_DUAL_RESOLUTION_CONFLICT"):
        apply_disposition(root.parent, task_id, approval, evidence)
    with queue.db() as db:
        assert db.execute("SELECT record_sha FROM dual_billing_resolutions").fetchone()[0] == result["record_sha"]
        db.execute("UPDATE dual_billing_resolutions SET record_sha=?", ("0"*64,))
    assert queue.dual_billing_unknown()


def test_one_disposition_does_not_clear_another_unresolved_incident(held_case, dual_runtime, monkeypatch):
    root, queue, flow, job, group, calls = held_case
    first = lose_response(held_case, monkeypatch)
    _, host, key, app, _, _ = dual_runtime
    with TestClient(app, base_url=f"https://{host}") as client:
        another = upload(client, host, key)
    prepared = flow.prepare(ACTOR, another, {**sample_input(), "image_size":"4:5",
                            "generation_mode":"composed"}, template_profile="A", live_dual=True)
    second, _ = queue.enqueue(actor=ACTOR, job_id=another, stage="analysis",
                              context_sha=prepared["input_sha"], mode=LIVE_DUAL_PROTOCOL)
    # Simulate a completed F09 commit followed by a lost Queue completion.
    reviewed = flow.text(ACTOR, another, text_model=TEXT_MODEL)
    with queue.db() as db:
        db.execute("UPDATE queued_ops SET state='BILLING_UNKNOWN' WHERE id=?", (second["id"],))
    plan = inspect_incident(root.parent, first)
    approval, evidence = reviewed_files(root.parent, plan)
    assert apply_disposition(root.parent, first, approval, evidence)["global_queue_held"]
    assert queue.claim("LIVE", include_dual=True) is None
    plan = inspect_incident(root.parent, second["id"])
    approval, evidence = reviewed_files(root.parent, plan)
    assert not apply_disposition(root.parent, second["id"], approval, evidence)["global_queue_held"]
    with pytest.raises(LiveGateError, match="LIVE_DUAL_GROUP_HELD"):
        flow.state.start_live_dual(ACTOR, another, expected_generation=reviewed["generation"],
            expected_review_sha=reviewed["review_sha"], execution_profile=live_dual_profile(),
            acknowledge_two_images=True)
    assert flow.state.live_dual_group(ACTOR, another)["child_job_id"] is None
    assert run_stage(root) == "NO_LIVE_TASK" and len(calls) == 1
