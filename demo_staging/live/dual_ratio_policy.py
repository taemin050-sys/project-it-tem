"""Explicit, owner-controlled admission for new Live Dual ratio contracts."""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat

from .contracts import LiveGateError, digest

MULTI_RATIO_FLAG="IT_TEM_BP18_LIVE_DUAL_MULTI_RATIO_ENABLED"
CTA_POLICY_ENV="IT_TEM_BP18_9_16_CTA_POLICY"
CTA_POLICY_ID="BP18_DUAL_9_16_IMAGE_CTA_V1"


def image_cta_policy():
    """Read a private registered decision, never infer one from a client flag."""
    raw=os.environ.get(CTA_POLICY_ENV,"")
    try:
        path=Path(raw)
        if not raw or not path.is_absolute() or path.is_symlink():
            raise ValueError
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
        with os.fdopen(fd,"rb") as stream:
            info=os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid() or
                    stat.S_IMODE(info.st_mode)!=0o600 or info.st_size>8192):
                raise ValueError
            def unique(pairs):
                obj={}
                for key,value in pairs:
                    if key in obj: raise ValueError
                    obj[key]=value
                return obj
            value=json.loads(stream.read(8193),object_pairs_hook=unique)
        if (type(value) is not dict or set(value)!={"version","policy_id","aspect_ratio",
                "composed_cta","freeform_cta","approved_by","approval_reference"} or
            type(value["version"]) is not int or value["version"]!=1 or
            value["policy_id"]!=CTA_POLICY_ID or value["aspect_ratio"]!="9:16" or
            value["composed_cta"]!="image" or value["freeform_cta"]!="image" or
            value["approved_by"] not in {"OWNER","PM","USER"} or
            type(value["approval_reference"]) is not str or
            not 1<=len(value["approval_reference"])<=500):
            raise ValueError
        return value
    except (OSError,ValueError,TypeError):
        raise LiveGateError("LIVE_DUAL_9_16_CTA_HOLD") from None


def ratio_admission(image_size):
    if image_size not in {"3:4","4:5","9:16"}:
        raise LiveGateError("LIVE_DUAL_RATIO_INVALID")
    if image_size=="4:5":
        return None
    # Check the explicit CTA decision first to retain the historical HOLD code.
    policy=image_cta_policy() if image_size=="9:16" else None
    if os.environ.get(MULTI_RATIO_FLAG)!="YES":
        raise LiveGateError("LIVE_DUAL_MULTI_RATIO_DISABLED")
    return digest(policy) if policy is not None else None
