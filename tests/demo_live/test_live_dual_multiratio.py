"""V2 multi-ratio integration over Signed SSO and real Owner MockTransport only."""
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from demo_staging.live import worker
from demo_staging.live.contracts import LiveGateError,digest
from demo_staging.live.dual_ratio_policy import CTA_POLICY_ID,CTA_POLICY_ENV,MULTI_RATIO_FLAG,image_cta_policy
from demo_staging.live.dual_worker import live_dual_lease,live_dual_profile,live_dual_worker_ready
from demo_staging.live.queue import LiveQueue,LIVE_DUAL_V2_PROTOCOL
from demo_staging.live.store import LiveStore
from src.image_generation.ad_resize import resize_ad_png
from tests.demo_live.test_live_dual_mock_transport import (
    dual_runtime,signed_env,signed_request,upload,attempts,mock_owner_adapter,ACTOR,sample_input,
)
from tests.demo_live.test_live_dual_protocol_guard import dual_environment


def register_cta(tmp_path,monkeypatch):
    value={"version":1,"policy_id":CTA_POLICY_ID,"aspect_ratio":"9:16",
           "composed_cta":"image","freeform_cta":"image","approved_by":"USER",
           "approval_reference":"OFFLINE_FIXTURE_ONLY_NOT_A_REAL_OWNER_DECISION"}
    path=tmp_path/"cta-decision.json"
    path.write_text(json.dumps(value));path.chmod(0o600)
    monkeypatch.setenv(CTA_POLICY_ENV,str(path))
    return path,value


@pytest.mark.parametrize("ratio,native,final,beta",[
    ("3:4",(1152,1536),(1080,1440),False),("9:16",(1152,2048),(1080,1920),False),
    ("3:4",(1152,1536),(1080,1440),True),("4:5",(1152,1440),(1080,1350),True),
    ("9:16",(1152,2048),(1080,1920),True)])
