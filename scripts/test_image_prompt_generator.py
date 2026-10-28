"""이미지 프롬프트 생성 테스트 (저장된 카피 결과 사용) : python -m scripts.test_image_prompt_generator"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path

from src.text_generation.image_prompt_generator import generate_image_prompt
from src.text_generation.llm_client import LLMError
from src.text_generation.schemas import AdCopyOutput, ProductAnalysis

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)

MODELS = [("gpt-5.4-mini", None), ("gpt-6-luna", "low")]
COPY_DIR = Path("outputs/copy")
OUT_DIR = Path("outputs/image_prompt")
NAME = "식물나라"

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


def load_copy(model: str) -> tuple[AdCopyOutput, Path]:
    """해당 모델의 가장 최근 카피 결과 JSON"""
    files = sorted(COPY_DIR.glob(f"{NAME}_{model}_*.json"))
    if not files:
        raise FileNotFoundError(f"{COPY_DIR}에 {NAME}_{model}_*.json 없음")
    data = json.loads(files[-1].read_text(encoding="utf-8"))
    return AdCopyOutput.model_validate(data["result"]), files[-1]


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    for model, effort in MODELS:
        print(f"\n===== {model} (reasoning={effort}) =====")
        copy, copy_path = load_copy(model)
        print(f"카피 결과 : {copy_path.name}")

        start = time.perf_counter()
        try:
            output = generate_image_prompt(
                copy.plan, ANALYSIS, model=model, reasoning_effort=effort
            )
        except LLMError as e:
            print(f"실패 : {e}")
            continue
        elapsed = time.perf_counter() - start

        print(f"{elapsed:.1f}초")
        print(f"콘셉트 : {output.concept}")
        print(f"무드 : {', '.join(output.mood)}")
        print(f"프롬프트 ({len(output.prompt)}자) :\n{output.prompt}")

        path = OUT_DIR / f"{NAME}_{model}_{stamp}.json"
        path.write_text(
            json.dumps(
                {
                    "model": model,
                    "reasoning_effort": effort,
                    "copy_file": copy_path.name,
                    "elapsed_sec": round(elapsed, 1),
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
