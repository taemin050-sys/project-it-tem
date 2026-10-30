"""이미지 프롬프트 생성 : AdPlan + ProductAnalysis → ImagePromptOutput (한국어 배경 프롬프트, 검색 없이 1회 호출)"""

import logging

from .config import MODEL_TEXT, REASONING_EFFORT
from .llm_client import call_structured
from .schemas import AdPlan, ImagePromptOutput, ProductAnalysis

logger = logging.getLogger(__name__)

INSTRUCTIONS = """너는 화장품 광고 이미지의 배경을 설계하는 아트 디렉터야.
광고 기획(콘셉트·무드)과 제품 용기 정보를 보고, 이미지 생성 AI에 넣을 배경 프롬프트를 한국어로 만들어.

[출력 항목]
- concept : 입력받은 콘셉트를 그대로 적어
- prompt : 배경 프롬프트. 하나의 완성된 한국어 문장, 80~200자
- mood : 입력받은 무드를 그대로 적어

[prompt 작성 규칙]
- 배경과 분위기만 묘사해. 장소·소품·빛·색감·질감(광택, 물방울, 젤 질감 등)을 구체적으로
- 제품이 놓일 자리를 화면 가운데에 비워둬. 제품 자체는 묘사하지 마
- 배경의 주된 색은 제품 용기 색과 다른 색 계열로 정해. 용기 색이나 비슷한 색을 배경 주색으로 쓰지 마
- 글자, 로고, 브랜드명, 다른 제품, 사람, 손이 없는 장면으로 묘사해. 단, 이런 금지 내용을 prompt에 적지 마
- 금지 문구나 제품 보존 문구는 쓰지 마 (이미지 쪽에서 따로 붙임)"""


def _build_input(plan: AdPlan, analysis: ProductAnalysis) -> str:
    return f"""[광고 기획]
- 콘셉트 : {plan.concept}
- 핵심 메시지 : {plan.key_message}
- 톤 : {plan.tone}
- 무드 : {", ".join(plan.mood)}

[제품 용기 (사진 분석)]
- 용기 : {analysis.container_type}
- 용기 색 : {", ".join(analysis.colors) or "없음"}
- 투명 용기 : {"예" if analysis.is_transparent else "아니오"}"""


def generate_image_prompt(
    plan: AdPlan,
    analysis: ProductAnalysis,
    model: str = MODEL_TEXT,
    reasoning_effort: str | None = REASONING_EFFORT,
) -> ImagePromptOutput:
    """한국어 배경 프롬프트 생성 (1회 호출, 실패 시 LLMError). concept·mood는 AdPlan 값으로 고정"""
    output = call_structured(
        _build_input(plan, analysis),
        ImagePromptOutput,
        instructions=INSTRUCTIONS,
        model=model,
        reasoning_effort=reasoning_effort,
    )
    output.concept = plan.concept
    output.mood = plan.mood
    logger.info("이미지 프롬프트 %d자", len(output.prompt))
    return output
