"""Signed evaluator own-Job revisions over nonbillable MockTransport only."""
from copy import deepcopy
import json

from fastapi.testclient import TestClient
import pytest

from demo_staging.live import worker
from demo_staging.live.composed_copy_edit import run_composed_copy_edit_once
from demo_staging.live.dual_worker import live_dual_profile
from demo_staging.live.image_correction import run_image_correction_once
from tests.demo_live.test_http_gateway import photo
from tests.demo_live.test_image_correction import wire_transport
from tests.demo_live.test_live_dual_mock_transport import (
    ACTOR, OTHER_ACTOR, TEXT_MODEL, dual_runtime, signed_env, signed_request, install_images, run_stage, sample_input, attempts,
)

EVALUATOR = OTHER_ACTOR


@pytest.fixture
def evaluator_owned(dual_runtime,monkeypatch):
    root,host,key,app,flow,text=dual_runtime
    monkeypatch.setenv("IT_TEM_LIVE_APPROVED_ACTORS", EVALUATOR)
    flow.approved_actors=frozenset({EVALUATOR})
    monkeypatch.setenv("IT_TEM_IMAGE_CORRECTION_ENABLED","YES")
    monkeypatch.setenv("IT_TEM_IMAGE_CORRECTION_PROTOCOL","FREEFORM_TEXT_EDIT_V1")
    monkeypatch.setenv("IT_TEM_COMPOSED_COPY_EDIT_ENABLED","YES")
    monkeypatch.setenv("IT_TEM_COMPOSED_COPY_EDIT_WORKER_PROTOCOL","COMPOSED_COPY_EDIT_V1")
    calls=[];install_images(monkeypatch,flow,calls)
    with TestClient(app,base_url=f"https://{host}") as client:
        uploaded=signed_request(client,host,key,"POST","/api/v1/jobs",actor=EVALUATOR,files=[
            ("product_images",("a.png",photo((120,130,140)),"image/png")),
            ("product_images",("b.png",photo((150,160,170)),"image/png"))])
        assert uploaded.status_code==201,uploaded.text
        parent=uploaded.json()["job_id"]
    flow.prepare(EVALUATOR,parent,{**sample_input(),"image_size":"4:5","generation_mode":"composed"},
                 template_profile="A",live_dual=True)
    review=flow.text(EVALUATOR,parent,text_model=TEXT_MODEL)
    flow.verify_live_dual_f09(EVALUATOR,parent)
    group=flow.state.start_live_dual(EVALUATOR,parent,expected_generation=review["generation"],
        expected_review_sha=review["review_sha"],execution_profile=live_dual_profile(),acknowledge_two_images=True)
    for _ in range(3):assert run_stage(root)=="LIVE_STAGE_COMMITTED"
    return root,host,key,app,flow,parent,group["child_job_id"],calls


def copy_body(flow,parent):
    source=flow.state.get(EVALUATOR,parent)
    ad=json.loads(source["copy_json"])["ad_copy"]
    ad.update(headline="매일의 샴푸 시간",subline="차분하게 시작해요",cta="제품 만나기")
    return {"expected_image_sha":source["image_sha"],"expected_copy_sha":source["copy_sha"],
            "expected_approval_sha":source["approval_sha"],"request_key":"1"*32,"ad_copy":ad}


def correction_body(flow,child):
    source=flow.state.get(EVALUATOR,child)
    return {"expected_image_sha":source["image_sha"],"expected_copy_sha":source["copy_sha"],
        "expected_approval_sha":source["approval_sha"],"request_key":"2"*32,"field":"subline",
        "observed_text":"자분하게 시작해요","region":[.1,.2,.8,.3],"acknowledge_paid_edit":True}


def test_registered_evaluator_own_manual_copy_and_image_approval_without_admin(evaluator_owned):
    root,host,key,app,flow,parent,child,calls=evaluator_owned
    original={job:flow.state.get(EVALUATOR,job) for job in (parent,child)}
    with TestClient(app,base_url=f"https://{host}") as client:
        base=f"/demo/api/live/jobs/{parent}/composed-copy-edits"
        def req(method,suffix="",**kwargs):
            with worker.exclusive_live_worker(root):
                return signed_request(client,host,key,method,base+suffix,actor=EVALUATOR,**kwargs)
        session=signed_request(client,host,key,"GET","/demo/api/session",actor=EVALUATOR)
        assert session.status_code==200 and session.json()["role"]=="evaluator"
        response=req("POST",json=copy_body(flow,parent))
        assert response.status_code==202,response.text
        assert run_composed_copy_edit_once(flow)=="COMPOSED_COPY_EDIT_REVIEW_COMMITTED"
        reviewed=req("GET").json()["edits"][0]
        assert reviewed["state"]=="COPY_REVIEW_REQUIRED"
        suffix="/"+reviewed["edit_id"]
        response=req("POST",suffix+"/copy-approval",json={"expected_revision":reviewed["revision"],
            "expected_copy_sha":reviewed["copy_sha"],"expected_review_sha":reviewed["review_sha"],"acknowledge_evidence":True})
        assert response.status_code==200,response.text
        preview=response.json()
        decision={"expected_revision":preview["revision"],"expected_preview_sha":preview["preview_sha"],"approve":True,
            "visual_review":{"product_matches":True,"label_matches":True,"cta_policy_matches":True,"no_extra_text":True,
                             "observed_copy":reviewed["copy"]["ad_copy"]}}
        response=req("POST",suffix+"/decision",json=decision)
        assert response.status_code==200,response.text
        assert response.json()["state"]=="COMPLETED"
        for name,url in response.json()["artifacts"].items():
            assert signed_request(client,host,key,"GET",url,actor=EVALUATOR).status_code==200
            assert signed_request(client,host,key,"GET",url,actor=ACTOR).status_code==404
        assert client.post(base,json=copy_body(flow,parent)).status_code==401
        assert signed_request(client,host,key,"POST",base,actor=ACTOR,json=copy_body(flow,parent)).status_code==404
        assert signed_request(client,host,key,"GET","/demo/api/admin/evaluations",actor=EVALUATOR).status_code==403
    assert {job:flow.state.get(EVALUATOR,job) for job in (parent,child)}==original
    assert len(calls)==2 and len(attempts(flow))==8


