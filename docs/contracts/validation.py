"""Reference contract validator for synthetic v0.5 review payloads.

This module is NOT a FastAPI approval gate and cannot authorize a provider call.
Offsets are Python Unicode code-point indices into the COMPLETE COPY FIELD.
Provisional hashtags policy: text is ' '.join(hashtags), subject to owner agreement.
"""
from __future__ import annotations

from hashlib import sha256
import json
from dataclasses import dataclass
from secrets import token_hex
from threading import RLock


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

    Optional revision/hash comparisons are legacy fixture-consistency checks
    ONLY; caller-provided hashes cannot prove the report's review origin.
    Only ReferenceReviewLedger.approve may decide a reference approval, using
    a server-pinned snapshot and server-owned review record.
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
        if field == "hashtags":
            # v0.5 supplies field+start/end but no hashtag index. Our proposed
            # join representation must never highlight across two list items.
            cursor = 0
            within_one_item = False
            for tag in copy_output["hashtags"]:
                if cursor <= start < end <= cursor + len(tag):
                    within_one_item = True
                    break
                cursor += len(tag) + 1
            if not within_one_item:
                raise ContractViolation("HASHTAG_CROSS_ITEM")
        if issue.get("risk_level") not in {"정상", "근거 확인 필요", "위반 의심"}:
            raise ContractViolation("INVALID_RISK_LEVEL")
        suspected |= issue["risk_level"] == "위반 의심"
    if report["passed"] == suspected:
        raise ContractViolation("PASSED_RISK_CONTRADICTION")
    if not isinstance(report.get("revised_fields"), dict) or not isinstance(report.get("checklist"), list):
        raise ContractViolation("INVALID_REVIEW_STRUCTURE")
    return report["passed"]


# Reference review scope v0 is PROVISIONAL until the Text owner confirms the
# precise fields supplied to the compliance model/rules. All fields supplied to
# that review MUST be captured; omitted context invalidates any Live gate claim.
REVIEW_INPUT_PROFILE = "it-tem-compliance-review-input-v0-proposed"
REQUIRED_CONTEXT = frozenset({
    "product_name", "user_text", "product_facts", "source_schema_version",
    "additional_review_inputs",
})


def canonical_review_input_hash(*, job_id: str, copy_revision: str,
                                copy_output: dict, review_context: dict,
                                model_version: str, rules_version: str) -> str:
    """Digest the exact, versioned *proposed* review input; NOT copy_sha256.

    The canonicalization profile is UTF-8 JSON with sorted keys, no whitespace,
    no Unicode normalization, ensure_ascii=False, allow_nan=False; JSON object
    keys must be strings, and numbers (if any) must be safe integers. Python
    and TypeScript implementations require cross-language golden-vector tests
    before a real HTTP freeze; the owner must confirm the review input scope.
    """
    if not isinstance(review_context, dict) or set(review_context) != REQUIRED_CONTEXT:
        raise ContractViolation("INCOMPLETE_REVIEW_CONTEXT")
    if not isinstance(review_context["product_name"], str) or not review_context["product_name"]:
        raise ContractViolation("INVALID_PRODUCT_NAME")
    if review_context["user_text"] is not None and not isinstance(review_context["user_text"], str):
        raise ContractViolation("INVALID_USER_TEXT")
    if not isinstance(review_context["product_facts"], dict) or not isinstance(
        review_context["additional_review_inputs"], dict
    ):
        raise ContractViolation("INVALID_REVIEW_FACTS")
    if not all(isinstance(x, str) and x for x in (
        job_id, copy_revision, model_version, rules_version,
        review_context["source_schema_version"],
    )):
        raise ContractViolation("INVALID_REVIEW_VERSION")
    content = {
        "profile": REVIEW_INPUT_PROFILE,
        "job_id": job_id,
        "copy_revision": copy_revision,
        "copy_output": copy_output,
        "review_context": review_context,
        "model_version": model_version,
        "rules_version": rules_version,
    }
    return _sha_of_json(content)


