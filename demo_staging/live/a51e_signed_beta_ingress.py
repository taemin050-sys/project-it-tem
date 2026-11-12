"""A51E nonbillable signed-SSO beta candidate's B0 upload admission route.

Requires signed Tailscale assertion on EVERY request; never trusts a browser
actor string or legacy invite cookie. Explicitly blocks all MPO containers
(including MPO disguised as .jpg), pending Image Owner/FE/PM MPO contract.
Must NOT be promoted to real paid beta, GCP or actual customer assets.
No online Provider calls, no Queue, no Owner Image multi-frame fallback.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import json
import re
import shutil

from fastapi import FastAPI,File,Form,Header,HTTPException,Request,UploadFile
from fastapi.responses import JSONResponse
from PIL import Image,UnidentifiedImageError
from starlette.datastructures import UploadFile as StarletteUpload

from .a51e_signed_beta_ingress_ledger import BetaUploadLedger,BetaIngressConflict
from src.serving.job_api import MAX_FILE_BYTES,MAX_TOTAL_BYTES,validate_upload

_ID=re.compile(r"^[0-9a-f]{32}$")
CONTRACT="A51E_SIGNED_SSO_NONBILLABLE_BETA_ADMISSION_CANDIDATE_V1"


def _reject(code:str,status:int=422):
    # Do not echo user-supplied filenames, JSON strings, credential or path.
    raise HTTPException(status_code=status,detail="A51E_"+code)


async def _read_and_validate(file:UploadFile):
    try:
        raw=await file.read(MAX_FILE_BYTES+1)
    finally:
        await file.close()
    if not raw or len(raw)>MAX_FILE_BYTES:
        _reject("SOURCE_SIZE_INVALID",413 if len(raw)>MAX_FILE_BYTES else 422)
    # Decoded container is authoritative, not spoofable extension/MIME.
    try:
        with Image.open(BytesIO(raw)) as image:
            actual_format=image.format
            frames=getattr(image,"n_frames",1)
    except (OSError,UnidentifiedImageError,ValueError,TypeError):
        _reject("INVALID_IMAGE_CONTAINER")
    if actual_format=="MPO" or frames!=1 or (
            file.filename or "").lower().endswith(".mpo"):
        # Until signed Owner/PM policy exists, explicitly reject both ordinary
        # .mpo and hidden MPO-in-JPEG. Never call legacy B0 frame-0 encoder.
        _reject("MPO_OWNER_POLICY_PENDING")
    wrapped=StarletteUpload(filename=file.filename,file=BytesIO(raw),
                            headers=file.headers)
    try:
        validated=await validate_upload(wrapped)
    except HTTPException:
        _reject("B0_INPUT_VALIDATION_FAILED")
    return raw,validated


def register_a51e_signed_beta_ingress(app:FastAPI,ledger,upload_ledger:BetaUploadLedger):
    """Register only after startup verifies A51E nonbillable SSO config."""
    @app.post("/demo/api/a51e/beta/jobs",status_code=201)
    async def create_signed_beta_job(
        request:Request,
        product_images:list[UploadFile]=File(...),
        reference_images:list[UploadFile]|None=File(None),
        product_input_json:str=Form(default=""),
        x_ittem_upload_request_id:str|None=Header(
            default=None,alias="X-IT-TEM-Upload-Request-ID"),
    ):
        identity=app.state.demo_request_identity(request)
        # Signed-only setup ensures identity cannot be supplied by invite.
        if not identity:
            _reject("SIGNED_SSO_REQUIRED",401)
        actor=identity[0]
        if not (isinstance(x_ittem_upload_request_id,str) and
                _ID.fullmatch(x_ittem_upload_request_id)):
            _reject("UPLOAD_REQUEST_ID_REQUIRED")
        refs=reference_images or []
        if not 2<=len(product_images)<=5 or len(refs)>5:
            _reject("PRODUCT_2_TO_5_REFERENCE_0_TO_5_REQUIRED")
        if len(product_input_json.encode("utf8"))>100000:
            _reject("INPUT_CONTEXT_SIZE_INVALID",413)
        # Validate nonempty UI input context if supplied. All file and
        # signed header checks precede any B0 filesystem mutation.
        try:
            if product_input_json and not isinstance(
                json.loads(product_input_json),dict):
                _reject("INPUT_CONTEXT_INVALID")
        except (TypeError,ValueError):
            _reject("INPUT_CONTEXT_INVALID")

        entries=[]
        inputs={"product":[],"reference":[]}
        total=0
        for role,files in (("product",product_images),("reference",refs)):
            for index,file in enumerate(files):
                raw,normalized=await _read_and_validate(file)
                total+=len(raw)
                if total>MAX_TOTAL_BYTES:
                    _reject("TOTAL_SOURCE_BYTES_TOO_LARGE",413)
                entries.append({
                    "role":role,"index":index,
                    "source_sha256":sha256(raw).hexdigest(),
                    "normalized_sha256":normalized.sha256,
                    "content_type":normalized.content_type,
                })
                inputs[role].append(normalized)
        if sum(len(x.data) for x in
                inputs["product"]+inputs["reference"])>MAX_TOTAL_BYTES:
            _reject("TOTAL_VALIDATED_BYTES_TOO_LARGE",413)

        request_sha=sha256(json.dumps({
            "contract":CONTRACT,"actor":actor,
            "source_image_order":entries,
            "product_input_sha256":sha256(
                product_input_json.encode("utf8")).hexdigest(),
        },sort_keys=True,separators=(",",":")).encode()).hexdigest()
        try:
            old_job=upload_ledger.reserve(
                request_id=x_ittem_upload_request_id,
                actor=actor,request_sha256=request_sha)
        except BetaIngressConflict:
            _reject("REQUEST_ID_REPLAY_OR_UNCERTAIN",409)
        if old_job is not None:
            # Idempotent retry returns the SAME Job ID; never redoes create.
            if not ledger.owns(actor,old_job):
                _reject("COMMITTED_JOB_OWNERSHIP_DRIFT",503)
            try:
                old=app.state.job_store.get_job(old_job)
            except HTTPException:
                _reject("COMMITTED_JOB_MISSING",503)
            return JSONResponse(old,status_code=200,
                  headers={"X-IT-TEM-Upload-Idempotent":"REPLAY_SAME_JOB"})

        job=None
        try:
            job=app.state.job_store.create_job(
                inputs["product"],inputs["reference"])
            ledger.claim(actor,job["job_id"])
            upload_ledger.settle(
                request_id=x_ittem_upload_request_id,actor=actor,
                request_sha256=request_sha,job_id=job["job_id"])
            return job
        except Exception:
            # Crash-safe RESERVED/failed tombstone remains even if this
            # exception handler itself dies. Do not automatically issue a
            # second Job because the durable ownership outcome is ambiguous.
            claimed=False
            if job is not None:
                try:
                    claimed=ledger.owns(actor,job["job_id"])
                except Exception:
                    pass
                if not claimed:
                    try:
                        candidate=app.state.job_store._job_dir(job["job_id"])
                        if candidate.is_dir() and not candidate.is_symlink():
                            shutil.rmtree(candidate)
                    except (OSError,ValueError):
                        pass
            try:
                upload_ledger.settle(
                    request_id=x_ittem_upload_request_id,actor=actor,
                    request_sha256=request_sha,
                    job_id=job["job_id"] if claimed else None)
            except Exception:
                # Token stays RESERVED. Human reconciliation required.
                pass
            _reject("JOB_COMMIT_UNCERTAIN_NO_AUTO_RETRY",503)
