"""Owner Text v0.10 message -> Serving API + safety regressions, no paid provider."""
import pytest
from fastapi.testclient import TestClient

from demo_staging.live.contracts import strict_review
from tests.demo_live.test_http_gateway import setup,login
from tests.demo_live.test_live_contracts import sample_input,safe_copy


@pytest.mark.parametrize("selected,expected_risk,expected_pass",[
    ([], "근거 확인 필요",True),
    (["미백"],"위반 의심",False),
    (["주름개선"],"근거 확인 필요",True),
])
def test_specific_functional_review_warn_or_block_without_owner_code_edit(
    selected,expected_risk,expected_pass
):
    analysis,_,copy,_=safe_copy()
    product=sample_input()["product"]
    product.update(is_functional=True,functional_types=selected)
    copy["ad_copy"]["headline"]="주름 개선"
    report=strict_review(copy,product,analysis)
    risks=[x["risk_level"] for x in report["issues"]
           if x["category"]=="기능성 오인" and x["text"]=="주름 개선"]
    assert expected_risk in risks,report
    assert report["passed"] is expected_pass


def test_text_cost_estimate_requires_session_and_never_dispatches(tmp_path,monkeypatch):
    # New authenticated estimate is pure arithmetic, not actual invoice or
    # provider attempt. It works even with all Live execution gates OFF.
    for k in ("IT_TEM_LIVE_ENABLED","IT_TEM_LIVE_EXECUTION_APPROVED",
              "IT_TEM_LIVE_WEB_QUEUE_ENABLED"):
        monkeypatch.setenv(k,"NO")
    monkeypatch.delenv("OPENAI_API_KEY",raising=False)
    monkeypatch.setenv("IT_TEM_TEXT_MODEL","gpt-6-luna")
    monkeypatch.setenv("IT_TEM_VISION_MODEL","gpt-6-luna")
    app,codes=setup(tmp_path)
    with TestClient(app) as c:
        assert c.get("/demo/api/live/text-cost-estimate?photo_count=2").status_code==401
        login(c,codes["alice"])
        url="/demo/api/live/text-cost-estimate"
        two=c.get(url,params={"photo_count":2})
        five=c.get(url,params={"photo_count":5})
        assert two.status_code==200 and five.status_code==200
        smaller=two.json();larger=five.json()
        assert smaller["mode"]=="NON_BILLABLE_ESTIMATE"
        assert smaller["scope"]=="TEXT_ONLY"
        assert smaller["includes_image_generation"] is False
        assert smaller["actual_charges_known"] is False
        assert smaller["model"]=="gpt-6-luna"
        assert 0<smaller["total_usd"]<larger["total_usd"]
        assert larger["total_usd"] < 0.1
        assert smaller["display"].startswith("약 $")
        copy=c.get(url,params={"revision_target":"copy"})
        image=c.get(url,params={"revision_target":"image_prompt"})
        assert copy.status_code==image.status_code==200
        assert 0<copy.json()["total_usd"]<0.001
        assert 0<image.json()["total_usd"]<0.001
        assert copy.json()["display"]=="$0.001 미만"
        assert c.get(url,params={"photo_count":1}).status_code==422
        assert c.get(url,params={"photo_count":6}).status_code==422
        assert c.get(url,params={"revision_target":"not-a-model"}).status_code==422
        monkeypatch.setenv("IT_TEM_TEXT_MODEL","unknown")
        assert c.get(url,params={"photo_count":2}).status_code==422
    for name in ("queue.sqlite","cost.sqlite"):
        from pathlib import Path
        import sqlite3
        file=tmp_path/"runtime"/"live"/name
        assert file.is_file()
        with sqlite3.connect(file) as db:
            tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            for table in ("queued_ops","attempts"):
                if table in tables:
                    assert db.execute("SELECT COUNT(*) FROM "+table).fetchone()[0]==0



@pytest.mark.parametrize("term,selected,expected_risk",[
    ("태닝",[], "근거 확인 필요"),
    ("태닝",["미백"],"위반 의심"),
    ("태닝",["태닝"],"근거 확인 필요"),
    ("모발 색상 변화",["미백"],"위반 의심"),
    ("모발 색상 변화",["모발색상변화"],"근거 확인 필요"),
    ("체모 제거",["미백"],"위반 의심"),
    ("체모 제거",["체모제거"],"근거 확인 필요"),
])
def test_missing_owner_functional_rule_literal_safety(
    term,selected,expected_risk
):
    analysis,_,copy,_=safe_copy()
    p=sample_input()["product"]
    p.update(is_functional=True,functional_types=selected)
    copy["ad_copy"]["headline"]=term
    report=strict_review(copy,p,analysis)
    risks=[issue["risk_level"] for issue in report["issues"]
           if issue["category"]=="기능성 오인" and issue["text"]==term]
    assert expected_risk in risks,(term,report)
    if expected_risk=="위반 의심":
        assert report["passed"] is False
