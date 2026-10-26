"""Reference contract validator for synthetic v0.5 review payloads.

This module is NOT a FastAPI approval gate and cannot authorize a provider call.
Offsets are Python Unicode code-point indices into the COMPLETE COPY FIELD.
Provisional hashtags policy: text is ' '.join(hashtags), subject to owner agreement.
"""
from __future__ import annotations

from hashlib import sha256
import json


COPY_FIELDS = frozenset({"product_name", "headline", "subline", "cta", "caption",
                         "hashtags", "user_text"})


class ContractViolation(ValueError):
    """A source-documented schema/revision/offset invariant was violated."""


def copy_fields(copy_output: dict, *, product_name: str, user_text: str | None = None) -> dict:
    if not isinstance(copy_output, dict) or not isinstance(copy_output.get("ad_copy"), dict):
        raise ContractViolation("INVALID_COPY")
    copy_set = copy_output["ad_copy"]
    values = {name: copy_set.get(name) for name in ("headline", "subline", "cta")}
    values["caption"] = copy_output.get("caption")
    values["product_name"] = product_name
    tags = copy_output.get("hashtags")
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
        raise ContractViolation("INVALID_HASHTAGS")
    values["hashtags"] = " ".join(tags)
    if user_text is not None:
        values["user_text"] = user_text
    if any(not isinstance(item, str) for item in values.values()):
        raise ContractViolation("INVALID_COPY_FIELD")
    return values


def canonical_copy_hash(copy_output: dict) -> str:
    """Deterministic proposed digest, computed on canonical JSON of full AdCopyOutput.

    Approval revision and this hash belong to a *serving sidecar*; the text
    owner's v0.5 models do NOT currently contain approval revision/hash fields.
    """
    if not isinstance(copy_output, dict):
        raise ContractViolation("INVALID_COPY")
    payload = json.dumps(copy_output, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"), allow_nan=False)
    return sha256(payload.encode("utf-8")).hexdigest()


def validate_compliance(
    copy_output: dict, report: dict, *, product_name: str, user_text: str | None = None,
    copy_revision: str | None = None, reviewed_revision: str | None = None,
    reviewed_copy_sha256: str | None = None,
) -> bool:
    """Validate report shape and offsets against the *full original text*.

    If supplied, revision/hash must match exact reviewed copy. For approval a
    service MUST supply and verify all three sidecar fields, plus check passed.
    Missing sidecar arguments here only supports synthetic fixture structure tests.
    """
    fields = copy_fields(copy_output, product_name=product_name, user_text=user_text)
    if not isinstance(report, dict) or not isinstance(report.get("issues"), list):
        raise ContractViolation("MISSING_COMPLIANCE")
    if not isinstance(report.get("passed"), bool):
        raise ContractViolation("INVALID_PASSED")
    if any(v is not None for v in (copy_revision, reviewed_revision, reviewed_copy_sha256)):
        if not (copy_revision and reviewed_revision and reviewed_copy_sha256):
            raise ContractViolation("MISSING_REVIEW_SIDECAR")
        if copy_revision != reviewed_revision:
            raise ContractViolation("STALE_REVIEW_REVISION")
        if canonical_copy_hash(copy_output) != reviewed_copy_sha256:
            raise ContractViolation("STALE_REVIEW_HASH")

    suspected = False
    for issue in report["issues"]:
        if not isinstance(issue, dict) or not issue.get("text"):
            raise ContractViolation("INVALID_ISSUE")
        field = issue.get("field")
        if field not in COPY_FIELDS or field not in fields:
            raise ContractViolation("UNRESOLVED_COPY_FIELD")
        actual = fields[field]
        start, end = issue.get("start"), issue.get("end")
        # bool is a subclass of int, so reject it explicitly.
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(actual):
            raise ContractViolation("INVALID_OFFSET")
        if actual[start:end] != issue["text"]:
            raise ContractViolation("OFFSET_TEXT_MISMATCH")
        if issue.get("risk_level") not in {"정상", "근거 확인 필요", "위반 의심"}:
            raise ContractViolation("INVALID_RISK_LEVEL")
        suspected |= issue["risk_level"] == "위반 의심"
    if report["passed"] == suspected:
        raise ContractViolation("PASSED_RISK_CONTRADICTION")
    if not isinstance(report.get("revised_fields"), dict) or not isinstance(report.get("checklist"), list):
        raise ContractViolation("INVALID_REVIEW_STRUCTURE")
    return report["passed"]


def approval_allowed(copy_output: dict, report: dict | None, *, product_name: str,
                     copy_revision: str | None, reviewed_revision: str | None,
                     reviewed_copy_sha256: str | None) -> bool:
    """Reference *policy* check only: server must enforce before real approval.

    Disallows missing or stale review, changed copy after auto-fix, suspected
    violations and missing immutable revision/hash sidecar.
    """
    if report is None:
        raise ContractViolation("MISSING_COMPLIANCE")
    if not copy_revision or not reviewed_revision or not reviewed_copy_sha256:
        raise ContractViolation("MISSING_REVIEW_SIDECAR")
    is_pass = validate_compliance(
        copy_output, report, product_name=product_name, copy_revision=copy_revision,
        reviewed_revision=reviewed_revision, reviewed_copy_sha256=reviewed_copy_sha256)
    if not is_pass:
        raise ContractViolation("COMPLIANCE_BLOCKED")
    return True
