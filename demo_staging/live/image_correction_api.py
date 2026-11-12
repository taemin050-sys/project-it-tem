"""Signed Job-scoped surgical Freeform text correction endpoints, opt-in only."""
from __future__ import annotations

from typing import Literal
import sqlite3

from fastapi import HTTPException, Request
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .contracts import LiveGateError
from demo_staging.live_safety import LiveNotAuthorized
from .image_correction import ImageCorrections, enabled


class CorrectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_image_sha: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_copy_sha: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_approval_sha: str = Field(pattern=r"^[0-9a-f]{64}$")
    field: Literal["headline", "subline", "cta"]
    observed_text: str = Field(min_length=1, max_length=600)
    region: list[float | int] = Field(min_length=4, max_length=4)
    request_key: str = Field(pattern=r"^[0-9a-f]{32}$")
    acknowledge_paid_edit: bool
    preserve_style_context: bool = False
    matte_style_context: bool = False
    stroke_source_box: list[int] | None = Field(default=None, min_length=4,max_length=4)


class CorrectionVisualReview(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    product_matches: bool
    label_matches: bool
    cta_policy_matches: bool
    no_extra_text: bool
    observed_copy: dict[str, str] | None = None
    copy_verified: bool | None = None


class EdgeBlendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_revision: int = Field(ge=0)
    expected_preview_sha: str = Field(pattern=r"^[0-9a-f]{64}$")


class CorrectionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_revision: int = Field(ge=0)
    expected_preview_sha: str = Field(pattern=r"^[0-9a-f]{64}$")
    approve: bool
    visual_review: CorrectionVisualReview | None = None


class InpaintingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_image_sha: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_copy_sha: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_approval_sha: str = Field(pattern=r"^[0-9a-f]{64}$")
    mask_png_base64: str = Field(min_length=1, max_length=2_800_000)
    prompt: str = Field(min_length=3, max_length=1200)
    request_key: str = Field(pattern=r"^[0-9a-f]{32}$")
    acknowledge_paid_edit: bool
    source_edit_id: str | None = Field(default=None,pattern=r"^[0-9a-f]{32}$")


def install_image_correction_routes(app, flow, authorized, require_queue, *, service_type=ImageCorrections,
                                    namespace="image-corrections", request_model=CorrectionRequest):
    service = service_type(flow)
    prefix = "/demo/api/live/jobs/{job_id}/" + namespace
    setattr(app.state, namespace.replace("-", "_"), service)

    def actor_for(request, job_id, *, write=False):
        actor = authorized(request)
        parent = flow.state.live_dual_membership(actor, job_id)
        authorized(request, parent or job_id)
        if not enabled():
            raise HTTPException(404, "IMAGE_CORRECTION_DISABLED")
        if write:
            identity = app.state.demo_request_identity(request)
            if not identity or identity[1] not in ("admin", "evaluator"):
                raise HTTPException(403, "IMAGE_CORRECTION_REVIEWER_FORBIDDEN")
            # Evaluators may edit only their own authenticated Job (the
            # parent/ledger ACL above remains authoritative), with a paid permit.
            try:
                flow.require_live_actor(actor)
            except LiveNotAuthorized:
                raise HTTPException(423, "IMAGE_CORRECTION_ACTOR_NOT_APPROVED") from None
        return actor

    def call(action):
        try:
            return action()
        except HTTPException:
            raise
        except LiveNotAuthorized:
            raise HTTPException(423, "IMAGE_CORRECTION_ACTOR_NOT_APPROVED") from None
        except LiveGateError as error:
            raise HTTPException(404 if "NOT_FOUND" in error.code else 409, error.code) from None
        except (sqlite3.Error, OSError):
            raise HTTPException(503, "IMAGE_CORRECTION_STORAGE_UNAVAILABLE") from None
        except (ValueError, TypeError, KeyError):
            raise HTTPException(422, "IMAGE_CORRECTION_CONTRACT_INVALID") from None

    @app.get(prefix)
    def listing(job_id: str, request: Request):
        if not enabled():
            actor = authorized(request)
            parent = flow.state.live_dual_membership(actor, job_id)
            authorized(request, parent or job_id)
            return {"job_id": job_id, "available": False, "corrections": []}
        actor = actor_for(request, job_id)
        def snapshot():
            from .revision_costs import revision_cost_summary
            kwargs=({'source_edit_id':request.query_params.get('source_edit_id')} if namespace=='final-inpainting' else {})
            return {**service.snapshot(actor, job_id,**kwargs),
                    "cost_summary": revision_cost_summary(flow, actor, job_id)}
        return call(snapshot)

    def prepare(job_id: str, body, request: Request):
        actor = actor_for(request, job_id, write=True)
        require_queue(actor)
        return call(lambda: JSONResponse(service.request(actor, job_id, body.model_dump(mode="json", exclude_defaults=True)), status_code=202))
    prepare.__annotations__["body"] = request_model
    app.post(prefix)(prepare)

    @app.get(prefix + "/source")
    def source(job_id: str, sha256: str, request: Request):
        actor = actor_for(request, job_id)
        def read():
            args=([request.query_params.get('source_edit_id')] if namespace=='final-inpainting' else [])
            _, context, raw, _ = service.source(actor, job_id,*args)
            if sha256 != context["source_image_sha"]:
                raise LiveGateError("IMAGE_CORRECTION_SOURCE_STALE")
            return Response(raw, media_type="image/png", headers={"Cache-Control": "no-store",
                "X-IT-TEM-Review": "SOURCE_FOR_CORRECTION_ONLY", "X-Content-SHA256": sha256})
        return call(read)

    @app.get(prefix + "/{correction_id}/artifacts/{kind}")
    def artifact(job_id: str, correction_id: str, kind: str, sha256: str, request: Request):
        actor = actor_for(request, job_id)
        def read():
            raw, mime = service.artifact(actor, job_id, correction_id, kind, sha256)
            return Response(raw, media_type=mime, headers={"Cache-Control": "no-store",
                "X-IT-TEM-Render-Mode": "independent-correction-see-receipt", "X-Content-SHA256": sha256})
        return call(read)

    if namespace == "final-inpainting":
        @app.post(prefix + "/{correction_id}/blend-edges")
        def blend_edges(job_id: str, correction_id: str, body: EdgeBlendRequest, request: Request):
            actor = actor_for(request, job_id, write=True)
            return call(lambda: service.blend_edges(actor, job_id, correction_id, body.model_dump(mode="json")))

    if namespace == 'image-corrections':
        @app.post(prefix + '/{correction_id}/fit-text')
        def fit_text(job_id: str, correction_id: str, body: EdgeBlendRequest, request: Request):
            actor=actor_for(request,job_id,write=True)
            return call(lambda: service.fit_text(actor,job_id,correction_id,body.model_dump(mode='json')))

    @app.post(prefix + "/{correction_id}/decision")
    def decision(job_id: str, correction_id: str, body: CorrectionDecision, request: Request):
        actor = actor_for(request, job_id, write=True)
        return call(lambda: service.decision(actor, job_id, correction_id, body.model_dump(mode="json", exclude_none=True)))
