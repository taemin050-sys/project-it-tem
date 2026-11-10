"""A51D: actual demo HTTP→B0 JobStore MPO preview/select integration, FIXTURE ONLY.

These routes exist only when a non-production local QA app explicitly opts in.
They are never installed on GCP A, Live or Owner production. All photos and
test tokens remain in local process memory; no provider or model I/O.

The Image Owner #24 / FE #26 / PM must still authorize a final MPO policy,
review the actor/job persistence format, and supply commercial usage rights
before any real-beta activation. This module is not that authorization.
"""
from __future__ import annotations

from base64 import b64encode
from hashlib import sha256
from io import BytesIO
import json
import secrets
import threading
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from demo_staging.live.contracts import LiveGateError
from demo_staging.live.a51c_explicit_mpo_ingress import (
    CONFIRM, CONTRACT, FrameSelection, inspect_source, preview_frame,
    normalize_selected_source, MAX_UPLOAD,
)
from src.serving.job_api import MAX_TOTAL_BYTES, validate_upload

MODE = "A51D_MPO_PREVIEW_EXPLICIT_SELECT_FIXTURE_V1"
TOKEN_TTL_SECONDS = 5 * 60
MAX_PREVIEW_TOKENS = 24


class MpoConfirm(BaseModel):
    model_config=ConfigDict(extra="forbid", strict=True)
    token: str=Field(min_length=40,max_length=80)
    selected_frame_index: StrictInt=Field(ge=0,le=15)
    selected_preview_sha256: str=Field(pattern=r"^[a-f0-9]{64}$")


class MpoChoice(BaseModel):
    model_config=ConfigDict(extra="forbid", strict=True)
    category: str
    index: StrictInt=Field(ge=0, le=4)
    token: str=Field(min_length=40, max_length=80)
    selected_frame_index: StrictInt=Field(ge=0, le=15)
    selected_preview_sha256: str=Field(pattern=r"^[a-f0-9]{64}$")


def _bad(code:str, status:int=422):
    # A typed, sanitized code. Never echo submitted filenames/source paths.
    raise HTTPException(status_code=status, detail="A51D_"+code)


async def _read(upload:UploadFile)->bytes:
    try:
        data=await upload.read(MAX_UPLOAD+1)
    finally:
        await upload.close()
    if not data or len(data)>MAX_UPLOAD:
        _bad("PHOTO_SIZE_INVALID",413 if len(data)>MAX_UPLOAD else 422)
    return data


def _actual_mpo(data:bytes, name:str)->bool:
    try:
        with Image.open(BytesIO(data)) as im:
            mpo=(im.format=="MPO")
    except (OSError,UnidentifiedImageError,ValueError):
        _bad("PHOTO_CONTAINER_INVALID")
    # An .mpo name must contain a real MPO, even if the MIME is misleading.
    if name.lower().endswith(".mpo") and not mpo:
        _bad("MPO_SUFFIX_CONTAINER_MISMATCH")
    return mpo


