"""A2-P0-03/04 A-only independent negative replays, zero billed model calls."""
import json
from copy import deepcopy
from threading import Barrier,Thread

import pytest

from demo_staging.live.contracts import LiveGateError
from demo_staging.live import pipeline as pipeline_module
from tests.demo_live.test_pipeline import prepare_service,FakeOwner
from tests.demo_live.test_live_contracts import sample_input


def approved_fixture(tmp_path):
    flow,jid=prepare_service(tmp_path)
    flow.prepare("alice",jid,sample_input(),template_profile="A")
    owner=FakeOwner()
    text=flow.text("alice",jid,owner,offline=True)
    flow.state.approve_copy("alice",jid,text["generation"],text["review_sha"])
    return flow,jid,owner


def test_fixture_cannot_be_promoted_to_live_prompt_even_with_enabled_flags(
    tmp_path,monkeypatch,
):
    flow,jid,owner=approved_fixture(tmp_path)
    flow.live_enabled=True
    flow.pm_authorized=True
    calls=[]
    monkeypatch.setattr(pipeline_module,"OfficialTextProvider",
        lambda *_:calls.append("CONSTRUCT") or owner)
    monkeypatch.setattr(flow,"_guarded",lambda *_args,**_kwargs:
        pytest.fail("Fixture must not enter paid path"))
    with pytest.raises(LiveGateError,match="PROMPT.*PROVENANCE|PROMPT.*MODE"):
        flow.prompt("alice",jid,offline=False)
    assert calls==[]
    assert flow.state.get("alice",jid)["state"]=="COPY_APPROVED"


def test_copy_edit_revert_reapprove_during_prompt_denies_stale_result(
    tmp_path,
):
    flow,jid,owner=approved_fixture(tmp_path)
    original=flow.state.get("alice",jid)
    class RaceOwner(FakeOwner):
        def generate_prompt(self,plan,analysis):
            current=json.loads(original["copy_json"])
            changed=deepcopy(current)
            changed["caption"]="중간 임시 카피 수정"
            flow.state.edit_copy("alice",jid,changed)
            restored=flow.state.edit_copy("alice",jid,current)
            flow.state.approve_copy("alice",jid,restored["generation"],restored["review_sha"])
            return super().generate_prompt(plan,analysis)
    with pytest.raises(LiveGateError,match="PROMPT.*CONTEXT|PROMPT.*CAS"):
        flow.prompt("alice",jid,RaceOwner(),offline=True)
    final=flow.state.get("alice",jid)
    assert final["state"]=="COPY_APPROVED"
    assert final["approval_sha"]!=original["approval_sha"]
    assert final["copy_sha"]==original["copy_sha"]
    assert final["prompt_json"] is None


def test_policy_epoch_mutation_during_prompt_denies_stale_result(
    tmp_path,monkeypatch,
):
    monkeypatch.setenv("IT_TEM_REVIEW_POLICY_EPOCH","policy-1")
    flow,jid,owner=approved_fixture(tmp_path)
    class EpochOwner(FakeOwner):
        def generate_prompt(self,plan,analysis):
            monkeypatch.setenv("IT_TEM_REVIEW_POLICY_EPOCH","policy-2")
            return super().generate_prompt(plan,analysis)
    with pytest.raises(LiveGateError,match="PROMPT_APPROVAL_POLICY_EPOCH_CHANGED"):
        flow.prompt("alice",jid,EpochOwner(),offline=True)
    assert flow.state.get("alice",jid)["prompt_json"] is None


def test_normal_offline_prompt_contract_still_works(tmp_path):
    flow,jid,owner=approved_fixture(tmp_path)
    ready=flow.prompt("alice",jid,owner,offline=True)
    assert ready["state"]=="PROMPT_READY" and ready["prompt_json"]
    assert flow.image_input("alice",jid).copy_hash==ready["copy_sha"]


