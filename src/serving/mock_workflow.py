"""Local-only staged E2E mock. No search, external AI, billing or real compliance review.

Provisional endpoint names: DO NOT use as an approved frontend contract until
PM and affected team members sign off on docs/interface_spec.md.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from PIL import Image, ImageDraw, ImageFont, ImageOps
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .job_api import get_job_store
from .job_store import JobStore, get_mock_artifact, transition_job

router = APIRouter(prefix="/api/v1/jobs", tags=["Mock workflow — provisional"])


class MockProductRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    brand_name: str = Field(min_length=1, max_length=80)
    product_name: str = Field(min_length=1, max_length=100)

    @field_validator("brand_name", "product_name")
    @classmethod
    def non_blank(cls, value: str) -> str:
        value = value.strip()
        if not value or any(ord(char) < 32 for char in value):
            raise ValueError("Must be nonblank, without control characters")
        return value


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approved: bool


def _as_json_bytes(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _korean_font(size: int) -> ImageFont.FreeTypeFont:
    override = os.getenv("IT_TEM_KOREAN_FONT")
    candidates = (
        [Path(override)] if override else []
    ) + [
        Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
    ]
    for path in candidates:
        if path.is_file():
            try:
                return ImageFont.truetype(str(path), size=size)
            except OSError:
                continue
    raise HTTPException(
        status_code=503,
        detail="Korean font missing. Install fonts-nanum or set IT_TEM_KOREAN_FONT",
    )


def _fit_line(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> str:
    if draw.textlength(text, font=font) <= max_width:
        return text
    suffix = "…"
    while text and draw.textlength(text + suffix, font=font) > max_width:
        text = text[:-1]
    return (text + suffix) if text else suffix


def _placeholder_image(store: JobStore, job: dict) -> bytes:
    first_product = next(asset for asset in job["assets"] if asset["role"] == "product")
    original, _ = store.get_asset(job["job_id"], first_product["asset_id"])
    with Image.open(original) as file:
        photo = ImageOps.exif_transpose(file).convert("RGB")
    canvas = Image.new("RGB", (1080, 1350), (242, 239, 234))
    photo.thumbnail((990, 1080), Image.Resampling.LANCZOS)
    canvas.paste(photo, ((1080 - photo.width) // 2, (1130 - photo.height) // 2))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 1245, 1080, 1350), fill=(29, 31, 35))
    draw.text((55, 1280), "IT-TEM MOCK IMAGE - NOT AI GENERATED", fill="white")
    buffer = io.BytesIO()
    canvas.save(buffer, format="PNG")
    return buffer.getvalue()


def _final_mock_image(store: JobStore, job: dict) -> bytes:
    path, _ = get_mock_artifact(store, job["job_id"], "image")
    with Image.open(path) as file:
        canvas = file.convert("RGB")
    font = _korean_font(56)
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 1045, 1080, 1255), fill=(255, 255, 255))
    copy = job["copy_candidate"]["text"]
    # Two lines, bounded by pixel width. The mock is NOT an ad compliance approval.
    first = _fit_line(draw, copy[:22], font, 980)
    second = _fit_line(draw, copy[22:], font, 980) if len(copy) > 22 else ""
    draw.text((50, 1080), first, fill=(20, 20, 20), font=font)
    if second:
        draw.text((50, 1150), second, fill=(20, 20, 20), font=font)
    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()


@router.post("/{job_id}/mock/plan")
def mock_plan(job_id: str, body: MockProductRequest, store: JobStore = Depends(get_job_store)):
    plan = {
        "mock": True,
        "research_performed": False,
        "brand_name": body.brand_name,
        "product_name": body.product_name,
        "audience": "화장품 관심 고객(검증되지 않은 예시 세그먼트)",
        "direction": "제품을 일상적인 루틴의 일부로 소개",
        "disclaimer": "실제 시장·경쟁사 조사 및 화장품 광고 적법성 검토 미실시",
    }
    return transition_job(
        store, job_id, expected_status="INPUTS_VALIDATED", next_status="PLAN_READY",
        updates={"plan": plan}, artifact_kind="plan", artifact_bytes=_as_json_bytes(plan),
    )


@router.post("/{job_id}/mock/copy")
def mock_copy(job_id: str, store: JobStore = Depends(get_job_store)):
    job = store.get_job(job_id)
    if job["status"] != "PLAN_READY":
        raise HTTPException(status_code=409, detail="Plan must be ready before copy")
    plan = job["plan"]
    copy = {
        "mock": True,
        "text": f"{plan['brand_name']} {plan['product_name']}, 일상의 루틴을 위한 한 가지 선택",
        "compliance_checked": False,
        "disclaimer": "AI 광고 문구 초안 예시. 실제 표시·광고 적법성 및 상품 사실관계 검증 필요",
    }
    return transition_job(
        store, job_id, expected_status="PLAN_READY", next_status="COPY_REVIEW_REQUIRED",
        updates={"copy_candidate": copy}, artifact_kind="copy", artifact_bytes=_as_json_bytes(copy),
    )


@router.post("/{job_id}/approvals/copy")
def approve_copy(job_id: str, body: ReviewRequest, request: Request,
                 store: JobStore = Depends(get_job_store)):
    # Test-only opt-in: actual POST approvals/copy now calls the durable
    # server-owned Fake review gate. No client-supplied report/hash/record.
    # Approved:false remains the existing explicit rejection transition.
    gate = getattr(request.app.state, "b1_fake_gate", None)
    if gate is not None and body.approved:
        return gate.approve(job_id)
    return transition_job(
        store, job_id, expected_status="COPY_REVIEW_REQUIRED",
        next_status="COPY_APPROVED" if body.approved else "COPY_REJECTED",
        updates={"copy_approved": body.approved},
    )


@router.post("/{job_id}/mock/image")
def mock_image(job_id: str, store: JobStore = Depends(get_job_store)):
    job = store.get_job(job_id)
    if job["status"] != "COPY_APPROVED":
        raise HTTPException(status_code=409, detail="Copy must be approved before image")
    image_bytes = _placeholder_image(store, job)
    return transition_job(
        store, job_id, expected_status="COPY_APPROVED", next_status="IMAGE_REVIEW_REQUIRED",
        updates={"image_candidate": {"mock": True, "source": "uploaded_product_photo", "size": [1080, 1350]}},
        artifact_kind="image", artifact_bytes=image_bytes,
    )


@router.post("/{job_id}/approvals/image")
def approve_image(job_id: str, body: ReviewRequest, store: JobStore = Depends(get_job_store)):
    return transition_job(
        store, job_id, expected_status="IMAGE_REVIEW_REQUIRED",
        next_status="IMAGE_APPROVED" if body.approved else "IMAGE_REJECTED",
        updates={"image_approved": body.approved},
    )


@router.post("/{job_id}/mock/compose")
def mock_compose(job_id: str, store: JobStore = Depends(get_job_store)):
    job = store.get_job(job_id)
    if job["status"] != "IMAGE_APPROVED":
        raise HTTPException(status_code=409, detail="Image must be approved before composition")
    png_data = _final_mock_image(store, job)
    caption = f"{job['copy_candidate']['text']}\n\n#화장품 #일상루틴\n"
    return transition_job(
        store, job_id, expected_status="IMAGE_APPROVED", next_status="COMPLETED",
        updates={"final_output": {"mock": True, "width": 1080, "height": 1350, "format": "PNG"}},
        artifact_kind="final", artifact_bytes=png_data,
        additional_artifacts={"caption": caption.encode("utf-8")},
    )


@router.get("/{job_id}/artifacts/{kind}")
def download_mock_artifact(job_id: str, kind: str, store: JobStore = Depends(get_job_store)):
    path, content_type = get_mock_artifact(store, job_id, kind)
    return FileResponse(path, media_type=content_type, filename=path.name, content_disposition_type="attachment")
