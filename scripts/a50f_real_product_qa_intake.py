"""A5-0F rights-evidence and real-image/mask QA intake, *review-only*.

Never writes any product photo, mask, font, approval/decision register or
production code. It can examine evidence files read-only and emit sanitized
SHA/geometry summaries into a NEW caller-owned output directory.

The existence of a local rights document or mask does NOT establish
authenticated rights clearance, product fidelity, platform safe-zone
conformance, or Owner/PM acceptance. These remain HOLD by design.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from PIL import Image

BASE=Path(__file__).resolve().parents[1]
E50=BASE/"docs/integration/evidence/A50E_20261110"
SCENARIOS={
 "A_REFLOW_EDITORIAL_CENTER",
 "C_REFLOW_CONTRAST_ACTION",
}
TEXT_FIELDS=("headline","subline","cta")
# A user-supplied case identifier is not a privacy-safe output identifier.
# Accept only short opaque ASCII IDs for lookup/duplicate checks. Use a
# deterministic index token in every exported case record (success or HOLD).
CASE_ID_FORMAT=re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", re.ASCII)


def safe_report_case_id(index:int)->str:
    return f"CASE_{index:06d}"


def digest(path:Path)->str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fail(reason:str):
    raise ValueError("A50F_"+reason)


def hexsha(value)->bool:
    return isinstance(value,str) and len(value)==64 and all(c in "0123456789abcdef" for c in value)


def immutable_source(path:str,expected:str)->Path:
    if not hexsha(expected):
        fail("SHA_EXPECTED_REQUIRED")
    p=Path(path).expanduser()
    if not p.is_file() or p.is_symlink():
        fail("EVIDENCE_FILE_MISSING_OR_SYMLINK")
    if digest(p)!=expected:
        fail("EVIDENCE_SHA_MISMATCH")
    return p


def image_validate(path:Path,expect_size:tuple|None=None):
    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        assert image.format in ("PNG","JPEG","WEBP")
        size=image.size
        if expect_size is not None and size!=expect_size:
            fail("OUTPUT_IMAGE_OR_MASK_SIZE_MISMATCH")
    return size


def mask_intersections(mask:Path,boxes:dict):
    with Image.open(mask) as im:
        if im.format!="PNG" or im.size!=(1080,1350):
            fail("MASK_FORMAT_OR_CANVAS_MISMATCH")
        if im.mode not in ("1","L"):
            fail("MASK_MUST_BE_SINGLE_CHANNEL_BINARY")
        pixels=im.convert("L")
        mm=pixels.getextrema()
        if mm[1]==0:
            fail("EMPTY_PRODUCT_MASK")
        histogram=pixels.histogram()
        if any(histogram[i] for i in range(1,255)):
            # Only a binary 0/255 mask, not probability maps.
            fail("MASK_NON_BINARY_VALUES")
        counts={}
        for field,box in boxes.items():
            crop=pixels.crop(tuple(box))
            hist=crop.histogram()
            counts[field]=sum(hist[1:])
        return counts


def load_reference()->dict:
    p=E50/"A50E_REFLOW_DESIGN_MANIFEST.json"
    m=json.loads(p.read_text("utf-8"))
    assert m["owner_pm_approved"] is False
    assert set(m["variants"])==SCENARIOS
    if "canvas" in m:
        assert m["canvas"]==[1080,1350]
    return m


def evaluate_case(case:dict,reference:dict)->dict:
    cid=case.get("case_id")
    if not isinstance(cid,str) or CASE_ID_FORMAT.fullmatch(cid) is None:
        fail("CASE_ID_INVALID")
    design=case.get("design_id")
    if design not in SCENARIOS:
        fail("DESIGN_ID_UNAPPROVED_OR_UNKNOWN")
    if case.get("source_type") not in ("RIGHTS_CLEARED_CUSTOMER_SAMPLE",
                                      "INTERNAL_AUTHORIZED_PRODUCT_PHOTO"):
        fail("SOURCE_TYPE_NOT_DECLARED")
    if case.get("source_asset_annotation") not in ("ACTUAL_PRODUCT_PHOTO",
                                                   "REAL_PROVIDER_GENERATED_AD"):
        fail("REAL_ASSET_TYPE_MISSING")
    if case.get("rights_document_ref") in ("",None):
        fail("RIGHTS_DOCUMENT_REF_MISSING")
    if case.get("rights_scope_statement") in ("",None):
        fail("RIGHTS_SCOPE_MISSING")
    if not case.get("rights_owner_role") or not case.get("rights_review_evidence_ref"):
        fail("RIGHTS_REVIEW_PROVENANCE_MISSING")
    src=immutable_source(case["source_image_path"],case["source_image_sha256"])
    rights=immutable_source(case["rights_file_path"],case["rights_sha256"])
    if src.resolve()==rights.resolve():
        fail("RIGHTS_AND_IMAGE_CANNOT_BE_IDENTICAL")
    source_dimensions=image_validate(src)
    product=immutable_source(case["candidate_canvas_path"],case["candidate_canvas_sha256"])
    image_validate(product,(1080,1350))
    mask=immutable_source(case["protected_mask_path"],case["protected_mask_sha256"])
    rects={
       field:reference["variants"][design]["copy"][field]["rect"]
       for field in TEXT_FIELDS
    }
    hits=mask_intersections(mask,rects)
    # If mask differs from real package/label protection or product identity,
    # only human & independent QA can decide. Region overlaps are hard HOLD.
    geometry="MASK_COLLISION_HOLD" if any(hits.values()) else "MASK_RECT_NONOVERLAP_ONLY"
    return {
        "case_id":cid,
        "design_id":design,
        "source_type":case["source_type"],
        "source_asset_annotation":case["source_asset_annotation"],
        "source_image_sha256":case["source_image_sha256"],
        "rights_evidence_sha256":case["rights_sha256"],
        "candidate_canvas_sha256":case["candidate_canvas_sha256"],
        "protected_mask_sha256":case["protected_mask_sha256"],
        "source_dimensions":list(source_dimensions),
        "canvas_dimensions":[1080,1350],
        "text_region_intersections_nonzero_pixels":hits,
        "geometry_review":geometry,
        "actual_product_identity_match":"NOT_AUDITED",
        "logo_label_readability":"NOT_AUDITED",
        "mask_annotation_correctness":"NOT_AUDITED",
        "image_rights_authentication":"REQUIRES_EXTERNAL_OWNER_LEGAL_REVIEW",
        "real_platform_safe_zone":"NOT_AUDITED",
        "mobile_human_readability":"NOT_AUDITED",
        "human_owner_pm_acceptance":"PENDING",
        "product_quality_gate":"HOLD",
    }


def make_report(manifest:dict)->dict:
    if manifest.get("contract")!="IT_TEM_P03_A50F_REAL_ASSET_INTAKE_V1":
        fail("MANIFEST_CONTRACT_MISMATCH")
    items=manifest.get("cases")
    if not isinstance(items,list):
        fail("CASES_LIST_MISSING")
    # Reject duplicate valid source keys without exposing raw case metadata.
    # Invalid metadata is handled as a blocked case, not echoed in reports.
    ids=[x.get("case_id") for x in items if isinstance(x,dict)
         and isinstance(x.get("case_id"),str)
         and CASE_ID_FORMAT.fullmatch(x["case_id"]) is not None]
    if len(ids)!=len(set(ids)):
        fail("CASE_ID_DUPLICATE_OR_INVALID")
    ref=load_reference()
    completed=[]
    blocked=[]
    for index,record in enumerate(items, start=1):
        external_id=safe_report_case_id(index)
        try:
            # Require a dictionary; malformed entries become safe HOLD rows.
            if not isinstance(record,dict):
                fail("CASE_SCHEMA_OR_INPUT_INVALID")
            checked=evaluate_case(record,ref)
            # Even syntactically valid raw IDs may be personal names/handles.
            # Never export the caller-supplied identifier, including on PASS.
            checked["case_id"]=external_id
            completed.append(checked)
        except (KeyError,TypeError,ValueError,AssertionError) as exc:
            reason=str(exc)
            # Hide private source paths in outward-facing report.
            if not reason.startswith("A50F_"):
                reason="A50F_CASE_SCHEMA_OR_INPUT_INVALID"
            blocked.append({"case_id":external_id,
                            "evidence_gate":"HOLD","reason_code":reason})
    return {
        "contract":"IT_TEM_P03_A50F_RIGHTS_MASK_READONLY_PREFLIGHT_V1",
        "review_only":True,
        "source_reference_a50e_sha256":digest(E50/"A50E_REFLOW_DESIGN_MANIFEST.json"),
        "cases_total":len(items),
        "evidence_present_cases":len(completed),
        "blocked_cases":len(blocked),
        "reports":completed,
        "blocked":blocked,
        "authentic_rights_clearance":"NOT_AUDITED",
        "real_product_fidelity":"NOT_AUDITED",
        "cta_platform_safe_zone":"NOT_AUDITED",
        "owner_pm_human_review":"PENDING",
        "d50_05_d50_06_gate":"HOLD",
        "a5_1_implementation_authorized":False,
        "gcp_qa_deployment":"HOLD",
        "paid_worker":"HOLD",
        "release":"NOT_RELEASE_READY",
        "source_binary_copied_to_output":False,
    }


def main()->None:
    ap=argparse.ArgumentParser()
    ap.add_argument("--manifest",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    args=ap.parse_args()
    raw=args.manifest.expanduser().resolve(strict=True)
    report=make_report(json.loads(raw.read_text("utf-8")))
    output=args.out.expanduser()
    if output.exists() or output.is_symlink():
        raise SystemExit("A50F_OUTPUT_EXISTS_FAIL_CLOSED")
    # Only create a new report JSON; no product images or masks are exported.
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print("A50F_READONLY_PRODUCT_EVIDENCE_PREFLIGHT")
    print("CASES",report["cases_total"],"SCHEMA_AND_HASH_READABLE",report["evidence_present_cases"])
    print("BLOCKED",report["blocked_cases"],"D50_05_D50_06_HOLD")
    print("RIGHTS/HUMAN/MODEL/PLATFORM_QUALITY_NOT_AUDITED")


if __name__=="__main__":
    main()
