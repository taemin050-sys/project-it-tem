"""제품 사진 분석 : python -m scripts.test_product_analyzer "제품명-*" [--models gpt-5.4-mini gpt-6-luna]

- 기본은 config 모델(MODEL_VISION)만 실행, 비교할 때만 --models로 여러 개 지정
- 결과는 outputs/product_analysis/에 모델 이름을 키로 저장 (test_pipeline이 읽음)
"""

import argparse
import json
import logging
from datetime import datetime
from pathlib import Path

from src.text_generation.config import MODEL_VISION
from src.text_generation.product_analyzer import analyze_product

logging.basicConfig(level=logging.INFO)

OUT_DIR = Path("outputs/product_analysis")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "pattern", help='data/test_products 안의 사진 패턴, 예: "메노킨버블마스크-*"'
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=[MODEL_VISION],
        help="비교할 모델 (기본 : config 모델)",
    )
    args = parser.parse_args()

    paths = sorted(Path("data/test_products").glob(args.pattern))
    images = [p.read_bytes() for p in paths]
    product = paths[0].stem.rsplit("-", 1)[0] if paths else "unknown"
    print("사진:", [p.name for p in paths])

    results = {"product": product, "photos": [p.name for p in paths]}
    for model in args.models:
        print(f"\n===== {model} =====")
        r = analyze_product(images, model=model)
        print(r.model_dump_json(indent=2))
        results[model] = r.model_dump()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{product}_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {out}")


if __name__ == "__main__":
    main()
