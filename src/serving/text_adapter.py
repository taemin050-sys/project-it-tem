"""Opt-in OpenAI Responses text adapter; disabled by default.

No web research or cosmetics-law verification is performed. Import the optional
SDK only after all billing gates are satisfied. Never log secrets or prompts.
"""
from __future__ import annotations

import json
import os
from typing import Any

from fastapi import HTTPException

# Structured Outputs (Responses API). Strict schemas are intentionally small.
PLAN_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "audience": {"type": "string"},
        "direction": {"type": "string"},
        "risk_flags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["audience", "direction", "risk_flags"],
}
COPY_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "text": {"type": "string"},
        "risk_flags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["text", "risk_flags"],
}


def configured_model() -> str:
    return os.getenv("IT_TEM_TEXT_MODEL", "").strip()


def provider_ready() -> bool:
    return (
        os.getenv("IT_TEM_ENABLE_BILLABLE_TEXT_CALLS") == "YES"
        and os.getenv("IT_TEM_TEXT_PROVIDER") == "openai"
        and bool(os.getenv("OPENAI_API_KEY"))
        and bool(configured_model())
    )


def _validate_generated(value: Any, schema_name: str) -> dict[str, Any]:
    expected = {"audience", "direction", "risk_flags"} if schema_name == "it_tem_plan_v1" else {"text", "risk_flags"}
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("Output does not match required keys")
    for key in expected - {"risk_flags"}:
        if not isinstance(value[key], str) or not value[key].strip() or len(value[key]) > 600:
            raise ValueError("Invalid output text")
    if not isinstance(value["risk_flags"], list) or len(value["risk_flags"]) > 10 or any(
        not isinstance(item, str) or len(item) > 180 for item in value["risk_flags"]
    ):
        raise ValueError("Invalid risk flags")
    return value


def generate_structured_text(*, instructions: str, user_input: dict[str, Any], kind: str) -> dict[str, Any]:
    """One bounded, non-retried call; caller must check workflow state first."""
    if not provider_ready():
        raise HTTPException(status_code=503, detail="TEXT_PROVIDER_NOT_ENABLED")
    if kind not in ("plan", "copy"):
        raise ValueError("Unsupported text operation")
    schema_name = "it_tem_plan_v1" if kind == "plan" else "it_tem_copy_v1"
    schema = PLAN_SCHEMA if kind == "plan" else COPY_SCHEMA
    try:
        from openai import OpenAI  # optional dependency, only needed for real text calls
    except ImportError:
        raise HTTPException(status_code=503, detail="OPENAI_SDK_NOT_INSTALLED") from None
    try:
        client = OpenAI(timeout=30.0, max_retries=0)
        response = client.responses.create(
            model=configured_model(),
            instructions=instructions,
            input=json.dumps(user_input, ensure_ascii=False),
            text={"format": {"type": "json_schema", "name": schema_name,
                             "strict": True, "schema": schema}},
            max_output_tokens=600,
            store=False,
        )
        if response.status != "completed" or not response.output_text:
            raise ValueError("Incomplete or empty response")
        result = _validate_generated(json.loads(response.output_text), schema_name)
    except Exception:
        # Avoid leaking provider payloads/credentials. Provider may have charged
        # for a timed-out call: no automatic retry by design.
        raise HTTPException(status_code=502, detail="TEXT_PROVIDER_FAILED_STATE_UNCHANGED") from None
    return result
