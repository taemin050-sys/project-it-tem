import pytest
from demo_staging.live.http_api import web_queue_policy
from tests.demo_live.test_http_gateway import setup,login
from fastapi.testclient import TestClient

ALL={
 "IT_TEM_LIVE_WEB_QUEUE_ENABLED":"YES",
 "IT_TEM_LIVE_ENABLED":"YES",
 "IT_TEM_LIVE_EXECUTION_APPROVED":"YES",
 "IT_TEM_PROVIDER_READINESS_CONFIRMED":"YES",
 "IT_TEM_LIVE_APPROVED_ACTORS":"alice",
 "IT_TEM_LIVE_REQUEST_LIMIT":"5",
 "IT_TEM_LIVE_BUDGET_USD":"3",
 "IT_TEM_TEXT_RESERVATION_USD":"0.5",
 "IT_TEM_IMAGE_RESERVATION_USD":"1",
}

def test_web_policy_explicit_all_controls_and_actor_scoping(monkeypatch,tmp_path):
    for k,v in ALL.items():monkeypatch.setenv(k,v)
    assert web_queue_policy()["enabled"] is True
    app,invites=setup(tmp_path)
    with TestClient(app) as alice,TestClient(app) as bob:
        login(alice,invites["alice"])
        login(bob,invites["bob"])
        assert alice.get("/demo/api/live/capabilities").json()["live_enabled"] is True
        assert bob.get("/demo/api/live/capabilities").json()["live_enabled"] is False
    # No provider calls, no key needed just to inspect policy.
    monkeypatch.setenv("IT_TEM_LIVE_WEB_QUEUE_ENABLED","NO")
    assert web_queue_policy()["enabled"] is False

@pytest.mark.parametrize("key,invalid",[
    ("IT_TEM_LIVE_BUDGET_USD","nan"),
    ("IT_TEM_LIVE_BUDGET_USD","0"),
    ("IT_TEM_TEXT_RESERVATION_USD","5"),
    ("IT_TEM_LIVE_APPROVED_ACTORS","*"),
    ("IT_TEM_LIVE_APPROVED_ACTORS",""),
    ("IT_TEM_LIVE_REQUEST_LIMIT","0"),
    ("IT_TEM_LIVE_EXECUTION_APPROVED","NO"),
])
def test_web_queue_policy_fail_closed(monkeypatch,key,invalid):
    for k,v in ALL.items():monkeypatch.setenv(k,v)
    monkeypatch.setenv(key,invalid)
    assert web_queue_policy()["enabled"] is False

def test_key_alone_is_never_sufficient(monkeypatch):
    for k in ALL:monkeypatch.delenv(k,raising=False)
    monkeypatch.setenv("OPENAI_API_KEY","never-use-test-key")
    assert web_queue_policy()["enabled"] is False
