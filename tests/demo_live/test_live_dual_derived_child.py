"""Real Live Dual topology, using only in-process Owner MockTransport.

The Freeform child has no original JobStore directory. Its protected derivative
must reuse the authenticated parent's uploads without cloning or rewriting any
original Job, Provider candidate, approval, or cost record. All scene checks in
this test are synthetic fixture assertions, never product-label ground truth.
"""
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path

from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image
import pytest

from demo_staging.live.contracts import LiveGateError
from demo_staging.live.derived_store import migrate_derived_schema
from demo_staging.live.derived_worker import run_once as render_once
from tests.demo_live.test_live_dual_mock_transport import (
    ACTOR,OTHER_ACTOR,dual_runtime,signed_env,signed_request,prepare_direct,run_stage,attempts,
)


def bytes_under(folder):
    return {path.relative_to(folder).as_posix():path.read_bytes()
            for path in folder.rglob("*") if path.is_file()}


def test_signed_freeform_child_derives_from_parent_original_without_child_jobstore(
        dual_runtime,tmp_path,monkeypatch):
    root,host,key,app,flow,text=dual_runtime
    authority=tmp_path/"derived-authority.json"
    authority.write_text(json.dumps({"schema":"bp18-derived-authority-v1","revision":1,
        "business_roles":{ACTOR:"owner",OTHER_ACTOR:"pm"},"delegations":[]}))
    authority.chmod(0o600)
    package=Path(__file__).resolve().parents[2]/"app/node_modules/pretendard/dist"
    for name,value in {"IT_TEM_DERIVED_ENABLED":"YES","IT_TEM_DERIVED_AUTHORITY_FILE":str(authority),
            "IT_TEM_DERIVED_ROOT":str(root/"protected"),
            "IT_TEM_DERIVED_FONT":str(package/"public/variable/PretendardVariable.ttf"),
            "IT_TEM_DERIVED_FONT_LICENSE":str(package/"LICENSE.txt"),
            "IT_TEM_DERIVED_SOURCE_TREE_SHA":"1"*40}.items():
        monkeypatch.setenv(name,value)
    for name in ("OPENAI_API_KEY","ANTHROPIC_API_KEY","GOOGLE_API_KEY","GEMINI_API_KEY","CREDENTIALS_DIRECTORY"):
        monkeypatch.delenv(name,raising=False)
    _,queue,_,parent,group,calls=prepare_direct(dual_runtime,monkeypatch)
    child=group["child_job_id"]
    for _ in range(3):assert run_stage(root)=="LIVE_STAGE_COMMITTED"
    assert len(calls)==2 and len(attempts(flow))==7
    assert not flow.jobs._job_dir(child).exists()
    with pytest.raises(HTTPException) as missing:
        flow.jobs.get_job(child)
    assert missing.value.status_code==404
    parent_uploads=flow.jobs.get_job(parent)["assets"]
    originals=bytes_under(flow.jobs.root)
    raw_states={job:flow.state.get(ACTOR,job) for job in (parent,child)}
    raw_outputs=bytes_under(flow.root/"outputs")
    costs=attempts(flow)
    migration=migrate_derived_schema(flow.state.filename)
    assert migration["changed"] and set(migration["added_tables"])=={
        "live_derived_recipe_admissions","live_derived_renders","live_derived_reviews"}

    with TestClient(app,base_url=f"https://{host}") as client:
        base=f"/demo/api/live/jobs/{child}/derived"
        def req(method,suffix="",**kwargs):
            return signed_request(client,host,key,method,base+suffix,**kwargs)
        assert client.get(base).status_code==401
        assert req("GET",actor=OTHER_ACTOR).status_code==404
        response=req("GET")
        assert response.status_code==200,response.text
        snapshot=response.json()
        assert snapshot["job_id"]==child and snapshot["can_admit"]
        assert {item["asset_id"] for item in snapshot["source_assets"]}=={
            item["asset_id"] for item in parent_uploads if item["role"]=="product"}
        source=snapshot["source_assets"][0]
        service=app.state.derived_service
        registered=service.registry.register_upload(ACTOR,child,source["asset_id"],expected_sha256=source["sha256"])
        assert registered.ref.sha256==source["sha256"]
        parent_path,_=flow.jobs.get_asset(parent,source["asset_id"])
        assert registered.data==parent_path.read_bytes()
        with pytest.raises(LiveGateError,match="NOT_FOUND"):
            service.registry.resolve_upload(OTHER_ACTOR,child,source["asset_id"])

        # These coordinates describe the synthetic flat-color fixture scene.
        # They are not a review of the real Anabiose packaging or generated ads.
        assert snapshot["proposals"][0]["hold_code"]=="PROTECTED_WHOLE_PRODUCT_REGISTRATION_REQUIRED"
        width,height=registered.image.upright_size
        mask=BytesIO();Image.new("L",(width,height),255).save(mask,"PNG")
        uploaded=req("POST","/assets",data={"kind":"product_mask"},
            files={"file":("whole-fixture-mask.png",mask.getvalue(),"image/png")})
        assert uploaded.status_code==200,uploaded.text
        configured=req("POST","/proposals",json={"source_asset_id":source["asset_id"],
            "mask_ref":uploaded.json(),
            "source_product_outline":[[0,0],[width-1,0],[width-1,height-1],[0,height-1]],
            "model_regions":[[450,340,640,600]],
            "copy_exclusions":[[50,40,1000,250],[280,1170,800,1280]],"acknowledge_regions":True})
        assert configured.status_code==200,configured.text
        proposal=configured.json()
        assert proposal["render_mode"]=="freeform_protected_product_hybrid"
        assert proposal["hold_code"] is None and proposal["requires_ground_truth"] is True
        body={"proposal_id":proposal["proposal_id"],"expected_recipe_sha":proposal["recipe_sha"],
            "expected_context_sha":snapshot["context_sha"],"expected_revision":snapshot["revision"],
            "acknowledge_source":True}
        assert req("POST","/recipes/admit",json=body,actor=OTHER_ACTOR).status_code==404
        admitted=req("POST","/recipes/admit",json=body)
        assert admitted.status_code==200,admitted.text
        grant=admitted.json()
        pending=req("POST","/renders",json={"admission_sha":grant["admission_sha"],
            "expected_recipe_sha":grant["recipe_sha"],"expected_context_sha":grant["context_sha"],
            "idempotency_key":"a"*64})
        assert pending.status_code==202,pending.text
        row=pending.json()
        rendered=render_once(service,worker_id="mock-live-dual-child-local-only")
        assert rendered["state"]=="REVIEW_REQUIRED",rendered
        current=req("GET","/renders/"+row["derived_id"])
        assert current.status_code==200,current.text
        result=current.json()
        assert result["approval_sha"] is None and result["final_sha"] is None
        preview=signed_request(client,host,key,"GET",result["artifacts"]["preview"])
        assert preview.status_code==200,preview.text
        assert sha256(preview.content).hexdigest()==result["preview_sha"]
        assert Image.open(BytesIO(preview.content)).size==(1080,1350)
        assert signed_request(client,host,key,"GET",result["artifacts"]["preview"],actor=OTHER_ACTOR).status_code==404
        stored=service.store.get_render(ACTOR,child,row["derived_id"])
        receipt=json.loads(service.registry.read_content(ACTOR,child,stored["artifacts"]["local_receipt"]).data)
        assert receipt["provider_calls"]==0 and receipt["literal_label_ground_truth"]=="PENDING"
        assert receipt["raw_provider_reference"]["job_id"]==child
        assert receipt["source_photo_sha"]==source["sha256"]
    assert flow.state.get(ACTOR,parent)==raw_states[parent]
    assert flow.state.get(ACTOR,child)==raw_states[child]
    assert attempts(flow)==costs
    assert bytes_under(flow.jobs.root)==originals
    assert bytes_under(flow.root/"outputs")==raw_outputs
    assert not flow.jobs._job_dir(child).exists()
    assert len(calls)==2
