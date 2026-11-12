"""Live Dual approval lineage and transactional outbox with synthetic F09 receipts."""
import json

import pytest

from demo_staging.live import pipeline
from demo_staging.live.contracts import LiveGateError, digest
from tests.demo_live.test_bp18_f09_two_stage import ReceiptedText
from tests.demo_live.test_live_contracts import sample_input
from tests.demo_live.test_pipeline import prepare_service


PROFILE = {
    "protocol": "LIVE_DUAL_V1",
    "release_sha": "1" * 40,
    "policy_sha": "2" * 64,
    "text_model": "f09-fake-model",
    "image_profile": {"model": "gpt-image-2.6-sunburst", "quality": "medium", "complexity": "high"},
    "image_size": "4:5",
}


class SharedPrompt(ReceiptedText):
    def generate_prompt(self, plan, analysis):
        self.receipt("image_prompt")
        return super().generate_prompt(plan, analysis)


@pytest.fixture
def live_store_case(tmp_path, monkeypatch):
    monkeypatch.setenv("IT_TEM_BP18_F11_ENABLED", "YES")
    monkeypatch.setenv("IT_TEM_BP18_F09_REQUIRED", "YES")
    monkeypatch.setenv("IT_TEM_TEXT_MODEL", "f09-fake-model")
    prepared, job_id = prepare_service(tmp_path)
    flow = pipeline.LivePipeline(
        prepared.root, prepared.jobs, live_enabled=True, pm_authorized=True,
        monitoring_only=True, approved_actors=frozenset({"alice"}),
    )
    flow.prepare("alice", job_id, {
        **sample_input(), "image_size": "4:5", "generation_mode": "composed",
    }, template_profile="A", live_dual=True)
    fake = SharedPrompt()
    monkeypatch.setattr(pipeline, "OfficialTextProvider", lambda *_: fake)
    reviewed = flow.text("alice", job_id, text_model="f09-fake-model")
    return flow, job_id, reviewed, fake


def start(flow, job_id, reviewed, actor="alice"):
    return flow.state.start_live_dual(
        actor, job_id, expected_generation=reviewed["generation"],
        expected_review_sha=reviewed["review_sha"], execution_profile=PROFILE,
        acknowledge_two_images=True,
    )


def test_one_approval_derives_child_authority_without_child_llm_proof(live_store_case):
    flow, parent_id, reviewed, _ = live_store_case
    group = start(flow, parent_id, reviewed)
    parent = flow.state.get("alice", parent_id)
    child = flow.state.get("alice", group["child_job_id"])
    parent_report = json.loads(parent["compliance_json"])
    child_report = json.loads(child["compliance_json"])
    assert "llm_review" in parent_report and "llm_review" not in child_report
    assert child_report["live_dual_f09_parent"] == {
        "job_id": parent_id, "review_sha": reviewed["review_sha"],
        "attempt_id": parent_report["llm_review"]["attempt_id"],
        "receipt_sha": parent_report["llm_review"]["receipt_sha"],
    }
    assert parent["copy_sha"] == child["copy_sha"] == reviewed["copy_sha"]
    assert parent["input_sha"] != child["input_sha"]
    assert parent["review_sha"] != child["review_sha"]
    assert parent["approval_sha"] != child["approval_sha"]
    assert group["authority_sha"] == digest(json.loads(group["authority_json"]))
    assert json.loads(group["authority_json"])["acknowledge_two_images"] is True
    assert json.loads(group["authority_json"])["planned_image_attempts"] == 2
    with flow.state.db() as c:
        event = c.execute("""SELECT payload_sha FROM live_events
            WHERE job_id=? AND event='live_dual_authority_committed'""", (parent_id,)).fetchone()
        assert event["payload_sha"] == group["authority_sha"]
    assert start(flow, parent_id, reviewed) == group
    assert [(item["job_id"], item["stage"]) for item in flow.state.live_dual_intents()] == [
        (parent_id, "image_prompt")]
    with flow.cost.connect() as c:
        assert c.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 4


