"""Trial accounting must separate reusable development from one-ad savings."""

from dataclasses import replace
from decimal import Decimal

import pytest

from src.image_generation.cost_estimate import (
    estimate_image_savings,
    summarize_preset_development,
)
from src.image_generation.cost_history import ImageTrialStage


def stage(**overrides):
    fields = {
        "stage_id": "lighting-refinement-fixture",
        "label": "배색과 조명을 함께 보완한 시험",
        "observed_attempt_count": 2,
        "assumed_attempt_count": 1,
        "usage_priced_attempt_count": 1,
        "usage_based_estimated_usd": "0.080000",
        "dimensions": ("palette", "lighting", "gloss"),
        "source_refs": ("fixture:lighting-report",),
        "assumption": "기록이 없는 추가 시도를 1회로 가정",
    }
    return ImageTrialStage(**(fields | overrides))


def test_missing_trial_and_missing_usage_are_both_priced_without_mixing_bases():
    summary = summarize_preset_development([stage()])

    assert summary["observed_attempt_count"] == 2
    assert summary["assumed_attempt_count"] == 1
    assert summary["attempt_count"] == 3
    assert summary["usage_priced_attempt_count"] == 1
    assert summary["unpriced_attempt_count"] == 2
    assert summary["normalized_estimated_cost_usd"] == "0.187257"
    assert summary["usage_based_known_estimate_usd"] == "0.080000"
    assert summary["fallback_estimated_cost_usd"] == "0.124838"
    assert summary["usage_plus_fallback_estimated_cost_usd"] == "0.204838"
    assert summary["actual_cost_usd"] is None
    assert summary["included_in_per_ad_savings"] is False
    assert len(summary["stages"]) == 1
    row = summary["stages"][0]
    assert row["stage_id"] == "lighting-refinement-fixture"
    assert row["assumed_attempt_count"] == 1
    assert row["assumption"] == "기록이 없는 추가 시도를 1회로 가정"
    assert "fixture:lighting-report" in row["source_refs"]


def test_duplicate_reports_and_multiple_dimension_tags_do_not_add_attempts():
    first = stage()
    summary = summarize_preset_development(iter([first, replace(first), first]))

    assert summary["attempt_count"] == 3
    assert summary["normalized_estimated_cost_usd"] == "0.187257"
    assert summary["usage_based_known_estimate_usd"] == "0.080000"
    assert len(summary["stages"]) == 1


def test_duplicate_stage_id_with_conflicting_evidence_is_rejected():
    first = stage()
    with pytest.raises(ValueError):
        summarize_preset_development([first, replace(first, observed_attempt_count=3)])


def test_distinct_stage_subtotals_include_unknown_usage_at_reference_price():
    second = stage(
        stage_id="geometry-refinement-fixture",
        observed_attempt_count=1,
        assumed_attempt_count=0,
        usage_priced_attempt_count=0,
        usage_based_estimated_usd=None,
        assumption=None,
        dimensions=("geometry",),
    )
    summary = summarize_preset_development([stage(), second])

    assert summary["observed_attempt_count"] == 3
    assert summary["assumed_attempt_count"] == 1
    assert summary["attempt_count"] == 4
    assert summary["unpriced_attempt_count"] == 3
    assert summary["normalized_estimated_cost_usd"] == "0.249676"
    assert summary["fallback_estimated_cost_usd"] == "0.187257"
    assert summary["usage_plus_fallback_estimated_cost_usd"] == "0.267257"


def test_zero_cost_usage_is_observed_and_does_not_use_a_fallback():
    summary = summarize_preset_development([stage(
        observed_attempt_count=1,
        assumed_attempt_count=0,
        usage_priced_attempt_count=1,
        usage_based_estimated_usd="0",
        assumption=None,
    )])

    assert summary["usage_based_known_estimate_usd"] == "0.000000"
    assert summary["fallback_estimated_cost_usd"] == "0.000000"
    assert summary["usage_plus_fallback_estimated_cost_usd"] == "0.000000"
    assert summary["normalized_estimated_cost_usd"] == "0.062419"
    assert summary["actual_cost_usd"] is None


def test_empty_inventory_is_not_replaced_by_defaults_or_reported_as_paid_cost():
    summary = summarize_preset_development([])

    assert summary["attempt_count"] == 0
    assert summary["stages"] == []
    assert summary["normalized_estimated_cost_usd"] == "0.000000"
    assert summary["usage_based_known_estimate_usd"] is None
    assert summary["usage_plus_fallback_estimated_cost_usd"] is None
    assert summary["actual_cost_usd"] is None


@pytest.mark.parametrize("field", [
    "observed_attempt_count", "assumed_attempt_count", "usage_priced_attempt_count",
])
@pytest.mark.parametrize("value", [-1, True, 1.5, "1"])
def test_attempt_counts_require_nonnegative_integers(field, value):
    with pytest.raises(ValueError):
        summarize_preset_development([stage(**{field: value})])


