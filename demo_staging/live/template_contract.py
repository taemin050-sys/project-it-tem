"""Additive, immutable per-Job A/legacy composition policy; no Provider code."""
from __future__ import annotations
import json
from src.image_generation.a_template import make_a_template
from src.image_generation.composition import CompositionLayout
from .contracts import LiveGateError, digest

A_ID="A_CENTERED"
A_VERSION="owner-a-v1"
LEGACY_ID="LEGACY_PINNED"
LEGACY_VERSION="legacy-layout-v1"

def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False)

def owner_a_policy():
    zone,layout=make_a_template()  # ALWAYS unverified, protected_regions=[]
    return {"profile_id":A_ID,"profile_version":A_VERSION,
            "safe_zone":zone.model_dump(mode="json"),
            "layout":layout.model_dump(mode="json")}

def normalize_layout(value):
    try:
        return CompositionLayout.model_validate(value,strict=True).model_dump(mode="json")
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
            expected=owner_a_policy()
            if (row["profile_version"]!=A_VERSION or zone!=expected["safe_zone"] or
                    layout!=expected["layout"]):
                raise ValueError("A owner mismatch")
        elif row["profile_id"]!=LEGACY_ID or zone is not None:
            raise ValueError("unknown profile")
        return {"profile_id":row["profile_id"],"profile_version":row["profile_version"],
                "safe_zone":zone,"layout":layout,"layout_sha":row["layout_sha"],
                "safe_zone_sha":row["safe_zone_sha"],
                "bound_font_sha":row["bound_font_sha"],
                "bound_context_sha":row["bound_context_sha"]}
    except (KeyError,TypeError,ValueError):
        raise LiveGateError("TEMPLATE_POLICY_INTEGRITY_FAILED") from None
