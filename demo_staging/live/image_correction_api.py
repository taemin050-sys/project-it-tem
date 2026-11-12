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


class CorrectionVisualReview(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    product_matches: bool
    label_matches: bool
    cta_policy_matches: bool
    no_extra_text: bool
    observed_copy: dict[str, str]


class CorrectionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_revision: int = Field(ge=0)
    expected_preview_sha: str = Field(pattern=r"^[0-9a-f]{64}$")
    approve: bool
    visual_review: CorrectionVisualReview | None = None


def install_image_correction_routes(app, flow, authorized, require_queue):
    service = ImageCorrections(flow)
    prefix = "/demo/api/live/jobs/{job_id}/image-corrections"
    app.state.image_corrections = service

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
            return {**service.snapshot(actor, job_id),
                    "cost_summary": revision_cost_summary(flow, actor, job_id)}
        return call(snapshot)

    @app.post(prefix)
    def prepare(job_id: str, body: CorrectionRequest, request: Request):
        actor = actor_for(request, job_id, write=True)
        require_queue(actor)
        return call(lambda: JSONResponse(service.request(actor, job_id, body.model_dump(mode="json", exclude_defaults=True)), status_code=202))

    @app.get(prefix + "/source")
    def source(job_id: str, sha256: str, request: Request):
        actor = actor_for(request, job_id)
        def read():
            _, context, raw, _ = service.source(actor, job_id)
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
                "X-IT-TEM-Render-Mode": "freeform_model_text_corrected_v1", "X-Content-SHA256": sha256})
        return call(read)

    @app.post(prefix + "/{correction_id}/decision")
    def decision(job_id: str, correction_id: str, body: CorrectionDecision, request: Request):
        actor = actor_for(request, job_id, write=True)
        return call(lambda: service.decision(actor, job_id, correction_id, body.model_dump(mode="json")))
