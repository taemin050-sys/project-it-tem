"""One-shot, explicitly authorized live worker; no implicit retry or mock fallback.

Not started in the GCP demo. A cost-approved operator must configure AND
execute this process after verifying model entitlements and provider receipts.
"""
from __future__ import annotations

import os
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
    if os.environ.get("IT_TEM_LIVE_COST_POLICY")!="MONITOR_ONLY":
        raise LiveNotAuthorized("COST_POLICY_NOT_AUTHORIZED")
    actors=frozenset(x.strip() for x in
        os.environ.get("IT_TEM_LIVE_APPROVED_ACTORS","").split(",") if x.strip())
    if not actors or "*" in actors:
        raise LiveNotAuthorized("LIVE_ACTOR_ALLOWLIST_REQUIRED")
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
    model=os.environ.get("IT_TEM_IMAGE_MODEL","gpt-image-2.6-sunburst")
    # Keep legacy pinned requests valid and accept the Owner #23 v2.6 model.
    if model not in ("gpt-image-2.6-sunburst",
                     "gpt-image-2.5-sunburst-2026-09-08","gpt-image-2-2026-04-21"):
        raise LiveGateError("UNAPPROVED_IMAGE_MODEL")
    transport=OpenAIImagesAdapter(OpenAIImagesConfig(
        live_calls=True,api_key=os.environ["OPENAI_API_KEY"],timeout_seconds=120))
    processor=ExternalImageProcessor(
        LocalAssetStore(runtime/"image_assets"),transport,
        ProviderAttemptStore(runtime/"image_attempts.sqlite"),
        budget_limit_usd=price_cap,reservation_usd=reserve,monitoring_only=True)
    return BackendImageAdapter(processor,runtime/"image_bindings.sqlite",model=model)


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


def _run_locked(root:Path,flow:LivePipeline)->str:
    queue=LiveQueue(root/"live"/"queue.sqlite")
    # Any previous RUNNING attempt has ambiguous provider billing; hold it.
    queue.reconcile_restart()
    item=queue.claim("LIVE")
    if not item:return "NO_LIVE_TASK"
    actor,jid=item["actor"],item["job_id"]
    try:
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


def serve_loop(root:Path,interval:float=2.0):
    """One task per cycle, no recursive attempt and no backend mock fallback."""
    import time
    while True:
        status=run_once(root)
        if status=="LIVE_STAGE_HELD_FOR_RECONCILIATION":
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
