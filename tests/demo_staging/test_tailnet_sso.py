"""Tailscale SSO auth: signed, exact allowlist, job ACL, admin & CSRF fail closed."""
import hashlib
import io
import json
import os
import time

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from demo_staging.app import make_demo_app
from demo_staging.tailnet_assertion import build_assertion


@pytest.fixture
def fixture(tmp_path,monkeypatch):
    dist=tmp_path/"dist";(dist/"assets").mkdir(parents=True)
    (dist/"index.html").write_text("<html>safe QA</html>")
    (tmp_path/"invites.json").write_text(json.dumps({
        "qaowner":{"role":"admin","digest":hashlib.sha256(b"legacy-test-admin-code-1234567").hexdigest()},
    }))
    secret=(b"isolated-offline-test-hmac-key-not-a-real-key-0123456789")
    key=tmp_path/"tailnet.key"
    key.write_bytes(secret);key.chmod(0o600)
    registry=tmp_path/"roles.json"
    registry.write_text(json.dumps({
        "exobiz7":"admin","hyuksang":"evaluator","dahye":"evaluator",
        "taemin":"evaluator","jisu":"evaluator"}))
    monkeypatch.setenv("IT_TEM_TAILNET_AUTH_ENABLED","YES")
    monkeypatch.setenv("IT_TEM_TAILNET_AUTH_KEY_FILE",str(key))
    monkeypatch.setenv("IT_TEM_TAILNET_ACTORS_FILE",str(registry))
    monkeypatch.setenv("IT_TEM_LIVE_ENABLED","NO")
    monkeypatch.setenv("IT_TEM_LIVE_EXECUTION_APPROVED","NO")
    app=make_demo_app(tmp_path/"runtime",tmp_path/"invites.json",dist,secure_cookie=False)
    return app,secret


def signed(key,actor,role,method,path,host="testserver",now=None):
    return {"Host":host,**build_assertion(key,actor,role,method,path,host,now=now)}


def png(rgb=(140,142,145)):
    data=io.BytesIO();Image.new("RGB",(120,160),rgb).save(data,"PNG")
    return data.getvalue()


def test_tailnet_zero_invite_session_admin_acl_and_signing(fixture):
    app,key=fixture
    j="a"*32
    with TestClient(app) as owner,TestClient(app) as member:
        assert owner.get("/demo/api/session").status_code==401
        unsigned=owner.get("/demo/api/session",headers={"Tailscale-User-Login":"exobiz7@gmail.com"})
        assert unsigned.status_code==401
        admin=owner.get("/demo/api/session",headers=signed(key,"exobiz7","admin","GET","/demo/api/session"))
        assert admin.status_code==200,admin.text
        assert admin.json()["evaluator_id"]=="exobiz7"
        assert admin.json()["auth_provider"]=="TAILSCALE_SERVE"
        assert admin.json()["role"]=="admin"
        assert owner.get("/demo/api/admin/evaluations",
            headers=signed(key,"exobiz7","admin","GET","/demo/api/admin/evaluations")).status_code==200
        m=member.get("/demo/api/session",
            headers=signed(key,"dahye","evaluator","GET","/demo/api/session"))
        assert m.status_code==200 and m.json()["evaluator_id"]=="dahye"
        assert member.get("/demo/api/admin/evaluations",
            headers=signed(key,"dahye","evaluator","GET","/demo/api/admin/evaluations")).status_code==403
        created=owner.post("/api/v1/jobs",files=[
            ("product_images",("one.png",png(),"image/png")),
            ("product_images",("two.png",png((142,145,146)),"image/png"))],
            headers={**signed(key,"exobiz7","admin","POST","/api/v1/jobs"),
                     "Origin":"http://testserver"})
        assert created.status_code==201,created.text
        jid=created.json()["job_id"]
        assert owner.get("/api/v1/jobs/"+jid,
            headers=signed(key,"exobiz7","admin","GET","/api/v1/jobs/"+jid)).status_code==200
        assert member.get("/api/v1/jobs/"+jid,
            headers=signed(key,"dahye","evaluator","GET","/api/v1/jobs/"+jid)).status_code==404
        assert member.post("/demo/api/live/jobs/"+jid+"/approve-copy",
            json={"expected_generation":1,"expected_review_sha":"x"},
            headers={**signed(key,"dahye","evaluator","POST","/demo/api/live/jobs/"+jid+"/approve-copy"),
                     "Origin":"http://testserver"}).status_code==404


