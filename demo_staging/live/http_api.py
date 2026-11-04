"""Provisional isolated /demo/api/live prefix; never modifies official B0 11 operations.

All write/read endpoints require application login and ownership. No fixture or
fake provider mode is exposed by HTTP. Live dispatch is default-off by policy.
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from fastapi import FastAPI,HTTPException,Request
from fastapi.responses import FileResponse,JSONResponse
from pydantic import BaseModel,ConfigDict,Field

from .contracts import LiveGateError
from .pipeline import LivePipeline
from .queue import LiveQueue
from .reviews import LiveShares
from demo_staging.app import ReviewBody
from demo_staging.live_safety import LiveNotAuthorized


class InputPayload(BaseModel):
    model_config=ConfigDict(extra="forbid",strict=True)
    product: dict
    customer_request_id: str


class CopyUpdate(BaseModel):
    model_config=ConfigDict(extra="forbid",strict=True)
    copy_output:dict


class CopyRevisionRequest(BaseModel):
    model_config=ConfigDict(extra="forbid",strict=True)
    instruction:str=Field(min_length=1,max_length=500)
    expected_generation:int
    expected_review_sha:str=Field(min_length=64,max_length=64)


class CopyRestoreRequest(BaseModel):
    model_config=ConfigDict(extra="forbid",strict=True)
    expected_generation:int
    expected_review_sha:str=Field(min_length=64,max_length=64)


class CopyApproval(BaseModel):
    model_config=ConfigDict(extra="forbid",strict=True)
    expected_generation:int
    expected_review_sha:str
    acknowledge_evidence:bool=False


class ImageApproval(BaseModel):
    model_config=ConfigDict(extra="forbid",strict=True)
    image_sha:str


class ComposeRequest(BaseModel):
    model_config=ConfigDict(extra="forbid",strict=True)
    layout:dict|None=None


def web_queue_policy() -> dict:
    """Queue-only PM policy. Web must never possess API credentials.

    Live remains entirely OFF unless all explicit controls agree. Worker
    independently validates the key and identical PM/cost configuration.
    """
    required=("IT_TEM_LIVE_WEB_QUEUE_ENABLED","IT_TEM_LIVE_ENABLED",
              "IT_TEM_LIVE_EXECUTION_APPROVED","IT_TEM_PROVIDER_READINESS_CONFIRMED")
    if any(os.environ.get(k)!="YES" for k in required):
        return {"enabled":False,"actors":frozenset()}
    actors=frozenset(x.strip() for x in
        os.environ.get("IT_TEM_LIVE_APPROVED_ACTORS","").split(",") if x.strip())
    if (os.environ.get("IT_TEM_LIVE_COST_POLICY")!="MONITOR_ONLY"
            or not actors or "*" in actors
            or any(not x.replace("_","").replace("-","").isalnum() for x in actors)):
        return {"enabled":False,"actors":frozenset()}
    return {"enabled":True,"actors":actors}


def register_live_api(app:FastAPI, ledger, runtime_root:Path, cookie_name:str):
    policy=web_queue_policy()
    flow=LivePipeline(Path(runtime_root)/"live",app.state.job_store,
        live_enabled=policy["enabled"],pm_authorized=policy["enabled"],
        approved_actors=policy["actors"],
        request_limit=policy.get("limit",0),budget_limit_usd=policy.get("budget",0),
        text_reservation_usd=policy.get("text",0),
        image_reservation_usd=policy.get("image",0),
        monitoring_only=policy["enabled"])
    queue=LiveQueue(Path(runtime_root)/"live"/"queue.sqlite")
    shares=LiveShares(Path(runtime_root)/"live"/"shares.sqlite")
    app.state.live_pipeline=flow
    app.state.live_queue=queue
    prefix="/demo/api/live"

    def authorized(request,job_id=None):
        ident=app.state.demo_request_identity(request)
        if not ident:
            raise HTTPException(status_code=401,detail="Login required")
        actor=ident[0]
        if job_id and not ledger.owns(actor,job_id):
            raise HTTPException(status_code=404,detail="Job not found")
        return actor

    def safe_error(error):
        if isinstance(error,LiveNotAuthorized):
            return HTTPException(status_code=423,detail="LIVE_PROVIDER_NOT_APPROVED")
        if isinstance(error,LiveGateError):
            code=error.code
            return HTTPException(status_code=409 if ("STATE" in code or "STALE" in code or
                             "APPROVAL" in code or "CONFLICT" in code or
                             code=="REAL_COMPLIANCE_BLOCKED") else 422,
                                detail={"code":code})
        return HTTPException(status_code=503,detail="LIVE_GATE_UNAVAILABLE")

    def visible(job):
        profile=flow.state.template(job["actor"],job["job_id"])
        # Never return internal Provider errors, signed URLs, input file paths
        # or private reference image contents to the browser.
        out={"job_id":job["job_id"],"state":job["state"],"mode":job["mode"],
             "generation":job["generation"],"input_sha":job["input_sha"],
             "copy_sha":job["copy_sha"],"review_sha":job["review_sha"],
             "image_sha":job["image_sha"],"final_sha":job["final_sha"],"caption_sha":job["caption_sha"],
             "approval_current":bool(job["approval_sha"]),
             "previous_copy_available":flow.state.previous_copy_available(job["actor"],job["job_id"]),
             "template_profile":profile["profile_id"] if profile else "PRE_POLICY_LEGACY",
             "functional_types":json.loads(job["input_json"])["product"].get("functional_types",[]),
             "functional_types_status":"OWNER_TEXT_DTO_PENDING"
                if json.loads(job["input_json"])["product"].get("functional_types") else "NO_SELECTION",
             "product_protection_status":"MANUAL_REVIEW_REQUIRED"
                if job["state"]=="COMPLETED" else "NOT_REVIEWED"}
        for stored,key in (("research_display_json","research_display"),
                           ("analysis_json","analysis"),
                           ("copy_json","copy"),
                           ("compliance_json","compliance"),
                           ("prompt_json","image_prompt")):
            if job[stored] is not None:
                out[key]=json.loads(job[stored])
        return out

    # Isolated developer QA fixture path. NOT a Live Provider substitute:
    # requires an explicit process permit, loopback-only request, and a QA
    # identity. It is never enabled by the team's normal serving process.
    qa_enabled=(os.environ.get("IT_TEM_QA_FIXTURE_ENABLED")=="YES"
                and os.environ.get("IT_TEM_LIVE_ENABLED")=="NO"
                and os.environ.get("IT_TEM_LIVE_EXECUTION_APPROVED")=="NO"
                and os.environ.get("IT_TEM_DEMO_SECURE_COOKIE")=="NO")
    qa_actors=frozenset(x.strip() for x in
          os.environ.get("IT_TEM_QA_ALLOWED_ACTORS","").split(",") if x.strip())

    def qa_access(request,job_id):
        if not qa_enabled or not qa_actors:
            raise HTTPException(404,"QA fixture endpoint disabled")
        if not request.client or request.client.host not in ("127.0.0.1","::1"):
            raise HTTPException(404,"QA fixture endpoint unavailable")
        actor=authorized(request,job_id)
        if actor not in qa_actors:
            raise HTTPException(404,"QA fixture actor unavailable")
        return actor

    @app.post("/demo/api/qa/jobs/{job_id}/text")
    def qa_text(job_id:str,request:Request):
        actor=qa_access(request,job_id)
        try:
            from tests.demo_live.test_pipeline import FakeOwner
            current=flow.state.get(actor,job_id)
            if current["state"]!="INPUT_STORED":
                raise LiveGateError("QA_TEXT_STATE_CONFLICT")
            product=json.loads(current["input_json"])["product"]
            if product.get("brand_name")!="라움":
                raise LiveGateError("QA_FIXTURE_REQUIRES_RAUM_TEST_BRAND")
            # Existing official DTOs, real compliance, no external provider.
            return visible(flow.text(actor,job_id,FakeOwner(),offline=True))
        except (LiveGateError,ValueError) as e:raise safe_error(e) from None

    @app.post("/demo/api/qa/jobs/{job_id}/prompt-image")
    def qa_prompt_image(job_id:str,request:Request):
        actor=qa_access(request,job_id)
        try:
            from tests.demo_live.test_pipeline import FakeOwner,png
            from src.image_generation.backend_adapter import BackendGeneratedImage
            import hashlib
            job=flow.state.get(actor,job_id)
            if job["state"]=="COPY_APPROVED":
                flow.prompt(actor,job_id,FakeOwner(),offline=True)
            owner_request=flow.image_input(actor,job_id)
            if owner_request.safe_zone is None:
                raise LiveGateError("QA_A_SAFE_ZONE_REQUIRED")
            # Synthetic pixel image, not an OpenAI result. Immutable copy and
            # candidate SHA still go through the real Serving binding gate.
            img=png((215,225,235),size=(1152,1440))
            candidate=BackendGeneratedImage(
                image_bytes=img,mime_type="image/png",width=1152,height=1440,
                sha256=hashlib.sha256(img).hexdigest(),job_id=job_id,
                copy_revision=owner_request.copy_revision,
                copy_hash=owner_request.copy_hash,mock=True,
                receipt={"mode":"OFFLINE_FIXTURE","provider_calls":0})
            return visible(flow.accept_image_result(actor,job_id,candidate,offline=True))
        except (LiveGateError,ValueError) as e:raise safe_error(e) from None

    @app.post("/demo/api/qa/jobs/{job_id}/compose")
    def qa_compose(job_id:str,body:ComposeRequest,request:Request):
        actor=qa_access(request,job_id)
        j=flow.state.get(actor,job_id)
        if j["mode"]!="OFFLINE_FIXTURE":
            raise HTTPException(409,"QA_REQUIRES_OFFLINE_FIXTURE")
        try:
            font=Path(os.environ.get("IT_TEM_LIVE_KOREAN_FONT",
                "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"))
            return visible(flow.compose(actor,job_id,layout=body.layout,font_path=font))
        except (LiveGateError,ValueError) as e:raise safe_error(e) from None
        except (OSError,sqlite3.Error):
            raise HTTPException(503,"QA_COMPOSITION_STORAGE_UNAVAILABLE") from None

    @app.get("/demo/api/qa/jobs/{job_id}/artifacts/{kind}")
    def qa_artifact(job_id:str,kind:str,request:Request):
        actor=qa_access(request,job_id)
        j=flow.state.get(actor,job_id)
        if j["mode"]!="OFFLINE_FIXTURE":
            raise HTTPException(409,"QA_REQUIRES_OFFLINE_FIXTURE")
        import hashlib
        if kind=="candidate":
            if j["state"] not in ("IMAGE_REVIEW_REQUIRED","IMAGE_APPROVED"):
                raise HTTPException(409,"QA_IMAGE_NOT_READY")
            target=flow.image_path(job_id)
            expected=j["image_sha"]
            media="image/png"
        elif kind in ("final","caption"):
            if j["state"]!="COMPLETED":
                raise HTTPException(409,"QA_COMPOSITION_NOT_COMPLETED")
            try:flow.validate_final_artifacts(actor,job_id)
            except LiveGateError:
                raise HTTPException(503,"QA_ARTIFACT_INTEGRITY_ERROR") from None
            target=flow.root/"outputs"/job_id/("final.png" if kind=="final" else "caption.txt")
            expected=j["final_sha"] if kind=="final" else j["caption_sha"]
            media="image/png" if kind=="final" else "text/plain; charset=utf-8"
        else:
            raise HTTPException(404,"QA_ARTIFACT_NOT_FOUND")
        try:
            if not expected or hashlib.sha256(target.read_bytes()).hexdigest()!=expected:
                raise ValueError
        except (OSError,ValueError):
            raise HTTPException(503,"QA_ARTIFACT_INTEGRITY_ERROR") from None
        return FileResponse(target,media_type=media,filename=target.name,
            headers={"Cache-Control":"private,no-store",
                     "X-IT-TEM-Provenance":"OFFLINE_FIXTURE"})

    @app.get(prefix+"/capabilities")
    def capabilities(request:Request):
        actor=authorized(request)
        allowed=bool(flow.live_enabled and flow.pm_authorized
                     and actor in flow.approved_actors)
        return {"live_enabled":allowed,
                "mode":"LIVE_QUEUE_READY" if allowed else "LIVE_BLOCKED",
                "reason":None if allowed else "COST_AND_CONTRACT_PM_GATE",
                "provisional_wire":True,"mock_fallback":False}

    @app.post(prefix+"/jobs/{job_id}/input")
    def create_input(job_id:str,body:InputPayload,request:Request):
        actor=authorized(request,job_id)
        try:
            return visible(flow.prepare(actor,job_id,body.model_dump(mode="json"),
                                        template_profile="A"))
        except (LiveGateError,ValueError) as e:
            raise safe_error(e) from None

    @app.get(prefix+"/jobs/{job_id}")
    def get_job(job_id:str,request:Request):
        actor=authorized(request,job_id)
        try:
            job=flow.state.get(actor,job_id)
            if job["state"]=="COMPLETED":
                # Avoid advertising a corrupted finished Job as downloadable.
                flow.validate_final_artifacts(actor,job_id)
            return visible(job)
        except LiveGateError as e:
            if e.code.startswith(("COMPOSITION_MANIFEST_",
                                  "COMPOSITION_RECEIPT_",
                                  "FINAL_ARTIFACT_",
                                  "TEMPLATE_POLICY_")):
                raise HTTPException(503,detail="Artifact integrity unavailable") from None
            raise safe_error(e) from None

    @app.post(prefix+"/jobs/{job_id}/queue-text")
    def queue_text(job_id:str,request:Request):
        actor=authorized(request,job_id)
        if not (flow.live_enabled and flow.pm_authorized and
                actor in flow.approved_actors):
            raise HTTPException(status_code=423,detail="LIVE_PROVIDER_NOT_APPROVED")
        j=flow.state.get(actor,job_id)
        if j["state"]!="INPUT_STORED":
            raise HTTPException(status_code=409,detail="LIVE_TEXT_STATE_CONFLICT")
        task,new=queue.enqueue(actor=actor,job_id=job_id,stage="analysis",
                               context_sha=j["input_sha"],mode="LIVE")
        return JSONResponse({"task_id":task["id"],"state":task["state"],
                             "new":new},status_code=202)

    @app.get(prefix+"/jobs/{job_id}/task-status")
    def latest_task_for_owner(job_id:str,request:Request):
        actor=authorized(request,job_id)
        try:flow.state.get(actor,job_id)
        except LiveGateError as e:raise safe_error(e) from None
        with queue.db() as db:
            last=db.execute("""SELECT id,job_id,stage,state,error_code,mode
                FROM queued_ops WHERE actor=? AND job_id=?
                ORDER BY created_at DESC,rowid DESC LIMIT 1""",
                (actor,job_id)).fetchone()
        return {"task":({"task_id":last["id"],"job_id":last["job_id"],
                         "stage":last["stage"],"state":last["state"],
                         "mode":last["mode"],"error_code":last["error_code"]}
                        if last is not None else None)}

    @app.post(prefix+"/jobs/{job_id}/copy")
    def edit_copy(job_id:str,body:CopyUpdate,request:Request):
        actor=authorized(request,job_id)
        try:return visible(flow.state.edit_copy(actor,job_id,body.copy_output))
        except (LiveGateError,ValueError) as e:raise safe_error(e) from None

    @app.post("/demo/api/qa/jobs/{job_id}/revise-copy")
    def qa_revision_copy(job_id:str,body:CopyRevisionRequest,request:Request):
        actor=qa_access(request,job_id)
        try:
            current=flow.state.get(actor,job_id)
            if current["mode"]!="OFFLINE_FIXTURE":
                raise LiveGateError("QA_REQUIRES_OFFLINE_FIXTURE")
            if current["state"]!="COPY_REVIEW_REQUIRED":
                raise LiveGateError("COPY_REVISION_STATE_CONFLICT")
            # Deterministic, named OFFLINE_FIXTURE candidate only. This does
            # NOT represent an AI model following the user's instruction.
            from copy import deepcopy
            original=json.loads(current["copy_json"])
            proposed=deepcopy(original)
            options=(
                ("매일 산뜻하게","가벼운 데일리 보습 루틴","자세히 보기"),
                ("촉촉한 하루","편안한 수분 케어의 시작","지금 만나기"),
                ("매일 수분 케어","산뜻하게 마무리되는 보습","제품 살펴보기"),
            )
            n=int(current["generation"])%len(options)
            headline,subline,cta=options[n]
            proposed["ad_copy"]={"headline":headline,"subline":subline,"cta":cta}
            proposed["caption"]=f"{headline}. {subline}. {cta}."
            updated=flow.state.apply_copy_revision(
                actor,job_id,proposed,body.instruction,
                body.expected_generation,body.expected_review_sha)
            return visible(updated)
        except (LiveGateError,ValueError) as e:raise safe_error(e) from None

    @app.post("/demo/api/qa/jobs/{job_id}/restore-copy")
    def qa_restore_copy(job_id:str,body:CopyRestoreRequest,request:Request):
        actor=qa_access(request,job_id)
        try:
            current=flow.state.get(actor,job_id)
            if current["mode"]!="OFFLINE_FIXTURE":
                raise LiveGateError("QA_REQUIRES_OFFLINE_FIXTURE")
            return visible(flow.state.restore_previous_copy(
                actor,job_id,body.expected_generation,body.expected_review_sha))
        except (LiveGateError,ValueError) as e:raise safe_error(e) from None

    @app.post(prefix+"/jobs/{job_id}/revise-copy")
    def paid_revision_requires_owner_contract(job_id:str,body:CopyRevisionRequest,request:Request):
        authorized(request,job_id)
        # The Text Owner's instruction-aware paid revision contract is not
        # accepted yet. Never substitute a fake answer, direct user edit, or
        # unaudited provider call into a live request.
        raise HTTPException(status_code=423,detail="TEXT_OWNER_LIVE_REVISION_CONTRACT_PENDING")

    @app.post(prefix+"/jobs/{job_id}/restore-copy")
    def live_restore_copy(job_id:str,body:CopyRestoreRequest,request:Request):
        actor=authorized(request,job_id)
        try:
            return visible(flow.state.restore_previous_copy(
                actor,job_id,body.expected_generation,body.expected_review_sha))
        except (LiveGateError,ValueError) as e:raise safe_error(e) from None

    @app.post(prefix+"/jobs/{job_id}/approve-copy")
    def approve_copy(job_id:str,body:CopyApproval,request:Request):
        actor=authorized(request,job_id)
        try:
            return visible(flow.state.approve_copy(
                actor,job_id,body.expected_generation,body.expected_review_sha,
                acknowledge_evidence=body.acknowledge_evidence))
        except (LiveGateError,ValueError) as e:raise safe_error(e) from None

    @app.post(prefix+"/jobs/{job_id}/reject-copy")
    def reject_copy(job_id:str,request:Request):
        actor=authorized(request,job_id)
        try:return visible(flow.state.reject_copy(actor,job_id))
        except LiveGateError as e:raise safe_error(e) from None

    @app.post(prefix+"/jobs/{job_id}/queue-prompt")
    def queue_prompt(job_id:str,request:Request):
        actor=authorized(request,job_id)
        if not (flow.live_enabled and flow.pm_authorized and
                actor in flow.approved_actors):
            raise HTTPException(status_code=423,detail="LIVE_PROVIDER_NOT_APPROVED")
        j=flow.state.get(actor,job_id)
        if j["state"]!="COPY_APPROVED" or not j["approval_sha"]:
            raise HTTPException(status_code=409,detail="COPY_NOT_APPROVED")
        task,new=queue.enqueue(actor=actor,job_id=job_id,stage="image_prompt",
                               context_sha=j["approval_sha"],mode="LIVE")
        return JSONResponse({"task_id":task["id"],"state":task["state"],"new":new},
                            status_code=202)

    @app.post(prefix+"/jobs/{job_id}/queue-image")
    def queue_image(job_id:str,request:Request):
        actor=authorized(request,job_id)
        if not (flow.live_enabled and flow.pm_authorized and
                actor in flow.approved_actors):
            raise HTTPException(status_code=423,detail="LIVE_PROVIDER_NOT_APPROVED")
        j=flow.state.get(actor,job_id)
        if j["state"]!="PROMPT_READY" or not j["prompt_json"]:
            raise HTTPException(status_code=409,detail="IMAGE_NOT_READY")
        task,new=queue.enqueue(actor=actor,job_id=job_id,stage="image",
                         context_sha=j["approval_sha"],mode="LIVE")
        return JSONResponse({"task_id":task["id"],"state":task["state"],"new":new},
                            status_code=202)

    @app.get(prefix+"/tasks/{task_id}")
    def task_status(task_id:str,request:Request):
        actor=authorized(request)
        task=queue.read(task_id)
        if not task or task["actor"]!=actor:
            raise HTTPException(status_code=404,detail="Task not found")
        return {"task_id":task_id,"job_id":task["job_id"],"stage":task["stage"],
                "state":task["state"],"mode":task["mode"],
                "error_code":task["error_code"]}

    @app.post(prefix+"/jobs/{job_id}/approve-image")
    def approve_image(job_id:str,body:ImageApproval,request:Request):
        actor=authorized(request,job_id)
        try:return visible(flow.state.approve_image(actor,job_id,body.image_sha))
        except LiveGateError as e:raise safe_error(e) from None

    @app.post(prefix+"/jobs/{job_id}/reject-image")
    def reject_image(job_id:str,body:ImageApproval,request:Request):
        actor=authorized(request,job_id)
        try:return visible(flow.state.reject_image(actor,job_id,body.image_sha))
        except LiveGateError as e:raise safe_error(e) from None

    @app.post(prefix+"/jobs/{job_id}/compose")
    def compose(job_id:str,body:ComposeRequest,request:Request):
        actor=authorized(request,job_id)
        if not flow.state.get(actor,job_id)["mode"]=="LIVE":
            raise HTTPException(status_code=423,detail="NOT_REAL_PROVIDER_OUTPUT")
        try:
            # Font path is server-configured only, never from untrusted input.
            font=Path(os.environ.get("IT_TEM_LIVE_KOREAN_FONT",
                     "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"))
            return visible(flow.compose(actor,job_id,layout=body.layout,font_path=font))
        except (LiveGateError,ValueError) as e:raise safe_error(e) from None
        except (OSError,sqlite3.Error):
            # A failed file/DB commit never signals COMPLETED; operator can
            # inspect the immutable compose identity and retry from IMAGE_APPROVED.
            raise HTTPException(503,detail="COMPOSITION_STORAGE_UNAVAILABLE") from None

    @app.get(prefix+"/jobs/{job_id}/performance")
    def live_performance(job_id:str,request:Request):
        actor=authorized(request,job_id)
        flow.state.get(actor,job_id)
        from datetime import datetime,timezone
        timings=[]
        with queue.db() as db:
            records=db.execute("""SELECT stage,state,created_at,started_at,ended_at
              FROM queued_ops WHERE job_id=? AND actor=? ORDER BY created_at""",
              (job_id,actor)).fetchall()
        for item in records:
            started=item["started_at"]
            ended=item["ended_at"]
            delta=None
            if started and ended:
                try:
                    a=datetime.fromisoformat(started).replace(tzinfo=timezone.utc)
                    b=datetime.fromisoformat(ended).replace(tzinfo=timezone.utc)
                    delta=max(0,(b-a).total_seconds())
                except ValueError:pass
            timings.append({"stage":item["stage"],"state":item["state"],
              "queued_at":item["created_at"],"started_at":started,
              "completed_at":ended,"server_elapsed_s":delta})
        attempts=[]
        with flow.cost.connect() as db:
            for r in db.execute("""SELECT stage,status,receipt,billing_unknown,created_at
                FROM attempts WHERE job_id=? AND actor=? ORDER BY created_at""",(job_id,actor)):
                x=json.loads(r["receipt"]) if r["receipt"] else {}
                attempts.append({"stage":r["stage"],"state":r["status"],
                    "model":x.get("model"),"usage":x.get("usage"),
                    "billing_unknown":bool(r["billing_unknown"]),
                    "started_at":r["created_at"],
                    "actual_cost_usd":None})
        return {"mode":"LIVE","job_id":job_id,"timings":timings,
          "provider_attempts":attempts,"project_spend_usd":None,
          "project_spend_status":"사용액 확인 필요",
          "application_cost_policy":"MONITOR_ONLY",
          "project_budget_warning_usd":25,"project_reference_budget_usd":30}

    @app.post(prefix+"/jobs/{job_id}/share")
    def share_for_evaluation(job_id:str,request:Request):
        actor=authorized(request,job_id)
        j=flow.state.get(actor,job_id)
        if j["state"]!="COMPLETED" or j["mode"]!="LIVE":
            raise HTTPException(409,"ONLY_COMPLETED_LIVE_CAN_BE_SHARED")
        import hashlib
        d=flow.root/"outputs"/job_id
        try:
            flow.validate_final_artifacts(actor,job_id)
            if (hashlib.sha256((d/"final.png").read_bytes()).hexdigest()!=j["final_sha"]
                or hashlib.sha256((d/"caption.txt").read_bytes()).hexdigest()!=j["caption_sha"]):
                raise ValueError
        except (OSError,ValueError,LiveGateError):
            raise HTTPException(503,"ARTIFACT_INTEGRITY_UNAVAILABLE") from None
        try:
            item=shares.publish(actor,job_id,j["final_sha"],j["caption_sha"])
        except LiveGateError as e:raise safe_error(e) from None
        return {"shared":True,"job_id":job_id,"final_sha":item["final_sha"],
                "mode":"LIVE","raw_product_images_shared":False}

    @app.get(prefix+"/shared")
    def shared_board(request:Request):
        authorized(request)
        results=[]
        for item in shares.all():
            # Explicit publication history is preserved. A damaged artifact
            # cannot silently become an eligible evaluation target.
            valid=False
            if ledger.owns(item["actor"],item["job_id"]):
                try:
                    job=flow.validate_final_artifacts(item["actor"],item["job_id"])
                    valid=(job["mode"]=="LIVE" and
                        job["final_sha"]==item["final_sha"] and
                        job["caption_sha"]==item["caption_sha"])
                except (LiveGateError,OSError,ValueError,KeyError):
                    valid=False
            results.append({"job_id":item["job_id"],"final_sha":item["final_sha"],
                "shared_at":item["shared_at"],
                "shared_at_utc":LiveShares.utc_iso8601(item["shared_at"]),
                "integrity_status":"VERIFIED" if valid else "UNAVAILABLE"})
        return {"mode":"LIVE","jobs":results}

    @app.get(prefix+"/shared/{job_id}/artifacts/{kind}")
    def shared_file(job_id:str,kind:str,request:Request):
        authorized(request)
        x=shares.item(job_id)
        if not x or kind not in ("final","caption"):
            raise HTTPException(404,"Shared result unavailable")
        if not ledger.owns(x["actor"],job_id):
            raise HTTPException(404,"Shared result unavailable")
        j=flow.state.get(x["actor"],job_id)
        if (j["state"]!="COMPLETED" or j["mode"]!="LIVE" or
            j["final_sha"]!=x["final_sha"] or j["caption_sha"]!=x["caption_sha"]):
            raise HTTPException(409,"Shared result no longer current")
        try:flow.validate_final_artifacts(x["actor"],job_id)
        except LiveGateError:
            raise HTTPException(503,"Shared result integrity error") from None
        target=flow.root/"outputs"/job_id/("final.png" if kind=="final" else "caption.txt")
        import hashlib
        expected=x["final_sha"] if kind=="final" else x["caption_sha"]
        if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest()!=expected:
            raise HTTPException(503,"Shared result integrity error")
        return FileResponse(target,media_type="image/png" if kind=="final" else
            "text/plain; charset=utf-8",headers={"Cache-Control":"private,no-store"})

    @app.post(prefix+"/shared/{job_id}/evaluations")
    def submit_shared_evaluation(job_id:str,data:ReviewBody,request:Request):
        actor=authorized(request)
        item=shares.item(job_id)
        if (not item or data.job_id!=job_id or
            data.category not in {"product_recognition","plan_copy_compliance",
                "image_fidelity","final_layout_korean","speed_reliability","ui_ux"}):
            raise HTTPException(404,"Shared evaluation unavailable")
        if not ledger.owns(item["actor"],job_id):
            raise HTTPException(404,"Shared evaluation unavailable")
        j=flow.state.get(item["actor"],job_id)
        if j["state"]!="COMPLETED" or j["mode"]!="LIVE" or j["final_sha"]!=item["final_sha"]:
            raise HTTPException(409,"Shared artifact changed")
        try:flow.validate_final_artifacts(item["actor"],job_id)
        except LiveGateError:
            raise HTTPException(503,"Shared result integrity error") from None
        previous=[x for x in ledger.reviews(actor,job_id)
                  if x["scenario_id"]==data.scenario_id and x["category"]==data.category]
        rev=ledger.review(actor,job_id,data,item["final_sha"],
                          "update" if previous else "submit")
        return {"saved":True,"mode":"LIVE","revision":rev,
                "artifact_sha256":item["final_sha"]}

    @app.get(prefix+"/shared/{job_id}/evaluations")
    def shared_evaluations(job_id:str,request:Request):
        actor=authorized(request)
        item=shares.item(job_id)
        if not item:raise HTTPException(404,"Shared evaluation unavailable")
        try:flow.validate_final_artifacts(item["actor"],job_id)
        except LiveGateError:
            raise HTTPException(503,"Shared result integrity error") from None
        return {"mode":"LIVE","job_id":job_id,
                "reviews":ledger.reviews(actor,job_id),
                "final_sha":item["final_sha"]}

    @app.get(prefix+"/jobs/{job_id}/artifacts/candidate")
    def candidate(job_id:str,request:Request):
        actor=authorized(request,job_id)
        j=flow.state.get(actor,job_id)
        if j["state"] not in ("IMAGE_REVIEW_REQUIRED","IMAGE_APPROVED") or j["mode"]!="LIVE":
            raise HTTPException(status_code=409,detail="IMAGE_NOT_READY")
        target=flow.image_path(job_id)
        import hashlib
        if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest()!=j["image_sha"]:
            raise HTTPException(status_code=503,detail="Image integrity unavailable")
        return FileResponse(target,media_type="image/png",
                            headers={"Cache-Control":"private,no-store"})

    @app.get(prefix+"/jobs/{job_id}/artifacts/{kind}")
    def download(job_id:str,kind:str,request:Request):
        actor=authorized(request,job_id)
        j=flow.state.get(actor,job_id)
        if j["state"]!="COMPLETED" or j["mode"]!="LIVE":
            raise HTTPException(status_code=409,detail="LIVE_OUTPUT_NOT_COMPLETED")
        if kind not in ("final","caption"):
            raise HTTPException(status_code=404,detail="Artifact not found")
        try:flow.validate_final_artifacts(actor,job_id)
        except LiveGateError:
            raise HTTPException(status_code=503,detail="Artifact integrity unavailable") from None
        target=flow.root/"outputs"/job_id/("final.png" if kind=="final" else "caption.txt")
        import hashlib
        if not target.is_file():
            raise HTTPException(status_code=503,detail="Artifact unavailable")
        if hashlib.sha256(target.read_bytes()).hexdigest()!=(
             j["final_sha"] if kind=="final" else j["caption_sha"]):
            raise HTTPException(status_code=503,detail="Artifact integrity error")
        return FileResponse(target,media_type="image/png" if kind=="final" else
                            "text/plain; charset=utf-8",filename=target.name,
                            headers={"Cache-Control":"private,no-store"})
