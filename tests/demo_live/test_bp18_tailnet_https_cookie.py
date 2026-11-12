"""BP18 r0.1: HTTPS host-only session cookie and A/B session boundaries.

No real API provider calls, no Tailnet admin mutation, no disk escape.
"""
import hashlib
import json
from fastapi.testclient import TestClient
import pytest
from demo_staging.app import make_demo_app


def _fixture(tmp_path):
    dist=tmp_path/"dist"
    (dist/"assets").mkdir(parents=True)
    (dist/"index.html").write_text("safe HTML")
    code="bp18-fake-test-invite-never-live-2026-11"
    reg=tmp_path/"invites.json"
    reg.write_text(json.dumps({
      "testactor":{"role":"evaluator","digest":hashlib.sha256(code.encode()).hexdigest()}
    }))
    return dist,reg,code


def test_https_host_only_secure_cookie_for_both_a_and_b(tmp_path,monkeypatch):
    dist,invites,code=_fixture(tmp_path)
    monkeypatch.delenv("IT_TEM_TAILNET_AUTH_ENABLED",raising=False)
    monkeypatch.setenv("IT_TEM_QA_FIXTURE_ENABLED","YES")
    monkeypatch.setenv("IT_TEM_LIVE_ENABLED","NO")
    monkeypatch.setenv("IT_TEM_LIVE_EXECUTION_APPROVED","NO")
    monkeypatch.setenv("IT_TEM_DEMO_SECURE_COOKIE","YES")
    monkeypatch.setenv("IT_TEM_QA_ALLOWED_ACTORS","testactor")
    hostname="macstudio-macstudio.tail17dfff.ts.net"
    a_base=f"https://{hostname}:10443"
    b_base=f"https://{hostname}:10500"
    monkeypatch.setenv("IT_TEM_DEMO_COOKIE_NAME","__Host-ittem_bp18_a_session")
    a=make_demo_app(tmp_path/"trackA",invites,dist,secure_cookie=True,
                    code_sha="a"*40)
    with TestClient(a,base_url=a_base) as client:
        signed=client.post("/demo/api/session",json={"invite_code":code},
                           headers={"Origin":a_base})
        assert signed.status_code==200,signed.text
        cookie=signed.headers["set-cookie"]
        assert "__Host-ittem_bp18_a_session=" in cookie
        assert "secure" in cookie.lower()
        assert "httponly" in cookie.lower() and "samesite=lax" in cookie.lower()
        assert "domain=" not in cookie.lower()
        assert "path=/" in cookie.lower()
        assert client.get("/demo/api/session").json()["authenticated"] is True
        # The HTTPS UAT server never exposes paid or fixture bypass routes.
        assert client.post("/demo/api/qa/jobs/"+"a"*32+"/text",
                   headers={"Origin":a_base}).status_code==404
        assert client.post("/api/v1/jobs",headers={"Origin":f"http://{hostname}:10443"}).status_code==403
        cookie_jar=client.cookies
        monkeypatch.setenv("IT_TEM_DEMO_COOKIE_NAME","__Host-ittem_bp18_b_session")
        b=make_demo_app(tmp_path/"trackB",invites,dist,secure_cookie=True,
                        code_sha="b"*40)
        with TestClient(b,base_url=b_base,cookies=cookie_jar) as peer:
            assert peer.get("/demo/api/session").status_code==401
            assert peer.get("/demo/api/live/capabilities").status_code==401
            assert peer.post("/api/v1/jobs",headers={"Origin":b_base}).status_code==401
        # Valid A remains logged in after peer verification.
        assert client.get("/demo/api/session").json()["authenticated"] is True


@pytest.mark.parametrize("cookie",[
  "ittem_bp18_a_session","__Host-","__Host-../etc/passwd",
  "__Host_invalid","a"*60,
])
def test_secure_cookie_rejects_non_host_or_invalid_audience(tmp_path,monkeypatch,cookie):
    dist,invites,_=_fixture(tmp_path)
    monkeypatch.delenv("IT_TEM_TAILNET_AUTH_ENABLED",raising=False)
    monkeypatch.setenv("IT_TEM_DEMO_COOKIE_NAME",cookie)
    with pytest.raises(ValueError,match="(DEMO_COOKIE_AUDIENCE_INVALID|SECURE_COOKIE_REQUIRES_HOST_PREFIX)"):
        make_demo_app(tmp_path/"runtime",invites,dist,secure_cookie=True)
