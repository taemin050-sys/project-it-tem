"""Additive, immutable per-Job A/legacy composition policy; no Provider code."""
from __future__ import annotations
import json
from src.image_generation.a_template import make_a_template
from src.image_generation.composition import CompositionLayout
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

def owner_size_policy(choice: str):
    """New image-size jobs freeze Owner #23 coordinates, not legacy A v1."""
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
