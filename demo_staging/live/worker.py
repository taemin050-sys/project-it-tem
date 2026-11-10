"""One-shot, explicitly authorized live worker; no implicit retry or mock fallback.

Not started in the GCP demo. A cost-approved operator must configure AND
execute this process after verifying model entitlements and provider receipts.
"""
from __future__ import annotations

import os
import json
import sqlite3
from pathlib import Path
from contextlib import contextmanager
import fcntl

from .pipeline import LivePipeline
from .queue import LiveQueue
from .contracts import LiveGateError
from demo_staging.live_safety import LiveNotAuthorized
from src.serving.job_store import JobStore


def policy_from_env(root:Path):
    # Deny even if the key exists; separate explicit PM gate required.
    approved=os.environ.get("IT_TEM_LIVE_EXECUTION_APPROVED")=="YES"
    live_enabled=os.environ.get("IT_TEM_LIVE_ENABLED")=="YES"
    if not (approved and live_enabled):
        raise LiveNotAuthorized("LIVE_WORKER_DISABLED")
    if os.environ.get("IT_TEM_PROVIDER_READINESS_CONFIRMED")!="YES":
        raise LiveNotAuthorized("PROVIDER_READINESS_NOT_CONFIRMED")
    if not os.environ.get("OPENAI_API_KEY"):
        raise LiveNotAuthorized("MODEL_CREDENTIAL_NOT_CONFIGURED")
    actors=frozenset(x.strip() for x in
        os.environ.get("IT_TEM_LIVE_APPROVED_ACTORS","").split(",") if x.strip())
    if not actors or "*" in actors:
        raise LiveNotAuthorized("LIVE_ACTOR_ALLOWLIST_REQUIRED")
    # New A-only hard-cap path is OFF by default and requires a genuine signed
    # PM cost decision, pinned candidate SHA, Signed SSO and all preinitialized
    # ledgers. Never fall back to the legacy MONITOR_ONLY path on failure.
    if os.environ.get("IT_TEM_A51C_HARD_CAP_ENABLE")=="YES":
        from .a51c_signed_cost_authority import (
            signed_hard_cap_policy,require_preinitialized_candidate_ledgers)
        signed=signed_hard_cap_policy(root)
        require_preinitialized_candidate_ledgers(root)
        return LivePipeline(root/"live",JobStore(root/"jobs"),live_enabled=True,
            pm_authorized=True,approved_actors=signed["approved_actors"],
            request_limit=signed["max_requests"],budget_limit_usd=signed["budget_usd"],
            text_reservation_usd=signed["text_reservation_usd"],
            image_reservation_usd=signed["image_reservation_usd"],
            monitoring_only=False)
    if os.environ.get("IT_TEM_LIVE_COST_POLICY")!="MONITOR_ONLY":
        raise LiveNotAuthorized("COST_POLICY_NOT_AUTHORIZED")
    return LivePipeline(root/"live",JobStore(root/"jobs"),live_enabled=True,
        pm_authorized=True,approved_actors=actors,monitoring_only=True)


def live_image_adapter(runtime:Path,request):
    """Owner's native paid ledger, no new HTTP clients or custom image runtime."""
    import uuid
    from src.image_generation.assets import LocalAssetStore
    from src.image_generation.api_image_processor import ExternalImageProcessor
    from src.image_generation.provider_attempts import ProviderAttemptStore
    from src.image_generation.openai_images import OpenAIImagesAdapter,OpenAIImagesConfig
    from src.image_generation.backend_adapter import BackendImageAdapter

    price_cap="0"
    reserve="0"
    monitoring=True
    if os.environ.get("IT_TEM_A51C_HARD_CAP_ENABLE")=="YES":
        from .a51c_signed_cost_authority import (
            signed_hard_cap_policy,require_preinitialized_candidate_ledgers)
        candidate_root=runtime.parent.parent
        signed=signed_hard_cap_policy(candidate_root)
        require_preinitialized_candidate_ledgers(candidate_root)
        price_cap=signed["budget_usd"]
        reserve=signed["image_reservation_usd"]
        monitoring=False
    from .image_runtime_profile import effective_image_profile
    profile=effective_image_profile()
    transport=OpenAIImagesAdapter(OpenAIImagesConfig(
        live_calls=True,api_key=os.environ["OPENAI_API_KEY"],timeout_seconds=120))
    processor=ExternalImageProcessor(
        LocalAssetStore(runtime/"image_assets"),transport,
        ProviderAttemptStore(runtime/"image_attempts.sqlite"),
        budget_limit_usd=price_cap,reservation_usd=reserve,monitoring_only=monitoring)
    return BackendImageAdapter(processor,runtime/"image_bindings.sqlite",
        model=profile["model"],quality=profile["quality"],
        complexity=profile["complexity"])


