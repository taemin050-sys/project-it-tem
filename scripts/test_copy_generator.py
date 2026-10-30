"""기획 + 카피 생성 테스트 (저장된 조사 결과 사용) : python -m scripts.test_copy_generator"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path

from src.text_generation.copy_generator import (
    MAX_COPY_CHARS,
    copy_lengths,
    generate_copy,
)
from src.text_generation.llm_client import LLMError
from src.text_generation.schemas import ProductAnalysis, ProductInput, ResearchResult

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)

MODELS = [("gpt-5.4-mini", None), ("gpt-6-luna", "low")]
RESEARCH_DIR = Path("outputs/research")
OUT_DIR = Path("outputs/copy")
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


def load_research(model: str) -> tuple[ResearchResult, Path]:
    """해당 모델의 가장 최근 조사 결과 JSON"""
    files = sorted(RESEARCH_DIR.glob(f"{NAME}_{model}_*.json"))
    if not files:
        raise FileNotFoundError(f"{RESEARCH_DIR}에 {NAME}_{model}_*.json 없음")
    data = json.loads(files[-1].read_text(encoding="utf-8"))
    return ResearchResult.model_validate(data["result"]), files[-1]


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    for model, effort in MODELS:
        print(f"\n===== {model} (reasoning={effort}) =====")
        research, research_path = load_research(model)
        print(f"조사 결과 : {research_path.name}")

        start = time.perf_counter()
        try:
            output = generate_copy(
                PRODUCT, ANALYSIS, research, model=model, reasoning_effort=effort
            )
        except LLMError as e:
            print(f"실패 : {e}")
            continue
        elapsed = time.perf_counter() - start

        lengths = copy_lengths(output)
        p = output.plan
        print(f"{elapsed:.1f}초 | 합계 {lengths['total']}자 / {MAX_COPY_CHARS}자")
        print(f"타깃 : {p.target}")
        print(f"콘셉트 : {p.concept}")
        print(f"핵심 메시지 : {p.key_message}")
        print(f"톤 : {p.tone} | 무드 : {', '.join(p.mood)}")
        print(f"헤드 ({lengths['headline']}자) : {output.ad_copy.headline}")
        print(f"서브 ({lengths['subline']}자) : {output.ad_copy.subline}")
        print(f"CTA ({lengths['cta']}자) : {output.ad_copy.cta}")
        print(f"본문 ({lengths['caption']}자) :\n{output.caption}")
        print(f"해시태그 ({lengths['hashtags_count']}개) : {' '.join(output.hashtags)}")

        path = OUT_DIR / f"{NAME}_{model}_{stamp}.json"
        path.write_text(
            json.dumps(
                {
                    "model": model,
                    "reasoning_effort": effort,
                    "research_file": research_path.name,
                    "elapsed_sec": round(elapsed, 1),
                    "lengths": lengths,
                    "result": output.model_dump(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"저장 : {path}")


if __name__ == "__main__":
    main()
