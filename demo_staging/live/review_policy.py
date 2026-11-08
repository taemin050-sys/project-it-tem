"""BP18 B-only F11/S03 review policy identity. Never updates old Jobs on import.

Version and SHA must both match. Content fingerprint covers all effective
Serving + Text Owner rule-code sources. No external requests, credentials
or mutable database operations are performed when computing identity.
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from .contracts import LiveGateError, digest

DEFAULT_VERSION = "bp18-f11-compliance-policy-v1"
SOURCES = (
    "demo_staging/live/contracts.py",
    "src/text_generation/compliance/rule_checker.py",
    "src/text_generation/compliance/report_builder.py",
    "src/text_generation/compliance/rules.yaml",
)

def enabled() -> bool:
    return os.environ.get("IT_TEM_BP18_F11_ENABLED") == "YES"

def current() -> dict:
    version = os.environ.get("IT_TEM_BP18_REVIEW_POLICY_ID", DEFAULT_VERSION)
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{3,99}", version):
        raise LiveGateError("REVIEW_POLICY_ID_INVALID")
    root = Path(__file__).resolve().parents[2]
    files = {}
    for rel in SOURCES:
        target = root / rel
        if not target.is_file() or target.is_symlink():
            raise LiveGateError("REVIEW_POLICY_FILE_MISSING")
        files[rel] = hashlib.sha256(target.read_bytes()).hexdigest()
    return {"version":version,"sha":digest({
        "version":version,"rule_source_hashes":files,
        "contract":"BP18_REVIEW_POLICY_SHA_V1"
    })}

def review_digest(input_sha, analysis, copy, report, generation, policy=None):
    record = {"input_sha":input_sha,"analysis":analysis,
              "copy":copy,"report":report,"generation":generation}
    if policy is not None:
        record["review_policy_version"] = policy["version"]
        record["review_policy_sha"] = policy["sha"]
    return digest(record)
