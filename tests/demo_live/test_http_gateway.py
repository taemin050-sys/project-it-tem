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


def test_live_performance_prices_saved_image_usage_only(tmp_path):
    from demo_staging.live_safety import AttemptLedger

    app, codes = setup(tmp_path)
    origin = {"Origin": "http://testserver"}
    with TestClient(app) as owner, TestClient(app) as other:
        login(owner, codes["alice"])
        login(other, codes["bob"])
        created = owner.post("/api/v1/jobs", files=[
            ("product_images", ("one.png", photo((120, 130, 140)), "image/png")),
            ("product_images", ("two.png", photo((150, 160, 170)), "image/png")),
        ], headers=origin)
        assert created.status_code == 201, created.text
        job_id = created.json()["job_id"]
        url = f"/demo/api/live/jobs/{job_id}"
        assert owner.post(f"{url}/input", json=sample_input(), headers=origin).status_code == 200

        ledger = AttemptLedger(app.state.live_pipeline.cost.filename,
                               live_enabled=True, monitoring_only=True)
        model = "gpt-image-2.5-sunburst-2026-09-08"
        usage = {"input_tokens": 6491, "input_text_tokens": 683,
                 "input_image_tokens": 5808, "output_tokens": 418, "total_tokens": 6909}
        cases = [
            ("image", model, usage, "0.062419"),
            ("image", "gpt-image-2.6-sunburst",
             {"input_tokens": 4947, "input_text_tokens": 1847, "input_image_tokens": 3100,
              "output_tokens": 1212, "total_tokens": 6159}, "0.070395"),
            ("image", model, {**usage, "input_image_tokens": None}, None),
            ("image", model, {**usage, "input_image_tokens": 5807}, None),
            ("image", model, {**usage, "output_tokens": True}, None),
            ("image", "unknown-image-model", usage, None),
            ("image", "gpt-image-2-2026-04-21", dict.fromkeys(usage, 0), "0.000000"),
            ("copy", "gpt-6-luna", usage, None),
        ]
        attempt_ids = []
        for index, (stage, model_id, counts, _) in enumerate(cases):
            record = ledger.reserve(actor="alice", role="live_operator", job_id=job_id,
                                    stage=stage, payload={"index": index},
                                    estimated_usd=0, pm_authorized=True)
            attempt_id = record["id"]
            attempt_ids.append(attempt_id)
            ledger.dispatch_intent(attempt_id)
            ledger.confirm_usage_unpriced(attempt_id, {
                "provider_response_id": f"req_test_{index}", "model": model_id,
                "usage": counts, "billing_status": "UNPRICED_RESERVATION_HELD",
            })
        for state in ("reserved", "unknown"):
            pending = ledger.reserve(actor="alice", role="live_operator", job_id=job_id,
                                     stage="image", payload={"state": state},
                                     estimated_usd=0, pm_authorized=True)
            if state == "unknown":
                ledger.dispatch_intent(pending["id"])
                ledger.mark_billing_unknown(pending["id"])

        assert other.get(f"{url}/performance").status_code == 404
        result = owner.get(f"{url}/performance")
        assert result.status_code == 200, result.text
        body = result.json()
        assert body["image_cost_summary"] == {
            "known_estimated_cost_usd": "0.132814",
            "estimated_total_usd": "0.444909",
            "priced_attempt_count": 3,
            "unpriced_attempt_count": 5,
        }
        comparison = body["image_savings_estimate"]
        assert comparison["reference_cost_usd"] == "0.062419"
        assert comparison["direct_attempt_count"] == 4
        assert comparison["direct_baseline_stages"] == [
            {"label": "초기 생성", "attempt_count": 1},
            {"label": "프롬프트 보강 후 재생성", "attempt_count": 1},
            {"label": "기존 이미지 편집 비교", "attempt_count": 1},
            {"label": "팀 피드백 반영 수정", "attempt_count": 1},
        ]
        assert comparison["dimension_experiment"] == {
            "variant_count": 8,
            "initial_attempt_count": 8,
            "refinement_attempt_count": 8,
            "total_tokens": 97022,
            "estimated_cost_usd": "1.297805",
        }
        assert comparison["service_attempt_count"] == 8
        assert comparison["service_attempt_count_is_estimated"] is False
        assert comparison["direct_estimated_cost_usd"] == "0.249676"
        assert comparison["service_estimated_cost_usd"] == "0.499352"
        assert comparison["estimated_savings_usd"] == "-0.249676"
        assert comparison["estimated_savings_tokens"] == -27636
        attempts = body["provider_attempts"]
        assert len(attempts) == len(cases) + 2
        for attempt, (stage, model_id, counts, expected) in zip(attempts, cases):
            assert attempt["stage"] == stage
            assert attempt["model"] == model_id
            assert attempt["usage"] == counts
            assert attempt["actual_cost_usd"] is None
            if stage == "image":
                assert attempt["estimated_cost_usd"] == expected
                assert attempt["estimate_rate_version"] == (
                    "openai-images-standard-uncached-2026-11-09-v1" if expected is not None else None
                )
            else:
                assert "estimated_cost_usd" not in attempt
        assert all(ledger.inspect(attempt_id)["cost_microusd"] is None for attempt_id in attempt_ids)
