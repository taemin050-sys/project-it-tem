"""Provisional isolated /demo/api/live prefix; never modifies official B0 11 operations.

All write/read endpoints require application login and ownership. No fixture or
fake provider mode is exposed by HTTP. Live dispatch is default-off by policy.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import logging
import os
import sqlite3
import stat
from pathlib import Path
from typing import Literal

from fastapi import FastAPI,HTTPException,Request
from fastapi.responses import FileResponse,JSONResponse,Response
from pydantic import BaseModel,ConfigDict,Field

from .contracts import LiveGateError,digest
from .pipeline import LivePipeline
from .queue import LiveQueue
from .review_policy import llm_required
from .reviews import LiveShares
from demo_staging.app import ReviewBody
from demo_staging.live_safety import LiveNotAuthorized

B_RUNTIME_ROOT = Path("/home/macstudio/ittem-bp18-product-completion-20261111/runtime")
B_TAILNET_HOST = "macstudio-macstudio.tail17dfff.ts.net:10500"


class InputPayload(BaseModel):
    model_config=ConfigDict(extra="forbid",strict=True)
    product: dict
    image_size: str | None = None
    generation_mode: str | None = None
    customer_request_id: str


class CopyUpdate(BaseModel):
    model_config=ConfigDict(extra="forbid",strict=True)
    copy_output:dict


class CopyRevisionRequest(BaseModel):
    model_config=ConfigDict(extra="forbid",strict=True)
    instruction:str=Field(min_length=1,max_length=300)
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


class DualImageDecision(BaseModel):
    model_config=ConfigDict(extra="forbid",strict=True)
    image_sha:str=Field(pattern=r"^[0-9a-f]{64}$")
    approve:bool
    visual_checked:bool


class DualSelection(BaseModel):
    model_config=ConfigDict(extra="forbid",strict=True)
    mode:Literal["composed","freeform"]
    final_sha:str=Field(pattern=r"^[0-9a-f]{64}$")


class ImageRegenerateRequest(BaseModel):
    model_config=ConfigDict(extra="forbid",strict=True)
    expected_image_sha:str=Field(pattern=r"^[0-9a-f]{64}$")
    request_key:str=Field(pattern=r"^[0-9a-f]{32}$")


class ComposeRequest(BaseModel):
    model_config=ConfigDict(extra="forbid",strict=True)
    layout:dict|None=None


def web_queue_policy(*, signed_b: bool = False) -> dict:
    """Web may enqueue work only when the deployment's controls agree.

    Track B's deployed web process must use signed identity without a provider key.
    """
    required=("IT_TEM_LIVE_WEB_QUEUE_ENABLED","IT_TEM_LIVE_ENABLED",
              "IT_TEM_LIVE_EXECUTION_APPROVED","IT_TEM_PROVIDER_READINESS_CONFIRMED")
    if any(os.environ.get(k)!="YES" for k in required):
        return {"enabled":False,"actors":frozenset()}
    if signed_b and (
        os.environ.get("IT_TEM_TAILNET_AUTH_ENABLED") != "YES"
        or os.environ.get("IT_TEM_TAILNET_SSO_ONLY") != "YES"
        or os.environ.get("IT_TEM_TAILNET_EXPECTED_HOST") != B_TAILNET_HOST
        or os.environ.get("IT_TEM_DEMO_ENABLE_LIVE_CONFIG") == "YES"
        or os.environ.get("OPENAI_API_KEY")
    ):
        return {"enabled":False,"actors":frozenset()}
    actors=frozenset(x.strip() for x in
        os.environ.get("IT_TEM_LIVE_APPROVED_ACTORS","").split(",") if x.strip())
    if (os.environ.get("IT_TEM_LIVE_COST_POLICY")!="MONITOR_ONLY"
            or not actors or "*" in actors
            or any(not x.replace("_","").replace("-","").isalnum() for x in actors)):
        return {"enabled":False,"actors":frozenset()}
    return {"enabled":True,"actors":actors}


def _worker_holds_lock(runtime_root: Path) -> bool:
    """Read the worker's lifetime lock without creating or changing it."""
    try:
        fd = os.open(runtime_root / "live/worker.lock",
                     os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    except OSError:
        return False
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return False
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
    except BlockingIOError:
        return True
    except OSError:
        return False
    finally:
        os.close(fd)
    return False


def register_live_api(app:FastAPI, ledger, runtime_root:Path, cookie_name:str):
    runtime_root = Path(runtime_root)
    signed_b = runtime_root.resolve() == B_RUNTIME_ROOT
    policy=web_queue_policy(signed_b=signed_b)
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

    def queue_blocker(actor):
        if not (flow.live_enabled and flow.pm_authorized and actor in flow.approved_actors):
            return "LIVE_PROVIDER_NOT_APPROVED"
        if signed_b and not _worker_holds_lock(runtime_root):
            return "LIVE_WORKER_UNAVAILABLE"
        return None

    def require_queue(actor):
        blocker = queue_blocker(actor)
        if blocker:
            raise HTTPException(status_code=503 if blocker == "LIVE_WORKER_UNAVAILABLE" else 423,
                                detail=blocker)

    def safe_error(error):
        if isinstance(error,LiveNotAuthorized):
            return HTTPException(status_code=423,detail="LIVE_PROVIDER_NOT_APPROVED")
        if isinstance(error,LiveGateError):
            code=error.code
            return HTTPException(status_code=409 if ("STATE" in code or "STALE" in code or
                             "APPROVAL" in code or "CONFLICT" in code or
                             code in ("REAL_COMPLIANCE_BLOCKED","REVISION_IN_PROGRESS",
                                      "LLM_REVIEW_REQUIRED",
                                      "REVIEW_POLICY_REVALIDATION_REQUIRED",
                                      "REVIEW_POLICY_BINDING_TAMPERED",
                                      "REVIEW_POLICY_RUNTIME_SOURCE_CHANGED",
                                      "REVIEW_POLICY_RUNTIME_VERSION_CHANGED",
                                      "REVIEW_POLICY_ACTIVATION_REQUIRED",
                                      "REVIEW_POLICY_ALREADY_CURRENT",
                                      "IMAGE_RETRY_OUTSTANDING_OR_UNKNOWN",
                                      "IMAGE_RETRY_STALE_REJECTION",
                                      "IMAGE_RETRY_LEDGER_MISMATCH"))
                             else 422,
                                detail={"code":code})
        return HTTPException(status_code=503,detail="LIVE_GATE_UNAVAILABLE")

    def visible(job):
        profile=flow.state.template(job["actor"],job["job_id"])
        attempt=flow.state.current_image_attempt(job["actor"],job["job_id"])
        # Never return internal Provider errors, signed URLs, input file paths
        # or private reference image contents to the browser.
        review_policy=flow.state.policy_status(job["actor"],job["job_id"])
        out={"job_id":job["job_id"],"state":job["state"],"mode":job["mode"],
             "generation":job["generation"],"input_sha":job["input_sha"],
             "copy_sha":job["copy_sha"],"review_sha":job["review_sha"],
             "image_sha":job["image_sha"],"final_sha":job["final_sha"],"caption_sha":job["caption_sha"],
             "approval_current":bool(job["approval_sha"]) and
                 review_policy["status"] in ("CURRENT","LEGACY_POLICY_MODE"),
             "review_policy":review_policy,
             "previous_copy_available":flow.state.previous_copy_available(job["actor"],job["job_id"]),
             "revision_feedback":flow.state.revision_feedback(job["actor"],job["job_id"]),
             "image_attempt_version":attempt["attempt_version"] if attempt else 1,
             "template_profile":profile["profile_id"] if profile else "PRE_POLICY_LEGACY",
             "image_size":json.loads(job["input_json"]).get("image_size","4:5"),
             "generation_mode":json.loads(job["input_json"]).get("generation_mode","composed"),
             "dual_requested":flow.state.dual_membership(job["actor"],job["job_id"]) is not None,
             "output_size":({"width":profile["safe_zone"]["final_size"][0],
                             "height":profile["safe_zone"]["final_size"][1]}
                     if profile and profile["profile_id"].startswith("OWNER_IMAGE_SIZE_")
                     else {"width":1080,"height":1350}),
             "functional_types":json.loads(job["input_json"])["product"].get("functional_types",[]),
             "functional_types_status":"OWNER_TEXT_V010_APPLIED"
                if json.loads(job["input_json"])["product"].get("functional_types") else "NO_SELECTION",
             "emoji_level":json.loads(job["input_json"])["product"].get("emoji_level","없음"),
             "product_protection_status":"MANUAL_REVIEW_REQUIRED"
                if job["state"]=="COMPLETED" else "NOT_REVIEWED"}
        for stored,key in (("research_display_json","research_display"),
                           ("analysis_json","analysis"),
                           ("copy_json","copy"),
                           ("compliance_json","compliance"),
                           ("prompt_json","image_prompt")):
            if job[stored] is not None:
                out[key]=json.loads(job[stored])
        required = llm_required(job["mode"])
        pending = bool(required and job["copy_sha"] and not out.get("compliance", {}).get("llm_review"))
        out["llm_review_required"] = required
        out["llm_review_pending"] = pending
        if pending:
            out["approval_current"] = False
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
    dual_qa_enabled=qa_enabled and os.environ.get("IT_TEM_BP18_DUAL_QA_ENABLED")=="YES"

    def qa_client(request):
        return request.client and request.client.host in ("127.0.0.1","::1")

    def qa_access(request,job_id):
        if not qa_enabled or not qa_actors:
            raise HTTPException(404,"QA fixture endpoint disabled")
        if not qa_client(request):
            raise HTTPException(404,"QA fixture endpoint unavailable")
        actor=authorized(request,job_id)
        if actor not in qa_actors:
            raise HTTPException(404,"QA fixture actor unavailable")
        return actor

    def single_image_job(actor,job_id):
        if flow.state.dual_membership(actor,job_id) is not None:
            raise HTTPException(409,"DUAL_REQUIRES_GROUP_ROUTE")

    def korean_font():
        return Path(os.environ.get("IT_TEM_LIVE_KOREAN_FONT",
            "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"))

    def fixture_image(actor,job_id,*,dual=False):
        from tests.demo_live.test_pipeline import FakeOwner,png
        from src.image_generation.backend_adapter import BackendGeneratedImage
        from src.image_generation.size_selection import resolve_size_choice

        job=flow.state.get(actor,job_id)
        if job["mode"]!="OFFLINE_FIXTURE":
            raise LiveGateError("QA_REQUIRES_OFFLINE_FIXTURE")
        if job["state"]=="COPY_APPROVED":
            flow.prompt(actor,job_id,FakeOwner(),offline=True)
        owner_request=flow.image_input(actor,job_id)
        if owner_request.safe_zone is None and owner_request.layout_selection is None:
            raise LiveGateError("QA_OWNER_IMAGE_LAYOUT_REQUIRED")
        native=(resolve_size_choice(owner_request.layout_selection.aspect_ratio)[1].native
            if owner_request.layout_selection is not None else (1152,1440))
        attempt=flow.state.current_image_attempt(actor,job_id)
        version=attempt["attempt_version"] if attempt else 1
        freeform=owner_request.generation_mode=="freeform"
        if dual:
            from .dual_fixture import render_composed_fixture,render_freeform_fixture
            if freeform:
                img=render_freeform_fixture(native,owner_request.ad_copy.model_dump(),korean_font())
            else:
                profile=flow.state.template(actor,job_id)
                img=render_composed_fixture(native,profile["layout"]["protected_regions"][0])
        else:
            img=png((215+version%8,225+version%10,235-version%10),size=native)
        receipt={"mode":"OFFLINE_FIXTURE","provider_calls":0}
        if freeform:
            receipt.update({"generation_mode":"freeform","state":"succeeded",
                            "rendering":("QA_SYNTHETIC_KOREAN_FIXTURE" if dual else
                                         "QA_FIXTURE_NO_ACTUAL_MODEL_TEXT")})
        candidate=BackendGeneratedImage(
            image_bytes=img,mime_type="image/png",width=native[0],height=native[1],
            sha256=hashlib.sha256(img).hexdigest(),job_id=job_id,
            copy_revision=owner_request.copy_revision,
            copy_hash=owner_request.copy_hash,mock=True,receipt=receipt)
        return flow.accept_image_result(actor,job_id,candidate,offline=True)

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
        single_image_job(actor,job_id)
        try:
            return visible(fixture_image(actor,job_id))
        except (LiveGateError,ValueError) as e:raise safe_error(e) from None

    @app.post("/demo/api/qa/jobs/{job_id}/regenerate-image")
    def qa_regenerate_image(job_id:str,body:ImageRegenerateRequest,request:Request):
        actor=qa_access(request,job_id)
        single_image_job(actor,job_id)
        try:
            queue.assert_image_retry_safe(actor,job_id)
            flow.begin_image_retry(actor,job_id,body.expected_image_sha,body.request_key)
            # This is a deterministic offline candidate, never a new paid request.
            return qa_prompt_image(job_id,request)
        except (LiveGateError,ValueError) as e:raise safe_error(e) from None

    @app.post("/demo/api/qa/jobs/{job_id}/compose")
    def qa_compose(job_id:str,body:ComposeRequest,request:Request):
        actor=qa_access(request,job_id)
        single_image_job(actor,job_id)
        j=flow.state.get(actor,job_id)
        if j["mode"]!="OFFLINE_FIXTURE":
            raise HTTPException(409,"QA_REQUIRES_OFFLINE_FIXTURE")
        try:
            return visible(flow.compose(actor,job_id,layout=body.layout,font_path=korean_font()))
        except (LiveGateError,ValueError) as e:raise safe_error(e) from None
        except (OSError,sqlite3.Error):
            raise HTTPException(503,"QA_COMPOSITION_STORAGE_UNAVAILABLE") from None

    @app.get("/demo/api/qa/jobs/{job_id}/artifacts/{kind}")
    def qa_artifact(job_id:str,kind:str,request:Request):
        actor=qa_access(request,job_id)
        single_image_job(actor,job_id)
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

    dual_prefix="/demo/api/qa/jobs/{job_id}/dual"

    def dual_access(request,job_id):
        if not dual_qa_enabled:
            raise HTTPException(404,"Dual QA fixture endpoint disabled")
        return qa_access(request,job_id)

    def dual_group(actor,job_id):
        try:
            group=flow.state.dual_group(actor,job_id)
        except LiveGateError as error:
            if error.code!="LIVE_JOB_NOT_FOUND":
                raise safe_error(error) from None
            group=None
        if group is None:
            raise HTTPException(404,"Dual job not found")
        return group

    def variant_job(group,mode):
        return group["parent_job_id"] if mode=="composed" else group["child_job_id"]

    def variant_snapshot(request,actor,group,mode):
        job_id=variant_job(group,mode)
        if job_id is None:
            return None
        job=flow.state.get(actor,job_id)
        dispatch=group["dispatch"].get(job_id,{})
        state=job["state"]
        receipt_sha=None
        image_review_sha=dispatch.get("visual_review_sha")
        error_code=dispatch.get("error_code")
        verification="NOT_REVIEWED"
        hashes={}
        if state=="COMPLETED":
            try:
                flow.validate_final_artifacts(actor,job_id)
                if not image_review_sha:
                    raise LiveGateError("DUAL_VISUAL_REVIEW_UNAVAILABLE")
                receipt_sha=flow.state.read_manifest(actor,job_id)["receipt_sha"]
            except (LiveGateError,OSError,sqlite3.Error):
                state,error_code="FAILED","DUAL_ARTIFACT_INTEGRITY_UNAVAILABLE"
                image_review_sha=None
            else:
                hashes={"final":job["final_sha"],"caption":job["caption_sha"],"receipt":receipt_sha}
                verification="FIXTURE_REVIEWED"
        elif state in ("IMAGE_REVIEW_REQUIRED","IMAGE_APPROVED"):
            hashes={"candidate":job["image_sha"]}
            verification="FIXTURE_REVIEWED" if state=="IMAGE_APPROVED" else "FIXTURE_REVIEW_REQUIRED"
        elif state=="IMAGE_REJECTED":
            verification="FIXTURE_REJECTED"
        elif dispatch.get("state")=="FAILED":
            state="FAILED"
        artifact_urls={}
        for kind,sha in hashes.items():
            url=request.app.url_path_for("dual_artifact",job_id=group["parent_job_id"],
                                         mode=mode,kind=kind)
            artifact_urls[kind]=f"{url}?sha256={sha}"
        profile=flow.state.template(actor,job_id)
        width,height=profile["safe_zone"]["final_size"] if profile else (1080,1350)
        return {"mode":mode,"state":state,"verification_state":verification,
                "variant_job_id":job_id,"approval_sha":job["approval_sha"],"review_sha":job["review_sha"],
                "dispatch_state":dispatch.get("state"),"image_review_sha":image_review_sha,
                "candidate_sha":job["image_sha"],"final_sha":hashes.get("final"),
                "caption_sha":hashes.get("caption"),"receipt_sha":receipt_sha,
                "error_code":error_code,"output_size":{"width":width,"height":height},
                "artifacts":artifact_urls,"cost":{"provider_attempt_count":0,"actual_usd":None}}

    def dual_snapshot(request,actor,group):
        variants={mode:variant_snapshot(request,actor,group,mode) for mode in ("composed","freeform")}
        if group["child_job_id"] is None:
            state="READY"
        else:
            states=[variant["state"] for variant in variants.values()]
            failed=sum(state in ("FAILED","IMAGE_REJECTED") for state in states)
            complete=states.count("COMPLETED")
            review=any(state in ("IMAGE_REVIEW_REQUIRED","IMAGE_APPROVED") for state in states)
            if complete==2:
                state="COMPLETED"
            elif failed==2:
                state="FAILED"
            elif complete or (failed and review):
                state="PARTIAL"
            elif review:
                state="REVIEW_REQUIRED"
            else:
                state="GENERATING"
        parent=flow.state.get(actor,group["parent_job_id"])
        preferred=group["preferred_mode"]
        selected=variants.get(preferred)
        if (not selected or selected["state"]!="COMPLETED" or
                selected["final_sha"]!=group.get("preferred_final_sha")):
            preferred=None
        return {"job_id":group["parent_job_id"],"state":state,"provenance":"OFFLINE_FIXTURE",
                "image_size":json.loads(parent["input_json"]).get("image_size","4:5"),
                "copy_sha":parent["copy_sha"],"copy_approval_sha":group["approval_sha"],
                "preferred_variant":preferred,
                "variants":variants}

    @app.post(dual_prefix+"/input")
    def dual_input(job_id:str,body:InputPayload,request:Request):
        actor=dual_access(request,job_id)
        if body.generation_mode not in (None,"composed") or body.image_size not in ("3:4","4:5","9:16"):
            raise HTTPException(422,"DUAL_INPUT_MODE_OR_RATIO_INVALID")
        payload=body.model_dump(mode="json")
        payload["generation_mode"]="composed"
        try:
            return visible(flow.prepare(actor,job_id,payload,template_profile="A",dual=True))
        except (LiveGateError,ValueError) as error:
            raise safe_error(error) from None

    @app.get(dual_prefix)
    def dual_status(job_id:str,request:Request):
        actor=dual_access(request,job_id)
        return dual_snapshot(request,actor,dual_group(actor,job_id))

    @app.post(dual_prefix+"/start")
    def dual_start(job_id:str,body:CopyApproval,request:Request):
        actor=dual_access(request,job_id)
        dual_group(actor,job_id)
        try:
            group=flow.state.start_dual(actor,job_id,expected_generation=body.expected_generation,
                expected_review_sha=body.expected_review_sha,acknowledge_evidence=body.acknowledge_evidence)
            for mode in ("composed","freeform"):
                variant_id=variant_job(group,mode)
                with flow.state.dual_dispatch_lock(actor,job_id,variant_id) as acquired:
                    if not acquired:
                        continue
                    error_code=None
                    try:
                        fixture_image(actor,variant_id,dual=True)
                    except LiveGateError as error:
                        error_code=error.code
                    except Exception as error:
                        logging.getLogger(__name__).warning("Dual fixture render failed (%s)",type(error).__name__)
                        error_code="DUAL_FIXTURE_RENDER_FAILED"
                    flow.state.finish_dual_dispatch(actor,job_id,variant_id,error_code=error_code)
            return dual_snapshot(request,actor,dual_group(actor,job_id))
        except (LiveGateError,ValueError) as error:
            raise safe_error(error) from None
        except (OSError,sqlite3.Error):
            raise HTTPException(503,"DUAL_FIXTURE_STORAGE_UNAVAILABLE") from None

    @app.post(dual_prefix+"/{mode}/decision")
    def dual_decision(job_id:str,mode:Literal["composed","freeform"],body:DualImageDecision,request:Request):
        actor=dual_access(request,job_id)
        group=dual_group(actor,job_id)
        variant_id=variant_job(group,mode)
        if variant_id is None:
            raise HTTPException(409,"DUAL_VARIANT_NOT_STARTED")
        if body.approve and not body.visual_checked:
            raise HTTPException(409,"DUAL_VISUAL_REVIEW_REQUIRED")
        try:
            current=flow.state.get(actor,variant_id)
            if current["image_sha"]!=body.image_sha:
                raise LiveGateError("IMAGE_APPROVAL_STALE")
            if body.approve:
                if current["state"]=="IMAGE_REVIEW_REQUIRED":
                    visual_review={"product_matches":True}
                    if mode=="freeform":
                        visual_review.update(copy_matches=True,no_duplicate_text=True)
                    current=flow.state.approve_image(actor,variant_id,body.image_sha,visual_review=visual_review)
                if current["state"]=="IMAGE_APPROVED":
                    flow.compose(actor,variant_id,font_path=korean_font())
                elif current["state"]!="COMPLETED":
                    raise LiveGateError("IMAGE_APPROVAL_STATE_CONFLICT")
            elif current["state"]!="IMAGE_REJECTED":
                flow.state.reject_image(actor,variant_id,body.image_sha)
            return dual_snapshot(request,actor,dual_group(actor,job_id))
        except (LiveGateError,ValueError) as error:
            if isinstance(error,LiveGateError) and error.code in (
                "IMAGE_APPROVAL_MISMATCH","FINAL_REQUIRES_IMAGE_APPROVAL",
                "COMPOSITION_ALREADY_FINALIZED","IMAGE_REJECTION_STATE_CONFLICT"):
                latest=flow.state.get(actor,variant_id)
                expected_state="COMPLETED" if body.approve else "IMAGE_REJECTED"
                if latest["state"]==expected_state and latest["image_sha"]==body.image_sha:
                    return dual_snapshot(request,actor,dual_group(actor,job_id))
            raise safe_error(error) from None
        except (OSError,sqlite3.Error):
            raise HTTPException(503,"DUAL_COMPOSITION_STORAGE_UNAVAILABLE") from None

    @app.post(dual_prefix+"/selection")
    def dual_selection(job_id:str,body:DualSelection,request:Request):
        actor=dual_access(request,job_id)
        variant_id=variant_job(dual_group(actor,job_id),body.mode)
        if variant_id is None:
            raise HTTPException(409,"DUAL_VARIANT_NOT_STARTED")
        try:
            flow.validate_final_artifacts(actor,variant_id)
            group=flow.state.select_dual_variant(actor,job_id,body.mode,body.final_sha)
            return dual_snapshot(request,actor,group)
        except (LiveGateError,ValueError) as error:
            raise safe_error(error) from None

    @app.get(dual_prefix+"/{mode}/artifacts/{kind}")
    def dual_artifact(job_id:str,mode:Literal["composed","freeform"],
                      kind:Literal["candidate","final","caption","receipt"],sha256:str,request:Request):
        actor=dual_access(request,job_id)
        group=dual_group(actor,job_id)
        variant=variant_snapshot(request,actor,group,mode)
        if variant is None or kind not in variant["artifacts"]:
            raise HTTPException(409,"DUAL_ARTIFACT_NOT_AVAILABLE")
        expected=variant[f"{kind}_sha"]
        if sha256!=expected:
            raise HTTPException(409,"DUAL_ARTIFACT_CHANGED")
        variant_id=variant_job(group,mode)
        filenames={"final":("final.png","image/png"),"caption":("caption.txt","text/plain; charset=utf-8"),
                   "receipt":("receipt.json","application/json"),"candidate":("candidate.png","image/png")}
        filename,media_type=filenames[kind]
        path=(flow.image_path(variant_id) if kind=="candidate" else flow.root/"outputs"/variant_id/filename)
        try:
            payload=path.read_bytes()
            if hashlib.sha256(payload).hexdigest()!=expected:
                raise ValueError
        except (OSError,ValueError):
            raise HTTPException(503,"DUAL_ARTIFACT_INTEGRITY_UNAVAILABLE") from None
        headers={"Cache-Control":"private,no-store","X-IT-TEM-Provenance":"OFFLINE_FIXTURE"}
        if kind!="candidate":
            headers["Content-Disposition"]=f'attachment; filename="{mode}-{filename}"'
        return Response(payload,media_type=media_type,headers=headers)

    @app.get(prefix+"/text-cost-estimate")
    def text_cost_estimate(request:Request,photo_count:int=5,revision_target:str|None=None):
        """Authenticated, deterministic Text Owner estimate. No model/client/secret."""
        authorized(request)
        from src.text_generation.cost import (
            estimate_generation_cost,estimate_revision_cost,format_usd)
        from fastapi import HTTPException
        model=os.environ.get("IT_TEM_TEXT_MODEL","gpt-6-luna")
        vision_model=os.environ.get("IT_TEM_VISION_MODEL","gpt-6-luna")
        try:
            if revision_target is None:
                estimated=estimate_generation_cost(
                    photo_count=photo_count,model=model,vision_model=vision_model)
            elif revision_target in ("copy","image_prompt"):
                estimated=estimate_revision_cost(revision_target,model=model)
            else:
                raise ValueError("Revision target unsupported")
        except ValueError:
            # Do not invent prices when configuration/model changes.
            raise HTTPException(status_code=422,detail="TEXT_ESTIMATE_UNAVAILABLE") from None
        return {
            "mode":"NON_BILLABLE_ESTIMATE",
            "scope":"TEXT_ONLY",
            "model":estimated.model,
            "steps":estimated.steps,
            "total_usd":estimated.total_usd,
            "display":format_usd(estimated.total_usd),
            "includes_image_generation":False,
            "actual_charges_known":False,
        }

    @app.get(prefix+"/total-cost-estimate")
    def total_cost_estimate(request:Request,photo_count:int=5,
                            image_size:str="4:5",generation_mode:str="composed"):
        """No-provider authenticated estimate: text+one image, no billable IO."""
        authorized(request)
        from src.text_generation.cost import estimate_generation_cost,format_usd
        from .image_cost_estimate import estimate_image_once
        text_model=os.environ.get("IT_TEM_TEXT_MODEL","gpt-6-luna")
        vision_model=os.environ.get("IT_TEM_VISION_MODEL","gpt-6-luna")
        from .image_runtime_profile import effective_image_profile
        try:
            execution=effective_image_profile()
            txt=estimate_generation_cost(photo_count=photo_count,
                 model=text_model,vision_model=vision_model)
            image=estimate_image_once(ratio=image_size,generation_mode=generation_mode,
                 model=execution["model"],quality=execution["quality"],
                 complexity=execution["complexity"])
        except (ValueError,LiveGateError):
            raise HTTPException(status_code=422,detail="TOTAL_ESTIMATE_UNAVAILABLE") from None
        median=image["reference_median_usd"]
        return {"mode":"NON_BILLABLE_ESTIMATE","scope":"TEXT_PLUS_ONE_IMAGE",
            "text":{"model":txt.model,"steps":txt.steps,
                    "estimate_usd":txt.total_usd,"display":format_usd(txt.total_usd)},
            "image":image,
            "total_reference_usd":round(txt.total_usd+median,6) if median is not None else None,
            "total_display":format_usd(txt.total_usd+median) if median is not None else None,
            "actual_charges_known":False,"billing_cap":False,
            "cost_policy":"MONITOR_ONLY"}

    @app.get(prefix+"/capabilities")
    def capabilities(request:Request):
        actor=authorized(request)
        blocker = queue_blocker(actor)
        return {"live_enabled":blocker is None,
                "mode":"LIVE_QUEUE_READY" if blocker is None else "LIVE_BLOCKED",
                "source_sha":app.state.demo_code_sha,
                "reason":"COST_AND_CONTRACT_PM_GATE" if not signed_b and
                         blocker == "LIVE_PROVIDER_NOT_APPROVED" else blocker,
                "dual_qa_enabled":bool(dual_qa_enabled and qa_client(request) and actor in qa_actors),
                "provisional_wire":True,"mock_fallback":False}

    @app.post(prefix+"/jobs/{job_id}/input")
    def create_input(job_id:str,body:InputPayload,request:Request):
        actor=authorized(request,job_id)
        single_image_job(actor,job_id)
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
            if job["state"]=="COMPLETED" and flow.state.dual_membership(actor,job_id) is None:
                # Avoid advertising a corrupted finished Job as downloadable.
                flow.validate_final_artifacts(actor,job_id)
            return visible(job)
        except LiveGateError as e:
            if e.code=="LIVE_JOB_NOT_FOUND":
                raise HTTPException(404,"Job not found") from None
            if e.code.startswith(("COMPOSITION_MANIFEST_",
                                  "COMPOSITION_RECEIPT_",
                                  "FINAL_ARTIFACT_",
                                  "TEMPLATE_POLICY_")):
                raise HTTPException(503,detail="Artifact integrity unavailable") from None
            raise safe_error(e) from None

    @app.post(prefix+"/jobs/{job_id}/queue-text")
    def queue_text(job_id:str,request:Request):
        actor=authorized(request,job_id)
        single_image_job(actor,job_id)
        require_queue(actor)
        j=flow.state.get(actor,job_id)
        if j["state"]!="INPUT_STORED" or j["mode"]!="INPUT_ONLY":
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
    def queue_owner_text_revision(job_id:str,body:CopyRevisionRequest,request:Request):
        actor=authorized(request,job_id)
        require_queue(actor)
        try:
            job=flow.state.get(actor,job_id)
            if job["mode"]!="LIVE":
                raise LiveGateError("REVISION_REQUIRES_REAL_MODEL")
            instruction=body.instruction.strip()
            text_model=os.environ.get("IT_TEM_TEXT_MODEL","gpt-6-luna")
            context=flow.revision_context(
                actor,job_id,instruction,body.expected_generation,
                body.expected_review_sha,text_model=text_model)
            from .contracts import digest
            task,new=queue.enqueue(
                actor=actor,job_id=job_id,stage="copy_revision",
                context_sha=digest(context),mode="LIVE",
                revision_payload={
                    "instruction":instruction,
                    "expected_generation":body.expected_generation,
                    "expected_review_sha":body.expected_review_sha})
            return JSONResponse({"task_id":task["id"],"state":task["state"],
                                  "new":new},status_code=202)
        except (LiveGateError,ValueError) as e:
            raise safe_error(e) from None

    @app.post(prefix+"/jobs/{job_id}/restore-copy")
    def live_restore_copy(job_id:str,body:CopyRestoreRequest,request:Request):
        actor=authorized(request,job_id)
        try:
            return visible(flow.state.restore_previous_copy(
                actor,job_id,body.expected_generation,body.expected_review_sha))
        except (LiveGateError,ValueError) as e:raise safe_error(e) from None

    @app.post(prefix+"/jobs/{job_id}/review-copy")
    def queue_copy_review(job_id:str,body:CopyRestoreRequest,request:Request):
        actor=authorized(request,job_id)
        require_queue(actor)
        try:
            context=flow.copy_review_context(
                actor,job_id,body.expected_generation,body.expected_review_sha,
                text_model=os.environ.get("IT_TEM_TEXT_MODEL","gpt-6-luna"))
            task,new=queue.enqueue(
                actor=actor,job_id=job_id,stage="copy_review",context_sha=digest(context),mode="LIVE",
                review_payload={"expected_generation":body.expected_generation,
                                "expected_review_sha":body.expected_review_sha})
            return JSONResponse({"task_id":task["id"],"state":task["state"],"new":new},
                                status_code=202)
        except (LiveGateError,ValueError) as error:
            raise safe_error(error) from None

    @app.post(prefix+"/jobs/{job_id}/revalidate-policy")
    def revalidate_review_policy(job_id:str,body:CopyRestoreRequest,request:Request):
        actor=authorized(request,job_id)
        try:
            return visible(flow.state.revalidate_review_policy(
                actor,job_id,body.expected_generation,body.expected_review_sha))
        except (LiveGateError,ValueError) as error:
            raise safe_error(error) from None

    @app.post(prefix+"/jobs/{job_id}/approve-copy")
    def approve_copy(job_id:str,body:CopyApproval,request:Request):
        actor=authorized(request,job_id)
        single_image_job(actor,job_id)
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
        single_image_job(actor,job_id)
        require_queue(actor)
        j=flow.state.get(actor,job_id)
        if j["state"]!="COPY_APPROVED" or j["mode"]!="LIVE" or not j["approval_sha"]:
            raise HTTPException(status_code=409,detail="COPY_NOT_APPROVED")
        task,new=queue.enqueue(actor=actor,job_id=job_id,stage="image_prompt",
                               context_sha=j["approval_sha"],mode="LIVE")
        return JSONResponse({"task_id":task["id"],"state":task["state"],"new":new},
                            status_code=202)

    @app.post(prefix+"/jobs/{job_id}/queue-image")
    def queue_image(job_id:str,request:Request):
        actor=authorized(request,job_id)
        single_image_job(actor,job_id)
        require_queue(actor)
        j=flow.state.get(actor,job_id)
        if j["state"]!="PROMPT_READY" or j["mode"]!="LIVE" or not j["prompt_json"]:
            raise HTTPException(status_code=409,detail="IMAGE_NOT_READY")
        attempt=flow.state.current_image_attempt(actor,job_id)
        ctx=(digest({"approval_sha":j["approval_sha"],"attempt_id":attempt["attempt_id"]})
             if attempt and attempt["attempt_version"]>1 else j["approval_sha"])
        task,new=queue.enqueue(actor=actor,job_id=job_id,stage="image",
                         context_sha=ctx,mode="LIVE")
        return JSONResponse({"task_id":task["id"],"state":task["state"],"new":new},
                            status_code=202)

    @app.post(prefix+"/jobs/{job_id}/regenerate-image")
    def regenerate_image(job_id:str,body:ImageRegenerateRequest,request:Request):
        actor=authorized(request,job_id)
        single_image_job(actor,job_id)
        require_queue(actor)
        try:
            if flow.state.get(actor,job_id)["mode"] != "LIVE":
                raise LiveGateError("IMAGE_RETRY_STATE_CONFLICT")
            queue.assert_image_retry_safe(actor,job_id)
            attempt=flow.begin_image_retry(actor,job_id,body.expected_image_sha,
                                           body.request_key)
            current=flow.state.get(actor,job_id)
            ctx=digest({"approval_sha":current["approval_sha"],
                        "attempt_id":attempt["attempt_id"]})
            task,new=queue.enqueue(actor=actor,job_id=job_id,stage="image",
                                   context_sha=ctx,mode="LIVE")
            return JSONResponse({"task_id":task["id"],"state":task["state"],
                                 "new":new,"attempt_version":attempt["attempt_version"]},
                                status_code=202)
        except LiveGateError as e:raise safe_error(e) from None

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
        single_image_job(actor,job_id)
        try:return visible(flow.state.approve_image(actor,job_id,body.image_sha))
        except LiveGateError as e:raise safe_error(e) from None

    @app.post(prefix+"/jobs/{job_id}/reject-image")
    def reject_image(job_id:str,body:ImageApproval,request:Request):
        actor=authorized(request,job_id)
        single_image_job(actor,job_id)
        try:return visible(flow.state.reject_image(actor,job_id,body.image_sha))
        except LiveGateError as e:raise safe_error(e) from None

    @app.post(prefix+"/jobs/{job_id}/compose")
    def compose(job_id:str,body:ComposeRequest,request:Request):
        actor=authorized(request,job_id)
        single_image_job(actor,job_id)
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
            actual_size=None
            actual_ratio=None
            if ledger.owns(item["actor"],item["job_id"]):
                try:
                    job=flow.validate_final_artifacts(item["actor"],item["job_id"])
                    valid=(job["mode"]=="LIVE" and
                        job["final_sha"]==item["final_sha"] and
                        job["caption_sha"]==item["caption_sha"])
                    if valid:
                        # The displayed ratio comes from the exact final PNG
                        # bytes after SHA verification, never an initial
                        # selected ratio, CSS default or a screenshot label.
                        from io import BytesIO
                        from PIL import Image
                        import hashlib
                        file=flow.root/"outputs"/item["job_id"]/"final.png"
                        payload=file.read_bytes()
                        if hashlib.sha256(payload).hexdigest()!=item["final_sha"]:
                            raise ValueError("PUBLISHED_FINAL_CHANGED")
                        with Image.open(BytesIO(payload)) as image:
                            if (image.format!="PNG" or image.width<=0 or
                                image.height<=0 or image.width*image.height>12_000_000):
                                raise ValueError("PUBLISHED_FINAL_DIMENSIONS_UNSAFE")
                            actual_size={"width":image.width,"height":image.height}
                        actual_ratio={(1080,1440):"3:4",
                                      (1080,1350):"4:5",
                                      (1080,1920):"9:16"}.get(
                            (actual_size["width"],actual_size["height"]))
                except (LiveGateError,OSError,ValueError,KeyError):
                    valid=False
                    actual_size=None
                    actual_ratio=None
            results.append({"job_id":item["job_id"],"final_sha":item["final_sha"],
                "shared_at":item["shared_at"],
                "shared_at_utc":LiveShares.utc_iso8601(item["shared_at"]),
                "integrity_status":"VERIFIED" if valid else "UNAVAILABLE",
                "image_size":actual_ratio if valid else None,
                "output_size":actual_size if valid else None,
                "dimensions_source":"VERIFIED_FINAL_PNG" if valid else "UNAVAILABLE"})
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
    def candidate(job_id:str,request:Request,sha256:str|None=None):
        actor=authorized(request,job_id)
        single_image_job(actor,job_id)
        j=flow.state.get(actor,job_id)
        if j["state"] not in ("IMAGE_REVIEW_REQUIRED","IMAGE_APPROVED") or j["mode"]!="LIVE":
            raise HTTPException(status_code=409,detail="IMAGE_NOT_READY")
        expected=j["image_sha"]
        if sha256 is not None and sha256!=expected:
            raise HTTPException(status_code=409,detail="IMAGE_CANDIDATE_CHANGED")
        import hashlib
        from fastapi.responses import Response
        try:
            payload=flow.image_path(job_id).read_bytes()
        except OSError:
            raise HTTPException(status_code=503,detail="Image integrity unavailable") from None
        if hashlib.sha256(payload).hexdigest()!=expected:
            raise HTTPException(status_code=503,detail="Image integrity unavailable")
        # Return the exact bytes verified above, even if a new candidate
        # replaces the file before the response is sent.
        return Response(payload,media_type="image/png",
                        headers={"Cache-Control":"private,no-store"})

    @app.get(prefix+"/jobs/{job_id}/artifacts/{kind}")
    def download(job_id:str,kind:str,request:Request):
        actor=authorized(request,job_id)
        single_image_job(actor,job_id)
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
