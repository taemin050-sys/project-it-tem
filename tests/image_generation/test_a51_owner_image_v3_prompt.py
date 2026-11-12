"""A5-1 Owner Image: optional v3 geometry in actual offline Owner request.

Versioned addition to Image Owner #24. Existing 3:4,4:5 v2,9:16 and freeform
contracts must retain the old serialization, hashes, prompt and output shape.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.image_generation.contracts import ExternalImageRequest, ImagePrompt, content_hash
from src.image_generation.backend_adapter import BackendImageAdapter
from src.image_generation.korean_image_policy import render_korean_image_policy
from src.image_generation.layout_profiles import render_layout_instruction, get_layout
from src.image_generation.layout_profiles_v3 import (
    GEOMETRY, OWNER_A5_LAYOUT_VERSION, OWNER_A5_PROFILE_MARKER_PREFIX,
    get_beta_composed45, render_v3_generation_instruction,
)
from tests.image_generation.test_backend_adapter import body


def build_request(profile):
    return ExternalImageRequest(
        operation="edit", width=1152, height=1440,
        layout_selection={"aspect_ratio":"4:5","placement":"feed"},
        composed_layout_profile=OWNER_A5_PROFILE_MARKER_PREFIX+profile,
        prompt={"positive":"원본 브랜드를 보존하는 배경", "source_revision":1,
                "prompt_version":"backend-composed-a5-v3-beta1"},
        product_images=[{"asset_id":uuid4(), "sha256":"a"*64, "width":480,
                         "height":640,"mime_type":"image/png"}],
    )


@pytest.mark.parametrize("which",("A","C"))
def test_a51_owner_prompt_v3_excludes_old_v2_platform_cta(which):
    profile=get_beta_composed45(which)
    g=GEOMETRY[which]
    assert profile.native==(1152,1440) and profile.final==(1080,1350)
    assert profile.product==g["product"]
    assert dict(profile.text)["cta"]==g["cta"]
    prompt=render_korean_image_policy(build_request(which))
    assert OWNER_A5_LAYOUT_VERSION in prompt
    assert "NOT_BY_MODEL_SERVER_COMPOSITOR_ONLY" in prompt
    assert '"cta_placement":"image"' in prompt
    assert '"source_design_sha256":"'+g["proposal_sha"]+'"' in prompt
    assert '"PRODUCT_TARGET":' in prompt
    assert '"cta":' in prompt
    assert g["cta"]==tuple(dict(profile.text)["cta"])
    assert "instagram-copy-hierarchy-v2" not in prompt
    assert '"cta_placement":"platform"' not in prompt
    assert "모델이 자체적으로 광고 문구나 CTA 버튼" in prompt


def test_a51_owner_old_4x5_still_platform_no_v3_fields():
    req=ExternalImageRequest(
        operation="edit",width=1152,height=1440,
        layout_selection={"aspect_ratio":"4:5","placement":"feed"},
        prompt={"positive":"기존 배경","source_revision":1,"prompt_version":"v2"},
        product_images=[{"asset_id":uuid4(),"sha256":"a"*64,"width":480,
                         "height":640,"mime_type":"image/png"}])
    assert "composed_layout_profile" not in req.model_dump(mode="json")
    assert "composed_layout_profile" not in req.model_dump_json()
    assert '"cta_placement":"platform"' in render_korean_image_policy(req)
    assert "instagram-copy-hierarchy-v2" in render_korean_image_policy(req)
    assert "backend-composed-a5-v3-beta1" not in render_korean_image_policy(req)
    assert content_hash(req)==content_hash(req.model_dump(mode="json"))


@pytest.mark.parametrize("ratio",("3:4","9:16"))
def test_a51_v3_layout_ratio_conflicts_rejected(ratio):
    with pytest.raises(ValidationError):
        ExternalImageRequest(
            operation="edit",width=1152,height=1440,
            layout_selection={"aspect_ratio":ratio,
                              "placement":"reels" if ratio=="9:16" else "feed"},
            composed_layout_profile="a5-v3-beta-A",
            prompt={"positive":"x","source_revision":1,"prompt_version":"v1"},
            product_images=[{"asset_id":uuid4(),"sha256":"a"*64,"width":480,
                             "height":640,"mime_type":"image/png"}])


def test_a51_freeform_cannot_use_composed_beta():
    with pytest.raises(ValidationError):
        ExternalImageRequest(
            operation="edit",width=1152,height=1440,
            text_rendering="freeform-v1",
            layout_selection={"aspect_ratio":"4:5","placement":"feed"},
            composed_layout_profile="a5-v3-beta-C",
            prompt={"positive":"x","source_revision":1,"prompt_version":"v1"},
            product_images=[{"asset_id":uuid4(),"sha256":"a"*64,"width":480,
                             "height":640,"mime_type":"image/png"}])


@pytest.mark.parametrize("which",("A","C"))
def test_a51_backend_owner_input_and_prompt_version_separates_v3(which):
    o=body(
        copy_revision=2,generation_mode="composed",
        layout_selection={"aspect_ratio":"4:5","placement":"feed"},
        composed_layout_profile=OWNER_A5_PROFILE_MARKER_PREFIX+which)
    prompt=BackendImageAdapter._build_prompt(o,"backend-v02-ko-v2")
    assert prompt.prompt_version=="backend-composed-a5-v3-beta1"
    assert prompt.language=="ko" and prompt.source_revision==2
    old=body(copy_revision=2,generation_mode="composed",
        layout_selection={"aspect_ratio":"4:5","placement":"feed"})
    assert old.composed_layout_profile is None
    assert BackendImageAdapter._build_prompt(old,"backend-v02-ko-v2").prompt_version=="backend-v02-ko-v2"
    assert o.composed_layout_profile!=old.composed_layout_profile


def test_a51_backend_rejects_freeform_composed_selector():
    with pytest.raises(ValidationError):
        body(generation_mode="freeform",layout_selection={
            "aspect_ratio":"4:5","placement":"feed"},
            copy_output={},composed_layout_profile="a5-v3-beta-A")

@pytest.mark.parametrize("which",("A","C"))
def test_a51_v3_owner_adapter_mocktransport_one_bound_provider_attempt(
        tmp_path,which):
    import base64
    from email import policy as email_policy
    from email.parser import BytesParser
    from pathlib import Path
    import httpx
    from src.image_generation.assets import LocalAssetStore
    from src.image_generation.api_image_processor import ExternalImageProcessor
    from src.image_generation.openai_images import OpenAIImagesAdapter, OpenAIImagesConfig
    from src.image_generation.provider_attempts import ProviderAttemptStore
    from tests.image_generation.test_backend_adapter import png
    calls=[]
    def handler(request):
        message=BytesParser(policy=email_policy.default).parsebytes(
            b"Content-Type: "+request.headers["content-type"].encode()+
            b"\r\n\r\n"+request.read())
        fields={
            item.get_param("name",header="content-disposition"):item.get_payload(decode=True)
            for item in message.iter_parts()
            if item.get_param("name",header="content-disposition")!="image[]"
        }
        calls.append(fields)
        return httpx.Response(200,json={
            "data":[{"b64_json":base64.b64encode(png(size=(1152,1440))).decode()}],
            "usage":{"input_tokens":12,"output_tokens":34,"total_tokens":46},
        },headers={"x-request-id":"offline-a51-v3-no-paid"})
    transport=httpx.MockTransport(handler)
    provider=OpenAIImagesAdapter(OpenAIImagesConfig(live_calls=False),
                                 transport=transport)
    folder=tmp_path/"owner-image-offline"
    processor=ExternalImageProcessor(
        LocalAssetStore(folder/"assets"),provider,
        ProviderAttemptStore(folder/"attempts.sqlite"),
        budget_limit_usd="2",reservation_usd="1")
    adapter=BackendImageAdapter(processor,folder/"bindings.sqlite")
    params=body(copy_revision=3,generation_mode="composed",
        layout_selection={"aspect_ratio":"4:5","placement":"feed"},
        composed_layout_profile="a5-v3-beta-"+which)
    proj=uuid4()
    first=adapter.generate(params,project_id=proj)
    second=adapter.generate(params,project_id=proj)
    assert first==second
    assert first.mock is True
    assert len(calls)==1
    assert first.receipt["usage"]["total_tokens"]==46
    assert len(first.image_bytes)>0
    assert (first.width,first.height)==(1152,1440)
    prompt=calls[0]["prompt"].decode()
    assert OWNER_A5_LAYOUT_VERSION in prompt
    assert '"cta_placement":"image"' in prompt
    assert '"source_design_sha256":"'+GEOMETRY[which]["proposal_sha"]+'"' in prompt
    assert "NOT_BY_MODEL_SERVER_COMPOSITOR_ONLY" in prompt
    assert "PRODUCT_TARGET" in prompt