def test_live_input_with_fixture_checkpoint_cannot_become_prompt(
    tmp_path,monkeypatch,
):
    flow,jid,owner=approved_fixture(tmp_path)
    with flow.state.db() as db:
        db.execute("UPDATE live_jobs SET mode='LIVE' WHERE job_id=?",(jid,))
    flow.live_enabled=True;flow.pm_authorized=True
    flow.approved_actors=frozenset({"alice"})
    monkeypatch.setattr(pipeline_module,"OfficialTextProvider",lambda *_:owner)
    monkeypatch.setattr(flow,"_guarded",lambda *_args,**_kwargs:
        pytest.fail("Fake-source LIVE job must not invoke billable provider"))
    with pytest.raises(LiveGateError,match="PROMPT.*SOURCE|PROMPT.*PROVENANCE"):
        flow.prompt("alice",jid,offline=False)


def test_isolated_live_checkpoints_authorize_genuine_live_prompt_path(
    tmp_path,monkeypatch,
):
    """Fake provider inserted ONLY at stage action. Mode and provenance LIVE."""
    flow,jid=prepare_service(tmp_path)
    flow.prepare("alice",jid,sample_input(),template_profile="A")
    flow.live_enabled=True
    flow.pm_authorized=True
    flow.approved_actors=frozenset({"alice"})
    fake=FakeOwner()
    monkeypatch.setattr(pipeline_module,"OfficialTextProvider",lambda *_:fake)
    monkeypatch.setattr(flow,"_guarded",lambda _actor,_jid,_stage,_ctx,action,**_:action())
    text=flow.text("alice",jid,offline=False)
    assert text["mode"]=="LIVE"
    approved=flow.state.approve_copy("alice",jid,text["generation"],text["review_sha"])
    prompt=flow.prompt("alice",jid,offline=False)
    assert prompt["state"]=="PROMPT_READY"
    assert prompt["mode"]=="LIVE"
    assert flow.image_input("alice",jid).copy_hash==approved["copy_sha"]
    with flow.state.db() as c:
        row=c.execute("SELECT * FROM live_prompt_context_bindings WHERE job_id=?",
                      (jid,)).fetchone()
        assert row["mode"]=="LIVE" and row["context_sha"]


def test_policy_epoch_change_after_prompt_denies_image_or_regenerate(
    tmp_path,monkeypatch,
):
    monkeypatch.setenv("IT_TEM_REVIEW_POLICY_EPOCH","review-one")
    flow,jid,owner=approved_fixture(tmp_path)
    prompt=flow.prompt("alice",jid,owner,offline=True)
    assert prompt["state"]=="PROMPT_READY"
    monkeypatch.setenv("IT_TEM_REVIEW_POLICY_EPOCH","review-two")
    with pytest.raises(LiveGateError,match="PROMPT_APPROVAL_POLICY_EPOCH_CHANGED"):
        flow.image_input("alice",jid)


def test_second_prompt_after_new_approved_revision_has_independent_checkpoint(
    tmp_path,
):
    flow,jid,owner=approved_fixture(tmp_path)
    first=flow.prompt("alice",jid,owner,offline=True)
    assert first["state"]=="PROMPT_READY"
    # Prompt cannot be overwritten in place; a new approval requires the
    # standard review/revision path. Simulate a separate re-review via
    # LiveStore only, preserving first immutable checkpoint and binding.
    with flow.state.db() as db:
        db.execute("""UPDATE live_jobs SET state='COPY_APPROVED' WHERE job_id=?""",(jid,))
    prior=flow.state.get("alice",jid)
    cp=json.loads(prior["copy_json"])
    cp["caption"]="새로운 승인된 광고 설명"
    updated=flow.state.edit_copy("alice",jid,cp)
    latest=flow.state.approve_copy("alice",jid,updated["generation"],updated["review_sha"])
    next_prompt=flow.prompt("alice",jid,owner,offline=True)
    assert next_prompt["state"]=="PROMPT_READY"
    assert next_prompt["generation"]==latest["generation"]
    with flow.checkpoints.db() as c:
        rows=c.execute("""SELECT context_sha FROM text_revision_checkpoints
            WHERE job_id=? AND stage='image_prompt'""",(jid,)).fetchall()
        assert len(rows)==2 and rows[0][0]!=rows[1][0]


