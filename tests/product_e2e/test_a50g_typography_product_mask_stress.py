"""A50G offline synthetic typography and product-mask quality review gates."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from PIL import Image

ROOT=Path(__file__).resolve().parents[2]
E=ROOT/"docs/integration/evidence/A50G_20261110"
OLD=ROOT/"docs/integration/evidence/A50E_20261110"
REPORT=json.loads((E/"A50G_SYNTHETIC_TYPOGRAPHY_MASK_STRESS_REPORT.json").read_text())


def digest(path:Path)->str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_a50g_product_policy_and_review_profile_gates_remain_separate():
    assert REPORT["contract"]=="IT_TEM_P03_A50G_SYNTHETIC_TYPOGRAPHY_PACKAGE_MASK_PRECHECK_V1"
    assert REPORT["product_policy"]=="PRODUCT_POLICY_APPROVED"
    assert REPORT["composed_4x5_design_profile"]=="DESIGN_PROFILE_V3_PENDING"
    assert REPORT["owner_pm_design_approved"] is False
    assert REPORT["licensing_signed"] is False
    assert REPORT["rights_cleared_real_product_count"]==0
    assert REPORT["actual_product_identity_mask"]=="NOT_AUDITED"
    assert REPORT["actual_platform_crop"]=="NOT_AUDITED"
    assert REPORT["360_390_human_visual"]=="NOT_AUDITED"
    assert REPORT["new_runtime_profile"]=="NOT_IMPLEMENTED"
    assert REPORT["d50_08_cta_9x16"]=="DECISION_PENDING_PM_OWNER"
    assert REPORT["a5_1"]==REPORT["gcp_qa"]==REPORT["paid_worker"]=="HOLD"
    assert REPORT["release"]=="NOT_RELEASE_READY"


@pytest.mark.parametrize("variant",(
    "A_REFLOW_EDITORIAL_CENTER","C_REFLOW_CONTRAST_ACTION"
))
def test_a50g_ink_boundaries_and_font_glyph_coverage(variant):
    e=REPORT["cases"][variant]
    original=json.loads((OLD/"A50E_REFLOW_DESIGN_MANIFEST.json").read_text())
    assert e["original_png_sha256"]==original["variants"][variant]["sha256"]
    assert e["cta_display_font_360"]>=16
    assert e["cta_native_to_safe_bottom"]/3>=12
    assert set(e["typography"])=={"headline","subline","cta"}
    for field,typ in e["typography"].items():
        assert typ["font_size_360"]>0
        assert typ["font_size_390"]>0
        assert typ["glyph_coverage"]["pass"] is True
        assert typ["glyph_coverage"]["missing_codepoints"]==[]
        assert typ["render_instructions"]==1
        region=typ["region"]
        x1,y1,x2,y2=typ["ink_bbox"]
        assert region[0]<=x1<x2<=region[2]
        assert region[1]<=y1<y2<=region[3]
        assert typ["text_sha256"]==original["variants"][variant]["copy"][field]["text_sha256"]
    assert e["typography"]["cta"]["font_size_360"]==20


@pytest.mark.parametrize("variant",(
    "A_REFLOW_EDITORIAL_CENTER","C_REFLOW_CONTRAST_ACTION"
))
def test_a50g_synthetic_product_mask_stress_marks_collision_as_hold(variant):
    scenarios=REPORT["cases"][variant]["synthetic_product_cases"]
    assert len(scenarios)==5
    for name in ("compact_bottle","two_short_products"):
        assert scenarios[name]["status"]=="SYNTHETIC_NO_COLLISION"
        assert scenarios[name]["brand_label_detected"] is False
        assert not scenarios[name]["reasons"]
    assert "MASK_INTERSECTS_CTA" in scenarios["tall_package_into_cta"]["reasons"]
    assert "OUTSIDE_SYNTHETIC_PRODUCT_TARGET" in scenarios["wide_package_beyond_target"]["reasons"]
    assert "MASK_INTERSECTS_HEADLINE" in scenarios["headline_overlap"]["reasons"]
    for name in ("tall_package_into_cta","wide_package_beyond_target",
                 "headline_overlap"):
        assert scenarios[name]["status"]=="GEOMETRIC_HOLD"
        assert scenarios[name]["brand_label_detected"] is False
        assert len(scenarios[name]["reasons"])>=1


@pytest.mark.parametrize("variant",(
    "A_REFLOW_EDITORIAL_CENTER","C_REFLOW_CONTRAST_ACTION"
))
@pytest.mark.parametrize("condition",("compact_bottle","tall_package_into_cta"))
def test_a50g_mask_overlay_is_proven_synthetic_png(variant,condition):
    scenario=REPORT["cases"][variant]["synthetic_product_cases"][condition]
    png=E/scenario["overlay_png"]
    assert digest(png)==scenario["overlay_sha256"]
    with Image.open(png) as img:
        assert img.size==(1080,1350)
        assert img.format=="PNG"
    assert scenario["model_data"] is False


def test_a50g_two_line_simulation_never_authorizes_product_cta():
    for name,details in REPORT["cases"].items():
        two=details["synthetic_two_line_cta_geometry_only"]
        assert two["line_count"]==2 and two["font_px"]>=48
        assert two["approved_for_image"] is False
        assert details["typography"]["cta"]["render_instructions"]==1


def test_a50g_instrumentation_does_not_include_font_file_or_real_product_data():
    assert REPORT["prior_a50e_manifest_sha256"]==digest(
        OLD/"A50E_REFLOW_DESIGN_MANIFEST.json")
    assert REPORT["font_file_sha256_read_only_not_bundled"]==(
        "3090ccde0442bb347aa7685d9ba8b17436a60682df6e8f92a9a670de14056e22")
    assert set(REPORT["cases"])=={
        "A_REFLOW_EDITORIAL_CENTER","C_REFLOW_CONTRAST_ACTION"}
    assert all(x.suffix not in (".ttf",".otf",".woff2",".sqlite",".db")
               for x in E.iterdir())


def test_a50g_independent_deterministic_rerender_and_output_no_clobber():
    with tempfile.TemporaryDirectory(prefix="ittem-A50G-nonbillable-") as temp:
        dest=Path(temp)/"render"
        cmd=[sys.executable,"-B",str(ROOT/"scripts/a50g_typography_product_mask_stress.py"),
             "--out",str(dest)]
        p=subprocess.run(cmd,cwd=ROOT,text=True,capture_output=True,timeout=30)
        assert p.returncode==0,p.stdout+p.stderr
        expected={x.name:digest(x) for x in E.iterdir() if x.is_file()
                  and x.name!="SHA256_MANIFEST.txt"}
        assert expected
        assert {x.name:digest(x) for x in dest.iterdir()}==expected
        second=subprocess.run(cmd,cwd=ROOT,text=True,capture_output=True,timeout=10)
        assert second.returncode!=0
        assert "A50G_OUTPUT_EXISTS_HOLD" in second.stdout+second.stderr
        assert {x.name:digest(x) for x in dest.iterdir()}==expected