@contextmanager
def exclusive_live_worker(root:Path):
    """Cross-process single flight on one host, held throughout provider I/O.

    The recovery scan must never run while another worker is active: doing
    so would incorrectly mark its active submission as uncertain and permit
    a second paid call.
    """
    lock_path=Path(root)/"live"/"worker.lock"
    lock_path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(lock_path,os.O_RDWR|os.O_CREAT,0o600)
    acquired=False
    try:
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            acquired=True
        except BlockingIOError:
            raise LiveNotAuthorized("LIVE_WORKER_ALREADY_RUNNING") from None
        yield
    finally:
        if acquired:
            fcntl.flock(fd,fcntl.LOCK_UN)
        os.close(fd)


def run_once(root:Path)->str:
    # Must run BEFORE queue claim: disabled worker must NOT consume a task.
    flow=policy_from_env(root)
    with exclusive_live_worker(root):
        return _run_locked(root,flow)



# A2: trusted web ACL is persisted in demo.sqlite3, not carried by Queue.
# The worker must verify BOTH the live job and the original web-claimed job.
_STAGE_STATES={
    "analysis":frozenset({"INPUT_STORED"}),
    "copy_revision":frozenset({"COPY_REVIEW_REQUIRED"}),
    "image_prompt":frozenset({"COPY_APPROVED"}),
    "image":frozenset({"PROMPT_READY"}),
}


def authorize_worker_item(flow:LivePipeline,item:dict) -> dict:
    """Server-side last-mile auth; a queued Actor string is not authority."""
    actor,jid,stage=item["actor"],item["job_id"],item["stage"]
    cost_mode=os.environ.get("IT_TEM_LIVE_COST_POLICY")
    beta_cap=(os.environ.get("IT_TEM_A51C_HARD_CAP_ENABLE")=="YES")
    if (not flow.live_enabled or not flow.pm_authorized or
            actor not in flow.approved_actors or
            os.environ.get("IT_TEM_LIVE_ENABLED")!="YES" or
            os.environ.get("IT_TEM_LIVE_EXECUTION_APPROVED")!="YES" or
            os.environ.get("IT_TEM_PROVIDER_READINESS_CONFIRMED")!="YES" or
            (cost_mode!="HARD_CAP" if beta_cap else cost_mode!="MONITOR_ONLY") or
            (beta_cap and flow.monitoring_only) or
            actor not in {x.strip() for x in
                os.environ.get("IT_TEM_LIVE_APPROVED_ACTORS","").split(",") if x.strip()}):
        raise LiveGateError("WORKER_ACTOR_REVOKED_OR_DISABLED")
    if beta_cap:
        from .a51c_signed_cost_authority import (
            signed_hard_cap_policy, require_preinitialized_candidate_ledgers)
        signed=signed_hard_cap_policy(flow.root.parent)
        require_preinitialized_candidate_ledgers(flow.root.parent)
        if (actor not in signed["approved_actors"]
            or flow.cost.budget_usd!=round(float(signed["budget_usd"])*1_000_000)
            or flow.cost.max_requests!=signed["max_requests"]
            or flow.text_reservation!=float(signed["text_reservation_usd"])
            or flow.image_reservation!=float(signed["image_reservation_usd"])):
            raise LiveGateError("A51C_HARD_CAP_RUNTIME_CONFIG_DRIFT")
    if stage not in _STAGE_STATES or item.get("mode")!="LIVE":
        raise LiveGateError("WORKER_STAGE_NOT_AUTHORIZED")
    # The read-only application ledger is the Actor ownership SSOT, separate
    # from the queue and LiveStore. Missing DB/table/row fails closed.
    try:
        with sqlite3.connect(flow.root.parent/"demo.sqlite3",timeout=10) as db:
            owned=db.execute("SELECT actor FROM jobs WHERE job_id=?",(jid,)).fetchone()
        if owned is None or owned[0]!=actor:
            raise LiveGateError("WORKER_JOB_OWNER_REVOKED")
        original=flow.jobs.get_job(jid)
        if (original.get("job_id")!=jid or
                original.get("status") in {"CANCELLED","CANCELED","DELETED","FAILED"}):
            raise LiveGateError("WORKER_ORIGINAL_JOB_INACTIVE")
        job=flow.state.get(actor,jid)
    except (sqlite3.Error,OSError,KeyError,ValueError) as exc:
        if isinstance(exc,LiveGateError):raise
        raise LiveGateError("WORKER_IDENTITY_UNVERIFIABLE") from None
    except Exception:
        raise LiveGateError("WORKER_ORIGINAL_JOB_UNAVAILABLE") from None
    if beta_cap:
        from .a51b_signed_beta_contract import (
            BETA_PREFIX,verify_frozen_runtime_activation)
        frozen=flow.state.template(actor,jid)
        if not frozen or not str(frozen.get("profile_id","")).startswith(BETA_PREFIX):
            raise LiveGateError("A51C_HARD_CAP_SIGNED_BETA_JOB_REQUIRED")
        zone=frozen.get("safe_zone")
        # A5-1B layout signatures do NOT authorize customer-image rights,
        # verified object/label masks or paid Provider submissions.
        # In the currently accepted A51B contract all four are FALSE:
        # consequently even a genuinely signed fixture cannot spend.
        required=("real_provider_permitted","real_customer_assets_permitted",
                  "candidate_mask_verified","rights_review_verified")
        if type(zone) is not dict or any(zone.get(k) is not True for k in required):
            raise LiveGateError("A51C_HARD_CAP_PRODUCT_RIGHTS_NOT_AUTHORIZED")
        # Even an attacker-forged DB row with all four booleans True cannot
        # substitute for a genuine reverified Owner+PM profile decision.
        verify_frozen_runtime_activation(frozen)
    if job["state"] not in _STAGE_STATES[stage] or (
            job["mode"]!="LIVE" and
            not (stage=="analysis" and job["mode"]=="INPUT_ONLY")):
        raise LiveGateError("WORKER_JOB_STAGE_OR_PROVENANCE_CHANGED")
    if stage=="analysis":
        expected=job["input_sha"]
    elif stage=="copy_revision":
        # The revision payload is separately revalidated in dispatch branch.
        expected=item["context_sha"]
    elif stage=="image_prompt":
        flow.state._approved(job)
        from .contracts import digest
        expected=digest(flow.state.prompt_context(actor,jid))
    else:
        flow.state._approved(job)
        attempt=flow.state.current_image_attempt(actor,jid)
        from .contracts import digest
        expected=(digest({"approval_sha":job["approval_sha"],
            "attempt_id":attempt["attempt_id"]})
            if attempt and attempt["attempt_version"]>1 else job["approval_sha"])
    if item["context_sha"]!=expected:
        raise LiveGateError("WORKER_JOB_CONTEXT_CHANGED")
    return job


