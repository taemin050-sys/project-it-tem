"""기획 AI 조사 테스트 (제품 1종, 모델 2개) : python -m scripts.test_researcher"""

import json
import logging
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from src.text_generation.researcher import research
from src.text_generation.schemas import ProductAnalysis, ProductInput

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)

MODELS = [("gpt-5.4-mini", None), ("gpt-6-luna", "low")]
OUT_DIR = Path("outputs/research")
NAME = "식물나라"

PRODUCT = ProductInput(
    brand_name="식물나라",
    product_name="제주 알로에 촉촉 수딩젤",
    product_category="수딩젤",
    features="제주 알로에 함유, 끈적임 없이 촉촉한 수딩젤, 얼굴과 몸 모두 사용 가능",
    ad_purpose="여름 시즌 홍보",
    is_functional=False,
    photo_verified=True,
    product_image_count=5,
)

ANALYSIS = ProductAnalysis(
    is_cosmetic=True,
    product_type="스킨케어",
    container_type="튜브",
    colors=["연두색", "초록색"],
    label_text=[
        "식물나라",
        "제주 알로에 촉촉 수딩젤",
        "Jeju Aloe Moisture Soothing Gel",
        "200 mL",
    ],
    mood=["청량", "내추럴", "심플"],
    is_transparent=True,
)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    for model, effort in MODELS:
        print(f"\n===== {model} (reasoning={effort}) =====")
        start = time.perf_counter()
        result = research(PRODUCT, ANALYSIS, model=model, reasoning_effort=effort)
        elapsed = time.perf_counter() - start

        r = result.research
        sources = Counter(
            i.source
            for i in [*r.market_insights, *r.similar_products, *r.display_summary]
        )
        print(f"검색 수행 : {result.research_performed} | 에러 : {result.error}")
        print(
            f"인용 {len(result.citations)}개 | 출처 {dict(sources)} | {elapsed:.1f}초"
        )
        for line in r.display_summary:
            print(f"  [{line.source}] {line.text} ({len(line.text)}자)")

        path = OUT_DIR / f"{NAME}_{model}_{stamp}.json"
        path.write_text(
            json.dumps(
                {
                    "model": model,
                    "elapsed_sec": round(elapsed, 1),
                    "result": result.model_dump(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"저장 : {path}")


if __name__ == "__main__":
    main()
