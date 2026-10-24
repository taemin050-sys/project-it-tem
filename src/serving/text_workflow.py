"""Parallel opt-in text endpoints; keeps P3 mock endpoints unchanged."""
from __future__ import annotations

import threading
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field, field_validator

from .job_api import get_job_store
from .job_store import JobStore, transition_job
from .mock_workflow import MockProductRequest, _as_json_bytes
from . import text_adapter

router = APIRouter(prefix="/api/v1/jobs", tags=["AI text — provisional"])

# Single process guard: prevent concurrent duplicate paid requests for same job/stage.
_active_lock = threading.Lock()
_active_calls: set[tuple[str, str]] = set()


class PlanRequest(MockProductRequest):
    product_facts: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("product_facts")
    @classmethod
    def valid_facts(cls, facts: list[str]) -> list[str]:
        for fact in facts:
            if not fact.strip() or len(fact) > 300 or any(ord(c) < 32 for c in fact):
                raise ValueError("Invalid product fact")
        return facts


def _guarded_generate(store: JobStore, job_id: str, phase: str,
                      expected_status: str, generate: Any) -> dict[str, Any]:
    key = (job_id, phase)
    with _active_lock:
        with store._lock:
            job = store.get_job(job_id)
            if job["status"] != expected_status:
                raise HTTPException(status_code=409, detail={
                    "error": "INVALID_WORKFLOW_STATE", "current_status": job["status"],
                    "expected_status": expected_status,
                })
            if key in _active_calls:
                raise HTTPException(status_code=409, detail="TEXT_CALL_ALREADY_IN_PROGRESS")
            _active_calls.add(key)
    try:
        return generate()
    finally:
        with _active_lock:
            _active_calls.discard(key)


@router.post("/{job_id}/ai/plan")
def ai_plan(job_id: str, body: PlanRequest, store: JobStore = Depends(get_job_store)):
    def run():
        out = text_adapter.generate_structured_text(
            kind="plan",
            instructions=(
                "한국어 화장품 인스타그램 광고 기획 초안을 작성하라. "
                "주어진 product_facts 이외에 제품 성능·성분·가격·인증·시장 데이터·경쟁사 사실을 만들어내지 말라. "
                "실제 시장조사·경쟁사 검색을 수행하지 않았으므로 추정 타깃을 검증된 조사처럼 표현하지 말라. "
                "의학적 효능·치료·완치 표현은 금지. 위험 가능성은 risk_flags에 기록. "
                "광고 법률 검토 완료라고 주장하지 말라. 반드시 JSON schema에 맞춰 응답."
            ),
            user_input=body.model_dump(),
        )
        plan = {
            "mock": False, "research_performed": False,
            "brand_name": body.brand_name, "product_name": body.product_name,
            "audience": out["audience"], "direction": out["direction"],
            "risk_flags": out["risk_flags"],
            "product_facts_user_supplied_unverified": body.product_facts,
            "provider": "openai", "model": text_adapter.configured_model(),
            "disclaimer": "실제 시장·경쟁사 리서치 및 광고 법규 준수 검증 미실시",
        }
        return transition_job(
            store, job_id, expected_status="INPUTS_VALIDATED", next_status="PLAN_READY",
            updates={"plan": plan}, artifact_kind="plan", artifact_bytes=_as_json_bytes(plan),
        )
    return _guarded_generate(store, job_id, "plan", "INPUTS_VALIDATED", run)


@router.post("/{job_id}/ai/copy")
def ai_copy(job_id: str, store: JobStore = Depends(get_job_store)):
    def run():
        job = store.get_job(job_id)
        plan = job["plan"]
        out = text_adapter.generate_structured_text(
            kind="copy",
            instructions=(
                "한국어 화장품 인스타그램 광고 카피 후보를 오직 한 개만 작성하라. "
                "검증되지 않은 기능성·성분·의학적 효능·임상결과·수상·가격·경쟁사 비교 주장을 하지 말라. "
                "짧은 카피를 text에, 검토 필요사항을 risk_flags에 넣어라. "
                "이 단계는 광고 표시·광고 법규의 적법성 심사가 아니다. JSON schema 준수."
            ),
            user_input={"brand_name": plan["brand_name"], "product_name": plan["product_name"],
                        "direction": plan["direction"],
                        "product_facts": plan.get("product_facts_user_supplied_unverified", [])},
        )
        copy = {
            "mock": False, "text": out["text"], "risk_flags": out["risk_flags"],
            "compliance_checked": False, "provider": "openai", "model": text_adapter.configured_model(),
            "disclaimer": "AI 생성 초안. 사실관계·화장품 광고 관련 법규·최종 책임자 검토 필요",
        }
        return transition_job(
            store, job_id, expected_status="PLAN_READY", next_status="COPY_REVIEW_REQUIRED",
            updates={"copy_candidate": copy}, artifact_kind="copy", artifact_bytes=_as_json_bytes(copy),
        )
    return _guarded_generate(store, job_id, "copy", "PLAN_READY", run)
