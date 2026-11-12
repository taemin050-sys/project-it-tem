"""Signed, Job-scoped manual Composed copy revision routes; no HTTP model call."""
from __future__ import annotations

from typing import Annotated
import sqlite3

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from demo_staging.live_safety import LiveNotAuthorized
from .contracts import LiveGateError
from .composed_copy_edit import ComposedCopyEdits, enabled

Sha = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class AdCopy(Body):
    headline: str = Field(min_length=1, max_length=600)
    subline: str = Field(max_length=2000)
    cta: str = Field(max_length=600)


class Create(Body):
    expected_image_sha: Sha
    expected_copy_sha: Sha
    expected_approval_sha: Sha
    ad_copy: AdCopy
    request_key: str = Field(pattern=r"^[0-9a-f]{32}$")


class CopyApproval(Body):
    expected_revision: int = Field(ge=0)
    expected_copy_sha: Sha
    expected_review_sha: Sha
    acknowledge_evidence: bool


class VisualReview(Body):
    product_matches: bool
    label_matches: bool
    cta_policy_matches: bool
    observed_copy: AdCopy | None = None
    copy_verified: bool | None = None
    no_extra_text: bool


class Decision(Body):
    expected_revision: int = Field(ge=0)
    expected_preview_sha: Sha
    approve: bool
    visual_review: VisualReview | None = None


def install_composed_copy_edit_routes(app, flow, authorized, require_queue):
    prefix = "/demo/api/live/jobs/{job_id}/composed-copy-edits"
    router = APIRouter(prefix=prefix)
    service = ComposedCopyEdits(flow)
    app.state.composed_copy_edit_service = service

    def access(request, job_id, *, write=False):
        actor = authorized(request, job_id)
        if not enabled():
            raise HTTPException(404, "COMPOSED_EDIT_DISABLED")
        identity = app.state.demo_request_identity(request)
        if write:
            if not identity or identity[1] not in ("admin", "evaluator"):
                raise HTTPException(403, "COMPOSED_EDIT_OWNER_REQUIRED")
            # Signed evaluators remain ordinary owners, never administrators
            # or delegates. Every write also requires the existing paid allowlist.
            try:
                flow.require_live_actor(actor)
            except LiveNotAuthorized:
                raise HTTPException(423, "COMPOSED_EDIT_EXECUTION_NOT_AUTHORIZED") from None
        return actor

    def call(action):
        try:
            return action()
        except LiveNotAuthorized:
            raise HTTPException(423, "COMPOSED_EDIT_EXECUTION_NOT_AUTHORIZED") from None
        except LiveGateError as error:
            code = error.code
            raise HTTPException(404 if "NOT_FOUND" in code else 409, code) from None
        except (OSError, sqlite3.Error):
            raise HTTPException(503, "COMPOSED_EDIT_STORAGE_UNAVAILABLE") from None
        except (ValueError, TypeError, KeyError):
            raise HTTPException(422, "COMPOSED_EDIT_CONTRACT_INVALID") from None

    @router.get("")
    def listing(job_id: str, request: Request):
        actor = authorized(request, job_id)
        if not enabled():
            return {"job_id": job_id, "available": False, "edits": []}
        return call(lambda: service.snapshot(actor, job_id))

    @router.post("")
    def create(job_id: str, body: Create, request: Request):
        actor = access(request, job_id, write=True)
        require_queue(actor)
        result = call(lambda: service.create(actor, job_id, body.model_dump(mode="json")))
        from fastapi.responses import JSONResponse
        return JSONResponse(result, status_code=202 if result["state"] == "QUEUED_REVIEW" else 200)

    @router.post("/{edit_id}/copy-approval")
    def copy_approval(job_id: str, edit_id: str, body: CopyApproval, request: Request):
        actor = access(request, job_id, write=True)
        return call(lambda: service.approve_copy(actor, job_id, edit_id, body.model_dump(mode="json")))

    @router.post("/{edit_id}/decision")
    def decision(job_id: str, edit_id: str, body: Decision, request: Request):
        actor = access(request, job_id, write=True)
        return call(lambda: service.decide(actor, job_id, edit_id, body.model_dump(mode="json", exclude_none=True)))

    @router.get("/{edit_id}/artifacts/{kind}")
    def artifact(job_id: str, edit_id: str, kind: str, request: Request, sha256: str):
        actor = access(request, job_id)
        raw = call(lambda: service.artifact(actor, job_id, edit_id, kind, sha256))
        media = {"preview": "image/png", "final": "image/png", "caption": "text/plain; charset=utf-8", "receipt": "application/json"}
        return Response(raw, media_type=media.get(kind, "application/octet-stream"),
                        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})

    app.include_router(router)
