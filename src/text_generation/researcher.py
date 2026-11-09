"""기획 AI 사전 조사 : ProductInput + ProductAnalysis → ResearchResult (웹 검색 1회 호출)"""

import json
import logging
import re
from datetime import date
from typing import Any

from .config import MODEL_TEXT, REASONING_EFFORT
from .llm_client import LLMError, call_structured
from .research_evidence import CLAIM_SECTIONS, citation_url, claim_sha256
from .schemas import (
    Citation,
    ClaimCitation,
    ProductAnalysis,
    ProductInput,
    ResearchClaimReference,
    ResearchOutput,
    ResearchResult,
    SummaryLine,
)

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOOL_CALLS = 2

_PAREN_LINK = re.compile(r"\s*\(\[[^\]]*\]\([^)]*\)\)")
_MD_LINK = re.compile(r"\s*\[[^\]]*\]\([^)]*\)")
_BARE_LINK = re.compile(r"https?://[^\s\])>\"}]+", re.IGNORECASE)
_CITATION_MARKER = re.compile(r"cite[^]*")
_JSON_CLAIM = re.compile(r'(?<!\\)"text"\s*:\s*("(?:[^"\\]|\\.)*")')
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
- functional_notes : 기능성 여부에 따라 쓸 수 있는 효능 표현 범위 1문장. 사용자 입력에 의약품으로 오인될 수 있는 표현이 있으면 기능성 효능과 구분해서 "의약품 오인 표현이라 사용 불가"라고 함께 적어
- market_insights : 시장 트렌드 2~3개, 각 한 문장
- similar_products : 유사 제품의 특징과 광고 방향 2~3개, 각 한 문장
- ad_direction : 광고 방향 1~2문장 (톤·무드는 정하지 마. 다음 단계에서 정함)
- display_summary : 사용자 화면에 보여줄 조사 요약 3~5줄, 한 줄 40자 이내

[출처 source]
- 사용자 입력 : 사용자가 입력한 제품 정보에 있는 원문 그대로
- 검색 결과 : 이번 웹 검색 결과에서 직접 확인한 사실만
- AI 추론 : 사진 분석 결과, 일반 지식, 그리고 검색 결과를 바탕으로 한 너의 판단·제안·광고 아이디어
- display_summary도 같은 기준으로 표시해
- 출처는 source에만 적고, text에는 출처 이름(사용자 입력, 검색 결과, AI 추론)을 쓰지 마
- 검색으로 확인하지 못한 내용을 검색 결과라고 표시하지 마
- 검색 결과의 각 문장은 검색 도구가 확인한 사실 하나만 담고, 같은 text 값 안에 실제 검색 인용을 붙여. 검색 인용이 없으면 AI 추론으로 표시해

[규칙]
- 브랜드명·제품명은 사용자 입력을 그대로 써. 사진에서 읽은 라벨 글자는 틀릴 수 있으니 확인된 사실로 쓰지 마
- 사용자가 입력하지 않은 효능·성분을 만들어내지 마
- 일반 화장품(기능성 아님)이면 미백, 주름 개선, 자외선 차단 같은 기능성 효능 표현은 쓸 수 없다고 functional_notes에 적어
- 기능성 화장품이면 심사·보고된 효능 범위 안에서만 표현할 수 있고 근거 확인이 필요하다고 적어
- 치료, 재생, 염증·피부염 완화, 질환명처럼 병을 고치거나 피부를 회복시키는 표현은 기능성 효능이 아니라 의약품으로 오인될 수 있는 표현이야. 기능성 화장품이어도 쓸 수 없고, 이런 표현을 "기능성 효능"이라고 부르지 마
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


def _strip_links(text: str) -> str:
    """표시용 본문에서 인용 링크를 분리한다."""
    text = _CITATION_MARKER.sub("", text)
    return _BARE_LINK.sub("", _MD_LINK.sub("", _PAREN_LINK.sub("", text))).strip()


def _strip_source_prefix(text: str) -> str:
    """text 앞에 붙은 출처 이름 제거 (예: '검색 결과: ...')"""
    return _SOURCE_PREFIX.sub("", text)


def _clean_output(output: ResearchOutput) -> ResearchOutput:
    output.product_summary = _strip_links(output.product_summary)
    output.functional_notes = _strip_links(output.functional_notes)
    output.ad_direction = _strip_links(output.ad_direction)
    for section in CLAIM_SECTIONS:
        for item in getattr(output, section):
            item.text = _strip_source_prefix(_strip_links(item.text))
    return output


