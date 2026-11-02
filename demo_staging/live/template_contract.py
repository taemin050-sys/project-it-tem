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

def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False)

def owner_a_policy():
    zone,layout=make_a_template()  # ALWAYS unverified, protected_regions=[]
    zone_json=zone.model_dump(mode="json")
    layout_json=layout.model_dump(mode="json")
    # If Owner releases new A defaults, require a new explicit version instead
    # of silently rewriting the historical owner-a-v1 schema.
    if (digest(zone_json)!=A_V1_SAFE_ZONE_SHA or
            digest(layout_json)!=A_V1_LAYOUT_SHA):
        raise LiveGateError("A_TEMPLATE_VERSION_DRIFT")
    return {"profile_id":A_ID,"profile_version":A_VERSION,
            "safe_zone":zone_json,"layout":layout_json}

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
            # Restore historical v1 from its stored snapshot and frozen SHA,
            # without asking the *current* Owner factory for old coordinates.
            if (row["profile_version"]!=A_VERSION or
                    row["safe_zone_sha"]!=A_V1_SAFE_ZONE_SHA or
                    row["layout_sha"]!=A_V1_LAYOUT_SHA):
                raise ValueError("A owner v1 version mismatch")
        elif row["profile_id"]!=LEGACY_ID or zone is not None:
            raise ValueError("unknown profile")
        return {"profile_id":row["profile_id"],"profile_version":row["profile_version"],
                "safe_zone":zone,"layout":layout,"layout_sha":row["layout_sha"],
                "safe_zone_sha":row["safe_zone_sha"],
                "bound_font_sha":row["bound_font_sha"],
                "bound_context_sha":row["bound_context_sha"]}
    except (KeyError,TypeError,ValueError):
        raise LiveGateError("TEMPLATE_POLICY_INTEGRITY_FAILED") from None
