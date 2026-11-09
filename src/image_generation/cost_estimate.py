"""Image cost projections and usage estimates, separate from billed amounts."""

from collections.abc import Iterable, Mapping
from decimal import Decimal

from .contracts import ImageProviderUsage
from .provider_attempts import money_units


RATE_VERSION = "openai-images-standard-uncached-2026-11-09-v1"
# The team's recorded rate table in USD per million tokens
# (text input, image input, image output).
_MODEL_RATES = {
    "gpt-image-2-2026-04-21": (5, 8, 30),
    "gpt-image-2.5-sunburst-2026-09-08": (5, 8, 30),
    "gpt-image-2.6-sunburst": (5, 8, 30),
}
_REFERENCE_MODEL = "gpt-image-2.5-sunburst-2026-09-08"
_REFERENCE_USAGE = {
    "input_tokens": 6491,
    "input_text_tokens": 683,
    "input_image_tokens": 5808,
    "output_tokens": 418,
    "total_tokens": 6909,
}
# Romand T1 exploration. The two branches share their initial result.
_DIRECT_BASELINE_STAGES = (
    "초기 생성",
    "프롬프트 보강 후 재생성",
    "기존 이미지 편집 비교",
    "팀 피드백 반영 수정",
)
# This is a separate eight-preset experiment, with two rounds over the set.
_DIMENSION_EXPERIMENT = {
    "comparison_unit": "eight_preset_set",
    "variant_count": 8,
    "initial_attempt_count": 8,
    "refinement_attempt_count": 8,
    "total_tokens": 97022,
    "estimated_cost_usd": "1.297805",
}
_ATTEMPT_STATES = frozenset({"succeeded", "failed", "submitting", "unknown"})
USDInput = str | Decimal | int | float


def _usd(micro_usd: int) -> str:
    dollars, fractional = divmod(abs(micro_usd), 1_000_000)
    return f"{'-' if micro_usd < 0 else ''}{dollars}.{fractional:06d}"


def _estimate_micro_usd(model: object, usage: object) -> int | None:
    if isinstance(usage, ImageProviderUsage):
        usage = usage.model_dump()
    if not isinstance(model, str) or model not in _MODEL_RATES or not isinstance(usage, Mapping):
        return None
    input_tokens = usage.get("input_tokens")
    text_tokens = usage.get("input_text_tokens")
    image_tokens = usage.get("input_image_tokens")
    output_tokens = usage.get("output_tokens")
    counts = (input_tokens, text_tokens, image_tokens, output_tokens)
    if any(type(count) is not int or not 0 <= count <= 2**63 - 1 for count in counts):
        return None
    if text_tokens + image_tokens != input_tokens:
        return None
    total_tokens = usage.get("total_tokens")
    if total_tokens is not None and (type(total_tokens) is not int
                                     or total_tokens != input_tokens + output_tokens):
        return None
    text_rate, image_rate, output_rate = _MODEL_RATES[model]
    return text_tokens * text_rate + image_tokens * image_rate + output_tokens * output_rate


def _reference_basis() -> tuple[int, dict]:
    micro_usd = _estimate_micro_usd(_REFERENCE_MODEL, _REFERENCE_USAGE)
    assert micro_usd is not None
    return micro_usd, {
        "currency": "USD",
        "rate_version": RATE_VERSION,
        "reference_model": _REFERENCE_MODEL,
        "reference_operation": "edit",
        "reference_aspect_ratio": "4:5",
        "reference_quality": "medium",
        "reference_usage": dict(_REFERENCE_USAGE),
        "reference_cost_usd": _usd(micro_usd),
    }


def estimate_image_generation_costs(planned_image_count: int, *,
                                    text_initial_usd: USDInput | None = None) -> dict:
    """Project first generation and a separate one-image regeneration.

    Count only planned provider images. Local copies such as A font variants
    incur no provider cost. The reference is one observed edit, not a live
    quote or an average across models, sizes or inputs.
    """
    if type(planned_image_count) is not int or planned_image_count < 0:
        raise ValueError("Planned provider image count must be a nonnegative integer.")
    reference, basis = _reference_basis()
    image_initial = planned_image_count * reference
    text_initial = None if text_initial_usd is None else money_units(text_initial_usd)
    return {
        **basis,
        "planned_image_count": planned_image_count,
        "initial_retry_count": 0,
        "image_initial_estimated_usd": _usd(image_initial),
        "image_regeneration_one_estimated_usd": _usd(reference),
        "text_initial_estimated_usd": None if text_initial is None else _usd(text_initial),
        "initial_total_estimated_usd": _usd(image_initial + (text_initial or 0)),
        "cost_scope": "image_only" if text_initial is None else "image_and_text",
        "local_composition_provider_cost_usd": "0.000000",
    }


