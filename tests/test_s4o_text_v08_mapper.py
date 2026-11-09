"""Unit-only S4 Text -> Serving boundary. No Text client, image SDK or network."""
import json
from copy import deepcopy
from pathlib import Path

import pytest

from src.serving.text_v08_mapper import (
    TextBoundaryError, verify_analysis, verify_research, verify_copy, verify_prompt,
)

FIX = Path(__file__).resolve().parents[1] / "docs/contracts/fixtures"


def fixture(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def vlm(**changes):
    return {"analysis": fixture("product_analysis.json"),
            "analysis_succeeded": True, "error": None, **changes}


def research(**changes):
    return {**fixture("research_result_no_search.json"), **changes}


def copy():
    return fixture("ad_copy_output.json")


def prompt():
    return fixture("image_prompt_output.json")


def assert_block(code, fn, *args, **kwargs):
    with pytest.raises(TextBoundaryError) as exc:
        fn(*args, **kwargs)
    assert exc.value.code == code
    assert str(exc.value) == code


def test_analysis_valid_and_not_reconstructed_from_image_dump():
    value = vlm()
    result = verify_analysis(value)
    assert result.raw == value
    assert result.image_owner_input == value
    value["analysis"]["is_cosmetic"] = False
    assert result.raw["analysis"]["is_cosmetic"] is True


@pytest.mark.parametrize("field,value,code", [
    ("analysis_succeeded", False, "VLM_FAILED"),
    ("analysis_succeeded", "true", "VLM_INVALID_RESULT"),
    ("analysis_succeeded", 1, "VLM_INVALID_RESULT"),
    ("analysis_succeeded", None, "VLM_INVALID_RESULT"),
    ("error", "provider transient private error", "VLM_FAILED"),
    ("error", "", "VLM_FAILED"),
    ("error", {"text": "provider"}, "VLM_INVALID_RESULT"),
    ("analysis", {"is_cosmetic": False}, "VLM_NOT_COSMETIC"),
    ("analysis", {"is_cosmetic": "true"}, "VLM_INVALID_RESULT"),
    ("analysis", {"is_cosmetic": 1}, "VLM_INVALID_RESULT"),
    ("analysis", {}, "VLM_INVALID_RESULT"),
])
def test_vlm_rejects_failures_and_coercions(field, value, code):
    assert_block(code, verify_analysis, vlm(**{field: value}))


def test_vlm_default_cosmetic_true_with_failed_flag_is_rejected():
    assert_block("VLM_FAILED", verify_analysis, vlm(analysis_succeeded=False))


@pytest.mark.parametrize("performed,error,citations,expected", [
    (False, None, [], "search_not_performed"),
    (False, "provider failure", [], "research_failed_fallback"),
    (True, None, [], "search_completed_uncited"),
    (True, None, [{"title": "Source", "url": "https://example.org/research"}], "search_completed_uncited"),
])
def test_research_failure_vs_not_performed_vs_citation(performed,error,citations,expected):
    original = research(research_performed=performed,error=error,citations=citations)
    # Deliberately insert unverified search labels for downgrade test.
    original["research"]["display_summary"][0]["source"] = "검색 결과"
    before = deepcopy(original)
    checked = verify_research(original)
    assert checked.outcome == expected
    assert checked.original == before
    assert original == before
    # Global citations cannot substantiate this particular item.
    assert checked.display["research"]["display_summary"][0]["source"] == "AI 추론"
    assert checked.display["citations"] == []
    if not performed or error is not None:
        assert checked.display["research_performed"] is False
    else:
        assert checked.display["research_performed"] is True


def test_research_error_keeps_raw_evidence_but_downgrades_display():
    original = research(research_performed=True, error="timeout",
                        citations=[{"url":"https://example.org", "title":None}])
    snap = verify_research(original)
    assert snap.original["research_performed"] is True
    assert snap.original["citations"]
    assert snap.original["error"] == "timeout"
    assert snap.display["citations"] == []
    assert snap.display["research_performed"] is False
    assert snap.outcome == "research_failed_fallback"


def test_research_screen_never_contains_provider_error_original_retained():
    secret = "https://provider.invalid/trace?api_key=FAKE_SECRET_123456"
    data = research(research_performed=False, error=secret)
    snap = verify_research(data)
    assert snap.original["error"] == secret
    assert snap.display["error"] == "RESEARCH_UNAVAILABLE"
    assert secret not in json.dumps(snap.display, ensure_ascii=False)
    assert snap.outcome == "research_failed_fallback"


def test_single_global_citation_does_not_verify_unrelated_search_claims():
    data = research(research_performed=True, error=None, citations=[
        {"title": "Research A", "url": "https://example.org/cited-a"},
    ])
    for key in ("market_insights", "similar_products", "display_summary"):
        data["research"][key] = [
            {"text": "개별 URL 연결 없는 주장 1", "source": "검색 결과"},
            {"text": "개별 URL 연결 없는 주장 2", "source": "검색 결과"},
        ]
    result = verify_research(data)
    assert result.outcome == "search_completed_uncited"
    assert result.original["citations"] == data["citations"]
    assert result.display["citations"] == []
    for key in ("market_insights", "similar_products", "display_summary"):
        assert all(item["source"] == "AI 추론"
                   for item in result.display["research"][key])
        assert all(item["source"] == "검색 결과"
                   for item in result.original["research"][key])


@pytest.mark.parametrize("value", ["true", 1, None])
def test_research_does_not_coerce_performed(value):
    assert_block("RESEARCH_INVALID_RESULT",verify_research,
                 research(research_performed=value))


def test_copy_snapshot_is_immutable_sha256_and_complete():
    raw = copy()
    frozen = verify_copy(raw)
    assert set(frozen.output) == {"plan","ad_copy","caption","hashtags"}
    assert len(frozen.sha256) == 64
    raw["ad_copy"]["headline"] = "changed"
    assert frozen.output != raw
    assert frozen.sha256 == verify_copy(copy()).sha256


def test_copy_hash_changes_for_caption_hashtags_and_plan():
    start=verify_copy(copy()).sha256
    for key in ("caption", "hashtags", "plan"):
        changed=copy()
        if key=="caption":
            changed[key] += " 변경"
        elif key=="hashtags":
            changed[key].append("#새로운광고")
        else:
            changed[key]["concept"] += " 변경"
        assert verify_copy(changed).sha256 != start


def test_copy_rejects_missing_and_extra_fields():
    missing=copy()
    del missing["caption"]
    assert_block("COPY_INVALID_RESULT",verify_copy,missing)
    extra=copy()
    extra["compliance_passed"]=True
    assert_block("COPY_INVALID_RESULT",verify_copy,extra)


def test_prompt_korean_value_preservation():
    raw=prompt()
    mapped=verify_prompt(raw, verify_copy(copy()))
    assert mapped == raw
    assert any("\uac00" <= ch <= "\ud7a3" for ch in mapped["prompt"])


def test_prompt_plan_mismatch_is_rejected():
    value=prompt()
    value["concept"]="stale concept"
    assert_block("PROMPT_PLAN_MISMATCH",verify_prompt,value,verify_copy(copy()))
    value=prompt()
    value["mood"]=["임의 무드"]
    assert_block("PROMPT_PLAN_MISMATCH",verify_prompt,value,verify_copy(copy()))


def test_prompt_has_no_new_400_char_limit():
    raw=prompt()
    raw["prompt"]="한글" * 250
    assert verify_prompt(raw,verify_copy(copy()))["prompt"] == raw["prompt"]
