"""Owner Text #25 real Python function contracts without external API or payment.

No network permitted. Model return values are deterministic local mocks.
"""
from __future__ import annotations
import importlib
import socket
import sys

import pytest

from src.text_generation.schemas import (
    AdCopyOutput,AdPlan,CopySet,ProductInput,ProductAnalysis,
    ResearchResult,ResearchOutput,ImagePromptOutput,CopyRevisionOutput,
    ImagePromptRevisionOutput,
)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    # Owner function tests must not pollute the hosting pytest process with
    # model clients. Older fail-closed tests assert the client has never been
    # imported by disabled worker startup.
    original_imports=set(sys.modules)
    monkeypatch.setenv("OPENAI_API_KEY","offline-test-not-provider-credential")
    def no_connection(*args,**kwargs):
        raise AssertionError("NETWORK_NOT_ALLOWED")
    monkeypatch.setattr(socket.socket,"connect",no_connection)
    monkeypatch.setattr(socket.socket,"connect_ex",no_connection)
    monkeypatch.setattr(socket,"create_connection",no_connection)
    yield
    for key in tuple(sys.modules):
        if (key not in original_imports and key.startswith("src.text_generation.")
            and key.rsplit(".",1)[-1] in (
                "copy_generator","image_prompt_generator","llm_client","config","cost")):
            sys.modules.pop(key,None)


def inputs():
    product=ProductInput(
        product_name="데일리 크림",brand_name="라움",features="촉촉한 사용감",
        ad_purpose="신제품 홍보",product_category="스킨케어",
        is_functional=True,functional_types=["자외선차단"],
        emoji_level="많이",photo_verified=True,product_image_count=2)
    analysis=ProductAnalysis(is_cosmetic=True,product_type="스킨케어",
        container_type="튜브",colors=["흰색"],label_text=[],
        mood=["청량"],is_transparent=False)
    research=ResearchResult(research=ResearchOutput(
        product_summary="크림",functional_notes="근거 확인 필요",
        market_insights=[],similar_products=[],ad_direction="보습 강조",
        display_summary=[]),research_performed=False)
    original=AdCopyOutput(plan=AdPlan(target="고객",concept="보습 컨셉",
        key_message="촉촉함",tone="따뜻한",mood=["청량"]),
        ad_copy=CopySet(headline="산뜻한 하루",subline="매일 보습",cta="더 알아보기"),
        caption="라움 데일리 크림의 사용감",hashtags=["#보습"])
    return product,analysis,research,original


def test_copy_revision_real_owner_function_preserves_other_fields(monkeypatch):
    mod=importlib.import_module("src.text_generation.copy_generator")
    product,analysis,research,original=inputs()
    def fake_structured(prompt,output_type,*,instructions,**kw):
        assert output_type is CopyRevisionOutput
        assert "자외선차단" in prompt
        assert "많이" in prompt and "헤드만" in prompt
        assert kw.get("model")=="offline-owner-text-test"
        revised=original.model_copy(deep=True)
        revised.ad_copy.headline="새로운 보습 하루"
        revised.caption="이것은 사용자가 요청하지 않은 변조"
        return CopyRevisionOutput(revised=revised,
            changed_fields=["headline"],note=None)
    monkeypatch.setattr(mod,"call_structured",fake_structured)
    result=mod.revise_copy(product,analysis,research,original,
         "헤드만 수정",model="offline-owner-text-test")
    assert result.changed_fields==["headline"]
    assert result.revised.ad_copy.headline=="새로운 보습 하루"
    assert result.revised.caption==original.caption
    assert result.revised.hashtags==original.hashtags
    assert result.revised.ad_copy.cta==original.ad_copy.cta


def test_owner_instruction_limit_before_network(monkeypatch):
    copy=importlib.import_module("src.text_generation.copy_generator")
    prompt=importlib.import_module("src.text_generation.image_prompt_generator")
    prod,analysis,research,previous=inputs()
    old_prompt=ImagePromptOutput(concept=previous.plan.concept,
        mood=previous.plan.mood,prompt="차분한 배경")
    def impossible(*args,**kw):
        raise AssertionError("SHOULD_NOT_CALL_PROVIDER")
    monkeypatch.setattr(copy,"call_structured",impossible)
    monkeypatch.setattr(prompt,"call_structured",impossible)
    for text in ("", "a"*301):
        with pytest.raises(ValueError):
            copy.revise_copy(prod,analysis,research,previous,text)
        with pytest.raises(ValueError):
            prompt.revise_image_prompt(previous.plan,analysis,old_prompt,text)


def test_image_prompt_revision_real_owner_function_pins_concept_mood(monkeypatch):
    mod=importlib.import_module("src.text_generation.image_prompt_generator")
    prod,analysis,research,previous=inputs()
    old=ImagePromptOutput(concept=previous.plan.concept,
        mood=previous.plan.mood,prompt="깨끗하고 맑은 배경")
    def fake(prompt,output_type,*,instructions,**kw):
        assert output_type is ImagePromptRevisionOutput
        assert "더 밝게" in prompt
        return ImagePromptRevisionOutput(revised=ImagePromptOutput(
            concept="변조된 기획",mood=["변조"],prompt="밝고 선명한 배경"),
            note="배경을 밝게 했습니다.")
    monkeypatch.setattr(mod,"call_structured",fake)
    result=mod.revise_image_prompt(previous.plan,analysis,old,"더 밝게",
        model="offline-owner-text-test")
    assert result.revised.concept==previous.plan.concept
    assert result.revised.mood==previous.plan.mood
    assert result.revised.prompt=="밝고 선명한 배경"
    assert result.note=="배경을 밝게 했습니다."


def test_cost_is_an_estimate_and_no_paid_dispatch():
    cost=importlib.import_module("src.text_generation.cost")
    estimate=cost.estimate_generation_cost(2,
        model="gpt-6-luna",vision_model="gpt-6-luna")
    assert estimate.total_usd>0
    assert "research" in estimate.steps and "analysis" in estimate.steps
    for target in ("copy","image_prompt"):
        prediction=cost.estimate_revision_cost(target,model="gpt-6-luna")
        assert 0<prediction.total_usd<estimate.total_usd
    with pytest.raises(ValueError):
        cost.estimate_generation_cost(1,
            model="gpt-6-luna",vision_model="gpt-6-luna")
    with pytest.raises(ValueError):
        cost.estimate_generation_cost(2,
            model="not-approved",vision_model="gpt-6-luna")
