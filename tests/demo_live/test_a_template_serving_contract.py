"""PR18 P0: pinned Owner A contract, legacy isolation, receipts and crash recovery.

Everything uses real Owner DTO/compositor, B0 JobStore, no provider HTTP or keys.
"""
import copy
import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from src.image_generation import make_a_template
from src.image_generation.backend_adapter import BackendGeneratedImage
from demo_staging.live.contracts import LiveGateError
from demo_staging.live.pipeline import LivePipeline
from demo_staging.live.store import LiveStore
from demo_staging.live.template_contract import A_ID,LEGACY_ID,digest,normalize_layout
from tests.demo_live.test_pipeline import prepare_service, FakeOwner,png,layout,FONT
from tests.demo_live.test_live_contracts import sample_input,assets

def staged(tmp_path,*,profile="A"):
    pipe,jid=prepare_service(tmp_path)
    pipe.prepare("alice",jid,sample_input(),template_profile=profile)
    fake=FakeOwner()
    text=pipe.text("alice",jid,fake,offline=True)
    pipe.state.approve_copy("alice",jid,text["generation"],text["review_sha"])
    pipe.prompt("alice",jid,fake,offline=True)
    request=pipe.image_input("alice",jid)
    image=png((220,230,230),size=(1152,1440))
    candidate=BackendGeneratedImage(image_bytes=image,mime_type="image/png",
        width=1152,height=1440,sha256=hashlib.sha256(image).hexdigest(),
        job_id=jid,copy_revision=text["generation"],copy_hash=text["copy_sha"],
        mock=True,receipt={"mock":True,"provider_calls":0})
    pipe.accept_image_result("alice",jid,candidate,offline=True)
    pipe.state.approve_image("alice",jid,candidate.sha256)
    return pipe,jid,request,fake

def final_files(pipe,jid):
    d=pipe.root/"outputs"/jid
    return [d/x for x in ("final.png","caption.txt","receipt.json")]

def test_new_a_safe_zone_pinned_at_creation_and_owner_binding(tmp_path):
    pipe,jid,req,owner=staged(tmp_path)
    zone,layout_owner=make_a_template()
    assert req.safe_zone==zone
    assert req.copy_revision==1
    assert req.image_prompt.concept
    profile=pipe.state.template("alice",jid)
    assert profile["profile_id"]==A_ID
    assert profile["safe_zone_sha"]==digest(zone.model_dump(mode="json"))
    assert profile["layout_sha"]==digest(layout_owner.model_dump(mode="json"))
    assert profile["layout"]["protected_regions"]==[]
    assert pipe.state.get("alice",jid)["state"]=="IMAGE_APPROVED"
    assert owner.calls==["analyze","research","copy","prompt"]
    # A installed before text: no mutation of input SHA and approval binding
    original=pipe.state.get("alice",jid)
    duplicate=pipe.prepare("alice",jid,sample_input(),template_profile="A")
    assert duplicate["input_sha"]==original["input_sha"]
    assert duplicate["approval_sha"]==original["approval_sha"]
    assert pipe.state.template("alice",jid)==profile

def test_a_rejects_foreign_layout_and_old_request_cannot_install_a(tmp_path):
    pipe,jid,req,_=staged(tmp_path)
    old=pipe.state.get("alice",jid)
    with pytest.raises(LiveGateError,match="COMPOSITION_LAYOUT_CONFLICT"):
        pipe.compose("alice",jid,layout=layout(),font_path=FONT)
    assert pipe.state.get("alice",jid)==old
    with pytest.raises(LiveGateError,match="A_TEMPLATE_REQUIRES_COMPOSITION_RECEIPT"):
        pipe.state.composed("alice",jid,"a"*64,"b"*64)
    # Freeze same policy: even exact Owner layout supplied is accepted
    a_layout=make_a_template()[1].model_dump(mode="json")
    chosen=pipe.state.plan_compose("alice",jid,a_layout,
        hashlib.sha256(FONT.read_bytes()).hexdigest())
    assert chosen["layout_sha"]==digest(a_layout)
    with pytest.raises(LiveGateError,match="COMPOSITION_LAYOUT_CONFLICT"):
        pipe.state.plan_compose("alice",jid,layout(),
            hashlib.sha256(FONT.read_bytes()).hexdigest())

