"""Fake provider only. Exercise B queue, worker lock and durable ledger together."""
import json
import time

import pytest

from demo_staging.live import pipeline, worker
from demo_staging.live.provider_receipts import record_owner_response
from demo_staging.live.queue import LiveQueue
from demo_staging.live_safety import LiveNotAuthorized
from tests.demo_live.test_live_contracts import safe_copy, sample_input
from tests.demo_live.test_pipeline import FakeOwner, prepare_service


class ReceiptPrompt(FakeOwner):
    def generate_prompt(self, plan, analysis):
        record_owner_response({
            "status": "completed", "id": "resp_fake_prompt", "model": "fake-no-network",
            "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
        })
        return super().generate_prompt(plan, analysis)


@pytest.fixture
def prepared_worker(tmp_path, monkeypatch):
    prepared, job_id = prepare_service(tmp_path)
    flow = pipeline.LivePipeline(
        prepared.root, prepared.jobs, live_enabled=True, pm_authorized=True,
        monitoring_only=True, approved_actors=frozenset({"alice"}),
    )
    flow.prepare("alice", job_id, sample_input())
    monkeypatch.setattr(worker, "policy_from_env", lambda root: flow)
    return flow, job_id, LiveQueue(flow.root / "queue.sqlite")


def _no_provider(monkeypatch):
    calls = []

    def unexpected(*args):
        calls.append(args)
        pytest.fail("provider initialization is forbidden")

    monkeypatch.setattr(pipeline, "OfficialTextProvider", unexpected)
    monkeypatch.setattr(worker, "live_image_adapter", unexpected)
    return calls


def _approve_copy(flow, job_id, mode):
    analysis, research, copy, _ = safe_copy()
    reviewed = flow.state.store_text("alice", job_id, analysis, research, copy, mode=mode)
    return flow.state.approve_copy("alice", job_id, reviewed["generation"], reviewed["review_sha"])


@pytest.mark.parametrize("case,error", [
    ("removed_actor", "LIVE_QUEUE_ACTOR_NOT_AUTHORIZED"),
    ("analysis", "TEXT_QUEUE_CONTEXT_STALE"),
    ("image_prompt", "PROMPT_QUEUE_CONTEXT_STALE"),
])
def test_worker_holds_revoked_actor_and_stale_context_without_attempt(
    case, error, prepared_worker, tmp_path, monkeypatch,
):
    flow, job_id, queue = prepared_worker
    calls = _no_provider(monkeypatch)
    stage = "image_prompt" if case == "image_prompt" else "analysis"
    if case == "image_prompt":
        _approve_copy(flow, job_id, "LIVE")
    context_sha = "a" * 64
    if case == "removed_actor":
        context_sha = flow.state.get("alice", job_id)["input_sha"]
        flow.approved_actors = frozenset({"bp18_b_taemin"})
    task, _ = queue.enqueue(actor="alice", job_id=job_id, stage=stage, context_sha=context_sha)

    assert worker.run_once(tmp_path) == "LIVE_STAGE_HELD_FOR_RECONCILIATION"
    assert queue.read(task["id"])["error_code"] == error
    assert worker.run_once(tmp_path) == "NO_LIVE_TASK"
    assert calls == []
    with flow.cost.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0


@pytest.mark.parametrize("stage", ["image_prompt", "image"])
def test_live_worker_rejects_fixture_provenance(prepared_worker, tmp_path, monkeypatch, stage):
    flow, job_id, queue = prepared_worker
    approved = _approve_copy(flow, job_id, "OFFLINE_FIXTURE")
    if stage == "image":
        flow.prompt("alice", job_id, FakeOwner(), offline=True)
    calls = _no_provider(monkeypatch)
    task, _ = queue.enqueue(actor="alice", job_id=job_id, stage=stage,
                           context_sha=approved["approval_sha"])

    assert worker.run_once(tmp_path) == "LIVE_STAGE_HELD_FOR_RECONCILIATION"
    assert queue.read(task["id"])["error_code"] == "LIVE_QUEUE_PROVENANCE_MISMATCH"
    assert calls == []
    with flow.cost.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0


