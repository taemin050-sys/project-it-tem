"""BP18 B-only provisional 4:5 visual design E2E, NEVER owner/PM accepted.
No paid provider requests; frozen per-Job policy and prior v2 both survive.
"""
import hashlib,json
from io import BytesIO

import pytest
from PIL import Image

from demo_staging.live.contracts import LiveGateError
from demo_staging.live.template_contract import (
    owner_size_policy,bp18_provisional_4x5_policy,
    BP18_PREFIX,BP18_VERSION,SIZE_VERSION,verify_policy,
)
from src.image_generation.size_selection import resolve_size_choice
from src.image_generation.backend_adapter import BackendGeneratedImage
from tests.demo_live.test_live_contracts import sample_input
from tests.demo_live.test_pipeline import FakeOwner,prepare_service,png,FONT


def test_bp18_4x5_head_sub_hierarchy_cta_and_provenance(monkeypatch):
    monkeypatch.setenv("IT_TEM_BP18_VISUAL_V3_ENABLED","YES")
    profile=owner_size_policy("4:5")
    assert profile["profile_id"]==BP18_PREFIX+"4_5"
    assert profile["profile_version"]==BP18_VERSION
    assert profile["safe_zone"]["human_visual_acceptance"]=="PENDING"
    layout=profile["layout"]
    head=layout["text_regions"]["headline"]
    sub=layout["text_regions"]["subline"]
    assert head["min_font_size"]>sub["max_font_size"]
    assert layout["cta_placement"]=="image"
    assert layout["text_regions"]["cta"]["background"]=="#593932"
    assert layout["canvas_size"]==[1080,1350]
    for choice in ("3:4","9:16"):
        assert owner_size_policy(choice)["profile_version"]==SIZE_VERSION


def make_job(tmp_path,monkeypatch,mode="composed"):
    monkeypatch.setenv("IT_TEM_BP18_VISUAL_V3_ENABLED","YES")
    flow,jid=prepare_service(tmp_path)
    flow.prepare("alice",jid,{**sample_input(),
        "image_size":"4:5","generation_mode":mode},template_profile="A")
    owner=FakeOwner()
    text=flow.text("alice",jid,owner,offline=True)
    policy=flow.state.template("alice",jid)
    assert policy["profile_id"]==BP18_PREFIX+"4_5"
    assert policy["profile_version"]==BP18_VERSION
    flow.state.approve_copy("alice",jid,text["generation"],text["review_sha"])
    flow.prompt("alice",jid,owner,offline=True)
    req=flow.image_input("alice",jid)
    assert req.layout_selection.aspect_ratio=="4:5"
    if mode=="freeform":
        assert req.safe_zone is None and req.copy_output==json.loads(text["copy_json"])
    else:
        assert req.generation_mode is None
    image=png((188,198,210),size=resolve_size_choice("4:5")[1].native)
    receipt={"mode":"OFFLINE_FIXTURE","provider_calls":0}
    if mode=="freeform":
        receipt.update({"state":"succeeded","generation_mode":"freeform",
                        "rendering":"QA_FIXTURE_NO_ACTUAL_MODEL_TEXT"})
    candidate=BackendGeneratedImage(image_bytes=image,mime_type="image/png",
       width=1152,height=1440,sha256=hashlib.sha256(image).hexdigest(),
       job_id=jid,copy_revision=req.copy_revision,copy_hash=req.copy_hash,
       mock=True,receipt=receipt)
    flow.accept_image_result("alice",jid,candidate,offline=True)
    flow.state.approve_image("alice",jid,candidate.sha256)
    completed=flow.compose("alice",jid,font_path=FONT if mode=="composed" else None)
    assert completed["state"]=="COMPLETED"
    assert flow.validate_final_artifacts("alice",jid)==completed
    return flow,jid,text


def test_bp18_composed_4x5_full_e2e_cta_rendered_sha_frozen(tmp_path,monkeypatch):
    flow,jid,copy=make_job(tmp_path,monkeypatch)
    manifest=flow.state.read_manifest("alice",jid)
    p=manifest["receipt"]["placements"]
    assert "headline" in p and "subline" in p and "cta" in p
    assert p["headline"]["font_size"]>p["subline"]["font_size"]
    assert p["subline"]["font_size"]>p["cta"]["font_size"]
    assert manifest["receipt"]["cta_placement"]=="image"
    assert manifest["receipt"]["provider_calls"]==0
    s=flow.state.get("alice",jid)
    assert s["copy_sha"]==copy["copy_sha"]
    with Image.open(BytesIO((flow.root/"outputs"/jid/"final.png").read_bytes())) as im:
        assert im.size==(1080,1350)
    assert hashlib.sha256((flow.root/"outputs"/jid/"caption.txt").read_bytes()).hexdigest()==s["caption_sha"]


def test_bp18_freeform_4x5_no_double_overlay(tmp_path,monkeypatch):
    flow,jid,copy=make_job(tmp_path,monkeypatch,mode="freeform")
    receipt=flow.state.read_manifest("alice",jid)["receipt"]
    assert receipt.get("generation_mode")=="freeform"
    assert receipt.get("font_sha256") is None
    assert receipt.get("placements") is None
    assert flow.state.get("alice",jid)["copy_sha"]==copy["copy_sha"]


