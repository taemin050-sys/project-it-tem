"""Cross-stage readiness without any network call, preserving existing HTTP API."""
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from src.serving.main import create_app
from src.serving.p4_cost_guard import P4CostGuard, fingerprint
from src.serving.p4_research_adapter import normalize_hits
from src.serving.p4_planning_bridge import build_plan
from src.serving.provisional_contracts import PlanResult, ProductFacts
from scripts.export_p4_contracts import export


class FixturePlanner:
    def plan(self, facts, evidence):
        return PlanResult(mock=True, brand_name=facts.brand_name, product_name=facts.product_name,
                          audience="가설", direction="예시", research_performed=False,
                          evidence=evidence, disclaimer="외부 조사 없음")


def test_preflight_four_module_gate_and_openapi_unchanged(tmp_path):
    facts = ProductFacts(brand_name="B", product_name="Lotion",
                         claim_source="user_supplied_unverified")
    # fixture-only evidence, no live data, no claim that research happened
    bundle = normalize_hits([], mode="fixture", retrieved_at=datetime.now(timezone.utc))
    proposal = build_plan(FixturePlanner(), facts, bundle)
    assert proposal.mock and not proposal.research_performed

    with TestClient(create_app(storage_root=tmp_path / "jobs")) as client:
        api = client.get("/openapi.json").json()
        assert "/api/v1/jobs/{job_id}/ai/plan" in api["paths"]
        assert not any("p4/cost" in x or "p4/image" in x for x in api["paths"])
        assert client.get("/api/v1/capabilities").json()["image_provider_ready"] is False
    manifest = export(tmp_path / "contracts")
    assert len(manifest["artifacts"]) == 8  # OpenAPI + seven schemas (manifest listed separately)
    assert manifest["contract_status"] == "PROVISIONAL_NOT_APPROVED"


def test_reservations_across_planning_and_image_share_budget(tmp_path):
    ledger = P4CostGuard(tmp_path / "ledger.sqlite3", max_budget_micro_usd=700, enable_billable=True)
    planning = ledger.execute(job_id="a"*32, phase="planning", operation_key="plan_req_01",
                              request_hash=fingerprint({"plan": "fixture"}),
                              max_cost_micro_usd=300, call=lambda: "mock-plan")
    image = ledger.execute(job_id="a"*32, phase="image", operation_key="image_req_01",
                           request_hash=fingerprint({"image": "fixture"}),
                           max_cost_micro_usd=400, call=lambda: "fake-image")
    assert planning.value == "mock-plan" and image.value == "fake-image"
    assert sum(x["reserved_micro_usd"] for x in ledger.snapshot()) == 700