@pytest.mark.parametrize("changes", [
    {"stage_id": ""},
    {"label": ""},
    {"source_refs": ()},
    {"assumption": None},
    {"assumption": ""},
    {"usage_priced_attempt_count": 3},
    {"usage_priced_attempt_count": 0},
    {"usage_based_estimated_usd": None},
    {"usage_based_estimated_usd": "-0.1"},
    {"usage_based_estimated_usd": "NaN"},
    {"usage_based_estimated_usd": "Infinity"},
])
def test_stage_evidence_and_usage_price_must_be_consistent(changes):
    with pytest.raises(ValueError):
        summarize_preset_development([stage(**changes)])


def test_development_total_does_not_inflate_one_ad_savings():
    without_research = estimate_image_savings(1, preset_stages=[])
    with_research = estimate_image_savings(1, preset_stages=[stage()])

    for key in (
        "direct_attempt_count", "service_attempt_count",
        "direct_estimated_cost_usd", "service_estimated_cost_usd",
        "estimated_savings_usd", "estimated_image_savings_tokens",
    ):
        assert with_research[key] == without_research[key]
    assert with_research["estimated_savings_usd"] == "0.187257"
    assert with_research["ad_production"] == without_research["ad_production"]
    assert with_research["preset_development"]["normalized_estimated_cost_usd"] == "0.187257"
    assert with_research["preset_development"]["included_in_per_ad_savings"] is False


def test_text_and_regeneration_comparison_stays_separate_from_development():
    estimate = estimate_image_savings(
        5, direct_text_usd="0.024", service_text_usd="0.024", preset_stages=[stage()],
    )

    assert estimate["cost_scope"] == "image_and_text"
    assert estimate["estimated_savings_usd"] == "-0.062419"
    assert estimate["preset_development"]["usage_plus_fallback_estimated_cost_usd"] == "0.204838"


def test_returned_inventory_changes_do_not_mutate_future_reports():
    original = summarize_preset_development()
    changed = summarize_preset_development()
    assert original["stages"]
    changed["stages"][0]["label"] = "caller modified"
    changed["stages"].append({"stage_id": "unexpected"})

    assert summarize_preset_development() == original


def test_default_history_accounts_for_missing_trials_and_keeps_tools_out_of_api_cost():
    result = estimate_image_savings(1, direct_text_usd="0.024", service_text_usd="0.024")
    development = result["preset_development"]
    assert development["attempt_count"] == 138
    assert development["observed_attempt_count"] == 113
    assert development["assumed_attempt_count"] == 25
    assert development["normalized_estimated_cost_usd"] == "8.613822"
    assert development["usage_based_known_estimate_usd"] == "7.992364"
    assert development["fallback_estimated_cost_usd"] == "1.560475"
    assert development["usage_plus_fallback_estimated_cost_usd"] == "9.552839"
    assert development["amortized_per_ad_usd"] is None
    assert development["actual_cost_usd"] is None

    history = result["historical_ad_production"]
    assert history["attempt_count"] == 2
    assert history["usage_based_known_estimate_usd"] == "0.100846"
    tools = result["unmetered_tool_development"]
    assert tools["assumed_api_equivalent_attempt_count"] == 6
    assert tools["normalized_equivalent_cost_usd"] == "0.374514"
    assert tools["team_image_api_attempt_count"] == 0
    assert tools["team_image_api_cost_usd"] == "0.000000"
    assert tools["actual_tool_cost_usd"] is None
    scopes = [development, history, tools]
    ids = [s["stage_id"] for scope in scopes for s in scope["stages"]]
    assert len(ids) == len(set(ids))
    assert result["ad_production"]["service_estimated_cost_usd"] == "0.086419"
    assert result["estimated_savings_usd"] == "0.187257"


def test_snapshot_keeps_dimension_rework_and_local_edits_as_distinct_operations():
    result = estimate_image_savings(1)
    rows = {row["stage_id"]: row for row in result["preset_development"]["stages"]}
    initial = rows["preset-expansion-skinfood-live-20261104"]
    refinement = rows["skinfood-dimension-refinement-live-20261104"]
    # The compatibility reference is not a third charge for these same 16 runs.
    assert initial["attempt_count"] + refinement["attempt_count"] == 16
    assert (Decimal(initial["usage_based_known_estimate_usd"])
            + Decimal(refinement["usage_based_known_estimate_usd"])) == Decimal("1.297805")
    assert len(refinement["dimensions"]) == 14
    assert refinement["attempt_count"] == 8  # not eight times fourteen
    for key in ("romand-bright-tones-20261029", "romand-a-fonts-20261109",
                "original-label-pixel-composite-20261105"):
        assert rows[key]["attempt_count"] == 0
        assert rows[key]["normalized_estimated_cost_usd"] == "0.000000"
    for key in ("T0", "T1R", "T1E", "T2E"):
        assert rows[key]["assumed_attempt_count"] == 6
        assert rows[key]["count_is_estimated"]
        assert rows[key]["assumption"]
    assert rows["prompt_refinement_recovery"]["assumed_attempt_count"] == 1
    assert rows["prompt_refinement_recovery"]["observed_attempt_count"] == 1
