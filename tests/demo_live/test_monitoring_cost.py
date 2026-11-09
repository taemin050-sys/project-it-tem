import hashlib
from uuid import uuid4
from demo_staging.live_safety import AttemptLedger
from src.image_generation.provider_attempts import ProviderAttemptStore

def test_aggregate_monitoring_only_has_no_budget_or_user_count_stop(tmp_path):
    q=AttemptLedger(tmp_path/"a.sqlite",live_enabled=True,monitoring_only=True,
                    max_requests=0,budget_usd=0)
    for i in range(5):
        row=q.reserve(actor="alice",role="live_operator",job_id="j"+str(i),
                stage="vision",payload={"i":i},estimated_usd=0,pm_authorized=True)
        assert row["new"]
        assert q.inspect(row["id"])["reserved_microusd"]==0
    duplicate=q.reserve(actor="alice",role="live_operator",job_id="j0",
                stage="vision",payload={"i":0},estimated_usd=0,pm_authorized=True)
    assert not duplicate["new"]

def test_image_owner_monitoring_only_allows_zero_without_duplicate(tmp_path):
    store=ProviderAttemptStore(tmp_path/"image.sqlite")
    job,project=uuid4(),uuid4()
    req="c"*64
    attempt=store.begin(job,project,req,budget_limit_usd="0",
                        reservation_usd="0",monitoring_only=True)
    assert attempt
    record=store.get(job,project)
    assert record["reservation_usd"]=="0.000000"
    import pytest
    from src.image_generation.errors import GatewayError
    with pytest.raises(GatewayError,match="already has a provider attempt"):
        store.begin(job,project,req,budget_limit_usd="0",
                    reservation_usd="0",monitoring_only=True)


def test_older_live_candidate_uses_explicit_one_attempt_scenario():
    from src.image_generation.cost_estimate import summarize_image_costs

    empty, no_comparison = summarize_image_costs([], has_candidate=False)
    assert empty["estimated_total_usd"] is None
    assert no_comparison is None

    summary, comparison = summarize_image_costs([], has_candidate=True)
    assert summary == {
        "known_estimated_cost_usd": None,
        "estimated_total_usd": "0.062419",
        "priced_attempt_count": 0,
        "unpriced_attempt_count": 1,
    }
    assert comparison["service_attempt_count"] == 1
    assert comparison["service_attempt_count_is_estimated"] is True
    assert comparison["estimated_savings_usd"] == "0.062419"
    assert comparison["estimated_savings_tokens"] == 6909
