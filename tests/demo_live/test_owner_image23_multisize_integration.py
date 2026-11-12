"""Image Owner #23 size-only Serving E2E, no paid model or external API.

Historical A v1 Layout SHA and its immutable stored Jobs remain unchanged.
New FE explicitly sends image_size, with native/final sizes decided in Image.
"""
from __future__ import annotations

import hashlib
import json
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from demo_staging.live.contracts import LiveGateError
from demo_staging.live.template_contract import A_V1_LAYOUT_SHA
from src.image_generation.backend_adapter import BackendGeneratedImage
from src.image_generation.size_selection import resolve_size_choice
from tests.demo_live.test_pipeline import FakeOwner, FONT, png, prepare_service
from tests.demo_live.test_live_contracts import sample_input
from tests.demo_live.test_http_gateway import login, photo, setup

SIZES=[
    ("3:4","OWNER_IMAGE_SIZE_3_4",(1152,1536),(1080,1440),"feed"),
    ("4:5","OWNER_IMAGE_SIZE_4_5",(1152,1440),(1080,1350),"feed"),
    ("9:16","OWNER_IMAGE_SIZE_9_16",(1152,2048),(1080,1920),"reels"),
]


@pytest.mark.parametrize("ratio,policy,native,final,placement",SIZES)
def test_new_owner_size_job_end_to_end_offline(tmp_path,ratio,policy,native,final,placement):
    flow,jid=prepare_service(tmp_path)
    payload={**sample_input(),"image_size":ratio}
    created=flow.prepare("alice",jid,payload,template_profile="A")
    stored=json.loads(created["input_json"])
    assert stored["image_size"]==ratio
    descriptor=flow.state.template("alice",jid)
    assert descriptor["profile_id"]==policy
    assert descriptor["safe_zone"]["final_size"]==list(final)
    assert descriptor["safe_zone"]["native_size"]==list(native)
    assert descriptor["safe_zone"]["layout_selection"]=={
        "version":"instagram-copy-hierarchy-v2","aspect_ratio":ratio,"placement":placement}
    assert tuple(descriptor["layout"]["canvas_size"])==final
    assert descriptor["layout_sha"]!=A_V1_LAYOUT_SHA
    owner=FakeOwner()
    review=flow.text("alice",jid,owner,offline=True)
    approval=flow.state.approve_copy("alice",jid,review["generation"],review["review_sha"])
    assert approval["approval_sha"]
    flow.prompt("alice",jid,owner,offline=True)
    image_request=flow.image_input("alice",jid)
    assert image_request.layout_selection is not None
    assert image_request.layout_selection.aspect_ratio==ratio
    assert image_request.layout_selection.placement==placement
    assert image_request.safe_zone is None
    assert image_request.copy_hash==review["copy_sha"]
    candidate_bytes=png((214,224,234),size=native)
    candidate=BackendGeneratedImage(
        image_bytes=candidate_bytes,mime_type="image/png",
        width=native[0],height=native[1],
        sha256=hashlib.sha256(candidate_bytes).hexdigest(),
        job_id=jid,copy_revision=review["generation"],copy_hash=review["copy_sha"],
        mock=True,receipt={"mode":"OFFLINE_FIXTURE","provider_calls":0})
    state=flow.accept_image_result("alice",jid,candidate,offline=True)
    assert state["state"]=="IMAGE_REVIEW_REQUIRED"
    flow.state.approve_image("alice",jid,candidate.sha256)
    finished=flow.compose("alice",jid,font_path=FONT)
    assert finished["state"]=="COMPLETED"
    target=flow.root/"outputs"/jid
    with Image.open(target/"final.png") as image:
        assert image.size==final and image.format=="PNG"
    assert hashlib.sha256((target/"final.png").read_bytes()).hexdigest()==finished["final_sha"]
    assert hashlib.sha256((target/"caption.txt").read_bytes()).hexdigest()==finished["caption_sha"]
    manifest=flow.state.read_manifest("alice",jid)
    assert manifest["envelope"]["profile_id"]==policy
    assert manifest["envelope"]["image_sha"]==candidate.sha256
    assert manifest["receipt"]["provider_calls"]==0
    assert manifest["receipt"]["needs_manual_check"] is True
    assert manifest["receipt"]["cta_placement"]==("image" if ratio=="3:4" else "platform")
    assert flow.validate_final_artifacts("alice",jid)==finished
    assert owner.calls==["analyze","research","copy","prompt"]
    with flow.state.db() as c:
        events=[row[0] for row in c.execute(
            "SELECT event FROM live_events WHERE job_id=? ORDER BY id",(jid,))]
    assert events.count("template_owner_size_ingress_v2")==1
    assert events.count("real_image_approved")==1
    assert events.count("composed")==1
    with pytest.raises(LiveGateError,match="FINAL_REQUIRES_IMAGE_APPROVAL"):
        flow.compose("alice",jid,font_path=FONT)


