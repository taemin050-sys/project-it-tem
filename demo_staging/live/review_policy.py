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
LLM_VERSION = "bp18-f09-two-stage-policy-v2"
SOURCES = (
    "demo_staging/live/contracts.py",
    "src/text_generation/compliance/rule_checker.py",
    "src/text_generation/compliance/report_builder.py",
    "src/text_generation/compliance/rules.yaml",
)

def llm_required(mode: str) -> bool:
    return mode == "LIVE" and os.environ.get("IT_TEM_BP18_F09_REQUIRED") == "YES"


def _source_paths():
    if llm_required("LIVE"):
        return SOURCES + ("demo_staging/live/copy_review.py", "src/text_generation/schemas.py")
    return SOURCES


def sources_fingerprint() -> str:
    """Boot-pinned rules and policy-code content. Runtime file swaps fail closed."""
    root=Path(__file__).resolve().parents[2]
    hashes={}
    for rel in _source_paths():
        target=root/rel
        if not target.is_file() or target.is_symlink():
            raise LiveGateError("REVIEW_POLICY_FILE_MISSING")
        hashes[rel]=hashlib.sha256(target.read_bytes()).hexdigest()
    return digest(hashes)


def enabled() -> bool:
    return os.environ.get("IT_TEM_BP18_F11_ENABLED") == "YES"

def current() -> dict:
    two_stage = llm_required("LIVE")
    version = os.environ.get("IT_TEM_BP18_REVIEW_POLICY_ID", LLM_VERSION if two_stage else DEFAULT_VERSION)
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{3,99}", version):
        raise LiveGateError("REVIEW_POLICY_ID_INVALID")
    root = Path(__file__).resolve().parents[2]
    files = {}
    for rel in _source_paths():
        target = root / rel
        if not target.is_file() or target.is_symlink():
            raise LiveGateError("REVIEW_POLICY_FILE_MISSING")
        files[rel] = hashlib.sha256(target.read_bytes()).hexdigest()
    identity = {
        "version":version,"rule_source_hashes":files,
        "contract":"BP18_REVIEW_POLICY_SHA_V1"
    }
    if two_stage:
        identity.update(
            contract="BP18_REVIEW_POLICY_SHA_V2",
            llm_model=os.environ.get("IT_TEM_TEXT_MODEL", "gpt-6-luna"),
        )
    return {"version": version, "sha": digest(identity)}

def review_digest(input_sha, analysis, copy, report, generation, policy=None):
    record = {"input_sha":input_sha,"analysis":analysis,
              "copy":copy,"report":report,"generation":generation}
    if policy is not None:
        record["review_policy_version"] = policy["version"]
        record["review_policy_sha"] = policy["sha"]
        if "epoch" in policy:
            record["review_policy_epoch"] = policy["epoch"]
    return digest(record)
