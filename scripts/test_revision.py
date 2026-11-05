"""수정 요청 반영 확인 : python -m scripts.test_revision [제품키] [--level 보통]

- 조사는 outputs/pipeline/에 저장된 gpt-6-luna 결과를 다시 사용 (검색 비용 없음)
- 카피 1개 생성 → 요청 4개로 각각 수정 (매번 원래 카피에서 시작)
- 이미지 프롬프트 1개 생성 → 요청 2개로 각각 수정
"""

import argparse
import json
import logging

from scripts.test_pipeline import INPUTS_PATH, OUT_DIR, load_analysis
from src.text_generation.compliance.report_builder import review_copy
from src.text_generation.copy_generator import (
    check_copy_content,
    check_copy_limits,
    generate_copy,
    revise_copy,
)
from src.text_generation.image_prompt_generator import (
    generate_image_prompt,
    revise_image_prompt,
)
from src.text_generation.schemas import AdCopyOutput, ProductInput, ResearchResult

logging.basicConfig(
    level=logging.WARNING, format="%(levelname)s | %(name)s | %(message)s"
)

MODEL = "gpt-6-luna"
LEVELS = ["없음", "보통", "많이"]

COPY_REQUESTS = [
    "헤드를 더 귀엽게 바꿔줘",  # 헤드만 바뀌어야 함
    "본문을 더 짧고 담백하게 써줘",  # 본문만 (짧아져서 길이 경고는 나올 수 있음)
    "전체적으로 더 고급스러운 느낌으로 바꿔줘",  # 여러 항목
    "피부 재생 효과가 있다고 강조해줘",  # 규칙 위반 → 반영 안 하고 note
]
IMAGE_REQUESTS = [
    "배경을 더 밝고 따뜻한 색으로 바꿔줘",
    "위쪽에 꽃을 가득 채워줘",  # 배치 규칙 위반 → note
]


def _fields(copy: AdCopyOutput) -> dict[str, str]:
    return {
        "plan": f"{copy.plan.tone} | {copy.plan.concept}",
        "headline": copy.ad_copy.headline,
        "subline": copy.ad_copy.subline,
        "cta": copy.ad_copy.cta,
        "caption": copy.caption,
        "hashtags": " ".join(copy.hashtags),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "name", nargs="?", default="메노킨버블마스크", help="inputs.json의 제품키"
    )
    parser.add_argument("--level", choices=LEVELS, default="보통", help="이모티콘 정도")
    args = parser.parse_args()

    inputs = json.loads(INPUTS_PATH.read_text(encoding="utf-8"))
    files = sorted(OUT_DIR.glob(f"{args.name}_{MODEL}_*.json"))
    if not files:
        raise FileNotFoundError(
            f"{OUT_DIR}에 {args.name}_{MODEL}_*.json 없음 (test_pipeline 먼저 실행)"
        )
    record = json.loads(files[-1].read_text(encoding="utf-8"))
    research = ResearchResult.model_validate(record["research"])
    analysis, photo_count = load_analysis(args.name)
    product = ProductInput(
        **inputs[args.name],
        emoji_level=args.level,
        photo_verified=True,
        product_image_count=min(max(photo_count, 2), 5),
    )
    print(f"조사 결과 재사용 : {files[-1].name} | 이모티콘 {args.level}")

    # ---------- 카피 ----------
    original = generate_copy(product, analysis, research, model=MODEL)
    before = _fields(original)
    print("\n===== 원래 카피 =====")
    for k, v in before.items():
        print(f"[{k}] {v}")

    for req in COPY_REQUESTS:
        result = revise_copy(product, analysis, research, original, req, model=MODEL)
        after = _fields(result.revised)
        report = review_copy(result.revised, product, analysis)

        print(f"\n===== 수정 요청 : {req} =====")
        print(f"고친 항목 : {result.changed_fields or '없음'}")
        print(f"note : {result.note}")
        for k in result.changed_fields:
            print(f"[{k}] 전 : {before[k]}")
            print(f"[{k}] 후 : {after[k]}")
        print(
            f"검수 : {'통과' if report.passed else '승인 차단'} | 문제 {len(report.issues)}개"
        )
        for i in report.issues:
            print(f"  [{i.risk_level}] {i.field} '{i.text}'")
        for w in check_copy_limits(
            result.revised, product.emoji_level
        ) + check_copy_content(result.revised, product):
            print(f"  경고 : {w}")

    # ---------- 이미지 프롬프트 ----------
    image = generate_image_prompt(original.plan, analysis, model=MODEL)
    print(f"\n===== 원래 이미지 프롬프트 ({len(image.prompt)}자) =====\n{image.prompt}")

    for req in IMAGE_REQUESTS:
        result = revise_image_prompt(original.plan, analysis, image, req, model=MODEL)
        print(f"\n===== 수정 요청 : {req} =====")
        print(f"후 ({len(result.revised.prompt)}자) : {result.revised.prompt}")
        print(f"note : {result.note}")


if __name__ == "__main__":
    main()