@pytest.mark.parametrize("ratio,policy,native,final,placement",SIZES)
def test_mismatched_native_bytes_fail_closed_without_image_approval(tmp_path,ratio,policy,native,final,placement):
    flow,jid=prepare_service(tmp_path)
    flow.prepare("alice",jid,{**sample_input(),"image_size":ratio},template_profile="A")
    owner=FakeOwner()
    review=flow.text("alice",jid,owner,offline=True)
    flow.state.approve_copy("alice",jid,review["generation"],review["review_sha"])
    flow.prompt("alice",jid,owner,offline=True)
    wrong=(1152,2048) if ratio!="9:16" else (1152,1440)
    b=png((200,200,200),size=wrong)
    candidate=BackendGeneratedImage(image_bytes=b,mime_type="image/png",
        width=wrong[0],height=wrong[1],sha256=hashlib.sha256(b).hexdigest(),
        job_id=jid,copy_revision=review["generation"],copy_hash=review["copy_sha"],
        mock=True,receipt={"mode":"OFFLINE_FIXTURE","provider_calls":0})
    with pytest.raises(LiveGateError,match="OWNER_IMAGE_SIZE_INVALID"):
        flow.accept_image_result("alice",jid,candidate,offline=True)
    assert flow.state.get("alice",jid)["state"]=="PROMPT_READY"
    assert not flow.image_path(jid).exists()


def test_size_is_immutable_and_wrong_values_cannot_enter_job(tmp_path):
    flow,jid=prepare_service(tmp_path)
    data={**sample_input(),"image_size":"3:4"}
    baseline=flow.prepare("alice",jid,data,template_profile="A")
    reentered=flow.prepare("alice",jid,data,template_profile="A")
    assert reentered["input_sha"]==baseline["input_sha"]
    with pytest.raises(LiveGateError,match="LIVE_INPUT_CONFLICT"):
        flow.prepare("alice",jid,{**data,"image_size":"9:16"},template_profile="A")
    bad={**data,"image_size":"story-9:16"}
    with pytest.raises(LiveGateError,match="PRODUCT_INPUT_INVALID"):
        flow.prepare("alice",jid,bad,template_profile="A")
    with pytest.raises(LiveGateError,match="LIVE_JOB_NOT_FOUND"):
        flow.state.template("bob",jid)


@pytest.mark.parametrize("ratio,policy,native,final,placement",SIZES)
def test_existing_http_job_qa_size_and_download_sha(tmp_path,monkeypatch,ratio,policy,native,final,placement):
    monkeypatch.setenv("IT_TEM_QA_FIXTURE_ENABLED","YES")
    monkeypatch.setenv("IT_TEM_LIVE_ENABLED","NO")
    monkeypatch.setenv("IT_TEM_LIVE_EXECUTION_APPROVED","NO")
    monkeypatch.setenv("IT_TEM_DEMO_SECURE_COOKIE","NO")
    monkeypatch.setenv("IT_TEM_QA_ALLOWED_ACTORS","alice,bob")
    monkeypatch.setenv("IT_TEM_LIVE_KOREAN_FONT",str(FONT))
    monkeypatch.delenv("OPENAI_API_KEY",raising=False)
    app,codes=setup(tmp_path)
    with TestClient(app,client=("127.0.0.1",12021)) as alice, \
         TestClient(app,client=("127.0.0.1",12022)) as bob:
        login(alice,codes["alice"])
        login(bob,codes["bob"])
        created=alice.post("/api/v1/jobs",files=[
            ("product_images",("p1.png",photo((120,130,140)),"image/png")),
            ("product_images",("p2.png",photo((150,160,170)),"image/png"))
        ],headers={"Origin":"http://testserver"})
        assert created.status_code==201,created.text
        jid=created.json()["job_id"]
        base=f"/demo/api/live/jobs/{jid}"
        qa=f"/demo/api/qa/jobs/{jid}"
        payload={**sample_input(),"image_size":ratio}
        r=alice.post(base+"/input",json=payload,headers={"Origin":"http://testserver"})
        assert r.status_code==200,r.text
        assert r.json()["template_profile"]==policy
        assert r.json()["image_size"]==ratio
        assert r.json()["output_size"]=={"width":final[0],"height":final[1]}
        assert bob.get(base).status_code==404
        txt=alice.post(qa+"/text",headers={"Origin":"http://testserver"})
        assert txt.status_code==200,txt.text
        review=txt.json()
        approved=alice.post(base+"/approve-copy",headers={"Origin":"http://testserver"},
             json={"expected_generation":review["generation"],
                   "expected_review_sha":review["review_sha"],"acknowledge_evidence":True})
        assert approved.status_code==200,approved.text
        prompted=alice.post(qa+"/prompt-image",headers={"Origin":"http://testserver"})
        assert prompted.status_code==200,prompted.text
        img=alice.get(qa+"/artifacts/candidate")
        assert img.status_code==200
        with Image.open(BytesIO(img.content)) as pixels:
            assert pixels.size==native
        sha=hashlib.sha256(img.content).hexdigest()
        approved_image=alice.post(base+"/approve-image",
             json={"image_sha":sha},headers={"Origin":"http://testserver"})
        assert approved_image.status_code==200,approved_image.text
        composed=alice.post(qa+"/compose",json={},
             headers={"Origin":"http://testserver"})
        assert composed.status_code==200,composed.text
        assert composed.json()["output_size"]=={"width":final[0],"height":final[1]}
        artifact=alice.get(qa+"/artifacts/final")
        assert artifact.status_code==200
        assert hashlib.sha256(artifact.content).hexdigest()==composed.json()["final_sha"]
        with Image.open(BytesIO(artifact.content)) as pixels:
            assert pixels.size==final and pixels.format=="PNG"
        cap=alice.get(qa+"/artifacts/caption")
        assert cap.status_code==200
        assert hashlib.sha256(cap.content).hexdigest()==composed.json()["caption_sha"]
        assert bob.get(qa+"/artifacts/final").status_code==404
        for path,table in (("queue.sqlite","queued_ops"),("cost.sqlite","attempts")):
            with __import__("sqlite3").connect(tmp_path/"runtime"/"live"/path) as db:
                assert db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]==0
