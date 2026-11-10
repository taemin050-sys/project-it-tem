"""Image cost projections and usage estimates, separate from billed amounts."""

from collections.abc import Iterable, Mapping
from decimal import Decimal

from .contracts import ImageProviderUsage
from .cost_history import (
    AD_PRODUCTION_HISTORY_STAGES,
    ImageTrialStage,
    PRESET_DEVELOPMENT_STAGES,
    TRIAL_INVENTORY_VERSION,
    UNMETERED_TOOL_STAGES,
)
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


def summarize_preset_development(stages: Iterable[ImageTrialStage] | None = None) -> dict:
    """Price the development inventory once, apart from per-ad savings.

    Normalized totals price every attempt at the same reference. The separate
    usage-plus-fallback total keeps known usage estimates and fills only missing
    costs. These are alternative views, not amounts to add together. An empty
    custom inventory explicitly declares no development trials in that scope.
    """
    reference, basis = _reference_basis()
    unique: dict[str, ImageTrialStage] = {}
    rows = []
    observed = assumed = priced_count = known = 0
    for stage in PRESET_DEVELOPMENT_STAGES if stages is None else stages:
        if not isinstance(stage, ImageTrialStage):
            raise ValueError("Expected ImageTrialStage records.")
        if any(not isinstance(value, str) or not value.strip()
               for value in (stage.stage_id, stage.label)):
            raise ValueError("Stage id and label are required.")
        for values in (stage.source_refs, stage.dimensions):
            if not isinstance(values, tuple) or any(
                not isinstance(value, str) or not value.strip() for value in values
            ):
                raise ValueError("Sources and dimensions must be tuples of nonempty strings.")
        if not stage.source_refs:
            raise ValueError("Stage sources are required.")
        counts = (stage.observed_attempt_count, stage.assumed_attempt_count,
                  stage.usage_priced_attempt_count)
        if any(type(count) is not int or count < 0 for count in counts):
            raise ValueError("Stage counts must be nonnegative integers.")
        if stage.usage_priced_attempt_count > stage.observed_attempt_count:
            raise ValueError("Usage-priced count cannot exceed observed attempts.")
        if (stage.assumption is not None and (
                not isinstance(stage.assumption, str) or not stage.assumption.strip())):
            raise ValueError("An assumption must be nonempty text.")
        if stage.assumed_attempt_count and stage.assumption is None:
            raise ValueError("Assumed attempts require an explicit assumption.")
        if (stage.usage_based_estimated_usd is not None) != bool(stage.usage_priced_attempt_count):
            raise ValueError("Usage cost and usage-priced count must be supplied together.")
        usage_cost = (money_units(stage.usage_based_estimated_usd)
                      if stage.usage_based_estimated_usd is not None else 0)
        if stage.stage_id in unique:
            if unique[stage.stage_id] != stage:
                raise ValueError("Conflicting trial stage records.")
            continue
        unique[stage.stage_id] = stage
        count = stage.observed_attempt_count + stage.assumed_attempt_count
        fallback = (count - stage.usage_priced_attempt_count) * reference
        observed += stage.observed_attempt_count
        assumed += stage.assumed_attempt_count
        priced_count += stage.usage_priced_attempt_count
        known += usage_cost
        rows.append({
            "stage_id": stage.stage_id, "label": stage.label,
            "scope": "preset_development",
            "observed_attempt_count": stage.observed_attempt_count,
            "assumed_attempt_count": stage.assumed_attempt_count,
            "attempt_count": count,
            "count_is_estimated": bool(stage.assumed_attempt_count),
            "usage_priced_attempt_count": stage.usage_priced_attempt_count,
            "unpriced_attempt_count": count - stage.usage_priced_attempt_count,
            "usage_based_known_estimate_usd": _usd(usage_cost) if stage.usage_priced_attempt_count else None,
            "normalized_estimated_cost_usd": _usd(count * reference),
            "fallback_estimated_cost_usd": _usd(fallback),
            "usage_plus_fallback_estimated_cost_usd": _usd(usage_cost + fallback),
            "dimensions": list(stage.dimensions), "source_refs": list(stage.source_refs),
            "assumption": stage.assumption,
        })
    total = observed + assumed
    fallback = (total - priced_count) * reference
    return {
        **basis,
        "inventory_version": TRIAL_INVENTORY_VERSION if stages is None else "caller_supplied",
        "comparison_unit": "reusable_preset_development",
        "coverage": "listed_batches_only_not_account_lifetime",
        "cost_scope": "image_api_only",
        "included_in_per_ad_savings": False,
        "stage_count": len(rows), "stages": rows,
        "observed_attempt_count": observed, "assumed_attempt_count": assumed,
        "attempt_count": total, "attempt_count_is_estimated": bool(assumed),
        "usage_priced_attempt_count": priced_count,
        "unpriced_attempt_count": total - priced_count,
        "normalized_estimated_cost_usd": _usd(total * reference),
        "usage_based_known_estimate_usd": _usd(known) if priced_count else None,
        "fallback_estimated_cost_usd": _usd(fallback),
        "usage_plus_fallback_estimated_cost_usd": _usd(known + fallback) if total else None,
        "actual_cost_usd": None,
        "unrecorded_http_retries": None,
        "amortized_per_ad_usd": None,
        "excluded_costs": ["human_labor", "text_api", "local_compute", "unrecorded_http_retries"],
    }


