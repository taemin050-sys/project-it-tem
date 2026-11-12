"""BP18 r0.1 F11/S03 — actual Owner revision prompt + atomic policy version fence.

OFFLINE_FIXTURE ONLY. The LLM call is intercepted at the structured
transport. Neither a paid API nor a copy of a real provider result is used.
"""
import importlib
import json
from copy import deepcopy

import pytest

from demo_staging.live.contracts import LiveGateError
from demo_staging.live.review_policy import current as current_policy
from src.text_generation.schemas import CopyRevisionOutput,AdCopyOutput
from tests.demo_live.test_pipeline import prepare_service,FakeOwner
from tests.demo_live.test_live_contracts import sample_input


@pytest.fixture(autouse=True)
def preserve_offline_lazy_import_boundary():
    """Restore modules imported by intercepted Owner prompt tests.

    The all-suite startup assertions must not observe a fake test's pre-import
    as though the disabled production Worker loaded an API client.
    """
    import sys
    initial=set(sys.modules)
    yield
    for name in ("src.text_generation.copy_generator",
                 "src.text_generation.config",
                 "src.text_generation.llm_client",
                 "src.text_generation.cost"):
        if name not in initial:
            sys.modules.pop(name,None)


@pytest.fixture
def enabled_f11(monkeypatch):
    monkeypatch.setenv("IT_TEM_BP18_F11_ENABLED","YES")
    monkeypatch.setenv("IT_TEM_BP18_REVIEW_POLICY_ID","bp18-f11-test-policy-v1")
    monkeypatch.setenv("OPENAI_API_KEY","offline-placeholder-no-provider")
    return monkeypatch


def start(tmp_path):
    flow,jid=prepare_service(tmp_path)
    flow.prepare("alice",jid,{**sample_input(),"image_size":"4:5",
         "generation_mode":"composed"},template_profile="A")
    text=flow.text("alice",jid,FakeOwner(),offline=True)
    from demo_staging.live.review_policy import enabled
    assert flow.state.policy_status("alice",jid)["status"]==(
        "CURRENT" if enabled() else "LEGACY_POLICY_MODE")
    return flow,jid,text


def fail_review(flow,jid,text):
    copy=deepcopy(json.loads(text["copy_json"]))
    copy["ad_copy"]["headline"]="여드름을 치료합니다"
    bad=flow.state.edit_copy("alice",jid,copy)
    assert bad["copy_sha"]!=text["copy_sha"]
    assert json.loads(bad["compliance_json"])["passed"] is False
    return bad


def test_f11_actual_owner_llm_prompt_contains_review_issue_snapshot(
    tmp_path,enabled_f11
):
    flow,jid,text=start(tmp_path)
    flagged=fail_review(flow,jid,text)
    context=flow.revision_context("alice",jid,"치료 표현 제거",
          flagged["generation"],flagged["review_sha"])
    assert context["review_policy_version"]==current_policy()["version"]
    assert context["review_policy_sha"]==current_policy()["sha"]
    assert context["compliance_issues"]
    assert any(i["risk_level"]=="위반 의심" and "치료" in i["text"]
               for i in context["compliance_issues"])
    owner=importlib.import_module("src.text_generation.copy_generator")
    transport=[]
    def intercepted_llm(prompt,schema,*,instructions,**kwargs):
        assert schema is CopyRevisionOutput
        assert "[BP18 검수 문맥" in prompt
        assert "bp18-structured-compliance-revision-v1" in prompt
        assert context["review_sha"] in prompt
        assert context["compliance_report_sha"] in prompt
        assert context["review_policy_sha"] in prompt
        assert "치료" in prompt and "위반 의심" in prompt
        assert "근거 없는 법률 단정" in prompt
        assert kwargs["model"]=="bp18-offline-no-model"
        transport.append(prompt)
        revised=AdCopyOutput.model_validate_json(
            json.dumps(json.loads(flagged["copy_json"]),ensure_ascii=False))
        revised.ad_copy.headline="촉촉한 보습 하루"
        return CopyRevisionOutput(revised=revised,changed_fields=["headline"],note=None)
    enabled_f11.setattr(owner,"call_structured",intercepted_llm)
    class BTextRevision(FakeOwner):
        def revise_copy(self,product,analysis,research,previous,instruction,
                        *,compliance_context):
            return owner.revise_copy(product,analysis,research,previous,instruction,
                model="bp18-offline-no-model",
                compliance_context=compliance_context)
    new=flow.revise_copy("alice",jid,"치료 표현 제거",
          flagged["generation"],flagged["review_sha"],
          provider=BTextRevision(),offline=True)
    assert len(transport)==1
    assert new["generation"]==flagged["generation"]+1
    assert new["copy_sha"]!=flagged["copy_sha"]
    assert json.loads(new["compliance_json"])["passed"] is True
    assert new["approval_sha"] is None
    assert flow.state.policy_status("alice",jid)["status"]=="CURRENT"
    with pytest.raises(LiveGateError,match="STALE_REVIEW_OR_REVISION"):
        flow.state.approve_copy("alice",jid,flagged["generation"],flagged["review_sha"])
    approval=flow.state.approve_copy("alice",jid,new["generation"],new["review_sha"],
                                  acknowledge_evidence=True)
    assert approval["approval_sha"]
    with flow.cost.connect() as con:
        assert con.execute("select count(*) from attempts").fetchone()[0]==0


