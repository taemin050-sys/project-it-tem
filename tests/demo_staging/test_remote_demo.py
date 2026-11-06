import hashlib
import io
import json
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from demo_staging.app import make_demo_app


def image(rgb):
    out=io.BytesIO()
    Image.new("RGB",(135,175),rgb).save(out,"PNG")
    return out.getvalue()


@pytest.fixture()
def setup(tmp_path,monkeypatch):
    frontend=tmp_path/"dist"
    (frontend/"assets").mkdir(parents=True)
    (frontend/"index.html").write_text("<html><body>IT-TEM MOCK</body></html>")
    codes={"alice":"secure-code-alice-test-not-real-2026",
           "bob":"secure-code-bob-test-not-real-2026",
           "pm_admin":"secure-code-admin-test-not-real-2026"}
    json_file=tmp_path/"invites.json"
    json_file.write_text(json.dumps({
      actor:{"digest":hashlib.sha256(code.encode()).hexdigest(),
             "role":"admin" if actor=="pm_admin" else "evaluator"} for actor,code in codes.items()
    }))
    monkeypatch.setenv("IT_TEM_KOREAN_FONT","/System/Library/Fonts/Supplemental/NotoSansGothic-Regular.ttf")
    app=make_demo_app(tmp_path/"runtime",json_file,frontend,secure_cookie=False,code_sha="test123")
    return app,codes


def login(client,code):
    return client.post("/demo/api/session",json={"invite_code":code},
                       headers={"Origin":"http://testserver"})


def step(client,job,path,body=None):
    return client.post("/api/v1/jobs/"+job+"/"+path,json=body,
                       headers={"Origin":"http://testserver"})


def create(client):
    return client.post("/api/v1/jobs",files=[
        ("product_images",("a.png",image((122,130,140)),"image/png")),
        ("product_images",("b.png",image((145,140,135)),"image/png")),
    ],headers={"Origin":"http://testserver"})


def finish(client,jid):
    assert step(client,jid,"mock/plan",{"brand_name":"라움","product_name":"크림"}).status_code==200
    assert step(client,jid,"mock/copy").status_code==200
    assert step(client,jid,"approvals/copy",{"approved":True}).status_code==200
    assert step(client,jid,"mock/image").status_code==200
    assert step(client,jid,"approvals/image",{"approved":True}).status_code==200
    assert step(client,jid,"mock/compose").status_code==200


def test_unauthenticated_and_csrf_fail_closed(setup):
    app,codes=setup
    with TestClient(app) as client:
        assert client.get("/api/v1/jobs/"+"a"*32).status_code==401
        assert create(client).status_code==401
        assert client.get("/demo/api/admin/evaluations").status_code==401
        assert client.get("/demo/api/session").status_code==401
        assert client.post("/demo/api/session",json={"invite_code":codes["alice"]}).status_code==403
        assert client.post("/demo/api/session",json={"invite_code":"wrong"*10},
                           headers={"Origin":"http://testserver"}).status_code==401
        assert login(client,codes["alice"]).status_code==200
        assert client.post("/api/v1/jobs",files=[],headers={"Origin":"http://evil.invalid"}).status_code==403


def test_owner_isolation_approvals_downloads_and_reviews(setup):
    app,codes=setup
    with TestClient(app) as alice,TestClient(app) as bob,TestClient(app) as pm:
        assert login(alice,codes["alice"]).status_code==200
        assert login(bob,codes["bob"]).status_code==200
        assert login(pm,codes["pm_admin"]).status_code==200
        created=create(alice)
        assert created.status_code==201,created.text
        job=created.json()["job_id"]
        asset=created.json()["assets"][0]["asset_id"]
        for endpoint in ("/api/v1/jobs/"+job,
            "/api/v1/jobs/"+job+"/assets/"+asset,
            "/api/v1/jobs/"+job+"/artifacts/final",
            "/demo/api/jobs/"+job+"/events",
            "/demo/api/jobs/"+job+"/evaluations"):
            assert bob.get(endpoint).status_code==404, endpoint
        assert step(bob,job,"approvals/copy",{"approved":True}).status_code==404
        assert step(bob,job,"mock/copy").status_code==404
        assert bob.post("/demo/api/evaluations",json={"job_id":job,"scenario_id":"UC-01",
                  "category":"ui_ux","score":5},headers={"Origin":"http://testserver"}).status_code==404
        assert alice.get("/api/v1/jobs/"+job).status_code==200
        assert alice.get("/api/v1/jobs/"+job+"/assets/"+asset).status_code==200
        assert alice.get("/demo/api/admin/evaluations").status_code==403
        assert alice.get("/demo/api/admin/evaluations.csv").status_code==403
        # Must not permit evaluation before the real B0 Job is completed.
        early=alice.post("/demo/api/evaluations",json={"job_id":job,"scenario_id":"UC-01",
                      "category":"ui_ux","score":5},headers={"Origin":"http://testserver"})
        assert early.status_code==409
        finish(alice,job)
        assert alice.get("/api/v1/jobs/"+job+"/artifacts/final").status_code==200
        r=alice.post("/demo/api/evaluations",json={"job_id":job,"scenario_id":"UC-01",
                      "category":"ui_ux","score":4,"comment":"레이아웃 개선"},
                      headers={"Origin":"http://testserver"})
        assert r.status_code==200,r.text
        assert len(r.json()["artifact_sha256"])==64
        update=alice.post("/demo/api/evaluations",json={"job_id":job,"scenario_id":"UC-01",
                       "category":"ui_ux","score":5},headers={"Origin":"http://testserver"})
        assert update.status_code==200 and update.json()["revision"]==2
        events=alice.get("/demo/api/jobs/"+job+"/events").json()
        assert len(events["events"])==7
        assert all(ev["mode"]=="MOCK" and ev["duration_ms"]>=0 for ev in events["events"])
        assert events["provider_elapsed_ms"] is None
        assert pm.get("/demo/api/admin/evaluations").json()["n"]==1
        assert pm.get("/demo/api/admin/evaluations.csv").status_code==200
        assert bob.get("/demo/api/jobs/"+job+"/evaluations").status_code==404
        assert alice.delete("/demo/api/session",headers={"Origin":"http://testserver"}).status_code==200
        assert alice.get("/api/v1/jobs/"+job).status_code==401


def test_persistence_without_session_leak(setup):
    app,codes=setup
    with TestClient(app) as user:
        assert login(user,codes["alice"]).status_code==200
        created=create(user)
        assert created.status_code==201
        jid=created.json()["job_id"]
    # Same backing database: fresh FastAPI process reconstructs durable ACL
    from demo_staging.app import make_demo_app
    root=app.state.demo_ledger.path.parent
    new=make_demo_app(root,root.parent/"invites.json",
                      root.parent/"dist",secure_cookie=False,code_sha="test123")
    with TestClient(new) as user2:
        assert login(user2,codes["alice"]).status_code==200
        assert user2.get("/api/v1/jobs/"+jid).status_code==200


def test_login_no_raw_code_stored_and_unknown_actor_denied(setup):
    app,codes=setup
    with TestClient(app) as client:
        assert login(client,codes["alice"]).status_code==200
    content=app.state.demo_ledger.path.read_bytes()
    assert codes["alice"].encode() not in content
    assert app.state.demo_mode=="MOCK_ONLY"
