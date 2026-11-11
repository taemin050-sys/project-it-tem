"""New-only 6-way visual selector. Composed 4:5 needs real crypto validation.

This test uses the existing A51B signed_beta pytest fixture with TEST keys only.
"""
import pytest
from demo_staging.live.a51j_paid_job_scope import derive_server_job_context
from demo_staging.live.a51b_signed_beta_contract import BETA_PREFIX
from demo_staging.live.contracts import LiveGateError
from tests.demo_live.test_pipeline import prepare_service
from tests.demo_live.test_live_contracts import sample_input
from tests.demo_live.test_a51b_signed_beta_contract import signed_beta

@pytest.mark.parametrize("mode,ratio",[
    ("freeform","3:4"),("freeform","4:5"),("freeform","9:16"),
    ("composed","3:4"),("composed","4:5"),("composed","9:16")])
def test_new_only_visual_ingress_does_not_promote_paid(tmp_path,monkeypatch,signed_beta,mode,ratio):
    flow,jid=prepare_service(tmp_path/"isolated")
    monkeypatch.setenv("IT_TEM_A51J_NEW_JOB_ENABLE","YES")
    monkeypatch.setenv("IT_TEM_A51J_COMPOSED45_CHOICE","A")
    monkeypatch.delenv("IT_TEM_A51B_PROFILE",raising=False)
    monkeypatch.delenv("IT_TEM_A5_V3_BETA_PROFILE",raising=False)
    # Prove new input selection does not borrow the A51B legacy OFFLINE-only selector.
    monkeypatch.setenv("IT_TEM_LIVE_ENABLED","YES")
    monkeypatch.setenv("IT_TEM_LIVE_EXECUTION_APPROVED","YES")
    saved=flow.prepare("alice",jid,
        {**sample_input(),"image_size":ratio,"generation_mode":mode},
        template_profile="A")
    visual=flow.state.template("alice",jid)
    if mode=="composed" and ratio=="4:5":
        assert visual["profile_id"]==BETA_PREFIX+"A"
        assert visual["safe_zone"]["real_provider_permitted"] is False
        assert visual["safe_zone"]["candidate_mask_verified"] is False
        assert visual["safe_zone"]["rights_review_verified"] is False
        assert visual["safe_zone"]["real_customer_assets_permitted"] is False
    else:
        assert visual["profile_id"]=="OWNER_IMAGE_SIZE_"+ratio.replace(":","_")
    assert flow.state.get("alice",jid)["mode"]=="INPUT_ONLY"
    with flow.state.db() as conn:
        event_names=[r[0] for r in conn.execute("select event from live_events where job_id=?",(jid,))]
    assert event_names.count("template_a51j_paid_visual_only_ingress")==1


def test_old_signed_selector_still_rejects_live(tmp_path,monkeypatch,signed_beta):
    from demo_staging.live.a51b_signed_beta_contract import select_signed_beta
    monkeypatch.delenv("IT_TEM_A51J_NEW_JOB_ENABLE",raising=False)
    monkeypatch.setenv("IT_TEM_LIVE_ENABLED","YES")
    with pytest.raises(LiveGateError,match="A51B_BETA_PAID_RUNTIME_NOT_ACTIVATED"):
        select_signed_beta({"image_size":"4:5","generation_mode":"composed"},template_profile="A")


def test_unsigned_composed45_cannot_select_when_real_keys_missing(tmp_path,monkeypatch):
    flow,jid=prepare_service(tmp_path)
    monkeypatch.setenv("IT_TEM_A51J_NEW_JOB_ENABLE","YES")
    monkeypatch.setenv("IT_TEM_A51J_COMPOSED45_CHOICE","A")
    monkeypatch.delenv("IT_TEM_A51B_PROFILE",raising=False)
    monkeypatch.delenv("IT_TEM_A5_V3_BETA_PROFILE",raising=False)
    for k in ("IT_TEM_A51B_POLICY_ROOT","IT_TEM_A51B_TRUST_ROOT"):
        monkeypatch.delenv(k,raising=False)
    with pytest.raises(LiveGateError,match="A51J_SIGNED_OWNER_VISUAL_TRUST_MISSING"):
        flow.prepare("alice",jid,
            {**sample_input(),"image_size":"4:5","generation_mode":"composed"},
            template_profile="A")
    with pytest.raises(LiveGateError,match="LIVE_JOB_NOT_FOUND"):
        flow.state.get("alice",jid)
