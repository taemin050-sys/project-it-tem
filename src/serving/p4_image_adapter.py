"""Image generator handoff, WITHOUT attaching an external provider to public APIs.

The team image owner supplies an implementation of ImageGenerator. No actual
OpenAI call, upload, JobStore transition, or product-preservation claim here.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from typing import Mapping, Protocol
from uuid import uuid4

from PIL import Image, UnidentifiedImageError

from .provisional_contracts import ImageResult, VisualBrief, GenerationReceipt
from .p4_cost_guard import P4CostGuard, ProviderInvalidResponse, fingerprint

_MAX_GENERATED_BYTES = 16 * 1024 * 1024
_MAX_PIXELS = 8192 * 8192


@dataclass(frozen=True)
class GeneratedImage:
    data: bytes
    content_type: str
    mock: bool


class ImageGenerator(Protocol):
    def generate(self, brief: VisualBrief, product_images: list[bytes],
                 reference_images: list[bytes]) -> GeneratedImage: ...


@dataclass(frozen=True)
class ImageHandoff:
    result: ImageResult
    bytes_data: bytes
    receipt: GenerationReceipt


def verify_image(blob: GeneratedImage) -> tuple[int, int]:
    mapping = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}
    if blob.content_type not in mapping.values() or not isinstance(blob.data, bytes):
        raise ProviderInvalidResponse("Unsupported content")
    if not blob.data or len(blob.data) > _MAX_GENERATED_BYTES:
        raise ProviderInvalidResponse("Image size out of bounds")
    try:
        with Image.open(BytesIO(blob.data)) as picture:
            fmt = picture.format
            width, height = picture.size
            if (width <= 0 or height <= 0 or width > 8192 or height > 8192
                    or width * height > _MAX_PIXELS or mapping.get(fmt) != blob.content_type):
                raise ProviderInvalidResponse("Mismatched or unsafe image")
            picture.verify()
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
        raise ProviderInvalidResponse("Corrupted image") from None
    return width, height


def generate_handoff(*, generator: ImageGenerator, brief: VisualBrief,
                     assets: Mapping[str, bytes], guard: P4CostGuard,
                     operation_key: str, max_cost_micro_usd: int,
                     provider_name: str = "team-image-wrapper") -> ImageHandoff:
    """Call once, no retries; an uncertain charge blocks another image attempt.

    Product/photo identity, approved copy revision, and safe zone come from an
    already-validated VisualBrief. Caller MUST verify copy approval in JobStore.
    """
    products = [assets[x] for x in brief.product_asset_ids]  # fails before reservation
    refs = [assets[x] for x in brief.reference_asset_ids]
    if any(not isinstance(p, bytes) or not p for p in products + refs):
        raise ValueError("Missing asset bytes")
    if len(provider_name) > 80:
        raise ValueError("Invalid provider label")

    def run() -> tuple[GeneratedImage, int, int]:
        result = generator.generate(brief, products, refs)
        if not isinstance(result, GeneratedImage):
            raise ProviderInvalidResponse("Wrapper did not return GeneratedImage")
        width, height = verify_image(result)
        if bool(max_cost_micro_usd) == result.mock:
            raise ProviderInvalidResponse("Mock/billable mode mismatch")
        return result, width, height

    output = guard.execute(
        job_id=brief.job_id, phase="image", operation_key=operation_key,
        request_hash=fingerprint({"brief": brief.model_dump(mode="json"),
                                  "asset_digests": {x: sha256(assets[x]).hexdigest()
                                                    for x in brief.product_asset_ids + brief.reference_asset_ids}}),
        max_cost_micro_usd=max_cost_micro_usd, call=run,
    )
    generated, width, height = output.value
    result = ImageResult(candidate_asset_id=uuid4().hex,
                         content_type=generated.content_type, width=width, height=height,
                         sha256=sha256(generated.data).hexdigest(), mock=generated.mock,
                         preservation_review="pending")
    receipt = GenerationReceipt(provider=provider_name, adapter_version="preflight-s2",
                                request_id=operation_key, attempt_id=output.attempt_id,
                                billing_state=output.billing_state)
    return ImageHandoff(result=result, bytes_data=generated.data, receipt=receipt)