def test_v2_signed_request_two_independent_artifacts_and_downloads(
        dual_runtime,monkeypatch,tmp_path,ratio,native,final,beta):
    root,host,key,app,flow,text=dual_runtime
    monkeypatch.setenv(MULTI_RATIO_FLAG,"YES")
    if ratio=="9:16": register_cta(tmp_path,monkeypatch)
    if beta:
        package=Path(__file__).resolve().parents[2]/"app/node_modules/pretendard/dist"
        monkeypatch.setenv("IT_TEM_BP18_BETA_TYPOGRAPHY_ENABLED","YES")
        monkeypatch.setenv("IT_TEM_DERIVED_FONT",str(package/"public/variable/PretendardVariable.ttf"))
        monkeypatch.setenv("IT_TEM_DERIVED_FONT_LICENSE",str(package/"LICENSE.txt"))
        monkeypatch.setenv("IT_TEM_LIVE_KOREAN_FONT",str(package/"public/variable/PretendardVariable.ttf"))
    protocol="LIVE_DUAL_V1" if ratio=="4:5" else LIVE_DUAL_V2_PROTOCOL
    calls=[]
    from demo_staging.live.image_runtime_profile import effective_image_profile
    monkeypatch.setattr(worker,"live_image_adapter",lambda path,request:
        mock_owner_adapter(path,effective_image_profile(),calls,native_size=native))
    with TestClient(app,base_url=f"https://{host}") as client:
        job=upload(client,host,key);base=f"/demo/api/live/jobs/{job}";dual=base+"/dual"
        def req(method,url,**kwargs):return signed_request(client,host,key,method,url,**kwargs)
        capability=req("GET","/demo/api/live/capabilities").json()
        assert ratio in capability["supported_ratios"]
        assert capability["cta_policy_9x16"]==("IMAGE_CTA_BOTH" if ratio=="9:16" else None)
        with worker.exclusive_live_worker(root),live_dual_lease(root):
            assert live_dual_worker_ready(root,ratio)
            response=req("POST",dual+"/input",json={**sample_input(),"image_size":ratio,"generation_mode":"composed"})
            assert response.status_code==200,response.text
            queued=req("POST",base+"/queue-text")
            assert queued.status_code==202,queued.text
            assert app.state.live_queue.read(queued.json()["task_id"])["mode"]==protocol
            if ratio!="4:5":assert app.state.live_queue.claim("LIVE",include_dual=True) is None
        assert worker.run_once(root)=="LIVE_STAGE_COMMITTED"
        current=req("GET",base).json()
        with worker.exclusive_live_worker(root),live_dual_lease(root):
            response=req("POST",dual+"/start",json={"expected_generation":current["generation"],
                "expected_review_sha":current["review_sha"],"acknowledge_two_images":True})
            assert response.status_code==202,response.text
        for _ in range(3): assert worker.run_once(root)=="LIVE_STAGE_COMMITTED"
        assert worker.run_once(root)=="NO_LIVE_TASK"
        pending=req("GET",dual).json()
        assert pending["state"]=="REVIEW_REQUIRED" and pending["image_size"]==ratio
        ad_copy=json.loads(flow.state.get(ACTOR,job)["copy_json"])["ad_copy"]
        final_shas=[]
        for mode in ("composed","freeform"):
            variant=pending["variants"][mode]
            candidate=req("GET",variant["artifacts"]["candidate"])
            assert sha256(candidate.content).hexdigest()==variant["candidate_sha"]
            assert Image.open(BytesIO(candidate.content)).size==native
            checks={"product_matches":True,"label_matches":True,"cta_policy_matches":True}
            if mode=="freeform":checks.update(observed_copy=ad_copy,no_extra_text=True)
            if beta and mode=="composed":
                correct_font=Path(__file__).resolve().parents[2]/"app/node_modules/pretendard/dist/public/variable/PretendardVariable.ttf"
                wrong_font=tmp_path/"unapproved-font.ttf"
                wrong_font.write_bytes(b"not-the-approved-Pretendard-font")
                monkeypatch.setenv("IT_TEM_LIVE_KOREAN_FONT",str(wrong_font))
                denied=req("POST",dual+f"/{mode}/decision",json={"image_sha":variant["candidate_sha"],
                    "approve":True,"visual_review":checks})
                assert denied.status_code==422 and "BETA_TYPOGRAPHY_FONT_SHA_MISMATCH" in denied.text
                monkeypatch.setenv("IT_TEM_LIVE_KOREAN_FONT",str(correct_font))
            result=req("POST",dual+f"/{mode}/decision",json={"image_sha":variant["candidate_sha"],
                "approve":True,"visual_review":checks})
            assert result.status_code==200,result.text
            artifact=result.json()["variants"][mode]
            saved={}
            for name in ("final","caption","receipt"):
                download=req("GET",artifact["artifacts"][name]);assert download.status_code==200,download.text
                assert sha256(download.content).hexdigest()==artifact[f"{name}_sha"]
                saved[name]=download.content
            assert Image.open(BytesIO(saved["final"])).size==final
            if mode=="freeform":
                assert saved["final"]==resize_ad_png(candidate.content,final_size=final).image_bytes
            final_shas.append(artifact["final_sha"])
        assert len(set(final_shas))==2
        assert req("GET",dual).json()["state"]=="COMPLETED"
        assert len(calls)==2 and len(attempts(flow))==7
        assert any("CTA".encode() in prompt for prompt in calls)
        group=flow.state.live_dual_group(ACTOR,job)
        profile=group["execution_profile"]
        assert profile["protocol"]==protocol and profile["image_size"]==ratio
        if beta:
            template=flow.state.template(ACTOR,job)
            assert template["profile_id"].startswith("BP18_BETA_EDITORIAL_")
            assert template["safe_zone"]["required_font_sha"]==template["bound_font_sha"]
        if ratio=="9:16":
            assert profile["cta_policy_sha"]==digest(image_cta_policy())
            assert any("플랫폼 버튼으로 CTA를 대체하지 않는다".encode() in prompt for prompt in calls)


def test_v1_profile_byte_shape_and_distinct_v2_worker_capability(tmp_path,monkeypatch):
    dual_environment(monkeypatch)
    (tmp_path/"live").mkdir()
    assert set(live_dual_profile())=={"protocol","release_sha","policy_sha","text_model","image_profile","image_size"}
    with live_dual_lease(tmp_path):
        monkeypatch.setenv(MULTI_RATIO_FLAG,"YES")
        assert live_dual_worker_ready(tmp_path)
        assert not live_dual_worker_ready(tmp_path,"3:4")
    with live_dual_lease(tmp_path):
        assert live_dual_worker_ready(tmp_path,"3:4")
    assert not live_dual_worker_ready(tmp_path,"3:4")