def estimate_image_savings(service_attempt_count: int, *,
                           direct_attempt_count: int | None = None,
                           service_attempt_count_is_estimated: bool = False,
                           direct_text_usd: USDInput | None = None,
                           service_text_usd: USDInput | None = None,
                           preset_stages: Iterable[ImageTrialStage] | None = None) -> dict:
    """Compare completed ads at the same reference price per image attempt.

    The default direct comparison is one historical Romand scenario. For a
    different output scope, supply counts for both paths on the same basis.
    Include both paths' text costs for a finished-ad estimate. Negative
    savings means increased cost. This is a scenario, not measured savings.
    Preset development is a separate inventory, never added to per-ad savings.
    Its historical trials can underpin this scenario; do not add the two views
    into a cumulative account expense.
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
    # This recorded example is production history, not part of the direct/service
    # scenario cost and not reusable preset R&D. Keep all three views distinct.
    recorded_example = summarize_preset_development(AD_PRODUCTION_HISTORY_STAGES)
    recorded_example["comparison_unit"] = "one_historical_ad_two_attempts"
    recorded_example["inventory_version"] = TRIAL_INVENTORY_VERSION
    for row in recorded_example["stages"]:
        row["scope"] = "ad_production_history"
    # Built-in image tools were not charged via the team's API. Only show the
    # hypothetical equivalent at the common rate, never fallback API expenditure.
    tool_trials = summarize_preset_development(UNMETERED_TOOL_STAGES)
    unmetered_tools = {
        "comparison_unit": "unmetered_image_tool_development",
        "inventory_version": TRIAL_INVENTORY_VERSION,
        "assumed_api_equivalent_attempt_count": tool_trials["attempt_count"],
        "normalized_equivalent_cost_usd": tool_trials["normalized_estimated_cost_usd"],
        "team_image_api_attempt_count": 0,
        "team_image_api_cost_usd": "0.000000",
        "actual_tool_cost_usd": None,
        "included_in_per_ad_savings": False,
        "stages": [{
            "stage_id": row["stage_id"], "label": row["label"],
            "assumed_api_equivalent_attempt_count": row["attempt_count"],
            "normalized_equivalent_cost_usd": row["normalized_estimated_cost_usd"],
            "source_refs": row["source_refs"], "assumption": row["assumption"],
        } for row in tool_trials["stages"]],
    }
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
        "ad_production": {
            "comparison_unit": "one_ad" if default_direct else "caller_supplied_same_output_scope",
            "cost_basis": "normalized_reference_scenario_not_billed_savings",
            "direct_attempt_count": direct,
            "service_attempt_count": service_attempt_count,
            "direct_estimated_cost_usd": _usd(direct_total),
            "service_estimated_cost_usd": _usd(service_total),
            "estimated_savings_usd": _usd(direct_total - service_total),
            "cost_scope": "image_and_text" if compare_text else "image_only",
            "includes_preset_development": False,
            "actual_savings_usd": None,
        },
        "preset_development": summarize_preset_development(preset_stages),
        "historical_ad_production": recorded_example,
        "unmetered_tool_development": unmetered_tools,
        # Compatibility detail only; these same runs appear once in the inventory.
        "separate_dimension_experiment": dict(_DIMENSION_EXPERIMENT),
    }