def test_header_spoof_tamper_expiry_method_query_acl_fail_closed(fixture):
    app,key=fixture
    path="/demo/api/session"
    with TestClient(app) as c:
        good=signed(key,"exobiz7","admin","GET",path)
        assert c.get(path,headers=good).status_code==200
        changed=dict(good);changed["x-ittem-tailnet-actor"]="dahye"
        assert c.get(path,headers=changed).status_code==401
        escalated=dict(good);escalated["x-ittem-tailnet-role"]="evaluator"
        assert c.get(path,headers=escalated).status_code==401
        fake_actor=signed(key,"unauthorized","evaluator","GET",path)
        assert c.get(path,headers=fake_actor).status_code==401
        old=signed(key,"exobiz7","admin","GET",path,now=int(time.time())-180)
        assert c.get(path,headers=old).status_code==401
        wrong_host=dict(good);wrong_host["Host"]="foreign.example"
        assert c.get(path,headers=wrong_host).status_code==401
        missing=dict(good);missing.pop("x-ittem-tailnet-signature")
        assert c.get(path,headers=missing).status_code==401
        # The assertion is scoped to method+path+query+Host.
        assert c.get(path+"?changed=yes",headers=good).status_code==401
        assert c.post(path,headers={**good,"Origin":"http://testserver"},
                      json={"invite_code":"legacy-test-admin-code-1234567"}).status_code==401
        # Browser CSRF applies even with a fresh signed identity.
        cross=c.post("/api/v1/jobs",files=[],
             headers={**signed(key,"exobiz7","admin","POST","/api/v1/jobs"),
                      "Origin":"http://evil.invalid"})
        assert cross.status_code==403


def test_signed_identity_cannot_be_switched_using_cookie_or_login(fixture):
    app,key=fixture
    with TestClient(app) as c:
        response=c.post("/demo/api/session",json={"invite_code":"legacy-test-admin-code-1234567"},
                        headers={"Origin":"http://testserver"})
        assert response.status_code==200
        who=c.get("/demo/api/session",
                  headers=signed(key,"dahye","evaluator","GET","/demo/api/session"))
        assert who.status_code==200 and who.json()["evaluator_id"]=="dahye"
        admin=c.get("/demo/api/admin/evaluations",
                    headers=signed(key,"dahye","evaluator","GET","/demo/api/admin/evaluations"))
        assert admin.status_code==403
        protected=c.delete("/demo/api/session",
                  headers={**signed(key,"dahye","evaluator","DELETE","/demo/api/session"),
                           "Origin":"http://testserver"})
        assert protected.status_code==409
        local_session=c.get("/demo/api/session")
        assert local_session.status_code==200 and local_session.json()["evaluator_id"]=="qaowner"


def test_signed_tailnet_identity_can_use_existing_private_qa_api(fixture,monkeypatch):
    app,key=fixture
    with TestClient(app) as c:
        good=c.get("/demo/api/live/capabilities",
            headers=signed(key,"taemin","evaluator","GET","/demo/api/live/capabilities"))
        assert good.status_code==200 and good.json()["live_enabled"] is False
        anon=c.get("/demo/api/live/capabilities")
        assert anon.status_code==401
        invalid=c.get("/demo/api/live/capabilities",
            headers=signed(key,"unauthorized","evaluator","GET","/demo/api/live/capabilities"))
        assert invalid.status_code==401


def test_mac_gateway_registry_is_exact_allowlist(tmp_path):
    from scripts.tailnet_sso_gateway import load_users
    p=tmp_path/"user-map.json"
    user_map={f"user{i}@example.com":{"actor":f"actor{i}","role":"evaluator"}
              for i in range(5)}
    p.write_text(json.dumps(user_map))
    p.chmod(0o600)
    assert len(load_users(str(p)))==5
    p.write_text(json.dumps({**user_map,"intruder@example.com":
                             {"actor":"intruder","role":"evaluator"}}))
    with pytest.raises(RuntimeError,match="EXACT_FIVE"):
        load_users(str(p))
    p.write_text(json.dumps(user_map))
    p.chmod(0o644)
    with pytest.raises(RuntimeError,match="INSECURE"):
        load_users(str(p))
