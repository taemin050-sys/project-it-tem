"""Dual-mode route evidence with no network, provider keys or paid attempts."""
import hashlib
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image,ImageChops

from demo_staging.live import dual_fixture
from tests.demo_live.test_http_gateway import login,photo,setup
from tests.demo_live.test_live_contracts import sample_input
from tests.demo_live.test_pipeline import FONT


ORIGIN={"Origin":"http://testserver"}


@pytest.fixture
def dual_app(tmp_path,monkeypatch):
    monkeypatch.setenv("IT_TEM_BP18_DUAL_QA_ENABLED","YES")
    monkeypatch.setenv("IT_TEM_QA_FIXTURE_ENABLED","YES")
    monkeypatch.setenv("IT_TEM_LIVE_ENABLED","NO")
    monkeypatch.setenv("IT_TEM_LIVE_EXECUTION_APPROVED","NO")
    monkeypatch.setenv("IT_TEM_DEMO_SECURE_COOKIE","NO")
    monkeypatch.setenv("IT_TEM_QA_ALLOWED_ACTORS","alice,bob")
    monkeypatch.setenv("IT_TEM_LIVE_KOREAN_FONT",str(FONT))
    monkeypatch.delenv("OPENAI_API_KEY",raising=False)
    return setup(tmp_path)


def create(client,ratio):
    response=client.post("/api/v1/jobs",files=[
        ("product_images",("a.png",photo((120,130,140)),"image/png")),
        ("product_images",("b.png",photo((150,160,170)),"image/png")),
    ],headers=ORIGIN)
    assert response.status_code==201,response.text
    job_id=response.json()["job_id"]
    live=f"/demo/api/live/jobs/{job_id}"
    qa=f"/demo/api/qa/jobs/{job_id}"
    dual=qa+"/dual"
    assert client.get(live).status_code==404
    assert client.get(dual).status_code==404
    prepared=client.post(dual+"/input",json={**sample_input(),"image_size":ratio,
                         "generation_mode":"composed"},headers=ORIGIN)
    assert prepared.status_code==200,prepared.text
    assert prepared.json()["dual_requested"] is True
    ready=client.get(dual).json()
    assert ready["state"]=="READY"
    assert ready["variants"]["freeform"] is None
    assert ready["provenance"]=="OFFLINE_FIXTURE"
    text=client.post(qa+"/text",headers=ORIGIN)
    assert text.status_code==200,text.text
    snapshot=text.json()
    approval={"expected_generation":snapshot["generation"],"expected_review_sha":snapshot["review_sha"]}
    return live,qa,dual,approval,snapshot


def decision(client,dual,variant,*,approve=True,visual_checked=True):
    return client.post(dual+f"/{variant['mode']}/decision",json={"image_sha":variant["candidate_sha"],
        "approve":approve,"visual_checked":visual_checked},headers=ORIGIN)


def artifact(client,variant,kind):
    response=client.get(variant["artifacts"][kind])
    assert response.status_code==200,response.text
    assert response.headers["x-it-tem-provenance"]=="OFFLINE_FIXTURE"
    assert hashlib.sha256(response.content).hexdigest()==variant[f"{kind}_sha"]
    return response


