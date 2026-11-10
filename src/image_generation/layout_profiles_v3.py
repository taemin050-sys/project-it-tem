"""Owner Image's additive, explicitly versioned 4:5 Composed A/C beta layouts.

Never changes old instagram-copy-hierarchy-v2 geometry. This is UNSIGNED and
must not be activated for paid/real-provider use. A5-0E source proposals are
synthetic; product bounding targets are not detection masks.
"""
from __future__ import annotations

import json

from .layout_profiles import LayoutProfile

OWNER_A5_LAYOUT_VERSION = "instagram-composed-4x5-a5-v3-beta-proposal1"
OWNER_A5_PROFILE_MARKER_PREFIX = "a5-v3-beta-"
OWNER_A5_SAFE = (64,64,1016,1286)

GEOMETRY = {
    "A": {
        "proposal_sha": "bcf1b8081a6164ed236cca0cc370d8b906dcd2b0b841aca7db1dc58c14e3e509",
        "headline": (86,82,994,223),
        "subline": (86,245,994,382),
        "cta": (218,1108,862,1238),
        "product": (436,410,644,1045),
        "cta_bg": "#253F55","cta_ink": "#FFFFFF",
        "headline_ink": "#263944","subline_ink": "#4C6470",
    },
    "C": {
        "proposal_sha": "eec55373cca228de34838b33baaf3b11e703e341b05739b34f4c909b1afea6fd",
        "headline": (86,82,994,223),
        "subline": (86,245,994,382),
        "cta": (80,1094,1000,1236),
        "product": (436,405,644,1035),
        "cta_bg": "#503B58","cta_ink": "#FFFFFF",
        "headline_ink": "#463447","subline_ink": "#6A526A",
    },
}


def get_beta_composed45(profile_id: str) -> LayoutProfile:
    if type(profile_id) is not str or profile_id not in GEOMETRY:
        raise ValueError("A5_V3_OWNER_PROFILE_UNRECOGNIZED")
    p=GEOMETRY[profile_id]
    return LayoutProfile(
        key="feed-4:5-"+OWNER_A5_PROFILE_MARKER_PREFIX+profile_id,
        native=(1152,1440), final=(1080,1350),
        safe=OWNER_A5_SAFE, product=p["product"],
        text=tuple((key,p[key]) for key in ("headline","subline","cta")),
    )


def render_v3_generation_instruction(profile_id: str) -> str:
    """Source-first layout request for pre-composition image BACKGROUND only."""
    profile=get_beta_composed45(profile_id)
    data={
        "layout_version":OWNER_A5_LAYOUT_VERSION,
        "proposal_status":"UNSIGNED_BETA_TEST_ONLY",
        "placement":profile.key,
        "generation_size":list(profile.native),
        "final_size":list(profile.final),
        "cta_placement":"image",
        "image_text_rendering":"NOT_BY_MODEL_SERVER_COMPOSITOR_ONLY",
        "normalized_ltrb":{
            key:profile.normalized(box) for key,box in {
                "UI_SAFE":profile.safe,
                "PRODUCT_TARGET":profile.product,
                **dict(profile.text),
            }.items()},
        "generation_px_ltrb":{
            key:profile.generation_box(box) for key,box in {
                "UI_SAFE":profile.safe,
                "PRODUCT_TARGET":profile.product,
                **dict(profile.text),
            }.items()},
        "source_design_sha256":GEOMETRY[profile_id]["proposal_sha"],
    }
    return (
        "4:5 합성형 배치 지시 — 개발용 Profile v3(미승인). "
        "좌표계는 최종 1080×1350 기준 LTRB 및 실제 모델 출력 1152×1440 변환 좌표다.\n"
        "첫 번째 제품 사진을 제품·라벨·브랜드 원본 보존 기준으로 한다. "
        "PRODUCT_TARGET은 제품의 목표 구도이고 실제 제품 검출 마스크가 아니다. "
        "제품의 형태·로고·인쇄 문구·색을 변형하지 않는다.\n"
        "Headline/Subcopy/CTA 각 박스는 실제 별도 합성 엔진이 글자를 그리는 예약 영역이다. "
        "이 영역에는 상품·포장·라벨·인물·장식·강한 반사광을 두지 않는다. "
        "모델이 자체적으로 광고 문구나 CTA 버튼·가격·효능 문구를 그리면 안 된다. "
        "CTA를 플랫폼 버튼으로 대체하거나 CTA 영역을 제거하면 안 된다. "
        "다른 과거 4:5 v2 배치 지시보다 현재 버전의 영역이 우선한다.\n"
        +json.dumps(data,ensure_ascii=False,separators=(",",":"))
    )
