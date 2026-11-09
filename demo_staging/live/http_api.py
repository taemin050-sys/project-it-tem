"""Provisional isolated /demo/api/live prefix; never modifies official B0 11 operations.

All write/read endpoints require application login and ownership. No fixture or
fake provider mode is exposed by HTTP. Live dispatch is default-off by policy.
"""
from __future__ import annotations

import json
import os
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
    layout:dict
    font_variants:bool=False


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
        ident=ledger.identity(request.cookies.get(cookie_name))
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
        # Never return internal Provider errors, signed URLs, input file paths
        # or private reference image contents to the browser.
        out={"job_id":job["job_id"],"state":job["state"],"mode":job["mode"],
             "generation":job["generation"],"input_sha":job["input_sha"],
             "copy_sha":job["copy_sha"],"review_sha":job["review_sha"],
             "image_sha":job["image_sha"],"final_sha":job["final_sha"],"caption_sha":job["caption_sha"],
             "approval_current":bool(job["approval_sha"])}
        for stored,key in (("research_display_json","research_display"),
                           ("analysis_json","analysis"),
                           ("copy_json","copy"),
                           ("compliance_json","compliance"),
                           ("prompt_json","image_prompt")):
            if job[stored] is not None:
                out[key]=json.loads(job[stored])
        if job["state"]=="COMPLETED" and job["font_variants_json"]:
            artifacts=f'{prefix}/jobs/{job["job_id"]}/artifacts/'
            out["font_variants"]=[
                {"preset":preset,"sha256":sha,
                 "download_url":artifacts+("final" if preset=="gothic" else f"font-{preset}")}
                for preset,sha in json.loads(job["font_variants_json"]).items()
            ]
        return out

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
            return visible(flow.prepare(actor,job_id,body.model_dump(mode="json")))
        except (LiveGateError,ValueError) as e:
            raise safe_error(e) from None

    @app.get(prefix+"/jobs/{job_id}")
    def get_job(job_id:str,request:Request):
        actor=authorized(request,job_id)
        try:
            return visible(flow.state.get(actor,job_id))
        except LiveGateError as e:
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
            return visible(flow.compose(actor,job_id,layout=body.layout,font_path=font,
                                        font_variants=body.font_variants))
        except (LiveGateError,ValueError) as e:raise safe_error(e) from None

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
            if (hashlib.sha256((d/"final.png").read_bytes()).hexdigest()!=j["final_sha"]
                or hashlib.sha256((d/"caption.txt").read_bytes()).hexdigest()!=j["caption_sha"]):
                raise ValueError
        except (OSError,ValueError):
            raise HTTPException(503,"ARTIFACT_INTEGRITY_UNAVAILABLE") from None
        try:
            item=shares.publish(actor,job_id,j["final_sha"],j["caption_sha"])
        except LiveGateError as e:raise safe_error(e) from None
        return {"shared":True,"job_id":job_id,"final_sha":item["final_sha"],
                "mode":"LIVE","raw_product_images_shared":False}

    @app.get(prefix+"/shared")
    def shared_board(request:Request):
        authorized(request)
        return {"mode":"LIVE","jobs":[{"job_id":x["job_id"],
            "final_sha":x["final_sha"],"shared_at":x["shared_at"]}
            for x in shares.all()]}

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
        if kind in ("final","caption"):
            filename="final.png" if kind=="final" else "caption.txt"
            expected_sha=j["final_sha"] if kind=="final" else j["caption_sha"]
        elif kind in ("font-round","font-myeongjo"):
            expected_sha=json.loads(j["font_variants_json"] or "{}").get(kind.removeprefix("font-"))
            if expected_sha is None:
                raise HTTPException(status_code=404,detail="Artifact not found")
            filename=f"{kind}.png"
        else:
            raise HTTPException(status_code=404,detail="Artifact not found")
        target=flow.root/"outputs"/job_id/filename
        import hashlib
        if not target.is_file():
            raise HTTPException(status_code=503,detail="Artifact unavailable")
        if hashlib.sha256(target.read_bytes()).hexdigest()!=expected_sha:
            raise HTTPException(status_code=503,detail="Artifact integrity error")
        return FileResponse(target,media_type="text/plain; charset=utf-8" if kind=="caption" else
                            "image/png",filename=target.name,
                            headers={"Cache-Control":"private,no-store"})