def test_policy_version_only_change_invalidates_existing_approval_and_blocks_image(
    tmp_path,enabled_f11
):
    flow,jid,text=start(tmp_path)
    allowed=flow.state.approve_copy("alice",jid,text["generation"],
                                  text["review_sha"],acknowledge_evidence=True)
    prior_sha=allowed["approval_sha"]
    assert prior_sha
    enabled_f11.setenv("IT_TEM_BP18_REVIEW_POLICY_ID","bp18-f11-test-policy-v2")
    from demo_staging.live.store import LiveStore
    flow.state=LiveStore(flow.state.filename)
    stale=flow.state.policy_status("alice",jid)
    assert stale["status"]=="REVALIDATION_REQUIRED"
    with pytest.raises(LiveGateError,match="REVIEW_POLICY_REVALIDATION_REQUIRED"):
        flow.prompt("alice",jid,FakeOwner(),offline=True)
    # Same copy SHA does not imply the review/approval can be reused.
    renewed=flow.state.revalidate_review_policy("alice",jid,
        allowed["generation"],allowed["review_sha"])
    assert renewed["generation"]==allowed["generation"]+1
    assert renewed["copy_sha"]==allowed["copy_sha"]
    assert renewed["review_sha"]!=allowed["review_sha"]
    assert renewed["approval_sha"] is None
    assert renewed["prompt_json"] is None and renewed["image_sha"] is None
    assert flow.state.policy_status("alice",jid)["status"]=="CURRENT"
    with pytest.raises(LiveGateError,match="STALE_REVIEW_OR_REVISION"):
        flow.state.approve_copy("alice",jid,allowed["generation"],allowed["review_sha"])
    new_approval=flow.state.approve_copy("alice",jid,renewed["generation"],
                                       renewed["review_sha"],acknowledge_evidence=True)
    assert new_approval["approval_sha"]!=prior_sha
    flow.prompt("alice",jid,FakeOwner(),offline=True)
    assert flow.state.get("alice",jid)["state"]=="PROMPT_READY"


def test_f11_policy_change_blocks_noop_and_restore_before_mutation(
    tmp_path,enabled_f11
):
    flow,jid,initial=start(tmp_path)
    bad=fail_review(flow,jid,initial)
    enabled_f11.setenv("IT_TEM_BP18_REVIEW_POLICY_ID","bp18-f11-test-policy-v3")
    from demo_staging.live.store import LiveStore
    flow.state=LiveStore(flow.state.filename)
    with pytest.raises(LiveGateError,match="REVIEW_POLICY_REVALIDATION_REQUIRED"):
        flow.state.apply_copy_revision("alice",jid,json.loads(bad["copy_json"]),
              "no op",bad["generation"],bad["review_sha"])
    assert flow.state.get("alice",jid)["generation"]==bad["generation"]
    renewed=flow.state.revalidate_review_policy("alice",jid,
               bad["generation"],bad["review_sha"])
    assert renewed["copy_sha"]==bad["copy_sha"]
    assert json.loads(renewed["compliance_json"])["passed"] is False
    with pytest.raises(LiveGateError,match="REAL_COMPLIANCE_BLOCKED"):
        flow.state.approve_copy("alice",jid,
              renewed["generation"],renewed["review_sha"])
    with pytest.raises(LiveGateError,match="REVIEW_POLICY_ALREADY_CURRENT"):
        flow.state.revalidate_review_policy("alice",jid,
              renewed["generation"],renewed["review_sha"])


def test_f11_policy_stamp_tampering_denies_noop_and_revalidation(
    tmp_path,enabled_f11
):
    flow,jid,current=start(tmp_path)
    with flow.state.db() as con:
        con.execute("UPDATE live_review_policy SET policy_sha=? WHERE job_id=?",
            ("0"*64,jid))
    assert flow.state.policy_status("alice",jid)["status"]=="BINDING_TAMPERED"
    with pytest.raises(LiveGateError,match="REVIEW_POLICY_BINDING_TAMPERED"):
        flow.revision_context("alice",jid,"표현 수정",
              current["generation"],current["review_sha"])
    with pytest.raises(LiveGateError,match="REVIEW_POLICY_BINDING_TAMPERED"):
        flow.state.approve_copy("alice",jid,
              current["generation"],current["review_sha"])
    with pytest.raises(LiveGateError,match="REVIEW_POLICY_BINDING_TAMPERED"):
        flow.state.revalidate_review_policy("alice",jid,
              current["generation"],current["review_sha"])
    with flow.cost.connect() as con:
        assert con.execute("select count(*) from attempts").fetchone()[0]==0


def test_f11_historical_pending_legacy_cannot_mutate_without_explicit_revalidate(
    tmp_path,monkeypatch
):
    monkeypatch.delenv("IT_TEM_BP18_F11_ENABLED",raising=False)
    flow,jid,text=start(tmp_path)
    approved=flow.state.approve_copy("alice",jid,text["generation"],text["review_sha"])
    flow.prompt("alice",jid,FakeOwner(),offline=True)
    # Historical pending pre-policy Jobs are never silently stamped on upgrade.
    monkeypatch.setenv("IT_TEM_BP18_F11_ENABLED","YES")
    # Enabling a new policy is a deployment/restart operation, not an in-place
    # rule-source hot reload (which must fail closed).
    from demo_staging.live.store import LiveStore
    flow.state=LiveStore(flow.state.filename)
    assert flow.state.policy_status("alice",jid)["status"]=="LEGACY_UNBOUND"
    assert flow.state.get("alice",jid)["approval_sha"]==approved["approval_sha"]
    with pytest.raises(LiveGateError,match="REVIEW_POLICY_REVALIDATION_REQUIRED"):
        flow.image_input("alice",jid)
    # Pending legacy can only advance by explicit policy revalidation.
    changed=flow.state.revalidate_review_policy("alice",jid,
                 text["generation"],text["review_sha"])
    assert changed["generation"]==text["generation"]+1
    assert changed["approval_sha"] is None
