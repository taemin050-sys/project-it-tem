"""OpenAI 호출 공통 함수 (재시도·타임아웃·출력 길이)"""

import logging
from typing import Any, TypeVar

from openai import OpenAI, OpenAIError
from pydantic import BaseModel, ValidationError

from .config import MODEL_TEXT, OPENAI_API_KEY

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

DEFAULT_TIMEOUT = 300
MAX_RETRIES = 0
DEFAULT_MAX_OUTPUT_TOKENS = 1200

client = OpenAI(
    api_key=OPENAI_API_KEY, timeout=DEFAULT_TIMEOUT, max_retries=MAX_RETRIES
)


class LLMError(Exception):
    """OpenAI 호출 실패 또는 스키마대로 응답이 안 나왔을 때"""


def _usage_text(usage: dict[str, Any] | None) -> str:
    if not usage:
        return "토큰 정보 없음"
    reasoning = (usage.get("output_tokens_details") or {}).get("reasoning_tokens", 0)
    return (
        f"in {usage.get('input_tokens')} / out {usage.get('output_tokens')} "
        f"(추론 {reasoning}) tokens"
    )


def call_structured(
    input: str | list[dict[str, Any]],
    schema: type[T],
    *,
    instructions: str | None = None,
    model: str = MODEL_TEXT,
    tools: list[dict[str, Any]] | None = None,
    max_tool_calls: int | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    reasoning_effort: str | None = None,
    return_raw: bool = False,
) -> T | tuple[T, Any]:
    """프롬프트를 보내고 schema(Pydantic 모델) 형식으로 결과를 받음
    return_raw=True면 (결과, 응답 원본) 반환 (url_citation 추출용)"""
    kwargs: dict[str, Any] = {
        "model": model,
        "input": input,
        "text_format": schema,
        "timeout": timeout,
        "max_output_tokens": max_output_tokens,
    }
    if instructions:
        kwargs["instructions"] = instructions
    if tools:
        kwargs["tools"] = tools
    if max_tool_calls is not None:
        kwargs["max_tool_calls"] = max_tool_calls
    if reasoning_effort:
        kwargs["reasoning"] = {"effort": reasoning_effort}

    try:
        raw = client.responses.with_raw_response.parse(**kwargs)
    except OpenAIError as e:
        raise LLMError(
            f"[{schema.__name__}] OpenAI 호출 실패: {type(e).__name__}: {e}"
        ) from e

    body = raw.http_response.json()
    status = body.get("status")
    reason = (body.get("incomplete_details") or {}).get("reason")
    tokens = _usage_text(body.get("usage"))

    try:
        res = raw.parse()
        parsed = res.output_parsed
    except ValidationError:
        parsed = None

    if parsed is None:
        logger.warning(
            "%s | %s | 실패 | status=%s, reason=%s | %s",
            schema.__name__,
            model,
            status,
            reason,
            tokens,
        )
        raise LLMError(
            f"[{schema.__name__}] 스키마대로 응답이 오지 않음 "
            f"(status={status}, reason={reason}, {tokens})"
        )

    logger.info("%s | %s | %s", schema.__name__, model, tokens)
    if return_raw:
        return parsed, res
    return parsed