def test_unknown_v2_blocks_all_claims_without_automatic_replay(tmp_path):
    queue=LiveQueue(tmp_path/"queue.sqlite")
    dual,_=queue.enqueue(actor="a",job_id="dual",stage="image",context_sha="a"*64,mode=LIVE_DUAL_V2_PROTOCOL)
    assert queue.claim("LIVE",include_dual=True) is None
    assert queue.claim("LIVE",include_dual=True,dual_protocols=(LIVE_DUAL_V2_PROTOCOL,))["id"]==dual["id"]
    queue.interrupt(dual["id"],"SENT_WITHOUT_RECEIPT")
    queue.enqueue(actor="a",job_id="other",stage="analysis",context_sha="b"*64)
    assert queue.dual_billing_unknown()
    assert queue.claim("LIVE") is None


def test_changed_9_16_decision_after_prompt_blocks_both_images_without_send(
        dual_runtime,tmp_path,monkeypatch):
    root,host,key,app,flow,text=dual_runtime
    monkeypatch.setenv(MULTI_RATIO_FLAG,"YES")
    path,value=register_cta(tmp_path,monkeypatch)
    calls=[]
    monkeypatch.setattr(worker,"live_image_adapter",lambda *args: calls.append(args))
    with TestClient(app,base_url=f"https://{host}") as client:
        job=upload(client,host,key)
    flow.prepare(ACTOR,job,{**sample_input(),"image_size":"9:16","generation_mode":"composed"},
                 template_profile="A",live_dual=True)
    review=flow.text(ACTOR,job,text_model=live_dual_profile("9:16")["text_model"])
    flow.state.start_live_dual(ACTOR,job,expected_generation=review["generation"],
        expected_review_sha=review["review_sha"],execution_profile=live_dual_profile("9:16"),
        acknowledge_two_images=True)
    assert worker.run_once(root)=="LIVE_STAGE_COMMITTED"
    path.write_text(json.dumps({**value,"approval_reference":"CHANGED_FIXTURE_DECISION"}))
    for _ in range(2):assert worker.run_once(root)=="LIVE_DUAL_STAGE_FAILED"
    assert calls==[] and len(attempts(flow))==5
    assert not app.state.live_queue.dual_billing_unknown()


def test_9_16_policy_requires_private_explicit_canonical_decision(tmp_path,monkeypatch):
    monkeypatch.delenv(CTA_POLICY_ENV,raising=False)
    with pytest.raises(LiveGateError,match="9_16_CTA_HOLD"):image_cta_policy()
    path,value=register_cta(tmp_path,monkeypatch)
    assert image_cta_policy()==value
    path.chmod(0o644)
    with pytest.raises(LiveGateError,match="9_16_CTA_HOLD"):image_cta_policy()
    path.chmod(0o600)
    path.write_text(json.dumps({**value,"freeform_cta":"platform"}))
    with pytest.raises(LiveGateError,match="9_16_CTA_HOLD"):image_cta_policy()
    path.write_text(json.dumps(value)[:-1]+',"version":1}')
    with pytest.raises(LiveGateError,match="9_16_CTA_HOLD"):image_cta_policy()


def test_live_store_open_existing_has_no_ddl_or_policy_activation(tmp_path,monkeypatch):
    monkeypatch.delenv("IT_TEM_BP18_F11_ENABLED",raising=False)
    database=tmp_path/"live.sqlite"
    with pytest.raises(LiveGateError,match="EXISTING_DATABASE"):LiveStore.open_existing(database)
    assert not database.exists()
    LiveStore(database)
    import gc
    gc.collect()  # Close constructor fixture's connection before changing journal mode.
    with sqlite3.connect(database) as c:
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        before_schema=c.execute("SELECT type,name,sql FROM sqlite_master ORDER BY name").fetchall()
        before_policy=c.execute("SELECT * FROM live_policy_activation").fetchall()
        c.execute("PRAGMA journal_mode=DELETE")
    before=database.read_bytes()
    existing=LiveStore.open_existing(database)
    with existing.db() as c:
        assert c.execute("PRAGMA journal_mode").fetchone()[0]=="delete"
        assert [tuple(r) for r in c.execute("SELECT type,name,sql FROM sqlite_master ORDER BY name")]==before_schema
        assert [tuple(r) for r in c.execute("SELECT * FROM live_policy_activation")]==before_policy
    assert database.read_bytes()==before
    database.unlink()
    with pytest.raises(sqlite3.OperationalError):existing.db()
    assert not database.exists()


def test_live_store_open_existing_refuses_partial_schema(tmp_path):
    database=tmp_path/"partial.sqlite"
    with sqlite3.connect(database) as c:c.execute("CREATE TABLE live_jobs(job_id TEXT)")
    before=database.read_bytes()
    with pytest.raises(LiveGateError,match="EXISTING_SCHEMA"):LiveStore.open_existing(database)
    assert database.read_bytes()==before
