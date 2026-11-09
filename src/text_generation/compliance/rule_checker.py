"""1차 규제 검수 : 금지어 사전(rules.yaml) 매칭 → ComplianceIssue 목록 (LLM 호출 없음)"""

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from ..schemas import AdCopyOutput, ComplianceIssue, ProductAnalysis, ProductInput

RULES_PATH = Path(__file__).with_name("rules.yaml")

RISK_ORDER = {"위반 의심": 2, "근거 확인 필요": 1, "정상": 0}
_SENTENCE_END = re.compile(r"[.!?\n]")


@dataclass
class _Rule:
    id: str
    patterns: list[re.Pattern]
    category: str
    risk: str
    suggestion: str | None
    basis: str
    basis_url: str | None
    reason: str
    except_with: list[str]


@dataclass
class _Rules:
    general: list[_Rule]
    functional: list[dict]
    color_patterns: list[re.Pattern]
    color_allow: list[str]
    color: dict


def _compile(patterns: list[str]) -> list[re.Pattern]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


def _source_url(sources: dict, rule: dict) -> str | None:
    """규칙의 source 이름 → 출처 URL (source가 null이면 None)"""
    name = rule.get("source")
    if name is None:
        return None
    if name not in sources:
        raise ValueError(
            f"rules.yaml : {rule.get('id', 'color_exceptions')}의 source '{name}'가 sources에 없음"
        )
    return sources[name]["url"]


@lru_cache(maxsize=1)
def load_rules() -> _Rules:
    data = yaml.safe_load(RULES_PATH.read_text(encoding="utf-8"))
    sources = data["sources"]
    general = [
        _Rule(
            id=r["id"],
            patterns=_compile(r["patterns"]),
            category=r["category"],
            risk=r["risk"],
            suggestion=r.get("suggestion"),
            basis=r["basis"],
            basis_url=_source_url(sources, r),
            reason=r["reason"],
            except_with=r.get("except_with", []),
        )
        for r in data["rules"]
    ]
    functional = [
        {**r, "compiled": _compile(r["patterns"]), "basis_url": _source_url(sources, r)}
        for r in data["functional_rules"]
    ]
    color = data["color_exceptions"]
    color = {**color, "basis_url": _source_url(sources, color)}
    return _Rules(
        general=general,
        functional=functional,
        color_patterns=_compile(color["patterns"]),
        color_allow=color["allow_with"],
        color=color,
    )


def _functional_rule(rule: dict, product: ProductInput) -> _Rule:
    """기능성 규칙의 위험도 결정

    - 일반 화장품 : 위반 의심
    - 기능성 + 종류 미입력 : 근거 확인 필요 (종류를 모르므로 모두 허용 범위로 봄)
    - 기능성 + 종류 입력 : 고른 종류는 근거 확인 필요, 고르지 않은 종류는 위반 의심
    """
    ftype = rule["functional_type"]
    types = product.functional_types
    if not product.is_functional:
        risk = rule["not_functional_risk"]
        reason = f"일반 화장품은 {ftype} 효능을 광고할 수 없습니다. 기능성 심사(보고)를 받은 제품만 사용할 수 있습니다."
    elif not types or ftype in types:
        risk = rule["functional_risk"]
        reason = f"심사(보고)받은 {ftype} 효능 범위 안에서만 사용할 수 있습니다."
    else:
        risk = rule["not_functional_risk"]
        reason = (
            f"이 제품이 심사(보고)받은 기능성({', '.join(types)})이 아니므로 "
            f"{ftype} 효능을 광고할 수 없습니다."
        )
    return _Rule(
        id=rule["id"],
        patterns=rule["compiled"],
        category=rule["category"],
        risk=risk,
        suggestion=rule.get("suggestion"),
        basis=rule["basis"],
        basis_url=rule["basis_url"],
        reason=reason,
        except_with=rule.get("except_with", []),
    )


