"""기획 + 카피 생성 : ProductInput + ProductAnalysis + ResearchResult → AdCopyOutput (검색 없이 1회 호출)"""

import logging

from .config import MODEL_TEXT
from .llm_client import call_structured
from .schemas import AdCopyOutput, ProductAnalysis, ProductInput, ResearchResult

logger = logging.getLogger(__name__)

MAX_COPY_CHARS = 400  # 헤드 + 서브 + CTA + 본문 합계 (해시태그 제외), 임시 기준

INSTRUCTIONS = f"""너는 소상공인 화장품 브랜드의 인스타그램 피드 광고 카피라이터야.
제품 정보, 사진 분석, 기획 AI 조사 결과를 보고 광고 기획과 카피를 만들어.

[출력 항목]
- plan.target : 광고 타깃 1문장
- plan.concept : 광고 콘셉트 1문장
- plan.key_message : 가장 전하고 싶은 메시지 1문장
- plan.tone : 카피 톤 (예: 친근한, 차분한, 고급스러운)
- plan.mood : 이미지 배경 분위기 2~3개, 한국어 한 단어씩 (예: 청량, 내추럴)
- ad_copy.headline : 이미지 위에 올라갈 큰 문구, 15자 이내
- ad_copy.subline : 헤드를 받쳐주는 문구, 25자 이내
- ad_copy.cta : 행동 유도 문구, 10자 이내
- caption : 인스타그램 게시글 본문 150~250자, 2~3문단으로 줄바꿈. 첫 문장에 핵심 메시지를 담고, 마지막 문장은 자연스러운 행동 유도로 마무리
- hashtags : 해시태그 5~10개, 각각 #으로 시작

헤드 + 서브 + CTA + 본문을 합쳐 {MAX_COPY_CHARS}자를 넘기지 마.

[규칙]
- 사용자가 입력하지 않은 효능·성분·용량·수치·특징을 만들어내지 마. 사진에서 읽은 라벨 글자도 카피의 근거로 쓰지 마
- 브랜드명·제품명은 사용자 입력 그대로 써
- 일반 화장품(기능성 아님)이면 미백, 주름 개선, 자외선 차단 같은 기능성 효능을 쓰거나 암시하지 마
- 기능성 화장품이어도 효능을 과장하지 마
- 의약품처럼 보이는 표현(치료, 재생, 염증 완화 등), 최고·1위 같은 최상급 표현, 전문가·매체 추천, 가상 후기를 쓰지 마
- 조사 결과의 유사 제품 내용은 방향 참고만 하고, 다른 브랜드명이나 문구를 그대로 쓰지 마"""


def _build_input(
    product: ProductInput, analysis: ProductAnalysis, research: ResearchResult
) -> str:
    r = research.research
    insights = (
        "\n".join(
            f"- [{i.source}] {i.text}"
            for i in [*r.market_insights, *r.similar_products]
        )
        or "- 없음"
    )
    return f"""[사용자 입력]
- 브랜드명 : {product.brand_name or "미입력"}
- 제품명 : {product.product_name}
- 제품 카테고리 : {product.product_category or "미입력"}
- 제품 특징 : {product.features}
- 광고 목적 : {product.ad_purpose}
- 기능성 화장품 : {"예" if product.is_functional else "아니오"}

[사진 분석 (AI 추론)]
- 제품 종류 : {analysis.product_type}
- 용기 : {analysis.container_type}
- 용기 색 : {", ".join(analysis.colors) or "없음"}

[기획 AI 조사]
- 제품 요약 : {r.product_summary}
- 표현 범위 : {r.functional_notes}
- 광고 방향 : {r.ad_direction}
- 시장·유사 제품 :
{insights}"""


def copy_lengths(output: AdCopyOutput) -> dict[str, int]:
    """항목별 글자 수 (total = 헤드 + 서브 + CTA + 본문, 해시태그 제외)"""
    lengths = {
        "headline": len(output.ad_copy.headline),
        "subline": len(output.ad_copy.subline),
        "cta": len(output.ad_copy.cta),
        "caption": len(output.caption),
    }
    lengths["total"] = sum(lengths.values())
    lengths["hashtags_count"] = len(output.hashtags)
    return lengths


def generate_copy(
    product: ProductInput,
    analysis: ProductAnalysis,
    research: ResearchResult,
    model: str = MODEL_TEXT,
    reasoning_effort: str | None = None,
) -> AdCopyOutput:
    """기획 + 카피 생성 (1회 호출, 실패 시 LLMError). 400자 초과는 경고만"""
    output = call_structured(
        _build_input(product, analysis, research),
        AdCopyOutput,
        instructions=INSTRUCTIONS,
        model=model,
        reasoning_effort=reasoning_effort,
    )
    lengths = copy_lengths(output)
    if lengths["total"] > MAX_COPY_CHARS:
        logger.warning("카피 %d자, 기준 %d자 초과", lengths["total"], MAX_COPY_CHARS)
    logger.info("카피 글자 수 %s", lengths)
    return output
