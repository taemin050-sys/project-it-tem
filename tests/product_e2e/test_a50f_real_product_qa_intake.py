"""A50F read-only rights/mask intake, with PRIVATE synthetic fixtures only.

No actual customer assets or license proof are created or placed into repo.
An evidence-shaped fixture can never be promoted to product fidelity PASS.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[2]


def sha(p:Path)->str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def lib():
    sp=importlib.util.spec_from_file_location(
        "a50f_qa",ROOT/"scripts/a50f_real_product_qa_intake.py")
    assert sp and sp.loader
    m=importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


@pytest.fixture()
def sample(tmp_path):
    a=tmp_path/"sample.png"
    b=tmp_path/"synthetic_candidate.png"
    mask=tmp_path/"mask.png"
    rights=tmp_path/"TEST_ONLY_not_real_license_proof.txt"
    Image.new("RGB",(720,960),(240,244,240)).save(a)
    Image.new("RGB",(1080,1350),(247,247,243)).save(b)
    bm=Image.new("L",(1080,1350),0)
    painter=ImageDraw.Draw(bm)
    painter.rectangle((480,510,615,1000),fill=255)
    bm.save(mask)
    rights.write_text("TEST_ONLY: THIS IS NOT A REAL RIGHTS CLEARANCE\n")
    rec={
      "case_id":"SYNTHETIC_TEST_ONLY",
      "design_id":"A_REFLOW_EDITORIAL_CENTER",
      "source_type":"INTERNAL_AUTHORIZED_PRODUCT_PHOTO",
      "source_asset_annotation":"ACTUAL_PRODUCT_PHOTO",
      "source_image_path":str(a),"source_image_sha256":sha(a),
      "rights_file_path":str(rights),"rights_sha256":sha(rights),
      "rights_document_ref":"TEST_ONLY_NEVER_REAL",
      "rights_scope_statement":"TEST_ONLY_NOT_RIGHTS_CLEARED",
      "rights_owner_role":"TEST_ONLY",
      "rights_review_evidence_ref":"TEST_ONLY_NONAUTHENTIC",
      "candidate_canvas_path":str(b),"candidate_canvas_sha256":sha(b),
      "protected_mask_path":str(mask),"protected_mask_sha256":sha(mask),
    }
    return rec


def test_a50f_empty_real_inventory_is_honestly_blocked(lib):
    source=ROOT/"docs/integration/BP18_A50F_REAL_ASSET_INTAKE_TEMPLATE_20261110.json"
    r=lib.make_report(json.loads(source.read_text("utf8")))
    assert r["cases_total"]==0
    assert r["evidence_present_cases"]==0
    assert r["d50_05_d50_06_gate"]=="HOLD"
    assert r["owner_pm_human_review"]=="PENDING"
    assert r["real_product_fidelity"]=="NOT_AUDITED"
    assert r["a5_1_implementation_authorized"] is False


def test_a50f_synthetic_mask_geometry_not_a_real_product_pass(lib,sample):
    o=lib.make_report({
        "contract":"IT_TEM_P03_A50F_REAL_ASSET_INTAKE_V1","cases":[sample]})
    assert o["cases_total"]==1
    assert o["evidence_present_cases"]==1
    r=o["reports"][0]
    assert r["geometry_review"]=="MASK_RECT_NONOVERLAP_ONLY"
    assert set(r["text_region_intersections_nonzero_pixels"])=={
        "headline","subline","cta"}
    assert all(x==0 for x in r["text_region_intersections_nonzero_pixels"].values())
    assert r["image_rights_authentication"]=="REQUIRES_EXTERNAL_OWNER_LEGAL_REVIEW"
    assert r["actual_product_identity_match"]=="NOT_AUDITED"
    assert r["product_quality_gate"]=="HOLD"
    assert o["authentic_rights_clearance"]=="NOT_AUDITED"


def test_a50f_large_mask_collision_is_hold(lib,sample,tmp_path):
    mask=tmp_path/"collision.png"
    bm=Image.new("L",(1080,1350),0)
    ImageDraw.Draw(bm).rectangle((480,980,605,1200),fill=255)
    bm.save(mask)
    sample={**sample,"protected_mask_path":str(mask),"protected_mask_sha256":sha(mask)}
    r=lib.make_report({
      "contract":"IT_TEM_P03_A50F_REAL_ASSET_INTAKE_V1","cases":[sample]})["reports"][0]
    assert r["geometry_review"]=="MASK_COLLISION_HOLD"
    assert r["text_region_intersections_nonzero_pixels"]["cta"]>0
    assert r["product_quality_gate"]=="HOLD"


@pytest.mark.parametrize("field",("source_image_sha256","rights_sha256",
                                   "candidate_canvas_sha256","protected_mask_sha256"))
def test_a50f_any_byte_hash_tamper_fail_closed(lib,sample,field):
    broken={**sample,field:"0"*64}
    r=lib.make_report({
      "contract":"IT_TEM_P03_A50F_REAL_ASSET_INTAKE_V1","cases":[broken]})
    assert r["blocked_cases"]==1
    assert r["evidence_present_cases"]==0
    assert r["blocked"][0]["reason_code"]=="A50F_EVIDENCE_SHA_MISMATCH"


def test_a50f_rights_review_missing_is_blocked(lib,sample):
    sample={**sample,"rights_review_evidence_ref":""}
    r=lib.make_report({
        "contract":"IT_TEM_P03_A50F_REAL_ASSET_INTAKE_V1","cases":[sample]})
    assert r["blocked_cases"]==1
    assert r["blocked"][0]["reason_code"]=="A50F_RIGHTS_REVIEW_PROVENANCE_MISSING"


def test_a50f_non_binary_mask_rejected(lib,sample,tmp_path):
    mask=tmp_path/"gray.png"
    bm=Image.new("L",(1080,1350),0)
    ImageDraw.Draw(bm).rectangle((480,510,615,990),fill=128)
    ImageDraw.Draw(bm).rectangle((500,510,520,530),fill=255)
    bm.save(mask)
    sample={**sample,"protected_mask_path":str(mask),"protected_mask_sha256":sha(mask)}
    r=lib.make_report({
       "contract":"IT_TEM_P03_A50F_REAL_ASSET_INTAKE_V1","cases":[sample]})
    assert r["blocked_cases"]==1
    assert r["blocked"][0]["reason_code"]=="A50F_MASK_NON_BINARY_VALUES"


def test_a50f_wrong_canvas_mask_rejected(lib,sample,tmp_path):
    m=tmp_path/"wrong.png"
    Image.new("L",(1080,1349),255).save(m)
    sample={**sample,"protected_mask_path":str(m),"protected_mask_sha256":sha(m)}
    r=lib.make_report({
        "contract":"IT_TEM_P03_A50F_REAL_ASSET_INTAKE_V1","cases":[sample]})
    assert r["blocked_cases"]==1
    assert r["blocked"][0]["reason_code"]=="A50F_MASK_FORMAT_OR_CANVAS_MISMATCH"


def test_a50f_cli_writes_only_sanitized_json_and_refuses_overwrite(tmp_path,sample):
    source=tmp_path/"input_manifest.private.json"
    source.write_text(json.dumps({
        "contract":"IT_TEM_P03_A50F_REAL_ASSET_INTAKE_V1",
        "cases":[sample]}))
    out=tmp_path/"A50F_report.json"
    cmd=[sys.executable,"-B",str(ROOT/"scripts/a50f_real_product_qa_intake.py"),
         "--manifest",str(source),"--out",str(out)]
    result=subprocess.run(cmd,cwd=ROOT,text=True,capture_output=True,timeout=20)
    assert result.returncode==0,result.stdout+result.stderr
    data=json.loads(out.read_text())
    assert "reports" in data and len(data["reports"])==1
    report=out.read_text()
    assert sample["source_image_path"] not in report
    assert sample["rights_file_path"] not in report
    assert sample["candidate_canvas_path"] not in report
    assert sample["protected_mask_path"] not in report
    assert data["source_binary_copied_to_output"] is False
    old=sha(out)
    again=subprocess.run(cmd,cwd=ROOT,text=True,capture_output=True,timeout=10)
    assert again.returncode!=0
    assert "A50F_OUTPUT_EXISTS_FAIL_CLOSED" in again.stdout+again.stderr
    assert sha(out)==old


def test_a50f_duplicate_case_ids_refused(lib,sample):
    with pytest.raises(ValueError,match="A50F_CASE_ID_DUPLICATE"):
        lib.make_report({
           "contract":"IT_TEM_P03_A50F_REAL_ASSET_INTAKE_V1",
           "cases":[sample,sample]})


def test_a50f_rights_and_image_same_bytes_refused(lib,sample):
    sample={**sample,"rights_file_path":sample["source_image_path"],
            "rights_sha256":sample["source_image_sha256"]}
    r=lib.make_report({
        "contract":"IT_TEM_P03_A50F_REAL_ASSET_INTAKE_V1","cases":[sample]})
    assert r["blocked_cases"]==1
    assert r["blocked"][0]["reason_code"]=="A50F_RIGHTS_AND_IMAGE_CANNOT_BE_IDENTICAL"

def test_a50f_request_is_not_delivery_or_owner_approval():
    p=ROOT/"docs/integration/BP18_A50F_OWNER_PM_FINAL_DECISION_REQUEST_20261110.md"
    t=p.read_text("utf8")
    for expected in (
        "박지수","이태민","PREPARED_NOT_CONFIRMED_DELIVERED",
        "A5-1","D50-02","D50-03","D50-04","D50-05","D50-06",
        "D50-07","D50-09","DECISION_PENDING_PM_OWNER",
        "43dba59f205b0cb5fc9a73eb9085481bd059cd1b2c3b3e383a05b32b0ba1579b",
    ):
        assert expected in t


def test_a50f_unsigned_human_scorecard_has_no_fake_scores_or_signatures():
    import csv
    p=ROOT/"docs/integration/BP18_A50F_OWNER_PM_HUMAN_AD_QUALITY_SCORECARD_UNSIGNED_20261110.csv"
    with p.open(newline="",encoding="utf8") as handle:
        rows=list(csv.DictReader(handle))
    assert len(rows)==10
    assert {x["candidate"] for x in rows}=={
        "A_REFLOW_EDITORIAL_CENTER","C_REFLOW_CONTRAST_ACTION"}
    assert {x["dimension"] for x in rows}=={
        "TYPOGRAPHY","CTA","PRODUCT_BRAND","COMMERCIAL_VISUAL","MOBILE"}
    assert {int(x["proposed_weight_NOT_APPROVED"]) for x in rows}=={10,15,20,25,30}
    for row in rows:
        assert row["owner_pm_approved_weight"]==""
        assert row["actual_human_score"]==""
        assert row["reviewer_identity_ref"]==""
        assert row["authentic_signed_evidence_ref"]==""
        assert row["human_acceptance"]=="PENDING"
        assert row["mask_protection_check"]=="NOT_AUDITED"
        assert row["rights_check"]=="NOT_AUDITED"
