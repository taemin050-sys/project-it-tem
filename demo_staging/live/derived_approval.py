"""Server-owned derived-render authority bound to the existing Copy/F09 state.

The configured business-role policy is separate from Tailnet authentication.
No actor, role, timestamp or expected content hash supplied by a client grants
access. All callers use the same live SQLite transaction for their CAS checks.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat

from .contracts import LiveGateError, digest
from .review_policy import enabled as policy_enabled


SCOPES = frozenset({"admit", "render", "review", "finalize", "select", "read"})
ACTOR = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
JOB = re.compile(r"^[0-9a-f]{32}$")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise LiveGateError("DERIVED_POLICY_DUPLICATE_FIELD")
        result[key] = value
    return result


class DerivedAuthority:
    """Read a protected, explicitly installed role/delegation policy each time."""

    def __init__(self, policy_file: Path):
        self.policy_file = Path(policy_file)

    def policy(self):
        try:
            descriptor = os.open(self.policy_file, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(descriptor, "rb") as stream:
                info = os.fstat(stream.fileno())
                if (not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077
                        or info.st_size > 256 * 1024 or info.st_uid not in (0, os.geteuid())):
                    raise ValueError
                policy = json.loads(stream.read(), object_pairs_hook=_unique_object)
            if (set(policy) != {"schema", "revision", "business_roles", "delegations"}
                    or policy["schema"] != "bp18-derived-authority-v1"
                    or type(policy["revision"]) is not int or policy["revision"] < 1
                    or not isinstance(policy["business_roles"], dict)
                    or not isinstance(policy["delegations"], list)):
                raise ValueError
            for actor, role in policy["business_roles"].items():
                if not ACTOR.fullmatch(actor) or role not in ("owner", "pm"):
                    raise ValueError
            for grant in policy["delegations"]:
                if (not isinstance(grant, dict) or set(grant) != {"actor", "owner_actor", "job_id", "scopes"}
                        or not ACTOR.fullmatch(grant["actor"])
                        or not ACTOR.fullmatch(grant["owner_actor"])
                        or not JOB.fullmatch(grant["job_id"])
                        or not isinstance(grant["scopes"], list) or not grant["scopes"]
                        or len(set(grant["scopes"])) != len(grant["scopes"])
                        or not set(grant["scopes"]) <= SCOPES):
                    raise ValueError
            return policy
        except (OSError, ValueError, TypeError, KeyError, UnicodeError):
            raise LiveGateError("DERIVED_AUTHORITY_POLICY_UNAVAILABLE") from None

    def authorize(self, actor, auth_role, owner_actor, job_id, scope):
        if (not isinstance(actor, str) or not ACTOR.fullmatch(actor)
                or auth_role not in ("admin", "evaluator") or scope not in SCOPES):
            raise LiveGateError("DERIVED_REVIEWER_FORBIDDEN")
        policy = self.policy()
        if actor != owner_actor:
            allowed = any(grant["actor"] == actor and grant["owner_actor"] == owner_actor
                          and grant["job_id"] == job_id and scope in grant["scopes"]
                          for grant in policy["delegations"])
            if not allowed:
                raise LiveGateError("DERIVED_JOB_NOT_FOUND")
        business_role = policy["business_roles"].get(actor)
        if scope in ("admit", "review", "finalize", "select") and business_role not in ("owner", "pm"):
            raise LiveGateError("DERIVED_BUSINESS_ROLE_REQUIRED")
        return {"reviewer_actor": actor, "reviewer_role": auth_role,
                "business_role": business_role, "authority_policy_sha": digest(policy),
                "authority_revision": policy["revision"]}


def current_derived_context(state, connection, owner_actor, job_id):
    """Validate the current real approval chain under the caller's DB lock."""
    job = state._read(connection, job_id, owner_actor)
    state._approved(job, connection, allow_completed=True)
    if not job["image_sha"] or not job["prompt_json"]:
        raise LiveGateError("DERIVED_RAW_CANDIDATE_REQUIRED")
    policy = state._ensure_current_review_policy(connection, job) if policy_enabled() else None
    if job["mode"] == "LIVE":
        attempt = state._live_dual_candidate(connection, job)
        group = state._live_dual_row(connection, owner_actor, job_id)
        parent = state._read(connection, group["parent_job_id"], owner_actor) if group else job
        f09 = state._live_dual_f09_proof(parent)
        candidate_receipt_sha = attempt["candidate_receipt_sha"]
        provider_attempt_id = attempt["provider_attempt_id"]
    else:
        # A fixture must stay explicitly labeled throughout review and export.
        f09 = {"scope": "OFFLINE_FIXTURE", "review_sha": job["review_sha"]}
        candidate_receipt_sha = None
        provider_attempt_id = None
        parent = job
    value = {"schema": "bp18-derived-live-context-v1", "owner_actor": owner_actor,
             "job_id": job_id, "mode": job["mode"], "generation": job["generation"],
             "source_upload_job_id": parent["job_id"], "source_input_sha": parent["input_sha"],
             "input_sha": job["input_sha"], "copy_sha": job["copy_sha"],
             "copy_approval_sha": job["approval_sha"], "f09_review_sha": job["review_sha"],
             "f09": f09, "policy": policy, "raw_candidate_sha": job["image_sha"],
             "owner_candidate_receipt_sha": candidate_receipt_sha,
             "provider_attempt_id": provider_attempt_id,
             "generation_mode": json.loads(job["input_json"]).get("generation_mode", "composed"),
             "image_size": json.loads(job["input_json"]).get("image_size", "4:5")}
    return job, value, digest(value)


def require_same_context(actual_sha, expected_sha):
    if actual_sha != expected_sha:
        raise LiveGateError("DERIVED_CONTEXT_STALE")
