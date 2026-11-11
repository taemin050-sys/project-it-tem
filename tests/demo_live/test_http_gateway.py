import hashlib
import json

from fastapi.testclient import TestClient
from PIL import Image

from demo_staging.app import make_demo_app
from tests.demo_live.test_live_contracts import sample_input


def setup(tmp_path):
    dist=tmp_path/"dist"
    (dist/"assets").mkdir(parents=True)
    (dist/"index.html").write_text("<html>no static secrets</html>")
    codes={"alice":"one-off-alice-evaluation-invite-secret-2026",
           "bob":"one-off-bob-evaluation-invite-secret-2026"}
    registry={
        name:{"role":"evaluator","digest":hashlib.sha256(code.encode()).hexdigest()}
        for name,code in codes.items()
    }
    invites=tmp_path/"invites.json"
    invites.write_text(json.dumps(registry))
    return make_demo_app(tmp_path/"runtime",invites,dist,secure_cookie=False),codes

def photo(color):
    from io import BytesIO
    b=BytesIO();Image.new("RGB",(135,175),color).save(b,"PNG")
    return b.getvalue()

def login(c,code):
    r=c.post("/demo/api/session",json={"invite_code":code},
             headers={"Origin":"http://testserver"})
    assert r.status_code==200,r.text

def test_provisional_live_contract_is_private_11_b0_routes_unchanged(tmp_path):
    app,codes=setup(tmp_path)
    http=app.openapi()["paths"]
    b0={(m,p) for p,item in http.items() if p.startswith("/api/v1/jobs")
         for m in item if m in {"get","post"}}
    assert len(b0)==10
    assert "get" in http["/health"]  # 10 Job operations + health = 11
    with TestClient(app) as a,TestClient(app) as b:
        assert a.get("/demo/api/live/capabilities").status_code==401
        login(a,codes["alice"]);login(b,codes["bob"])
        caps=a.get("/demo/api/live/capabilities")
        assert caps.status_code==200 and caps.json()["live_enabled"] is False
        assert caps.json()["mock_fallback"] is False
        created=a.post("/api/v1/jobs",files=[
            ("product_images",("one.png",photo((120,130,140)),"image/png")),
            ("product_images",("two.png",photo((150,160,170)),"image/png"))
        ],headers={"Origin":"http://testserver"})
        assert created.status_code==201,created.text
        jid=created.json()["job_id"]
        payload=sample_input()
        bad=a.post("/demo/api/live/jobs/"+jid+"/input",json=payload,
                   headers={"Origin":"http://malicious.invalid"})
        assert bad.status_code==403
        impossible=b.post("/demo/api/live/jobs/"+jid+"/input",json=payload,
                          headers={"Origin":"http://testserver"})
        assert impossible.status_code==404
        accepted=a.post("/demo/api/live/jobs/"+jid+"/input",json=payload,
                        headers={"Origin":"http://testserver"})
        assert accepted.status_code==200,accepted.text
        assert accepted.json()["state"]=="INPUT_STORED"
        assert "ordered_asset_hashes" not in accepted.json()
        assert "product" not in accepted.json()
        assert "research_display" not in accepted.json()
        assert b.get("/demo/api/live/jobs/"+jid).status_code==404
        assert a.get("/demo/api/live/jobs/"+jid).status_code==200
        for name in ("queue-text","queue-prompt","queue-image"):
            r=a.post("/demo/api/live/jobs/"+jid+"/"+name,
                     headers={"Origin":"http://testserver"})
            assert r.status_code==423
        for kind in ("final","caption","receipt"):
            # An authorized owner cannot export incomplete or fake output.
            assert a.get("/demo/api/live/jobs/"+jid+"/artifacts/"+kind).status_code==409
            # An unrelated Actor must never see image bytes or receipt.
            assert b.get("/demo/api/live/jobs/"+jid+"/artifacts/"+kind).status_code==404
        assert a.get("/demo/api/live/jobs/"+jid+"/artifacts/unknown").status_code==409

def test_live_endpoint_no_unprotected_mutation_or_paid_approvals(tmp_path):
    app,codes=setup(tmp_path)
    with TestClient(app) as c:
        login(c,codes["alice"])
        jid="d"*32
        assert c.post("/demo/api/live/jobs/"+jid+"/approve-copy",
                 json={"expected_generation":1,"expected_review_sha":"x"},
                 headers={"Origin":"http://testserver"}).status_code==404
        assert c.post("/demo/api/live/jobs/"+jid+"/input",json={"product":{}},
                 headers={"Origin":"http://testserver"}).status_code in {404,422}
        assert c.get("/demo/api/live/tasks/"+"f"*32).status_code==404