def test_provider_prompt_result_cannot_attach_to_reapproved_copy(prepared_worker, tmp_path, monkeypatch):
    flow, job_id, queue = prepared_worker
    original = _approve_copy(flow, job_id, "LIVE")
    task, _ = queue.enqueue(actor="alice", job_id=job_id, stage="image_prompt",
                            context_sha=original["approval_sha"])

    class ReapprovedDuringProvider(ReceiptPrompt):
        def generate_prompt(self, plan, analysis):
            candidate = json.loads(original["copy_json"])
            candidate["caption"] = "차분하게 즐기는 매일의 수분 케어"
            edited = flow.state.edit_copy("alice", job_id, candidate)
            flow.state.approve_copy("alice", job_id, edited["generation"], edited["review_sha"])
            return super().generate_prompt(plan, analysis)

    fake = ReapprovedDuringProvider()
    monkeypatch.setattr(pipeline, "OfficialTextProvider", lambda *args: fake)
    assert worker.run_once(tmp_path) == "LIVE_STAGE_HELD_FOR_RECONCILIATION"
    assert queue.read(task["id"])["error_code"] == "PROMPT_APPROVAL_STALE"
    assert fake.calls == ["prompt"]
    current = flow.state.get("alice", job_id)
    assert current["generation"] == original["generation"] + 1
    assert current["approval_sha"] != original["approval_sha"]
    assert current["state"] == "COPY_APPROVED"
    assert current["prompt_json"] is None
    with flow.cost.connect() as db:
        assert db.execute("SELECT status FROM attempts").fetchone()[0] == "SUCCEEDED_USAGE_UNPRICED"

    replacement, created = queue.enqueue(actor="alice", job_id=job_id, stage="image_prompt",
                                         context_sha=current["approval_sha"])
    assert created and replacement["id"] != task["id"]
    new_provider = ReceiptPrompt()
    monkeypatch.setattr(pipeline, "OfficialTextProvider", lambda *args: new_provider)
    assert worker.run_once(tmp_path) == "LIVE_STAGE_COMMITTED"
    assert new_provider.calls == ["prompt"]
    assert queue.read(replacement["id"])["state"] == "SUCCEEDED"
    assert flow.state.get("alice", job_id)["state"] == "PROMPT_READY"


def test_crash_holds_queue_and_provider_intent_without_dispatch(prepared_worker, tmp_path, monkeypatch):
    flow, job_id, queue = prepared_worker
    calls = _no_provider(monkeypatch)
    job = flow.state.get("alice", job_id)
    task, _ = queue.enqueue(actor="alice", job_id=job_id, stage="analysis", context_sha=job["input_sha"])
    assert queue.claim()["id"] == task["id"]
    next_task, _ = queue.enqueue(actor="alice", job_id="b" * 32, stage="analysis", context_sha="c" * 64)
    attempt = flow.cost.reserve(actor="alice", role="live_operator", job_id=job_id,
                                stage="vision", payload={}, estimated_usd=0, pm_authorized=True)
    flow.cost.dispatch_intent(attempt["id"])

    assert worker.run_once(tmp_path) == "LIVE_STAGE_HELD_FOR_RECONCILIATION"
    assert queue.read(task["id"])["state"] == "BILLING_UNKNOWN"
    assert flow.cost.inspect(attempt["id"])["status"] == "BILLING_UNKNOWN"
    assert queue.read(next_task["id"])["state"] == "QUEUED"
    assert calls == []


def test_worker_commits_current_prompt_once_with_provider_receipt(prepared_worker, tmp_path, monkeypatch):
    flow, job_id, queue = prepared_worker
    approved = _approve_copy(flow, job_id, "LIVE")
    task, _ = queue.enqueue(actor="alice", job_id=job_id, stage="image_prompt",
                            context_sha=approved["approval_sha"])

    fake = ReceiptPrompt()
    monkeypatch.setattr(pipeline, "OfficialTextProvider", lambda *args: fake)
    assert worker.run_once(tmp_path) == "LIVE_STAGE_COMMITTED"
    assert worker.run_once(tmp_path) == "NO_LIVE_TASK"
    assert queue.read(task["id"])["state"] == "SUCCEEDED"
    assert flow.state.get("alice", job_id)["state"] == "PROMPT_READY"
    assert fake.calls == ["prompt"]
    with flow.cost.connect() as db:
        receipt, = db.execute("SELECT receipt FROM attempts").fetchone()
    assert json.loads(receipt)["provider_response_id"] == "resp_fake_prompt"


def test_worker_loop_holds_single_worker_lock_while_idle(prepared_worker, tmp_path, monkeypatch):
    class EndIdleLoop(Exception):
        pass

    def inspect_lock(interval):
        with pytest.raises(LiveNotAuthorized, match="LIVE_WORKER_ALREADY_RUNNING"):
            worker.run_once(tmp_path)
        raise EndIdleLoop

    monkeypatch.setattr(time, "sleep", inspect_lock)
    with pytest.raises(EndIdleLoop):
        worker.serve_loop(tmp_path)
    assert worker.run_once(tmp_path) == "NO_LIVE_TASK"
