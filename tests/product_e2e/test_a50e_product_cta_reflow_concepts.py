"""A5-0E visual proposal invariant tests; no real model / actual product masks."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from PIL import Image

ROOT=Path(__file__).resolve().parents[2]
E=ROOT/"docs/integration/evidence/A50E_20261110"
OLD=ROOT/"docs/integration/evidence/A50_20261110"
M=json.loads((E/"A50E_REFLOW_DESIGN_MANIFEST.json").read_text("utf-8"))
O=json.loads((OLD/"A50_DESIGN_PROPOSALS_MANIFEST.json").read_text("utf-8"))


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def lib():
    spec=importlib.util.spec_from_file_location(
        "a50e_designer",ROOT/"scripts/a50e_composed45_product_cta_reflow_concepts.py")
    assert spec and spec.loader
    m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_a50e_metadata_and_older_mocks_are_immutable():
    assert M["contract"]=="IT_TEM_P03_A50E_CTAPRODUCT_REFLOW_DESIGN_PROPOSAL_V1"
    assert M["source_prior_a50_manifest_sha256"]==sha(
        OLD/"A50_DESIGN_PROPOSALS_MANIFEST.json")
    assert M["old_a50_original_candidates_sha256"]=={
        k:v["sha256"] for k,v in O["candidates"].items()}
    assert M["unchanged_b_editorial_sha256"]==sha(OLD/"B_EDITORIAL_LEFT.png")
    assert M["source_background_sha256"]==sha(OLD/"fixture_base_1080x1350.png")
    assert M["owner_pm_approved"] is False
    assert M["a5_1_implementation_authorized"] is False
    assert M["gcp_qa_deployment"]==M["paid_worker"]=="HOLD"
    assert M["platform_safezone"]=="NOT_CERTIFIED"
    assert M["real_product_object_detection"]=="NOT_AUDITED"
    assert M["real_provider"]=="NOT_AUDITED"
    assert M["9x16_cta_policy"]=="DECISION_PENDING_PM_OWNER"


@pytest.mark.parametrize("name", (
    "A_REFLOW_EDITORIAL_CENTER","C_REFLOW_CONTRAST_ACTION",
))
def test_a50e_two_native_png_reflow_proposals_and_safe_insets(name,lib):
    c=M["variants"][name]
    with Image.open(E/c["png"]) as im:
        assert im.size==(1080,1350) and im.format=="PNG"
    assert c["pixels"]==[1080,1350]
    assert c["sha256"]==sha(E/c["png"])
    assert c["owner_pm_decision"]=="PENDING"
    assert c["commercial_font_approval"]=="HOLD"
    assert c["cta_safe_bottom_360"]>=12
    assert c["cta_safe_bottom_native"]>=36
    assert c["cta_to_fake_product_target_gap_native"]>=48
    assert c["cta_foreground_background_contrast"]>=4.5
    assert c["object_coverage"]=="SYNTHETIC_MASK_ONLY_NOT_REAL_BRAND_LABEL"
    assert lib.fully_inside(c["fake_object_mask"],c["fake_protected_target"])
    assert not lib.overlap(c["copy"]["cta"]["rect"],c["fake_protected_target"])
    assert set(c["copy"])=={"headline","subline","cta"}
    for field,record in c["copy"].items():
        assert record["text"]==lib.COPY[field]
        assert record["text_sha256"]==lib.sha_text(lib.COPY[field])
        assert record["render_instruction_count"]==1
        assert not lib.overlap(record["rect"],c["fake_object_mask"])
    assert c["copy"]["cta"]["font_px_on_360"]>=16


@pytest.mark.parametrize("name", (
    "A_REFLOW_EDITORIAL_CENTER","C_REFLOW_CONTRAST_ACTION",
))
@pytest.mark.parametrize("w", (360,390))
def test_a50e_cropped_mobile_preview_not_certified(name,w):
    variant=M["variants"][name]
    m=variant["mobile"][str(w)]
    f=E/m["png"]
    assert sha(f)==m["sha256"]
    with Image.open(f) as im:
        assert im.size==tuple(m["pixels"])
        assert im.format=="PNG"
    crop=E/m["crop_simulation_12px"]
    assert sha(crop)==m["crop_simulation_sha256"]
    with Image.open(crop) as im:
        assert im.size==(w,m["pixels"][1]-12)
    assert m["cta_bottom_remains_above_crop_px"]>=12
    assert variant["platform_crop"]=="SIMULATION_ONLY_NOT_PLATFORM_CERTIFIED"


def test_a50e_before_after_sha_and_stress_evidence():
    assert M["comparison_sha256"]==sha(E/M["comparison_png"])
    assert M["stress_sha256"]==sha(E/"A50E_SYNTHETIC_STRESS_RESULTS.json")
    stress=json.loads((E/"A50E_SYNTHETIC_STRESS_RESULTS.json").read_text())
    assert stress==M["stress_scenarios"]
    assert len(stress)==9
    for key in (
        "actual_object_mask_missing","large_packaging_into_cta",
        "cta_overlap_fake_mask","overlong_korean_headline",
        "long_cta_no_truncation","multiline_cta_unapproved",
        "three_line_cta_disallowed",
    ):
        assert stress[key]["status"]=="REJECTED_AS_EXPECTED"
    assert stress["two_line_cta_explicit_simulation"]["status"].startswith(
        "SYNTHETIC_LAYOUT_FEASIBLE")
    assert stress["small_package_synthetic_mask"]["status"].startswith(
        "SYNTHETIC_GEOMETRY_PASS")


def test_a50e_real_protected_mask_absent_is_fail_closed(lib):
    with pytest.raises(ValueError,match="REAL_PRODUCT_MASK_REQUIRED"):
        lib.verify_reflow_geometry(lib.NEW["A_REFLOW_EDITORIAL_CENTER"],None,
                                   require_real_mask=True)
    with pytest.raises(ValueError,match="PROTECTED_MASK_OUTSIDE_TARGET"):
        lib.verify_reflow_geometry(lib.NEW["C_REFLOW_CONTRAST_ACTION"],
                                   [(100,500,940,1270)])
    with pytest.raises(ValueError,match="CTA_MULTILINE_REQUIRES_PROFILE_APPROVAL"):
        lib.fit_text("지금 만나보세요\n한정 할인",
                     lib.NEW["A_REFLOW_EDITORIAL_CENTER"]["regions"]["cta"],
                     fontpath=lib.PRETENDARD,size=54,minimum=48,weight=700)


def test_a50e_deterministic_replay_without_touching_canonical_evidence():
    with tempfile.TemporaryDirectory(prefix="ittem-a50e-repeat-") as t:
        out=Path(t)/"generated"
        p=subprocess.run([sys.executable,"-B",
            str(ROOT/"scripts/a50e_composed45_product_cta_reflow_concepts.py"),
            "--out",str(out)],cwd=ROOT,text=True,
            stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=35)
        assert p.returncode==0,p.stdout
        ours={x.name:sha(x) for x in E.iterdir()
              if x.is_file() and x.name!="SHA256_MANIFEST.txt"}
        for n,h in ours.items():
            assert (out/n).is_file(),n
            assert sha(out/n)==h,n
        assert not any(x.suffix in (".ttf",".otf",".woff",".woff2",".db",".sqlite")
                       for x in out.iterdir())
        p2=subprocess.run([sys.executable,"-B",
            str(ROOT/"scripts/a50e_composed45_product_cta_reflow_concepts.py"),
            "--out",str(out)],cwd=ROOT,text=True,
            stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=10)
        assert p2.returncode!=0
        assert "A50E_EXISTING_OUTPUT_HOLD" in p2.stdout



def test_a50e_v2_owner_pm_zip_determinism_and_no_signed_authority():
    from zipfile import ZipFile
    original=ROOT/"docs/integration/handoffs/IT_TEM_P03_A50E_OWNER_PM_REFLOW_REVIEW_ONLY_V2_20261110.zip"
    assert sha(original)=="43dba59f205b0cb5fc9a73eb9085481bd059cd1b2c3b3e383a05b32b0ba1579b"
    with ZipFile(original) as z:
        assert z.testzip() is None
        names=z.namelist()
        assert len(names)==24
        assert not any(n.lower().endswith((".ttf",".otf",".woff",".woff2",".db",".sqlite",".env",".key"))
                       for n in names)
        policy=json.loads(z.read("BUNDLE_CONDITIONS.json"))
        assert policy["owner_signoff"]==policy["pm_signoff"]=="MISSING"
        assert policy["selected_profile"]=="NONE"
        assert policy["profile_v3_implementation"]=="NOT_AUTHORIZED"
        assert policy["9x16_cta"]=="DECISION_PENDING_PM_OWNER"
        assert policy["payload_files"]==22
        manifest=z.read("SHA256_CONTENT_MANIFEST.txt")
        assert hashlib.sha256(manifest).hexdigest()==policy["payload_manifest_sha256"]
        for line in manifest.decode().splitlines():
            h,member=line.split("  ",1)
            assert hashlib.sha256(z.read(member)).hexdigest()==h
    with tempfile.TemporaryDirectory(prefix="ittem-a50e-zip-v2-repeat-") as t:
        output=Path(t)/"packet.zip"
        r=subprocess.run([sys.executable,"-B",str(ROOT/
            "scripts/a50e_make_owner_pm_reflow_review_zip.py"),
            "--output",str(output)],cwd=ROOT,
            stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=25)
        assert r.returncode==0,r.stdout
        assert sha(output)==sha(original)
        r2=subprocess.run([sys.executable,"-B",str(ROOT/
            "scripts/a50e_make_owner_pm_reflow_review_zip.py"),
            "--output",str(output)],cwd=ROOT,
            stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=10)
        assert r2.returncode!=0
        assert "A50E_ZIP_EXISTS_OR_SYMLINK_HOLD" in r2.stdout
        assert sha(output)==sha(original)


def test_a50e_previous_v1_owner_pm_zip_untouched():
    original=ROOT/"docs/integration/handoffs/IT_TEM_P03_A50D_OWNER_PM_REVIEW_ONLY_20261110.zip"
    assert sha(original)=="fb8fb89a76a675b994aba9b62d4229a8ff715747b18486c998ea9ab41ef07eff"
