"""이모티콘 정도별 카피 비교 : python -m scripts.test_emoji [제품키] [--levels 많이] [--effort medium]

- 조사는 outputs/pipeline/에 저장된 gpt-6-luna 결과를 다시 사용 (검색 비용 없음)
- 카피만 이모티콘 정도별로 생성 (기본 : 없음 / 보통 / 많이 3번)
- --effort : 추론 강도 (low / medium / high), 생략하면 정도별 기본값
"""

import argparse
import json
import logging
import time

from scripts.test_pipeline import INPUTS_PATH, OUT_DIR, load_analysis
from src.text_generation.compliance.report_builder import review_copy
from src.text_generation.copy_generator import (
    check_copy_content,
    check_copy_limits,
    copy_lengths,
    copy_reasoning_effort,
    generate_copy,
)
from src.text_generation.schemas import ProductInput, ResearchResult

logging.basicConfig(
    level=logging.WARNING, format="%(levelname)s | %(name)s | %(message)s"
)

MODEL = "gpt-6-luna"
LEVELS = ["없음", "보통", "많이"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "name", nargs="?", default="메노킨버블마스크", help="inputs.json의 제품키"
    )
    parser.add_argument(
        "--levels", nargs="+", choices=LEVELS, default=LEVELS, help="이모티콘 정도"
    )
    parser.add_argument(
        "--effort", default=None, help="추론 강도 (low / medium / high)"
    )
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
    print(f"조사 결과 재사용 : {files[-1].name}")

    for level in args.levels:
        product = ProductInput(
            **inputs[args.name],
            emoji_level=level,
            photo_verified=True,
            product_image_count=min(max(photo_count, 2), 5),
        )
        effort = args.effort or copy_reasoning_effort(level)
        start = time.perf_counter()
        copy = generate_copy(
            product, analysis, research, model=MODEL, reasoning_effort=effort
        )
        elapsed = time.perf_counter() - start
        n = copy_lengths(copy)
        report = review_copy(copy, product, analysis)

        print(f"\n===== 이모티콘 {level} (추론 {effort}, {elapsed:.1f}초) =====")
        print(f"헤드 : {copy.ad_copy.headline}")
        print(f"서브 : {copy.ad_copy.subline}")
        print(f"CTA : {copy.ad_copy.cta}")
        print(
            f"본문 ({n['caption']}자, 이모티콘 {n['caption_emojis']}개) :\n{copy.caption}"
        )
        print(f"해시태그 : {' '.join(copy.hashtags)}")
        print(
            f"검수 : {'통과' if report.passed else '승인 차단'} | 문제 {len(report.issues)}개"
        )
        for i in report.issues:
            print(f"  [{i.risk_level}] {i.field} '{i.text}'")
        for w in check_copy_limits(copy, level) + check_copy_content(copy, product):
            print(f"  경고 : {w}")


if __name__ == "__main__":
    main()
