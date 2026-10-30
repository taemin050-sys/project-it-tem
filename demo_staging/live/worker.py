"""One-shot, explicitly authorized live worker; no implicit retry or mock fallback.

Not started in the GCP demo. A cost-approved operator must configure AND
execute this process after verifying model entitlements and provider receipts.
"""
from __future__ import annotations

import os
from pathlib import Path

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
    budget=os.environ.get("IT_TEM_LIVE_BUDGET_USD","0")
    t=os.environ.get("IT_TEM_TEXT_RESERVATION_USD","0")
    i=os.environ.get("IT_TEM_IMAGE_RESERVATION_USD","0")
    n=int(os.environ.get("IT_TEM_LIVE_REQUEST_LIMIT","0"))
    if n<=0 or min(float(budget),float(t),float(i))<=0:
        raise LiveNotAuthorized("LIVE_BUDGET_NOT_CONFIGURED")
    actors=frozenset(x.strip() for x in
         os.environ.get("IT_TEM_LIVE_APPROVED_ACTORS","").split(",") if x.strip())
    if not actors or "*" in actors:
        raise LiveNotAuthorized("LIVE_ACTOR_ALLOWLIST_REQUIRED")
    return LivePipeline(root/"live",JobStore(root/"jobs"),live_enabled=True,
        pm_authorized=True,budget_limit_usd=float(budget),
        text_reservation_usd=float(t),image_reservation_usd=float(i),
        request_limit=n,approved_actors=actors)


def live_image_adapter(runtime:Path,request):
    """Owner's native paid ledger, no new HTTP clients or custom image runtime."""
    import uuid
    from src.image_generation.assets import LocalAssetStore
    from src.image_generation.api_image_processor import ExternalImageProcessor
    from src.image_generation.provider_attempts import ProviderAttemptStore
    from src.image_generation.openai_images import OpenAIImagesAdapter,OpenAIImagesConfig
    from src.image_generation.backend_adapter import BackendImageAdapter

    price_cap=os.environ["IT_TEM_LIVE_BUDGET_USD"]
    reserve=os.environ["IT_TEM_IMAGE_RESERVATION_USD"]
    model=os.environ.get("IT_TEM_IMAGE_MODEL","gpt-image-2.5-sunburst-2026-09-08")
    # Exact two models permitted by official Image Owner DTO at PR #17.
    if model not in ("gpt-image-2.5-sunburst-2026-09-08","gpt-image-2-2026-04-21"):
        raise LiveGateError("UNAPPROVED_IMAGE_MODEL")
    transport=OpenAIImagesAdapter(OpenAIImagesConfig(
        live_calls=True,api_key=os.environ["OPENAI_API_KEY"],timeout_seconds=120))
    processor=ExternalImageProcessor(
        LocalAssetStore(runtime/"image_assets"),transport,
        ProviderAttemptStore(runtime/"image_attempts.sqlite"),
        budget_limit_usd=price_cap,reservation_usd=reserve)
    return BackendImageAdapter(processor,runtime/"image_bindings.sqlite",model=model)


def run_once(root:Path)->str:
    # Must run BEFORE queue claim: disabled worker must NOT consume a task.
    flow=policy_from_env(root)
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
        elif item["stage"]=="image_prompt":
            result=flow.prompt(actor,jid,offline=False,
                text_model=os.environ.get("IT_TEM_TEXT_MODEL","gpt-6-luna"))
            from .contracts import digest
            import json
            result_sha=digest(json.loads(result["prompt_json"]))
        elif item["stage"]=="image":
            req=flow.image_input(actor,jid)
            adapter=live_image_adapter(root/"live"/"owner_image",req)
            result=flow._guarded(actor,jid,"image",{
                "copy_sha":req.copy_hash,"revision":req.copy_revision,
                "image_model":adapter.model},
                lambda:adapter.generate(req,project_id=flow.project_id),
                image=True)
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


if __name__=="__main__":
    base=os.environ.get("IT_TEM_DEMO_ROOT")
    if not base:raise SystemExit("IT_TEM_DEMO_ROOT_REQUIRED")
    try:
        print(run_once(Path(base)/"runtime"))
    except LiveNotAuthorized:
        print("LIVE_WORKER_DISABLED_OR_NOT_APPROVED")
        raise SystemExit(4)