def reconcile_worker_ledgers(queue:LiveQueue,flow:LivePipeline)->bool:
    """Never restart provider work with an unresolved cross-DB attempt.

    Under the host singleflight lock, reconcile each SQLite independently:
    no cross-file atomic commit is falsely assumed. Repeat is idempotent.
    Any ambiguous queue OR ledger row blocks all new paid claims pending
    human reconciliation. RESERVED is included (crash after reservation).
    """
    flow.cost.reconcile_crashed_dispatches()
    queue.reconcile_restart()
    try:
        with queue.db() as db:
            bad_q=db.execute("""SELECT COUNT(*) FROM queued_ops
                WHERE mode='LIVE' AND state='BILLING_UNKNOWN'""").fetchone()[0]
        with flow.cost.connect() as db:
            bad_cost=db.execute("""SELECT COUNT(*) FROM attempts
                WHERE status IN ('RESERVED','DISPATCHED','BILLING_UNKNOWN')
                   OR billing_unknown!=0""").fetchone()[0]
        # Third, independent Owner Image attempt ledger. A submitting,
        # failed or unknown provider attempt cannot be ignored merely
        # because the aggregate cost ledger has no outstanding row.
        image_file=flow.root/"owner_image"/"image_attempts.sqlite"
        bad_image=0
        if image_file.exists():
            with sqlite3.connect(f"file:{image_file}?mode=ro",uri=True) as db:
                bad_image=db.execute("""SELECT COUNT(*) FROM provider_attempts
                    WHERE state IN ('submitting','unknown','failed')""").fetchone()[0]
        return bool(bad_q or bad_cost or bad_image)
    except (sqlite3.Error,OSError):
        # A missing/corrupt schema is NOT permission to submit again.
        return True

