from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from src.serving.main import create_app


def image_bytes(color, *, format="PNG"):
    image = Image.new("RGB", (16, 12), color)
    buffer = BytesIO()
    image.save(buffer, format=format)
    return buffer.getvalue()


@pytest.fixture()
def app_client(tmp_path):
    app = create_app(storage_root=tmp_path / "jobs")
    with TestClient(app) as client:
        yield client, tmp_path / "jobs"


def send(client, products=2, references=0, **kwargs):
    images = [
        ("product_images", (f"photo{i}.png", image_bytes((i * 41, 0, 11)), "image/png"))
        for i in range(products)
    ]
    images += [
        ("reference_images", (f"ref{i}.png", image_bytes((0, i * 43, 29)), "image/png"))
        for i in range(references)
    ]
    return client.post("/api/v1/jobs", files=images, **kwargs)


def test_create_persistent_job_and_download(app_client):
    client, root = app_client
    response = send(client, products=2, references=1)
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["status"] == "INPUTS_VALIDATED"
    assert len(result["job_id"]) == 32
    assert [a["role"] for a in result["assets"]] == ["product", "product", "reference"]
    assert (root / result["job_id"] / "job.json").is_file()

    # A new app instance reads the previous job without in-memory state.
    with TestClient(create_app(storage_root=root)) as fresh_client:
        loaded = fresh_client.get(f"/api/v1/jobs/{result['job_id']}")
        assert loaded.status_code == 200
        assert loaded.json() == result
        first_asset = result["assets"][0]
        download = fresh_client.get(f"/api/v1/jobs/{result['job_id']}/assets/{first_asset['asset_id']}")
        assert download.status_code == 200
        assert download.headers["content-type"] == "image/png"
        assert download.content == image_bytes((0, 0, 11))


def test_valid_limits(app_client):
    client, _ = app_client
    response = send(client, products=5, references=5)
    assert response.status_code == 201, response.text
    assert len(response.json()["assets"]) == 10


@pytest.mark.parametrize("product_count,ref_count", [(1, 0), (6, 0), (2, 6)])
def test_invalid_image_counts(app_client, product_count, ref_count):
    client, root = app_client
    assert send(client, product_count, ref_count).status_code == 422
    assert list(root.iterdir()) == []


def test_missing_products(app_client):
    client, _ = app_client
    assert client.post("/api/v1/jobs").status_code == 422


def test_disallowed_mime(app_client):
    client, root = app_client
    result = client.post("/api/v1/jobs", files=[
        ("product_images", ("a.gif", b"GIF89a", "image/gif")),
        ("product_images", ("b.png", image_bytes((1, 1, 1)), "image/png")),
    ])
    assert result.status_code == 422
    assert list(root.iterdir()) == []


def test_corrupted_image(app_client):
    client, root = app_client
    result = client.post("/api/v1/jobs", files=[
        ("product_images", ("a.png", b"not-a-real-png", "image/png")),
        ("product_images", ("b.png", image_bytes((1, 1, 1)), "image/png")),
    ])
    assert result.status_code == 422
    assert list(root.iterdir()) == []


def test_reject_format_mismatch(app_client):
    client, root = app_client
    result = client.post("/api/v1/jobs", files=[
        ("product_images", ("a.png", image_bytes((1, 1, 1), format="JPEG"), "image/png")),
        ("product_images", ("b.png", image_bytes((2, 2, 2)), "image/png")),
    ])
    assert result.status_code == 422
    assert list(root.iterdir()) == []


def test_duplicate_content_rejected(app_client):
    client, root = app_client
    same = image_bytes((1, 1, 1))
    result = client.post("/api/v1/jobs", files=[
        ("product_images", ("a.png", same, "image/png")),
        ("product_images", ("b.png", same, "image/png")),
    ])
    assert result.status_code == 422
    assert list(root.iterdir()) == []


def test_upload_too_large(app_client, monkeypatch):
    import src.serving.job_api as module

    monkeypatch.setattr(module, "MAX_FILE_BYTES", 50)
    client, root = app_client
    assert send(client).status_code == 413
    assert list(root.iterdir()) == []


def test_no_traversal_or_random_asset(app_client):
    client, _ = app_client
    response = send(client)
    job_id = response.json()["job_id"]
    assert client.get("/api/v1/jobs/not-a-valid-id").status_code == 404
    assert client.get(f"/api/v1/jobs/{job_id}/assets/{'f'*32}").status_code == 404
    assert client.get(f"/api/v1/jobs/{job_id}/assets/not-an-id").status_code == 404


def test_health_endpoint_kept(app_client):
    client, _ = app_client
    assert client.get("/health").json()["status"] == "ok"
    schema = client.get("/openapi.json").json()
    assert "/api/v1/jobs" in schema["paths"]
