"""예상 비용 확인 : python -m scripts.test_cost (실제 호출 없음, 비용 없음)"""

from src.text_generation.cost import (
    estimate_generation_cost,
    estimate_revision_cost,
    format_usd,
)

from src.text_generation.config import MODEL_TEXT


def main():
    print(f"===== {MODEL_TEXT} =====")
    for photos in (2, 5):
        est = estimate_generation_cost(photo_count=photos)
        steps = ", ".join(f"{k} ${v:.4f}" for k, v in est.steps.items())
        print(
            f"처음 생성 (사진 {photos}장) : {format_usd(est.total_usd)} (${est.total_usd:.4f}) | {steps}"
        )
    for target in ("copy", "image_prompt"):
        est = estimate_revision_cost(target)
        print(f"{target} 수정 1회 : {format_usd(est.total_usd)} (${est.total_usd:.5f})")

    print("\n===== 입력 오류 =====")
    try:
        estimate_generation_cost(photo_count=1)
        print("FAIL | 사진 1장인데 ValueError가 안 남")
    except ValueError as e:
        print(f"PASS | {e}")
    try:
        estimate_generation_cost(model="gpt-unknown")
        print("FAIL | 없는 모델인데 ValueError가 안 남")
    except ValueError as e:
        print(f"PASS | {e}")


if __name__ == "__main__":
    main()