def test_receipt_original_replay_integrity_manual_warning_and_completion(tmp_path,monkeypatch):
    pipe,jid,req,_=staged(tmp_path)
    import src.image_generation as owner_module
    real=owner_module.compose_ad_png
    captured=[]
    def instrument(body,*,font_path):
        result=real(body,font_path=font_path)
        captured.append(copy.deepcopy(result.receipt))
        return result
    monkeypatch.setattr(owner_module,"compose_ad_png",instrument)
    complete=pipe.compose("alice",jid,font_path=FONT)
    assert complete["state"]=="COMPLETED" and len(captured)==1
    assert complete["mode"]=="OFFLINE_FIXTURE"
    manifest=pipe.state.read_manifest("alice",jid)
    assert manifest["receipt"]==captured[0]
    assert manifest["envelope"]["image_sha"]==complete["image_sha"]
    assert manifest["envelope"]["image_approval_sha"]==complete["image_approval_sha"]
    assert manifest["envelope"]["profile_id"]==A_ID
    assert manifest["receipt"]["warnings"]==["PRODUCT_REGION_NOT_PROVIDED"]
    assert manifest["receipt"]["needs_manual_check"] is True
    assert manifest["receipt"]["protected_region_check"] is False
    assert manifest["receipt"]["provider_calls"]==0
    files=final_files(pipe,jid)
    assert all(x.is_file() for x in files)
    assert json.loads(files[2].read_text())==captured[0]
    assert pipe.validate_final_artifacts("alice",jid)==complete
    for p,sha in zip(files[:2],(complete["final_sha"],complete["caption_sha"])):
        assert hashlib.sha256(p.read_bytes()).hexdigest()==sha
    from PIL import Image
    with Image.open(files[0]) as image:
        assert image.format=="PNG" and image.size==(1080,1350)
    files[1].read_bytes().decode("utf-8")
    with pytest.raises(LiveGateError,match="FINAL_REQUIRES_IMAGE_APPROVAL"):
        pipe.compose("alice",jid,font_path=FONT)
    assert len(captured)==1
    assert pipe.validate_final_artifacts("alice",jid)==complete

@pytest.mark.parametrize("which",["final.png","caption.txt","receipt.json","db_receipt","db_envelope","policy_layout","approval"])
def test_completed_integrity_fails_closed_on_tampering(tmp_path,which):
    pipe,jid,_,_=staged(tmp_path)
    pipe.compose("alice",jid,font_path=FONT)
    if which.endswith(".txt") or which.endswith(".png") or which=="receipt.json":
        p=pipe.root/"outputs"/jid/which
        p.write_bytes(b"tampered")
    else:
        with pipe.state.db() as c:
            if which=="db_receipt":
                c.execute("UPDATE live_compose_manifests SET receipt_json='{}' WHERE job_id=?",(jid,))
            elif which=="db_envelope":
                c.execute("UPDATE live_compose_manifests SET envelope_json='{}' WHERE job_id=?",(jid,))
            elif which=="policy_layout":
                c.execute("UPDATE live_job_templates SET layout_sha=? WHERE job_id=?",("e"*64,jid))
            elif which=="approval":
                c.execute("UPDATE live_jobs SET approval_sha=? WHERE job_id=?",("f"*64,jid))
    with pytest.raises(LiveGateError,match="INTEGRITY|FAILED"):
        pipe.validate_final_artifacts("alice",jid)

@pytest.mark.parametrize("failure",["font_unavailable","file_commit","db_commit"])
def test_failure_preserves_approval_and_retries_same_input_without_provider(tmp_path,monkeypatch,failure):
    pipe,jid,req,owner=staged(tmp_path)
    fake_path=pipe.root/"missing-font.ttf"
    if failure=="font_unavailable":
        with pytest.raises(LiveGateError,match="COMPOSITION_FONT_UNAVAILABLE"):
            pipe.compose("alice",jid,font_path=fake_path)
    elif failure=="file_commit":
        from demo_staging.live import pipeline as module
        original=module.atomic_write
        calls=[0]
        def fault(path,data):
            calls[0]+=1
            if calls[0]==2:raise OSError("disk full (synthetic)")
            return original(path,data)
        monkeypatch.setattr(module,"atomic_write",fault)
        with pytest.raises(OSError,match="disk full"):
            pipe.compose("alice",jid,font_path=FONT)
        monkeypatch.setattr(module,"atomic_write",original)
    elif failure=="db_commit":
        original=pipe.state.commit_composition
        def fault(*args,**kwargs):raise sqlite3.OperationalError("disk db IO fault")
        monkeypatch.setattr(pipe.state,"commit_composition",fault)
        with pytest.raises(sqlite3.OperationalError):
            pipe.compose("alice",jid,font_path=FONT)
        monkeypatch.setattr(pipe.state,"commit_composition",original)
    job=pipe.state.get("alice",jid)
    assert job["state"]=="IMAGE_APPROVED"
    assert job["image_approval_sha"] and not job["final_sha"]
    done=pipe.compose("alice",jid,font_path=FONT)
    assert done["state"]=="COMPLETED"
    assert owner.calls==["analyze","research","copy","prompt"]
    assert pipe.validate_final_artifacts("alice",jid)
    with pipe.cost.connect() as c:
        assert c.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]==0

