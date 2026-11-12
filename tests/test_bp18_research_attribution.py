"""F07 attribution uses synthetic responses and never imports a Provider client."""
import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from src.serving.text_v08_mapper import verify_research
from src.text_generation.research_evidence import citation_url, claim_sha256
from src.text_generation.schemas import (
    ProductAnalysis, ProductInput, ResearchOutput, ResearchResult,
)
from tests.demo_live.test_live_contracts import fixture, sample_input


@pytest.fixture
def researcher(monkeypatch):
    config = ModuleType("src.text_generation.config")
    config.MODEL_TEXT = "offline-fixture"
    config.REASONING_EFFORT = None
    client = ModuleType("src.text_generation.llm_client")
    client.LLMError = type("LLMError", (Exception,), {})

    def forbidden(*args, **kwargs):
        raise AssertionError("A test must inject its synthetic response")

    client.call_structured = forbidden
    monkeypatch.setitem(sys.modules, config.__name__, config)
    monkeypatch.setitem(sys.modules, client.__name__, client)
    spec = importlib.util.spec_from_file_location(
        "src.text_generation._offline_researcher",
        Path(__file__).resolve().parents[1] / "src/text_generation/researcher.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def inputs():
    return (
        ProductInput.model_validate(sample_input()["product"], strict=True),
        ProductAnalysis.model_validate(fixture("product_analysis.json"), strict=True),
    )


def output():
    data = fixture("research_result_no_search.json")["research"]
    data["market_insights"] = [
        {"text": "공식 발표에서 확인한 시장 정보 citefixture0", "source": "검색 결과"},
        {"text": "인용 없는 다른 시장 주장", "source": "검색 결과"},
    ]
    data["display_summary"] = [
        {"text": "보습과 촉촉한 사용감", "source": "사용자 입력"},
        {"text": "입력에 없는 성분 정보", "source": "사용자 입력"},
        {"text": "차분한 배경이 어울릴 수 있음", "source": "AI 추론"},
    ]
    return ResearchOutput.model_validate(data, strict=True)


def response(value, *, annotation=True, performed=True, wrong_text=False):
    raw = json.dumps(value.model_dump(mode="json"), ensure_ascii=False)
    marker = "citefixture0"
    start = raw.index(marker)
    citation = SimpleNamespace(
        type="url_citation",
        url="https://example.org/report?source=publisher&utm_source=fixture",
        title="공식 발표",
        start_index=start,
        end_index=start + len(marker),
    )
    if wrong_text:
        raw = raw.replace("공식 발표에서", "변경된 응답에서")
    message = SimpleNamespace(
        type="message",
        content=[SimpleNamespace(text=raw, annotations=[citation] if annotation else [])],
    )
    search = SimpleNamespace(
        type="web_search_call", status="completed" if performed else "failed",
    )
    return SimpleNamespace(output=[search, message])


def test_exact_annotation_survives_roundtrip_to_only_its_claim(researcher, monkeypatch):
    value = output()
    raw = response(value)
    calls = []

    def fake_call(*args, **kwargs):
        calls.append(kwargs)
        return value, raw

    monkeypatch.setattr(researcher, "call_structured", fake_call)
    result = researcher.research(*inputs(), model="offline-fixture")
    restored = ResearchResult.model_validate_json(result.model_dump_json(), strict=True)
    checked = verify_research(restored, model=ResearchResult)
    market = checked.display["research"]["market_insights"]
    assert checked.outcome == "search_cited"
    assert market[0] == {
        "text": "공식 발표에서 확인한 시장 정보",
        "source": "검색 결과",
        "citations": [{"url": "https://example.org/report?source=publisher", "title": "공식 발표"}],
    }
    assert market[1]["source"] == "AI 추론"
    summary = checked.display["research"]["display_summary"]
    assert summary[0]["source"] == "사용자 입력"
    assert summary[1]["source"] == "AI 추론"
    assert summary[2]["source"] == "AI 추론"
    assert result.citations[0].claims[0].text_sha256 == claim_sha256(market[0]["text"])
    assert len(calls) == 1
    assert calls[0]["tools"] == [{"type": "web_search"}]


@pytest.mark.parametrize("case", ["no_annotation", "wrong_text", "search_failed", "outside_claim"])
def test_unbound_or_unsuccessful_search_is_inference(researcher, monkeypatch, case):
    value = output()
    raw = response(
        value, annotation=case != "no_annotation",
        performed=case != "search_failed", wrong_text=case == "wrong_text",
    )
    if case == "outside_claim":
        citation = raw.output[-1].content[0].annotations[0]
        citation.start_index, citation.end_index = 0, 3
    monkeypatch.setattr(researcher, "call_structured", lambda *args, **kwargs: (value, raw))
    result = researcher.research(*inputs())
    checked = verify_research(result, model=ResearchResult)
    assert all(item["source"] == "AI 추론" for item in checked.display["research"]["market_insights"])
    assert checked.display["citations"] == []
    assert checked.outcome == ("search_not_performed" if case == "search_failed"
                               else "search_completed_uncited")


def test_provider_error_falls_back_once_with_safe_error(researcher, monkeypatch):
    calls = []

    def failure(*args, **kwargs):
        calls.append(1)
        raise researcher.LLMError("private-provider-error")

    monkeypatch.setattr(researcher, "call_structured", failure)
    result = researcher.research(*inputs())
    checked = verify_research(result, model=ResearchResult)
    assert calls == [1]
    assert checked.outcome == "research_failed_fallback"
    assert checked.display["research_performed"] is False
    assert checked.display["error"] == "RESEARCH_UNAVAILABLE"
    assert "private-provider-error" not in json.dumps(checked.display)


def test_claim_copy_or_index_tamper_cannot_reuse_a_link(researcher):
    original = output()
    citations = researcher._extract_citations(response(original), original)
    researcher._clean_output(original)
    payload = ResearchResult(
        research=original, citations=citations, research_performed=True,
    ).model_dump(mode="json")
    for case in ("text", "index"):
        changed = deepcopy(payload)
        if case == "text":
            changed["research"]["market_insights"][0]["text"] = "현재 문장에 맞지 않는 예전 근거"
        else:
            changed["citations"][0]["claims"][0]["index"] = 1
        checked = verify_research(changed, model=ResearchResult)
        assert checked.display["citations"] == []
        assert checked.display["research"]["market_insights"][0]["source"] == "AI 추론"


@pytest.mark.parametrize("url", [
    "javascript:alert(1)", "file:///tmp/private", "https://user:secret@example.org/report",
    "https://example.org:invalid", "https://example.org/\nprivate", "https:\\example.org/report",
])
def test_unsafe_citation_urls_are_rejected(url):
    assert citation_url(url) is None
