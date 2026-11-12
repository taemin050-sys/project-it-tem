"""Versioned nonbillable A5-1 Composed 4:5 Profile v3 Runtime adapter.

Owner-first: this is ADDITIVE and NEVER redefines historical Image Owner v2
profiles. The geometry is explicitly derived from the independently reviewed
A50E A/C proposals; final Owner/PM profile acceptance is still pending.

Only an explicitly authorized OFFLINE_FIXTURE developer process may select a
beta proposal. Signed production policy activation is NOT provided here.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path

from src.image_generation.composition import (
    CompositionLayout, CompositionRect, CompositionTextRegion,
)
from src.image_generation.layout_profiles_v3 import (
    GEOMETRY, OWNER_A5_SAFE as SAFE_FRAME, OWNER_A5_PROFILE_MARKER_PREFIX,
)
from .contracts import LiveGateError, digest

PROFILE_VERSION = "owner-composed-4x5-v3-beta-proposal1"
PROPOSAL_EPOCH = "a5-v3-beta-unsigned-20261110"
PROFILE_PREFIX = "OWNER_COMPOSED_4X5_V3_BETA_"
PROFILE_OPTIONS = ("A", "C")
REFERENCE_MANIFEST_SHA = "42995a82027e727eebfb416f9cf4270b3870b1849b041f2e0151a0578e2615b8"
PRETENDARD_139_SHA = "3090ccde0442bb347aa7685d9ba8b17436a60682df6e8f92a9a670de14056e22"
FONT_LICENSE_SHA = "b04538c9abec39a3db75108cf0af0fd9c77032fe8aa2cf38345b4d250e98e38e"


def _rect(box: tuple[int,int,int,int]) -> CompositionRect:
    return CompositionRect(
        left=math.nextafter(box[0]/1080,0.0),
        top=math.nextafter(box[1]/1350,0.0),
        right=math.nextafter(box[2]/1080,1.0),
        bottom=math.nextafter(box[3]/1350,1.0),
    )


def _text_region(box, *, ink, background=None, min_font=36, max_font=80):
    values=_rect(box).model_dump()
    return CompositionTextRegion(**values, max_lines=1,
        vertical_align="center", min_font_size=min_font,
        max_font_size=max_font, align="center", padding=16,
        color=ink, background=background)


def build_proposal(profile: str) -> dict:
    if profile not in PROFILE_OPTIONS or type(profile) is not str:
        raise LiveGateError("A5_V3_PROFILE_UNRECOGNIZED")
    g=GEOMETRY[profile]
    # Fail CLOSED if a proposed fixed design accidentally puts its text or
    # CTA inside the synthetic product target; a real mask is still required
    # for actual product fidelity.
    boxes=(g["headline"],g["subline"],g["cta"])
    product=g["product"]
    for a in boxes:
        if (max(a[0],product[0]) < min(a[2],product[2])
            and max(a[1],product[1]) < min(a[3],product[3])):
            raise LiveGateError("A5_V3_PRODUCT_TARGET_TEXT_COLLISION")
        if not (SAFE_FRAME[0] <= a[0] < a[2] <= SAFE_FRAME[2]
                and SAFE_FRAME[1] <= a[1] < a[3] <= SAFE_FRAME[3]):
            raise LiveGateError("A5_V3_SAFE_FRAME_VIOLATION")
    if (SAFE_FRAME[3]-g["cta"][3])/3 < 12:
        raise LiveGateError("A5_V3_PROPOSED_MOBILE_CTA_SAFE_INSET_HOLD")
    layout=CompositionLayout(
        cta_placement="image",canvas_size=(1080,1350),
        text_regions={
          "headline":_text_region(g["headline"],ink=g["headline_ink"],
                                  min_font=64,max_font=116),
          "subline":_text_region(g["subline"],ink=g["subline_ink"],
                                 min_font=54,max_font=75),
          "cta":_text_region(g["cta"],ink=g["cta_ink"],
                             background=g["cta_bg"],min_font=48,max_font=60),
        },
        protected_regions=[_rect(product)],
    )
    meta={
        "size":"4:5",
        "mode":"composed",
        "final_size":[1080,1350],
        "native_size":[1152,1440],
        "layout_selection":{"aspect_ratio":"4:5","placement":"feed"},
        "policy_epoch":PROPOSAL_EPOCH,
        "proposal_sha256":g["proposal_sha"],
        "font_file_sha256_required":PRETENDARD_139_SHA,
        "font_license_sha256_reference":FONT_LICENSE_SHA,
        "safe_frame_ltrb":list(SAFE_FRAME),
        "protection_basis":"SYNTHETIC_TARGET_NOT_REAL_MASK",
        "deployment_authority":"OFFLINE_FIXTURE_ONLY_NOT_PM_OWNER_SIGNED",
        "real_provider_permitted":False,
        "real_customer_assets_permitted":False,
    }
    return {
        "profile_id":PROFILE_PREFIX+profile,
        "profile_version":PROFILE_VERSION,
        "safe_zone":meta,
        "layout":layout.model_dump(mode="json"),
    }


def selected_dev_profile(input_snapshot: dict, *, template_profile: str) -> str|None:
    """No implicit selection, always fail-closed on unsafe activation."""
    selected=os.environ.get("IT_TEM_A5_V3_BETA_PROFILE","").strip()
    if not selected:
        return None
    if selected not in PROFILE_OPTIONS:
        raise LiveGateError("A5_V3_PROFILE_UNRECOGNIZED")
    if (template_profile!="A" or input_snapshot.get("image_size")!="4:5"
        or input_snapshot.get("generation_mode")!="composed"):
        # Do not alter Freeform, 3:4, 9:16 or historical Jobs.
        return None
    if (os.environ.get("IT_TEM_A5_V3_OFFLINE_DEV_ALLOWED")!="YES"
        or os.environ.get("IT_TEM_LIVE_ENABLED","NO")=="YES"
        or os.environ.get("IT_TEM_ENABLE_BILLABLE_TEXT_CALLS","NO")=="YES"):
        raise LiveGateError("A5_V3_PROPOSAL_UNAUTHORIZED_FOR_BILLABLE_OR_LIVE")
    return selected


def validate_frozen(row, zone, layout):
    """Validate the saved nonbillable v3 proposal without changing it."""
    profile_id=row["profile_id"]
    if not profile_id.startswith(PROFILE_PREFIX):
        raise ValueError("not proposal v3")
    candidate=profile_id[len(PROFILE_PREFIX):]
    expected=build_proposal(candidate)
    if (row["profile_version"]!=PROFILE_VERSION
        or zone!=expected["safe_zone"]
        or digest(layout)!=digest(expected["layout"])
        or row["safe_zone_sha"]!=digest(expected["safe_zone"])
        or row["layout_sha"]!=digest(expected["layout"])):
        raise ValueError("v3 immutable profile snapshot mismatch")
    return candidate


def verify_receipt_for_v3(receipt:dict, *, plan:dict, font_sha:str, copy_json:dict)->dict:
    """Serving validation of actual Owner-rendered Head/Sub/CTA, not mock PNG."""
    import hashlib
    if not plan["profile_id"].startswith(PROFILE_PREFIX):
        return receipt
    profile=plan["profile_id"][len(PROFILE_PREFIX):]
    expected=build_proposal(profile)
    if (font_sha!=PRETENDARD_139_SHA
        or plan["profile_version"]!=PROFILE_VERSION
        or plan["layout_sha"]!=digest(expected["layout"])
        or plan["profile_id"]!=expected["profile_id"]):
        raise LiveGateError("A5_V3_FROZEN_PROFILE_FONT_MISMATCH")
    placements=receipt.get("placements",{})
    texts=copy_json.get("ad_copy",{})
    if (receipt.get("cta_placement")!="image"
        or receipt.get("omitted_image_fields")!=[]
        or set(placements)!={"headline","subline","cta"}
        or set(texts)!={"headline","subline","cta"}):
        raise LiveGateError("A5_V3_CTA_MISSING_OR_DUPLICATED")
    for field in ("headline","subline","cta"):
        value=texts[field]
        if not isinstance(value,str) or not value.strip():
            raise LiveGateError("A5_V3_REQUIRED_COPY_FIELD_EMPTY")
        actual=placements[field]
        if actual.get("text_sha256")!=hashlib.sha256(value.encode("utf-8")).hexdigest():
            raise LiveGateError("A5_V3_COPY_SHA_MISMATCH")
        if actual.get("region")!=[
            int(round(x)) for x in GEOMETRY[profile][field]]:
            # PIL native conversion must not shift any approved rectangle.
            raise LiveGateError("A5_V3_RENDERED_LAYOUT_MISMATCH")
        if actual.get("line_count")!=1 or not actual.get("ink_boxes"):
            raise LiveGateError("A5_V3_COPY_OVERFLOW_OR_MULTILINE")
        if field=="cta" and actual["font_size"]<48:
            raise LiveGateError("A5_V3_CTA_TOO_SMALL")
    if (receipt.get("beta_style")!=profile
        or receipt.get("cta_corner_radius")!=GEOMETRY[profile]["cta_corner_radius"]
        or receipt.get("typography_variable_weight")!={
            "headline":700,"subline":500,"cta":700}):
        raise LiveGateError("A5_V3_STYLED_RENDERER_CONTRACT_MISMATCH")
    return {
        **receipt,
        "profile_id":plan["profile_id"],
        "profile_version":plan["profile_version"],
        "profile_layout_sha256":plan["layout_sha"],
        "profile_policy_epoch":PROPOSAL_EPOCH,
        "proposal_design_sha256":expected["safe_zone"]["proposal_sha256"],
        "font_license_sha256_reference":FONT_LICENSE_SHA,
        # Owner v2 reports protected_region_check=True for any supplied box.
        # This beta has ONLY a synthetic target: never represent it as a
        # verified product/brand/label/object mask.
        "protected_region_check":False,
        "synthetic_target_region_check":True,
        "protection_evidence":"SYNTHETIC_TARGET_ONLY_REAL_PRODUCT_NOT_AUDITED",
        "beta_only":True,
        "owner_pm_signed":False,
    }
