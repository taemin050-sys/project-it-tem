"""Additive, immutable per-Job A/legacy composition policy; no Provider code."""
from __future__ import annotations
import json
import os
from src.image_generation.a_template import make_a_template
from src.image_generation.composition import CompositionLayout
from src.image_generation.contracts import BP18_V3_LAYOUT_VERSION
from .contracts import LiveGateError, digest

A_ID="A_CENTERED"
A_VERSION="owner-a-v1"
# Pinned from the released Owner A v1 DTO (SHA of canonical JSON).
# NEVER derive these historical digests from a future mutable factory.
A_V1_SAFE_ZONE_SHA="c0fed10c854d6c8483d782f8721d60df7e6b975ceabeaab23dfb5ebe0861f4ce"
A_V1_LAYOUT_SHA="c9fe0d76a35e8171cbfca2b23ae1eafc2bd4d60e9ad7cb8164098b6f420d43e1"
LEGACY_ID="LEGACY_PINNED"
LEGACY_VERSION="legacy-layout-v1"
SIZE_PREFIX="OWNER_IMAGE_SIZE_"
SIZE_VERSION="instagram-copy-hierarchy-v2"
BP18_PREFIX="BP18_PROVISIONAL_SIZE_"
BP18_VERSION=BP18_V3_LAYOUT_VERSION
BP18_DESIGN_CONTRACT={
    "style":"BP18_EDITORIAL_WARM_PROVISIONAL",
    "version":BP18_VERSION,
    "production_approved":False,
    "aspect_ratio":"4:5",
    "cta":"IMAGE_REQUIRED",
    "font_license":"HUMAN_REVIEW_PENDING",
    "font_rule":"HEAD_MIN_64_SUB_MAX_50",
    "claim_policy":"COPY_UNMODIFIED_SERVER_COMPOSITION",
    "product_target":"OWNER_V2_GEOMETRY_UNVERIFIED_ACTUAL_BOUNDS",
}

def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False)

def _validated_layout(value):
    """Rehydrate canonical JSON arrays to the one exact typed tuple field."""
    from pydantic import BaseModel
    if isinstance(value,BaseModel):
        value=value.model_dump(mode="json")
    if not isinstance(value,dict):
        raise ValueError("Layout must be an object")
    value=dict(value)
    canvas=value.get("canvas_size")
    if type(canvas) is list:
        if (len(canvas)!=2 or any(type(x) is not int for x in canvas)):
            raise ValueError("Malformed canvas tuple")
        value["canvas_size"]=tuple(canvas)
    return CompositionLayout.model_validate(value,strict=True).model_dump(mode="json")


def historical_a_v1_layout(value):
    """Project Owner #23's expanded DTO back to the exact A v1 wire bytes.

    The new Owner added canvas_size/cta_placement and per-region text options.
    These are defaults for historical A only, NOT authority to rehash or migrate
    old Job snapshots. Reject any non-v1 semantics before canonical projection.
    """
    layout=_validated_layout(value)
    if layout.get("canvas_size")!=[1080,1350] or layout.get("cta_placement")!="image":
        raise LiveGateError("A_TEMPLATE_VERSION_DRIFT")
    old={k:v for k,v in layout.items() if k not in ("canvas_size","cta_placement")}
    for region in old["text_regions"].values():
        if region.get("max_lines") is not None or region.get("vertical_align")!="top":
            raise LiveGateError("A_TEMPLATE_VERSION_DRIFT")
        region.pop("max_lines",None)
        region.pop("vertical_align",None)
    return old


def owner_a_policy():
    zone,layout=make_a_template()  # ALWAYS unverified, protected_regions=[]
    zone_json=zone.model_dump(mode="json")
    layout_json=historical_a_v1_layout(layout)
    # If Owner releases new A defaults, require a new explicit version instead
    # of silently rewriting the historical owner-a-v1 schema.
    if (digest(zone_json)!=A_V1_SAFE_ZONE_SHA or
            digest(layout_json)!=A_V1_LAYOUT_SHA):
        raise LiveGateError("A_TEMPLATE_VERSION_DRIFT")
    return {"profile_id":A_ID,"profile_version":A_VERSION,
            "safe_zone":zone_json,"layout":layout_json}

def bp18_provisional_4x5_policy():
    """B-only experimental, snapshot-bound composed ad style. Not Owner approved."""
    from src.image_generation.layout_profiles import get_layout
    from src.image_generation.composition import (
        CompositionRect,CompositionLayout,CompositionTextRegion
    )
    from src.image_generation.size_selection import resolve_size_choice
    selection,profile=resolve_size_choice("4:5")
    def rect(box):
        w,h=profile.final
        return dict(zip(("left","top","right","bottom"),
                        [v/d for v,d in zip(box,(w,h,w,h))]))
    protected=[CompositionRect(**rect(profile.product))]
    zones={
        "headline":CompositionTextRegion(**rect((86,81,994,231)),
            min_font_size=64,max_font_size=88,max_lines=1,
            vertical_align="center",align="center",padding=12,
            color="#402A28",background="#FFF7F1"),
        "subline":CompositionTextRegion(**rect((86,247,994,410)),
            min_font_size=36,max_font_size=50,max_lines=2,
            vertical_align="center",align="center",padding=12,
            color="#402A28",background="#FFF7F1"),
        "cta":CompositionTextRegion(**rect((306,1195,774,1278)),
            min_font_size=30,max_font_size=40,max_lines=1,
            vertical_align="center",align="center",padding=9,
            color="#FFFFFF",background="#593932"),
    }
    layout=CompositionLayout(cta_placement="image",canvas_size=profile.final,
                             text_regions=zones,protected_regions=protected)
    metadata={"size":"4:5",
              "layout_selection":selection.model_dump(mode="json"),
              "native_size":list(profile.native),"final_size":list(profile.final),
              "design_profile_sha":digest(BP18_DESIGN_CONTRACT),
              "human_visual_acceptance":"PENDING",
              "mode":"DESIGN_INTENT_PROVISIONAL"}
    return {"profile_id":BP18_PREFIX+"4_5","profile_version":BP18_VERSION,
            "safe_zone":metadata,"layout":layout.model_dump(mode="json")}


