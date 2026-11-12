"""A5-1B: bind per-Job signed candidate mask + immutable image/layout proof.

A trusted annotator's binary object/label mask is read ONLY from an
operator-owned protected directory. Mask geometry and compositor pixel
preservation are mechanical checks, NOT an algorithmic certification of
actual product identity, labels or legal rights.

Current integration remains OFFLINE_FIXTURE: no paid Provider authority.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image, ImageChops

from .contracts import LiveGateError
from .a51b_signed_beta_contract import (
    BETA_PREFIX, KEYS, HEX, IDENTIFIER, _blocked, _regular, _sealed_dir,
    _verify_signature, _verify_trust_anchor,
)
from src.image_generation.composition import resize_ad_png

CONTRACT="IT_TEM_P03_A51B_SIGNED_CANDIDATE_MASK_V1"
IMAGE_SIZE=(1080,1350)
# Bound signed review UTC dates in BOTH directions. Review time is not an
# authorization to pre-date future product acceptance. Skew is for limited
# clock synchronization only, never a 30-day look-ahead.
MAX_FUTURE_REVIEW_SKEW=timedelta(seconds=30)
MAX_REVIEW_AGE=timedelta(days=90)


def validate_review_time(review_utc:str, *, now_utc:datetime|None=None)->None:
    """Strict UTC/timezone and asymmetric age checks (inclusive boundaries).

    All malformed or non-UTC timestamps fail closed. Injection of a fixed
    aware UTC clock is only for deterministic boundary testing.
    """
    if not isinstance(review_utc,str):
        _blocked("MASK_REVIEW_TIME_INVALID")
    try:
        review=datetime.fromisoformat(review_utc.replace("Z","+00:00"))
        current=now_utc if now_utc is not None else datetime.now(timezone.utc)
        if (review.tzinfo is None or review.utcoffset()!=timedelta(0)
            or current.tzinfo is None or current.utcoffset()!=timedelta(0)):
            _blocked("MASK_REVIEW_TIME_INVALID")
    except (TypeError,ValueError,AttributeError,OverflowError) as exc:
        # LiveGateError inherits ValueError: never swallow an explicit
        # rejection code and reclassify it as merely malformed input.
        if isinstance(exc,LiveGateError):
            raise
        _blocked("MASK_REVIEW_TIME_INVALID")
    if review > current + MAX_FUTURE_REVIEW_SKEW:
        _blocked("MASK_REVIEW_TIME_IN_FUTURE")
    if current - review > MAX_REVIEW_AGE:
        _blocked("MASK_REVIEW_TIME_STALE")



def sha(data:bytes)->str:
    return hashlib.sha256(data).hexdigest()


def validate_candidate_review(*, root:Path|str, trust_root:Path|str,
                              trusted_sha:dict, job:dict, policy:dict,
                              input_png:bytes, final_png:bytes)->dict:
    """Require dual-signature mask decision AFTER image+copy approval.

    caller must pass authenticated DB Job and immutable template snapshot,
    never arbitrary browser JSON; user cannot supply arbitrary filesystem
    paths. Product/rights authenticity is never inferred from a binary mask.
    """
    private=_sealed_dir(str(root))
    trust=_sealed_dir(str(trust_root))
    if private==trust:
        _blocked("MASK_ROOT_AND_TRUST_ROOT_CONFLICT")
    if type(trusted_sha) is not dict or set(trusted_sha)!=set(KEYS):
        _blocked("MASK_TRUST_ANCHORS_MISSING")
    pub={role:_verify_trust_anchor(trust,role,trusted_sha[role]) for role in KEYS}
    if trusted_sha["image_owner"]==trusted_sha["pm"]:
        _blocked("MASK_SIGNERS_NOT_INDEPENDENT")
    jid=job.get("job_id")
    if type(jid) is not str or not IDENTIFIER.fullmatch(jid):
        _blocked("MASK_JOB_ID_INVALID")
    decision_file=_regular(private,jid+".maskreview.json")
    raw=decision_file.read_bytes()
    try:
        decision=json.loads(raw)
    except (ValueError,UnicodeError):
        _blocked("MASK_RECORD_JSON_INVALID")
    required={
        "contract","job_id","policy_epoch","signed_profile_decision_sha256",
        "profile_id","layout_sha256","copy_sha256","approval_sha256",
        "source_candidate_sha256","mask_sha256","annotation_kind",
        "annotation_scope","rights_evidence_sha256",
        "rights_scope","review_time_utc","review_decision",
    }
    if type(decision) is not dict or set(decision)!=required:
        _blocked("MASK_RECORD_SCHEMA_INVALID")
    if (decision["contract"]!=CONTRACT
        or decision["job_id"]!=jid
        or decision["profile_id"]!=policy["profile_id"]
        or not policy["profile_id"].startswith(BETA_PREFIX)
        or decision["layout_sha256"]!=policy["layout_sha"]
        or decision["policy_epoch"]!=policy["safe_zone"]["policy_epoch"]
        or decision["signed_profile_decision_sha256"]!=policy["safe_zone"][
            "signed_owner_pm_decision_sha256"]
        or decision["copy_sha256"]!=job["copy_sha"]
        or decision["approval_sha256"]!=job["approval_sha"]
        or decision["source_candidate_sha256"]!=sha(input_png)
        or decision["annotation_kind"]!="PRODUCT_PACKAGE_LOGO_LABEL_UNION"
        or decision["annotation_scope"]!="FINAL_1080x1350_COORDINATES"
        or decision["review_decision"]!="APPROVED_FOR_MASK_GEOMETRY_ONLY"
        or not HEX.fullmatch(str(decision["rights_evidence_sha256"]))
        or decision["rights_scope"] not in (
            "LOCAL_READ_ONLY_PRODUCT_QA_ONLY",
            "RIGHTS_DECLARED_PENDING_INDEPENDENT_LEGAL_REVIEW",
        )):
        _blocked("MASK_RECORD_CONTEXT_OR_RIGHTS_MISMATCH")
    validate_review_time(decision["review_time_utc"])
    for role,key in pub.items():
        signature=_regular(private,jid+"."+role+".sig")
        _verify_signature(raw,signature,key,decision_file)
    mask_file=_regular(private,jid+".protected_mask.png",max_bytes=8*1024*1024)
    if sha(mask_file.read_bytes())!=decision["mask_sha256"]:
        _blocked("MASK_FILE_SHA_CHANGED")
    try:
        with Image.open(mask_file) as picture:
            picture.load()
            if picture.format!="PNG" or picture.size!=IMAGE_SIZE or picture.mode!="L":
                _blocked("MASK_FORMAT_OR_CANVAS_INVALID")
            if picture.getextrema()!=(0,255):
                _blocked("MASK_EMPTY_OR_FULL")
            histogram=picture.histogram()
            if any(histogram[i] for i in range(1,255)):
                _blocked("MASK_BINARY_VALUES_REQUIRED")
            mask=picture.copy()
    except (OSError,ValueError):
        _blocked("MASK_DECODE_FAILED")
    if not 100 <= histogram[255] < 1080*1350*0.85:
        _blocked("MASK_COVERAGE_OUT_OF_BOUNDS")
    # A real mask must never intersect the ACTUAL frozen textarea or CTA.
    for field, region in policy["layout"]["text_regions"].items():
        from src.image_generation.composition import CompositionTextRegion
        box=CompositionTextRegion.model_validate(region).pixels(IMAGE_SIZE)
        if mask.crop(box).getbbox() is not None:
            _blocked("MASK_INTERSECTS_"+field.upper())
    try:
        expected=resize_ad_png(input_png,final_size=IMAGE_SIZE).image_bytes
        with Image.open(__import__("io").BytesIO(expected)) as src:
            src.load()
            baseline=src.convert("RGB")
        with Image.open(__import__("io").BytesIO(final_png)) as output:
            output.load()
            if output.format!="PNG" or output.size!=IMAGE_SIZE:
                _blocked("MASK_FINAL_IMAGE_FORMAT_INVALID")
            rendered=output.convert("RGB")
        diff=ImageChops.difference(baseline,rendered)
        # Any of the 3 color channels changing within protected mask is HOLD.
        protected_diff=ImageChops.multiply(diff,mask.convert("RGB"))
        if protected_diff.getbbox() is not None:
            _blocked("MASK_PROTECTED_PRODUCT_PIXELS_CHANGED")
    except (OSError,ValueError):
        _blocked("MASK_IMAGE_COMPARE_FAILED")
    return {
        "contract":"IT_TEM_P03_A51B_CANDIDATE_MASK_VALIDATION_V1",
        "job_id":jid,
        "signed_review_sha256":sha(raw),
        "candidate_image_sha256":sha(input_png),
        "final_png_sha256":sha(final_png),
        "mask_sha256":decision["mask_sha256"],
        "protected_pixel_count":histogram[255],
        "layout_sha256":policy["layout_sha"],
        "profile_id":policy["profile_id"],
        "policy_epoch":policy["safe_zone"]["policy_epoch"],
        "approval_sha256":job["approval_sha"],
        "copy_sha256":job["copy_sha"],
        "signatures_verified":list(KEYS),
        "geometry_and_pixel_preservation":"PASS",
        "actual_product_identity_match":"NOT_AUDITED",
        "actual_label_readability":"NOT_AUDITED",
        "actual_product_rights_authenticated":False,
        "real_provider_transfer_authorized":False,
        "human_pm_visual_accepted":False,
        "product_quality_gate":"HOLD",
    }
