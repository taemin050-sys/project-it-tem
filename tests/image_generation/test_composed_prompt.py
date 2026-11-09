from uuid import uuid4

import pytest

from src.image_generation import make_a_template
from src.image_generation.composed_prompt import COMPOSED_PROMPT_VERSION, composed_dimension_sources
from src.image_generation.errors import GatewayError
from src.image_generation.korean_image_policy import render_korean_image_policy
from . import test_backend_adapter as backend


def scene(*lines):
    return "\n".join(("[장면 디멘션]", *lines, "[/장면 디멘션]"))


def test_new_binding_covers_product_only_dimensions_and_preserves_received_prompt(tmp_path):
    sent = "밝은 라일락 배경\n" + scene("palette: 라일락", "lighting: 왼쪽 확산광", "props: 없음")
    zone, _ = make_a_template()
    body = backend.body(image_prompt=dict(concept="정갈한 루틴", prompt=sent, mood=["차분"]),
                        safe_zone=zone)
    adapter = backend.setup(tmp_path, lambda _: pytest.fail("Binding must stay offline"))
    request = adapter._bind(body, uuid4())
    assert request.prompt.prompt_version == COMPOSED_PROMPT_VERSION
    assert request.prompt.positive.startswith(sent + "\n\n콘셉트: 정갈한 루틴")
    assert "왼쪽 0.06, 위 0.05, 오른쪽 0.94, 아래 0.25" in request.prompt.positive
    assert composed_dimension_sources(request.prompt.positive) == {
        "palette": "explicit", "tone": "conditional_default", "lighting": "explicit",
        "material": "conditional_default", "gloss": "conditional_default", "props": "explicit",
        "concept": "explicit", "product_color": "fixed", "geometry": "fixed", "place_truth": "fixed",
        "composition": "generation_and_local", "attention": "generation_and_local",
        "typography": "local", "mobile": "local_review",
    }
    provider_prompt = adapter.processor.adapter._prompt(request)
    assert provider_prompt.startswith(render_korean_image_policy(request))
    assert "인물과 손을 그리지 않는다" in provider_prompt
    assert "공간이 부족하면 제품을 같은 비율로 작게" in provider_prompt
    assert "결이 잔잔한 무광 표면" in provider_prompt
    assert "약한 접촉 그림자" not in provider_prompt
    assert "별도 소품을 넣지 않는다" not in provider_prompt
    assert body.ad_copy.headline not in provider_prompt


def test_plain_prompt_keeps_original_directions_and_saved_old_versions(tmp_path):
    sent = "노란색 배경, 오른쪽 조명과 세라믹 소품을 사용한다."
    adapter = backend.setup(tmp_path, lambda _: pytest.fail("Binding must stay offline"))
    request = adapter._bind(backend.body(image_prompt=sent), uuid4())
    assert composed_dimension_sources(request.prompt.positive)["lighting"] == "conditional_default"
    provider_prompt = adapter.processor.adapter._prompt(request)
    assert provider_prompt.startswith(sent)
    assert "위 장면 설명에서 해당 항목을 지정하지 않았을 때만" in provider_prompt
    assert "별도 콘셉트가 없으면 전달받은 무드" in provider_prompt
    for version in ("backend-v02-ko-v1", "backend-v02-ko-v2", "backend-v02-ko-v3", "backend-freeform-ko-v1"):
        old = request.model_copy(update={"prompt": request.prompt.model_copy(update={"prompt_version": version})})
        assert adapter.processor.adapter._prompt(old) == render_korean_image_policy(old)


@pytest.mark.parametrize("prompt", [
    scene("palette: "),
    scene("tone: 밝음", "tone: 차분함"),
    scene("model_gaze: 카메라"),
    "[장면 디멘션]\nlighting: 확산광",
    scene("palette: 라일락") + "\n" + scene("tone: 밝음"),
])
def test_bad_opt_in_block_is_rejected_before_provider_call(tmp_path, prompt):
    adapter = backend.setup(tmp_path, lambda _: pytest.fail("Invalid dimensions must not call provider"))
    with pytest.raises(GatewayError) as error:
        adapter.generate(backend.body(image_prompt=prompt), project_id=uuid4())
    assert error.value.code == "PROVIDER_INPUT_INVALID"
    with adapter._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM backend_image_bindings").fetchone()[0] == 0


def test_maximum_text_prompt_length_does_not_include_provider_suffix(tmp_path):
    adapter = backend.setup(tmp_path, lambda _: pytest.fail("Binding must stay offline"))
    sent = "가" * 3000
    request = adapter._bind(backend.body(image_prompt=sent), uuid4())
    assert request.prompt.positive.startswith(sent + "\n\n")
    assert len(request.prompt.positive) <= 4000
    assert "제품 단독 합성형 연출" in adapter.processor.adapter._prompt(request)
