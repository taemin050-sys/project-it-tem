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


def enable_derived(dual_runtime,tmp_path,monkeypatch):
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


def test_signed_freeform_child_derives_from_parent_original_without_child_jobstore(
        dual_runtime,tmp_path,monkeypatch):
    root,host,key,app,flow,text=dual_runtime
    enable_derived(dual_runtime,tmp_path,monkeypatch)
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


@pytest.fixture
def rejected_source_runtime(dual_runtime,tmp_path,monkeypatch):
    """Disposable Signed Live bookkeeping; both Provider outputs are mocks."""
    root,host,key,app,flow,_=dual_runtime
    enable_derived(dual_runtime,tmp_path,monkeypatch)
    _,_,_,parent,group,calls=prepare_direct(dual_runtime,monkeypatch)
    child=group["child_job_id"]
    for _ in range(3):
        assert run_stage(root)=="LIVE_STAGE_COMMITTED"
    migrate_derived_schema(flow.state.filename)
    with TestClient(app,base_url=f"https://{host}") as client:
        def request(method,path,**kwargs):
            return signed_request(client,host,key,method,path,**kwargs)
        base=f"/demo/api/live/jobs/{child}/derived"
        response=request("GET",base)
        assert response.status_code==200,response.text
        snapshot=response.json()
        source=snapshot["source_assets"][0]
        width,height=source["width"],source["height"]
        mask=BytesIO();Image.new("L",(width,height),255).save(mask,"PNG")
        uploaded=request("POST",base+"/assets",data={"kind":"product_mask"},
            files={"file":("whole-fixture-mask.png",mask.getvalue(),"image/png")})
        assert uploaded.status_code==200,uploaded.text
        options={"source_asset_id":source["asset_id"],"mask_ref":uploaded.json(),
            "source_product_outline":[[0,0],[width-1,0],[width-1,height-1],[0,height-1]],
            "model_regions":[[450,340,640,600]],
            "copy_exclusions":[[50,40,1000,250],[280,1170,800,1280]],"acknowledge_regions":True}
        configured=request("POST",base+"/proposals",json=options)
        assert configured.status_code==200,configured.text
        proposal=configured.json()
        admission_body={"proposal_id":proposal["proposal_id"],"expected_recipe_sha":proposal["recipe_sha"],
            "expected_context_sha":snapshot["context_sha"],"expected_revision":snapshot["revision"],
            "acknowledge_source":True}
        admitted=request("POST",base+"/recipes/admit",json=admission_body)
        assert admitted.status_code==200,admitted.text
        grant=admitted.json()
        prepare_body={"admission_sha":grant["admission_sha"],"expected_recipe_sha":grant["recipe_sha"],
            "expected_context_sha":grant["context_sha"],"idempotency_key":"a"*64}
        pending=request("POST",base+"/renders",json=prepare_body)
        assert pending.status_code==202,pending.text
        yield {"request":request,"base":base,"flow":flow,"service":app.state.derived_service,
            "parent":parent,"child":child,"calls":calls,"row":pending.json(),
            "options":options,"admission_body":admission_body,"prepare_body":prepare_body}


def fixture_review_body(flow,child,row):
    # Synthetic fixture assertions never establish real label ground truth.
    checks={name:True for name in ("source_pixels_preserved","edges_acceptable","no_duplicate_product",
        "no_ghost_product","no_copy_occlusion","cta_policy_matches","mobile_readable",
        "label_ground_truth_confirmed")}
    checks["observed_copy"]=json.loads(flow.state.get(ACTOR,child)["copy_json"])["ad_copy"]
    return {"expected_revision":row["revision"],"expected_preview_sha":row["preview_sha"] or "0"*64,
        "expected_recipe_sha":row["recipe_sha"],"expected_context_sha":row["context_sha"],
        "approve":True,"visual_review":checks}


