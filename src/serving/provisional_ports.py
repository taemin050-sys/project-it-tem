"""Review-only boundaries for parallel teams. Not wired into public HTTP routes.

Adapters own just their input -> output operation; FastAPI owns job state,
approvals, storage, retry decisions, auth and cost governance. The source code
here must not be used as a claim that the team has agreed to v0.1.
"""
from __future__ import annotations

from typing import Protocol

from .provisional_contracts import (
    CopyResult, Evidence, ImageResult, PlanResult, ProductFacts, VisualBrief,
)


class ResearchPort(Protocol):
    def research(self, facts: ProductFacts) -> list[Evidence]: ...


class PlanningPort(Protocol):
    def plan(self, facts: ProductFacts, evidence: list[Evidence]) -> PlanResult: ...


class CopyPort(Protocol):
    def copy(self, plan: PlanResult) -> CopyResult: ...


class ImagePort(Protocol):
    def image(self, brief: VisualBrief) -> ImageResult: ...