@pytest.mark.parametrize("acknowledgement", [None, False, 1, "true"])
def test_two_image_acknowledgement_is_required_before_approval(live_store_case, acknowledgement):
    flow, parent_id, reviewed, _ = live_store_case
    acknowledgement_arg = (
        {} if acknowledgement is None else {"acknowledge_two_images": acknowledgement}
    )
    with pytest.raises(LiveGateError, match="LIVE_DUAL_TWO_IMAGES_ACKNOWLEDGEMENT_REQUIRED"):
        flow.state.start_live_dual(
            "alice", parent_id, expected_generation=reviewed["generation"],
            expected_review_sha=reviewed["review_sha"], execution_profile=PROFILE,
            **acknowledgement_arg,
        )
    current = flow.state.get("alice", parent_id)
    assert current["state"] == "COPY_REVIEW_REQUIRED"
    assert current["approval_sha"] is None
    assert flow.state.live_dual_group("alice", parent_id)["child_job_id"] is None
    assert flow.state.live_dual_intents() == []


@pytest.mark.parametrize("mutation", ["receipt", "context", "actor", "job", "status"])
def test_forged_original_f09_rolls_back_approval_child_and_intent(live_store_case, mutation):
    flow, parent_id, reviewed, _ = live_store_case
    proof = json.loads(reviewed["compliance_json"])["llm_review"]
    changes = {
        "receipt": ("receipt", "{}"),
        "context": ("payload_hash", "0" * 64),
        "actor": ("actor", "mallory"),
        "job": ("job_id", "f" * 32),
        "status": ("status", "BILLING_UNKNOWN"),
    }
    field, value = changes[mutation]
    with flow.cost.connect() as c:
        c.execute(f"UPDATE attempts SET {field}=? WHERE id=?", (value, proof["attempt_id"]))
    with pytest.raises(LiveGateError, match="LIVE_DUAL_F09_RECEIPT_UNVERIFIED"):
        start(flow, parent_id, reviewed)
    assert flow.state.get("alice", parent_id)["state"] == "COPY_REVIEW_REQUIRED"
    assert flow.state.live_dual_group("alice", parent_id)["child_job_id"] is None
    assert flow.state.live_dual_intents() == []


def test_wrong_actor_stale_review_and_legacy_approval_cannot_start(live_store_case):
    flow, parent_id, reviewed, _ = live_store_case
    with pytest.raises(LiveGateError, match="LIVE_JOB_NOT_FOUND"):
        start(flow, parent_id, reviewed, actor="mallory")
    with pytest.raises(LiveGateError, match="STALE_REVIEW_OR_REVISION"):
        start(flow, parent_id, {**reviewed, "review_sha": "f" * 64})
    with pytest.raises(LiveGateError, match="DUAL_COPY_APPROVAL_REQUIRED"):
        flow.state.approve_copy("alice", parent_id, reviewed["generation"], reviewed["review_sha"])
    assert flow.state.live_dual_group("alice", parent_id)["child_job_id"] is None


@pytest.mark.parametrize("member", ["parent", "child"])
def test_approved_dual_copy_is_immutable_before_prompt(live_store_case, member):
    flow, parent_id, reviewed, _ = live_store_case
    group = start(flow, parent_id, reviewed)
    job_id = parent_id if member == "parent" else group["child_job_id"]
    current = flow.state.get("alice", job_id)
    copy = json.loads(current["copy_json"])
    copy["ad_copy"]["headline"] = "새 데일리 크림"
    with pytest.raises(LiveGateError, match="DUAL_APPROVED_COPY_IMMUTABLE"):
        flow.state.edit_copy("alice", job_id, copy)
    with pytest.raises(LiveGateError, match="DUAL_APPROVED_COPY_IMMUTABLE"):
        flow.state.revalidate_review_policy(
            "alice", job_id, current["generation"], current["review_sha"])
    assert flow.state.get("alice", job_id) == current


