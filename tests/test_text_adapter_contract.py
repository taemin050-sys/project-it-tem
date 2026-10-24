"""No paid calls. Validate the P4A text-transport and P3 compatibility contract."""
from __future__ import annotations

import os
from io import BytesIO

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image

from src.serving import text_adapter
from src.serving.main import create_app


def png(color: str):
    buf = BytesIO()
    Image.new("RGB", (48, 48), color).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(storage_root=tmp_path / "jobs")) as c:
        yield c


def new_job(client):
    r = client.post("/api/v1/jobs", files=[
        ("product_images", ("one.png", png("red"), "image/png")),
        ("product_images", ("two.png", png("blue"), "image/png")),
    ])
    assert r.status_code == 201, r.text
    return r.json()["job_id"]


def test_capabilities_non_sensitive(client, monkeypatch):
    monkeypatch.delenv("IT_TEM_ENABLE_BILLABLE_TEXT_CALLS", raising=False)
    data = client.get("/api/v1/capabilities").json()
    assert data["api_contract"] == "PROVISIONAL"
    assert data["text_provider_ready"] is False
    assert data["image_provider_ready"] is False
    assert "OPENAI_API_KEY" not in str(data)


def test_live_text_disabled_by_default(client, monkeypatch):
    monkeypatch.delenv("IT_TEM_ENABLE_BILLABLE_TEXT_CALLS", raising=False)
    jid = new_job(client)
    url = f"/api/v1/jobs/{jid}/ai/plan"
    result = client.post(url, json={"brand_name": "브랜드", "product_name": "크림"})
    assert result.status_code == 503
    assert result.json()["detail"] == "TEXT_PROVIDER_NOT_ENABLED"
    assert client.get(f"/api/v1/jobs/{jid}").json()["status"] == "INPUTS_VALIDATED"


def test_nonblank_facts_required(client):
    jid = new_job(client)
    bad = client.post(f"/api/v1/jobs/{jid}/ai/plan", json={
        "brand_name": "브랜드", "product_name": "크림", "product_facts": [" "]})
    assert bad.status_code == 422


def test_ai_plan_copy_and_mock_approval_unchanged(client, monkeypatch):
    jid = new_job(client)
    calls = []

    def fake_generator(*, kind, instructions, user_input):
        calls.append((kind, user_input))
        if kind == "plan":
            return {"audience": "일상 보습 고객 (가설)", "direction": "일상 루틴", "risk_flags": []}
        return {"text": "브랜드 크림, 일상의 보습 루틴", "risk_flags": []}

    monkeypatch.setattr(text_adapter, "generate_structured_text", fake_generator)
    monkeypatch.setattr(text_adapter, "configured_model", lambda: "test-injected-model")
    plan = client.post(f"/api/v1/jobs/{jid}/ai/plan", json={
        "brand_name": "브랜드", "product_name": "크림", "product_facts": ["보습 크림"]})
    assert plan.status_code == 200, plan.text
    assert plan.json()["plan"]["research_performed"] is False
    assert plan.json()["plan"]["mock"] is False
    assert plan.json()["plan"]["product_facts_user_supplied_unverified"] == ["보습 크림"]
    assert client.post(f"/api/v1/jobs/{jid}/mock/image").status_code == 409
    copy = client.post(f"/api/v1/jobs/{jid}/ai/copy")
    assert copy.status_code == 200, copy.text
    assert copy.json()["copy_candidate"]["compliance_checked"] is False
    assert copy.json()["copy_candidate"]["mock"] is False
    assert copy.json()["status"] == "COPY_REVIEW_REQUIRED"
    assert client.post(f"/api/v1/jobs/{jid}/mock/image").status_code == 409
    assert client.post(f"/api/v1/jobs/{jid}/approvals/copy", json={"approved": True}).status_code == 200
    image = client.post(f"/api/v1/jobs/{jid}/mock/image")
    assert image.status_code == 200, image.text
    assert image.json()["image_candidate"]["mock"] is True
    assert [c[0] for c in calls] == ["plan", "copy"]


def test_ai_duplicate_blocked_without_extra_provider_call(client, monkeypatch):
    jid = new_job(client)
    calls = []

    def fake_generator(**kwargs):
        calls.append(kwargs)
        return {"audience": "A", "direction": "D", "risk_flags": []}

    monkeypatch.setattr(text_adapter, "generate_structured_text", fake_generator)
    monkeypatch.setattr(text_adapter, "configured_model", lambda: "test")
    path = f"/api/v1/jobs/{jid}/ai/plan"
    body = {"brand_name": "A", "product_name": "B"}
    assert client.post(path, json=body).status_code == 200
    assert client.post(path, json=body).status_code == 409
    assert len(calls) == 1


def test_provider_fail_does_not_change_job(client, monkeypatch):
    jid = new_job(client)
    def failure(**kwargs):
        raise HTTPException(status_code=502, detail="TEXT_PROVIDER_FAILED_STATE_UNCHANGED")
    monkeypatch.setattr(text_adapter, "generate_structured_text", failure)
    result = client.post(f"/api/v1/jobs/{jid}/ai/plan", json={"brand_name": "A", "product_name": "B"})
    assert result.status_code == 502
    data = client.get(f"/api/v1/jobs/{jid}").json()
    assert data["status"] == "INPUTS_VALIDATED"
    assert "plan" not in data.get("artifacts", {})


@pytest.mark.parametrize("payload,kind", [
    ({"audience": "A", "direction": "B", "risk_flags": []}, "it_tem_plan_v1"),
    ({"text": "화장품 광고", "risk_flags": ["검토 필요"]}, "it_tem_copy_v1"),
])
def test_provider_output_valid(payload, kind):
    assert text_adapter._validate_generated(payload, kind) == payload


@pytest.mark.parametrize("payload,kind", [
    ({"audience": "A", "direction": "B", "risk_flags": [], "extra": True}, "it_tem_plan_v1"),
    ({"text": "", "risk_flags": []}, "it_tem_copy_v1"),
    ({"text": "X", "risk_flags": "x"}, "it_tem_copy_v1"),
])
def test_provider_output_invalid(payload, kind):
    with pytest.raises(ValueError):
        text_adapter._validate_generated(payload, kind)


def test_mock_still_works(client):
    jid = new_job(client)
    resp = client.post(f"/api/v1/jobs/{jid}/mock/plan", json={"brand_name": "A", "product_name": "B"})
    assert resp.status_code == 200
    assert resp.json()["plan"]["mock"] is True


def test_sdk_request_shape_without_network(monkeypatch):
    """Verify bounded Responses call format using an injected fake SDK."""
    import sys
    from types import SimpleNamespace
    seen = {}

    class FakeResponses:
        def create(self, **kwargs):
            seen.update(kwargs)
            return SimpleNamespace(status="completed", output_text='{"text":"카피","risk_flags":[]}')

    class FakeOpenAI:
        def __init__(self, **kwargs):
            seen["client_config"] = kwargs
            self.responses = FakeResponses()

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    monkeypatch.setenv("IT_TEM_ENABLE_BILLABLE_TEXT_CALLS", "YES")
    monkeypatch.setenv("IT_TEM_TEXT_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "fake-only-for-mock-test")
    monkeypatch.setenv("IT_TEM_TEXT_MODEL", "example-structured-output-model")
    result = text_adapter.generate_structured_text(instructions="Return JSON", user_input={"product":"A"}, kind="copy")
    assert result["text"] == "카피"
    assert seen["store"] is False
    assert seen["max_output_tokens"] == 600
    assert seen["text"]["format"]["strict"] is True
    assert seen["client_config"]["max_retries"] == 0
