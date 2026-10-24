"""Executable draft for cross-team discussion. NEVER calls external models."""
from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError

from src.serving.main import create_app
from src.serving.provisional_contracts import (
    PROVISIONAL_MODELS, CopyResult, ImageResult, PlanResult, SafeZone,
    VisualBrief,
)
from scripts.export_p4_contracts import export

FIXTURES = Path(__file__).parent / "contracts" / "fixtures"


def fixture(name):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def sample_png(color):
    buffer = BytesIO()
    Image.new("RGB", (64, 64), color).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.mark.parametrize("name", sorted(PROVISIONAL_MODELS))
def test_each_team_fixture_matches_provisional_dto(name):
    value = PROVISIONAL_MODELS[name].model_validate_json((FIXTURES / f"{name}.json").read_text())
    assert value.model_dump(mode="json") == fixture(name)


def test_provisional_fixture_is_not_pretending_to_have_research_or_approval():
    plan = PlanResult.model_validate(fixture("plan_result"))
    copy = CopyResult.model_validate(fixture("copy_result"))
    assert not plan.research_performed and plan.evidence == []
    assert not copy.compliance_checked


def test_research_cannot_be_claimed_without_provenance():
    payload = fixture("plan_result")
    payload["research_performed"] = True
    with pytest.raises(ValidationError):
        PlanResult.model_validate(payload)


def test_visual_brief_blocks_overlapping_asset_ids():
    payload = fixture("visual_brief")
    payload["reference_asset_ids"] = payload["product_asset_ids"][:]
    with pytest.raises(ValidationError):
        VisualBrief.model_validate(payload)


def test_visual_brief_blocks_invalid_approval_revision_and_job_id():
    payload = fixture("visual_brief")
    payload["copy_revision"] = 0
    with pytest.raises(ValidationError):
        VisualBrief.model_validate(payload)
    payload["copy_revision"] = 1
    payload["job_id"] = "../../../etc/passwd"
    with pytest.raises(ValidationError):
        VisualBrief.model_validate(payload)


def test_safe_zone_requires_normalized_nonempty_rectangle():
    with pytest.raises(ValidationError):
        SafeZone(left=0.9, top=0.1, right=0.1, bottom=0.3)
    with pytest.raises(ValidationError):
        SafeZone(left=-0.1, top=0.1, right=0.6, bottom=0.3)


def test_image_candidate_not_forced_to_final_1080x1350():
    obj = ImageResult.model_validate(fixture("image_result"))
    assert (obj.width, obj.height) == (1024, 1536)


def test_api_upload_and_approval_gate_unchanged(tmp_path, monkeypatch):
    monkeypatch.delenv("IT_TEM_ENABLE_BILLABLE_TEXT_CALLS", raising=False)
    with TestClient(create_app(storage_root=tmp_path / "jobs")) as client:
        response = client.post("/api/v1/jobs", files=[
            ("product_images", ("one.png", sample_png("red"), "image/png")),
            ("product_images", ("two.png", sample_png("blue"), "image/png")),
        ])
        assert response.status_code == 201
        job = response.json()
        assert job["status"] == "INPUTS_VALIDATED"
        assert len(job["assets"]) == 2
        assert client.post(f"/api/v1/jobs/{job['job_id']}/mock/image").status_code == 409
        assert client.post(f"/api/v1/jobs/{job['job_id']}/ai/plan", json={
            "brand_name": "A", "product_name": "B"
        }).status_code == 503
        assert client.get(f"/api/v1/jobs/{job['job_id']}").json()["status"] == "INPUTS_VALIDATED"


def test_existing_openapi_contract_paths_and_field_names(tmp_path):
    with TestClient(create_app(storage_root=tmp_path / "jobs")) as client:
        api = client.get("/openapi.json").json()
    assert api["openapi"].startswith("3.")
    for path in [
        "/health", "/api/v1/capabilities", "/api/v1/jobs",
        "/api/v1/jobs/{job_id}", "/api/v1/jobs/{job_id}/mock/plan",
        "/api/v1/jobs/{job_id}/mock/copy", "/api/v1/jobs/{job_id}/ai/plan",
        "/api/v1/jobs/{job_id}/ai/copy", "/api/v1/jobs/{job_id}/mock/image",
        "/api/v1/jobs/{job_id}/approvals/copy",
        "/api/v1/jobs/{job_id}/approvals/image",
        "/api/v1/jobs/{job_id}/mock/compose",
        "/api/v1/jobs/{job_id}/artifacts/{kind}",
    ]:
        assert path in api["paths"], path
    upload = api["paths"]["/api/v1/jobs"]["post"]["requestBody"]
    assert "multipart/form-data" in upload["content"]


def test_machine_contract_export_is_repeatable_and_not_approved(tmp_path):
    out = tmp_path / "contracts"
    first = export(out)
    second = export(out)
    assert first == second
    assert first["contract_status"] == "PROVISIONAL_NOT_APPROVED"
    assert "openapi.json" in first["artifacts"]
    assert "schemas/visual_brief.schema.json" in first["artifacts"]
    assert json.loads((out / "openapi.json").read_text())["info"]["title"] == "IT-TEM Backend API"


def test_typescript_provisional_client_exports_current_states():
    ts = (Path(__file__).parent.parent / "docs/drafts/react_client_provisional.ts").read_text()
    for status in [
        "INPUTS_VALIDATED", "PLAN_READY", "COPY_REVIEW_REQUIRED", "COPY_APPROVED",
        "IMAGE_REVIEW_REQUIRED", "IMAGE_APPROVED", "COMPLETED",
        "COPY_REJECTED", "IMAGE_REJECTED",
    ]:
        assert f'"{status}"' in ts
    assert 'form.append("product_images", file)' in ts
    assert 'form.append("reference_images", file)' in ts