def test_billed_prompt_cas_collision_preserves_usage_no_automatic_repost(
    tmp_path,monkeypatch,
):
    """Synthetic LIVE response/usage, not a real provider. Receipt survives CAS."""
    from demo_staging.live.provider_receipts import record_owner_response
    from tests.demo_live.test_receipts import fake_response
    flow,jid=prepare_service(tmp_path)
    flow.prepare("alice",jid,sample_input(),template_profile="A")
    flow.live_enabled=True
    flow.pm_authorized=True
    flow.approved_actors=frozenset({"alice"})
    flow.cost.live_enabled=True
    flow.cost.monitoring_only=True
    initial_owner=FakeOwner()
    monkeypatch.setattr(pipeline_module,"OfficialTextProvider",lambda *_:initial_owner)
    original_guard=flow._guarded
    flow._guarded=lambda _actor,_jid,_stage,_context,callback,**_:callback()
    try:
        text=flow.text("alice",jid,offline=False)
    finally:
        flow._guarded=original_guard
    flow.state.approve_copy("alice",jid,text["generation"],text["review_sha"])
    before=flow.state.get("alice",jid)

    class BilledRace(FakeOwner):
        def generate_prompt(self,plan,analysis):
            original=json.loads(before["copy_json"])
            changed=deepcopy(original)
            changed["caption"]="잠시 변경한 카피입니다"
            flow.state.edit_copy("alice",jid,changed)
            back=flow.state.edit_copy("alice",jid,original)
            flow.state.approve_copy("alice",jid,back["generation"],back["review_sha"])
            record_owner_response(fake_response())
            return super().generate_prompt(plan,analysis)
    monkeypatch.setattr(pipeline_module,"OfficialTextProvider",lambda *_:BilledRace())
    with pytest.raises(LiveGateError,match="PROMPT_APPROVAL_CONTEXT_CAS_FAILED"):
        flow.prompt("alice",jid,offline=False)
    with flow.cost.connect() as c:
        rows=c.execute("SELECT * FROM attempts WHERE stage='image_prompt'").fetchall()
        assert len(rows)==1
        assert rows[0]["status"]=="SUCCEEDED_USAGE_UNPRICED"
        assert json.loads(rows[0]["receipt"])["usage"]["total_tokens"]==44
    with flow.checkpoints.db() as c:
        assert c.execute("""SELECT count(*) FROM text_revision_checkpoints
            WHERE job_id=? AND stage='image_prompt'""",(jid,)).fetchone()[0]==0
    current=flow.state.get("alice",jid)
    assert current["prompt_json"] is None and current["state"]=="COPY_APPROVED"
    assert current["approval_sha"]!=before["approval_sha"]


def test_concurrent_offline_prompt_only_one_cas_commit(tmp_path):
    from threading import Barrier,Thread
    flow,jid,owner=approved_fixture(tmp_path)
    gate=Barrier(2,timeout=5)
    class SlowOwner(FakeOwner):
        def generate_prompt(self,plan,analysis):
            gate.wait()
            return super().generate_prompt(plan,analysis)
    results=[]
    def run():
        try:
            flow.prompt("alice",jid,SlowOwner(),offline=True)
            results.append("COMMITTED")
        except LiveGateError as err:
            results.append(err.code)
    t1=Thread(target=run)
    t2=Thread(target=run)
    t1.start();t2.start()
    t1.join(10);t2.join(10)
    assert not t1.is_alive() and not t2.is_alive()
    assert results.count("COMMITTED")==1
    assert any(x in ("PROMPT_REQUIRES_COPY_APPROVAL",
                     "PROMPT_APPROVAL_CONTEXT_CAS_FAILED") for x in results)
    assert flow.state.get("alice",jid)["state"]=="PROMPT_READY"
    with flow.state.db() as c:
        assert c.execute("SELECT COUNT(*) FROM live_prompt_context_bindings WHERE job_id=?",
                         (jid,)).fetchone()[0]==1