def _run_locked(root:Path,flow:LivePipeline)->str:
    queue=LiveQueue(root/"live"/"queue.sqlite")
    # The host singleflight lock MUST protect this cross-ledger scan.
    if reconcile_worker_ledgers(queue,flow):
        return "LIVE_WORKER_BILLING_HOLD"
    item=queue.claim("LIVE")
    if not item:return "NO_LIVE_TASK"
    actor,jid=item["actor"],item["job_id"]
    try:
        authorize_worker_item(flow,item)
        # Re-evaluate immediately before each actual paid dispatch via
        # LivePipeline._guarded (no trusted browser Actor strings).
        flow._worker_claim=item
        if item["stage"]=="analysis":
            result=flow.text(actor,jid,offline=False,
                text_model=os.environ.get("IT_TEM_TEXT_MODEL","gpt-6-luna"),
                vision_model=os.environ.get("IT_TEM_VISION_MODEL","gpt-6-luna"))
            result_sha=result["copy_sha"]
        elif item["stage"]=="copy_revision":
            from .contracts import digest
            payload=queue.revision_payload(item["id"])
            text_model=os.environ.get("IT_TEM_TEXT_MODEL","gpt-6-luna")
            context=flow.revision_context(
                actor,jid,payload["instruction"],
                payload["expected_generation"],payload["expected_review_sha"],
                text_model=text_model)
            if digest(context)!=item["context_sha"]:
                raise LiveGateError("REVISION_CONTEXT_SHA_MISMATCH")
            result=flow.revise_copy(
                actor,jid,payload["instruction"],payload["expected_generation"],
                payload["expected_review_sha"],offline=False,text_model=text_model)
            result_sha=result["review_sha"]
        elif item["stage"]=="image_prompt":
            result=flow.prompt(actor,jid,offline=False,
                text_model=os.environ.get("IT_TEM_TEXT_MODEL","gpt-6-luna"))
            from .contracts import digest
            import json
            result_sha=digest(json.loads(result["prompt_json"]))
        elif item["stage"]=="image":
            from uuid import uuid5
            from .contracts import digest
            job=flow.state.get(actor,jid)
            current=flow.state.current_image_attempt(actor,jid)
            retry=current is not None and current["attempt_version"]>1
            expected_context=(digest({"approval_sha":job["approval_sha"],
                "attempt_id":current["attempt_id"]}) if retry else job["approval_sha"])
            if item["context_sha"]!=expected_context:
                raise LiveGateError("IMAGE_ATTEMPT_QUEUE_CONTEXT_CHANGED")
            if retry and (current["state"]!="REQUESTED" or
                          current["approval_sha"]!=job["approval_sha"]):
                raise LiveGateError("IMAGE_ATTEMPT_NOT_REQUESTED")
            from .contracts import assert_single_image_scope
            import json
            assert_single_image_scope(json.loads(job["input_json"]))
            req=flow.image_input(actor,jid)
            adapter=live_image_adapter(root/"live"/"owner_image",req)
            fingerprint={"copy_sha":req.copy_hash,"revision":req.copy_revision,
                         "image_model":adapter.model}
            # Distinct Owner project UUID and attempt fingerprint prevent
            # replaying the old immutable provider binding on an explicit retry.
            project_id=flow.project_id
            if retry:
                fingerprint["image_attempt_id"]=current["attempt_id"]
                project_id=uuid5(flow.project_id,"image-attempt/"+current["attempt_id"])
            result=flow._guarded(actor,jid,"image",fingerprint,
                lambda:adapter.generate(req,project_id=project_id),image=True)
            committed=flow.accept_image_result(actor,jid,result,offline=False)
            result_sha=committed["image_sha"]
        else:
            raise LiveGateError("INVALID_WORK_STAGE")
        queue.complete(item["id"],result_sha)
        return "LIVE_STAGE_COMMITTED"
    except BaseException as exc:
        code=exc.code if isinstance(exc,LiveGateError) else "WORKER_ATTEMPT_UNCERTAIN"
        queue.interrupt(item["id"],code)
        # No hidden retry, no provider traceback/secret in HTTP output.
        return "LIVE_STAGE_HELD_FOR_RECONCILIATION"
    finally:
        if hasattr(flow,"_worker_claim"):
            del flow._worker_claim


def serve_loop(root:Path,interval:float=2.0):
    """One task per cycle, no recursive attempt and no backend mock fallback."""
    import time
    while True:
        status=run_once(root)
        if status in ("LIVE_STAGE_HELD_FOR_RECONCILIATION","LIVE_WORKER_BILLING_HOLD"):
            # A charged or ambiguous failure is a hard safety stop, unrelated
            # to monetary project threshold. Requires manual incident review.
            return status
        time.sleep(interval)


if __name__=="__main__":
    import sys
    from .env_loader import load_from_fixed_path
    try:
        load_from_fixed_path(worker=True)
    except Exception:
        print("OPENAI_ENV_NOT_READY")
        raise SystemExit(4)
    base=os.environ.get("IT_TEM_DEMO_ROOT")
    if not base:raise SystemExit("IT_TEM_DEMO_ROOT_REQUIRED")
    try:
        root=Path(base)/"runtime"
        print(serve_loop(root) if "--loop" in sys.argv[1:] else run_once(root),
              flush=True)
    except LiveNotAuthorized:
        print("LIVE_WORKER_DISABLED_OR_NOT_APPROVED")
        raise SystemExit(4)
