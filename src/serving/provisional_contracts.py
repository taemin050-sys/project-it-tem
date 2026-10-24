"""Provisional cross-team *internal* DTOs for the 2026-10-26 review.

NOT wire-authoritative. Existing P1-P4A endpoints and their responses are
unchanged. Do not call these schema names v0.1-approved before PM sign-off.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Hex32 = str  # Constrained using explicit regex on each ID field.
HEX_ID = r"^[a-f0-9]{32}$"
HEX_SHA = r"^[a-f0-9]{64}$"


class ContractDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SafeZone(ContractDTO):
    coordinate_system: Literal["final_canvas_normalized"] = "final_canvas_normalized"
    left: float = Field(ge=0, le=1)
    top: float = Field(ge=0, le=1)
    right: float = Field(ge=0, le=1)
    bottom: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def ordered_bounds(self) -> "SafeZone":
        if self.left >= self.right or self.top >= self.bottom:
            raise ValueError("safe zone bounds must have positive area")
        return self


class Evidence(ContractDTO):
    source_id: str = Field(min_length=1, max_length=80)
    source_type: Literal["web", "paper", "regulator", "browser"]
    title: str = Field(min_length=1, max_length=300)
    url_or_doi: str = Field(min_length=1, max_length=1000)
    retrieved_at: datetime
    claim_ids: list[str] = Field(default_factory=list, max_length=30)
    verification_status: Literal["unverified", "corroborated", "rejected"]


class ProductFacts(ContractDTO):
    brand_name: str = Field(min_length=1, max_length=80)
    product_name: str = Field(min_length=1, max_length=100)
    claims: list[str] = Field(default_factory=list, max_length=12)
    attributes: list[str] = Field(default_factory=list, max_length=20)
    claim_source: Literal["user_supplied_unverified", "verified_document"]

    @field_validator("claims", "attributes")
    @classmethod
    def no_empty_or_controls(cls, value: list[str]) -> list[str]:
        if any(not item.strip() or len(item) > 300 or any(ord(c) < 32 for c in item) for item in value):
            raise ValueError("claims and attributes must be short nonblank text")
        return value


class PlanResult(ContractDTO):
    mock: bool
    brand_name: str = Field(min_length=1, max_length=80)
    product_name: str = Field(min_length=1, max_length=100)
    audience: str = Field(min_length=1, max_length=600)
    direction: str = Field(min_length=1, max_length=600)
    research_performed: bool = False
    evidence: list[Evidence] = Field(default_factory=list, max_length=30)
    risk_flags: list[str] = Field(default_factory=list, max_length=15)
    disclaimer: str = Field(min_length=1, max_length=400)

    @model_validator(mode="after")
    def research_provenance(self) -> "PlanResult":
        if self.research_performed and not self.evidence:
            raise ValueError("Research may not be marked performed without provenance")
        if self.mock and self.research_performed:
            raise ValueError("Mock plan may not claim live research")
        return self


class CopyResult(ContractDTO):
    mock: bool
    text: str = Field(min_length=1, max_length=220)
    risk_flags: list[str] = Field(default_factory=list, max_length=15)
    compliance_checked: bool = False
    disclaimer: str = Field(min_length=1, max_length=400)


class VisualBrief(ContractDTO):
    job_id: str = Field(pattern=HEX_ID)
    copy_revision: int = Field(ge=1)
    copy_text: str = Field(min_length=1, max_length=220)
    prompt_en: str = Field(min_length=1, max_length=2500)
    product_asset_ids: list[str] = Field(min_length=1, max_length=5)
    reference_asset_ids: list[str] = Field(default_factory=list, max_length=5)
    safe_zone: SafeZone
    negative_constraints: list[str] = Field(default_factory=list, max_length=15)

    @model_validator(mode="after")
    def validate_asset_ids(self) -> "VisualBrief":
        import re
        ids = self.product_asset_ids + self.reference_asset_ids
        if any(not re.fullmatch(HEX_ID, value) for value in ids) or len(ids) != len(set(ids)):
            raise ValueError("Asset IDs must be unique 32-char hexadecimal IDs")
        return self


class ImageResult(ContractDTO):
    candidate_asset_id: str = Field(pattern=HEX_ID)
    content_type: Literal["image/png", "image/jpeg", "image/webp"]
    width: int = Field(gt=0, le=8192)
    height: int = Field(gt=0, le=8192)
    sha256: str = Field(pattern=HEX_SHA)
    mock: bool
    preservation_review: Literal["pending", "pass", "fail"]


class GenerationReceipt(ContractDTO):
    provider: str = Field(min_length=1, max_length=80)
    model: str | None = None
    adapter_version: str = Field(min_length=1, max_length=40)
    request_id: str = Field(min_length=1, max_length=128)
    attempt_id: str = Field(min_length=1, max_length=128)
    billing_state: Literal["not_called", "unknown", "charged", "no_charge"]
    elapsed_ms: int | None = Field(default=None, ge=0)
    error_code: str | None = None


PROVISIONAL_MODELS: dict[str, type[ContractDTO]] = {
    "product_facts": ProductFacts,
    "evidence": Evidence,
    "plan_result": PlanResult,
    "copy_result": CopyResult,
    "visual_brief": VisualBrief,
    "image_result": ImageResult,
    "generation_receipt": GenerationReceipt,
}