def test_outbox_attach_and_shared_prompt_fanout_are_idempotent(live_store_case):
    flow, parent_id, reviewed, fake = live_store_case
    group = start(flow, parent_id, reviewed)
    intent = flow.state.live_dual_intents()[0]
    flow.state.attach_live_dual_task(intent, "a" * 32)
    flow.state.attach_live_dual_task(intent, "a" * 32)
    with pytest.raises(LiveGateError, match="LIVE_DUAL_QUEUE_IDENTITY_CONFLICT"):
        flow.state.attach_live_dual_task(intent, "b" * 32)
    flow.prompt("alice", parent_id, text_model="f09-fake-model")
    shared_sha = flow.state.share_live_dual_prompt("alice", parent_id)
    assert flow.state.share_live_dual_prompt("alice", parent_id) == shared_sha
    child = flow.state.get("alice", group["child_job_id"])
    assert digest(json.loads(child["prompt_json"])) == shared_sha
    image_intents = flow.state.live_dual_intents()
    assert len(image_intents) == 2
    assert {item["job_id"] for item in image_intents} == {parent_id, child["job_id"]}
    assert len({item["context_sha"] for item in image_intents}) == 2
    assert fake.calls.count("prompt") == 1
    assert len(flow.state.live_dual_group("alice", parent_id)["intents"]) == 3
    flow.state.hold_live_dual(parent_id, "TEST_UNCERTAIN")
    assert flow.state.live_dual_intents() == []
    with pytest.raises(LiveGateError, match="LIVE_DUAL_GROUP_HELD"):
        flow.state.share_live_dual_prompt("alice", parent_id)


@pytest.mark.parametrize("field", ["copy_sha", "approval_sha", "input_sha", "compliance_json"])
def test_child_authority_rejects_substituted_context(live_store_case, field):
    flow, parent_id, reviewed, _ = live_store_case
    group = start(flow, parent_id, reviewed)
    child = flow.state.get("alice", group["child_job_id"])
    value = "{}" if field == "compliance_json" else "0" * 64
    with flow.state.db() as c:
        c.execute(f"UPDATE live_jobs SET {field}=? WHERE job_id=?", (value, child["job_id"]))
    with pytest.raises(LiveGateError):
        flow.state._approved(flow.state.get("alice", child["job_id"]))


def test_live_visual_review_persists_server_role_and_immutable_timestamp(live_store_case):
    from datetime import datetime, timezone

    flow, parent_id, reviewed, _ = live_store_case
    start(flow, parent_id, reviewed)
    prompt_intent = flow.state.live_dual_intents()[0]
    flow.state.attach_live_dual_task(prompt_intent, "a" * 32)
    flow.prompt("alice", parent_id, text_model="f09-fake-model")
    flow.state.share_live_dual_prompt("alice", parent_id)
    image_intent = next(
        item for item in flow.state.live_dual_intents() if item["job_id"] == parent_id
    )
    flow.state.attach_live_dual_task(image_intent, "b" * 32)
    candidate = flow.state.store_image_candidate(
        "alice", parent_id, "1" * 64, provider_attempt_id="test-owner-image",
        candidate_receipt_sha="2" * 64,
    )
    checks = {"product_matches": True, "label_matches": True, "cta_policy_matches": True}
    with pytest.raises(LiveGateError, match="LIVE_DUAL_REVIEWER_ROLE_REQUIRED"):
        flow.state.approve_image(
            "alice", parent_id, candidate["image_sha"], visual_review=checks
        )
    assert flow.state.get("alice", parent_id)["state"] == "IMAGE_REVIEW_REQUIRED"
    before = datetime.now(timezone.utc)
    flow.state.approve_image(
        "alice", parent_id, candidate["image_sha"], visual_review=checks, reviewer_role="admin"
    )
    after = datetime.now(timezone.utc)
    with flow.state.db() as c:
        row = c.execute(
            "SELECT * FROM live_paid_dual_visual_reviews WHERE job_id=?", (parent_id,)
        ).fetchone()
        record = json.loads(row["record_json"])
        assert record["actor"] == "alice"
        assert record["reviewer_role"] == "admin"
        assert before <= datetime.fromisoformat(record["reviewed_utc"]) <= after
        assert digest(record) == row["record_sha"]
        job = flow.state._read(c, parent_id, "alice")
        group = flow.state._live_dual_row(c, "alice", parent_id)
        binding = flow.state._live_dual_artifact_binding(c, job, group)
        assert binding["live_dual_visual_review_sha"] == row["record_sha"]
        changed = {**record, "reviewed_utc": "2026-11-10T01:00:00"}
        c.execute(
            "UPDATE live_paid_dual_visual_reviews SET record_json=? WHERE job_id=?",
            (json.dumps(changed), parent_id),
        )
    with flow.state.db() as c, pytest.raises(LiveGateError, match="LIVE_DUAL_VISUAL_BINDING_INVALID"):
        flow.state._live_dual_artifact_binding(
            c, flow.state._read(c, parent_id, "alice"),
            flow.state._live_dual_row(c, "alice", parent_id),
        )
