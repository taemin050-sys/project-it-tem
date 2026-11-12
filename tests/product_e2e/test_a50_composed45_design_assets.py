"""A5-0 mock artifact integrity only. Not a design approval or real product QA."""
import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image

ROOT=Path(__file__).resolve().parents[2]
E=ROOT/"docs/integration/evidence/A50_20261110"
SHA=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
M=json.loads((E/"A50_DESIGN_PROPOSALS_MANIFEST.json").read_text(encoding="utf-8"))

def test_a50_copy_and_baseline_exact_sha_and_not_approved():
    assert M["contract"]=="IT_TEM_P03_A5_0_DESIGN_PROPOSALS_NOT_OWNER_APPROVED_V1"
    assert M["owner_pm_approval"]=="DECISION_PENDING"
    assert M["runtime_profile_implementation"]=="NOT_PERFORMED"
    assert M["9x16_cta_policy"]=="DECISION_PENDING_PM_OWNER"
    assert M["copy"]=={
        "headline":"데일리 크림",
        "subline":"매일 촉촉한 사용감",
        "cta":"지금 만나보세요",
    }
    assert M["copy_sha256"]=={
      k:hashlib.sha256(v.encode("utf8")).hexdigest() for k,v in M["copy"].items()
    }
    assert SHA(E/"A41_ORIGINAL_WITHOUT_CTA.png")==M["actual_a41_png_sha256"]
    assert M["actual_a41_png_sha256"]==SHA(
        ROOT/"docs/integration/evidence/A41_20261109/ad_1080x1350.png")
    assert M["candidate_base_original_1152_sha256"]==SHA(
        E/"A41_RAW_SYNTHETIC_CANDIDATE_1152x1440.png")
    assert M["fixture_base_scaled_sha256"]==SHA(E/"fixture_base_1080x1350.png")
    assert M["four_up_comparison_sha256"]==SHA(E/"A50_OWNER_PM_4UP_COMPARISON.png")

def _intersects(a,b):
    return a[0]<b[2] and a[2]>b[0] and a[1]<b[3] and a[3]>b[1]

@pytest.mark.parametrize("name",(
 "A_EDITORIAL_CENTER","B_EDITORIAL_LEFT","C_CONTRAST_ACTION",
))
def test_a50_three_separate_full_size_proposals_in_safe_target(name):
    a=M["candidates"][name]
    f=E/a["png"]
    with Image.open(f) as im:
        assert im.format=="PNG" and im.size==(1080,1350)
    assert SHA(f)==a["sha256"]
    assert a["decision"]=="PENDING_IMAGE_OWNER_AND_PM"
    assert a["visual_quality"]=="NOT_HUMAN_ACCEPTED"
    assert a["cta_policy"]=="on_image_PROPOSAL_ONLY"
    assert a["CTA_one_instruction"] is True
    assert set(a["text"])=={"headline","subline","cta"}
    for field,actual in a["text"].items():
        assert actual["text"]==M["copy"][field]
        assert actual["text_sha256"]==M["copy_sha256"][field]
        assert not _intersects(actual["region"],a["protected_target_unverified"])
        x1,y1,x2,y2=actual["region"]
        assert 64<=x1<x2<=1016 and 64<=y1<y2<=1286
    assert a["text"]["cta"]["render_count"]==1
    assert a["text"]["cta"]["font_px"]>=44

@pytest.mark.parametrize("name",(
 "A_EDITORIAL_CENTER","B_EDITORIAL_LEFT","C_CONTRAST_ACTION",
))
@pytest.mark.parametrize("w", (360,390))
def test_a50_mobile_proposals_exact_pixels_and_sha(name,w):
    v=M["candidates"][name]["mobile"][str(w)]
    assert v["pixels"]==[w,round(1350*w/1080)]
    assert SHA(E/v["file"])==v["sha256"]
    with Image.open(E/v["file"]) as im:
        assert im.size==tuple(v["pixels"])
    assert v["cta_text_scaled_px"]>=14

def test_a50_synthetic_does_not_claim_product_photo_or_commercial_font():
    assert M["font_license"]=="MACOS_LOCAL_INTERNAL_DESIGN_ONLY_NOT_COMMERCIAL_CLEARANCE"
    assert M["product_region_status"]=="OWNER_LAYOUT_TARGET_ONLY_NOT_REAL_PRODUCT_SEGMENTATION"
    assert M["real_provider"]=="NOT_AUDITED"
    assert len(M["candidates"])==3