def test_frozen_font_protects_against_different_font_bytes_after_failed_layout(tmp_path,monkeypatch):
    pipe,jid,_,_=staged(tmp_path)
    from demo_staging.live import pipeline as mod
    original=mod.atomic_write
    def fail(path,data):raise OSError("injected")
    monkeypatch.setattr(mod,"atomic_write",fail)
    with pytest.raises(OSError):pipe.compose("alice",jid,font_path=FONT)
    monkeypatch.setattr(mod,"atomic_write",original)
    different=tmp_path/"not-a-real-font.ttf"
    different.write_bytes(b"DIFFERENT_FONT_BYTES")
    with pytest.raises(LiveGateError,match="COMPOSITION_FROZEN_INPUT_CONFLICT"):
        pipe.compose("alice",jid,font_path=different)
    assert pipe.state.get("alice",jid)["state"]=="IMAGE_APPROVED"
    assert pipe.compose("alice",jid,font_path=FONT)["state"]=="COMPLETED"

def test_concurrent_compose_only_one_final_state_transition(tmp_path):
    pipe,jid,_,_=staged(tmp_path)
    def run(_):
        try:return pipe.compose("alice",jid,font_path=FONT)["state"]
        except LiveGateError as e:return e.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(run,(1,2)))
    assert results.count("COMPLETED")==1
    assert len(results)==2 and any(x in ("FINAL_REQUIRES_IMAGE_APPROVAL","database is locked") for x in results if x!="COMPLETED")
    assert pipe.validate_final_artifacts("alice",jid)["state"]=="COMPLETED"
    with pipe.state.db() as c:
        assert c.execute("SELECT COUNT(*) FROM live_compose_manifests WHERE job_id=?",(jid,)).fetchone()[0]==1

def test_old_job_with_no_a_is_not_mutated_and_old_completed_readable(tmp_path):
    pipe,jid,req,_=staged(tmp_path,profile="LEGACY")
    assert req.safe_zone is None
    assert pipe.state.template("alice",jid) is None
    original=pipe.state.get("alice",jid)
    outcome=pipe.compose("alice",jid,layout=layout(),font_path=FONT)
    assert pipe.state.template("alice",jid)["profile_id"]==LEGACY_ID
    assert original["input_sha"]==outcome["input_sha"]
    assert original["image_approval_sha"]==outcome["image_approval_sha"]
    assert pipe.validate_final_artifacts("alice",jid)["state"]=="COMPLETED"
    # Old fully COMPOSED rows without manifest: existing final/caption GET is valid.
    with pipe.state.db() as c:
        c.execute("DELETE FROM live_compose_manifests WHERE job_id=?",(jid,))
        c.execute("DELETE FROM live_job_templates WHERE job_id=?",(jid,))
        # Reproduce a genuinely pre-policy historical completion; an old row
        # must have no durable compose-contract-frozen event.
        c.execute("DELETE FROM live_events WHERE job_id=? AND event='compose_contract_frozen_v1'",(jid,))
    assert pipe.state.template("alice",jid) is None
    assert pipe.state.read_manifest("alice",jid) is None
    assert pipe.validate_final_artifacts("alice",jid)["state"]=="COMPLETED"
    # A new create request for the same pre-policy Job cannot retrofit A.
    assert pipe.prepare("alice",jid,sample_input(),template_profile="A")["input_sha"]==original["input_sha"]
    assert pipe.state.template("alice",jid) is None

