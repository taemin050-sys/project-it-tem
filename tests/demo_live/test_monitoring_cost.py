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
