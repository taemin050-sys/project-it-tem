"""Provisional IT-TEM upload and job API, for local E2E mock integration only."""

from __future__ import annotations

import io
import os
import warnings
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from PIL import Image, ImageOps, ImageCms, UnidentifiedImageError

from .job_store import JobStore, ValidatedUpload, hash_bytes

router = APIRouter(prefix="/api/v1/jobs", tags=["Jobs — provisional"])

# Provisional prototype limits; not a team-approved product contract.
MAX_FILE_BYTES = int(os.environ.get("IT_TEM_MAX_FILE_MB", "10")) * 1024 * 1024
MAX_TOTAL_BYTES = int(os.environ.get("IT_TEM_MAX_TOTAL_MB", "60")) * 1024 * 1024
MAX_PIXELS = 40_000_000
IMAGE_FORMATS = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}


def get_job_store(request: Request) -> JobStore:
    return request.app.state.job_store



def _normalize_mpo_upload(filename: str, declared_mime: str, data: bytes) -> ValidatedUpload:
    """Primary frame only, with EXIF orientation and validated sRGB conversion.

    No MPO original is published. Hash-only provenance is durable in the Job
    asset record; color/EXIF metadata are removed from the emitted JPEG.
    """
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as im:
                if im.format!="MPO" or getattr(im,"n_frames",1)<2:
                    raise HTTPException(422,"MPO 파일 구조 또는 복수 사진 프레임이 올바르지 않습니다.")
                frames=im.n_frames
                im.seek(0)
                width,height=im.size
                if width<=0 or height<=0 or width*height>MAX_PIXELS:
                    raise HTTPException(422,"MPO 대표 사진의 픽셀 수가 허용 범위를 초과했습니다.")
                orientation=im.getexif().get(274,1)
                icc=im.info.get("icc_profile")
                im.load()
                upright=ImageOps.exif_transpose(im)
                if icc:
                    source=ImageCms.ImageCmsProfile(io.BytesIO(icc))
                    source_input=upright if upright.mode in ("RGB","CMYK","LAB") else upright.convert("RGB")
                    image=ImageCms.profileToProfile(source_input,source,ImageCms.createProfile("sRGB"),outputMode="RGB")
                else:
                    image=upright.convert("RGB")
                # New pixel-only JPEG: remove private EXIF/ICC/XMP/GPS.
                image=Image.frombytes("RGB",image.size,image.tobytes())
                out=io.BytesIO()
                image.save(out,format="JPEG",quality=94,subsampling=0)
                data_jpeg=out.getvalue()
                if len(data_jpeg)>MAX_FILE_BYTES:
                    raise HTTPException(413,"변환된 MPO 사진이 파일 크기 제한을 초과했습니다.")
                normalized_width,normalized_height=image.size
    except HTTPException:
        raise
    except (OSError,EOFError,SyntaxError,TypeError,ValueError,UnidentifiedImageError,
            Image.DecompressionBombWarning,Image.DecompressionBombError,ImageCms.PyCMSError):
        raise HTTPException(422,"MPO 변환에 실패했습니다. 원본을 JPEG로 변환해 다시 올려 주세요.") from None
    provenance={"normalization":"mpo-primary-srgb-jpeg-v1",
        "original_filename":filename,"original_mime":declared_mime,
        "original_sha256":hash_bytes(data),"selected_frame":0,
        "source_frame_count":frames,"source_orientation":orientation,
        "source_icc_sha256":hash_bytes(icc) if icc else None,
        "converted_sha256":hash_bytes(data_jpeg)}
    return ValidatedUpload(filename,"image/jpeg",data_jpeg,
                           normalized_width,normalized_height,hash_bytes(data_jpeg),provenance)


async def validate_upload(upload: UploadFile) -> ValidatedUpload:
    # MPO is only admitted through the explicitly named extension+strict
    # decoded MPO format. A renamed JPEG or spoofed MIME is NOT an MPO.
    filename = (upload.filename or "unnamed").replace("\\", "/").split("/")[-1][:180]
    is_mpo = filename.lower().endswith(".mpo")
    expected_type = upload.content_type or ""
    mpo_mimes = {"image/mpo","image/jpeg","application/octet-stream",""}
    if not ((is_mpo and expected_type in mpo_mimes) or
            (not is_mpo and expected_type in IMAGE_FORMATS.values())):
        raise HTTPException(status_code=422, detail="지원하지 않는 사진 형식입니다. JPG, PNG, WEBP 또는 실제 MPO 사진을 사용해 주세요.")
    data = bytearray()
    try:
        while True:
            chunk = await upload.read(min(1024 * 1024, MAX_FILE_BYTES + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > MAX_FILE_BYTES:
                raise HTTPException(status_code=413, detail="Image exceeds per-file size limit")
    finally:
        await upload.close()
    if not data:
        raise HTTPException(status_code=422, detail="Empty image is not allowed")

    if is_mpo:
        return _normalize_mpo_upload(filename, expected_type, bytes(data))
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as img:
                actual_type = IMAGE_FORMATS.get(img.format)
                width, height = img.size
                if not width or not height or width * height > MAX_PIXELS:
                    raise HTTPException(status_code=422, detail="Invalid image dimensions")
                if getattr(img, "n_frames", 1) != 1:
                    raise HTTPException(status_code=422, detail="Animated images are not accepted")
                if actual_type != upload.content_type:
                    raise HTTPException(status_code=422, detail="Image format does not match MIME type")
                img.verify()
            with Image.open(io.BytesIO(data)) as img:
                ImageOps.exif_transpose(img).load()
    except HTTPException:
        raise
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(status_code=422, detail="Image is invalid or corrupted") from None

    return ValidatedUpload(filename, upload.content_type, bytes(data), width, height, hash_bytes(data))


@router.post("", status_code=201)
async def create_job(
    product_images: Annotated[list[UploadFile], File(description="2–5 product images")],
    reference_images: Annotated[list[UploadFile] | None, File(description="0–5 reference images")] = None,
    store: JobStore = Depends(get_job_store),
):
    references = reference_images or []
    if not 2 <= len(product_images) <= 5 or len(references) > 5:
        raise HTTPException(status_code=422, detail="Expected 2–5 product and 0–5 reference images")
    validated_products = [await validate_upload(item) for item in product_images]
    validated_refs = [await validate_upload(item) for item in references]
    if sum(len(i.data) for i in validated_products + validated_refs) > MAX_TOTAL_BYTES:
        raise HTTPException(status_code=413, detail="Upload exceeds total size limit")
    return store.create_job(validated_products, validated_refs)


@router.get("/{job_id}")
def read_job(job_id: str, store: JobStore = Depends(get_job_store)):
    return store.get_job(job_id)


@router.get("/{job_id}/assets/{asset_id}")
def download_asset(job_id: str, asset_id: str, store: JobStore = Depends(get_job_store)):
    asset_path, metadata = store.get_asset(job_id, asset_id)
    ext = asset_path.suffix
    return FileResponse(
        asset_path,
        media_type=metadata["content_type"],
        filename=f"{metadata['role']}-{asset_id}{ext}",
        content_disposition_type="attachment",
    )
