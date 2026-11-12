"""Read-only attribution of result revisions to their existing CostLedger rows.

Revision usage is a subset of the Job ledger, never additional billed usage.
Only exact Actor/Job/stage/fingerprint matches may be excluded from base Dual
counts. Missing USD remains unknown; this module neither prices nor dispatches.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import sqlite3

from .contracts import LiveGateError, digest

SCHEMA = "bp18-result-revision-costs-v1"
_ID = re.compile(r"^[0-9a-f]{32}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_MODEL = re.compile(r"^[A-Za-z0-9_.:-]{1,100}$")
_ACTOR = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
_IMAGE_PROTOCOL = "FREEFORM_TEXT_EDIT_V1"
_COPY_PROTOCOL = "COMPOSED_COPY_EDIT_V1"


def _strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError
            result[key] = value
        return result
    def invalid(_):
        raise ValueError
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


@contextmanager
def _readonly(file):
    """No constructors, schema checks that write, WAL checkpoint, or CREATE."""
    file = Path(file)
    if file.is_symlink() or not file.is_file():
        raise LiveGateError("REVISION_COST_STORAGE_UNAVAILABLE")
    try:
        db = sqlite3.connect(file.resolve().as_uri()+"?mode=ro", uri=True, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        yield db
    except sqlite3.Error:
        raise LiveGateError("REVISION_COST_STORAGE_UNAVAILABLE") from None
    finally:
        if "db" in locals():
            db.close()


def _status(attempts):
    if any(row["billing_unknown"] or row["state"] == "BILLING_UNKNOWN" for row in attempts):
        return "BILLING_UNKNOWN"
    if any(row["state"] == "DISPATCHED" for row in attempts):
        return "AWAITING_RECEIPT"
    if any(row["state"] != "RESERVED" for row in attempts):
        return "UNPRICED"
    return "NOT_DISPATCHED"


def _public_attempt(row):
    try:
        receipt = _strict_json(row["receipt"] or "{}")
        if not isinstance(receipt, dict):
            receipt = {}
    except (TypeError, ValueError):
        receipt = {}
    usage = receipt.get("usage")
    counts = {key: value for key, value in usage.items() if isinstance(key, str)
        and re.fullmatch(r"[a-z_]{1,60}", key) and type(value) is int and value >= 0} if isinstance(usage, dict) else {}
    model = receipt.get("model")
    response_id = receipt.get("provider_response_id")
    return {"attempt_id": row["id"], "stage": row["stage"], "state": row["status"],
        "billing_unknown": bool(row["billing_unknown"]),
        "model": model if isinstance(model, str) and _MODEL.fullmatch(model) else None,
        "usage": counts or None, "actual_usd": None,
        "receipt_sha": digest(receipt) if receipt else None,
        "provider_response_id": response_id if isinstance(response_id, str)
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,199}", response_id) else None}


def _aggregate(attempts):
    return {"provider_attempt_count": sum(row["state"] != "RESERVED" for row in attempts),
        "status": _status(attempts), "actual_usd": None, "attempts": attempts}


def _image_revision(row, actor, job_id):
    payload = _strict_json(row["payload_json"])
    source = payload["source_context"]
    if (not _ID.fullmatch(row["correction_id"]) or not _SHA.fullmatch(row["request_sha"])
            or digest(payload) != row["request_sha"] or digest(source) != row["context_sha"]
            or source["protocol"] != _IMAGE_PROTOCOL or source["actor"] != actor or source["job_id"] != job_id
            or payload["request_key"] != row["request_key"]
            or any(payload[name] != source[target] for name, target in (
                ("expected_image_sha", "source_image_sha"), ("expected_copy_sha", "copy_sha"),
                ("expected_approval_sha", "approval_sha")))):
        raise ValueError
    for field in ("source_image_sha", "copy_sha", "approval_sha", "review_sha"):
        if not _SHA.fullmatch(source[field]):
            raise ValueError
    return {"revision_id": row["correction_id"], "kind": "image_correction", "state": row["state"],
        "fingerprints": {digest({"protocol": _IMAGE_PROTOCOL, "correction_id": row["correction_id"],
                                "request_sha": row["request_sha"]})},
        "stage": "image", "evidence": None, "nonbillable":"stroke_source_box" in payload}


def _copy_revision(row, actor, job_id):
    record = _strict_json(row["record_json"])
    source = record["source_context"]
    request = {"expected_image_sha": source["image_sha"], "expected_copy_sha": source["copy_sha"],
        "expected_approval_sha": source["approval_sha"], "ad_copy": record["copy"]["ad_copy"],
        "request_key": row["request_key"]}
    if (not _ID.fullmatch(row["edit_id"]) or record["edit_id"] != row["edit_id"]
            or record["actor"] != actor or record["job_id"] != job_id or record["state"] != row["state"]
            or record["protocol"] != _COPY_PROTOCOL or source["protocol"] != _COPY_PROTOCOL
            or source["actor"] != actor or source["job_id"] != job_id
            or record["request_key"] != row["request_key"] or record["request_sha"] != row["request_sha"]
            or digest(request) != row["request_sha"] or digest(source) != record["source_context_sha"]
            or digest(record["copy"]) != record["copy_sha"]):
        raise ValueError
    for field in ("image_sha", "copy_sha", "approval_sha", "review_sha"):
        if not _SHA.fullmatch(source[field]):
            raise ValueError
    llm = (record.get("report") or {}).get("llm_review") or {}
    # New revisions freeze this at admission. Historical pending rows can still
    # be exactly attributed if their hash matches the old protected worker model.
    models = {record.get("review_model"), llm.get("model"), os.environ.get("IT_TEM_TEXT_MODEL", "gpt-6-luna")}
    models = {model for model in models if isinstance(model, str) and _MODEL.fullmatch(model)}
    return {"revision_id": row["edit_id"], "kind": "composed_copy_edit", "state": row["state"],
        "fingerprints": {digest({"protocol": _COPY_PROTOCOL, "edit_id": row["edit_id"],
            "source_context_sha": record["source_context_sha"], "copy_sha": record["copy_sha"], "model": model}) for model in models},
        "stage": "copy_review", "evidence": record.get("cost_receipt")}


def revision_cost_summary(flow, actor, job_id):
    """Return one Actor/Job's revision rows and proven CostLedger exclusions.

    ``excluded_attempt_ids`` is for the server's base Dual count filter. The same
    rows are shown under ``revisions`` and must not be added to a whole-Job total
    a second time. Unknown and dispatched attempts remain visible before result
    publication because attribution uses durable request fingerprints.
    """
    if not isinstance(actor, str) or not _ACTOR.fullmatch(actor) or not isinstance(job_id, str) or not _ID.fullmatch(job_id):
        raise LiveGateError("REVISION_COST_PRINCIPAL_INVALID")
    try:
        revisions = []
        specs = (("image_corrections.sqlite", "image_corrections", _image_revision),
                 ("composed_copy_edits.sqlite", "composed_copy_edits", _copy_revision))
        for filename, table, parser in specs:
            file = Path(flow.root)/filename
            if not file.exists() and not file.is_symlink():
                continue
            with _readonly(file) as db:
                rows = db.execute(f"SELECT * FROM {table} WHERE actor=? AND job_id=? ORDER BY rowid", (actor,job_id)).fetchall()
                revisions.extend(parser(row, actor, job_id) for row in rows)
        costs = []
        file = Path(flow.cost.filename)
        if file.exists() or file.is_symlink():
            with _readonly(file) as db:
                costs = db.execute("SELECT id,actor,job_id,stage,payload_hash,status,billing_unknown,receipt FROM attempts WHERE actor=? AND job_id=? ORDER BY created_at,id",
                                   (actor,job_id)).fetchall()
        mapped, excluded, items = [], set(), []
        classification = "COMPLETE"
        for revision in revisions:
            rows = [row for row in costs if row["stage"] == revision["stage"] and row["payload_hash"] in revision["fingerprints"]]
            if len(rows) > 1:
                raise ValueError  # One explicit revision may dispatch at most once.
            evidence = revision["evidence"]
            if evidence:
                if len(rows) != 1 or rows[0]["id"] != evidence.get("attempt_id"):
                    raise ValueError
                receipt = _strict_json(rows[0]["receipt"] or "{}")
                if (digest(receipt) != evidence.get("receipt_sha") or receipt.get("model") != evidence.get("response_model")):
                    raise ValueError
            attempts = [_public_attempt(row) for row in rows]
            if any(row["attempt_id"] in excluded for row in attempts):
                raise ValueError
            excluded.update(row["attempt_id"] for row in attempts)
            mapped.extend(attempts)
            if not rows and revision["state"] in ("RUNNING", "BILLING_UNKNOWN"):
                classification = "PENDING_LEDGER_BINDING"
            aggregate = _aggregate(attempts)
            if revision.get("nonbillable"):
                if rows:raise ValueError
                aggregate["status"]="NO_NEW_PROVIDER_CALL"
            if revision["state"] == "BILLING_UNKNOWN":
                aggregate["status"] = "BILLING_UNKNOWN"
            items.append({"revision_id": revision["revision_id"], "kind": revision["kind"],
                          "state": revision["state"], **aggregate})
        unclassified_unknown = sum(bool(row["billing_unknown"]) or row["status"] in ("DISPATCHED", "BILLING_UNKNOWN")
                                   for row in costs if row["id"] not in excluded)
        total = _aggregate(mapped)
        if any(item["status"] == "BILLING_UNKNOWN" for item in items):
            total["status"] = "BILLING_UNKNOWN"
        return {"schema": SCHEMA, "job_id": job_id, **total, "revisions": items,
            "excluded_attempt_ids": sorted(excluded), "classification_status": classification,
            "unclassified_uncertain_attempt_count": unclassified_unknown}
    except (KeyError, TypeError, ValueError, RecursionError):
        raise LiveGateError("REVISION_COST_CLASSIFICATION_INTEGRITY") from None
