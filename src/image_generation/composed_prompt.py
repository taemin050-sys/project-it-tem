"""Product-only composition direction for new service image requests."""

COMPOSED_PROMPT_VERSION = "backend-composed-ko-v1"
_START = "[장면 디멘션]"
_END = "[/장면 디멘션]"

_SCENE_DEFAULTS = {
    "palette": "제품과 구분되는 밝은 배경색과 작은 강조색만 사용한다.",
    "tone": "원래 무드를 유지하면서 밝고 탁하지 않게 표현한다.",
    "lighting": "부드러운 확산광과 약한 접촉 그림자를 사용한다.",
    "material": "배경은 결이 잔잔한 무광 표면으로 표현한다.",
    "gloss": "배경 반사는 약하게 제한하고 제품 반사는 원본을 따른다.",
    "props": "별도 소품을 넣지 않는다.",
}

_FIXED_DIRECTION = (
    "제품 단독 합성형 연출\n"
    "인물과 손을 그리지 않는다. 첫 사진의 보이는 면, 두께와 각도, 원색과 부품별 재질·광택을 유지한다. "
    "장면의 조명이나 주변색을 제품 자체에 옮기지 않는다. 원본에 없는 산지·원료·효능·인증은 암시하지 않는다. "
    "제품과 라벨에 먼저 시선이 가도록 배경과 소품을 절제한다. 지정한 카피 영역은 단순한 배경으로 비운다. "
    "영역이 지정되지 않은 경우에도 제품 위아래에 충분한 카피 공간을 남긴다. "
    "제품·소품·강한 반사와 카피 영역 사이에 여유를 두고, 공간이 부족하면 제품을 같은 비율로 작게 배치한다. "
    "광고 글자와 버튼은 나중에 합성한다. 제품에 원래 인쇄된 글자는 보존한다."
)


def _explicit_scene_keys(positive: str) -> set[str]:
    lines = positive.splitlines()
    starts = [i for i, line in enumerate(lines) if line.strip() == _START]
    ends = [i for i, line in enumerate(lines) if line.strip() == _END]
    if not starts and not ends:
        return set()
    if len(starts) != 1 or len(ends) != 1 or starts[0] >= ends[0]:
        raise ValueError("Invalid composed scene block")
    explicit = set()
    for line in lines[starts[0] + 1:ends[0]]:
        if not line.strip():
            continue
        key, separator, value = line.partition(":")
        key = key.strip()
        if not separator or key not in _SCENE_DEFAULTS or not value.strip() or key in explicit:
            raise ValueError("Invalid or duplicate composed scene dimension")
        explicit.add(key)
    return explicit


def composed_dimension_sources(positive: str) -> dict[str, str]:
    """Audit the 14 instructions from the bound positive prompt.

    A conditional default also allows directions in unstructured text. This
    check reports instruction coverage, not visual compliance.
    """
    explicit = _explicit_scene_keys(positive)
    concept_prefix = "콘셉트: "
    has_concept = any(line.startswith(concept_prefix) and line.removeprefix(concept_prefix).strip()
                      for line in positive.splitlines())
    return {
        **{key: "explicit" if key in explicit else "conditional_default" for key in _SCENE_DEFAULTS},
        "concept": "explicit" if has_concept else "conditional_default",
        "product_color": "fixed",
        "geometry": "fixed",
        "place_truth": "fixed",
        "composition": "generation_and_local",
        "attention": "generation_and_local",
        "typography": "local",
        "mobile": "local_review",
    }


def render_composed_direction(positive: str) -> str:
    sources = composed_dimension_sources(positive)
    defaults = [value for key, value in _SCENE_DEFAULTS.items()
                if sources[key] == "conditional_default"]
    if sources["concept"] == "conditional_default":
        defaults.insert(0, "별도 콘셉트가 없으면 전달받은 무드에 맞춘 제품 중심 정물로 연출한다.")
    if not defaults:
        return _FIXED_DIRECTION
    return "\n".join((_FIXED_DIRECTION,
                      "위 장면 설명에서 해당 항목을 지정하지 않았을 때만 다음 기본값을 사용한다.",
                      *defaults))
