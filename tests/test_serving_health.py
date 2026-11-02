from fastapi.testclient import TestClient

from src.serving.main import app


client = TestClient(app)


def test_health_check():
    response = client.get("/health")

    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "it-tem-backend"
    assert data["version"] == "0.1.0"


def test_openapi_schema():
    response = client.get("/openapi.json")

    assert response.status_code == 200

    schema = response.json()
    assert schema["info"]["title"] == "IT-TEM Backend API"
    assert "/health" in schema["paths"]