def test_legacy_partial_files_without_pinned_layout_requires_manual_recovery(tmp_path):
    pipe,jid,_,_=staged(tmp_path,profile="LEGACY")
    path=pipe.root/"outputs"/jid/"final.png"
    path.write_bytes(b"orphaned")
    with pytest.raises(LiveGateError,match="LEGACY_LAYOUT_MANUAL_RECONCILIATION_REQUIRED"):
        pipe.compose("alice",jid,layout=layout(),font_path=FONT)
    assert path.read_bytes()==b"orphaned"
    assert pipe.state.template("alice",jid) is None

def test_a_policy_corrupt_or_replay_different_safe_zone_fails_closed(tmp_path):
    pipe,jid,req,_=staged(tmp_path)
    assert req.safe_zone==make_a_template()[0]
    with pipe.state.db() as c:
        c.execute("UPDATE live_job_templates SET safe_zone_sha=? WHERE job_id=?",("0"*64,jid))
    with pytest.raises(LiveGateError,match="TEMPLATE_POLICY_INTEGRITY_FAILED"):
        pipe.state.template("alice",jid)
    with pytest.raises(LiveGateError,match="TEMPLATE_POLICY_INTEGRITY_FAILED"):
        pipe.compose("alice",jid,font_path=FONT)

def test_official_http_input_installs_a_at_first_ingress_preserving_b0_wire(tmp_path):
    from fastapi.testclient import TestClient
    from tests.demo_live.test_http_gateway import setup,login,photo
    app,codes=setup(tmp_path)
    assert len([p for p in app.openapi()["paths"] if p.startswith("/api/v1/jobs")])==10
    with TestClient(app) as user,TestClient(app) as other:
        login(user,codes["alice"]);login(other,codes["bob"])
        r=user.post("/api/v1/jobs",files=[
            ("product_images",("p1.png",photo((120,130,140)),"image/png")),
            ("product_images",("p2.png",photo((150,160,170)),"image/png"))],
            headers={"Origin":"http://testserver"})
        assert r.status_code==201
        jid=r.json()["job_id"]
        prefix=f"/demo/api/live/jobs/{jid}"
        assert other.get(prefix).status_code==404
        x=user.post(prefix+"/input",json=sample_input(),
                    headers={"Origin":"http://testserver"})
        assert x.status_code==200,x.text
        assert x.json()["template_profile"]==A_ID
        assert x.json()["product_protection_status"]=="NOT_REVIEWED"
        assert "safe_zone" not in x.json() and "receipt" not in x.json()
        y=user.post(prefix+"/input",json=sample_input(),
                    headers={"Origin":"http://testserver"})
        assert y.status_code==200 and y.json()["input_sha"]==x.json()["input_sha"]
        profile=app.state.live_pipeline.state.template("alice",jid)
        assert profile["layout_sha"]==digest(make_a_template()[1].model_dump(mode="json"))
        with app.state.live_pipeline.state.db() as c:
            assert c.execute("SELECT COUNT(*) FROM live_job_templates WHERE job_id=?",
                             (jid,)).fetchone()[0]==1
            assert c.execute("SELECT COUNT(*) FROM live_compose_manifests").fetchone()[0]==0
            assert c.execute("SELECT COUNT(*) FROM live_events WHERE job_id=? AND event='input_committed'",
                             (jid,)).fetchone()[0]==1
        assert other.get(prefix).status_code==404
        assert user.get(prefix).json()["template_profile"]==A_ID
        from demo_staging.live.http_api import ComposeRequest
        assert ComposeRequest.model_validate({}).layout is None

def test_legacy_http_repeat_does_not_inject_a(tmp_path):
    from fastapi.testclient import TestClient
    from tests.demo_live.test_http_gateway import setup,login,photo
    app,codes=setup(tmp_path)
    with TestClient(app) as user:
        login(user,codes["alice"])
        r=user.post("/api/v1/jobs",files=[
            ("product_images",("p1.png",photo((120,130,140)),"image/png")),
            ("product_images",("p2.png",photo((150,160,170)),"image/png"))],
            headers={"Origin":"http://testserver"})
        jid=r.json()["job_id"]
        original=app.state.live_pipeline.prepare("alice",jid,sample_input(),
                                                  template_profile="LEGACY")
        x=user.post(f"/demo/api/live/jobs/{jid}/input",json=sample_input(),
                    headers={"Origin":"http://testserver"})
        assert x.status_code==200 and x.json()["template_profile"]=="PRE_POLICY_LEGACY"
        assert app.state.live_pipeline.state.template("alice",jid) is None
        assert app.state.live_pipeline.state.get("alice",jid)["input_sha"]==original["input_sha"]