def test_registered_evaluator_own_freeform_correction_and_decision(evaluator_owned):
    root,host,key,app,flow,parent,child,calls=evaluator_owned
    before={job:flow.state.get(EVALUATOR,job) for job in (parent,child)}
    with TestClient(app,base_url=f"https://{host}") as client:
        base=f"/demo/api/live/jobs/{child}/image-corrections"
        def req(method,suffix="",**kwargs):
            with worker.exclusive_live_worker(root):
                return signed_request(client,host,key,method,base+suffix,actor=EVALUATOR,**kwargs)
        assert client.post(base,json=correction_body(flow,child)).status_code==401
        assert signed_request(client,host,key,"POST",base,actor=ACTOR,json=correction_body(flow,child)).status_code==404
        response=req("POST",json=correction_body(flow,child))
        assert response.status_code==202,response.text
        edits=[]
        assert run_image_correction_once(flow,transport=wire_transport(flow,child,edits))=="IMAGE_CORRECTION_REVIEW_REQUIRED"
        reviewed=req("GET").json()["corrections"][0]
        decision={"expected_revision":reviewed["revision"],"expected_preview_sha":reviewed["preview_sha"],"approve":True,
            "visual_review":{"product_matches":True,"label_matches":True,"cta_policy_matches":True,"no_extra_text":True,
                             "observed_copy":reviewed["approved_copy"]}}
        response=req("POST","/"+reviewed["correction_id"]+"/decision",json=decision)
        assert response.status_code==200,response.text
        assert response.json()["state"]=="COMPLETED"
        for name,url in response.json()["artifacts"].items():
            assert signed_request(client,host,key,"GET",url,actor=EVALUATOR).status_code==200
            assert signed_request(client,host,key,"GET",url,actor=ACTOR).status_code==404
    assert {job:flow.state.get(EVALUATOR,job) for job in (parent,child)}==before
    assert len(calls)==2 and len(edits)==1 and len(attempts(flow))==8


@pytest.mark.parametrize("kind",["composed-copy-edits","image-corrections"])
def test_nonallowlisted_owner_gets423_and_unexpected_business_role_gets403(evaluator_owned,monkeypatch,kind):
    root,host,key,app,flow,parent,child,_=evaluator_owned
    job=parent if kind=="composed-copy-edits" else child
    body=copy_body(flow,parent) if kind=="composed-copy-edits" else correction_body(flow,child)
    base=f"/demo/api/live/jobs/{job}/{kind}"
    initial=attempts(flow)
    with TestClient(app,base_url=f"https://{host}") as client:
        with worker.exclusive_live_worker(root):
            flow.approved_actors=frozenset()
            response=signed_request(client,host,key,"POST",base,actor=EVALUATOR,json=body)
            assert response.status_code==423,response.text
            flow.approved_actors=frozenset({EVALUATOR})
            identity=app.state.demo_request_identity
            # The Signed middleware normally rejects unknown roles earlier. This
            # injected identity tests the route's independent role fail-closed.
            app.state.demo_request_identity=lambda request:(EVALUATOR,"observer")
            response=signed_request(client,host,key,"POST",base,actor=EVALUATOR,json=body)
            assert response.status_code==403,response.text
            app.state.demo_request_identity=identity
    assert attempts(flow)==initial


@pytest.mark.parametrize("kind,action",[("composed-copy-edits","copy-approval"),
    ("composed-copy-edits","decision"),("image-corrections","decision")])
def test_allowlist_withdrawal_blocks_every_revision_approval_write(evaluator_owned,kind,action):
    root,host,key,app,flow,parent,child,_=evaluator_owned
    job=parent if kind=="composed-copy-edits" else child
    url=f"/demo/api/live/jobs/{job}/{kind}/{'e'*32}/{action}"
    payload=({"expected_revision":0,"expected_copy_sha":"a"*64,"expected_review_sha":"b"*64,"acknowledge_evidence":True}
             if action=="copy-approval" else {"expected_revision":0,"expected_preview_sha":"c"*64,"approve":False})
    flow.approved_actors=frozenset()
    with TestClient(app,base_url=f"https://{host}") as client, worker.exclusive_live_worker(root):
        response=signed_request(client,host,key,"POST",url,actor=EVALUATOR,json=payload)
        assert response.status_code==423,response.text
