"""Signed, Job-scoped original-product derivative routes. Default disabled."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from src.image_generation.protected_recipe import ContentRef
from .contracts import LiveGateError


Sha = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Revision = Annotated[int, Field(strict=True, ge=0, le=9_007_199_254_740_991)]


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Admit(Body):
    proposal_id: Sha
    expected_context_sha: Sha
    expected_recipe_sha: Sha
    expected_revision: Revision
    acknowledge_source: bool


class Prepare(Body):
    admission_sha: Sha
    expected_context_sha: Sha
    expected_recipe_sha: Sha
    idempotency_key: Sha


class VisualReview(Body):
    source_pixels_preserved: bool
    edges_acceptable: bool
    no_duplicate_product: bool
    no_ghost_product: bool
    no_copy_occlusion: bool
    cta_policy_matches: bool
    label_ground_truth_confirmed: bool
    mobile_readable: bool
    observed_copy: dict[str, str]


class Decision(Body):
    expected_revision: Revision
    expected_preview_sha: Sha
    expected_recipe_sha: Sha
    expected_context_sha: Sha
    approve: bool
    visual_review: VisualReview


class Finalize(Body):
    expected_revision: Revision
    expected_approval_sha: Sha
    expected_preview_sha: Sha


class Selection(Body):
    derived_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
    expected_final_sha: Sha
    expected_approval_sha: Sha


class Revoke(Body):
    expected_revision: Revision
    expected_context_sha: Sha
    expected_admission_sha: Sha


class Configure(Body):
    source_asset_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
    mask_ref: ContentRef | None = None
    source_crop: list[Revision] | None = Field(default=None, min_length=4, max_length=4)
    registered_size: list[Revision] | None = Field(default=None, min_length=2, max_length=2)
    output_offset: list[Revision] | None = Field(default=None, min_length=2, max_length=2)
    protected_rois: dict[str, list[Revision]] | None = Field(default=None, max_length=20)
    model_regions: list[list[Revision]] = Field(default_factory=list, max_length=12)
    copy_exclusions: list[list[Revision]] = Field(default_factory=list, max_length=12)
    acknowledge_regions: bool


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("DERIVED_JSON_DUPLICATE_KEY")
        result[key] = value
    return result


async def _strict_json(request: Request):
    if request.method in ("POST", "PUT", "PATCH") and request.headers.get("content-type", "").startswith("application/json"):
        data = await request.body()
        if len(data) > 128*1024:
            raise HTTPException(413, "DERIVED_JSON_LIMIT")
        def invalid(_):
            raise ValueError
        try:
            json.loads(data, object_pairs_hook=_unique, parse_constant=invalid)
        except (ValueError, UnicodeError, RecursionError):
            raise HTTPException(422, "DERIVED_JSON_INVALID") from None


def register_derived_api(app, ledger, flow, runtime_root):
    prefix = "/demo/api/live/jobs/{job_id}/derived"
    router = APIRouter(prefix=prefix, dependencies=[Depends(_strict_json)])
    cached = {}

    def identity(request):
        value = app.state.demo_request_identity(request)
        if value is None:
            raise HTTPException(401, "Login required")
        return value

    def configured():
        return (os.environ.get("IT_TEM_DERIVED_ENABLED") == "YES"
                and os.environ.get("IT_TEM_TAILNET_AUTH_ENABLED") == "YES"
                and os.environ.get("IT_TEM_TAILNET_SSO_ONLY") == "YES")

    def service():
        if not configured():
            raise HTTPException(404, "DERIVED_DISABLED")
        if "service" not in cached:
            from .derived_worker import service_from_runtime
            cached["service"] = service_from_runtime(runtime_root)
            # Use the already-running app's exact state and owner registry.
            cached["service"].state = flow.state
            cached["service"].jobs = flow.jobs
            cached["service"].owns = ledger.owns
            cached["service"].registry.jobs = flow.jobs
            cached["service"].registry.owns = cached["service"].owns_job
            app.state.derived_service = cached["service"]
        return cached["service"]

    def call(action):
        try:
            return action()
        except HTTPException:
            raise
        except LiveGateError as error:
            code = error.code
            if "NOT_FOUND" in code:
                status = 404
            elif "BUSINESS_ROLE" in code or "FORBIDDEN" in code:
                status = 403
            elif "UNAVAILABLE" in code or "CORRUPT" in code or "INTEGRITY" in code or "SCHEMA" in code:
                status = 503
            else:
                status = 409
            raise HTTPException(status, code) from None
        except (sqlite3.Error, OSError):
            raise HTTPException(503, "DERIVED_STORAGE_UNAVAILABLE") from None
        except (ValueError, TypeError, KeyError):
            raise HTTPException(422, "DERIVED_CONTRACT_INVALID") from None

    @router.get("")
    def listing(job_id: str, request: Request):
        actor, role = identity(request)
        if not configured():
            if not ledger.owns(actor, job_id):
                raise HTTPException(404, "Job not found")
            return {"job_id": job_id, "available": False, "can_admit": False, "can_review": False,
                    "context_sha": "", "revision": 0, "hold_code": None, "proposals": [], "renders": [], "selected_derived_id": None}
        return call(lambda: service().snapshot(actor, role, job_id))

    @router.post("/proposals")
    def proposal(job_id: str, body: Configure, request: Request):
        actor, role = identity(request)
        return call(lambda: service().save_proposal(actor, role, job_id, body.model_dump(mode="json", exclude_none=True)))

    @router.post("/assets")
    async def upload(job_id: str, request: Request, file: UploadFile = File(), kind: str = Form()):
        actor, role = identity(request)
        if kind != "product_mask":
            raise HTTPException(422, "DERIVED_UPLOAD_KIND_INVALID")
        raw = await file.read(32*1024*1024+1)
        if len(raw) > 32*1024*1024:
            raise HTTPException(413, "DERIVED_ASSET_BYTE_LIMIT")
        def write():
            current = service()
            with current.store.transaction() as c:
                owner, _, _, _, _ = current.context(c, actor, role, job_id, "admit")
                return current.registry.put_content(owner, job_id, raw, "image/png", kind="product_mask").model_dump()
        return call(write)

    @router.post("/recipes/admit")
    def admit(job_id: str, body: Admit, request: Request):
        actor, role = identity(request)
        return call(lambda: service().admit(actor, role, job_id, body.model_dump()))

    @router.post("/renders", status_code=202)
    def prepare(job_id: str, body: Prepare, request: Request):
        actor, role = identity(request)
        return call(lambda: service().prepare(actor, role, job_id, body.model_dump()))

    @router.get("/renders/{derived_id}")
    def render(job_id: str, derived_id: str, request: Request):
        actor, role = identity(request)
        def read():
            current = service()
            with current.store.connection(readonly=True) as c:
                owner, _, _, context_sha, _ = current.context(c, actor, role, job_id, "read")
                return current.public_render(current.store.get_render(owner, job_id, derived_id, c=c), context_sha)
        return call(read)

    @router.post("/renders/{derived_id}/decision")
    def decision(job_id: str, derived_id: str, body: Decision, request: Request):
        actor, role = identity(request)
        return call(lambda: service().decide(actor, role, job_id, derived_id, body.model_dump()))

    @router.post("/renders/{derived_id}/finalize")
    def finalize(job_id: str, derived_id: str, body: Finalize, request: Request):
        actor, role = identity(request)
        return call(lambda: service().finalize(actor, role, job_id, derived_id, body.model_dump()))

    @router.post("/renders/{derived_id}/revoke-admission")
    def revoke(job_id: str, derived_id: str, body: Revoke, request: Request):
        actor, role = identity(request)
        return call(lambda: service().revoke(actor, role, job_id, derived_id, body.model_dump()))

    @router.post("/selection")
    def selection(job_id: str, body: Selection, request: Request):
        actor, role = identity(request)
        def choose():
            current = service()
            current.select(actor, role, job_id, body.model_dump())
            return current.snapshot(actor, role, job_id)
        return call(choose)

    @router.get("/renders/{derived_id}/artifacts/{kind}")
    def artifact(job_id: str, derived_id: str, kind: Literal["preview", "final", "caption", "receipt"], sha256: str, request: Request):
        actor, role = identity(request)
        def read():
            current = service()
            with current.store.connection(readonly=True) as c:
                owner, _, _, context_sha, _ = current.context(c, actor, role, job_id, "read")
                row = current.store.get_render(owner, job_id, derived_id, c=c)
                if row["context_sha"] != context_sha or row.get(kind+"_sha") != sha256:
                    raise LiveGateError("DERIVED_ARTIFACT_STALE")
                current.store._bound_admission(c, row)
                if kind != "preview":
                    current.store.require_approval(owner, job_id, derived_id, c=c)
                    if row["state"] != "COMPLETED":
                        raise LiveGateError("DERIVED_FINAL_NOT_AVAILABLE")
                raw = current.read_artifact(owner, job_id, row, kind)
            media = {"preview": "image/png", "final": "image/png", "caption": "text/plain; charset=utf-8", "receipt": "application/json"}[kind]
            filename = {"preview": "preview.png", "final": "protected-ad.png", "caption": "caption.txt", "receipt": "receipt.json"}[kind]
            headers = {"Cache-Control": "private,no-store", "X-IT-TEM-Provenance": "DERIVED_PROTECTED_PRODUCT"}
            if kind != "preview":
                headers["Content-Disposition"] = f'attachment; filename="{filename}"'
            return Response(raw, media_type=media, headers=headers)
        return call(read)

    app.include_router(router)