def test_live_serving_a_owner_binding_v3_and_asset_replay_no_provider(tmp_path,monkeypatch):
    from src.image_generation.assets import LocalAssetStore
    from src.image_generation.api_image_processor import ExternalImageProcessor
    from src.image_generation.backend_adapter import BackendImageAdapter
    from src.image_generation.openai_images import OpenAIImagesAdapter,OpenAIImagesConfig
    from src.image_generation.provider_attempts import ProviderAttemptStore
    from src.image_generation.errors import GatewayError
    import httpx

    pipe,jid=prepare_service(tmp_path)
    pipe.prepare("alice",jid,sample_input(),template_profile="A")
    fake=FakeOwner()
    text=pipe.text("alice",jid,fake,offline=True)
    pipe.state.approve_copy("alice",jid,text["generation"],text["review_sha"])
    pipe.prompt("alice",jid,fake,offline=True)
    body=pipe.image_input("alice",jid)
    calls=[]
    def deny(request):
        calls.append(request)
        pytest.fail("Owner binding must never reach a Provider")
    root=tmp_path/"owner_binding"
    offline_provider=OpenAIImagesAdapter(OpenAIImagesConfig(live_calls=False),
                                         transport=httpx.MockTransport(deny))
    processor=ExternalImageProcessor(LocalAssetStore(root/"assets"),offline_provider,
                      ProviderAttemptStore(root/"attempts.sqlite"),
                      budget_limit_usd="2",reservation_usd="1")
    adapter=BackendImageAdapter(processor,root/"bindings.sqlite")
    first=adapter._bind(body,pipe.project_id)
    assert first.prompt.prompt_version=="backend-v02-ko-v3"
    assert "카피 여백" in first.prompt.positive
    assert "강한 반사광" in first.prompt.positive
    assert len(first.product_images)==2
    with adapter._connect() as c:
        before=c.execute("SELECT input_hash,request_json,request_hash FROM backend_image_bindings").fetchone()
    def forbidden(*args,**kwargs):pytest.fail("Binding replay must not reupload or rebuild")
    monkeypatch.setattr(adapter.processor.assets,"put_upload",forbidden)
    monkeypatch.setattr(adapter,"_build_prompt",forbidden)
    assert adapter._bind(body,pipe.project_id)==first
    with adapter._connect() as c:
        after=c.execute("SELECT input_hash,request_json,request_hash FROM backend_image_bindings").fetchone()
    assert after==before
    assert calls==[]
    changed=body.model_copy(deep=True)
    changed=changed.model_copy(update={"product_images":list(reversed(body.product_images))})
    with pytest.raises(GatewayError) as error:
        adapter._bind(changed,pipe.project_id)
    assert error.value.code=="BACKEND_INPUT_CONFLICT"
    with adapter._connect() as c:
        assert c.execute("SELECT input_hash,request_json,request_hash FROM backend_image_bindings").fetchone()==before
    with pipe.cost.connect() as c:
        assert c.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]==0

def test_owner_render_failure_does_not_mark_complete_or_trigger_image_api(tmp_path,monkeypatch):
    pipe,jid,_,fake=staged(tmp_path)
    import src.image_generation as owner
    from src.image_generation.errors import GatewayError
    actual=owner.compose_ad_png
    def fail(*args,**kwargs):
        raise GatewayError("COMPOSITION_TEXT_OVERFLOW","synthetic test copy too long")
    monkeypatch.setattr(owner,"compose_ad_png",fail)
    with pytest.raises(LiveGateError,match="COMPOSITION_RENDER_FAILED"):
        pipe.compose("alice",jid,font_path=FONT)
    assert pipe.state.get("alice",jid)["state"]=="IMAGE_APPROVED"
    assert pipe.state.read_manifest("alice",jid) is None
    assert fake.calls==["analyze","research","copy","prompt"]
    monkeypatch.setattr(owner,"compose_ad_png",actual)
    assert pipe.compose("alice",jid,font_path=FONT)["state"]=="COMPLETED"

