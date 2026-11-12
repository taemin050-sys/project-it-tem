"""New-Job-only editorial policy using the accepted display type renderer.

Existing snapshots and Owner factories are untouched. Actual private-configured
Pretendard/font-license bytes are checked before their SHA enters a new policy.
These engineering checks never claim human visual or commercial acceptance.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import os
from pathlib import Path
import re
import stat

from fontTools.ttLib import TTFont

from src.image_generation.composition import CompositionLayout
from src.image_generation.contracts import BP18_DUAL_IMAGE_CTA_VERSION, BP18_V3_LAYOUT_VERSION
from src.image_generation.protected_product import professional_layout
from src.image_generation.size_selection import resolve_size_choice
from .contracts import digest


FLAG="IT_TEM_BP18_BETA_TYPOGRAPHY_ENABLED"
PREFIX="BP18_BETA_EDITORIAL_"
VERSION="bp18-beta-editorial-v1"
# Existing audited Pretendard 1.3.9 artifacts. A private server copy must have
# exactly the same bytes; no filename, font-family string, or env claim suffices.
FONT_SHA="3090ccde0442bb347aa7685d9ba8b17436a60682df6e8f92a9a670de14056e22"
LICENSE_SHA="b04538c9abec39a3db75108cf0af0fd9c77032fe8aa2cf38345b4d250e98e38e"
LAYOUT_SHA={
    "3:4":"9c35cf392140e4a48ff6aa239289a77d091e10a0629411c2d726be833d28d183",
    "4:5":"fe13fe67c1df1efe2699c06309f844ba0dcaaede9b2ceb262e2f76d04dccef13",
    "9:16":"4ae2629474d741b5212fe56de762c47f18f8005c01918db61bfcae04bb5a15ee",
}
DESIGN={"schema":VERSION,"typography":"display-typography-v1","direction":"editorial",
        "copy_policy":"APPROVED_COPY_ONCE_SERVER_COMPOSITION","cta":"IMAGE_REQUIRED",
        "product_protection":"OWNER_TARGET_NOT_MEASURED_OBJECT_BOUNDS",
        "human_visual_acceptance":"PENDING","commercial_acceptance":"PENDING"}


def is_enabled():
    return os.environ.get(FLAG)=="YES"


def _private_configured_bytes(name,limit):
    raw=os.environ.get(name,"")
    try:
        path=Path(raw)
        if not raw or not path.is_absolute() or path.is_symlink():
            raise ValueError
        descriptor=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
        with os.fdopen(descriptor,"rb") as stream:
            info=os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or not 0<info.st_size<=limit
                    or info.st_mode & 0o022 or info.st_uid not in (0,os.geteuid())):
                raise ValueError
            value=stream.read(limit+1)
        if len(value)!=info.st_size:
            raise ValueError
        return value
    except (OSError,ValueError):
        raise ValueError("BETA_TYPOGRAPHY_PRIVATE_FONT_CONFIG_REQUIRED") from None


def _font_evidence():
    data=_private_configured_bytes("IT_TEM_DERIVED_FONT",64*1024*1024)
    license_data=_private_configured_bytes("IT_TEM_DERIVED_FONT_LICENSE",128*1024)
    if sha256(data).hexdigest()!=FONT_SHA or sha256(license_data).hexdigest()!=LICENSE_SHA:
        raise ValueError("BETA_TYPOGRAPHY_FONT_OR_LICENSE_CHANGED")
    try:
        with TTFont(BytesIO(data)) as face:
            families={value.toUnicode() for value in face["name"].names if value.nameID in (1,16)}
            axes=[{"tag":axis.axisTag,"min":axis.minValue,"default":axis.defaultValue,"max":axis.maxValue}
                  for axis in face["fvar"].axes] if "fvar" in face else []
            weight=next((axis for axis in axes if axis["tag"]=="wght"),None)
            if ("Pretendard Variable" not in families or weight is None
                    or not weight["min"]<=510<=730<=770<=weight["max"]):
                raise ValueError
            cmap=face.getBestCmap() or {}
            if any(ord(char) not in cmap for char in "한글광고가나다0123456789"):
                raise ValueError
        text=license_data.decode("utf-8")
        if "SIL OPEN FONT LICENSE Version 1.1" not in text or "Reserved Font Name Pretendard" not in text:
            raise ValueError
    except (KeyError,ValueError,TypeError,UnicodeError):
        raise ValueError("BETA_TYPOGRAPHY_VARIABLE_FONT_REQUIRED") from None
    return {"schema":"bp18-beta-font-evidence-v1","source":"pretendard@1.3.9",
            "font_sha256":FONT_SHA,"font_license_sha256":LICENSE_SHA,
            "family":"Pretendard Variable","variable_axes":axes,"license":"OFL-1.1",
            "human_font_acceptance":"PENDING"}


def _layout(choice,profile):
    value=professional_layout({},profile.final).model_dump(mode="json")
    # Freeze the Owner product TARGET, not a claim of measured object bounds.
    value["protected_regions"]=[dict(zip(("left","top","right","bottom"),profile.normalized(profile.product)))]
    # The model prompt already reserves these exact regions at each contract
    # version. Reuse display styling without changing that generation geometry.
    boxes=(dict(profile.text) if choice=="3:4" else
           {"headline":(86,81,994,231),"subline":(86,247,994,410),"cta":(306,1195,774,1278)} if choice=="4:5" else
           {"headline":(86,288,610,550),"subline":(86,580,610,830),"cta":(86,900,610,1040)})
    for name,box in boxes.items():
        value["text_regions"][name].update(dict(zip(("left","top","right","bottom"),profile.normalized(box))))
    value["canvas_size"]=tuple(value["canvas_size"])
    layout=CompositionLayout.model_validate(value,strict=True).model_dump(mode="json")
    if digest(layout)!=LAYOUT_SHA[choice]:
        raise ValueError("BETA_TYPOGRAPHY_LAYOUT_VERSION_DRIFT")
    return layout


def _policy(choice,cta_policy_sha):
    selected,profile=resolve_size_choice(choice)
    selection=selected.model_dump(mode="json")
    if choice=="4:5":selection["version"]=BP18_V3_LAYOUT_VERSION
    elif choice=="9:16":
        if not isinstance(cta_policy_sha,str) or not re.fullmatch(r"[0-9a-f]{64}",cta_policy_sha):
            raise ValueError("BETA_TYPOGRAPHY_9_16_CTA_POLICY_REQUIRED")
        selection["version"]=BP18_DUAL_IMAGE_CTA_VERSION
    elif cta_policy_sha is not None:
        raise ValueError("BETA_TYPOGRAPHY_UNEXPECTED_CTA_POLICY")
    if choice=="4:5" and cta_policy_sha is not None:
        raise ValueError("BETA_TYPOGRAPHY_UNEXPECTED_CTA_POLICY")
    evidence=_font_evidence()
    zone={"size":choice,"layout_selection":selection,"native_size":list(profile.native),
          "final_size":list(profile.final),"design_profile_sha":digest(DESIGN),
          "required_font_sha":FONT_SHA,"font_license_sha":LICENSE_SHA,"font_policy_sha":digest(evidence),
          "font_evidence":evidence,"human_visual_acceptance":"PENDING","mode":"BETA_EDITORIAL_DESIGN_INTENT"}
    if choice=="9:16":zone["cta_policy_sha"]=cta_policy_sha
    return {"profile_id":PREFIX+choice.replace(":","_"),"profile_version":VERSION,
            "safe_zone":zone,"layout":_layout(choice,profile)}


def build_policy(choice,cta_policy_sha=None):
    """Select only at new-Job ingress under the explicit beta feature flag."""
    if not is_enabled():raise ValueError("BETA_TYPOGRAPHY_DISABLED")
    return _policy(choice,cta_policy_sha)


def verify_profile(row,zone,layout):
    """Validate frozen beta authority independently of today's feature flag."""
    try:
        if not isinstance(zone,dict):raise ValueError
        expected=_policy(zone.get("size"),zone.get("cta_policy_sha"))
        if (row["profile_id"]!=expected["profile_id"] or row["profile_version"]!=VERSION
                or zone!=expected["safe_zone"] or layout!=expected["layout"]):
            raise ValueError
    except (KeyError,TypeError,ValueError):
        raise ValueError("BETA_TYPOGRAPHY_PROFILE_INVALID") from None
    return True