def owner_size_policy(choice: str):
    """New image-size jobs freeze Owner #23 v2 or B-provisional v3 by environment."""
    if (choice=="4:5" and
        os.environ.get("IT_TEM_BP18_VISUAL_V3_ENABLED")=="YES"):
        return bp18_provisional_4x5_policy()
    from src.image_generation.size_selection import size_composition_policy
    spec=size_composition_policy(choice)
    layout=_validated_layout(spec["layout"])
    metadata={"size":choice,"layout_selection":spec["selection"],
              "native_size":spec["native_size"],"final_size":spec["final_size"]}
    return {"profile_id":spec["profile_id"],"profile_version":spec["profile_version"],
            "safe_zone":metadata,"layout":layout}


def normalize_layout(value):
    try:
        return _validated_layout(value)
    except (TypeError,ValueError):
        raise LiveGateError("COMPOSITION_LAYOUT_INVALID") from None

def verify_policy(row):
    if row is None:return None
    try:
        zone=json.loads(row["safe_zone_json"]) if row["safe_zone_json"] is not None else None
        layout=json.loads(row["layout_json"])
        if digest(zone)!=row["safe_zone_sha"] or digest(layout)!=row["layout_sha"]:
            raise ValueError("hash")
        normalize_layout(layout)
        if row["profile_id"]==A_ID:
            # Restore historical v1 from its stored snapshot and frozen SHA,
            # without asking the *current* Owner factory for old coordinates.
            if (row["profile_version"]!=A_VERSION or
                    row["safe_zone_sha"]!=A_V1_SAFE_ZONE_SHA or
                    row["layout_sha"]!=A_V1_LAYOUT_SHA):
                raise ValueError("A owner v1 version mismatch")
        elif row["profile_id"]==LEGACY_ID:
            if zone is not None:
                raise ValueError("legacy profile cannot carry a new size")
        elif row["profile_id"].startswith(BP18_PREFIX):
            # B candidate only. The persisted profile SHA, not the current
            # layout factory, remains historical authority after ingress.
            from src.image_generation.size_selection import resolve_size_choice
            if (row["profile_id"]!=BP18_PREFIX+"4_5"
                or row["profile_version"]!=BP18_VERSION
                or not isinstance(zone,dict)
                or zone.get("size")!="4:5"
                or zone.get("design_profile_sha")!=digest(BP18_DESIGN_CONTRACT)
                or zone.get("human_visual_acceptance")!="PENDING"
                or zone.get("mode")!="DESIGN_INTENT_PROVISIONAL"
                or layout.get("cta_placement")!="image"
                or "cta" not in layout["text_regions"]):
                raise ValueError("BP18 provisional profile invalid")
            selection,profile=resolve_size_choice("4:5")
            if (zone.get("layout_selection")!=selection.model_dump(mode="json")
                or zone.get("native_size")!=list(profile.native)
                or zone.get("final_size")!=list(profile.final)
                or tuple(layout.get("canvas_size",()))!=profile.final
                or layout["text_regions"]["headline"]["min_font_size"]
                   <=layout["text_regions"]["subline"]["max_font_size"]):
                raise ValueError("BP18 profile geometry or hierarchy invalid")
        elif row["profile_id"].startswith(SIZE_PREFIX):
            # Snapshot-bound v2 image geometry is independent of the mutable
            # current Owner factory; only the original stored hash is authority.
            from src.image_generation.size_selection import resolve_size_choice
            if row["profile_version"]!=SIZE_VERSION or not isinstance(zone,dict):
                raise ValueError("size policy version invalid")
            choice=zone.get("size")
            selection,profile=resolve_size_choice(choice)
            if (row["profile_id"]!=SIZE_PREFIX+choice.replace(":","_")
                or zone.get("layout_selection")!=selection.model_dump(mode="json")
                or zone.get("native_size")!=list(profile.native)
                or zone.get("final_size")!=list(profile.final)
                or tuple(layout.get("canvas_size",()))!=profile.final):
                raise ValueError("size policy geometry invalid")
        else:
            raise ValueError("unknown profile")
        return {"profile_id":row["profile_id"],"profile_version":row["profile_version"],
                "safe_zone":zone,"layout":layout,"layout_sha":row["layout_sha"],
                "safe_zone_sha":row["safe_zone_sha"],
                "bound_font_sha":row["bound_font_sha"],
                "bound_context_sha":row["bound_context_sha"]}
    except (KeyError,TypeError,ValueError):
        raise LiveGateError("TEMPLATE_POLICY_INTEGRITY_FAILED") from None