@pytest.mark.parametrize("ratio,size",[("3:4",(1080,1440)),("4:5",(1080,1350)),("9:16",(1080,1920))])
def test_dual_qa_both_variants_keep_the_same_approval_and_independent_final_artifacts(dual_app,ratio,size):
    app,codes=dual_app
    with TestClient(app,client=("127.0.0.1",12121)) as user, \
         TestClient(app,client=("127.0.0.1",12122)) as peer:
        login(user,codes["alice"]);login(peer,codes["bob"])
        assert user.get("/demo/api/live/capabilities").json()["dual_qa_enabled"] is True
        live,qa,dual,approval,copy=create(user,ratio)
        assert peer.get(dual).status_code==404
        assert peer.post(dual+"/start",json=approval,headers=ORIGIN).status_code==404
        assert user.post(live+"/approve-copy",json=approval,headers=ORIGIN).status_code==409
        stale={**approval,"expected_generation":approval["expected_generation"]+1}
        assert user.post(dual+"/start",json=stale,headers=ORIGIN).status_code==409
        started=user.post(dual+"/start",json=approval,headers=ORIGIN)
        assert started.status_code==200,started.text
        first=started.json()
        assert first["state"]=="REVIEW_REQUIRED"
        assert first["copy_sha"]==copy["copy_sha"]
        assert first["copy_approval_sha"]
        assert first["image_size"]==ratio
        assert user.post(dual+"/start",json=approval,headers=ORIGIN).json()==first
        assert user.post(qa+"/prompt-image",headers=ORIGIN).status_code==409
        assert user.post(live+"/queue-image",headers=ORIGIN).status_code==409
        composed,freeform=(first["variants"][mode] for mode in ("composed","freeform"))
        assert composed["variant_job_id"]!=freeform["variant_job_id"]
        assert composed["approval_sha"] and freeform["approval_sha"]
        assert composed["review_sha"] and freeform["review_sha"]
        assert first["copy_approval_sha"]==composed["approval_sha"]!=freeform["approval_sha"]
        store=app.state.live_pipeline.state
        parent=store.get("alice",composed["variant_job_id"])
        child=store.get("alice",freeform["variant_job_id"])
        for shared in ("analysis_json","copy_json","compliance_json","copy_sha","generation"):
            assert parent[shared]==child[shared]
        assert composed["candidate_sha"]!=freeform["candidate_sha"]
        assert set(composed["artifacts"])==set(freeform["artifacts"])=={"candidate"}
        assert user.get(dual+"/freeform/artifacts/final",params={"sha256":"0"*64}).status_code==409
        assert peer.get(freeform["artifacts"]["candidate"]).status_code==404
        assert user.get(f"/demo/api/live/jobs/{freeform['variant_job_id']}").status_code==404
        assert user.post(live+"/approve-image",json={"image_sha":composed["candidate_sha"]},
                         headers=ORIGIN).status_code==409
        assert decision(user,dual,freeform,visual_checked=False).status_code==409
        assert decision(user,dual,{**freeform,"candidate_sha":composed["candidate_sha"]}).status_code==409
        candidate=artifact(user,freeform,"candidate")

        first_approval=decision(user,dual,composed)
        assert first_approval.status_code==200,first_approval.text
        assert first_approval.json()["state"]=="PARTIAL"
        assert first_approval.json()["variants"]["freeform"]["state"]=="IMAGE_REVIEW_REQUIRED"
        second_approval=decision(user,dual,freeform)
        assert second_approval.status_code==200,second_approval.text
        complete=second_approval.json()
        assert complete["state"]=="COMPLETED"
        assert decision(user,dual,freeform).json()==complete
        final_variants=complete["variants"]
        assert final_variants["composed"]["final_sha"]!=final_variants["freeform"]["final_sha"]
        assert final_variants["composed"]["image_review_sha"]!=final_variants["freeform"]["image_review_sha"]
        assert final_variants["composed"]["receipt_sha"]!=final_variants["freeform"]["receipt_sha"]
        captions=[]
        for mode,variant in final_variants.items():
            assert variant["verification_state"]=="FIXTURE_REVIEWED"
            assert variant["cost"]=={"provider_attempt_count":0,"actual_usd":None}
            png=artifact(user,variant,"final")
            captions.append(artifact(user,variant,"caption").content.decode("utf-8"))
            receipt=artifact(user,variant,"receipt").json()
            assert receipt["provider_calls"]==0
            assert receipt["provenance"]=="OFFLINE_FIXTURE"
            with Image.open(BytesIO(png.content)) as final:
                assert final.format=="PNG" and final.size==size
                if mode=="freeform":
                    assert receipt.get("font_sha256") is None
                    assert receipt["fixture_rendering"]=="QA_SYNTHETIC_KOREAN_FIXTURE"
                    with Image.open(BytesIO(candidate.content)) as raw:
                        expected=raw.convert("RGB").resize(size,Image.Resampling.LANCZOS)
                    assert ImageChops.difference(final.convert("RGB"),expected).getbbox() is None
        assert captions[0]==captions[1]
        assert copy["copy"]["caption"] in captions[0]
        target=final_variants["freeform"]
        assert user.get(target["artifacts"]["final"].replace(target["final_sha"],"0"*64)).status_code==409
        selection={"mode":"freeform","final_sha":target["final_sha"]}
        assert user.post(dual+"/selection",json={**selection,"final_sha":"0"*64},
                         headers=ORIGIN).status_code==409
        selected=user.post(dual+"/selection",json=selection,headers=ORIGIN)
        assert selected.status_code==200,selected.text
        assert selected.json()["preferred_variant"]=="freeform"
        assert user.get(dual).json()["preferred_variant"]=="freeform"
        assert user.post(live+"/share",headers=ORIGIN).status_code==409
        with app.state.live_pipeline.cost.connect() as db:
            assert db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]==0


