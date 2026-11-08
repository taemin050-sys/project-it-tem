"""1차 규제 검수 테스트 (API 호출 없음) : python -m scripts.test_compliance

- 생성한 카피(outputs/pipeline/*.json) 전체 검수
- 일부러 만든 위반 문구 검수 (일반 / 기능성 종류 미입력 / 기능성 종류 입력)
"""

import json
from pathlib import Path

from scripts.test_pipeline import INPUTS_PATH, load_analysis
from src.text_generation.compliance.report_builder import review_copy
from src.text_generation.schemas import (
    AdCopyOutput,
    AdPlan,
    ComplianceReport,
    CopySet,
    ProductInput,
)

PIPELINE_DIR = Path("outputs/pipeline")

VIOLATION_COPY = {
    "headline": "최고의 미백 크림",
    "subline": "피부 재생부터 주름 개선까지",
    "cta": "지금 만나보세요",
    "caption": "의사가 추천한 크림으로 2주 만에 피부결 20% 개선! 여드름 흔적도 없애줘요. 진정 효과까지.",
    "hashtags": ["#필수템", "#줄기세포", "#토너추천"],
}

VIOLATION_CASES = [
    {"name": "위반 문구 (일반 화장품)", "is_functional": False, "functional_types": []},
    {
        "name": "같은 문구 (기능성, 종류 미입력)",
        "is_functional": True,
        "functional_types": [],
    },
    {
        "name": "같은 문구 (기능성, 미백만 선택)",
        "is_functional": True,
        "functional_types": ["미백"],
    },
]


def print_report(report: ComplianceReport, copy: AdCopyOutput) -> None:
    status = "통과" if report.passed else "승인 차단"
    print(f"결과 : {status} | 문제 {len(report.issues)}개")
    for i in report.issues:
        print(
            f"  [{i.risk_level}] {i.field} '{i.text}' ({i.start}~{i.end}) {i.category} → {i.suggestion or '삭제 권장'}"
        )
    for field, text in report.revised_fields.items():
        print(f"  수정안 {field} : {text}")
    for item in report.checklist:
        print(f"  ☐ {item}")


def run_pipeline_outputs(inputs: dict) -> None:
    for path in sorted(PIPELINE_DIR.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if "copy" not in record:
            continue
        name = record["product"]
        analysis, photo_count = load_analysis(name)
        product = ProductInput(
            **inputs[name],
            photo_verified=True,
            product_image_count=min(max(photo_count, 2), 5),
        )
        copy = AdCopyOutput.model_validate(record["copy"])
        print(f"\n===== {path.name} =====")
        print_report(review_copy(copy, product, analysis), copy)


def run_violation_cases(inputs: dict) -> None:
    name = next(iter(inputs))
    analysis, _ = load_analysis(name)
    copy = AdCopyOutput(
        plan=AdPlan(target="-", concept="-", key_message="-", tone="-", mood=[]),
        ad_copy=CopySet(
            headline=VIOLATION_COPY["headline"],
            subline=VIOLATION_COPY["subline"],
            cta=VIOLATION_COPY["cta"],
        ),
        caption=VIOLATION_COPY["caption"],
        hashtags=VIOLATION_COPY["hashtags"],
    )
    for case in VIOLATION_CASES:
        product = ProductInput(
            brand_name="테스트",
            product_name="테스트 크림",
            features="테스트",
            ad_purpose="테스트",
            is_functional=case["is_functional"],
            functional_types=case["functional_types"],
            photo_verified=True,
            product_image_count=2,
        )
        print(f"\n===== {case['name']} =====")
        print_report(review_copy(copy, product, analysis), copy)


def main():
    inputs = json.loads(INPUTS_PATH.read_text(encoding="utf-8"))
    run_violation_cases(inputs)
    run_pipeline_outputs(inputs)


if __name__ == "__main__":
    main()