def test_pre_policy_image_approved_without_persisted_layout_is_manual_hold(tmp_path):
    pipe,jid,_,_=staged(tmp_path,profile="LEGACY")
    with pipe.state.db() as c:
        c.execute("DELETE FROM live_events WHERE job_id=? AND event='legacy_ingress_contract_v1'",(jid,))
    assert pipe.state.template("alice",jid) is None
    with pytest.raises(LiveGateError,match="LEGACY_LAYOUT_MANUAL_RECONCILIATION_REQUIRED"):
        pipe.compose("alice",jid,layout=layout(),font_path=FONT)
    assert pipe.state.get("alice",jid)["state"]=="IMAGE_APPROVED"
    assert pipe.state.template("alice",jid) is None

@pytest.mark.parametrize("profile",["A","LEGACY"])
def test_auditor_p0_deleted_manifest_must_not_downgrade_managed_complete(tmp_path,profile):
    pipe,jid,_,_=staged(tmp_path,profile=profile)
    pipe.compose("alice",jid,layout=layout() if profile=="LEGACY" else None,font_path=FONT)
    assert pipe.validate_final_artifacts("alice",jid)["state"]=="COMPLETED"
    with pipe.state.db() as c:
        c.execute("DELETE FROM live_compose_manifests WHERE job_id=?",(jid,))
    assert pipe.state.get("alice",jid)["state"]=="COMPLETED"
    assert pipe.state.template("alice",jid) is not None
    with pytest.raises(LiveGateError,match="COMPOSITION_MANIFEST_REQUIRED"):
        pipe.state.read_manifest("alice",jid)
    with pytest.raises(LiveGateError,match="COMPOSITION_MANIFEST_REQUIRED"):
        pipe.validate_final_artifacts("alice",jid)


@pytest.mark.parametrize("profile",["A","LEGACY"])
def test_auditor_policy_and_manifest_both_deleted_still_fail_closed(tmp_path,profile):
    pipe,jid,_,_=staged(tmp_path,profile=profile)
    pipe.compose("alice",jid,layout=layout() if profile=="LEGACY" else None,font_path=FONT)
    with pipe.state.db() as c:
        c.execute("DELETE FROM live_compose_manifests WHERE job_id=?",(jid,))
        c.execute("DELETE FROM live_job_templates WHERE job_id=?",(jid,))
    # Append-only policy/compose events survived metadata deletion.
    assert pipe.state.template("alice",jid) is None
    with pytest.raises(LiveGateError,match="COMPOSITION_MANIFEST_REQUIRED"):
        pipe.validate_final_artifacts("alice",jid)


@pytest.mark.parametrize("file",["receipt.json","final.png","caption.txt"])
def test_auditor_missing_artifact_file_fails_closed(tmp_path,file):
    pipe,jid,_,_=staged(tmp_path)
    pipe.compose("alice",jid,font_path=FONT)
    (pipe.root/"outputs"/jid/file).unlink()
    with pytest.raises(LiveGateError,match="INTEGRITY|FAILED"):
        pipe.validate_final_artifacts("alice",jid)


def test_auditor_true_pre_policy_completed_without_contract_still_replays(tmp_path):
    pipe,jid,_,_=staged(tmp_path,profile="LEGACY")
    # Truly legacy: state.composed was the old implementation path, with
    # final/Caption only, no template and no compose receipt manifest.
    from demo_staging.live.pipeline import atomic_write
    final=png((80,90,100),size=(1080,1350))
    caption="과거 완료 Job의 한국어 캡션\n#보습".encode("utf8")
    d=pipe.root/"outputs"/jid
    atomic_write(d/"final.png",final)
    atomic_write(d/"caption.txt",caption)
    pipe.state.composed("alice",jid,hashlib.sha256(final).hexdigest(),
                        hashlib.sha256(caption).hexdigest())
    assert pipe.state.template("alice",jid) is None
    assert pipe.state.read_manifest("alice",jid) is None
    assert pipe.validate_final_artifacts("alice",jid)["state"]=="COMPLETED"


