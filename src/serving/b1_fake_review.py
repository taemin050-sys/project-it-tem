"""B1-R opt-in, server-owned FAKE Compliance approval gate.

This is a single-process local prototype. The existing B0 app remains the
default; no provider calls, new HTTP endpoints, user-supplied review records,
authenticated actors, or multi-worker/process-safe claims.
"""
from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException

from docs.contracts.validation import (
    ContractViolation, _canonical_json, canonical_copy_hash,
    canonical_review_input_hash, validate_compliance,
)
from .job_store import JobStore, transition_job

_PROFILE = "b1-fake-mock-to-owner-copy-v0-unapproved"
_MODEL = "fake-compliance-no-provider"
_RULES = "fake-rule-v0"
_FILE = "b1_fake_review.json"


def _blocked(reason: str):
    raise HTTPException(status_code=409, detail={
        "error": "B1_FAKE_COMPLIANCE_BLOCKED", "reason": reason,
    })


def _sha(data: object) -> str:
    return sha256(_canonical_json(data).encode("utf-8")).hexdigest()


# Explicit persisted-file schema: reject malformed internal values *before*
# any approval code can call .encode(), .get(), index dictionaries or unpack
# arrays. Error output must never echo provider text, report JSON or secrets.
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_RECORD_ID_RE = re.compile(r"[0-9a-f]{32}\Z")
_ROOT_FIELDS = frozenset({
    "job_id", "copy_revision", "generation", "snapshot_json", "copy_sha256",
    "user_text", "product_facts", "extra", "pending", "records", "runs",
    "latest_record_id", "approved",
})
_RECORD_FIELDS = frozenset({
    "review_record_id", "source_review_token", "reviewed_job_generation",
    "review_input_sha256", "copy_sha256", "copy_revision", "report_sha256",
    "report_json", "reviewed_snapshot_json", "model_version", "rules_version",
})
_PENDING_FIELDS = frozenset({
    "token", "generation", "snapshot_json", "input_sha256",
})


def _valid_unicode_string(value: object) -> bool:
    if type(value) is not str:
        return False
    try:
        value.encode("utf-8")
        return True
    except UnicodeError:
        return False


def _nonempty_string(value: object) -> bool:
    return _valid_unicode_string(value) and bool(value)


def _valid_canonical_object(value: object) -> bool:
    if type(value) is not dict:
        return False
    try:
        _canonical_json(value)
        return True
    except (ContractViolation, ValueError, TypeError, UnicodeError):
        return False


def _token(value: object) -> bool:
    return type(value) is str and _RECORD_ID_RE.fullmatch(value) is not None


def _digest(value: object) -> bool:
    return type(value) is str and _SHA256_RE.fullmatch(value) is not None


def _generation(value: object) -> bool:
    return type(value) is int and value >= 1


def _json_object_string(value: object) -> bool:
    if type(value) is not str:
        return False
    try:
        # Exclude floats, non-string keys, out-of-range ints, lone surrogate
        # values and nonstandard NaN/Infinity within stored JSON objects.
        return _valid_canonical_object(json.loads(value))
    except (ValueError, TypeError, UnicodeError):
        return False


def _valid_review_record(key: object, rec: object) -> bool:
    if not _token(key) or type(rec) is not dict or set(rec) != _RECORD_FIELDS:
        return False
    return (
        rec["review_record_id"] == key
        and _token(rec["source_review_token"])
        and _generation(rec["reviewed_job_generation"])
        and _digest(rec["review_input_sha256"])
        and _digest(rec["copy_sha256"])
        and _nonempty_string(rec["copy_revision"])
        and _digest(rec["report_sha256"])
        and _json_object_string(rec["report_json"])
        and _json_object_string(rec["reviewed_snapshot_json"])
        and _nonempty_string(rec["model_version"])
        and _nonempty_string(rec["rules_version"])
    )


def _valid_review_state(value: object, job_id: str) -> bool:
    if type(value) is not dict or set(value) not in (_ROOT_FIELDS, _ROOT_FIELDS | {"dirty"}):
        return False
    if not (
        value["job_id"] == job_id
        and _nonempty_string(value["copy_revision"])
        and _generation(value["generation"])
        and _json_object_string(value["snapshot_json"])
        and _digest(value["copy_sha256"])
        and (value["user_text"] is None or _valid_unicode_string(value["user_text"]))
        and _valid_canonical_object(value["product_facts"])
        and _valid_canonical_object(value["extra"])
        and type(value["records"]) is dict
        and type(value["runs"]) is dict
        and (value["latest_record_id"] is None or _token(value["latest_record_id"]))
        and type(value["approved"]) is bool
        and ("dirty" not in value or type(value["dirty"]) is bool)
    ):
        return False
    pending = value["pending"]
    if pending is not None and (
        type(pending) is not dict
        or set(pending) != _PENDING_FIELDS
        or not _token(pending["token"])
        or not _generation(pending["generation"])
        or not _json_object_string(pending["snapshot_json"])
        or not _digest(pending["input_sha256"])
    ):
        return False
    if not all(_valid_review_record(key, rec) for key, rec in value["records"].items()):
        return False
    return all(
        _token(key)
        and type(run) is list
        and len(run) == 3
        and _token(run[0])
        and _digest(run[1])
        and _generation(run[2])
        for key, run in value["runs"].items()
    )


