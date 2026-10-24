"""Port examples prove research, planning, copy and image can develop separately.

All implementations are local stubs, NOT real AI providers or HTTP endpoints.
"""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError
import pytest

from src.serving.provisional_contracts import (
    CopyResult, Evidence, ImageResult, PlanResult, ProductFacts, VisualBrief,
)
from src.serving.provisional_ports import CopyPort, ImagePort, PlanningPort, ResearchPort

FIXTURE_ROOT = Path(__file__).parent / "contracts" / "fixtures"


def load(model, name):
    return model.model_validate_json((FIXTURE_ROOT / f"{name}.json").read_text(encoding="utf-8"))


class StubResearch:
    def research(self, facts: ProductFacts) -> list[Evidence]:
        return []  # no external search, do not mark as researched


class StubPlanning:
    def plan(self, facts: ProductFacts, evidence: list[Evidence]) -> PlanResult:
        return PlanResult(
            mock=True, brand_name=facts.brand_name, product_name=facts.product_name,
            audience="가설 타깃", direction="일상 루틴",
            research_performed=False, evidence=evidence,
            disclaimer="계약 검증용 Stub. 외부 검색 없음",
        )


class StubCopy:
    def copy(self, plan: PlanResult) -> CopyResult:
        return CopyResult(
            mock=True, text=f"{plan.brand_name}의 일상 루틴",
            compliance_checked=False, disclaimer="Stub 카피, 광고 적법성 미검토",
        )


class StubImage:
    def image(self, brief: VisualBrief) -> ImageResult:
        assert brief.copy_revision > 0
        return load(ImageResult, "image_result")


def test_four_ports_can_run_with_local_fixtures_without_network():
    facts = load(ProductFacts, "product_facts")
    research: ResearchPort = StubResearch()
    planning: PlanningPort = StubPlanning()
    writing: CopyPort = StubCopy()
    generating: ImagePort = StubImage()
    evidence = research.research(facts)
    plan = planning.plan(facts, evidence)
    copy = writing.copy(plan)
    brief_data = json.loads((FIXTURE_ROOT / "visual_brief.json").read_text())
    brief_data["copy_text"] = copy.text
    brief = VisualBrief.model_validate(brief_data)
    image = generating.image(brief)
    assert plan.research_performed is False and plan.mock is True
    assert copy.compliance_checked is False and copy.mock is True
    assert image.mock is True and image.preservation_review == "pending"


def test_independent_image_port_rejects_missing_copy_and_unsafe_ids():
    source = json.loads((FIXTURE_ROOT / "visual_brief.json").read_text())
    source["copy_text"] = ""
    with pytest.raises(ValidationError):
        VisualBrief.model_validate(source)
    source["copy_text"] = "카피"
    source["product_asset_ids"] = ["invalid"]
    with pytest.raises(ValidationError):
        VisualBrief.model_validate(source)
