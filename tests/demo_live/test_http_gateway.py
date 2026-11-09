import hashlib
import json

from fastapi.testclient import TestClient
from PIL import Image
import pytest

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


def test_approved_a_export_publishes_three_local_font_outputs_together(tmp_path, monkeypatch):
    from io import BytesIO
    from pathlib import Path

    from PIL import ImageChops

    from demo_staging.live import pipeline as live_pipeline
    from src.image_generation import make_a_template
    from src.text_generation.schemas import (
        AdCopyOutput, ImagePromptOutput, ProductAnalysisResult, ResearchResult,
    )
    from tests.demo_live.test_live_contracts import safe_copy
    from tests.demo_live.test_pipeline import png

    font = Path(__file__).resolve().parents[1] / "image_generation/fixtures/fonts/NanumGothic-Regular.ttf"
    monkeypatch.setenv("IT_TEM_LIVE_KOREAN_FONT", str(font))
    app, codes = setup(tmp_path)
    origin = {"Origin": "http://testserver"}
    with TestClient(app) as owner, TestClient(app) as other:
        login(owner, codes["alice"])
        login(other, codes["bob"])
        upload = owner.post("/api/v1/jobs", files=[
            ("product_images", ("a.png", photo((110, 150, 120)), "image/png")),
            ("product_images", ("b.png", photo((120, 140, 140)), "image/png")),
        ], headers=origin)
        assert upload.status_code == 201
        job_id = upload.json()["job_id"]
        flow = app.state.live_pipeline
        monkeypatch.setattr(flow, "_guarded", lambda *args, **kwargs: pytest.fail("Unexpected provider dispatch"))
        flow.prepare("alice", job_id, sample_input())
        analysis, research, copy, prompt = safe_copy()
        snapshot = flow.state.store_text("alice", job_id, ProductAnalysisResult.model_validate(analysis),
            ResearchResult.model_validate(research), AdCopyOutput.model_validate(copy), mode="LIVE")
        flow.state.approve_copy("alice", job_id, snapshot["generation"], snapshot["review_sha"])
        flow.state.store_prompt("alice", job_id, ImagePromptOutput.model_validate(prompt))
        candidate = png((255, 228, 230), size=(1152, 1440))
        candidate_sha = hashlib.sha256(candidate).hexdigest()
        original_write = live_pipeline.atomic_write
        original_write(flow.image_path(job_id), candidate)
        flow.state.store_image_candidate("alice", job_id, candidate_sha)
        url = f"/demo/api/live/jobs/{job_id}"
        _, layout = make_a_template()
        body = {"layout": layout.model_dump(mode="json", exclude={"canvas_size"}), "font_variants": True}
        assert owner.post(f"{url}/compose", json=body, headers=origin).status_code == 409
        approval = owner.post(f"{url}/approve-image", json={"image_sha": candidate_sha}, headers=origin)
        assert approval.status_code == 200

        def fail_last_output(path, data):
            if path.name == "font-myeongjo.png":
                raise OSError("fixture write failure")
            original_write(path, data)

        monkeypatch.setattr(live_pipeline, "atomic_write", fail_last_output)
        failed = owner.post(f"{url}/compose", json=body, headers=origin)
        assert failed.status_code == 422, failed.text
        pending = owner.get(url).json()
        assert pending["state"] == "IMAGE_APPROVED"
        assert "font_variants" not in pending
        assert owner.get(f"{url}/artifacts/font-round").status_code == 409

        monkeypatch.setattr(live_pipeline, "atomic_write", original_write)
        finished = owner.post(f"{url}/compose", json=body, headers=origin)
        assert finished.status_code == 200, finished.text
        result = finished.json()
        assert result["state"] == "COMPLETED"
        assert result["image_sha"] == candidate_sha and result["copy_sha"] == snapshot["copy_sha"]
        variants = result["font_variants"]
        assert [variant["preset"] for variant in variants] == ["gothic", "round", "myeongjo"]
        assert variants[0]["sha256"] == result["final_sha"]
        assert owner.get(url).json()["font_variants"] == variants
        assert len({variant["sha256"] for variant in variants}) == 3
        outputs = []
        for variant in variants:
            saved = owner.get(variant["download_url"])
            assert saved.status_code == 200
            assert saved.headers["content-type"] == "image/png"
            assert hashlib.sha256(saved.content).hexdigest() == variant["sha256"]
            assert other.get(variant["download_url"]).status_code == 404
            with Image.open(BytesIO(saved.content)) as image:
                assert image.format == "PNG" and image.size == (1080, 1350)
                outputs.append(image.convert("RGB"))
        left, top, right, bottom = layout.text_regions["headline"].pixels()
        for output in outputs[1:]:
            box = ImageChops.difference(outputs[0], output).getbbox()
            assert box and left <= box[0] < box[2] <= right and top <= box[1] < box[3] <= bottom
        assert owner.get(f"{url}/artifacts/caption").status_code == 200
        assert flow.image_path(job_id).read_bytes() == candidate
        with flow.cost.connect() as db:
            assert db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0
        (flow.image_path(job_id).parent / "font-round.png").write_bytes(b"tampered")
        assert owner.get(f"{url}/artifacts/font-round").status_code == 503
