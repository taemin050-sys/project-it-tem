"""Provisional IT-TEM upload and job API, for local E2E mock integration only."""

from __future__ import annotations

import io
import os
import warnings
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from PIL import Image, ImageOps, UnidentifiedImageError

from .job_store import JobStore, ValidatedUpload, hash_bytes

router = APIRouter(prefix="/api/v1/jobs", tags=["Jobs — provisional"])

# Provisional prototype limits; not a team-approved product contract.
MAX_FILE_BYTES = int(os.environ.get("IT_TEM_MAX_FILE_MB", "10")) * 1024 * 1024
MAX_TOTAL_BYTES = int(os.environ.get("IT_TEM_MAX_TOTAL_MB", "60")) * 1024 * 1024
MAX_PIXELS = 40_000_000
IMAGE_FORMATS = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}


def get_job_store(request: Request) -> JobStore:
    return request.app.state.job_store


async def validate_upload(upload: UploadFile) -> ValidatedUpload:
    if upload.content_type not in IMAGE_FORMATS.values():
        raise HTTPException(status_code=422, detail="Only PNG, JPEG and WEBP images are accepted")
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

    filename = (upload.filename or "unnamed").replace("\\", "/").split("/")[-1][:180]
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
