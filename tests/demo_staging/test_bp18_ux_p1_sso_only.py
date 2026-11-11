"""BP18 UX P1: signed Tailnet-only identity, no invitation-cookie fallback."""
import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from demo_staging.app import make_demo_app
from demo_staging.tailnet_assertion import build_assertion
from scripts.tailnet_sso_gateway import SERVICES,load_users


@pytest.fixture
def env(tmp_path,monkeypatch):
    key=tmp_path/"hmac.key"; key.write_bytes(b"bp18-ux-p1-isolated-test-hmac-do-not-deploy-20261108");key.chmod(0o600)
    actors={"a_test_pm":"admin","a_test_fe":"evaluator","a_test_text":"evaluator",
            "a_test_image":"evaluator","a_test_ops":"evaluator"}
    roles=tmp_path/"roles.json";roles.write_text(json.dumps(actors));roles.chmod(0o600)
    registry=tmp_path/"invites.json"
    code="offline-legacy-cookie-which-must-not-work-in-sso-only-2026"
    registry.write_text(json.dumps({"legacy":{"role":"admin",
        "digest":hashlib.sha256(code.encode()).hexdigest()}}))
    dist=tmp_path/"dist";dist.mkdir();(dist/"assets").mkdir();(dist/"index.html").write_text("<html>product</html>")
    monkeypatch.setenv("IT_TEM_TAILNET_AUTH_ENABLED","YES")
    monkeypatch.setenv("IT_TEM_TAILNET_AUTH_KEY_FILE",str(key))
    monkeypatch.setenv("IT_TEM_TAILNET_ACTORS_FILE",str(roles))
    monkeypatch.setenv("IT_TEM_TAILNET_SSO_ONLY","YES")
    monkeypatch.setenv("IT_TEM_TAILNET_EXPECTED_HOST","my-tailnet.example.ts.net:10500")
    monkeypatch.setenv("IT_TEM_LIVE_ENABLED","NO")
    monkeypatch.setenv("IT_TEM_LIVE_EXECUTION_APPROVED","NO")
    return tmp_path,dist,registry,key.read_bytes(),code


def sign(key,actor,method="GET",target="/demo/api/session",
         host="my-tailnet.example.ts.net:10500",role=None):
    return {"Host":host,**build_assertion(key,actor,role or ("admin" if actor=="a_test_pm" else "evaluator"),
                                          method,target,host)}


def test_sso_only_signed_identity_autologin_and_no_login_prompt(env):
    tmp,dist,inv,key,code=env
    app=make_demo_app(tmp/"app",inv,dist,secure_cookie=True)
    with TestClient(app,base_url="https://my-tailnet.example.ts.net:10500") as c:
        anon=c.get("/demo/api/session")
        assert anon.status_code==401
        user=c.get("/demo/api/session",headers=sign(key,"a_test_pm"))
        assert user.status_code==200
        assert user.json()["auth_provider"]=="TAILSCALE_SERVE"
        assert user.json()["evaluator_id"]=="a_test_pm"
        assert user.json()["role"]=="admin"
        assert c.post("/demo/api/session",json={"invite_code":code},
                      headers={"Origin":"https://my-tailnet.example.ts.net:10500"}).status_code in (401,403)
        assert c.get("/demo/api/session",headers={"Tailscale-User-Login":"someone@example.com"}).status_code==401


def test_cookie_valid_in_legacy_mode_but_ignored_in_sso_mode(env,monkeypatch):
    tmp,dist,inv,key,code=env
    monkeypatch.setenv("IT_TEM_TAILNET_SSO_ONLY","NO")
    legacy=make_demo_app(tmp/"shared",inv,dist,secure_cookie=True)
    with TestClient(legacy,base_url="https://my-tailnet.example.ts.net:10500") as c:
        login=c.post("/demo/api/session",json={"invite_code":code},
                     headers={"Origin":"https://my-tailnet.example.ts.net:10500"})
        assert login.status_code==200
        cookie_name=next(iter(login.cookies.keys()))
        cookie=login.cookies.get(cookie_name)
        assert cookie
        assert c.get("/demo/api/session").status_code==200
    monkeypatch.setenv("IT_TEM_TAILNET_SSO_ONLY","YES")
    hardened=make_demo_app(tmp/"shared",inv,dist,secure_cookie=True)
    with TestClient(hardened,base_url="https://my-tailnet.example.ts.net:10500") as c:
        c.cookies.set(cookie_name,cookie)
        assert c.get("/demo/api/session").status_code==401
        assert c.get("/demo/api/live/capabilities").status_code==401
        signed=c.get("/demo/api/session",headers=sign(key,"a_test_fe"))
        assert signed.status_code==200
        assert signed.json()["evaluator_id"]=="a_test_fe"


def test_old_admin_cookie_cannot_escalate_signed_evaluator(env):
    tmp,dist,inv,key,code=env
    app=make_demo_app(tmp/"app",inv,dist,secure_cookie=True)
    with TestClient(app,base_url="https://my-tailnet.example.ts.net:10500") as c:
        assert c.get("/demo/api/admin/evaluations",
            headers=sign(key,"a_test_fe","GET","/demo/api/admin/evaluations")).status_code==403
        assert c.get("/demo/api/admin/evaluations",
            headers=sign(key,"a_test_pm","GET","/demo/api/admin/evaluations")).status_code==200
        wrong=sign(key,"a_test_pm")
        wrong["x-ittem-tailnet-actor"]="a_test_fe"
        assert c.get("/demo/api/session",headers=wrong).status_code==401


def test_cross_track_signature_key_host_and_role_fail_closed(env):
    tmp,dist,inv,key,code=env
    app=make_demo_app(tmp/"app",inv,dist,secure_cookie=True)
    with TestClient(app,base_url="https://my-tailnet.example.ts.net:10500") as c:
        assert c.get("/demo/api/session",headers=sign(b"different-cross-track-key-12345678901234567890","a_test_pm")).status_code==401
        assert c.get("/demo/api/session",headers=sign(key,"a_test_pm",host="my-tailnet.example.ts.net:10443")).status_code==401
        assert c.get("/demo/api/session",headers=sign(key,"a_test_fe",role="admin")).status_code==401
        forged=sign(key,"a_test_pm");forged["x-ittem-tailnet-signature"]="0"*64
        assert c.get("/demo/api/session",headers=forged).status_code==401


def test_sso_only_cannot_boot_without_signed_provider(tmp_path,monkeypatch):
    monkeypatch.setenv("IT_TEM_TAILNET_AUTH_ENABLED","NO")
    monkeypatch.setenv("IT_TEM_TAILNET_SSO_ONLY","YES")
    dist=tmp_path/"dist";dist.mkdir();(dist/"assets").mkdir();(dist/"index.html").write_text("x")
    registry=tmp_path/"invites.json";registry.write_text("{}")
    with pytest.raises(RuntimeError,match="TAILNET_SSO_ONLY_REQUIRES_SIGNED_AUTH"):
        make_demo_app(tmp_path/"runtime",registry,dist)


def test_sso_gateway_a_b_ports_scoped_exact_not_live_gateway():
    assert SERVICES["8443"]==(18987,18988)
    assert SERVICES["10443"]==(19097,19096)
    assert SERVICES["10500"]==(19101,19100)
    assert SERVICES["10444"]==(19103,19102)
    assert len(set(SERVICES.values()))==4
