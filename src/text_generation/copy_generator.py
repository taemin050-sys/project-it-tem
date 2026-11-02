"""기획 + 카피 생성 : ProductInput + ProductAnalysis + ResearchResult → AdCopyOutput (검색 없이 1회 호출)"""

import logging

from .config import MODEL_TEXT, REASONING_EFFORT
from .llm_client import call_structured
from .schemas import AdCopyOutput, ProductAnalysis, ProductInput, ResearchResult

logger = logging.getLogger(__name__)

MAX_COPY_CHARS = 400  # 헤드 + 서브 + CTA + 본문 합계 (해시태그 제외), 임시 기준

# 이미지 합성 A 템플릿 기준 (10/30 이미지 담당 합의, 공백·문장부호 포함, 줄바꿈 제외)
HEADLINE_MAX = 15
SUBLINE_MAX = 25
SUBLINE_LINE_MAX = 15
SUBLINE_MAX_LINES = 2
CTA_MAX = 10

INSTRUCTIONS = f"""너는 소상공인 화장품 브랜드의 인스타그램 피드 광고 카피라이터야.
제품 정보, 사진 분석, 기획 AI 조사 결과를 보고 광고 기획과 카피를 만들어.

[출력 항목]
- plan.target : 광고 타깃 1문장
- plan.concept : 광고 콘셉트 1문장
- plan.key_message : 가장 전하고 싶은 메시지 1문장
- plan.tone : 카피 톤 (예: 친근한, 차분한, 고급스러운)
- plan.mood : 이미지 배경 분위기 2~3개, 한국어 한 단어씩 (예: 청량, 내추럴)
- ad_copy.headline : 이미지 위에 올라갈 큰 문구, {HEADLINE_MAX}자 이내 한 줄 (줄바꿈 없이)
- ad_copy.subline : 헤드를 받쳐주는 문구, 총 {SUBLINE_MAX}자 이내. {SUBLINE_LINE_MAX}자 이하면 한 줄로 쓰고, {SUBLINE_LINE_MAX}자를 넘으면 의미 단위로 끊어 줄바꿈(\\n)을 한 번 넣어 두 줄로 써. 각 줄은 {SUBLINE_LINE_MAX}자 이내
- ad_copy.cta : 행동 유도 문구, {CTA_MAX}자 이내 한 줄 (줄바꿈 없이)
- caption : 인스타그램 게시글 본문 150~250자, 2~3문단으로 줄바꿈. 첫 문장에 핵심 메시지를 담고, 마지막 문장은 자연스러운 행동 유도로 마무리
- hashtags : 해시태그 5~10개, 각각 #으로 시작

헤드·서브·CTA 글자 수는 공백과 문장부호를 포함하고 줄바꿈은 빼고 세.
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


def _count(text: str) -> int:
    """줄바꿈을 뺀 글자 수 (공백·문장부호 포함)"""
    return len(text.replace("\n", ""))


def _normalize_subline(text: str) -> str:
    """줄 앞뒤 공백과 빈 줄 정리 (예: '몸까지,\\n 끈적임' → '몸까지,\\n끈적임')"""
    lines = [line.strip() for line in text.replace("\r\n", "\n").split("\n")]
    return "\n".join(line for line in lines if line)


def copy_lengths(output: AdCopyOutput) -> dict[str, int]:
    """항목별 글자 수 (헤드·서브·CTA는 줄바꿈 제외, total = 헤드 + 서브 + CTA + 본문, 해시태그 제외)"""
    sub_lines = output.ad_copy.subline.split("\n")
    lengths = {
        "headline": _count(output.ad_copy.headline),
        "subline": _count(output.ad_copy.subline),
        "cta": _count(output.ad_copy.cta),
        "caption": len(output.caption),
    }
    lengths["total"] = sum(lengths.values())
    lengths["subline_lines"] = len(sub_lines)
    lengths["subline_line_max"] = max(len(line) for line in sub_lines)
    lengths["hashtags_count"] = len(output.hashtags)
    return lengths


def check_copy_limits(output: AdCopyOutput) -> list[str]:
    """이미지 위 문구(헤드·서브·CTA) 기준 초과 항목 (경고용, 차단·재생성 없음)"""
    n = copy_lengths(output)
    warnings = []
    if n["headline"] > HEADLINE_MAX:
        warnings.append(f"헤드 {n['headline']}자 (기준 {HEADLINE_MAX}자)")
    if "\n" in output.ad_copy.headline:
        warnings.append("헤드에 줄바꿈 있음 (기준 1줄)")
    if n["subline"] > SUBLINE_MAX:
        warnings.append(f"서브 {n['subline']}자 (기준 {SUBLINE_MAX}자)")
    if n["subline_lines"] > SUBLINE_MAX_LINES:
        warnings.append(f"서브 {n['subline_lines']}줄 (기준 {SUBLINE_MAX_LINES}줄)")
    if n["subline_line_max"] > SUBLINE_LINE_MAX:
        warnings.append(
            f"서브 한 줄 {n['subline_line_max']}자 (기준 {SUBLINE_LINE_MAX}자)"
        )
    if n["cta"] > CTA_MAX:
        warnings.append(f"CTA {n['cta']}자 (기준 {CTA_MAX}자)")
    if "\n" in output.ad_copy.cta:
        warnings.append("CTA에 줄바꿈 있음 (기준 1줄)")
    if n["total"] > MAX_COPY_CHARS:
        warnings.append(f"카피 합계 {n['total']}자 (기준 {MAX_COPY_CHARS}자)")
    return warnings


def generate_copy(
    product: ProductInput,
    analysis: ProductAnalysis,
    research: ResearchResult,
    model: str = MODEL_TEXT,
    reasoning_effort: str | None = REASONING_EFFORT,
) -> AdCopyOutput:
    """기획 + 카피 생성 (1회 호출, 실패 시 LLMError). 글자 수 기준 초과는 경고만"""
    output = call_structured(
        _build_input(product, analysis, research),
        AdCopyOutput,
        instructions=INSTRUCTIONS,
        model=model,
        reasoning_effort=reasoning_effort,
    )
    output.ad_copy.subline = _normalize_subline(output.ad_copy.subline)

    for w in check_copy_limits(output):
        logger.warning("글자 수 기준 초과 : %s", w)
    logger.info("카피 글자 수 %s", copy_lengths(output))
    return output
