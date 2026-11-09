"""Authoritative Owner DTOs adapted to a monotonic, immutable live workflow."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from src.text_generation.schemas import (
    AdCopyOutput, ImagePromptOutput, ProductAnalysisResult, ProductInput, ResearchResult,
    ComplianceReport, FunctionalType, EmojiLevel
)
from src.serving.text_v08_mapper import (
    verify_analysis, verify_copy, verify_research, verify_prompt,
    TextBoundaryError,
)


class LiveGateError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code=code


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                separators=(",", ":"), allow_nan=False).encode()).hexdigest()


class LiveInput(BaseModel):
    model_config=ConfigDict(extra="forbid",strict=True)
    # Current Owner Text #25 (v0.10) defines functional_types and emoji_level.
    # Existing snapshots remain immutable; only new inputs follow this DTO.
    product: dict
    # A new FE explicitly sends this final image ratio; old requests omit it
    # and continue to replay their exact historical A v1 snapshots.
    image_size: Literal["3:4","4:5","9:16"] | None = None
    generation_mode: Literal["composed","freeform"] | None = None
    customer_request_id: str=Field(min_length=10,max_length=128)


# PM_TRACK_A_OWNER_INTEGRATION_PRIORITY_AND_IMAGE_SCOPE_20261109
# The Owner Image library can generate individually for different Job IDs,
# but Track A does NOT authorize batch/mixed candidates per Job/request.
# Validate at ingress, Queue admission, and again in the paid Worker.
_SINGLE_IMAGE_SNAPSHOT_KEYS=frozenset({
    "product","customer_request_id","image_size","generation_mode",
    "ordered_asset_hashes",
})


def assert_single_image_scope(snapshot: dict) -> None:
    """Require exactly one frozen mode/ratio; no count/mix/batch extension.

    Legacy approved Jobs without explicit mode/ratio remain composed, 4:5.
    This validator has no IO and must execute before any paid reservation.
    """
    if type(snapshot) is not dict or set(snapshot)-_SINGLE_IMAGE_SNAPSHOT_KEYS:
        raise LiveGateError("PM_IMAGE_MULTICANDIDATE_SCOPE_NOT_APPROVED")
    mode=snapshot.get("generation_mode","composed")
    ratio=snapshot.get("image_size","4:5")
    if (mode not in ("composed","freeform") or ratio not in ("3:4","4:5","9:16")
            or ("generation_mode" in snapshot and "image_size" not in snapshot)):
        raise LiveGateError("PM_IMAGE_SINGLE_MODE_RATIO_INVALID")


def assert_single_image_request_params(request) -> None:
    """Reject count/mix flags on bodyless queue actions, even if ignored by old handlers."""
    if request.query_params:
        raise LiveGateError("PM_IMAGE_MULTICANDIDATE_SCOPE_NOT_APPROVED")


def validate_input(value: dict, asset_rows: list[dict]) -> tuple[dict,str]:
    try:
        incoming=LiveInput.model_validate(value,strict=True)
        raw=incoming.product
        if not isinstance(raw,dict):
            raise LiveGateError("PRODUCT_INPUT_INVALID")
        extras=set(raw)-set(ProductInput.model_fields)
        if extras:raise LiveGateError("PRODUCT_INPUT_UNKNOWN_FIELDS")
        # Owner Text v0.10 ProductInput intentionally accepts:
        #   is_functional=True,  functional_types=[] -> claims require evidence
        #   is_functional=False, functional_types=[...] -> auto-switch True
        #   repeated types -> de-duplicate in its own model_validator.
        # Never replace Owner's normalization with a contradictory Serving gate.
        TypeAdapter(list[FunctionalType]).validate_python(
            raw.get("functional_types",[]),strict=True)
        product=ProductInput.model_validate(raw,strict=True)
        if not product.photo_verified:
            raise LiveGateError("PHOTO_RIGHTS_NOT_VERIFIED")
        products=[a for a in asset_rows if a["role"]=="product"]
        references=[a for a in asset_rows if a["role"]=="reference"]
        if (len(products)!=product.product_image_count or
            len(references)!=product.reference_image_count or
            not 2<=len(products)<=5 or len(references)>5):
            raise LiveGateError("PHOTO_COUNT_MISMATCH")
        if not product.product_name.strip() or not product.features.strip() or not product.ad_purpose.strip():
            raise LiveGateError("PRODUCT_INPUT_INCOMPLETE")
        snapshot={"product":product.model_dump(mode="json"),
                  "customer_request_id":incoming.customer_request_id}
        if incoming.image_size is not None:
            snapshot["image_size"]=incoming.image_size
        if incoming.generation_mode is not None:
            # New-mode Jobs must pin the ratio, legacy Jobs stay byte-identical.
            if incoming.image_size is None:
                raise LiveGateError("GENERATION_MODE_REQUIRES_IMAGE_SIZE")
            snapshot["generation_mode"]=incoming.generation_mode
        snapshot["ordered_asset_hashes"]=[
            {"asset_id":a["asset_id"],"role":a["role"],"sha256":a["sha256"]}
            for a in asset_rows]
        assert_single_image_scope(snapshot)
        return snapshot,digest(snapshot)
    except (TypeError,ValueError) as e:
        if isinstance(e,LiveGateError):raise
        raise LiveGateError("PRODUCT_INPUT_INVALID") from None


def owner_text_snapshots(analysis, research, copy):
    a=verify_analysis(analysis,model=ProductAnalysisResult)
    r=verify_research(research,model=ResearchResult)
    c=verify_copy(copy,model=AdCopyOutput)
    return a.raw,r.original,r.display,c.output,c.sha256


def strict_review(copy: dict, product: dict, analysis: dict) -> dict:
    """Owner rule engine + fail-safe name exception audit.

    Owner excludes ALL occurrences of any risky word equal to a brand name.
    That can hide a second, independent treatment claim ("치료 ... 치료").
    Run the original checker, then unprotected checks with name masking disabled;
    conservatively block unverified risk claims (including ambiguous brand use).
    """
    from src.text_generation.compliance.report_builder import review_copy
    from src.text_generation.compliance.rule_checker import check_copy
    owner_copy=AdCopyOutput.model_validate(copy,strict=True)
    owner_product=ProductInput.model_validate(product,strict=True)
    owner_analysis=ProductAnalysisResult.model_validate(analysis,strict=True).analysis
    baseline=review_copy(owner_copy,owner_product,owner_analysis)
    unprotected=owner_product.model_copy(update={"brand_name":None,"product_name":""})
    extra=check_copy(owner_copy,unprotected,owner_analysis)
    issues=list(baseline.issues)
    existing={(x.field,x.start,x.end,x.text) for x in issues}
    for issue in extra:
        key=(issue.field,issue.start,issue.end,issue.text)
        if key not in existing:
            issues.append(issue)
            existing.add(key)
    # Owner #27/v0.11 already evaluates specific functional types, but its
    # explanation no longer contains the old "기능성(<type>)" marker.
    # Re-evaluate the EXACT matched expression against the Owner rule
    # taxonomy, never infer the type from the free-form explanation alone.
    # Unknown or multi-category matches fail closed unless ALL types were
    # selected; the legacy reason marker remains a compatibility fallback.
    selected=set(owner_product.functional_types)
    if selected:
        import re
        from src.text_generation.compliance.rule_checker import load_rules
        functional=load_rules().functional
        upgraded=[]
        for issue in issues:
            if issue.category=="기능성 오인" and issue.risk_level!="위반 의심":
                types_for_claim={
                    r["functional_type"] for r in functional
                    if any(pattern.fullmatch(issue.text) for pattern in r["compiled"])
                }
                legacy=re.search(r"기능성\(([^)]+)\)",issue.reason)
                if legacy:
                    types_for_claim.add(legacy.group(1))
                if not types_for_claim or not types_for_claim.issubset(selected):
                    issue=issue.model_copy(update={
                        "risk_level":"위반 의심",
                        "reason":"선택한 기능성 종류가 아닌 효능 표현입니다. "+
                                 issue.reason,
                    })
            upgraded.append(issue)
        issues=upgraded
    # Owner's functional taxonomy is 10 entries, while rule_checker.yaml
    # currently specifies regexes for only 7. Conservative literal fallback
    # for the 3 uncovered names; NOT exhaustive regulation/clinical validation.
    # For unselected types, fail closed on direct claims; for selected or
    # unspecified functional type, warn that evidence remains unverified.
    from src.text_generation.schemas import ComplianceIssue
    literal_fallback={
        "태닝":(r"태닝",),
        "모발색상변화":(r"모발\s*색상\s*변화",r"모발색상변화"),
        "체모제거":(r"체모\s*제거",r"체모제거"),
    }
    snippets={
        "product_name":owner_product.product_name,
        "headline":owner_copy.ad_copy.headline,
        "subline":owner_copy.ad_copy.subline,
        "cta":owner_copy.ad_copy.cta,
        "caption":owner_copy.caption,
        "hashtags":" ".join(owner_copy.hashtags),
    }
    import re
    for kind,patterns in literal_fallback.items():
        for field,text in snippets.items():
            for pattern in patterns:
                for match in re.finditer(pattern,text,re.IGNORECASE):
                    if any(x.field==field and
                           match.start()<x.end and match.end()>x.start
                           for x in issues):
                        continue
                    selected_types=set(owner_product.functional_types)
                    risk=("위반 의심" if not owner_product.is_functional or
                          (selected_types and kind not in selected_types)
                          else "근거 확인 필요")
                    issues.append(ComplianceIssue(
                        field=field,text=match.group(0),
                        start=match.start(),end=match.end(),
                        category="기능성 오인",risk_level=risk,
                        reason=(f"기능성 종류 '{kind}' 관련 표현: "
                                "선택 종류 및 심사·보고 근거를 확인해야 합니다. "
                                "현재 검출은 명시적 효능 이름에 한정합니다."),
                        suggestion=None,basis="Text Owner v0.10 기능성 종류 분류",
                        detected_by="rule",auto_fixed=False,
                    ))
    issues.sort(key=lambda x:(x.field,x.start,x.end))
    confirmed=not any(x.risk_level=="위반 의심" for x in issues)
    report=baseline.model_copy(update={
        "passed":bool(baseline.passed and confirmed),
        "issues":issues,
        "checklist":list(baseline.checklist)+(
            ["브랜드/제품명 포함 위험어는 원본 표시광고 근거를 별도로 확인해야 합니다."]
            if len(issues)!=len(baseline.issues) else []
        )
    })
    return report.model_dump(mode="json")


def live_prompt(prompt: dict, copy: dict) -> dict:
    cp=verify_copy(copy,model=AdCopyOutput)
    return verify_prompt(prompt,cp,model=ImagePromptOutput)