def test_freeform_render_failure_does_not_lose_composed_and_is_not_automatically_retried(dual_app,monkeypatch):
    app,codes=dual_app
    render_calls=[]

    def unavailable(*args):
        render_calls.append(True)
        raise OSError("private diagnostic details")

    monkeypatch.setattr(dual_fixture,"render_freeform_fixture",unavailable)
    with TestClient(app,client=("127.0.0.1",12121)) as user:
        login(user,codes["alice"])
        _,_,dual,approval,_=create(user,"4:5")
        started=user.post(dual+"/start",json=approval,headers=ORIGIN)
        assert started.status_code==200,started.text
        assert "private diagnostic details" not in started.text
        partial=started.json()
        assert partial["state"]=="PARTIAL"
        failed=partial["variants"]["freeform"]
        assert failed["state"]=="FAILED"
        assert failed["error_code"]=="DUAL_FIXTURE_RENDER_FAILED"
        assert failed["artifacts"]=={}
        assert user.post(dual+"/start",json=approval,headers=ORIGIN).json()==partial
        assert len(render_calls)==1
        approved=decision(user,dual,partial["variants"]["composed"])
        assert approved.status_code==200,approved.text
        assert approved.json()["state"]=="PARTIAL"
        artifact(user,approved.json()["variants"]["composed"],"final")


def test_dual_qa_refuses_nonloopback_even_with_allowed_fixture_actor(dual_app):
    app,codes=dual_app
    with TestClient(app,client=("198.51.100.1",12121)) as user:
        login(user,codes["alice"])
        assert user.get("/demo/api/live/capabilities").json()["dual_qa_enabled"] is False
        assert user.get("/demo/api/qa/jobs/"+"0"*32+"/dual").status_code==404


@pytest.mark.parametrize("variable,value",[
    ("IT_TEM_BP18_DUAL_QA_ENABLED","NO"),
    ("IT_TEM_QA_FIXTURE_ENABLED","NO"),
    ("IT_TEM_LIVE_ENABLED","YES"),
    ("IT_TEM_LIVE_EXECUTION_APPROVED","YES"),
])
def test_dual_qa_requires_explicit_isolated_fixture_environment(dual_app,tmp_path,monkeypatch,variable,value):
    monkeypatch.setenv(variable,value)
    app,codes=setup(tmp_path/"disabled")
    with TestClient(app,client=("127.0.0.1",12121)) as user:
        login(user,codes["alice"])
        assert user.get("/demo/api/live/capabilities").json()["dual_qa_enabled"] is False
        blocked=user.get("/demo/api/qa/jobs/"+"0"*32+"/dual")
        assert blocked.status_code==404
        assert blocked.json()["detail"]=="Dual QA fixture endpoint disabled"


def test_rejected_freeform_does_not_remove_the_composed_download(dual_app):
    app,codes=dual_app
    with TestClient(app,client=("127.0.0.1",12121)) as user:
        login(user,codes["alice"])
        _,_,dual,approval,_=create(user,"4:5")
        started=user.post(dual+"/start",json=approval,headers=ORIGIN).json()
        composed,freeform=(started["variants"][mode] for mode in ("composed","freeform"))
        completed=decision(user,dual,composed).json()["variants"]["composed"]
        rejected=decision(user,dual,freeform,approve=False,visual_checked=False)
        assert rejected.status_code==200,rejected.text
        result=rejected.json()
        assert result["state"]=="PARTIAL"
        assert result["variants"]["freeform"]["verification_state"]=="FIXTURE_REJECTED"
        assert result["variants"]["freeform"]["artifacts"]=={}
        assert user.get(freeform["artifacts"]["candidate"]).status_code==409
        assert user.post(dual+"/start",json=approval,headers=ORIGIN).json()==result
        artifact(user,completed,"final")