def register_fixture_mpo_bridge(app:FastAPI, ledger)->None:
    """Install only from make_demo_app after configured *test-only* opt-in.

    Does not alter the existing B0 or Image Owner routes. Safe to leave code
    in branch with installation disabled. The server's existing /demo/api
    middleware authenticates all requests and enforces same-origin CSRF.
    """
    pending:dict[str,dict]={}
    lock=threading.RLock()

    def actor_of(request:Request)->str:
        identity=app.state.demo_request_identity(request)
        if not identity:
            _bad("ACTOR_NOT_AUTHENTICATED",401)
        return identity[0]

    def prune(now:float):
        for key,record in list(pending.items()):
            if record["expires"] < now:
                pending.pop(key,None)

    @app.post("/demo/api/a51d/mpo/preview")
    async def preview(request:Request, photo:UploadFile=File(...)):
        actor=actor_of(request)
        raw=await _read(photo)
        try:
            inspected=inspect_source(
                raw,filename=photo.filename or "",mime=photo.content_type or "")
            frames=[{
                "index":f["index"],
                "width":f["width"],"height":f["height"],
                "preview_png_sha256":f["preview_png_sha256"],
                "preview_data_uri":"data:image/png;base64,"+b64encode(
                    preview_frame(raw,filename=photo.filename or "",
                                  mime=photo.content_type or "",
                                  index=f["index"])).decode("ascii"),
            } for f in inspected["candidate_frames"]]
        except LiveGateError:
            _bad("MPO_INSPECTION_FAILED")
        now=time.monotonic()
        with lock:
            prune(now)
            if len(pending)>=MAX_PREVIEW_TOKENS:
                _bad("PREVIEW_CAPACITY_EXHAUSTED",429)
            token=secrets.token_urlsafe(32)
            pending[sha256(token.encode()).hexdigest()]={
                "actor":actor,
                "sha":inspected["original_sha256"],
                "count":inspected["source_frame_count"],
                "previews":{f["index"]:f["preview_png_sha256"] for f in frames},
                "expires":now+TOKEN_TTL_SECONDS,
                "confirmed_selection":None,
            }
        return {
            "contract":MODE,
            "token":token,
            "source_sha256":inspected["original_sha256"],
            "source_frame_count":inspected["source_frame_count"],
            "frames":frames,
            "requires_explicit_confirmation":True,
            "provider_calls":0,
            "contract_final_owner_approved":False,
        }

    @app.post("/demo/api/a51d/mpo/confirm")
    async def confirm_selection(request:Request,choice:MpoConfirm):
        """Separate authenticated *user action* receipt, consumed by Job POST.

        A direct HTTP invocation by an authenticated actor still cannot prove
        subjective human perception of the image; test UI click + trace is
        evidence of browser interaction, not an Owner release approval.
        """
        actor=actor_of(request)
        now=time.monotonic()
        token_key=sha256(choice.token.encode()).hexdigest()
        with lock:
            prune(now)
            rec=pending.get(token_key)
            if (not rec or rec["actor"]!=actor or rec["expires"]<now
                or rec["confirmed_selection"] is not None
                or rec["previews"].get(choice.selected_frame_index)!=
                    choice.selected_preview_sha256):
                _bad("FRAME_CONFIRM_ACTOR_TOKEN_CAS_DENIED",409)
            rec["confirmed_selection"]=(
                choice.selected_frame_index,choice.selected_preview_sha256)
        return {"contract":MODE,"confirmed":True,"frame_index":
                choice.selected_frame_index,"provider_calls":0}

    @app.post("/demo/api/a51d/mpo/jobs",status_code=201)
    async def create_mpo_job(request:Request,
                product_images:list[UploadFile]=File(...),
                reference_images:list[UploadFile]|None=File(None),
                mpo_choices_json:str=Form(...)):
        actor=actor_of(request)
        ref=reference_images or []
        if not 2<=len(product_images)<=5 or len(ref)>5:
            _bad("ONE_PRODUCT_2_TO_5_INPUTS_REQUIRED")
        try:
            choices=json.loads(mpo_choices_json)
            if type(choices) is not list or len(choices)>10:
                _bad("CHOICE_LIST_INVALID")
            records=[MpoChoice.model_validate(c,strict=True) for c in choices]
        except (ValueError,TypeError):
            _bad("CHOICE_PAYLOAD_INVALID")
        selection:dict[tuple[str,int],MpoChoice]={}
        for choice in records:
            if choice.category not in ("product","reference"):
                _bad("CHOICE_CATEGORY_INVALID")
            key=(choice.category,choice.index)
            if key in selection:
                _bad("DUPLICATE_FRAME_CHOICE")
            selection[key]=choice

        outputs={"product":[],"reference":[]}
        total_bytes=0
        # All source SHA / selection checks before persisting ANY asset.
        # Race-safe token consumption happens under the same lock. A missing
        # token or mismatched Actor+frame is never a fallback to frame 0.
        with lock:
            now=time.monotonic()
            prune(now)
            used:set[str]=set()
            for role,files in (("product",product_images),("reference",ref)):
                for idx,file in enumerate(files):
                    raw=await _read(file)
                    total_bytes+=len(raw)
                    if total_bytes>MAX_TOTAL_BYTES:
                        _bad("TOTAL_INPUT_TOO_LARGE",413)
                    name=file.filename or ""
                    actual=_actual_mpo(raw,name)
                    choice=selection.get((role,idx))
                    if actual and choice is None:
                        _bad("EXPLICIT_FRAME_SELECTION_REQUIRED")
                    if not actual and choice is not None:
                        _bad("NON_MPO_CANNOT_HAVE_FRAME_SELECTION")
                    if actual:
                        token_key=sha256(choice.token.encode()).hexdigest()
                        preview=pending.get(token_key)
                        if (not preview or preview["actor"]!=actor or
                                preview["sha"]!=sha256(raw).hexdigest() or
                                preview["expires"]<now or
                                preview["confirmed_selection"]!=(
                                    choice.selected_frame_index,
                                    choice.selected_preview_sha256) or
                                choice.selected_frame_index not in preview["previews"] or
                                choice.selected_preview_sha256!=preview["previews"][
                                    choice.selected_frame_index] or token_key in used):
                            _bad("PREVIEW_TOKEN_ACTOR_SHA_OR_FRAME_MISMATCH",409)
                        selected=FrameSelection(
                            contract=CONTRACT,
                            original_sha256=preview["sha"],
                            source_frame_count=preview["count"],
                            selected_frame_index=choice.selected_frame_index,
                            selected_preview_sha256=choice.selected_preview_sha256,
                            confirmation=CONFIRM,
                            upload_request_sha256=sha256(
                                (actor+":"+token_key).encode()).hexdigest(),
                        )
                        try:
                            norm=normalize_selected_source(
                                raw,filename=name,mime=file.content_type or "",
                                selected=selected,
                                expected_upload_request_sha256=selected.upload_request_sha256)
                        except LiveGateError:
                            _bad("MPO_NORMALIZATION_FAILED")
                        outputs[role].append(norm)
                        used.add(token_key)
                    else:
                        # Calls official B0 upload validation (does not change
                        # its historical primary-frame MPO behavior).
                        from starlette.datastructures import UploadFile as SUpload
                        normal=SUpload(filename=name,file=BytesIO(raw),
                                       headers=file.headers)
                        outputs[role].append(await validate_upload(normal))
            if len(used)!=len(selection):
                _bad("UNUSED_OR_MISSING_FRAME_CHOICE")
            for token_key in used:
                pending.pop(token_key,None)

        if sum(len(x.data) for x in outputs["product"]+outputs["reference"])>MAX_TOTAL_BYTES:
            _bad("TOTAL_NORMALIZED_INPUT_TOO_LARGE",413)
        job=app.state.job_store.create_job(outputs["product"],outputs["reference"])
        # This route lies under /demo/api/ and is not auto-claimed by the B0
        # middleware; explicitly persist ownership before sending a job ID.
        try:
            ledger.claim(actor,job["job_id"])
        except Exception:
            _bad("JOB_OWNERSHIP_PERSIST_FAILED",503)
        return job
