"""수정 요청 반영 확인 : python -m scripts.test_revision [제품키] [--level 보통]

- 조사는 outputs/pipeline/에 저장된 gpt-6-luna 결과를 다시 사용 (검색 비용 없음)
- 카피 1개 생성 → 검수 → 요청 5개로 각각 수정 (매번 원래 카피에서 시작, 원래 카피의 검수 결과를 같이 넘김)
- 이미지 프롬프트 1개 생성 → 요청 2개로 각각 수정
- 검수 요청은 원래 걸린 표현이 남았는지, 헤드·서브를 고친 요청은 두 항목에 겹치는 단어가 있는지 출력
"""

import argparse
import json
import logging
import re

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
from src.text_generation.schemas import (
    AdCopyOutput,
    ComplianceIssue,
    ProductInput,
    ResearchResult,
)

logging.basicConfig(
    level=logging.WARNING, format="%(levelname)s | %(name)s | %(message)s"
)

MODEL = "gpt-6-luna"
LEVELS = ["없음", "보통", "많이"]

COMPLIANCE_REQUEST = "검수에서 걸린 표현은 다 빼줘"

COPY_REQUESTS = [
    "헤드를 더 귀엽게 바꿔줘",  # 헤드만 바뀌어야 함, 서브와 단어가 겹치지 않아야 함
    "본문을 더 짧고 담백하게 써줘",  # 본문만 (짧아져서 길이 경고는 나올 수 있음)
    "전체적으로 더 고급스러운 느낌으로 바꿔줘",  # 여러 항목
    "피부 재생 효과가 있다고 강조해줘",  # 규칙 위반 → 반영 안 하고 note
    COMPLIANCE_REQUEST,  # 검수 결과를 보고 걸린 표현을 모두 빼야 함 (남기면 note)
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


def _remaining(issues: list[ComplianceIssue], copy: AdCopyOutput) -> list[str]:
    """원래 검수에 걸린 표현 중 수정 후에도 같은 항목에 남아 있는 것"""
    fields = _fields(copy)
    return [i.text for i in issues if i.text in fields.get(i.field, "")]


def _shared_words(headline: str, subline: str) -> list[str]:
    """헤드 단어 중 앞 두 글자가 서브에도 있는 것 (예 : '촉촉' ↔ '촉촉하게')"""
    words = re.findall(r"[가-힣]{2,}", headline)
    return sorted({w for w in words if w[:2] in subline})


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
    original_report = review_copy(original, product, analysis)
    issues = original_report.issues
    before = _fields(original)
    print("\n===== 원래 카피 =====")
    for k, v in before.items():
        print(f"[{k}] {v}")
    print(f"검수 : 문제 {len(issues)}개 (수정 요청에 같이 넘김)")
    for i in issues:
        print(f"  [{i.risk_level}] {i.field} '{i.text}'")
    shared = _shared_words(original.ad_copy.headline, original.ad_copy.subline)
    print(f"헤드·서브 겹침 : {shared or '없음'}")

    for req in COPY_REQUESTS:
        result = revise_copy(
            product, analysis, research, original, req, issues=issues, model=MODEL
        )
        after = _fields(result.revised)
        report = review_copy(result.revised, product, analysis)

        print(f"\n===== 수정 요청 : {req} =====")
        print(f"고친 항목 : {result.changed_fields or '없음'}")
        print(f"note : {result.note}")
        for k in result.changed_fields:
            print(f"[{k}] 전 : {before[k]}")
            print(f"[{k}] 후 : {after[k]}")
        if req == COMPLIANCE_REQUEST:
            print(f"남은 표현 : {_remaining(issues, result.revised) or '없음'}")
        if {"headline", "subline"} & set(result.changed_fields):
            shared = _shared_words(
                result.revised.ad_copy.headline, result.revised.ad_copy.subline
            )
            print(f"헤드·서브 겹침 : {shared or '없음'}")
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
