"""BP13 no-charge cost reference: official rates × 10 image usage records, strict profile."""
import pytest
from fastapi.testclient import TestClient

from demo_staging.live.image_cost_estimate import (MODEL,estimate_image_once,
    OBSERVED_USAGE,RATES_PER_MILLION_USD)
from tests.demo_live.test_http_gateway import setup,login


@pytest.mark.parametrize("ratio,n",[("3:4",2),("4:5",5),("9:16",3)])
def test_composed_profile_has_conservative_observed_range_not_cap(ratio,n):
    result=estimate_image_once(ratio=ratio,generation_mode="composed",model=MODEL)
    assert result["status"]=="LIMITED_EMPIRICAL_REFERENCE"
    assert result["sample_count"]==n
    assert 0<result["observed_min_usd"]<=result["reference_median_usd"]<=result["observed_max_usd"]
    assert result["monitor_only"] is True
    assert result["billing_cap"] is False and result["actual_charges_known"] is False
    assert sum(len(x) for x in OBSERVED_USAGE.values())==10
    assert RATES_PER_MILLION_USD=={"input_text":5.0,"input_image":8.0,"output_image":30.0}


@pytest.mark.parametrize("mode,model,quality,complexity",[
    ("freeform",MODEL,"medium","high"),
    ("composed",MODEL,"high","high"),
    ("composed","gpt-image-2-2026-04-21","medium","high"),
    ("composed",MODEL,"medium","low"),
])
def test_no_observation_produces_no_fabricated_dollar(mode,model,quality,complexity):
    s=estimate_image_once(ratio="4:5",generation_mode=mode,model=model,
                         quality=quality,complexity=complexity)
    assert s["reference_median_usd"] is None
    assert s["observed_min_usd"] is None and s["observed_max_usd"] is None
    assert s["status"]=="NO_MATCHING_PROFILE_EVIDENCE"


@pytest.mark.parametrize("ratio,mode",[
    ("1:1","composed"),("4:5","batch"),("4x5","freeform")])
def test_bad_scope_fails_closed(ratio,mode):
    with pytest.raises(ValueError):
        estimate_image_once(ratio=ratio,generation_mode=mode,model=MODEL)


def test_cost_estimate_authenticated_and_not_a_provider_call(tmp_path):
    app,codes=setup(tmp_path)
    with TestClient(app) as anon:
        assert anon.get("/demo/api/live/total-cost-estimate").status_code==401
    with TestClient(app) as client:
        login(client,codes["alice"])
        old=client.get("/demo/api/live/text-cost-estimate?photo_count=2")
        assert old.status_code==200,old.text
        assert old.json()["scope"]=="TEXT_ONLY"
        composed=client.get("/demo/api/live/total-cost-estimate",
            params={"photo_count":2,"image_size":"4:5","generation_mode":"composed"})
        assert composed.status_code==200,composed.text
        row=composed.json()
        assert row["scope"]=="TEXT_PLUS_ONE_IMAGE"
        assert row["text"]["estimate_usd"]==old.json()["total_usd"]
        assert row["image"]["sample_count"]==5
        assert row["total_reference_usd"]==pytest.approx(
            row["image"]["reference_median_usd"]+row["text"]["estimate_usd"],abs=1e-6)
        assert row["actual_charges_known"] is False and row["cost_policy"]=="MONITOR_ONLY"
        free=client.get("/demo/api/live/total-cost-estimate",
            params={"photo_count":2,"image_size":"4:5","generation_mode":"freeform"})
        assert free.status_code==200
        assert free.json()["image"]["reference_median_usd"] is None
        assert free.json()["total_reference_usd"] is None
        invalid=client.get("/demo/api/live/total-cost-estimate",
            params={"photo_count":2,"image_size":"4:5","generation_mode":"batch"})
        assert invalid.status_code==422
        with app.state.live_pipeline.cost.connect() as c:
            assert c.execute("select count(*) from attempts").fetchone()[0]==0
        with app.state.live_queue.db() as c:
            assert c.execute("select count(*) from queued_ops").fetchone()[0]==0
