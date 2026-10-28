"""5종 전체 흐름 테스트 (조사 → 카피 → 이미지 프롬프트)

python -m scripts.test_pipeline                 # 전체
python -m scripts.test_pipeline 롬앤글래스팅스프링피버   # 특정 제품만
"""

import json
import logging
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from src.text_generation.copy_generator import copy_lengths, generate_copy
from src.text_generation.image_prompt_generator import generate_image_prompt
from src.text_generation.llm_client import LLMError
from src.text_generation.researcher import research
from src.text_generation.schemas import ProductAnalysis, ProductInput

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)

MODELS = [("gpt-5.4-mini", None), ("gpt-6-luna", "low")]
ANALYSIS_MODEL = "gpt-6-luna"  # 사진 분석 결과는 이 모델 것을 우선 사용

INPUTS_PATH = Path("data/test_products/inputs.json")
ANALYSIS_DIR = Path("outputs/product_analysis")
OUT_DIR = Path("outputs/pipeline")


def load_analysis(name: str) -> tuple[ProductAnalysis, int]:
    """제품의 가장 최근 사진 분석 JSON → (분석 결과, 사진 장수)"""
    files = sorted(ANALYSIS_DIR.glob(f"{name}_*.json"))
    if not files:
        raise FileNotFoundError(f"{ANALYSIS_DIR}에 {name}_*.json 없음")
    data = json.loads(files[-1].read_text(encoding="utf-8"))
    key = (
        ANALYSIS_MODEL
        if ANALYSIS_MODEL in data
        else next(k for k in data if k not in ("product", "photos"))
    )
    value = data[key]
    if "analysis" in value:
        if not value.get("analysis_succeeded", True):
            raise ValueError(
                f"{files[-1].name} : 사진 분석 실패 결과 ({value.get('error')})"
            )
        value = value["analysis"]
    return ProductAnalysis.model_validate(value), len(data.get("photos", []))


def run_one(
    name: str,
    product: ProductInput,
    analysis: ProductAnalysis,
    model: str,
    effort: str | None,
) -> dict:
    record: dict = {"product": name, "model": model, "reasoning_effort": effort}
    times: dict[str, float] = {}

    start = time.perf_counter()
    res = research(product, analysis, model=model, reasoning_effort=effort)
    times["research"] = round(time.perf_counter() - start, 1)
    record["research"] = res.model_dump()

    start = time.perf_counter()
    try:
        copy = generate_copy(
            product, analysis, res, model=model, reasoning_effort=effort
        )
    except LLMError as e:
        record["copy_error"] = str(e)
        record["times"] = times
        return record
    times["copy"] = round(time.perf_counter() - start, 1)
    record["copy"] = copy.model_dump()
    record["copy_lengths"] = copy_lengths(copy)

    start = time.perf_counter()
    try:
        prompt = generate_image_prompt(
            copy.plan, analysis, model=model, reasoning_effort=effort
        )
        record["image_prompt"] = prompt.model_dump()
    except LLMError as e:
        record["image_prompt_error"] = str(e)
    times["image_prompt"] = round(time.perf_counter() - start, 1)

    record["times"] = times
    return record


def print_record(r: dict) -> None:
    rs = r["research"]["research"]
    sources = Counter(
        i["source"]
        for i in [
            *rs["market_insights"],
            *rs["similar_products"],
            *rs["display_summary"],
        ]
    )
    print(
        f"조사 : 검색 {r['research']['research_performed']} | 인용 {len(r['research']['citations'])}개 "
        f"| 출처 {dict(sources)} | 에러 {r['research']['error']}"
    )
    for line in rs["display_summary"]:
        print(f"  [{line['source']}] {line['text']}")

    if "copy_error" in r:
        print(f"카피 실패 : {r['copy_error']}")
        return
    c, n = r["copy"], r["copy_lengths"]
    print(
        f"기획 : {c['plan']['concept']} | 톤 {c['plan']['tone']} | 무드 {', '.join(c['plan']['mood'])}"
    )
    print(f"헤드 ({n['headline']}자) : {c['ad_copy']['headline']}")
    print(f"서브 ({n['subline']}자) : {c['ad_copy']['subline']}")
    print(f"CTA ({n['cta']}자) : {c['ad_copy']['cta']}")
    print(f"본문 ({n['caption']}자) :\n{c['caption']}")
    print(f"해시태그 ({n['hashtags_count']}개) : {' '.join(c['hashtags'])}")

    if "image_prompt_error" in r:
        print(f"이미지 프롬프트 실패 : {r['image_prompt_error']}")
    else:
        p = r["image_prompt"]["prompt"]
        print(f"이미지 프롬프트 ({len(p)}자) :\n{p}")
    print(f"시간 : {r['times']}")


def main():
    inputs = json.loads(INPUTS_PATH.read_text(encoding="utf-8"))
    names = sys.argv[1:] or list(inputs)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary = []

    for name in names:
        analysis, photo_count = load_analysis(name)
        product = ProductInput(
            **inputs[name],
            photo_verified=True,
            product_image_count=min(max(photo_count, 2), 5),
        )
        for model, effort in MODELS:
            print(f"\n===== {name} | {model} (reasoning={effort}) =====")
            record = run_one(name, product, analysis, model, effort)
            print_record(record)

            path = OUT_DIR / f"{name}_{model}_{stamp}.json"
            path.write_text(
                json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"저장 : {path}")

            summary.append(
                (
                    name,
                    model,
                    record["research"]["research_performed"],
                    len(record["research"]["citations"]),
                    record.get("copy_lengths", {}).get("total", "-"),
                    len(record["image_prompt"]["prompt"])
                    if "image_prompt" in record
                    else "-",
                    round(sum(record["times"].values()), 1),
                )
            )

    print("\n===== 요약 =====")
    print("제품 | 모델 | 검색 | 인용 | 카피 합계 | 프롬프트 | 시간(초)")
    for row in summary:
        print(" | ".join(str(x) for x in row))


if __name__ == "__main__":
    main()