def test_auditor_historical_a_v1_recovery_ignores_current_owner_factory(tmp_path,monkeypatch):
    from demo_staging.live import template_contract as tc
    pipe,jid,_,_=staged(tmp_path)
    pipe.compose("alice",jid,font_path=FONT)
    saved=pipe.state.template("alice",jid)
    def changed_owner():
        zone,ly=make_a_template()
        changed=zone.model_copy(update={"left":.07})
        return changed,ly
    monkeypatch.setattr(tc,"make_a_template",changed_owner)
    # Old frozen owner-a-v1 is valid even after a future Owner default changes.
    assert pipe.state.template("alice",jid)==saved
    assert pipe.validate_final_artifacts("alice",jid)["state"]=="COMPLETED"
    with pytest.raises(LiveGateError,match="A_TEMPLATE_VERSION_DRIFT"):
        pipe.state.create("alice","a"*32,sample_input(),assets(),template_profile="A")


def test_http_deleted_manifest_denies_get_download_share_and_shared_file(tmp_path):
    from fastapi.testclient import TestClient
    from tests.demo_live.test_http_gateway import setup,login,photo
    app,codes=setup(tmp_path)
    with TestClient(app) as user, TestClient(app) as peer:
        login(user,codes["alice"]);login(peer,codes["bob"])
        r=user.post("/api/v1/jobs",files=[
            ("product_images",("p1.png",photo((120,130,140)),"image/png")),
            ("product_images",("p2.png",photo((150,160,170)),"image/png"))],
            headers={"Origin":"http://testserver"})
        assert r.status_code==201
        jid=r.json()["job_id"]
        prefix=f"/demo/api/live/jobs/{jid}"
        response=user.post(prefix+"/input",json=sample_input(),
                           headers={"Origin":"http://testserver"})
        assert response.status_code==200
        pipe=app.state.live_pipeline
        fake=FakeOwner()
        text=pipe.text("alice",jid,fake,offline=True)
        pipe.state.approve_copy("alice",jid,text["generation"],text["review_sha"])
        pipe.prompt("alice",jid,fake,offline=True)
        data=png((220,230,235),size=(1152,1440))
        output=BackendGeneratedImage(image_bytes=data,mime_type="image/png",
            width=1152,height=1440,sha256=hashlib.sha256(data).hexdigest(),
            job_id=jid,copy_revision=text["generation"],copy_hash=text["copy_sha"],
            mock=True,receipt={"mode":"SYNTHETIC_FIXTURE","provider_calls":0})
        pipe.accept_image_result("alice",jid,output,offline=True)
        pipe.state.approve_image("alice",jid,output.sha256)
        pipe.compose("alice",jid,font_path=FONT)
        # Synthetic test-only mode bit permits checking HTTP Live sharing ACL.
        # There was no real Provider call and no real model billing.
        with pipe.state.db() as c:
            c.execute("UPDATE live_jobs SET mode='LIVE' WHERE job_id=?",(jid,))
        assert user.get(prefix).status_code==200
        assert user.get(prefix+"/artifacts/final").status_code==200
        assert user.get(prefix+"/artifacts/caption").status_code==200
        assert peer.get(prefix+"/artifacts/final").status_code==404
        shared=user.post(prefix+"/share",headers={"Origin":"http://testserver"})
        assert shared.status_code==200,shared.text
        board_before=peer.get("/demo/api/live/shared")
        assert board_before.status_code==200
        assert board_before.json()["jobs"][0]["integrity_status"]=="VERIFIED"
        url=f"/demo/api/live/shared/{jid}/artifacts/final"
        assert peer.get(url).status_code==200
        with pipe.state.db() as c:
            c.execute("DELETE FROM live_compose_manifests WHERE job_id=?",(jid,))
        board_after=peer.get("/demo/api/live/shared")
        assert board_after.status_code==200
        assert len(board_after.json()["jobs"])==1
        assert board_after.json()["jobs"][0]["integrity_status"]=="UNAVAILABLE"
        # Existing author publication record remains untouched.
        from demo_staging.live.reviews import LiveShares
        assert LiveShares(tmp_path/"runtime/live/shares.sqlite").item(jid)["final_sha"]==shared.json()["final_sha"]
        assert user.get(prefix).status_code==503
        assert user.get(prefix+"/artifacts/final").status_code==503
        assert user.get(prefix+"/artifacts/caption").status_code==503
        assert user.post(prefix+"/share",headers={"Origin":"http://testserver"}).status_code==503
        assert peer.get(url).status_code==503
        assert peer.get(f"/demo/api/live/shared/{jid}/artifacts/caption").status_code==503
        assert peer.get(f"/demo/api/live/shared/{jid}/evaluations").status_code==503
        assert peer.get(prefix).status_code==404
