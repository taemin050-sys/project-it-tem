"""Worker-side dispatch for the separately enabled Live Dual protocol."""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat

from .contracts import LiveGateError, digest
from .image_runtime_profile import effective_image_profile
from .pipeline import live_dual_owner_project
from .queue import LIVE_DUAL_PROTOCOL,LIVE_DUAL_V2_PROTOCOL
from .dual_ratio_policy import ratio_admission,MULTI_RATIO_FLAG
from demo_staging.live_safety import LiveNotAuthorized


LIVE_DUAL_FLAG = "IT_TEM_BP18_LIVE_DUAL_ENABLED"
LOCK_NAME = "dual_worker.lock"
LOCK_V2_NAME = "dual_worker_v2.lock"
HOLD = "LIVE_STAGE_HELD_FOR_RECONCILIATION"
COMMITTED = "LIVE_STAGE_COMMITTED"
FAILED = "LIVE_DUAL_STAGE_FAILED"
POST_APPROVAL_STAGES = frozenset({"image_prompt", "image"})
TEXT_COST_STAGES = {"analysis": ("vision", "research", "copy", "copy_review"),
                    "copy_revision": ("copy_revision", "copy_review"),
                    "copy_review": ("copy_review",)}


def live_dual_profile(image_size="4:5") -> dict:
    release = os.environ.get("IT_TEM_BP18_LIVE_RELEASE_SHA", "")
    policy = os.environ.get("IT_TEM_BP18_LIVE_POLICY_SHA", "")
    text_model = os.environ.get("IT_TEM_TEXT_MODEL", "gpt-6-luna")
    required = (LIVE_DUAL_FLAG, "IT_TEM_TAILNET_AUTH_ENABLED", "IT_TEM_TAILNET_SSO_ONLY",
                "IT_TEM_BP18_F09_REQUIRED", "IT_TEM_BP18_F11_ENABLED")
    if (any(os.environ.get(key) != "YES" for key in required) or
            os.environ.get("IT_TEM_TAILNET_EXPECTED_HOST") != "macstudio-macstudio.tail17dfff.ts.net:10500" or
            not re.fullmatch(r"[0-9a-f]{40}", release) or
            not re.fullmatch(r"[0-9a-f]{64}", policy) or
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", text_model)):
        raise LiveNotAuthorized("LIVE_DUAL_PROTOCOL_NOT_APPROVED")
    cta_policy_sha=ratio_admission(image_size)
    result={"protocol": LIVE_DUAL_PROTOCOL, "release_sha": release, "policy_sha": policy,
            "text_model": text_model, "image_profile": effective_image_profile(), "image_size": image_size}
    if image_size!="4:5":
        result.update(protocol=LIVE_DUAL_V2_PROTOCOL,cta_policy_sha=cta_policy_sha)
    return result


def _check_lock(fd):
    info = os.fstat(fd)
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or
            stat.S_IMODE(info.st_mode) != 0o600):
        raise LiveNotAuthorized("LIVE_DUAL_WORKER_LOCK_INVALID")