@pytest.mark.parametrize("phase",["queued","review_required","completed"])
def test_rejected_source_blocks_prior_hybrid_grants_reviews_and_cached_downloads(rejected_source_runtime,phase):
    value=rejected_source_runtime
    request,base,flow,service=(value[k] for k in ("request","base","flow","service"))
    parent,child,row=(value[k] for k in ("parent","child","row"))
    if phase!="queued":
        assert render_once(service,worker_id="before-source-rejection")["state"]=="REVIEW_REQUIRED"
        response=request("GET",base+"/renders/"+row["derived_id"])
        assert response.status_code==200,response.text
        row=response.json()
    if phase=="completed":
        approved=request("POST",base+"/renders/"+row["derived_id"]+"/decision",
            json=fixture_review_body(flow,child,row))
        assert approved.status_code==200,approved.text
        row=approved.json()
        finalized=request("POST",base+"/renders/"+row["derived_id"]+"/finalize",json={
            "expected_revision":row["revision"],"expected_approval_sha":row["approval_sha"],
            "expected_preview_sha":row["preview_sha"]})
        assert finalized.status_code==200,finalized.text
        row=finalized.json()
    before=flow.state.get(ACTOR,child)
    sibling=flow.state.get(ACTOR,parent)
    costs=attempts(flow)
    outputs=bytes_under(flow.root/"outputs")
    originals=bytes_under(flow.jobs.root)
    stored=service.store.get_render(ACTOR,child,row["derived_id"])
    protected_files=bytes_under(service.registry.root)
    dual=f"/demo/api/live/jobs/{parent}/dual"
    rejected=request("POST",dual+"/freeform/decision",json={"image_sha":before["image_sha"],"approve":False})
    assert rejected.status_code==200,rejected.text
    group=rejected.json()
    assert group["state"]=="PARTIAL"
    assert group["variants"]["freeform"]["state"]=="IMAGE_REJECTED"
    assert group["variants"]["freeform"]["artifacts"]=={}
    assert group["variants"]["composed"]["state"]=="IMAGE_REVIEW_REQUIRED"
    assert request("GET",group["variants"]["composed"]["artifacts"]["preview"]).status_code==200

    # Previously saved bodies and URLs cannot revive a derivative of a
    # rejected source, even if it was fully approved and finalized earlier.
    render_path=base+"/renders/"+row["derived_id"]
    operations=[("GET",base,None),("GET",render_path,None),
        ("POST",base+"/proposals",value["options"]),
        ("POST",base+"/recipes/admit",value["admission_body"]),
        ("POST",base+"/renders",value["prepare_body"]),
        ("POST",render_path+"/decision",fixture_review_body(flow,child,row)),
        ("POST",render_path+"/finalize",{"expected_revision":row["revision"],
            "expected_approval_sha":row["approval_sha"] or "0"*64,
            "expected_preview_sha":row["preview_sha"] or "0"*64}),
        ("POST",base+"/selection",{"derived_id":row["derived_id"],
            "expected_final_sha":row["final_sha"] or "0"*64,
            "expected_approval_sha":row["approval_sha"] or "0"*64})]
    operations.extend(("GET",url,None) for url in row["artifacts"].values())
    operations.append(("GET",dual+"/freeform/artifacts/candidate?sha256="+before["image_sha"],None))
    for method,path,body in operations:
        response=request(method,path,**({"json":body} if body is not None else {}))
        assert response.status_code==409,(method,path,response.text)
        expected="LIVE_DUAL_ARTIFACT_NOT_AVAILABLE" if path.startswith(dual) else "DERIVED_SOURCE_IMAGE_REJECTED"
        assert response.json()["detail"]==expected
    assert request("GET",base,actor=OTHER_ACTOR).status_code==404
    if phase=="queued":
        held=render_once(service,worker_id="rejected-source-worker")
        assert held["state"]=="HOLD" and held["error_code"]=="DERIVED_SOURCE_IMAGE_REJECTED"
    else:
        assert service.store.get_render(ACTOR,child,row["derived_id"])==stored
    assert bytes_under(service.registry.root)==protected_files
    after=flow.state.get(ACTOR,child)
    assert after=={**before,"state":"IMAGE_REJECTED","image_approval_sha":None}
    flow.state._approved(after)  # Copy/F09 authority itself is still valid.
    assert flow.state.get(ACTOR,parent)==sibling
    assert attempts(flow)==costs and len(value["calls"])==2
    assert bytes_under(flow.root/"outputs")==outputs
    assert bytes_under(flow.jobs.root)==originals


def test_source_rejected_after_worker_files_publish_never_becomes_reviewable(rejected_source_runtime):
    value=rejected_source_runtime
    flow,service,child=(value[k] for k in ("flow","service","child"))
    before=flow.state.get(ACTOR,child)
    costs=attempts(flow)
    def reject_after_publish(phase,row):
        assert phase=="files_published"
        flow.state.reject_image(ACTOR,child,before["image_sha"])
    held=render_once(service,worker_id="source-rejection-race",phase_hook=reject_after_publish)
    assert held["state"]=="HOLD" and held["error_code"]=="DERIVED_SOURCE_IMAGE_REJECTED"
    stored=service.store.get_render(ACTOR,child,value["row"]["derived_id"])
    assert stored["approval_sha"] is None and stored["final_sha"] is None
    response=value["request"]("GET",value["base"]+"/renders/"+stored["derived_id"])
    assert response.status_code==409 and response.json()["detail"]=="DERIVED_SOURCE_IMAGE_REJECTED"
    assert attempts(flow)==costs and len(value["calls"])==2