def test_corrupt_visual_attestation_isolated_to_one_result_and_selected_sha_is_hidden(dual_app):
    app,codes=dual_app
    with TestClient(app,client=("127.0.0.1",12121)) as user:
        login(user,codes["alice"])
        live,_,dual,approval,_=create(user,"4:5")
        first=user.post(dual+"/start",json=approval,headers=ORIGIN).json()
        assert decision(user,dual,first["variants"]["composed"]).status_code==200
        final=decision(user,dual,first["variants"]["freeform"]).json()["variants"]
        composed=final["composed"]
        selected=user.post(dual+"/selection",json={"mode":"composed","final_sha":composed["final_sha"]},
                           headers=ORIGIN)
        assert selected.json()["preferred_variant"]=="composed"
        with app.state.live_pipeline.state.db() as db:
            db.execute("UPDATE live_dual_variants SET visual_review_json='{}' WHERE job_id=?",
                       (composed["variant_job_id"],))
        assert user.get(live).json()["dual_requested"] is True
        partial=user.get(dual).json()
        assert partial["state"]=="PARTIAL"
        assert partial["preferred_variant"] is None
        assert partial["variants"]["composed"]["state"]=="FAILED"
        assert user.get(composed["artifacts"]["receipt"]).status_code==409
        artifact(user,partial["variants"]["freeform"],"final")


def test_interrupted_dispatch_is_marked_failed_without_replay_and_other_mode_can_run(dual_app,monkeypatch):
    app,codes=dual_app
    render_calls=[]
    render_composed=dual_fixture.render_composed_fixture

    def track(*args):
        render_calls.append(True)
        return render_composed(*args)

    monkeypatch.setattr(dual_fixture,"render_composed_fixture",track)
    with TestClient(app,client=("127.0.0.1",12121)) as user:
        login(user,codes["alice"])
        _,_,dual,approval,snapshot=create(user,"4:5")
        job_id=snapshot["job_id"]
        store=app.state.live_pipeline.state
        store.start_dual("alice",job_id,**approval)
        with store.dual_dispatch_lock("alice",job_id,job_id) as acquired:
            assert acquired
        assert user.get(dual).json()["state"]=="GENERATING"
        resumed=user.post(dual+"/start",json=approval,headers=ORIGIN)
        assert resumed.status_code==200,resumed.text
        state=resumed.json()
        assert state["state"]=="PARTIAL"
        assert state["variants"]["composed"]["error_code"]=="DUAL_FIXTURE_DISPATCH_INTERRUPTED"
        assert state["variants"]["freeform"]["state"]=="IMAGE_REVIEW_REQUIRED"
        assert not render_calls


def test_same_decision_retries_only_failed_composition_after_durable_visual_approval(dual_app,monkeypatch):
    app,codes=dual_app
    flow=app.state.live_pipeline
    compose=flow.compose
    compose_calls=[]

    def interrupted(*args,**kwargs):
        compose_calls.append(True)
        if len(compose_calls)==1:
            raise OSError("injected local write failure")
        return compose(*args,**kwargs)

    monkeypatch.setattr(flow,"compose",interrupted)
    with TestClient(app,client=("127.0.0.1",12121)) as user:
        login(user,codes["alice"])
        _,_,dual,approval,_=create(user,"4:5")
        initial=user.post(dual+"/start",json=approval,headers=ORIGIN).json()["variants"]["freeform"]
        assert decision(user,dual,initial).status_code==503
        recover=user.get(dual).json()["variants"]["freeform"]
        assert recover["state"]=="IMAGE_APPROVED"
        assert recover["image_review_sha"]
        assert recover["candidate_sha"]==initial["candidate_sha"]
        resumed=decision(user,dual,initial)
        assert resumed.status_code==200,resumed.text
        completed=resumed.json()["variants"]["freeform"]
        assert completed["image_review_sha"]==recover["image_review_sha"]
        assert completed["state"]=="COMPLETED"
        assert len(compose_calls)==2
        artifact(user,completed,"final")
