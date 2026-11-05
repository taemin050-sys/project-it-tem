"""예상 비용 (만들기 전 안내용, 실제 호출 없음) : 단가 × 단계별 평균 토큰

- 텍스트 파트만 (사진 분석, 기획 AI 조사, 카피, 이미지 프롬프트). 이미지 생성 비용은 이미지 파트에서 따로 계산
- 단위 : 달러
- 평균 토큰은 11/4 gpt-6-luna 측정값을 넉넉하게 올린 값 (프롬프트가 크게 바뀌면 다시 측정)
"""

from typing import Literal

from pydantic import BaseModel, Field

from .config import MODEL_TEXT, MODEL_VISION

# 1M 토큰당 달러 (입력, 출력). 추론 토큰은 출력 토큰에 포함되어 과금
PRICES: dict[str, tuple[float, float]] = {
    "gpt-6-luna": (0.10, 0.50),
    "gpt-5.4-mini": (0.75, 4.50),
}
WEB_SEARCH_PRICE = 0.01  # 웹 검색 1회
WEB_SEARCH_MAX = 2  # researcher의 max_tool_calls (예상은 최대치로 계산)

# 단계별 평균 토큰 (입력, 출력)
STEP_TOKENS: dict[str, tuple[int, int]] = {
    "research": (15_000, 1_000),  # 측정 14,512~14,661 / 895~991 (검색 결과 포함)
    "copy": (3_600, 700),  # 측정 2,376~3,552 / 399~691 (이모티콘 "많이"가 가장 김)
    "image_prompt": (800, 300),  # 측정 735~753 / 174~283
    "copy_revision": (4_400, 800),  # 측정 4,297~4,328 / 385~729
    "image_prompt_revision": (1_700, 400),  # 측정 1,583~1,635 / 159~364
}
ANALYSIS_TOKENS_PER_PHOTO = 2_400  # 측정 4장 9,448 → 장당 약 2,362
ANALYSIS_OUTPUT_TOKENS = 300  # 측정 229~246

RevisionTarget = Literal["copy", "image_prompt"]


class CostEstimate(BaseModel):
    """예상 비용 (코드에서 계산, LLM 출력 아님)"""

    model: str
    steps: dict[str, float] = Field(..., description="단계별 예상 비용 (달러)")
    total_usd: float = Field(..., description="합계 (달러)")


def _token_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    if model not in PRICES:
        raise ValueError(f"단가표에 없는 모델입니다 : {model}")
    price_in, price_out = PRICES[model]
    return (input_tokens * price_in + output_tokens * price_out) / 1_000_000


def estimate_generation_cost(
    photo_count: int = 5,
    model: str = MODEL_TEXT,
    vision_model: str = MODEL_VISION,
) -> CostEstimate:
    """처음 생성 예상 비용 : 사진 분석 + 조사(웹 검색 최대 2회) + 카피 + 이미지 프롬프트"""
    if not 2 <= photo_count <= 5:
        raise ValueError(f"제품 사진은 2~5장이어야 합니다. (받은 장수: {photo_count})")
    steps = {
        "analysis": _token_cost(
            vision_model,
            ANALYSIS_TOKENS_PER_PHOTO * photo_count,
            ANALYSIS_OUTPUT_TOKENS,
        ),
        "research": _token_cost(model, *STEP_TOKENS["research"])
        + WEB_SEARCH_PRICE * WEB_SEARCH_MAX,
        "copy": _token_cost(model, *STEP_TOKENS["copy"]),
        "image_prompt": _token_cost(model, *STEP_TOKENS["image_prompt"]),
    }
    return CostEstimate(
        model=model,
        steps={k: round(v, 6) for k, v in steps.items()},
        total_usd=round(sum(steps.values()), 6),
    )


def estimate_revision_cost(
    target: RevisionTarget, model: str = MODEL_TEXT
) -> CostEstimate:
    """수정 요청 1회 예상 추가 비용 (target : "copy" 또는 "image_prompt")"""
    step = f"{target}_revision"
    cost = _token_cost(model, *STEP_TOKENS[step])
    return CostEstimate(
        model=model, steps={step: round(cost, 6)}, total_usd=round(cost, 6)
    )


def format_usd(amount: float) -> str:
    """화면 표시용 (예 : '약 $0.024', '$0.001 미만')"""
    if amount < 0.001:
        return "$0.001 미만"
    return f"약 ${amount:.3f}"
