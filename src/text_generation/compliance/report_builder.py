"""검수 리포트 : ComplianceIssue 목록 → ComplianceReport (4단계 카피 검토 화면용)"""

from ..schemas import (
    AdCopyOutput,
    ComplianceIssue,
    ComplianceReport,
    ProductAnalysis,
    ProductInput,
)
from .rule_checker import check_copy


def _quote(issues: list[ComplianceIssue]) -> str:
    return ", ".join(dict.fromkeys(f"'{i.text}'" for i in issues))


def _checklist(issues: list[ComplianceIssue], product: ProductInput) -> list[str]:
    items = []
    violations = [i for i in issues if i.risk_level == "위반 의심"]
    need_proof = [i for i in issues if i.risk_level == "근거 확인 필요"]
    if violations:
        items.append(
            f"{_quote(violations)} 표현을 대체 문구를 참고해 수정하거나 삭제해야 승인할 수 있습니다"
        )
    if need_proof:
        items.append(
            f"{_quote(need_proof)} 표현은 시험·심사 자료 등 근거가 있을 때만 사용하세요"
        )
    if product.is_functional:
        items.append(
            "기능성 화장품 심사(보고)를 받은 효능 범위 안의 표현인지 확인하세요"
        )
    items.append("입력한 제품 특징·효능이 실제와 같은지 확인하세요")
    return items


def build_report(
    issues: list[ComplianceIssue], product: ProductInput
) -> ComplianceReport:
    # revised_fields(대체 문구 자동 반영본)는 1차 규칙 검수에서 만들지 않음
    # 단어만 바꾸면 문장이 어색해져서, 문장 단위 재작성은 LLM 단계(고도화)에서 처리
    return ComplianceReport(
        passed=not any(i.risk_level == "위반 의심" for i in issues),
        issues=issues,
        revised_fields={},
        checklist=_checklist(issues, product),
    )


def review_copy(
    copy: AdCopyOutput, product: ProductInput, analysis: ProductAnalysis
) -> ComplianceReport:
    """1차 규제 검수 (규칙 기반, LLM 호출 없음)"""
    return build_report(check_copy(copy, product, analysis), product)
