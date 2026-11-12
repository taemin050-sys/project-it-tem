import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from demo_staging.app import make_demo_app
from src.text_generation.schemas import ImagePromptOutput
from tests.demo_live.test_live_contracts import safe_copy,sample_input


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
        assert a.get("/demo/api/live/jobs/"+jid+"/artifacts/final").status_code==409
        assert b.get("/demo/api/live/jobs/"+jid+"/artifacts/final").status_code==404

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


def test_live_candidate_get_pins_bytes_and_rejects_stale_sha(tmp_path,monkeypatch):
    app,codes=setup(tmp_path)
    with TestClient(app) as owner,TestClient(app) as peer:
        login(owner,codes["alice"])
        login(peer,codes["bob"])
        uploaded=owner.post("/api/v1/jobs",files=[
            ("product_images",("one.png",photo((120,130,140)),"image/png")),
            ("product_images",("two.png",photo((150,160,170)),"image/png")),
        ],headers={"Origin":"http://testserver"})
        assert uploaded.status_code==201
        jid=uploaded.json()["job_id"]
        flow=app.state.live_pipeline
        flow.prepare("alice",jid,sample_input())
        analysis,research,copy,prompt=safe_copy()
        # Seed a synthetic review candidate directly. No Provider calls.
        stage=flow.state.store_text("alice",jid,analysis,research,copy,mode="LIVE")
        flow.state.approve_copy("alice",jid,stage["generation"],stage["review_sha"])
        flow.state.store_prompt("alice",jid,ImagePromptOutput.model_validate(prompt))
        candidate=photo((160,190,195))
        replacement=photo((12,34,56))
        candidate_sha=hashlib.sha256(candidate).hexdigest()
        replacement_sha=hashlib.sha256(replacement).hexdigest()
        path=flow.image_path(jid)
        path.parent.mkdir(parents=True)
        path.write_bytes(candidate)
        flow.state.store_image_candidate("alice",jid,candidate_sha)

        url=f"/demo/api/live/jobs/{jid}/artifacts/candidate"
        assert owner.get(url).content==candidate
        assert owner.get(url,params={"sha256":replacement_sha}).status_code==409
        assert peer.get(url,params={"sha256":candidate_sha}).status_code==404

        read_bytes=Path.read_bytes
        def replace_after_read(target):
            payload=read_bytes(target)
            if target==path:
                target.write_bytes(replacement)
            return payload
        monkeypatch.setattr(Path,"read_bytes",replace_after_read)

        verified=owner.get(url,params={"sha256":candidate_sha})
        assert verified.status_code==200
        assert verified.headers["content-type"]=="image/png"
        assert verified.content==candidate
        assert owner.get(url,params={"sha256":candidate_sha}).status_code==503
