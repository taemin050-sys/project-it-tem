"""Provisional E2E mock contracts; no external AI calls or real ad claims."""

from io import BytesIO

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image

from src.serving.main import create_app


def png(color):
    buffer = BytesIO()
    Image.new("RGB", (30, 20), color).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def client_and_root(tmp_path):
    root = tmp_path / "jobs"
    with TestClient(create_app(storage_root=root)) as client:
        yield client, root


def new_job(client):
    response = client.post("/api/v1/jobs", files=[
        ("product_images", ("a.png", png("red"), "image/png")),
        ("product_images", ("b.png", png("blue"), "image/png")),
    ])
    assert response.status_code == 201, response.text
    return response.json()["job_id"]


def post(client, job_id, action, json=None):
    return client.post(f"/api/v1/jobs/{job_id}/{action}", json=json)


def to_copy(client, job_id):
    first = post(client, job_id, "mock/plan", {"brand_name": "테스트브랜드", "product_name": "보습 크림"})
    assert first.status_code == 200, first.text
    second = post(client, job_id, "mock/copy")
    assert second.status_code == 200, second.text


def to_image(client, job_id):
    to_copy(client, job_id)
    assert post(client, job_id, "approvals/copy", {"approved": True}).status_code == 200
    assert post(client, job_id, "mock/image").status_code == 200


def test_full_e2e_and_independent_artifacts(client_and_root):
    client, root = client_and_root
    job_id = new_job(client)
    assert client.get(f"/api/v1/jobs/{job_id}").json()["status"] == "INPUTS_VALIDATED"
    to_image(client, job_id)
    assert post(client, job_id, "approvals/image", {"approved": True}).json()["status"] == "IMAGE_APPROVED"
    composed = post(client, job_id, "mock/compose")
    assert composed.status_code == 200, composed.text
    job = composed.json()
    assert job["status"] == "COMPLETED"
    assert job["plan"]["mock"] is True
    assert job["plan"]["research_performed"] is False
    assert job["copy_candidate"]["compliance_checked"] is False
    assert job["image_candidate"]["mock"] is True
    assert job["final_output"]["format"] == "PNG"
    assert set(job["artifacts"]) == {"plan", "copy", "image", "final", "caption"}
    for kind in job["artifacts"]:
        download = client.get(f"/api/v1/jobs/{job_id}/artifacts/{kind}")
        assert download.status_code == 200, kind
        assert len(download.content) == job["artifacts"][kind]["size_bytes"]
    assert b'"research_performed": false' in client.get(f"/api/v1/jobs/{job_id}/artifacts/plan").content
    assert "테스트브랜드" in client.get(f"/api/v1/jobs/{job_id}/artifacts/caption").content.decode("utf-8")
    for kind in ("image", "final"):
        with Image.open(BytesIO(client.get(f"/api/v1/jobs/{job_id}/artifacts/{kind}").content)) as img:
            assert img.size == (1080, 1350)
            assert img.format == "PNG"
    assert (root / job_id / "job.json").is_file()


def test_restart_job_and_download(client_and_root):
    client, root = client_and_root
    job_id = new_job(client)
    to_copy(client, job_id)
    with TestClient(create_app(storage_root=root)) as second:
        state = second.get(f"/api/v1/jobs/{job_id}").json()
        assert state["status"] == "COPY_REVIEW_REQUIRED"
        assert second.get(f"/api/v1/jobs/{job_id}/artifacts/copy").status_code == 200
        assert post(second, job_id, "approvals/copy", {"approved": True}).status_code == 200


@pytest.mark.parametrize("action,body", [
    ("mock/copy", None),
    ("mock/image", None),
    ("mock/compose", None),
    ("approvals/copy", {"approved": True}),
    ("approvals/image", {"approved": True}),
])
def test_cannot_skip_initial_stage(client_and_root, action, body):
    client, _ = client_and_root
    job_id = new_job(client)
    response = post(client, job_id, action, body)
    assert response.status_code == 409
    assert client.get(f"/api/v1/jobs/{job_id}").json()["status"] == "INPUTS_VALIDATED"


