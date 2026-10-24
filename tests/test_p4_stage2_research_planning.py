from datetime import datetime, timezone
import pytest

from src.serving.p4_research_adapter import SearchHit, normalize_hits, ResearchBundle
from src.serving.p4_planning_bridge import build_plan
from src.serving.provisional_contracts import ProductFacts, PlanResult


NOW = datetime(2026, 10, 24, tzinfo=timezone.utc)


def sample_hit(**override):
    return SearchHit.model_validate({"source_id": "s1", "source_type": "paper",
        "title": "synthetic reference, NOT actual paper", "url_or_doi": "https://doi.org/10.0000/example",
        "claim_ids": [], **override})


def facts():
    return ProductFacts(brand_name="테스트", product_name="로션",
                        claim_source="user_supplied_unverified")


def test_research_keeps_source_unverified():
    bundle = normalize_hits([sample_hit()], mode="live", retrieved_at=NOW)
    assert bundle.research_performed
    e, = bundle.evidence
    assert e.retrieved_at == NOW and e.verification_status == "unverified"


def test_fixture_does_not_claim_live_research():
    bundle = normalize_hits([sample_hit()], mode="fixture", retrieved_at=NOW)
    assert not bundle.research_performed and bundle.completed
    assert not normalize_hits([], mode="live", retrieved_at=NOW).research_performed


@pytest.mark.parametrize("url", ["http://example.org/a", "file:///etc/passwd",
    "https://localhost/a", "https://127.0.0.1/x", "https://10.0.0.1/x",
    "https://user:secret@example.com/x", "https://service.local/a", "https://example.com\nX:Y"])
def test_unsafe_reference_rejected(url):
    with pytest.raises(ValueError):
        normalize_hits([sample_hit(url_or_doi=url)], mode="live", retrieved_at=NOW)


def test_duplicate_evidence_and_naive_time_rejected():
    with pytest.raises(ValueError):
        normalize_hits([sample_hit(), sample_hit()], mode="fixture")
    with pytest.raises(ValueError):
        normalize_hits([], mode="live", retrieved_at=datetime(2026, 10, 24))


class Planner:
    def __init__(self, **changes):
        self.changes = changes
    def plan(self, f, evidence):
        result = dict(mock=False, brand_name=f.brand_name, product_name=f.product_name,
                      audience="가설", direction="루틴", research_performed=True,
                      evidence=evidence, disclaimer="실제 검증 아님")
        result.update(self.changes)
        return PlanResult.model_validate(result)


def test_live_plan_uses_only_passed_through_evidence():
    b = normalize_hits([sample_hit()], mode="live", retrieved_at=NOW)
    p = build_plan(Planner(), facts(), b)
    assert p.research_performed and p.evidence[0].source_id == "s1"


def test_planner_cannot_claim_fixture_as_live():
    b = normalize_hits([sample_hit()], mode="fixture", retrieved_at=NOW)
    with pytest.raises(ValueError):
        build_plan(Planner(), facts(), b)


def test_planner_cannot_invent_source_or_alter_product():
    b = normalize_hits([sample_hit()], mode="live", retrieved_at=NOW)
    with pytest.raises(ValueError):
        build_plan(Planner(product_name="다른 로션"), facts(), b)
    fake = b.evidence[0].model_copy(update={"source_id": "invented"})
    with pytest.raises(ValueError):
        build_plan(Planner(evidence=[fake]), facts(), b)
    edited = b.evidence[0].model_copy(update={"verification_status": "corroborated"})
    with pytest.raises(ValueError):
        build_plan(Planner(evidence=[edited]), facts(), b)


def test_planner_must_label_fixture_as_mock():
    b = normalize_hits([], mode="fixture", retrieved_at=NOW)
    plan = build_plan(Planner(mock=True, research_performed=False), facts(), b)
    assert plan.mock and not plan.research_performed