def _claim_spans(raw: object, output: ResearchOutput):
    """Find exact JSON text values in the response used for structured parsing."""
    if not isinstance(raw, str):
        return []
    try:
        data = json.loads(raw)
    except ValueError:
        return []
    if data != output.model_dump(mode="json"):
        return []
    claims = [
        (section, index, item)
        for section in data if section in CLAIM_SECTIONS
        for index, item in enumerate(data[section])
    ]
    spans = list(_JSON_CLAIM.finditer(raw))
    if [json.loads(match[1]) for match in spans] != [item["text"] for _, _, item in claims]:
        return []

    # A range must identify the same field whether the indices count Unicode
    # characters or UTF-16 code units. This is identical for Hangul and ASCII.
    def units(offset: int) -> int:
        return len(raw[:offset].encode("utf-16-le", errors="surrogatepass")) // 2

    return [
        (section, index, item, units(match.start(1) + 1), match.end(1) - 1)
        for (section, index, item), match in zip(claims, spans, strict=True)
    ]


def _extract_citations(res: Any, output: ResearchOutput) -> list[ClaimCitation | Citation]:
    """Bind only Provider citation ranges contained in the exact claim value."""
    citations: dict[str, Citation] = {}
    references: dict[str, list[ResearchClaimReference]] = {}
    for item in res.output:
        for c in getattr(item, "content", None) or []:
            spans = _claim_spans(getattr(c, "text", None), output)
            for a in getattr(c, "annotations", None) or []:
                if getattr(a, "type", None) != "url_citation":
                    continue
                url = citation_url(getattr(a, "url", None))
                if url is None:
                    continue
                title = getattr(a, "title", None)
                citations.setdefault(url, Citation(title=title if isinstance(title, str) else None, url=url))
                start, end = getattr(a, "start_index", None), getattr(a, "end_index", None)
                if type(start) is not int or type(end) is not int or start >= end:
                    continue
                for section, index, claim, first, last in spans:
                    if claim["source"] != "검색 결과" or not first <= start < end <= last:
                        continue
                    text = _strip_source_prefix(_strip_links(claim["text"]))
                    if not text:
                        continue
                    ref = ResearchClaimReference(section=section, index=index, text_sha256=claim_sha256(text))
                    refs = references.setdefault(url, [])
                    if ref not in refs:
                        refs.append(ref)
    return [
        ClaimCitation(title=c.title, url=url, claims=references[url]) if url in references else c
        for url, c in citations.items()
    ]


def _search_succeeded(res: Any) -> bool:
    """웹 검색이 1번이라도 완료됐는지"""
    return any(
        item.type == "web_search_call" and item.status == "completed"
        for item in res.output
    )


def _check_sources(output: ResearchOutput, citations: list[ClaimCitation | Citation], product: ProductInput) -> None:
    sourced = {
        (claim.section, claim.index, claim.text_sha256)
        for citation in citations if isinstance(citation, ClaimCitation)
        for claim in citation.claims
    }
    user_values = (product.brand_name, product.product_name, product.product_category,
                   product.features, product.ad_purpose)
    for section in CLAIM_SECTIONS:
        for index, item in enumerate(getattr(output, section)):
            if item.source == "검색 결과" and (section, index, claim_sha256(item.text)) not in sourced:
                item.source = "AI 추론"
            if item.source == "사용자 입력" and not (
                item.text and any(value and item.text in value for value in user_values)
            ):
                item.source = "AI 추론"


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
    except LLMError:
        logger.warning("기획 AI 조사 실패, 기본 조사로 대체")
        return ResearchResult(
            research=default_research(product, analysis),
            citations=[],
            research_performed=False,
            error="RESEARCH_UNAVAILABLE",
        )

    performed = _search_succeeded(res)
    citations = _extract_citations(res, output) if performed else []
    _clean_output(output)
    _check_sources(output, citations, product)
    if not performed:
        logger.warning("웹 검색이 수행되지 않음 (호출은 성공)")

    search_calls = sum(1 for item in res.output if item.type == "web_search_call")
    logger.info(
        "검색 %d회 (완료 %s) | 인용 %d개", search_calls, performed, len(citations)
    )
    return ResearchResult(
        research=output, citations=citations, research_performed=performed
    )
