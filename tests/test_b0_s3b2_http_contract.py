"""S3-B.2: explicit B0 HTTP status and binary compatibility matrix.

Uses only the current P2/P3 FastAPI TestClient, with a disposable JobStore.
No public endpoint, model call, or production HTTP behavior modification.
"""
from __future__ import annotations

from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from src.serving.main import create_app


def png(color: tuple[int, int, int]) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (40, 40), color).save(buffer, "PNG")
    return buffer.getvalue()


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(storage_root=tmp_path / "jobs")) as instance:
        yield instance


def upload(client, *, products=2, references=0):
    files = [
        ("product_images", (f"p{i}.png", png((i * 31, 20, 11)), "image/png"))
        for i in range(products)
    ]
    files += [
        ("reference_images", (f"r{i}.png", png((0, i * 37, 27)), "image/png"))
        for i in range(references)
    ]
    return client.post("/api/v1/jobs", files=files)


def new_job(client):
    result = upload(client)
    assert result.status_code == 201, result.text
    return result.json()["job_id"]


def invoke(client, job_id, suffix, body=None):
    return client.post(f"/api/v1/jobs/{job_id}/{suffix}", json=body)


def test_public_openapi_operations_exactly_11(client):
    s = client.get("/openapi.json")
    assert s.status_code == 200
    methods = {
        (method.upper(), path)
        for path, ops in s.json()["paths"].items()
        for method in ops
        if method in {"get", "post", "delete", "put", "patch"}
    }
    expected = {
        ("GET", "/health"),
        ("POST", "/api/v1/jobs"),
        ("GET", "/api/v1/jobs/{job_id}"),
        ("GET", "/api/v1/jobs/{job_id}/assets/{asset_id}"),
        ("POST", "/api/v1/jobs/{job_id}/mock/plan"),
        ("POST", "/api/v1/jobs/{job_id}/mock/copy"),
        ("POST", "/api/v1/jobs/{job_id}/approvals/copy"),
        ("POST", "/api/v1/jobs/{job_id}/mock/image"),
        ("POST", "/api/v1/jobs/{job_id}/approvals/image"),
        ("POST", "/api/v1/jobs/{job_id}/mock/compose"),
        ("GET", "/api/v1/jobs/{job_id}/artifacts/{kind}"),
    }
    assert methods == expected
    assert all("/ai/" not in path for _, path in methods)


@pytest.mark.parametrize("n_products,n_refs", [(2, 0), (3, 2), (5, 5)])
def test_valid_counts_preserve_asset_order_and_content(client, n_products, n_refs):
    result = upload(client, products=n_products, references=n_refs)
    assert result.status_code == 201
    result = result.json()
    assert [a["role"] for a in result["assets"]] == ["product"] * n_products + ["reference"] * n_refs
    for i, asset in enumerate(result["assets"]):
        f = client.get(f"/api/v1/jobs/{result['job_id']}/assets/{asset['asset_id']}")
        assert f.status_code == 200
        assert f.headers["content-type"] == "image/png"
        assert f.headers["content-disposition"].startswith("attachment;")


@pytest.mark.parametrize("products,references", [(1, 0), (6, 0), (2, 6)])
def test_invalid_counts_are_422(client, products, references):
    assert upload(client, products=products, references=references).status_code == 422


@pytest.mark.parametrize("first,mime", [(b"GIF89a", "image/gif"), (b"brokenPNG", "image/png")])
def test_invalid_mime_or_corrupt_data_are_422(client, first, mime):
    result = client.post("/api/v1/jobs", files=[
        ("product_images", ("bad.img", first, mime)),
        ("product_images", ("good.png", png((1, 20, 3)), "image/png")),
    ])
    assert result.status_code == 422


def test_duplicate_bytes_422(client):
    duplicate = png((1, 2, 3))
    result = client.post("/api/v1/jobs", files=[
        ("product_images", ("first.png", duplicate, "image/png")),
        ("product_images", ("second.png", duplicate, "image/png")),
    ])
    assert result.status_code == 422


def test_per_file_and_total_sizes_are_413_without_changing_defaults(client, monkeypatch):
    from src.serving import job_api
    with monkeypatch.context() as m:
        m.setattr(job_api, "MAX_FILE_BYTES", 10)
        assert upload(client).status_code == 413
    with monkeypatch.context() as m:
        m.setattr(job_api, "MAX_TOTAL_BYTES", 100)
        assert upload(client).status_code == 413


def test_missing_job_asset_and_unavailable_artifact_404(client):
    job = new_job(client)
    assert client.get("/api/v1/jobs/" + "f" * 32).status_code == 404
    assert client.get(f"/api/v1/jobs/{job}/assets/" + "f" * 32).status_code == 404
    assert client.get(f"/api/v1/jobs/{job}/artifacts/final").status_code == 404
    assert client.get(f"/api/v1/jobs/{job}/artifacts/not_a_kind").status_code == 404


def test_order_conflict_409_recovery_and_duplicate_operation(client):
    job = new_job(client)
    wrong = invoke(client, job, "mock/copy")
    assert wrong.status_code == 409
    state = client.get(f"/api/v1/jobs/{job}")
    assert state.status_code == 200
    assert state.json()["status"] == "INPUTS_VALIDATED"
    args = {"brand_name": "라움", "product_name": "크림"}
    assert invoke(client, job, "mock/plan", args).status_code == 200
    dup = invoke(client, job, "mock/plan", args)
    assert dup.status_code == 409
    assert invoke(client, job, "mock/copy").status_code == 200
    assert invoke(client, job, "approvals/copy", {"approved": True}).status_code == 200
    assert invoke(client, job, "approvals/copy", {"approved": True}).status_code == 409


def test_completed_artifacts_are_real_file_responses(client):
    job = new_job(client)
    assert invoke(client, job, "mock/plan", {"brand_name": "라움", "product_name": "크림"}).status_code == 200
    assert invoke(client, job, "mock/copy").status_code == 200
    assert invoke(client, job, "approvals/copy", {"approved": True}).status_code == 200
    assert invoke(client, job, "mock/image").status_code == 200
    assert invoke(client, job, "approvals/image", {"approved": True}).status_code == 200
    complete = invoke(client, job, "mock/compose")
    assert complete.status_code == 200
    assert complete.json()["status"] == "COMPLETED"
    final = client.get(f"/api/v1/jobs/{job}/artifacts/final")
    caption = client.get(f"/api/v1/jobs/{job}/artifacts/caption")
    assert final.status_code == caption.status_code == 200
    assert final.headers["content-type"] == "image/png"
    assert final.headers["content-disposition"].startswith("attachment;")
    assert "final_mock.png" in final.headers["content-disposition"]
    assert final.content[:8] == bytes.fromhex("89504e470d0a1a0a")
    with Image.open(BytesIO(final.content)) as im:
        assert im.size == (1080, 1350)
    assert caption.headers["content-type"].startswith("text/plain")
    assert "caption.txt" in caption.headers["content-disposition"]
    assert "라움" in caption.content.decode("utf-8")
