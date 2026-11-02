"""S4-0 offline-only Text Owner v0.8 -> Serving/Image boundary.

The official schema module is injected. Import never loads Text config/OpenAI.
No HTTP routes, compliance attestations, user approval or live calls.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Mapping

from pydantic import BaseModel, ValidationError


class TextBoundaryError(ValueError):
    """Safe internal error code without provider messages or user content."""
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _mapping(value: Mapping[str, Any] | BaseModel, code: str) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        # Image Owner may exclude error on model_dump; inspect live attribute.
        data = value.model_dump(mode="json")
        if hasattr(value, "error"):
            data["error"] = getattr(value, "error")
        return data
    if type(value) is not dict:
        raise TextBoundaryError(code)
    return deepcopy(value)


def _owner_validate(payload: dict, model: type[BaseModel] | None, code: str) -> dict:
    if model is None:
        return payload  # pure boundary unit probes; official integration injects models
    try:
        return model.model_validate(payload, strict=True).model_dump(mode="json")
    except (ValidationError, ValueError, TypeError):
        raise TextBoundaryError(code) from None


@dataclass(frozen=True)
class VerifiedAnalysis:
    raw: dict[str, Any]
    image_owner_input: dict[str, Any]


def verify_analysis(
    incoming: Mapping[str, Any] | BaseModel,
    *, model: type[BaseModel] | None = None,
) -> VerifiedAnalysis:
    """Reject before Image DTO serialization, asset writes, or provider calls."""
    raw = _mapping(incoming, "VLM_INVALID_RESULT")
    if set(raw) - {"analysis", "analysis_succeeded", "error"}:
        raise TextBoundaryError("VLM_INVALID_RESULT")
    success = raw.get("analysis_succeeded")
    error = raw.get("error")
    analysis = raw.get("analysis")
    if type(success) is not bool or (error is not None and type(error) is not str):
        raise TextBoundaryError("VLM_INVALID_RESULT")
    if success is not True or error is not None:
        raise TextBoundaryError("VLM_FAILED")
    if type(analysis) is not dict or type(analysis.get("is_cosmetic")) is not bool:
        raise TextBoundaryError("VLM_INVALID_RESULT")
    if analysis["is_cosmetic"] is not True:
        raise TextBoundaryError("VLM_NOT_COSMETIC")
    parsed = _owner_validate(raw, model, "VLM_INVALID_RESULT")
    if set(parsed) != {"analysis", "analysis_succeeded", "error"}:
        raise TextBoundaryError("VLM_INVALID_RESULT")
    if parsed["analysis_succeeded"] is not True or parsed["error"] is not None:
        raise TextBoundaryError("VLM_FAILED")
    return VerifiedAnalysis(
        raw=deepcopy(parsed),
        image_owner_input={
            "analysis": deepcopy(parsed["analysis"]),
            "analysis_succeeded": True,
            "error": None,
        },
    )


@dataclass(frozen=True)
class ResearchSnapshot:
    original: dict[str, Any]
    display: dict[str, Any]
    outcome: str


def verify_research(
    incoming: Mapping[str, Any] | BaseModel,
    *, model: type[BaseModel] | None = None,
) -> ResearchSnapshot:
    """Preserve owner raw result and separately downgrade unverified UI claims."""
    raw = _mapping(incoming, "RESEARCH_INVALID_RESULT")
    if set(raw) - {"research", "citations", "research_performed", "error"}:
        raise TextBoundaryError("RESEARCH_INVALID_RESULT")
    if type(raw.get("research_performed")) is not bool:
        raise TextBoundaryError("RESEARCH_INVALID_RESULT")
    if raw.get("error") is not None and type(raw["error"]) is not str:
        raise TextBoundaryError("RESEARCH_INVALID_RESULT")
    parsed = _owner_validate(raw, model, "RESEARCH_INVALID_RESULT")
    if not isinstance(parsed.get("research"), dict) or type(parsed.get("citations")) is not list:
        raise TextBoundaryError("RESEARCH_INVALID_RESULT")
    original = deepcopy(parsed)
    display = deepcopy(parsed)
    failure = display.get("error") is not None
    performed = display["research_performed"]
    cited = bool(display["citations"])
    if failure:
        outcome = "research_failed_fallback"
    elif not performed:
        outcome = "search_not_performed"
    elif not cited:
        outcome = "search_completed_uncited"
    else:
        outcome = "search_cited"
    # The v0.8 schema offers a global citation list, NOT item-to-URL bindings.
    # Even one real citation cannot substantiate every individual search claim.
    # Retain the original research/citations internally, but show neither
    # unbound citations nor an unsupported per-item "검색 결과" claim.
    display["citations"] = []
    if failure or not performed:
        display["research_performed"] = False
    for key in ("market_insights", "similar_products", "display_summary"):
        for item in display["research"].get(key, []):
            if item.get("source") == "검색 결과":
                item["source"] = "AI 추론"
    # Provider error details belong to the internal original only.
    # No exceptions, API URLs, credentials, or provider traces in UI payload.
    if failure:
        display["error"] = "RESEARCH_UNAVAILABLE"
    return ResearchSnapshot(original=original, display=display, outcome=outcome)


@dataclass(frozen=True)
class CopySnapshot:
    output: dict[str, Any]
    sha256: str


def verify_copy(
    incoming: Mapping[str, Any] | BaseModel,
    *, model: type[BaseModel] | None = None,
) -> CopySnapshot:
    raw = _mapping(incoming, "COPY_INVALID_RESULT")
    if set(raw) != {"plan", "ad_copy", "caption", "hashtags"}:
        raise TextBoundaryError("COPY_INVALID_RESULT")
    parsed = _owner_validate(raw, model, "COPY_INVALID_RESULT")
    if set(parsed) != {"plan", "ad_copy", "caption", "hashtags"}:
        raise TextBoundaryError("COPY_INVALID_RESULT")
    ad = parsed["ad_copy"]
    if (type(parsed["plan"]) is not dict or type(ad) is not dict
        or set(ad) != {"headline", "subline", "cta"}
        or any(type(v) is not str for v in ad.values())
        or type(parsed["caption"]) is not str
        or type(parsed["hashtags"]) is not list
        or any(type(v) is not str for v in parsed["hashtags"])):
        raise TextBoundaryError("COPY_INVALID_RESULT")
    return CopySnapshot(output=deepcopy(parsed),
                        sha256=_digest(parsed, "COPY_INVALID_RESULT"))


def _digest(value: dict[str, Any], code: str) -> str:
    """The same canonical full-value digest used by the existing Image Owner."""
    try:
        canonical = json.dumps(value, sort_keys=True, ensure_ascii=False,
                               separators=(",", ":"), allow_nan=False)
        return sha256(canonical.encode("utf-8")).hexdigest()
    except (TypeError, ValueError, UnicodeError, OverflowError, RecursionError):
        raise TextBoundaryError(code) from None


def verify_prompt(
    incoming: Mapping[str, Any] | BaseModel,
    copy: CopySnapshot,
    *, model: type[BaseModel] | None = None,
) -> dict[str, Any]:
    raw = _mapping(incoming, "PROMPT_INVALID_RESULT")
    if set(raw) != {"concept", "prompt", "mood"}:
        raise TextBoundaryError("PROMPT_INVALID_RESULT")
    parsed = _owner_validate(raw, model, "PROMPT_INVALID_RESULT")
    if (type(parsed["concept"]) is not str or type(parsed["prompt"]) is not str
        or not parsed["prompt"].strip() or type(parsed["mood"]) is not list
        or any(type(v) is not str for v in parsed["mood"])):
        raise TextBoundaryError("PROMPT_INVALID_RESULT")
    if (parsed["concept"] != copy.output["plan"].get("concept")
        or parsed["mood"] != copy.output["plan"].get("mood")):
        raise TextBoundaryError("PROMPT_PLAN_MISMATCH")
    return deepcopy(parsed)


@dataclass(frozen=True)
class OfflineTextStage:
    copy_output: dict[str, Any]
    copy_revision: str | int
    product_analysis: dict[str, Any]
    image_prompt: dict[str, Any]
    copy_hash: str
    research: ResearchSnapshot
    _image_prompt_hash: str
    _analysis_hash: str

    def fixture_args(self) -> dict[str, Any]:
        """Recheck mutable snapshots at the S4->S5 boundary (NOT user approval)."""
        cp = verify_copy(self.copy_output)
        if cp.sha256 != self.copy_hash:
            raise TextBoundaryError("STAGED_COPY_CHANGED")
        ip = verify_prompt(self.image_prompt, cp)
        if _digest(ip, "STAGED_PROMPT_CHANGED") != self._image_prompt_hash:
            raise TextBoundaryError("STAGED_PROMPT_CHANGED")
        vlm = verify_analysis(self.product_analysis)
        if _digest(vlm.image_owner_input, "STAGED_ANALYSIS_CHANGED") != self._analysis_hash:
            raise TextBoundaryError("STAGED_ANALYSIS_CHANGED")
        if not ((type(self.copy_revision) is str and bool(self.copy_revision.strip()))
                or (type(self.copy_revision) is int and self.copy_revision > 0)):
            raise TextBoundaryError("COPY_INVALID_REVISION")
        return {
            "copy_output": deepcopy(cp.output),
            "copy_revision": self.copy_revision,
            "product_analysis": deepcopy(vlm.image_owner_input),
            "image_prompt": deepcopy(ip),
        }


def prepare_offline_stage(
    analysis: Mapping[str, Any] | BaseModel,
    research: Mapping[str, Any] | BaseModel,
    copy: Mapping[str, Any] | BaseModel,
    prompt: Mapping[str, Any] | BaseModel,
    *,
    owner_schemas: Any,
    copy_revision: str | int,
) -> OfflineTextStage:
    """Explicit official models; never import OpenAI config or client."""
    if not ((type(copy_revision) is str and bool(copy_revision.strip()))
            or (type(copy_revision) is int and copy_revision > 0)):
        raise TextBoundaryError("COPY_INVALID_REVISION")
    vlm = verify_analysis(analysis, model=owner_schemas.ProductAnalysisResult)
    rs = verify_research(research, model=owner_schemas.ResearchResult)
    cp = verify_copy(copy, model=owner_schemas.AdCopyOutput)
    ip = verify_prompt(prompt, cp, model=owner_schemas.ImagePromptOutput)
    return OfflineTextStage(
        copy_output=cp.output, copy_revision=copy_revision,
        product_analysis=vlm.image_owner_input, image_prompt=ip,
        copy_hash=cp.sha256, research=rs,
        _image_prompt_hash=_digest(ip, "PROMPT_INVALID_RESULT"),
        _analysis_hash=_digest(vlm.image_owner_input, "VLM_INVALID_RESULT"),
    )
