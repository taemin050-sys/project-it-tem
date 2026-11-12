"""R6 NEW paid last-mile source & signer negative gates. NO billable calls."""
import pytest
from demo_staging.live.a51j_paid_job_scope import verify_worker_paid_scope
from demo_staging.live.contracts import LiveGateError
from tests.demo_live.test_pipeline import prepare_service
from tests.demo_live.test_live_contracts import sample_input

def test_paid_scope_is_default_off_even_with_a_real_b0_job(tmp_path,monkeypatch):
    flow,jid=prepare_service(tmp_path)
    flow.prepare("alice",jid,{**sample_input(),"generation_mode":"freeform",
        "image_size":"4:5"},template_profile="A")
    monkeypatch.delenv("IT_TEM_A51J_PAID_SCOPE_RUNTIME",raising=False)
    with pytest.raises(LiveGateError,match="A51J_SIGNED_PAID_SCOPE_RUNTIME_DISABLED"):
        verify_worker_paid_scope(flow=flow,actor="alice",job_id=jid)

def test_new_runtime_flag_cannot_replace_actual_pm_signature(tmp_path,monkeypatch):
    flow,jid=prepare_service(tmp_path)
    flow.prepare("alice",jid,{**sample_input(),"generation_mode":"composed",
        "image_size":"3:4"},template_profile="A")
    monkeypatch.setenv("IT_TEM_A51J_PAID_SCOPE_RUNTIME","YES")
    monkeypatch.delenv("IT_TEM_A51C_COST_POLICY_ROOT",raising=False)
    monkeypatch.delenv("IT_TEM_A51C_COST_TRUST_ROOT",raising=False)
    with pytest.raises(LiveGateError,match="A51C_HARD_CAP"):
        verify_worker_paid_scope(flow=flow,actor="alice",job_id=jid)

def test_pre_generation_field_does_not_claim_candidate_verified():
    from demo_staging.live.a51j_paid_job_scope import BASE
    assert "source_protection_plan_sha256" in BASE
    assert "mask_review_decision_sha256" not in BASE


def test_candidate_post_review_never_predates_actual_output(tmp_path):
    from demo_staging.live.a51j_paid_job_scope import verify_post_candidate_signed_review
    flow,jid=prepare_service(tmp_path)
    flow.prepare("alice",jid,{**sample_input(),"generation_mode":"composed",
        "image_size":"3:4"},template_profile="A")
    with pytest.raises(LiveGateError,match="A51J_POST_REVIEW_REQUIRES_IMAGE_APPROVAL"):
        verify_post_candidate_signed_review(flow=flow,actor="alice",job_id=jid)


def test_new_job_cannot_downgrade_to_legacy_compose_on_restart(tmp_path,monkeypatch):
    monkeypatch.setenv("IT_TEM_A51J_NEW_JOB_ENABLE","YES")
    monkeypatch.delenv("IT_TEM_A51B_PROFILE",raising=False)
    monkeypatch.delenv("IT_TEM_A5_V3_BETA_PROFILE",raising=False)
    flow,jid=prepare_service(tmp_path)
    flow.prepare("alice",jid,{**sample_input(),"generation_mode":"freeform",
        "image_size":"4:5"},template_profile="A")
    monkeypatch.delenv("IT_TEM_A51J_PAID_SCOPE_RUNTIME",raising=False)
    with pytest.raises(LiveGateError,match="A51J_PAID_JOB_COMPOSE_RUNTIME_DOWNGRADE_FORBIDDEN"):
        flow.compose("alice",jid,font_path=None)
