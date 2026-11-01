from fastapi.testclient import TestClient
from tests.demo_live.test_http_gateway import setup

def test_exact_owner_favicon_static_and_public_contract_unchanged(tmp_path):
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