def test_bp18_old_v2_snapshot_survives_new_enabled_flag(tmp_path,monkeypatch):
    monkeypatch.delenv("IT_TEM_BP18_VISUAL_V3_ENABLED",raising=False)
    flow,jid=prepare_service(tmp_path)
    flow.prepare("alice",jid,{**sample_input(),
         "image_size":"4:5","generation_mode":"composed"},template_profile="A")
    old=flow.state.template("alice",jid)
    assert old["profile_version"]==SIZE_VERSION
    old_layout_sha=old["layout_sha"]
    monkeypatch.setenv("IT_TEM_BP18_VISUAL_V3_ENABLED","YES")
    assert flow.state.template("alice",jid)["layout_sha"]==old_layout_sha
    assert owner_size_policy("4:5")["profile_version"]==BP18_VERSION

def test_bp18_v3_composed_provider_prompt_is_background_only_with_cta_zone(
    tmp_path,monkeypatch
):
    from uuid import uuid4
    from src.image_generation.backend_adapter import BackendImageAdapter
    from src.image_generation.korean_image_policy import render_korean_image_policy
    from src.image_generation.contracts import (
        ExternalImageRequest,AssetRef,BP18_V3_LAYOUT_VERSION
    )
    flow,jid=prepare_service(tmp_path)
    monkeypatch.setenv("IT_TEM_BP18_VISUAL_V3_ENABLED","YES")
    flow.prepare("alice",jid,{**sample_input(),"image_size":"4:5",
                 "generation_mode":"composed"},template_profile="A")
    owner=FakeOwner()
    t=flow.text("alice",jid,owner,offline=True)
    flow.state.approve_copy("alice",jid,t["generation"],t["review_sha"])
    flow.prompt("alice",jid,owner,offline=True)
    body=flow.image_input("alice",jid)
    assert body.layout_selection.version==BP18_V3_LAYOUT_VERSION
    prompt=BackendImageAdapter._build_prompt(body,"backend-v02-ko-v2")
    assert prompt.prompt_version=="backend-composed-ko-bp18-v3-provisional"
    asset=AssetRef(asset_id=uuid4(),sha256="a"*64,width=720,height=960,mime_type="image/png")
    external=ExternalImageRequest(operation="edit",layout_selection=body.layout_selection,
             width=1152,height=1440,product_images=[asset],prompt=prompt)
    rendered=render_korean_image_policy(external)
    assert "CTA(306,1195,774,1278)" in rendered
    assert "서버가 승인 원문" in rendered
    assert "CTA는 인스타그램 플랫폼 버튼" not in rendered
    assert "이미지 모델은 Head/Sub/CTA 문자를 직접 그리지 않는다" in rendered


def test_bp18_v3_freeform_prompts_exact_approved_cta_without_server_overlay(
    tmp_path,monkeypatch
):
    from uuid import uuid4
    from src.image_generation.backend_adapter import BackendImageAdapter
    from src.image_generation.korean_image_policy import render_korean_image_policy
    from src.image_generation.contracts import (
        ExternalImageRequest,AssetRef,BP18_V3_LAYOUT_VERSION
    )
    flow,jid=prepare_service(tmp_path)
    monkeypatch.setenv("IT_TEM_BP18_VISUAL_V3_ENABLED","YES")
    flow.prepare("alice",jid,{**sample_input(),"image_size":"4:5",
                "generation_mode":"freeform"},template_profile="A")
    owner=FakeOwner()
    t=flow.text("alice",jid,owner,offline=True)
    flow.state.approve_copy("alice",jid,t["generation"],t["review_sha"])
    flow.prompt("alice",jid,owner,offline=True)
    body=flow.image_input("alice",jid)
    assert body.layout_selection.version==BP18_V3_LAYOUT_VERSION
    assert body.safe_zone is None
    prompt=BackendImageAdapter._build_prompt(body,"backend-v02-ko-v2")
    assert prompt.prompt_version=="backend-freeform-ko-bp18-v3-provisional"
    ad=body.ad_copy.model_dump()
    assert ad["cta"] in prompt.positive
    asset=AssetRef(asset_id=uuid4(),sha256="b"*64,width=720,height=960,mime_type="image/png")
    external=ExternalImageRequest(operation="edit",layout_selection=body.layout_selection,
             width=1152,height=1440,product_images=[asset],prompt=prompt,text_rendering="freeform-v1")
    rendered=render_korean_image_policy(external)
    assert "승인된 Head/Sub/CTA 원문" in rendered
    assert "합성형 텍스트 박스" in rendered
    assert "CTA는 인스타그램 플랫폼 버튼" not in rendered
    assert "서버가 승인 원문" not in rendered


def test_bp18_v3_is_restricted_to_4_5_feed_and_old_v2_prompt_unchanged():
    from pydantic import ValidationError
    from src.image_generation.contracts import LayoutSelection,BP18_V3_LAYOUT_VERSION
    from src.image_generation.backend_adapter import BackendImageAdapter
    from tests.image_generation.test_backend_adapter import body as image_body
    for dims,placement in [("9:16","reels"),("3:4","feed")]:
        with pytest.raises(ValidationError):
            LayoutSelection(version=BP18_V3_LAYOUT_VERSION,
                            aspect_ratio=dims,placement=placement)
    old=image_body(layout_selection={"aspect_ratio":"4:5","placement":"feed"},
                   generation_mode="freeform",copy_output={
                       "plan":{"concept":"테스트"},"ad_copy":{"headline":"헤드","subline":"서브","cta":"CTA"},
                       "caption":"본문","hashtags":[]})
    # Older v2 owner behavior intentionally excludes platform CTA from direct
    # provider text; do not rewrite already bound historical image requests.
    old_prompt=BackendImageAdapter._build_prompt(old,"backend-v02-ko-v2")
    assert old_prompt.prompt_version=="backend-freeform-ko-v1"