class FakeComplianceGate:
    """Trusted in-process testing interface; NOT an HTTP/Owner API.

    All stage / begin / complete / approve operations share the JobStore RLock.
    A separate review sidecar is published using write-fsync-os.replace.
    Approval uses the *same* lock and existing transition_job durable ledger.

    A real multi-process backend needs a transactional DB, actor ownership,
    durable provider attestation and signed Owner input scope instead.
    """

    def __init__(self, store: JobStore):
        self.store = store

    def _file(self, job_id: str) -> Path:
        return self.store._job_dir(job_id) / _FILE

    def _read(self, job_id: str) -> dict:
        try:
            path = self._file(job_id)
            if path.is_symlink():
                _blocked("INVALID_SERVER_REVIEW_RECORD")
            with path.open("r", encoding="utf-8") as f:
                value = json.load(f)
            if not _valid_review_state(value, job_id):
                _blocked("INVALID_SERVER_REVIEW_RECORD")
            return value
        except (FileNotFoundError, ValueError, TypeError, OSError):
            _blocked("MISSING_OR_INVALID_SERVER_REVIEW")

    def _write(self, job_id: str, state: dict) -> None:
        # Only the trusted server writes this file. The token/record are not
        # authentication and a local filesystem attacker is out of scope.
        dest = self._file(job_id)
        if dest.is_symlink():
            _blocked("INVALID_SERVER_REVIEW_RECORD")
        tmp = dest.parent / ("b1_fake_review." + uuid4().hex + ".tmp")
        try:
            with tmp.open("x", encoding="utf-8") as f:
                os.chmod(tmp, 0o600)
                json.dump(state, f, ensure_ascii=False, sort_keys=True, allow_nan=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, dest)
        finally:
            tmp.unlink(missing_ok=True)

    @staticmethod
    def _copy_output(job: dict) -> dict:
        # Explicit FAKE bridge: the B0 copy_candidate is NOT the Text Owner's
        # v0.7 AdCopyOutput; this synthetic shape is for security tests only.
        candidate = job.get("copy_candidate", {})
        if not isinstance(candidate, dict) or not isinstance(candidate.get("text"), str):
            _blocked("MISSING_SERVER_COPY")
        return {
            "ad_copy": {"headline": candidate["text"], "subline": "", "cta": ""},
            "caption": candidate["text"], "hashtags": [],
        }

    @staticmethod
    def _context(job: dict, *, user_text: str | None, product_facts: dict,
                 extra: dict) -> dict:
        plan = job.get("plan", {})
        if not isinstance(plan, dict) or not plan.get("product_name"):
            _blocked("MISSING_SERVER_PLAN")
        asset_scope = [
            {"asset_id": a["asset_id"], "role": a["role"], "sha256": a["sha256"],
             "ordinal": i}
            for i, a in enumerate(job["assets"])
        ]
        return {
            "product_name": plan["product_name"],
            "user_text": user_text,
            "product_facts": deepcopy(product_facts),
            "additional_review_inputs": {
                "fake_consumed_assets": asset_scope,
                "fake_brand_name": plan["brand_name"],
                "fake_extra": deepcopy(extra),
            },
            "source_schema_version": _PROFILE,
        }

    def _snapshot(self, job: dict, state: dict) -> dict:
        return {
            "job_id": job["job_id"],
            "copy_revision": state["copy_revision"],
            "copy_output": self._copy_output(job),
            "review_context": self._context(
                job, user_text=state["user_text"],
                product_facts=state["product_facts"], extra=state["extra"],
            ),
        }

    def observe_transition(self, current: dict, next_job: dict) -> None:
        """Trusted JobStore mutation observer, invoked inside store's lock.

        It invalidates an earlier review for EVERY intervening relevant Job
        input change, even if a caller never explicitly restages and eventually
        restores the exact old bytes. Single-process only; not a DB trigger.
        """
        jid = current["job_id"]
        if not self._file(jid).exists():
            return  # Initial plan/copy before any Fake reviewer state.
        state = self._read(jid)  # Corrupted state prevents silent mutations.
        old = self._snapshot(current, state)
        new = self._snapshot(next_job, state)
        if _canonical_json(old) == _canonical_json(new):
            return
        if current["status"] != "COPY_REVIEW_REQUIRED":
            _blocked("APPROVED_INPUT_IMMUTABLE")
        state["generation"] += 1
        state["pending"] = None
        state["latest_record_id"] = None
        state["dirty"] = True
        self._write(jid, state)

    def stage(self, job_id: str, *, revision: str = "mock-copy-r01",
              user_text: str | None = None, product_facts: dict | None = None,
              extra: dict | None = None) -> int:
        """Stage exact trusted Fake reviewer inputs. Changed inputs bump generation.

        Same snapshot is idempotent. No user-controlled HTTP mutation exists.
        Trusted future copy/context writers MUST call this on each mutation.
        """
        with self.store._lock:
            job = self.store.get_job(job_id)
            if job["status"] != "COPY_REVIEW_REQUIRED":
                _blocked("WRONG_COPY_REVIEW_STATE")
            if not isinstance(revision, str) or not revision:
                _blocked("INVALID_REVISION")
            current = {
                "job_id": job_id,
                "copy_revision": revision,
                "user_text": user_text,
                "product_facts": deepcopy(product_facts if product_facts is not None else {}),
                "extra": deepcopy(extra if extra is not None else {}),
            }
            try:
                snapshot = self._snapshot(job, current)
                canonical_review_input_hash(
                    **snapshot, model_version=_MODEL, rules_version=_RULES,
                )
                serialized = _canonical_json(snapshot)
            except (ContractViolation, ValueError, TypeError):
                _blocked("INVALID_REVIEW_INPUT")
            try:
                previous = self._read(job_id)
            except HTTPException as exc:
                if exc.detail.get("reason") != "MISSING_OR_INVALID_SERVER_REVIEW":
                    raise
                if self._file(job_id).exists():
                    raise  # Corrupted records must fail closed, never reinitialize.
                previous = None
            if previous is not None:
                if previous.get("approved"):
                    _blocked("ALREADY_APPROVED")
                if (previous.get("copy_revision") == revision and
                    previous.get("copy_sha256") != canonical_copy_hash(snapshot["copy_output"])):
                    _blocked("CONFLICTING_COPY_REVISION")
                if previous["snapshot_json"] == serialized and not previous.get("dirty"):
                    return previous["generation"]
            state = {
                **current,
                "snapshot_json": serialized,
                "copy_sha256": canonical_copy_hash(snapshot["copy_output"]),
                # observe_transition already bumped generation at the actual
                # Job mutation boundary. Don't double-count its dirty snapshot.
                "generation": (
                    previous["generation"] if previous and previous.get("dirty")
                    else (previous["generation"] + 1 if previous else 1)
                ),
                "dirty": False,
                "pending": None,
                "records": previous.get("records", {}) if previous else {},
                "runs": previous.get("runs", {}) if previous else {},
                "latest_record_id": None,
                "approved": False,
            }
            self._write(job_id, state)
            return state["generation"]

    def begin(self, job_id: str) -> tuple[str, dict]:
        with self.store._lock:
            job = self.store.get_job(job_id)
            state = self._read(job_id)
            if job["status"] != "COPY_REVIEW_REQUIRED" or state["approved"]:
                _blocked("WRONG_COPY_REVIEW_STATE")
            snap = self._snapshot(job, state)
            if _canonical_json(snap) != state["snapshot_json"]:
                _blocked("REVIEW_INPUT_CHANGED")
            token = uuid4().hex
            state["pending"] = {
                "token": token, "generation": state["generation"],
                "snapshot_json": state["snapshot_json"],
                "input_sha256": canonical_review_input_hash(
                    **snap, model_version=_MODEL, rules_version=_RULES,
                ),
            }
            self._write(job_id, state)
            return token, deepcopy(snap)

    def complete(self, job_id: str, token: str, report: dict) -> str:
        """Only backend tests/trusted Fake reviewer may submit reports.

        Completing a report through a new HTTP endpoint is intentionally absent.
        """
        with self.store._lock:
            state = self._read(job_id)
            job = self.store.get_job(job_id)
            pending = state.get("pending")
            if not pending or pending["token"] != token:
                _blocked("UNTRUSTED_OR_REPLAYED_COMPLETION")
            state["pending"] = None
            if job["status"] != "COPY_REVIEW_REQUIRED" or (
                pending["generation"] != state["generation"]
            ) or pending["snapshot_json"] != state["snapshot_json"] or (
                _canonical_json(self._snapshot(job, state)) != state["snapshot_json"]
            ):
                self._write(job_id, state)
                _blocked("REVIEW_INPUT_CHANGED_DURING_REVIEW")
            snap = json.loads(state["snapshot_json"])
            try:
                validate_compliance(
                    snap["copy_output"], report,
                    product_name=snap["review_context"]["product_name"],
                    user_text=snap["review_context"]["user_text"],
                )
                report_json = _canonical_json(report)
            except (ContractViolation, ValueError, TypeError):
                self._write(job_id, state)
                _blocked("INVALID_COMPLIANCE_REPORT")
            rid = uuid4().hex
            state["records"][rid] = {
                "review_record_id": rid,
                "source_review_token": token,
                "reviewed_job_generation": state["generation"],
                "review_input_sha256": pending["input_sha256"],
                "copy_sha256": state["copy_sha256"],
                "copy_revision": state["copy_revision"],
                "report_sha256": sha256(report_json.encode("utf-8")).hexdigest(),
                "report_json": report_json,
                "reviewed_snapshot_json": state["snapshot_json"],
                "model_version": _MODEL,
                "rules_version": _RULES,
            }
            state["runs"][token] = [rid, pending["input_sha256"], state["generation"]]
            state["latest_record_id"] = rid
            self._write(job_id, state)
            return rid

    def approve(self, job_id: str) -> dict:
        """Existing approved:true HTTP gate; single-lock verify + Job status CAS."""
        with self.store._lock:
            job = self.store.get_job(job_id)
            if job["status"] != "COPY_REVIEW_REQUIRED":
                _blocked("WRONG_COPY_REVIEW_STATE")
            state = self._read(job_id)
            rid = state.get("latest_record_id")
            rec = state.get("records", {}).get(rid) if rid else None
            if not rec:
                _blocked("MISSING_TRUSTED_REVIEW_RECORD")
            if state.get("approved"):
                _blocked("ALREADY_APPROVED")
            if rec["reviewed_job_generation"] != state["generation"]:
                _blocked("STALE_REVIEW_GENERATION")
            if rec["copy_revision"] != state["copy_revision"]:
                _blocked("STALE_REVIEW_REVISION")
            if rec["copy_sha256"] != state["copy_sha256"]:
                _blocked("STALE_REVIEW_COPY")
            if state["runs"].get(rec["source_review_token"]) != [
                rid, rec["review_input_sha256"], rec["reviewed_job_generation"],
            ]:
                _blocked("UNTRUSTED_REVIEW_PROVENANCE")
            snap = self._snapshot(job, state)
            if _canonical_json(snap) != state["snapshot_json"] or (
                rec["reviewed_snapshot_json"] != state["snapshot_json"]
            ):
                _blocked("STALE_REVIEW_CONTEXT")
            try:
                if canonical_review_input_hash(
                    **snap, model_version=rec["model_version"],
                    rules_version=rec["rules_version"],
                ) != rec["review_input_sha256"]:
                    _blocked("STALE_REVIEW_FINGERPRINT")
                if canonical_copy_hash(snap["copy_output"]) != rec["copy_sha256"]:
                    _blocked("STALE_REVIEW_COPY")
                if sha256(rec["report_json"].encode("utf-8")).hexdigest() != rec["report_sha256"]:
                    _blocked("TAMPERED_COMPLIANCE_REPORT")
                report = json.loads(rec["report_json"])
                passed = validate_compliance(
                    snap["copy_output"], report,
                    product_name=snap["review_context"]["product_name"],
                    user_text=snap["review_context"]["user_text"],
                )
            except (ContractViolation, ValueError, TypeError):
                _blocked("INVALID_STORED_COMPLIANCE")
            if not passed:
                _blocked("COMPLIANCE_BLOCKED")
            # This Job transition is an atomic single-job ledger replacement.
            # Under the SAME RLock no concurrent stage/review can interleave.
            # No approved flag is required in separate sidecar for correctness.
            result = transition_job(
                self.store, job_id, expected_status="COPY_REVIEW_REQUIRED",
                next_status="COPY_APPROVED", updates={"copy_approved": True},
            )
            return result


def fake_report(snapshot: dict, *, passed: bool = True) -> dict:
    """Clearly marked deterministic FAKE reviewer, usable only inside tests."""
    report: dict = {
        "passed": passed, "issues": [], "revised_fields": {},
        "checklist": ["FAKE ONLY — 법적 적합성 검증 아님"],
    }
    if not passed:
        headline = snapshot["copy_output"]["ad_copy"]["headline"]
        report["issues"] = [{
            "field": "headline", "start": 0, "end": len(headline),
            "text": headline, "risk_level": "위반 의심",
        }]
    return report
