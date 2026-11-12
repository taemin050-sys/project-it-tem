"""A51C additive, offline-only MPO frame choice/normalization prototype.

NOT connected to the public B0 upload route until Image Owner #24 and FE #26
approve the actual Beta contract. No silent frame-0 selection, no provider
transfer and no customer rights/brand attestation. No old v2 schema changes.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import re
import warnings

from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from .contracts import LiveGateError
from src.serving.job_store import ValidatedUpload

CONTRACT="IT_TEM_P03_A51C_MPO_EXPLICIT_USER_SELECTION_PROPOSAL_V1"
CONFIRM="USER_VIEWED_AND_CONFIRMED_SELECTED_MPO_FRAME_V1"
COLOR_NORMALIZATION="EXIF_UPRIGHT_ICC_TO_SRGB_V2"
MAX_UPLOAD=10*1024*1024
MAX_PIXELS=40_000_000
FRAME_LIMIT=16
_SHA=re.compile(r"^[a-f0-9]{64}$")
_FILE=re.compile(r"^[^\x00-\x1f/\\]{1,180}$")


def _block(code:str):
    raise LiveGateError("A51C_"+code)


class FrameSelection(BaseModel):
    model_config=ConfigDict(extra="forbid",strict=True)
    contract:str
    original_sha256:str=Field(pattern=r"^[a-f0-9]{64}$")
    selected_frame_index:StrictInt=Field(ge=0,le=15)
    selected_preview_sha256:str=Field(pattern=r"^[a-f0-9]{64}$")
    source_frame_count:StrictInt=Field(ge=2,le=16)
    confirmation:str
    # Server-authenticated caller must be separately bound by job controller.
    # This ID is a context commitment, not a trusted login assertion.
    upload_request_sha256:str=Field(pattern=r"^[a-f0-9]{64}$")


def _sha(raw:bytes)->str:
    return sha256(raw).hexdigest()


def _allowed(raw:bytes, filename:str, mime:str):
    if not isinstance(raw,bytes) or not 8<=len(raw)<=MAX_UPLOAD:
        _block("MPO_INPUT_BYTES_INVALID")
    if not isinstance(filename,str) or not _FILE.fullmatch(filename):
        _block("MPO_INPUT_FILENAME_INVALID")
    if not filename.lower().endswith((".mpo",".jpg",".jpeg")):
        _block("MPO_INPUT_SUFFIX_UNSUPPORTED")
    if mime not in ("image/jpeg","image/mpo","application/octet-stream"):
        _block("MPO_INPUT_MIME_UNSUPPORTED")
    if raw[:2]!=b"\xff\xd8":
        _block("MPO_JPEG_MAGIC_INVALID")


def _frames(raw:bytes):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error",Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as im:
                if im.format!="MPO" or not 2<=getattr(im,"n_frames",0)<=FRAME_LIMIT:
                    _block("REAL_MULTIFRAME_MPO_REQUIRED")
                count=im.n_frames
                for index in range(count):
                    im.seek(index)
                    if (not im.width or not im.height or
                        im.width*im.height>MAX_PIXELS):
                        _block("FRAME_PIXELS_OUT_OF_BOUNDS")
                    im.load()
                    # Each index is inspected independently; never choose a
                    # default. No image metadata is returned to the browser.
                    selected=im.copy()
                    yield index, count, selected
    except (OSError,EOFError,UnidentifiedImageError,
            Image.DecompressionBombError,Image.DecompressionBombWarning,
            ValueError,TypeError) as exc:
        if isinstance(exc,LiveGateError):
            raise
        _block("MPO_DECODE_FAILED")


def _to_srgb_upright(image:Image.Image)->Image.Image:
    """One canonical, fail-closed color transform for both preview and JPEG.

    Color-managed thumbnails must be generated from the same upright sRGB
    pixels as the export, not the source profile's unconverted RGB channels.
    The returned RGB pixels intentionally carry no EXIF or ICC metadata.
    """
    try:
        upright=ImageOps.exif_transpose(image)
        icc=image.info.get("icc_profile")
        if icc:
            converted=ImageCms.profileToProfile(
                upright if upright.mode in ("RGB","CMYK","LAB") else upright.convert("RGB"),
                ImageCms.ImageCmsProfile(BytesIO(icc)),
                ImageCms.createProfile("sRGB"),outputMode="RGB",
            )
        else:
            converted=upright.convert("RGB")
        if converted.width*converted.height>MAX_PIXELS:
            _block("NORMALIZED_PIXELS_OUT_OF_BOUNDS")
        return Image.frombytes("RGB",converted.size,converted.tobytes())
    except (OSError,ValueError,TypeError,ImageCms.PyCMSError) as exc:
        if isinstance(exc,LiveGateError):
            raise
        _block("COLOR_MANAGEMENT_INVALID")


def _preview(image:Image.Image)->bytes:
    clean=_to_srgb_upright(image)
    clean.thumbnail((480,480),resample=Image.Resampling.LANCZOS)
    out=BytesIO()
    clean.save(out,format="PNG")
    return out.getvalue()


def inspect_source(raw:bytes, *, filename:str, mime:str):
    """Return no preview image bytes to log/manifest.

    Actual previews are returned separately, in memory, to an authenticated
    local caller. The preview digest is a visual confirmation commitment.
    """
    _allowed(raw,filename,mime)
    inspected=list(_frames(raw))
    return {
        "contract":CONTRACT,
        "original_sha256":_sha(raw),
        "source_frame_count":len(inspected),
        "color_normalization_contract":COLOR_NORMALIZATION,
        "candidate_frames":[{
            "index":index,
            "width":image.width,
            "height":image.height,
            "preview_png_sha256":_sha(_preview(image)),
            "decoded_rgb_sha256":_sha(image.convert("RGB").tobytes()),
            "exif_orientation":image.getexif().get(274,1),
            "icc_sha256":_sha(image.info["icc_profile"])
                if image.info.get("icc_profile") else None,
        } for index,_,image in inspected],
        "implicit_frame_selected":False,
        "user_confirmation_required":True,
        "provider_transfer_authorized":False,
        "product_rights_verified":False,
        "normalized_output_created":False,
    }


def preview_frame(raw:bytes, *, filename:str, mime:str, index:int)->bytes:
    """MPO preview bytes, trusted code only; no disk or Provider side effect."""
    _allowed(raw,filename,mime)
    if type(index) is not int or not 0<=index<FRAME_LIMIT:
        _block("PREVIEW_FRAME_INDEX_INVALID")
    for i,_,image in _frames(raw):
        if i==index:
            return _preview(image)
    _block("PREVIEW_FRAME_NOT_FOUND")


def normalize_selected_source(raw:bytes, *,
                              filename:str,
                              mime:str,
                              selected:FrameSelection,
                              expected_upload_request_sha256:str)->ValidatedUpload:
    """Called ONLY after visually selected frame and origin/context binding.

    Request/actor authentication is an external controller concern. This
    function *never* grants permission to upload a source photo to Provider.
    """
    _allowed(raw,filename,mime)
    if not isinstance(selected,FrameSelection):
        _block("FRAME_SELECTION_SCHEMA_INVALID")
    if (selected.contract!=CONTRACT or selected.confirmation!=CONFIRM or
        selected.original_sha256!=_sha(raw) or
        type(expected_upload_request_sha256) is not str or
        not _SHA.fullmatch(expected_upload_request_sha256) or
        selected.upload_request_sha256!=expected_upload_request_sha256):
        _block("FRAME_USER_CHOICE_OR_JOB_CONTEXT_MISSING")
    inspected=inspect_source(raw,filename=filename,mime=mime)
    count=inspected["source_frame_count"]
    if selected.source_frame_count!=count or selected.selected_frame_index>=count:
        _block("FRAME_INDEX_OR_COUNT_MISMATCH")
    entry=inspected["candidate_frames"][selected.selected_frame_index]
    if selected.selected_preview_sha256!=entry["preview_png_sha256"]:
        _block("FRAME_VISUAL_PREVIEW_COMMITMENT_MISMATCH")
    for i,_,image in _frames(raw):
        if i==selected.selected_frame_index:
            break
    try:
        orientation=image.getexif().get(274,1)
        icc=image.info.get("icc_profile")
        clean=_to_srgb_upright(image)
        encoded=BytesIO()
        clean.save(encoded,format="JPEG",quality=94,subsampling=0)
        output=encoded.getvalue()
        if len(output)>MAX_UPLOAD:
            _block("NORMALIZED_BYTES_OUT_OF_BOUNDS")
    except (OSError,ValueError,TypeError,ImageCms.PyCMSError) as exc:
        if isinstance(exc,LiveGateError):
            raise
        _block("NORMALIZATION_FAILED")
    converted_sha=_sha(output)
    result={
        "normalization_contract":CONTRACT,
        "color_normalization_contract":COLOR_NORMALIZATION,
        "original_sha256":_sha(raw),
        "source_filename":filename,
        "source_container_format":"MPO",
        "source_frame_count":count,
        "selected_frame":selected.selected_frame_index,
        "selected_frame_preview_png_sha256":entry["preview_png_sha256"],
        "selected_frame_decoded_rgb_sha256":entry["decoded_rgb_sha256"],
        "selected_frame_srgb_upright_sha256":_sha(_to_srgb_upright(image).tobytes()),
        "explicit_frame_selection_confirmation":CONFIRM,
        "upload_request_sha256":selected.upload_request_sha256,
        "source_exif_orientation":orientation,
        "source_icc_sha256":_sha(icc) if icc else None,
        "normalized_mime_type":"image/jpeg",
        "normalized_sha256":converted_sha,
        "normalized_width":clean.width,
        "normalized_height":clean.height,
        "exif_icc_private_metadata_removed":True,
        "actual_owner_pm_contract_accepted":False,
        "brand_rights_accepted":False,
        "external_provider_transfer_permitted":False,
    }
    return ValidatedUpload(filename,"image/jpeg",output,
                           clean.width,clean.height,converted_sha,result)
