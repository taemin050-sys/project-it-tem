"""Track A Owner #27 v0.11 contract and current-review-to-LLM binding.

Entirely offline. No provider credential, request or billable execution.
"""
import pytest
import importlib
import socket
import sys

from demo_staging.live.contracts import strict_review
from demo_staging.live.pipeline import OfficialTextProvider
from src.text_generation.compliance.rule_checker import check_text
from src.text_generation.schemas import CopyRevisionOutput
from tests.demo_live.test_live_contracts import sample_input, safe_copy
from tests.demo_live.test_owner_text25_source_contract import inputs


@pytest.mark.parametrize(
    ("selected", "expected_risk", "expected_pass"),
    [
        (["주름개선"], "근거 확인 필요", True),
        (["미백"], "위반 의심", False),
        ([], "근거 확인 필요", True),
    ],
)
def test_owner27_functional_type_review_is_reason_independent(
    selected, expected_risk, expected_pass
):
    analysis, _, copy, _ = safe_copy()
    product = sample_input()["product"]
    product.update(is_functional=True, functional_types=selected)
    copy["ad_copy"]["headline"] = "주름 개선"
    report = strict_review(copy, product, analysis)
    matches = [
        item for item in report["issues"]
        if item["field"] == "headline"
        and item["text"] == "주름 개선"
        and item["category"] == "기능성 오인"
    ]
    assert len(matches) == 1
    issue = matches[0]
    assert issue["risk_level"] == expected_risk
    assert report["passed"] is expected_pass
    assert issue["basis_url"].startswith("https://")
    if selected == ["주름개선"]:
        # Owner #27 no longer encodes the functional type in parentheses.
        # Track A must not infer a violation from that wording change.
        assert "기능성(" not in issue["reason"]


@pytest.fixture
def no_billable_network_for_owner_module(monkeypatch):
    loaded_before=set(sys.modules)
    monkeypatch.setenv("OPENAI_API_KEY", "offline-test-not-provider-credential")
    def block_connection(*args, **kwargs):
        raise AssertionError("NETWORK_NOT_ALLOWED_IN_A1")
    monkeypatch.setattr(socket.socket, "connect", block_connection)
    monkeypatch.setattr(socket.socket, "connect_ex", block_connection)
    monkeypatch.setattr(socket, "create_connection", block_connection)
    yield
    for name in list(sys.modules):
        if (name not in loaded_before and name.startswith("src.text_generation.")
            and name.rsplit(".", 1)[-1] in
            ("config", "llm_client", "copy_generator", "cost")):
            sys.modules.pop(name, None)


def test_owner27_structured_compliance_issues_reach_revision_llm_input(
    monkeypatch, no_billable_network_for_owner_module
):
    copy=importlib.import_module("src.text_generation.copy_generator")
    product, analysis, research, original = inputs()
    issues = check_text("headline", "치료 효과", product, analysis)
    assert issues and any(x.risk_level == "위반 의심" for x in issues)
    seen = []

    def fake_llm(prompt, output_type, *, instructions, **settings):
        # This is the actual Owner #27 prompt-building code; only the
        # external LLM network transport is replaced with a fake.
        assert output_type is CopyRevisionOutput
        assert "[검수 결과]" in prompt
        assert "치료" in prompt
        assert "위반 의심" in prompt
        assert "의약품 오인" in prompt
        assert "검수 표현을 지워 줘" in prompt
        assert settings["model"] == "offline-test-only"
        seen.append(prompt)
        return CopyRevisionOutput(
            revised=original.model_copy(deep=True),
            changed_fields=[],
            note="기존 카피에 위험 표현이 없어 수정하지 않았습니다.",
        )

    monkeypatch.setattr(copy, "call_structured", fake_llm)
    result = OfficialTextProvider("offline-test-only", "unused").revise_copy(
        product, analysis, research, original, "검수 표현을 지워 줘",
        issues=issues,
    )
    assert len(seen) == 1
    assert result.changed_fields == []
    assert result.revised.model_dump() == original.model_dump()
