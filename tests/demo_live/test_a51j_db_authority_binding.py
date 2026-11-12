"""R6: prove Paid Scope source comes from actual B0 + LiveStore, not caller JSON."""
import pytest
from fastapi.testclient import TestClient
from demo_staging.live.a51j_paid_job_scope import derive_server_job_context
from demo_staging.live.contracts import LiveGateError
from tests.demo_live.test_http_gateway import setup,login,photo
from tests.demo_live.test_live_contracts import sample_input

SHA="46c8bb5d57fe54ff2a9d3d115fdb7a72b5150bb8"
ORIGIN={"Origin":"http://testserver"}

def fresh(tmp_path,mode,ratio):
    app,codes=setup(tmp_path)
    with TestClient(app,client=("127.0.0.1",12021)) as client:
        login(client,codes["alice"])
        r=client.post("/api/v1/jobs",files=[
            ("product_images",("front.png",photo((130,145,140)),"image/png")),
            ("product_images",("angle.png",photo((155,162,150)),"image/png"))
        ],headers=ORIGIN)
        assert r.status_code==201,r.text
        jid=r.json()["job_id"]
        r=client.post(f"/demo/api/live/jobs/{jid}/input",
            json={**sample_input(),"generation_mode":mode,"image_size":ratio},
            headers=ORIGIN)
        assert r.status_code==200,r.text
    return app,jid

@pytest.mark.parametrize("mode,ratio,expected_overlay",[
    ("freeform","3:4",False),
    ("freeform","4:5",False),
    ("freeform","9:16",False),
    ("composed","3:4",True),
    ("composed","9:16",True),
])
def test_true_db_and_source_bytes_authority(tmp_path,mode,ratio,expected_overlay):
    app,jid=fresh(tmp_path,mode,ratio)
    got=derive_server_job_context(flow=app.state.live_pipeline,
        actor="alice",job_id=jid,deployed_source_sha=SHA)
    assert got["job_id"]==jid and got["actor"]=="alice"
    assert got["source_commit"]==SHA
    assert got["one_candidate"] is True
    assert got["mode"]==mode and got["ratio"]==ratio
    assert got["owner_design_profile"]=="OWNER_IMAGE_SIZE_"+ratio.replace(":","_")
    assert got["current_state"]=="INPUT_STORED"
    assert got["current_provenance"]=="INPUT_ONLY"
    assert got["ordered_assets_sha256"]
    assert ("owner_ratio_composition" if expected_overlay else
           "provider_text_single_image")==got["rendering"]

def test_composed45_unsigned_design_not_auto_promoted(tmp_path):
    app,jid=fresh(tmp_path,"composed","4:5")
    with pytest.raises(LiveGateError,match="A51J_COMPOSED45_REQUIRES_SIGNED_OWNER_DESIGN"):
        derive_server_job_context(flow=app.state.live_pipeline,
            actor="alice",job_id=jid,deployed_source_sha=SHA)

def test_cross_actor_and_job_no_impersonation(tmp_path):
    app,jid=fresh(tmp_path,"freeform","4:5")
    with pytest.raises(LiveGateError,match="A51J_SERVER_ACTOR_JOB_NOT_OWNED"):
        derive_server_job_context(flow=app.state.live_pipeline,
            actor="bob",job_id=jid,deployed_source_sha=SHA)
    with pytest.raises(LiveGateError,match="A51J_SERVER_IDENTITY_OR_SOURCE_INVALID"):
        derive_server_job_context(flow=app.state.live_pipeline,
            actor="alice",job_id=jid,deployed_source_sha="bad")

def test_b0_asset_mutation_does_not_authorize_paid_scope(tmp_path):
    app,jid=fresh(tmp_path,"composed","3:4")
    original=app.state.job_store.get_job(jid)
    asset=original["assets"][0]
    path,record=app.state.job_store.get_asset(jid,asset["asset_id"])
    path.write_bytes(b"tampered-real-source-bytes")
    with pytest.raises(LiveGateError,match="A51F_RIGHTS_ASSET_SHA_CHANGED"):
        derive_server_job_context(flow=app.state.live_pipeline,
            actor="alice",job_id=jid,deployed_source_sha=SHA)

def test_bad_live_input_record_cannot_enter_paid_scope(tmp_path):
    app,jid=fresh(tmp_path,"freeform","9:16")
    flow=app.state.live_pipeline
    with flow.state.db() as conn:
        conn.execute("UPDATE live_jobs SET input_sha=? WHERE job_id=?",("0"*64,jid))
    with pytest.raises(LiveGateError,match="A51J_LIVESTORE_INPUT_HASH_CHANGED"):
        derive_server_job_context(flow=flow,
            actor="alice",job_id=jid,deployed_source_sha=SHA)

def test_client_supplied_sku_does_not_become_authority(tmp_path):
    app,jid=fresh(tmp_path,"composed","9:16")
    got=derive_server_job_context(flow=app.state.live_pipeline,
         actor="alice",job_id=jid,deployed_source_sha=SHA)
    assert "product_sku" not in got
    assert "source_rights_decision_sha256" not in got
    assert "source_protection_plan_sha256" not in got
    assert "pm_cost_policy_sha256" not in got
