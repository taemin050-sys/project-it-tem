"""Synthetic provider receipts only. No OpenAI imports, keys or network IO."""
import json
from threading import Event

import pytest

from demo_staging.live import pipeline, worker
from demo_staging.live.contracts import LiveGateError, digest
from demo_staging.live.copy_review import CopyReviewIssue, CopyReviewResult
from demo_staging.live.provider_receipts import record_owner_response
from demo_staging.live.queue import LiveQueue
from src.text_generation.schemas import CopyRevisionOutput
from tests.demo_live.test_live_contracts import safe_copy, sample_input
from tests.demo_live.test_pipeline import FakeOwner, prepare_service


class ReceiptedText(FakeOwner):
    def receipt(self, stage):
        record_owner_response({
            "status": "completed", "id": "resp_fake_" + stage,
            "model": "f09-fake-model",
            "usage": {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
        })

    def analyze(self, photos):
        self.receipt("vision")
        return super().analyze(photos)

    def research(self, product, analysis):
        self.receipt("research")
        return super().research(product, analysis)

    def generate_copy(self, product, analysis, research):
        self.receipt("copy")
        return super().generate_copy(product, analysis, research)

    def review_copy(self, copy, product, report):
        self.calls.append("review")
        self.receipt("review")
        return CopyReviewResult(issues=[])


@pytest.fixture
def live_case(tmp_path, monkeypatch):
    monkeypatch.setenv("IT_TEM_BP18_F11_ENABLED", "YES")
    monkeypatch.setenv("IT_TEM_BP18_F09_REQUIRED", "YES")
    monkeypatch.setenv("IT_TEM_TEXT_MODEL", "f09-fake-model")
    prepared, job_id = prepare_service(tmp_path)
    flow = pipeline.LivePipeline(
        prepared.root, prepared.jobs, live_enabled=True, pm_authorized=True,
        monitoring_only=True, approved_actors=frozenset({"alice"}),
    )
    flow.prepare("alice", job_id, sample_input())
    monkeypatch.setattr(worker, "policy_from_env", lambda _: flow)
    fake = ReceiptedText()
    monkeypatch.setattr(pipeline, "OfficialTextProvider", lambda *args: fake)
    return flow, job_id, fake


def stage_pending(flow, job_id):
    analysis, research, copy, _ = safe_copy()
    return flow.state.store_text("alice", job_id, analysis, research, copy, mode="LIVE")


def review(flow, job_id, pending):
    return flow.review_current_copy(
        "alice", job_id, pending["generation"], pending["review_sha"],
        text_model="f09-fake-model",
    )


def test_analysis_has_separate_review_attempt_before_approval(live_case):
    flow, job_id, fake = live_case
    row = flow.text("alice", job_id, text_model="f09-fake-model")
    assert fake.calls == ["analyze", "research", "copy", "review"]
    proof = json.loads(row["compliance_json"])["llm_review"]
    assert proof["copy_sha"] == row["copy_sha"]
    assert proof["generation"] == row["generation"]
    with flow.cost.connect() as db:
        attempts = db.execute("SELECT stage,status,receipt FROM attempts").fetchall()
    assert [r["stage"] for r in attempts] == ["vision", "research", "copy", "copy_review"]
    assert {r["status"] for r in attempts} == {"SUCCEEDED_USAGE_UNPRICED"}
    receipt = json.loads(attempts[-1]["receipt"])
    assert proof["receipt_sha"] == digest(receipt)
    approved = flow.state.approve_copy("alice", job_id, row["generation"], row["review_sha"])
    assert approved["approval_sha"]


def test_rules_only_edit_restore_and_revalidate_cannot_reuse_llm_approval(live_case):
    flow, job_id, fake = live_case
    pending = stage_pending(flow, job_id)
    with pytest.raises(LiveGateError, match="LLM_REVIEW_REQUIRED"):
        flow.state.approve_copy("alice", job_id, pending["generation"], pending["review_sha"])
    reviewed = review(flow, job_id, pending)
    replacement = json.loads(reviewed["copy_json"])
    replacement["caption"] = "매일 가볍게 시작하는 수분 루틴"
    edited = flow.state.edit_copy("alice", job_id, replacement)
    with pytest.raises(LiveGateError, match="LLM_REVIEW_REQUIRED"):
        flow.state.approve_copy("alice", job_id, edited["generation"], edited["review_sha"])
    restored = flow.state.restore_previous_copy(
        "alice", job_id, edited["generation"], edited["review_sha"],
    )
    assert restored["copy_sha"] == reviewed["copy_sha"]
    assert restored["review_sha"] != reviewed["review_sha"]
    assert "llm_review" not in json.loads(restored["compliance_json"])
    assert restored["approval_sha"] is None
    with pytest.raises(LiveGateError, match="LLM_REVIEW_REQUIRED"):
        flow.state.approve_copy("alice", job_id, restored["generation"], restored["review_sha"])
    current = review(flow, job_id, restored)
    assert fake.calls == ["review", "review"]
    assert current["review_sha"] != restored["review_sha"]


def test_llm_issues_cannot_clear_rule_failure(live_case):
    flow, job_id, _ = live_case
    pending = stage_pending(flow, job_id)
    copy = json.loads(pending["copy_json"])
    copy["ad_copy"]["headline"] = "여드름 치료"
    edited = flow.state.edit_copy("alice", job_id, copy)
    assert not json.loads(edited["compliance_json"])["passed"]
    reviewed = review(flow, job_id, edited)
    assert not json.loads(reviewed["compliance_json"])["passed"]
    with pytest.raises(LiveGateError, match="REAL_COMPLIANCE_BLOCKED"):
        flow.state.approve_copy("alice", job_id, reviewed["generation"], reviewed["review_sha"])


def test_copy_mutation_while_llm_running_rejects_old_report(live_case, monkeypatch):
    flow, job_id, _ = live_case
    pending = stage_pending(flow, job_id)

    class ConcurrentEdit(ReceiptedText):
        def review_copy(self, copy, product, report):
            replacement = copy.model_dump(mode="json")
            replacement["caption"] = "바뀐 문구와 함께하는 촉촉한 하루"
            flow.state.edit_copy("alice", job_id, replacement)
            return super().review_copy(copy, product, report)

    fake = ConcurrentEdit()
    monkeypatch.setattr(pipeline, "OfficialTextProvider", lambda *args: fake)
    with pytest.raises(LiveGateError, match="STALE_REVIEW_OR_REVISION"):
        review(flow, job_id, pending)
    current = flow.state.get("alice", job_id)
    assert current["generation"] == pending["generation"] + 1
    assert "llm_review" not in json.loads(current["compliance_json"])
    with flow.cost.connect() as db:
        assert db.execute("SELECT status FROM attempts").fetchone()[0] == "SUCCEEDED_USAGE_UNPRICED"


def test_review_checkpoint_resumes_store_without_another_provider_attempt(live_case, monkeypatch):
    flow, job_id, fake = live_case
    pending = stage_pending(flow, job_id)
    original = flow.state.complete_copy_review
    monkeypatch.setattr(flow.state, "complete_copy_review", lambda *args: (_ for _ in ()).throw(RuntimeError("test crash")))
    with pytest.raises(RuntimeError, match="test crash"):
        review(flow, job_id, pending)
    monkeypatch.setattr(flow.state, "complete_copy_review", original)
    reviewed = review(flow, job_id, pending)
    assert reviewed["copy_sha"] == pending["copy_sha"]
    assert fake.calls == ["review"]
    with flow.cost.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 1


def test_review_worker_queue_is_idempotent_and_checks_payload(live_case, tmp_path):
    flow, job_id, fake = live_case
    pending = stage_pending(flow, job_id)
    context = flow.copy_review_context(
        "alice", job_id, pending["generation"], pending["review_sha"], text_model="f09-fake-model",
    )
    queue = LiveQueue(flow.root / "queue.sqlite")
    args = dict(actor="alice", job_id=job_id, stage="copy_review", context_sha=digest(context),
                review_payload={"expected_generation":pending["generation"],
                                "expected_review_sha":pending["review_sha"]})
    task, created = queue.enqueue(**args)
    duplicate, created_again = queue.enqueue(**args)
    assert created and not created_again and duplicate["id"] == task["id"]
    assert worker.run_once(tmp_path) == "LIVE_STAGE_COMMITTED"
    assert worker.run_once(tmp_path) == "NO_LIVE_TASK"
    assert fake.calls == ["review"]
    assert queue.read(task["id"])["state"] == "SUCCEEDED"


def test_llm_review_span_must_exist_in_exact_copy(live_case, monkeypatch):
    flow, job_id, _ = live_case
    pending = stage_pending(flow, job_id)

    class InventedIssue(ReceiptedText):
        def review_copy(self, copy, product, report):
            self.receipt("review")
            return CopyReviewResult(issues=[CopyReviewIssue(
                field="headline",text="원문에 없는 표현",category="효능 과장",
                risk_level="위반 의심",reason="가짜 검수 오류",suggestion=None,
            )])

    monkeypatch.setattr(pipeline, "OfficialTextProvider", lambda *args: InventedIssue())
    with pytest.raises(LiveGateError, match="LLM_REVIEW_RESULT_NOT_GROUNDED"):
        review(flow, job_id, pending)
    assert flow.state.get("alice", job_id)["review_sha"] == pending["review_sha"]


def test_graceful_worker_stop_does_not_claim_next_task(live_case, tmp_path):
    flow, job_id, fake = live_case
    pending = stage_pending(flow, job_id)
    context = flow.copy_review_context(
        "alice", job_id, pending["generation"], pending["review_sha"], text_model="f09-fake-model",
    )
    queue = LiveQueue(flow.root / "queue.sqlite")
    task, _ = queue.enqueue(
        actor="alice", job_id=job_id, stage="copy_review", context_sha=digest(context),
        review_payload={"expected_generation":pending["generation"],
                        "expected_review_sha":pending["review_sha"]},
    )
    stopped = Event()
    stopped.set()
    assert worker.serve_loop(tmp_path, stop_requested=stopped) == "LIVE_WORKER_STOPPED"
    assert queue.read(task["id"])["state"] == "QUEUED"
    assert not fake.calls