def estimate_image_cost(model: object, usage: object) -> tuple[str | None, str | None]:
    """Price a recorded usage breakdown at the pinned, uncached rates."""
    estimate = _estimate_micro_usd(model, usage)
    return (None, None) if estimate is None else (_usd(estimate), RATE_VERSION)


def summarize_image_costs(receipts: Iterable[Mapping[str, object]], *,
                          has_candidate: bool = False) -> dict:
    """Summarize image-module attempt receipts, including explicit assumptions.

    Pass the latest receipt per attempt. Identical estimate evidence is counted
    once. A reserved-only entry has no submission, and a submitting/unknown
    receipt has uncertain delivery. Neither estimated field is an invoice.
    """
    attempts: dict[str, tuple[str, int | None]] = {}
    for receipt in receipts:
        state = receipt.get("state")
        if state in ("reserved", "RESERVED"):
            continue
        attempt_id = receipt.get("attempt_id")
        if (not isinstance(state, str) or state not in _ATTEMPT_STATES
                or not isinstance(attempt_id, str) or not attempt_id):
            raise ValueError("Invalid image attempt receipt.")
        evidence = (state, _estimate_micro_usd(receipt.get("model"), receipt.get("usage")))
        if attempts.setdefault(attempt_id, evidence) != evidence:
            raise ValueError("Conflicting image attempt receipts.")

    priced = [amount for _, amount in attempts.values() if amount is not None]
    assumed_count = not attempts and has_candidate
    attempt_count = len(attempts) + int(assumed_count)
    uncertain_count = sum(state in {"submitting", "unknown"} for state, _ in attempts.values())
    unpriced_count = attempt_count - len(priced)
    reference, basis = _reference_basis()
    return {
        **basis,
        "estimated_total_usd": _usd(sum(priced) + reference * unpriced_count) if attempt_count else None,
        "known_estimated_cost_usd": _usd(sum(priced)) if priced else None,
        "actual_cost_usd": None,
        "attempt_count": attempt_count,
        "attempt_count_is_estimated": bool(assumed_count or uncertain_count),
        "uncertain_submission_count": uncertain_count,
        "priced_attempt_count": len(priced),
        "unpriced_attempt_count": unpriced_count,
    }


def estimate_image_savings(service_attempt_count: int, *,
                           direct_attempt_count: int | None = None,
                           service_attempt_count_is_estimated: bool = False,
                           direct_text_usd: USDInput | None = None,
                           service_text_usd: USDInput | None = None) -> dict:
    """Compare completed ads at the same reference price per image attempt.

    The default direct comparison is one historical Romand scenario. For a
    different output scope, supply counts for both paths on the same basis.
    Include both paths' text costs for a finished-ad estimate. Negative
    savings means increased cost. This is a scenario, not measured savings.
    """
    default_direct = direct_attempt_count is None
    direct = len(_DIRECT_BASELINE_STAGES) if default_direct else direct_attempt_count
    if any(type(count) is not int or count < 1 for count in (direct, service_attempt_count)):
        raise ValueError("Both paths must have at least one image attempt.")
    if (direct_text_usd is None) != (service_text_usd is None):
        raise ValueError("Provide both paths' text costs to compare full ads.")
    compare_text = direct_text_usd is not None
    direct_text = money_units(direct_text_usd) if compare_text else 0
    service_text = money_units(service_text_usd) if compare_text else 0
    reference, basis = _reference_basis()
    direct_image, service_image = reference * direct, reference * service_attempt_count
    direct_total, service_total = direct_image + direct_text, service_image + service_text
    return {
        **basis,
        "direct_attempt_count": direct,
        "direct_basis": "romand_t1_one_ad" if default_direct else "caller_supplied_same_scope",
        "direct_baseline_stages": [
            {"label": label, "attempt_count": 1} for label in _DIRECT_BASELINE_STAGES
        ] if default_direct else [],
        "service_attempt_count": service_attempt_count,
        "service_attempt_count_is_estimated": service_attempt_count_is_estimated,
        "cost_scope": "image_and_text" if compare_text else "image_only",
        "direct_image_estimated_cost_usd": _usd(direct_image),
        "service_image_estimated_cost_usd": _usd(service_image),
        "direct_text_estimated_cost_usd": _usd(direct_text) if compare_text else None,
        "service_text_estimated_cost_usd": _usd(service_text) if compare_text else None,
        "direct_estimated_cost_usd": _usd(direct_total),
        "service_estimated_cost_usd": _usd(service_total),
        "estimated_savings_usd": _usd(direct_total - service_total),
        "estimated_image_savings_tokens": _REFERENCE_USAGE["total_tokens"] * (direct - service_attempt_count),
        "separate_dimension_experiment": dict(_DIMENSION_EXPERIMENT),
    }
