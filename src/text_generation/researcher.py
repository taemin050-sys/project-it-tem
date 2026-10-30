"""기획 AI 사전 조사 : ProductInput + ProductAnalysis → ResearchResult (웹 검색 1회 호출)"""

import logging
import re
from datetime import date
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .config import MODEL_TEXT, REASONING_EFFORT
from .llm_client import LLMError, call_structured
from .schemas import (
    Citation,
    ProductAnalysis,
    ProductInput,
    ResearchOutput,
    ResearchResult,
    SummaryLine,
)

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOOL_CALLS = 2

_PAREN_LINK = re.compile(r"\s*\(\[[^\]]*\]\([^)]*\)\)")
_MD_LINK = re.compile(r"\s*\[[^\]]*\]\([^)]*\)")
_SOURCE_PREFIX = re.compile(
    r"^\s*(?:\[(?:사용자 입력|검색 결과|AI 추론)\]|(?:사용자 입력|검색 결과|AI 추론)\s*[:：])\s*"
)

INSTRUCTIONS = """너는 소상공인 화장품 브랜드의 인스타그램 피드 광고를 기획하는 기획 AI야.
제품 정보와 사진 분석 결과를 보고, 웹 검색으로 시장과 유사 제품을 조사한 뒤 광고 방향을 정해.

[결과물]
- 이 광고의 결과물은 사용자가 올린 제품 사진을 AI가 만든 배경에 합성하고 카피를 얹은 인스타그램 피드 이미지 1장이야
- 영상, 모델·사람 등장, 사용 전후 비교, 피부·입술 클로즈업처럼 이 형식으로 만들 수 없는 연출은 제안하지 마

[검색]
- 이 제품 카테고리의 최근 시장 트렌드와 유사 제품의 광고 포인트만 검색해
- 최근 자료를 우선해. 오래된 자료는 쓰지 마

[출력 항목]
- product_summary : 사용자 입력을 바탕으로 제품을 2문장으로 요약. 사진 라벨에서 읽은 성분·효능은 넣지 마 (용기 모양·색은 써도 됨)
- functional_notes : 기능성 여부에 따라 쓸 수 있는 효능 표현 범위 1문장
- market_insights : 시장 트렌드 2~3개, 각 한 문장
- similar_products : 유사 제품의 특징과 광고 방향 2~3개, 각 한 문장
- ad_direction : 광고 방향 1~2문장 (톤·무드는 정하지 마. 다음 단계에서 정함)
- display_summary : 사용자 화면에 보여줄 조사 요약 3~5줄, 한 줄 40자 이내

[출처 source]
- 사용자 입력 : 사용자가 입력한 제품 정보를 정리한 내용
- 검색 결과 : 이번 웹 검색 결과에서 직접 확인한 사실만
- AI 추론 : 사진 분석 결과, 일반 지식, 그리고 검색 결과를 바탕으로 한 너의 판단·제안·광고 아이디어
- display_summary도 같은 기준으로 표시해
- 출처는 source에만 적고, text에는 출처 이름(사용자 입력, 검색 결과, AI 추론)을 쓰지 마
- 검색으로 확인하지 못한 내용을 검색 결과라고 표시하지 마
- 검색 결과로 표시한 문장에는 출처 링크를 달아

[규칙]
- 브랜드명·제품명은 사용자 입력을 그대로 써. 사진에서 읽은 라벨 글자는 틀릴 수 있으니 확인된 사실로 쓰지 마
- 사용자가 입력하지 않은 효능·성분을 만들어내지 마
- 일반 화장품(기능성 아님)이면 미백, 주름 개선, 자외선 차단 같은 기능성 효능 표현은 쓸 수 없다고 functional_notes에 적어
- 기능성 화장품이면 심사·보고된 효능 범위 안에서만 표현할 수 있고 근거 확인이 필요하다고 적어
- 유사 제품의 광고 문구는 방향 참고용으로만 정리하고, 문구를 그대로 옮겨 적지 마"""


def _build_input(product: ProductInput, analysis: ProductAnalysis) -> str:
    """사용자 입력 + 사진 분석 요약을 프롬프트 텍스트로"""
    return f"""오늘 날짜 : {date.today().isoformat()}

[사용자 입력]
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
- 라벨에서 읽은 글자 : {", ".join(analysis.label_text) or "없음"}"""


def _clean_url(url: str) -> str:
    """utm_ 추적 값 제거 (예: ?utm_source=openai)"""
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query) if not k.startswith("utm_")]
    return urlunsplit(parts._replace(query=urlencode(query)))


def _strip_links(text: str) -> str:
    """본문에 붙은 마크다운 링크 제거 (화면 표시용)"""
    return _MD_LINK.sub("", _PAREN_LINK.sub("", text)).strip()