@contextmanager
def live_dual_lease(runtime_root: Path):
    """A separate held lock proves protocol support; a stale file proves nothing."""
    if os.environ.get(LIVE_DUAL_FLAG) != "YES":
        yield None
        return
    profile = live_dual_profile()
    fd = os.open(runtime_root / "live" / LOCK_NAME,
                 os.O_RDWR | os.O_CREAT | os.O_NONBLOCK | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "r+b") as lease:
        _check_lock(lease.fileno())
        try:
            fcntl.flock(lease.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise LiveNotAuthorized("LIVE_DUAL_WORKER_ALREADY_RUNNING") from None
        lease.seek(0)
        lease.truncate()
        lease.write(digest(profile).encode("ascii"))
        lease.flush()
        os.fsync(lease.fileno())
        if os.environ.get(MULTI_RATIO_FLAG)=="YES":
            # Distinct held capability: a V1 lock can never prove V2 support.
            v2=live_dual_profile("3:4")
            v2fd=os.open(runtime_root/"live"/LOCK_V2_NAME,
                        os.O_RDWR|os.O_CREAT|os.O_NONBLOCK|os.O_NOFOLLOW,0o600)
            with os.fdopen(v2fd,"r+b") as capability:
                _check_lock(capability.fileno())
                try:
                    fcntl.flock(capability.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                except BlockingIOError:
                    raise LiveNotAuthorized("LIVE_DUAL_WORKER_ALREADY_RUNNING") from None
                capability.seek(0);capability.truncate()
                capability.write(digest(v2).encode("ascii"));capability.flush();os.fsync(capability.fileno())
                yield profile
        else:
            yield profile


def live_dual_worker_ready(runtime_root: Path,image_size="4:5") -> bool:
    """Check the Worker handshake using no credentials and no write."""
    try:
        live_dual_profile(image_size)  # Includes current explicit 9:16 decision.
        profile=live_dual_profile("3:4" if image_size!="4:5" else "4:5")
        filename=LOCK_V2_NAME if image_size!="4:5" else LOCK_NAME
        fd = os.open(runtime_root / "live" / filename, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as lease:
            _check_lock(lease.fileno())
            try:
                fcntl.flock(lease.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:
                return lease.read(65) == digest(profile).encode("ascii")
    except (OSError, LiveGateError, LiveNotAuthorized):
        pass
    return False


def project_intents(flow, queue):
    # Durable state precedes queue. A process loss between enqueue and attach
    # reuses the existing row by actor, job, stage and exact context on restart.
    for intent in flow.state.live_dual_intents():
        group=flow.state.live_dual_group(intent["actor"],intent["parent_job_id"])
        task, _ = queue.enqueue(actor=intent["actor"], job_id=intent["job_id"],
                                stage=intent["stage"], context_sha=intent["context_sha"],
                                mode=group["execution_profile"]["protocol"])
        flow.state.attach_live_dual_task(intent, task["id"])


def authorize_shared_text(flow, item):
    """Allow preapproval stages only on the visible parent of an open request."""
    actor, job_id = item["actor"], item["job_id"]
    parent = flow.state.live_dual_membership(actor, job_id)
    group = flow.state.live_dual_group(actor, job_id) if parent == job_id else None
    if (item["stage"] not in TEXT_COST_STAGES or not group or
            group["child_job_id"] is not None or group["hold_code"]):
        raise LiveGateError("LIVE_DUAL_SHARED_TEXT_NOT_AUTHORIZED")
    ratio=json.loads(flow.state.get(actor,job_id)["input_json"])["image_size"]
    if item["mode"]!=live_dual_profile(ratio)["protocol"]:
        raise LiveGateError("LIVE_DUAL_PROTOCOL_REQUIRED")


def image_cost_fingerprint(context_sha, wire_mode, profile):
    return {"dual_protocol": profile["protocol"], "context_sha": context_sha,
            "mode": wire_mode, "image_size": profile["image_size"],
            "image_profile": profile["image_profile"]}


def execute_live_dual(flow, queue, item, profile, image_adapter):
    try:
        actor, job_id = item["actor"], item["job_id"]
        flow.require_live_actor(actor)
        if live_dual_profile(profile["image_size"]) != profile or item["mode"]!=profile["protocol"]:
            raise LiveGateError("LIVE_DUAL_EXECUTION_PROFILE_CHANGED")
        group = flow.state.live_dual_task(item, profile)
        parent = group["parent_job_id"]
        flow.verify_live_dual_f09(actor, parent)
        job = flow.state.get(actor, job_id)
        if item["stage"] == "image_prompt":
            flow.prompt(actor, parent, offline=False, text_model=profile["text_model"],
                        expected_approval_sha=job["approval_sha"])
            result_sha = flow.state.share_live_dual_prompt(actor, parent)
        else:
            request = flow.image_input(actor, job_id, expected_approval_sha=job["approval_sha"])
            adapter = image_adapter(flow.root / "owner_image", request)
            expected = profile["image_profile"]
            if {key: getattr(adapter, key) for key in expected} != expected:
                raise LiveGateError("LIVE_DUAL_IMAGE_PROFILE_CHANGED")
            fingerprint = image_cost_fingerprint(item["context_sha"], request.generation_mode, profile)
            project = live_dual_owner_project(flow.project_id, parent)
            output, receipt = flow._guarded(actor, job_id, "image", fingerprint,
                lambda: adapter.generate(request, project_id=project, include_provider_prompt_sha=True),
                image=True, include_receipt=True)
            evidence = {**receipt, "payload_hash": flow.cost.digest(fingerprint)}
            committed = flow.accept_image_result(actor, job_id, output, offline=False,
                expected_approval_sha=job["approval_sha"], dual_receipt=evidence)
            result_sha = committed["image_sha"]
    except Exception as error:
        return fail_live_dual(flow, queue, item, error)
    # A persistence failure here leaves RUNNING. Restart checks the already
    # committed result without invoking either provider.
    _complete(flow, queue, item, result_sha)
    return COMMITTED


def _cost_state(flow, item):
    """An outer DISPATCHED row is written before any Owner transport I/O."""
    stages = TEXT_COST_STAGES.get(item["stage"], (item["stage"],))
    if not flow.cost.filename.is_file():
        return "UNKNOWN"
    try:
        with flow.cost.connect() as db:
            placeholders = ",".join("?" for _ in stages)
            rows = db.execute(f"SELECT actor,status,receipt,billing_unknown FROM attempts "
                              f"WHERE job_id=? AND stage IN ({placeholders})",
                              (item["job_id"], *stages)).fetchall()
    except (OSError, sqlite3.Error):
        return "UNKNOWN"
    used = False
    for actor, state, receipt, billing_unknown in rows:
        if actor != item["actor"] or billing_unknown:
            return "UNKNOWN"
        if state == "RESERVED":
            continue
        if state != "SUCCEEDED_USAGE_UNPRICED":
            return "UNKNOWN"
        try:
            data = json.loads(receipt)
            if not data["provider_response_id"] or not isinstance(data["usage"], dict):
                return "UNKNOWN"
        except (ValueError, TypeError, KeyError):
            return "UNKNOWN"
        used = True
    return "RECORDED" if used else "NOT_SENT"


def _complete(flow, queue, item, result_sha):
    if item["stage"] in POST_APPROVAL_STAGES:
        flow.state.finish_live_dual_intent(item, "SUCCEEDED", result_sha=result_sha)
    queue.complete(item["id"], result_sha)


def _fail(flow, queue, item, code, *, uncertain):
    if uncertain:
        # The queue latch is durable even if Store settlement then fails.
        queue.interrupt(item["id"], code)
    if item["stage"] in POST_APPROVAL_STAGES:
        state = "BILLING_UNKNOWN" if uncertain else "FAILED"
        try:
            flow.state.finish_live_dual_intent(item, state, error_code=code)
        except LiveGateError:
            if not uncertain:
                raise
    if uncertain:
        parent = flow.state.live_dual_membership(item["actor"], item["job_id"])
        if parent:
            flow.state.hold_live_dual(parent, code)
        return HOLD
    queue.fail_dual(item["id"], code)
    return FAILED


def fail_live_dual(flow, queue, item, error):
    code = error.code if isinstance(error, LiveGateError) else "LIVE_DUAL_TASK_FAILED"
    cost = _cost_state(flow, item)
    # Verified receipt and a deterministically invalid result is terminal for
    # this variant. Missing receipt or a storage fault after dispatch is held.
    known_invalid = code in {"PROVIDER_RESULT_INVALID", "OWNER_IMAGE_SIZE_INVALID",
                             "IMAGE_MODE_MISMATCH", "IMAGE_BINDING_MISMATCH", "IMAGE_HASH_MISMATCH"}
    return _fail(flow, queue, item, code,
                 uncertain=(cost == "UNKNOWN" or (cost == "RECORDED" and not known_invalid)))


def reconcile_live_dual(flow, queue):
    """Recover only already committed results, or terminate without redispatch."""
    for item in queue.running_dual():
        actor, job_id, stage = item["actor"], item["job_id"], item["stage"]
        cost = _cost_state(flow, item)
        if cost == "NOT_SENT":
            _fail(flow, queue, item, "LIVE_DUAL_WORKER_STOPPED_BEFORE_SEND", uncertain=False)
            continue
        if cost == "RECORDED" and stage in POST_APPROVAL_STAGES:
            try:
                intent = flow.state.live_dual_intent_by_task(item)
                if stage == "image_prompt":
                    prompt_sha = flow.state.share_live_dual_prompt(actor, intent["parent_job_id"])
                    _complete(flow, queue, item, prompt_sha)
                else:
                    evidence = flow.live_dual_candidate_receipt(actor, job_id)
                    source_sha = hashlib.sha256(flow.image_path(job_id).read_bytes()).hexdigest()
                    if evidence["source_sha256"] != source_sha:
                        raise LiveGateError("LIVE_DUAL_RECOVERY_IMAGE_CHANGED")
                    _complete(flow, queue, item, source_sha)
                continue
            except (LiveGateError, OSError, sqlite3.Error, KeyError, ValueError):
                pass
        _fail(flow, queue, item, "LIVE_DUAL_WORKER_RESTART_UNCERTAIN", uncertain=True)
    return queue.dual_billing_unknown()
