from fastapi.testclient import TestClient
from tests.demo_live.test_http_gateway import setup

def test_exact_owner_favicon_static_and_public_contract_unchanged(tmp_path):
    # The static directory is created before app setup in the integration app;
    # a test instance can also mount the exact public preview files explicitly.
    app,_=setup(tmp_path)
    target=tmp_path/"dist"/"favicon.svg"
    target.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>',encoding="utf-8")
    with TestClient(app) as client:
        r=client.get("/favicon.svg")
        assert r.status_code==200
        assert r.headers["content-type"].startswith("image/svg+xml")
        assert r.content==target.read_bytes()
        assert client.get("/nothing.svg").status_code==404
        assert client.get("/api/v1/jobs").status_code!=200
    assert "/favicon.svg" not in app.openapi()["paths"]

def test_owner_landing_mock_previews_are_static_only(tmp_path):
    from demo_staging.app import make_demo_app
    import hashlib,json
    from pathlib import Path
    dist=tmp_path/"owner-dist"
    (dist/"assets").mkdir(parents=True)
    (dist/"mock").mkdir()
    (dist/"index.html").write_text("<html>owner</html>")
    for name in ("ad_moss.svg","ad_beige.svg","ad_tile.svg"):
        (dist/"mock"/name).write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
    invites=tmp_path/"invites.json"
    invites.write_text(json.dumps({"alice":{"role":"evaluator",
        "digest":hashlib.sha256(b"example-test-invite-not-secret").hexdigest()}}))
    app=make_demo_app(tmp_path/"runtime-public",invites,dist,secure_cookie=False)
    with TestClient(app) as client:
        for name in ("ad_moss.svg","ad_beige.svg","ad_tile.svg"):
            r=client.get("/mock/"+name)
            assert r.status_code==200 and r.headers["content-type"].startswith("image/svg+xml")
        assert client.get("/mock/does-not-exist.svg").status_code==404
        assert client.get("/mock/../config/openai.env").status_code==404
        assert client.get("/demo/api/live/shared").status_code==401
    assert "/mock" not in app.openapi()["paths"]
