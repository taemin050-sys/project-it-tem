from pathlib import Path

import pytest

from demo_staging.live_safety import AttemptLedger, LiveNotAuthorized


def test_live_disabled_by_default(tmp_path):
    guard=AttemptLedger(tmp_path/"a.sqlite")
    with pytest.raises(LiveNotAuthorized):
        guard.reserve(actor="a",role="live_operator",job_id="j",stage="text",
                      payload={"copy":"hello"},estimated_usd=.001,pm_authorized=True)


def test_role_and_pm_auth_always_required(tmp_path):
    guard=AttemptLedger(tmp_path/"a.sqlite",live_enabled=True,max_requests=2,budget_usd=1)
    for role,pm in [("evaluator",True),("live_operator",False)]:
        with pytest.raises(LiveNotAuthorized):
            guard.reserve(actor="a",role=role,job_id="j",stage="text",
                          payload={"x":"1"},estimated_usd=.01,pm_authorized=pm)


def test_idempotent_single_dispatch_and_crash_unknown_never_retries(tmp_path):
    file=tmp_path/"a.sqlite"
    kwargs={"actor":"a","role":"live_operator","job_id":"j1",
            "stage":"text","payload":{"x":"1"},"estimated_usd":.25,
            "pm_authorized":True}
    g=AttemptLedger(file,live_enabled=True,max_requests=2,budget_usd=.5)
    original=g.reserve(**kwargs)
    assert original["new"] is True
    assert g.reserve(**kwargs)==dict(original,id=original["id"],status="RESERVED",new=False)
    g.dispatch_intent(original["id"])
    with pytest.raises(LiveNotAuthorized):g.dispatch_intent(original["id"])
    restarted=AttemptLedger(file,live_enabled=True,max_requests=2,budget_usd=.5)
    assert restarted.reconcile_crashed_dispatches()==1
    assert restarted.inspect(original["id"])["billing_unknown"]==1
    again=restarted.reserve(**kwargs)
    assert again["status"]=="BILLING_UNKNOWN" and not again["new"]
    with pytest.raises(LiveNotAuthorized):restarted.dispatch_intent(original["id"])


def test_budget_and_receipt_guards(tmp_path):
    g=AttemptLedger(tmp_path/"a.sqlite",live_enabled=True,max_requests=2,budget_usd=.3)
    args={"actor":"a","role":"live_operator","job_id":"j1","stage":"image",
          "payload":{"prompt":"mock"},"estimated_usd":.2,"pm_authorized":True}
    a=g.reserve(**args)
    with pytest.raises(LiveNotAuthorized):
        g.reserve(**dict(args,job_id="j2",payload={"prompt":"different"}))
    g.dispatch_intent(a["id"])
    with pytest.raises(LiveNotAuthorized):g.confirm(a["id"],cost_usd=.5,receipt="r")
    g.confirm(a["id"],cost_usd=.15,receipt="fake-receipt")
    assert g.inspect(a["id"])["status"]=="SUCCEEDED"
    assert not g.reserve(**args)["new"]