def _strip_source_prefix(text: str) -> str:
    """text 앞에 붙은 출처 이름 제거 (예: '검색 결과: ...')"""
    return _SOURCE_PREFIX.sub("", text)


def _clean_output(output: ResearchOutput) -> ResearchOutput:
    output.product_summary = _strip_links(output.product_summary)
    output.functional_notes = _strip_links(output.functional_notes)
    output.ad_direction = _strip_links(output.ad_direction)
    for item in [
        *output.market_insights,
        *output.similar_products,
        *output.display_summary,
    ]:
        item.text = _strip_source_prefix(_strip_links(item.text))
    return output


def _extract_citations(res: Any) -> list[Citation]:
    """응답의 url_citation만 모아서 Citation 목록으로 (utm 제거, 중복 URL 제거)"""
    citations: dict[str, Citation] = {}
    for item in res.output:
        for c in getattr(item, "content", None) or []:
            for a in getattr(c, "annotations", None) or []:
                if a.type != "url_citation":
                    continue
                url = _clean_url(a.url)
                if url not in citations:
                    citations[url] = Citation(title=a.title, url=url)
    return list(citations.values())


def _search_succeeded(res: Any) -> bool:
    """웹 검색이 1번이라도 완료됐는지"""
    return any(
        item.type == "web_search_call" and item.status == "completed"
        for item in res.output
    )


def _downgrade_search_sources(output: ResearchOutput) -> ResearchOutput:
    """인용이 없는데 '검색 결과'로 표시된 항목 → 'AI 추론'"""
    for item in [
        *output.market_insights,
        *output.similar_products,
        *output.display_summary,
    ]:
        if item.source == "검색 결과":
            item.source = "AI 추론"
    return output


def _functional_notes(product: ProductInput) -> str:
    if product.is_functional:
        return "기능성 화장품으로 입력됨. 기능성 효능은 심사·보고된 범위 안에서만 표현 가능, 근거 확인 필요."
    return "일반 화장품. 미백·주름 개선·자외선 차단 등 기능성 효능 표현 사용 불가."


def default_research(
    product: ProductInput, analysis: ProductAnalysis
) -> ResearchOutput:
    """검색·호출 실패 시 입력 정보와 사진 분석만으로 채운 기본 조사 (전부 AI 추론)"""
    name = " ".join(filter(None, [product.brand_name, product.product_name]))
    return ResearchOutput(
        product_summary=f"{name} ({analysis.product_type}, {analysis.container_type} 용기). 특징 : {product.features}",
        functional_notes=_functional_notes(product),
        market_insights=[],
        similar_products=[],
        ad_direction=f"광고 목적({product.ad_purpose})에 맞춰 사용자가 입력한 제품 특징 중심으로 표현.",
        display_summary=[
            SummaryLine(text="시장·유사 제품 조사를 하지 못했어요", source="AI 추론"),
            SummaryLine(text="입력한 제품 특징 중심으로 기획했어요", source="AI 추론"),
            SummaryLine(
                text="기능성 표현 근거 확인 필요"
                if product.is_functional
                else "기능성 효능 표현은 쓸 수 없어요",
                source="AI 추론",
            ),
        ],
    )


def research(
    product: ProductInput,
    analysis: ProductAnalysis,
    model: str = MODEL_TEXT,
    max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS,
    reasoning_effort: str | None = REASONING_EFFORT,
) -> ResearchResult:
    """기획 AI 사전 조사 (웹 검색 포함 1회 호출, 실패 시 재호출 없이 기본 조사)"""
    try:
        output, res = call_structured(
            _build_input(product, analysis),
            ResearchOutput,
            instructions=INSTRUCTIONS,
            model=model,
            tools=[{"type": "web_search"}],
            max_tool_calls=max_tool_calls,
            reasoning_effort=reasoning_effort,
            return_raw=True,
        )
    except LLMError as e:
        logger.warning("기획 AI 조사 실패, 기본 조사로 대체: %s", e)
        return ResearchResult(
            research=default_research(product, analysis),
            citations=[],
            research_performed=False,
            error=str(e),
        )

    citations = _extract_citations(res)
    output = _clean_output(output)
    performed = _search_succeeded(res)
    if not performed:
        logger.warning("웹 검색이 수행되지 않음 (호출은 성공)")
    if not citations:
        output = _downgrade_search_sources(output)

    search_calls = sum(1 for item in res.output if item.type == "web_search_call")
    logger.info(
        "검색 %d회 (완료 %s) | 인용 %d개", search_calls, performed, len(citations)
    )
    return ResearchResult(
        research=output, citations=citations, research_performed=performed
    )
