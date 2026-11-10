from decimal import Decimal

import pytest

from src.image_generation.contracts import ImageProviderUsage
from src.image_generation.cost_estimate import (
    RATE_VERSION,
    estimate_image_cost,
    estimate_image_generation_costs,
    estimate_image_savings,
    summarize_image_costs,
)


MODEL = "gpt-image-2.5-sunburst-2026-09-08"
USAGE = {
    "input_tokens": 6491,
    "input_text_tokens": 683,
    "input_image_tokens": 5808,
    "output_tokens": 418,
    "total_tokens": 6909,
}


def test_initial_estimate_keeps_regeneration_and_local_composition_separate():
    first = estimate_image_generation_costs(1, text_initial_usd="0.024")
    assert first["reference_model"] == MODEL
    assert first["reference_aspect_ratio"] == "4:5"
    assert first["reference_quality"] == "medium"
    assert first["reference_usage"] == USAGE
    assert first["initial_retry_count"] == 0
    assert first["image_initial_estimated_usd"] == "0.062419"
    assert first["image_regeneration_one_estimated_usd"] == "0.062419"
    assert first["initial_total_estimated_usd"] == "0.086419"
    assert first["local_composition_provider_cost_usd"] == "0.000000"
    assert estimate_image_generation_costs(3)["initial_total_estimated_usd"] == "0.187257"
    assert estimate_image_generation_costs(0)["initial_total_estimated_usd"] == "0.000000"


@pytest.mark.parametrize("planned", [-1, True, 1.5, "1"])
def test_initial_estimate_rejects_invalid_planned_image_count(planned):
    with pytest.raises(ValueError, match="nonnegative integer"):
        estimate_image_generation_costs(planned)


def test_recorded_usage_can_be_priced_without_any_generation_projection():
    assert estimate_image_cost(MODEL, ImageProviderUsage(**USAGE)) == ("0.062419", RATE_VERSION)
    zero = dict.fromkeys(USAGE, 0)
    assert estimate_image_cost(MODEL, zero) == ("0.000000", RATE_VERSION)
    assert estimate_image_cost("unsupported", USAGE) == (None, None)


@pytest.mark.parametrize("change", [
    {"input_image_tokens": None},
    {"input_text_tokens": True},
    {"input_tokens": 0},
    {"total_tokens": 0},
    {"output_tokens": -1},
])
def test_inconsistent_or_incomplete_usage_has_no_recorded_cost(change):
    assert estimate_image_cost(MODEL, USAGE | change) == (None, None)


def test_receipt_summary_separates_observed_usage_and_unknown_submissions():
    first = {"attempt_id": "first", "state": "succeeded", "model": MODEL, "usage": USAGE}
    unpriced = {"attempt_id": "second", "state": "unknown", "model": MODEL, "usage": None}
    summary = summarize_image_costs([first, first, unpriced, {"state": "reserved"}])
    assert summary["priced_attempt_count"] == 1
    assert summary["unpriced_attempt_count"] == 1
    assert summary["uncertain_submission_count"] == 1
    assert summary["attempt_count"] == 2 and summary["attempt_count_is_estimated"]
    assert summary["known_estimated_cost_usd"] == "0.062419"
    assert summary["estimated_total_usd"] == "0.124838"
    assert summary["actual_cost_usd"] is None
    with pytest.raises(ValueError, match="Conflicting"):
        summarize_image_costs([first, first | {"usage": None}])


def test_missing_history_does_not_turn_into_observed_cost():
    assert summarize_image_costs([])["estimated_total_usd"] is None
    older_candidate = summarize_image_costs([], has_candidate=True)
    assert older_candidate["known_estimated_cost_usd"] is None
    assert older_candidate["estimated_total_usd"] == "0.062419"
    assert older_candidate["attempt_count"] == 1 and older_candidate["attempt_count_is_estimated"]


def test_savings_uses_a_shared_reference_and_keeps_the_eight_preset_trial_separate():
    estimate = estimate_image_savings(1)
    assert estimate["direct_basis"] == "romand_t1_one_ad"
    assert estimate["direct_attempt_count"] == 4
    assert [step["label"] for step in estimate["direct_baseline_stages"]] == [
        "초기 생성", "프롬프트 보강 후 재생성", "기존 이미지 편집 비교", "팀 피드백 반영 수정",
    ]
    assert estimate["direct_estimated_cost_usd"] == "0.249676"
    assert estimate["service_estimated_cost_usd"] == "0.062419"
    assert estimate["estimated_savings_usd"] == "0.187257"
    assert estimate["estimated_image_savings_tokens"] == 20727
    assert estimate["separate_dimension_experiment"] == {
        "comparison_unit": "eight_preset_set",
        "variant_count": 8,
        "initial_attempt_count": 8,
        "refinement_attempt_count": 8,
        "total_tokens": 97022,
        "estimated_cost_usd": "1.297805",
    }
    assert estimate_image_savings(4)["estimated_savings_usd"] == "0.000000"
    assert estimate_image_savings(5)["estimated_savings_usd"] == "-0.062419"


def test_full_ad_savings_requires_costs_for_each_path():
    estimate = estimate_image_savings(1, direct_text_usd="0.010", service_text_usd=Decimal("0.024"))
    assert estimate["cost_scope"] == "image_and_text"
    assert estimate["direct_estimated_cost_usd"] == "0.259676"
    assert estimate["service_estimated_cost_usd"] == "0.086419"
    assert estimate["estimated_savings_usd"] == "0.173257"
    same = estimate_image_savings(8, direct_attempt_count=16, direct_text_usd=0, service_text_usd=0)
    assert same["direct_basis"] == "caller_supplied_same_scope"
    assert same["direct_baseline_stages"] == []
    assert same["estimated_savings_usd"] == "0.499352"
    with pytest.raises(ValueError, match="both paths"):
        estimate_image_savings(1, service_text_usd="0.024")
    with pytest.raises(ValueError, match="at least one"):
        estimate_image_savings(0)
