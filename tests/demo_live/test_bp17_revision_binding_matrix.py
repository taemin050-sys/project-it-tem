"""BP17 A' six state transitions on existing Owner-preserving Serving contracts.

These do NOT stand in for a new Text Owner compliance context or v3 prompt.
All calls are offline FakeOwner/SQLite, never billable or networked.
"""
from copy import deepcopy
import json
from uuid import uuid4

import pytest

from demo_staging.live.contracts import LiveGateError,digest
from demo_staging.live import store as store_module
from tests.demo_live.test_owner_text25_revision_integration import (
    FakeRevision, create_ready,
)
from tests.demo_live.test_bp13_single_image_retry import ready

def test_01_copy_edit_invalidates_active_approval_and_image_prompt_binding(tmp_path):
    flow,jid,original,owner=create_ready(tmp_path)
    approved=flow.state.approve_copy("alice",jid,original["generation"],original["review_sha"])
    assert approved["approval_sha"]
    revised=json.loads(approved["copy_json"])
    revised["ad_copy"]["headline"]="매일 더 산뜻하게"
    modified=flow.state.edit_copy("alice",jid,revised)
    assert modified["state"]=="COPY_REVIEW_REQUIRED"
    assert modified["generation"]==approved["generation"]+1
    assert modified["copy_sha"]!=approved["copy_sha"]
    assert modified["review_sha"]!=approved["review_sha"]
    assert modified["approval_sha"] is None
    assert all(modified[k] is None for k in (
        "prompt_json","image_sha","image_approval_sha","final_sha","caption_sha"))
    with pytest.raises(LiveGateError,match="STALE_REVIEW_OR_REVISION"):
        flow.state.approve_copy("alice",jid,approved["generation"],approved["review_sha"])
    with pytest.raises(LiveGateError,match="PROMPT_REQUIRES_APPROVED_COPY"):
        flow.prompt("alice",jid,owner,offline=True)

def test_02_planning_concept_or_mood_change_rebinds_next_prompt(tmp_path):
    flow,jid,original,owner=create_ready(tmp_path)
    initial=json.loads(original["copy_json"])
    changed=deepcopy(initial)
    changed["plan"]["concept"]="봄의 맑은 수분 캠페인"
    changed["plan"]["mood"]=["상큼함","깨끗함"]
    edited=flow.state.edit_copy("alice",jid,changed)
    assert edited["copy_sha"]!=original["copy_sha"]
    assert edited["review_sha"]!=original["review_sha"]
    assert edited["generation"]==original["generation"]+1
    approved=flow.state.approve_copy("alice",jid,edited["generation"],edited["review_sha"])
    class CaptureOwner(FakeRevision):
        def __init__(self):
            super().__init__();self.plans=[]
        def generate_prompt(self,plan,analysis):
            self.plans.append(plan.model_dump(mode="json"))
            output=super().generate_prompt(plan,analysis)
            output.concept=plan.concept
            output.mood=list(plan.mood)
            return output
    spy=CaptureOwner()
    prompted=flow.prompt("alice",jid,spy,offline=True)
    assert prompted["state"]=="PROMPT_READY"
    assert len(spy.plans)==1 and spy.plans[0]["mood"]==changed["plan"]["mood"]
    assert spy.plans[0]["concept"]==changed["plan"]["concept"]
    assert owner.calls==["analyze","research","copy"]
    assert digest({"copy_sha":approved["copy_sha"],"generation":approved["generation"]})!=(
        digest({"copy_sha":original["copy_sha"],"generation":original["generation"]}))

def test_03_same_copy_and_identical_review_stays_same_generation(tmp_path):
    flow,jid,original,_=create_ready(tmp_path)
    same=json.loads(original["copy_json"])
    after=flow.state.apply_copy_revision(
        "alice",jid,same,"규정 준수 확인",original["generation"],original["review_sha"])
    assert all(after[k]==original[k] for k in
        ("generation","review_sha","copy_sha","approval_sha","compliance_json"))
    with flow.state.db() as conn:
        events=conn.execute("select count(*) from live_events where job_id=? "
            "and event='copy_revision_no_change'",(jid,)).fetchone()[0]
    assert events==1

def test_04_same_copy_changed_compliance_result_invalidates_review(tmp_path,monkeypatch):
    flow,jid,original,_=create_ready(tmp_path)
    from demo_staging.live import store as module
    original_review=module.strict_review
    def new_policy_result(copy,product,analysis):
        report=deepcopy(original_review(copy,product,analysis))
        report["passed"]=False
        report["issues"]=[{"field":"ad_copy.headline",
            "text":"새 검수 규칙","risk_level":"위반 의심",
            "reason":"새 정책에 따라 추가 검토 필요",
            "suggestion":"해당 표현 재검토","basis":"확인 필요"}]
        return report
    monkeypatch.setattr(module,"strict_review",new_policy_result)
    changed=flow.state.apply_copy_revision(
        "alice",jid,json.loads(original["copy_json"]),"동일한 카피 다시 검수",
        original["generation"],original["review_sha"])
    assert changed["copy_sha"]==original["copy_sha"]
    assert changed["generation"]==original["generation"]+1
    assert changed["review_sha"]!=original["review_sha"]
    assert changed["approval_sha"] is None
    with pytest.raises(LiveGateError,match="REAL_COMPLIANCE_BLOCKED"):
        flow.state.approve_copy("alice",jid,changed["generation"],changed["review_sha"])

def test_05_image_retry_preserves_approved_text_and_planning_no_model_replay(tmp_path):
    flow,jid,owner,first=ready(tmp_path)
    flow.state.reject_image("alice",jid,first.sha256)
    before=flow.state.get("alice",jid)
    attempt=flow.begin_image_retry("alice",jid,first.sha256,uuid4().hex)
    after=flow.state.get("alice",jid)
    assert attempt["attempt_version"]==2
    assert all(after[k]==before[k] for k in (
        "analysis_json","research_json","copy_json","copy_sha","review_sha",
        "approval_sha","prompt_json","generation"))
    assert after["image_sha"] is None
    assert owner.calls==["analyze","research","copy","prompt"]

def test_06_restored_old_copy_and_stale_attempt_never_reactivate_approval(tmp_path):
    flow,jid,original,_=create_ready(tmp_path)
    rev=flow.revise_copy("alice",jid,"헤드를 변경해 주세요",
        original["generation"],original["review_sha"],
        provider=FakeRevision(),offline=True)
    restored=flow.state.restore_previous_copy(
        "alice",jid,rev["generation"],rev["review_sha"])
    assert restored["copy_sha"]==original["copy_sha"]
    assert restored["generation"]==original["generation"]+2
    assert restored["review_sha"]!=original["review_sha"]
    assert restored["approval_sha"] is None
    with pytest.raises(LiveGateError,match="STALE_REVIEW_OR_REVISION"):
        flow.state.approve_copy("alice",jid,original["generation"],original["review_sha"])
    other,jid2,_,first=ready(tmp_path/"other")
    other.state.reject_image("alice",jid2,first.sha256)
    other.begin_image_retry("alice",jid2,first.sha256,uuid4().hex)
    with pytest.raises(LiveGateError,match="IMAGE_RETRY_STALE_REJECTION"):
        other.begin_image_retry("alice",jid2,first.sha256,uuid4().hex)