def test_image_requires_copy_approval(client_and_root):
    client, _ = client_and_root
    job_id = new_job(client)
    to_copy(client, job_id)
    assert post(client, job_id, "mock/image").status_code == 409
    assert post(client, job_id, "mock/compose").status_code == 409
    assert client.get(f"/api/v1/jobs/{job_id}/artifacts/image").status_code == 404


def test_composition_requires_image_approval(client_and_root):
    client, _ = client_and_root
    job_id = new_job(client)
    to_image(client, job_id)
    assert post(client, job_id, "mock/compose").status_code == 409
    assert client.get(f"/api/v1/jobs/{job_id}/artifacts/final").status_code == 404


def test_copy_rejection_terminal(client_and_root):
    client, _ = client_and_root
    job_id = new_job(client)
    to_copy(client, job_id)
    response = post(client, job_id, "approvals/copy", {"approved": False})
    assert response.json()["status"] == "COPY_REJECTED"
    assert post(client, job_id, "mock/image").status_code == 409
    assert post(client, job_id, "approvals/copy", {"approved": True}).status_code == 409


def test_image_rejection_terminal(client_and_root):
    client, _ = client_and_root
    job_id = new_job(client)
    to_image(client, job_id)
    response = post(client, job_id, "approvals/image", {"approved": False})
    assert response.json()["status"] == "IMAGE_REJECTED"
    assert post(client, job_id, "mock/compose").status_code == 409


def test_duplicate_generation_and_approvals_blocked(client_and_root):
    client, _ = client_and_root
    job_id = new_job(client)
    assert post(client, job_id, "mock/plan", {"brand_name": "A", "product_name": "B"}).status_code == 200
    assert post(client, job_id, "mock/plan", {"brand_name": "A", "product_name": "B"}).status_code == 409
    assert post(client, job_id, "mock/copy").status_code == 200
    assert post(client, job_id, "mock/copy").status_code == 409
    assert post(client, job_id, "approvals/copy", {"approved": True}).status_code == 200
    assert post(client, job_id, "approvals/copy", {"approved": True}).status_code == 409


@pytest.mark.parametrize("body", [
    {"brand_name": "  ", "product_name": "크림"},
    {"brand_name": "A", "product_name": "\n"},
    {"brand_name": "A", "product_name": "x" * 101},
    {"brand_name": "A", "product_name": "B", "unexpected": 1},
])
def test_mock_plan_validates_request(client_and_root, body):
    client, _ = client_and_root
    job_id = new_job(client)
    assert post(client, job_id, "mock/plan", body).status_code == 422
    assert client.get(f"/api/v1/jobs/{job_id}").json()["status"] == "INPUTS_VALIDATED"


def test_missing_job_or_artifact(client_and_root):
    client, _ = client_and_root
    job_id = new_job(client)
    assert post(client, "f" * 32, "mock/plan", {"brand_name": "a", "product_name": "b"}).status_code == 404
    assert client.get(f"/api/v1/jobs/{job_id}/artifacts/unknown").status_code == 404
    assert client.get(f"/api/v1/jobs/{job_id}/artifacts/final").status_code == 404


def test_missing_font_fail_closed(client_and_root, monkeypatch):
    import src.serving.mock_workflow as workflow
    client, _ = client_and_root
    job_id = new_job(client)
    to_image(client, job_id)
    post(client, job_id, "approvals/image", {"approved": True})
    def missing_font(_size):
        raise HTTPException(status_code=503, detail="Korean font missing")
    monkeypatch.setattr(workflow, "_korean_font", missing_font)
    assert post(client, job_id, "mock/compose").status_code == 503
    state = client.get(f"/api/v1/jobs/{job_id}").json()
    assert state["status"] == "IMAGE_APPROVED"
    assert "final" not in state.get("artifacts", {})