def _protected_spans(text: str, product: ProductInput) -> list[tuple[int, int]]:
    """사용자가 입력한 브랜드명·제품명 위치 (이 안에서 걸린 표현은 검수 제외)"""
    spans = []
    for name in filter(None, [product.brand_name, product.product_name]):
        for m in re.finditer(re.escape(name), text):
            spans.append((m.start(), m.end()))
    return spans


def _inside(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    return any(s <= start and end <= e for s, e in spans)


def _sentence(text: str, start: int, end: int) -> str:
    """표현이 들어 있는 문장"""
    left = max((m.end() for m in _SENTENCE_END.finditer(text, 0, start)), default=0)
    right = _SENTENCE_END.search(text, end)
    return text[left : right.start() if right else len(text)]


def _remove_overlaps(issues: list[ComplianceIssue]) -> list[ComplianceIssue]:
    """같은 위치에 여러 규칙이 걸리면 위험도가 높고 긴 것 하나만"""
    issues.sort(key=lambda i: (-RISK_ORDER[i.risk_level], -(i.end - i.start), i.start))
    kept: list[ComplianceIssue] = []
    for issue in issues:
        if all(issue.end <= k.start or issue.start >= k.end for k in kept):
            kept.append(issue)
    return sorted(kept, key=lambda i: i.start)


def check_text(
    field: str,
    text: str,
    product: ProductInput,
    analysis: ProductAnalysis,
) -> list[ComplianceIssue]:
    """문구 하나 검수 (start, end는 이 문구 안에서의 위치, end 미포함)"""
    rules = load_rules()
    protected = _protected_spans(text, product)
    candidates = rules.general + [
        _functional_rule(r, product) for r in rules.functional
    ]

    issues: list[ComplianceIssue] = []
    for rule in candidates:
        for pattern in rule.patterns:
            for m in pattern.finditer(text):
                if m.end() == m.start() or _inside(m.start(), m.end(), protected):
                    continue
                if rule.except_with and all(
                    w in _sentence(text, m.start(), m.end()) for w in rule.except_with
                ):
                    continue
                issues.append(
                    ComplianceIssue(
                        field=field,
                        text=m.group(),
                        start=m.start(),
                        end=m.end(),
                        category=rule.category,
                        risk_level=rule.risk,
                        reason=rule.reason,
                        suggestion=rule.suggestion,
                        basis=rule.basis,
                        basis_url=rule.basis_url,
                        detected_by="rule",
                    )
                )

    color = rules.color
    for pattern in rules.color_patterns:
        for m in pattern.finditer(text):
            if _inside(m.start(), m.end(), protected):
                continue
            sentence = _sentence(text, m.start(), m.end())
            if analysis.product_type == "색조" and any(
                w in sentence for w in rules.color_allow
            ):
                continue
            issues.append(
                ComplianceIssue(
                    field=field,
                    text=m.group(),
                    start=m.start(),
                    end=m.end(),
                    category=color["category"],
                    risk_level=color["risk"],
                    reason=color["reason"],
                    suggestion=None,
                    basis=color["basis"],
                    basis_url=color["basis_url"],
                    detected_by="rule",
                )
            )

    return _remove_overlaps(issues)


def copy_fields(copy: AdCopyOutput) -> dict[str, str]:
    """검수 대상 필드 (해시태그는 공백으로 이어 붙여 하나의 문구로 검수)"""
    return {
        "headline": copy.ad_copy.headline,
        "subline": copy.ad_copy.subline,
        "cta": copy.ad_copy.cta,
        "caption": copy.caption,
        "hashtags": " ".join(copy.hashtags),
    }


def check_copy(
    copy: AdCopyOutput, product: ProductInput, analysis: ProductAnalysis
) -> list[ComplianceIssue]:
    """카피 전체 검수"""
    issues: list[ComplianceIssue] = []
    for field, text in copy_fields(copy).items():
        issues.extend(check_text(field, text, product, analysis))
    return issues
