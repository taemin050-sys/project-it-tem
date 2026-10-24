"""Contract checks for a research -> planning handoff, without invoking models."""
from __future__ import annotations

from .provisional_contracts import PlanResult, ProductFacts
from .provisional_ports import PlanningPort
from .p4_research_adapter import ResearchBundle


def build_plan(planner: PlanningPort, facts: ProductFacts, bundle: ResearchBundle) -> PlanResult:
    proposal = PlanResult.model_validate(planner.plan(facts, list(bundle.evidence)))
    if (proposal.brand_name, proposal.product_name) != (facts.brand_name, facts.product_name):
        raise ValueError("Plan changed product identity")
    # Reject invented sources, altered titles/status, unsupported 'research performed'.
    known = {item.source_id: item for item in bundle.evidence}
    if len({e.source_id for e in proposal.evidence}) != len(proposal.evidence):
        raise ValueError("Duplicate evidence in plan")
    for item in proposal.evidence:
        if item.source_id not in known or item != known[item.source_id]:
            raise ValueError("Plan invented or modified an evidence source")
    if proposal.research_performed and not bundle.research_performed:
        raise ValueError("Planning cannot claim completed live research")
    if bundle.mode == "fixture" and not proposal.mock:
        raise ValueError("Fixture planning must remain visibly mocked")
    return proposal
