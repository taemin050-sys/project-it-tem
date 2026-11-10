"""Operator-only dispositions for Live Dual billing incidents.

A disposition resumes unrelated work. It never revives the affected group
or edits the original Queue, CostLedger, Owner receipt, or artifact rows.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
from uuid import UUID, uuid5

from deploy.systemd.bp18_live_launch import private_text, release_sha
from .contracts import LiveGateError, digest
from .dual_worker import POST_APPROVAL_STAGES, TEXT_COST_STAGES, image_cost_fingerprint
from .pipeline import DEFAULT_LIVE_PROJECT_ID, live_dual_owner_project
from .queue import (DUAL_BILLING_DISPOSITIONS, LIVE_DUAL_PROTOCOL, LIVE_DUAL_STAGES,
                    LiveQueue, incident_identity)


APPROVAL_FIELDS = frozenset({"version", "operator", "approval_reference", "plan_sha",
                             "evidence_sha", "disposition", "acknowledge_no_replay"})
RECOVERY_SOURCE_FILES = ("demo_staging/live/dual_billing.py", "demo_staging/live/dual_worker.py",
                         "demo_staging/live/pipeline.py", "demo_staging/live/queue.py")


def _hex(value, size):
    return isinstance(value, str) and re.fullmatch(rf"[0-9a-f]{{{size}}}", value) is not None


def _unique_fields(pairs):
    fields = dict(pairs)
    if len(fields) != len(pairs):
        raise LiveGateError("LIVE_DUAL_RECONCILE_APPROVAL_INVALID")
    return fields


def _owner_directory(path, *, private=False):
    info = path.lstat()
    forbidden = 0o077 if private else 0o022
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & forbidden:
        raise LiveGateError("LIVE_DUAL_RECONCILE_DIRECTORY_INVALID")


@contextmanager
def _db(path, *, write=False):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o022:
        raise LiveGateError("LIVE_DUAL_RECONCILE_DATABASE_INVALID")
    mode = "rw" if write else "ro"
    connection = sqlite3.connect(path.resolve().as_uri() + f"?mode={mode}", uri=True, timeout=4)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            if not write:
                connection.execute("PRAGMA query_only=ON")
            yield connection
    finally:
        connection.close()


@contextmanager
def _lock(path):
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise LiveGateError("LIVE_DUAL_RECONCILE_LOCK_INVALID")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise LiveGateError("LIVE_DUAL_RECONCILE_LOCK_BUSY") from None
        yield
    finally:
        os.close(fd)


def _paths(root: Path):
    config, live = root / "config", root / "runtime/live"
    _owner_directory(root)
    _owner_directory(config, private=True)
    _owner_directory(root / "runtime")
    _owner_directory(live)
    return config, live


def _verify_active_recovery_source(root, active_sha):
    source = Path(__file__).resolve().parents[2]
    release = root / "releases" / active_sha
    for name in RECOVERY_SOURCE_FILES:
        staged = release / name
        if (staged.is_symlink() or not staged.is_file()
                or staged.read_bytes() != (source / name).read_bytes()):
            raise LiveGateError("LIVE_DUAL_RECONCILE_RELEASE_INCOMPATIBLE")


def _live_context(live, task):
    with _db(live / "live.sqlite") as db:
        group = db.execute("""SELECT parent_job_id,child_job_id,authority_sha,authority_json,prompt_sha
            FROM live_paid_dual_groups WHERE actor=? AND (parent_job_id=? OR child_job_id=?)""",
            (task["actor"], task["job_id"], task["job_id"])).fetchall()
        if len(group) != 1:
            raise LiveGateError("LIVE_DUAL_INCIDENT_GROUP_NOT_FOUND")
        parent, child, authority_sha, raw_authority, prompt_sha = group[0]
        if not _hex(parent, 32) or (child is not None and not _hex(child, 32)):
            raise LiveGateError("LIVE_DUAL_INCIDENT_GROUP_INVALID")
        group_identity = {"parent_job_id": parent, "child_job_id": child, "authority_sha": authority_sha}
        authority = None
        job = None
        if task["stage"] in POST_APPROVAL_STAGES:
            authority = json.loads(raw_authority)
            if (digest(authority) != authority_sha or authority["actor"] != task["actor"]
                    or authority["parent_job_id"] != parent or authority["child_job_id"] != child):
                raise LiveGateError("LIVE_DUAL_INCIDENT_AUTHORITY_CHANGED")
            intent = db.execute("""SELECT 1 FROM live_paid_dual_intents WHERE queue_task_id=?
                AND parent_job_id=? AND actor=? AND job_id=? AND stage=? AND context_sha=?""",
                (task["id"], parent, task["actor"], task["job_id"], task["stage"], task["context_sha"])).fetchone()
            job = db.execute("""SELECT input_json,input_sha,approval_sha FROM live_jobs WHERE job_id=?
                AND actor=? AND mode='LIVE'""", (task["job_id"], task["actor"])).fetchone()
            side = "parent" if task["job_id"] == parent else "child"
            if (not intent or not job or job["input_sha"] != authority[side + "_input_sha"]
                    or digest(json.loads(job["input_json"])) != job["input_sha"]
                    or job["approval_sha"] != authority[side + "_approval_sha"]
                    or task["context_sha"] != digest({"authority_sha": authority_sha,
                        "prompt_sha": prompt_sha if task["stage"] == "image" else None,
                        "job_id": task["job_id"], "stage": task["stage"], "approval_sha": job["approval_sha"]})):
                raise LiveGateError("LIVE_DUAL_INCIDENT_CONTEXT_CHANGED")
        return group_identity, authority, json.loads(job["input_json"]) if job else None


def _image_receipt(live, task, authority, job_input, attempts):
    """Read the existing native response and join it to the exact image intent."""
    from src.image_generation.contracts import ExternalImageRequest, ExternalImageResult, content_hash

    mode = job_input["generation_mode"]
    profile = authority["execution_profile"]
    # Composed preserves the Owner adapter's original mode-less wire input.
    wire_mode = "freeform" if mode == "freeform" else None
    fingerprint = digest(image_cost_fingerprint(task["context_sha"], wire_mode, profile))
    matching = [attempt for attempt in attempts if attempt["payload_hash"] == fingerprint]
    native = live / "owner_image"
    if len(matching) != 1 or matching[0]["status"] not in (
            "BILLING_UNKNOWN", "SUCCEEDED_USAGE_UNPRICED", "SUCCEEDED"):
        return None
    bindings, receipts = native / "image_bindings.sqlite", native / "image_attempts.sqlite"
    if not bindings.exists() or not receipts.exists():
        return None
    _owner_directory(native)
    expected_project = str(live_dual_owner_project(DEFAULT_LIVE_PROJECT_ID, authority["parent_job_id"]))
    with _db(bindings) as db:
        rows = db.execute("""SELECT project_id,request_json,request_hash FROM backend_image_bindings
            WHERE project_id=? AND service_job_id=?""", (expected_project, task["job_id"])).fetchall()
    if len(rows) != 1:
        return None
    project, request_json, request_sha = rows[0]
    request = ExternalImageRequest.model_validate_json(request_json)
    image_profile = {field: getattr(request, field) for field in ("model", "quality", "complexity")}
    assets = [asset.sha256 for asset in (*request.product_images, *request.reference_images)]
    if (content_hash(request) != request_sha or image_profile != profile["image_profile"]
            or ("freeform" if request.text_rendering == "freeform-v1" else "composed") != mode
            or (request.width, request.height) != (1152, 1440)
            or assets != [asset["sha256"] for asset in job_input["ordered_asset_hashes"]]):
        raise LiveGateError("LIVE_DUAL_INCIDENT_NATIVE_REQUEST_CHANGED")
    native_job = str(uuid5(UUID(project), "beautyai/backend/image/v1/" + task["job_id"]))
    with _db(receipts) as db:
        receipt = db.execute("""SELECT attempt_id,request_hash,state,provider_request_id,usage_json,result_json
            FROM provider_attempts WHERE project_id=? AND job_id=?""", (project, native_job)).fetchone()
    if receipt is None or receipt["state"] != "succeeded":
        return None
    result = ExternalImageResult.model_validate_json(receipt["result_json"])
    usage = result.usage.model_dump(mode="json") if result.usage else None
    if (receipt["request_hash"] != request_sha or str(result.attempt_id) != receipt["attempt_id"]
            or result.provider_request_id != receipt["provider_request_id"]
            or result.model != request.model or usage != json.loads(receipt["usage_json"] or "null")):
        raise LiveGateError("LIVE_DUAL_INCIDENT_NATIVE_RECEIPT_CHANGED")
    if not result.provider_request_id or not usage or not any(type(value) is int for value in usage.values()):
        return None
    attempt = matching[0]
    if attempt["receipt"]:
        outer = json.loads(attempt["receipt"])
        if (outer.get("provider_response_id") != result.provider_request_id
                or outer.get("model") != result.model or outer.get("usage") != usage):
            raise LiveGateError("LIVE_DUAL_INCIDENT_OUTER_RECEIPT_CHANGED")
    return {"cost_attempt_id": attempt["id"], "owner_attempt_id": receipt["attempt_id"],
            "request_sha": request_sha, "provider_request_id": result.provider_request_id,
            "model": result.model, "usage": usage, "native_result_sha": content_hash(result),
            "actual_usd": None}


def inspect_incident(root, task_id):
    """Return an exact snapshot for local operator review; all DB opens are read-only."""
    if not _hex(task_id, 32):
        raise LiveGateError("LIVE_DUAL_INCIDENT_ID_INVALID")
    _, live = _paths(root)
    with _db(live / "queue.sqlite") as db:
        row = db.execute("SELECT * FROM queued_ops WHERE id=?", (task_id,)).fetchone()
        if (not row or row["mode"] != LIVE_DUAL_PROTOCOL or row["state"] != "BILLING_UNKNOWN"
                or row["stage"] not in LIVE_DUAL_STAGES
                or not _hex(row["job_id"], 32) or not _hex(row["context_sha"], 64)):
            raise LiveGateError("LIVE_DUAL_INCIDENT_NOT_HELD")
        task = incident_identity(row)
    group, authority, job_input = _live_context(live, task)
    stages = TEXT_COST_STAGES.get(task["stage"], (task["stage"],))
    placeholders = ",".join("?" for _ in stages)
    with _db(live / "cost.sqlite") as db:
        attempts = [dict(row) for row in db.execute(f"""SELECT id,actor,stage,payload_hash,status,
            cost_microusd,billing_unknown,receipt FROM attempts WHERE job_id=? AND stage IN ({placeholders})
            ORDER BY id""", (task["job_id"], *stages))]
    if any(attempt["actor"] != task["actor"] for attempt in attempts):
        raise LiveGateError("LIVE_DUAL_INCIDENT_COST_ACTOR_MISMATCH")
    image_receipt = _image_receipt(live, task, authority, job_input, attempts) if task["stage"] == "image" else None
    for attempt in attempts:
        receipt = attempt.pop("receipt")
        attempt["receipt_sha"] = sha256(receipt.encode()).hexdigest() if receipt is not None else None
    plan = {"version": 1, "release_sha": release_sha(root), "task": task, "group": group,
            "attempts": attempts, "image_receipt": image_receipt}
    return {**plan, "plan_sha": digest(plan)}


def _evidence_sha(path):
    _owner_directory(path.parent, private=True)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as source:
        info = os.fstat(source.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) not in (0o400, 0o600)
                or not 0 < info.st_size <= 64 * 1024 * 1024):
            raise LiveGateError("LIVE_DUAL_RECONCILE_EVIDENCE_INVALID")
        checksum = sha256()
        remaining = info.st_size
        while remaining:
            block = source.read(min(remaining, 1024 * 1024))
            if not block:
                raise LiveGateError("LIVE_DUAL_RECONCILE_EVIDENCE_CHANGED")
            checksum.update(block)
            remaining -= len(block)
        if source.read(1):
            raise LiveGateError("LIVE_DUAL_RECONCILE_EVIDENCE_CHANGED")
        return checksum.hexdigest()


def apply_disposition(root, task_id, approval_path, evidence_path):
    """Record an authorized, terminal no-replay disposition with both B5 locks held."""
    config, live = _paths(root)
    with _lock(config / ".b5_operator_control.lock"), _lock(live / "worker.lock"):
        approval = json.loads(private_text(approval_path), object_pairs_hook=_unique_fields)
        if (not isinstance(approval, dict) or set(approval) != APPROVAL_FIELDS
                or type(approval["version"]) is not int or approval["version"] != 1
                or approval["acknowledge_no_replay"] is not True
                or approval["disposition"] not in DUAL_BILLING_DISPOSITIONS
                or not isinstance(approval["operator"], str)
                or not re.fullmatch(r"bp18_b_[A-Za-z0-9_-]{1,33}", approval["operator"])
                or not isinstance(approval["approval_reference"], str)
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{2,79}", approval["approval_reference"])
                or not _hex(approval["evidence_sha"], 64) or not _hex(approval["plan_sha"], 64)):
            raise LiveGateError("LIVE_DUAL_RECONCILE_APPROVAL_INVALID")
        roles = json.loads(private_text(config / "bp18_tailnet_roles.json"))
        if roles.get(approval["operator"]) != "admin":
            raise LiveGateError("LIVE_DUAL_RECONCILE_ADMIN_REQUIRED")
        if _evidence_sha(evidence_path) != approval["evidence_sha"]:
            raise LiveGateError("LIVE_DUAL_RECONCILE_EVIDENCE_CHANGED")
        plan = inspect_incident(root, task_id)
        if plan["plan_sha"] != approval["plan_sha"]:
            raise LiveGateError("LIVE_DUAL_RECONCILE_PLAN_CHANGED")
        _verify_active_recovery_source(root, plan["release_sha"])
        if approval["disposition"] == "RECEIPT_MATCHED_UNPRICED" and not plan["image_receipt"]:
            raise LiveGateError("LIVE_DUAL_RECONCILE_RECEIPT_REQUIRED")
        with _db(live / "queue.sqlite") as db:
            if db.execute("SELECT 1 FROM queued_ops WHERE state='RUNNING' LIMIT 1").fetchone():
                raise LiveGateError("LIVE_DUAL_RECONCILE_ACTIVE_QUEUE")
        with _db(live / "cost.sqlite") as db:
            if db.execute("SELECT 1 FROM attempts WHERE status='DISPATCHED' LIMIT 1").fetchone():
                raise LiveGateError("LIVE_DUAL_RECONCILE_DISPATCH_INTENT_PENDING")

        # Set the Store hold first. A crash before the separate Queue commit
        # leaves the global latch active, and the same reviewed plan remains usable.
        group, task = plan["group"], plan["task"]
        with _db(live / "live.sqlite", write=True) as db:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute("""UPDATE live_paid_dual_groups SET hold_code=COALESCE(hold_code,?)
                WHERE parent_job_id=? AND actor=? AND child_job_id IS ? AND authority_sha IS ?""",
                ("LIVE_DUAL_OPERATOR_QUARANTINED", group["parent_job_id"], task["actor"],
                 group["child_job_id"], group["authority_sha"])).rowcount
            if changed != 1:
                raise LiveGateError("LIVE_DUAL_INCIDENT_GROUP_CHANGED")
        record = {**plan, **approval, "decision_sha": digest(approval),
                  "recorded_utc": datetime.now(timezone.utc).isoformat()}
        queue = LiveQueue(live / "queue.sqlite")
        record_sha = queue.record_dual_billing_resolution(record)
        return {"task_id": task_id, "record_sha": record_sha, "disposition": approval["disposition"],
                "affected_group": "QUARANTINED_NO_REPLAY", "actual_usd": None,
                "global_queue_held": queue.dual_billing_unknown()}