def _canonical_json(data: object) -> str:
    """Restricted deterministic JSON for this reference contract."""
    def check(value):
        if value is None or type(value) in (str, bool):
            return
        if type(value) is int and -(2**53 - 1) <= value <= (2**53 - 1):
            return
        if isinstance(value, list):
            for v in value:
                check(v)
            return
        if isinstance(value, dict) and all(type(k) is str for k in value):
            for v in value.values():
                check(v)
            return
        raise ContractViolation("UNSUPPORTED_CANONICAL_JSON_TYPE")
    check(data)
    try:
        raw = json.dumps(data, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"), allow_nan=False)
        raw.encode("utf-8")  # no lone Unicode surrogate
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ContractViolation("INVALID_CANONICAL_JSON") from exc
    return raw


def _sha_of_json(data: object) -> str:
    return sha256(_canonical_json(data).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class StoredReview:
    """Immutable value written by trusted serving review-completion code."""
    review_record_id: str
    job_id: str
    copy_revision: str
    copy_sha256: str
    review_input_sha256: str
    reviewed_job_generation: int
    report_sha256: str
    reviewed_snapshot_json: str
    report_json: str
    source_review_token: str  # internal begin->complete linkage, not a browser credential
    model_version: str
    rules_version: str


class ReferenceReviewLedger:
    """IN-MEMORY reference only. NOT durable/authenticated/multi-worker safe.

    stage_job/begin_review/complete_review are TRUSTED SERVING methods. Browser
    clients can only submit job/record IDs, expected revision/hash and approval
    intent; they never supply review reports, trusted hashes, or the ledger.
    """
    def __init__(self):
        self._lock = RLock()
        self._jobs: dict[str, dict] = {}
        self._pending: dict[str, dict] = {}
        self._records: dict[str, StoredReview] = {}
        self._completed_runs: dict[str, tuple[str, str, int]] = {}

    def stage_job(self, *, job_id: str, copy_revision: str, copy_output: dict,
                  review_context: dict) -> None:
        """Trusted server persists immutable copy/review inputs before review."""
        if not job_id or not copy_revision:
            raise ContractViolation("MISSING_JOB_REVISION")
        # Validate completeness even when no reviewer run has begun yet.
        canonical_review_input_hash(
            job_id=job_id, copy_revision=copy_revision,
            copy_output=copy_output, review_context=review_context,
            model_version="preflight", rules_version="preflight",
        )
        payload = {
            "job_id": job_id,
            "copy_revision": copy_revision,
            "copy_output": copy_output,
            "review_context": review_context,
        }
        serialized = _canonical_json(payload)
        with self._lock:
            old = self._jobs.get(job_id)
            if old:
                if old["approved_record_id"] is not None:
                    raise ContractViolation("ALREADY_APPROVED")
                if old["payload"]["copy_revision"] == copy_revision and (
                    canonical_copy_hash(old["payload"]["copy_output"]) != canonical_copy_hash(copy_output)
                ):
                    raise ContractViolation("CONFLICTING_COPY_REVISION")
                if old["serialized"] == serialized:
                    return
            self._jobs[job_id] = {
                "payload": json.loads(serialized), "serialized": serialized,
                "generation": (old["generation"] + 1 if old else 1),
                "approved_record_id": None,
            }

    def begin_review(self, job_id: str, *, model_version: str,
                     rules_version: str) -> tuple[str, dict]:
        """Server starts a real review against a server-pinned input snapshot."""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                raise ContractViolation("MISSING_JOB")
            snapshot = json.loads(job["serialized"])
            review_sha = canonical_review_input_hash(
                **snapshot, model_version=model_version, rules_version=rules_version,
            )
            token = token_hex(16)
            self._pending[token] = {
                "snapshot": snapshot,
                "generation": job["generation"],
                "review_sha256": review_sha,
                "model_version": model_version,
                "rules_version": rules_version,
            }
            return token, json.loads(job["serialized"])

    def complete_review(self, review_token: str, report: dict) -> str:
        """Server accepts a result ONLY from its trusted reviewer invocation.

        The caller must be the backend's own reviewer completion handler, NOT an
        HTTP endpoint exposed to a user. The token is merely a correlation ID;
        it is not authentication/attestation of OpenAI or the reviewer.
        """
        with self._lock:
            pending = self._pending.pop(review_token, None)
            if pending is None:
                raise ContractViolation("UNTRUSTED_REVIEW_COMPLETION")
            snap = pending["snapshot"]
            job = self._jobs.get(snap["job_id"])
            if not job or job["generation"] != pending["generation"]:
                raise ContractViolation("REVIEW_INPUT_CHANGED_DURING_REVIEW")
            if job["serialized"] != _canonical_json(snap):
                raise ContractViolation("REVIEW_INPUT_CHANGED_DURING_REVIEW")
            validate_compliance(
                snap["copy_output"], report,
                product_name=snap["review_context"]["product_name"],
                user_text=snap["review_context"]["user_text"],
            )
            report_json = _canonical_json(report)
            record_id = token_hex(16)
            self._records[record_id] = StoredReview(
                review_record_id=record_id,
                job_id=snap["job_id"],
                copy_revision=snap["copy_revision"],
                copy_sha256=canonical_copy_hash(snap["copy_output"]),
                review_input_sha256=pending["review_sha256"],
                reviewed_job_generation=pending["generation"],
                report_sha256=sha256(report_json.encode("utf-8")).hexdigest(),
                reviewed_snapshot_json=_canonical_json(snap),
                report_json=report_json,
                source_review_token=review_token,
                model_version=pending["model_version"],
                rules_version=pending["rules_version"],
            )
            self._completed_runs[review_token] = (
                record_id, pending["review_sha256"], pending["generation"],
            )
            return record_id

    def approve(self, *, job_id: str, review_record_id: str,
                requested_copy_revision: str, requested_copy_sha256: str) -> bool:
        """Simulated one-lock compare-and-set over trusted snapshot + review."""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                raise ContractViolation("MISSING_JOB")
            if job["approved_record_id"] is not None:
                raise ContractViolation("ALREADY_APPROVED")
            rec = self._records.get(review_record_id)
            if rec is None:
                raise ContractViolation("MISSING_TRUSTED_REVIEW_RECORD")
            if rec.job_id != job_id:
                raise ContractViolation("REVIEW_JOB_MISMATCH")
            # Reject records inserted/copied without a completed server-run ledger entry.
            if self._completed_runs.get(rec.source_review_token) != (
                rec.review_record_id, rec.review_input_sha256,
                rec.reviewed_job_generation,
            ) or rec.review_record_id != review_record_id:
                raise ContractViolation("UNTRUSTED_REVIEW_PROVENANCE")
            current = job["payload"]
            if current["copy_revision"] != requested_copy_revision or (
                canonical_copy_hash(current["copy_output"]) != requested_copy_sha256
            ):
                raise ContractViolation("CLIENT_COPY_MISMATCH")
            if rec.copy_revision != current["copy_revision"] or (
                rec.copy_sha256 != canonical_copy_hash(current["copy_output"])
            ):
                raise ContractViolation("STALE_REVIEW_COPY")
            if rec.reviewed_snapshot_json != job["serialized"]:
                raise ContractViolation("STALE_REVIEW_CONTEXT")
            current_review_sha = canonical_review_input_hash(
                **current, model_version=rec.model_version, rules_version=rec.rules_version
            )
            if current_review_sha != rec.review_input_sha256:
                raise ContractViolation("STALE_REVIEW_CONTEXT")
            # Snapshot equality alone does not prove no intervening changes:
            # v1 -> v2 -> v1 must invalidate the review from the first v1.
            if rec.reviewed_job_generation != job["generation"]:
                raise ContractViolation("STALE_REVIEW_GENERATION")
            if sha256(rec.report_json.encode("utf-8")).hexdigest() != rec.report_sha256:
                raise ContractViolation("REVIEW_REPORT_TAMPERED")
            report = json.loads(rec.report_json)
            reviewed = json.loads(rec.reviewed_snapshot_json)
            verified = validate_compliance(
                reviewed["copy_output"], report,
                product_name=reviewed["review_context"]["product_name"],
                user_text=reviewed["review_context"]["user_text"],
            )
            if not verified:
                raise ContractViolation("COMPLIANCE_BLOCKED")
            # In the production JobStore, this must be a durable, atomic,
            # access-controlled transaction with expected Job state/version.
            job["approved_record_id"] = review_record_id
            return True


def approval_allowed(ledger: ReferenceReviewLedger, *, job_id: str,
                     review_record_id: str, requested_copy_revision: str,
                     requested_copy_sha256: str) -> bool:
    """Reference in-memory approval; old caller-provided report/hash API removed.

    Browser-provided hashes only perform a preliminary match against SERVER
    state. This reference deliberately refuses to run without a stored review.
    Real auth, JobStore persistence, 409 response and recovery are NOT built.
    """
    if not isinstance(ledger, ReferenceReviewLedger):
        raise ContractViolation("UNTRUSTED_REVIEW_STORE")
    return ledger.approve(
        job_id=job_id, review_record_id=review_record_id,
        requested_copy_revision=requested_copy_revision,
        requested_copy_sha256=requested_copy_sha256,
    )
