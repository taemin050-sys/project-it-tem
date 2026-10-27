"""T-01..T-16: immutable, server-owned review binding (REFERENCE ONLY).

No FastAPI runtime gate, real owner wrapper, or DB transaction is exercised.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import copy
import json
from pathlib import Path

import pytest

from docs.contracts.validation import (
    ContractViolation, ReferenceReviewLedger, approval_allowed,
    canonical_copy_hash, canonical_review_input_hash,
)

FIX = Path(__file__).resolve().parents[1] / "docs" / "contracts" / "fixtures"


def fixture(name):
    return json.loads((FIX / (name + ".json")).read_text(encoding="utf-8"))


def context():
    return {
        "product_name": "라움 데일리 크림",
        "user_text": "건조함을 느낄 때 사용하는 부드러운 화장품",
        "product_facts": {
            "features": "부드러운 사용감",
            "ad_purpose": "신제품 소개",
            "is_functional": False,
        },
        "source_schema_version": "meeting-v0.5-unverified",
        "additional_review_inputs": {"declared_label": "라움 데일리 크림"},
    }


def stage(store, c, *, job="job01", revision="copy-r01", ctx=None):
    store.stage_job(
        job_id=job, copy_revision=revision, copy_output=c,
        review_context=context() if ctx is None else ctx,
    )


def finish(store, *, job="job01", report=None):
    token, snapshot = store.begin_review(
        job, model_version="fake-model-no-provider", rules_version="rule-set-v1",
    )
    return store.complete_review(
        token, fixture("compliance_report_pass") if report is None else report,
    )


def approve(store, c, rid, *, job="job01", revision="copy-r01"):
    return approval_allowed(
        store, job_id=job, review_record_id=rid,
        requested_copy_revision=revision, requested_copy_sha256=canonical_copy_hash(c),
    )


def reviewed(*, report=None, copy_name="ad_copy_output"):
    store = ReferenceReviewLedger()
    c = fixture(copy_name)
    stage(store, c)
    rec_id = finish(store, report=report)
    return store, c, rec_id


def test_t01_trusted_review_unchanged_copy_context_pass():
    store, c, record_id = reviewed()
    assert approve(store, c, record_id) is True


def test_t02_changed_headline_after_review_fails():
    store, c, record_id = reviewed()
    changed = copy.deepcopy(c)
    changed["ad_copy"]["headline"] = "수정된 광고 제목"
    stage(store, changed, revision="copy-r02")
    with pytest.raises(ContractViolation, match="STALE_REVIEW_COPY"):
        approve(store, changed, record_id, revision="copy-r02")


def test_t03_stale_report_with_new_copy_hash_remains_rejected():
    store, c, record_id = reviewed()
    changed = copy.deepcopy(c)
    changed["ad_copy"]["headline"] = "과거 보고서로 검수되지 않은 문장"
    stage(store, changed, revision="copy-r02")
    # Recomputing a caller-supplied expected hash does not forge a review.
    assert canonical_copy_hash(c) != canonical_copy_hash(changed)
    with pytest.raises(ContractViolation, match="STALE_REVIEW_COPY"):
        approve(store, changed, record_id, revision="copy-r02")


def test_t04_product_name_changes_while_copy_hash_unchanged_fails():
    store, c, record_id = reviewed()
    changed_ctx = context()
    changed_ctx["product_name"] = "미검수 변경제품명"
    stage(store, c, ctx=changed_ctx)
    with pytest.raises(ContractViolation, match="STALE_REVIEW_CONTEXT"):
        approve(store, c, record_id)


def test_t05_user_text_changed_after_review_fails():
    store, c, record_id = reviewed()
    ctx = context()
    ctx["user_text"] = "병을 완치하는 약이라는 문구"
    stage(store, c, ctx=ctx)
    with pytest.raises(ContractViolation, match="STALE_REVIEW_CONTEXT"):
        approve(store, c, record_id)


def test_t06_reviewed_product_claims_changed_after_review_fails():
    store, c, record_id = reviewed()
    ctx = context()
    ctx["product_facts"]["features"] = "질환 치료 효능"
    stage(store, c, ctx=ctx)
    with pytest.raises(ContractViolation, match="STALE_REVIEW_CONTEXT"):
        approve(store, c, record_id)


def test_t07_same_copy_new_revision_old_report_fails():
    store, c, record_id = reviewed()
    stage(store, c, revision="copy-r02")
    with pytest.raises(ContractViolation, match="STALE_REVIEW_COPY"):
        approve(store, c, record_id, revision="copy-r02")


def test_t08_missing_compliance_report_cannot_record_or_approve():
    store = ReferenceReviewLedger()
    c = fixture("ad_copy_output")
    stage(store, c)
    token, _ = store.begin_review(
        "job01", model_version="fake-model", rules_version="rule-v1",
    )
    with pytest.raises(ContractViolation, match="MISSING_COMPLIANCE"):
        store.complete_review(token, None)
    with pytest.raises(ContractViolation, match="MISSING_TRUSTED_REVIEW_RECORD"):
        approve(store, c, "any-unissued-report")


def test_t09_untrusted_or_nonexistent_record_fails():
    store, c, _ = reviewed()
    with pytest.raises(ContractViolation, match="MISSING_TRUSTED_REVIEW_RECORD"):
        approve(store, c, "arbitrary-client-claimed-record")
    with pytest.raises(ContractViolation, match="UNTRUSTED_REVIEW_STORE"):
        approve(None, c, "arbitrary-client-claimed-record")


def test_t09_forged_record_inserted_without_trusted_completion_is_rejected():
    original, c, rid = reviewed()
    other = ReferenceReviewLedger()
    stage(other, c)
    # A forged/copied dataclass is not a trusted completed reviewer execution.
    other._records[rid] = original._records[rid]
    with pytest.raises(ContractViolation, match="UNTRUSTED_REVIEW_PROVENANCE"):
        approve(other, c, rid)


def test_t10_report_passed_false_cannot_approve():
    store, c, record_id = reviewed(
        copy_name="copy_for_block",
        report=fixture("compliance_report_block"),
    )
    with pytest.raises(ContractViolation, match="COMPLIANCE_BLOCKED"):
        approve(store, c, record_id)


def test_t11_auto_revised_copy_stale_report_rejected():
    store, c, record_id = reviewed(
        copy_name="copy_for_block",
        report=fixture("compliance_report_block"),
    )
    changed = copy.deepcopy(c)
    changed["ad_copy"]["headline"] = "피부 결 정돈을 위한 루틴"
    stage(store, changed, revision="copy-r02")
    with pytest.raises(ContractViolation, match="STALE_REVIEW_COPY"):
        approve(store, changed, record_id, revision="copy-r02")


def test_t12_fresh_review_record_for_new_revision_passes():
    store, c, record_id = reviewed(
        copy_name="copy_for_block",
        report=fixture("compliance_report_block"),
    )
    fixed = copy.deepcopy(c)
    fixed["ad_copy"]["headline"] = "피부 결 정돈을 위한 루틴"
    stage(store, fixed, revision="copy-r02")
    with pytest.raises(ContractViolation):
        approve(store, fixed, record_id, revision="copy-r02")
    fresh_record_id = finish(store)  # new trusted reviewer cycle
    assert fresh_record_id != record_id
    assert approve(store, fixed, fresh_record_id, revision="copy-r02") is True


def test_t13_report_id_and_persisted_report_hash_mismatch_rejected():
    store, c, record_id = reviewed()
    with pytest.raises(ContractViolation, match="MISSING_TRUSTED_REVIEW_RECORD"):
        approve(store, c, "wrong-report-id")
    stored = store._records[record_id]  # simulate at-rest corruption, not user input
    store._records[record_id] = replace(stored, report_sha256="0" * 64)
    with pytest.raises(ContractViolation, match="REVIEW_REPORT_TAMPERED"):
        approve(store, c, record_id)


def test_t14_reuse_review_record_from_other_job_fails():
    store, c, record_id = reviewed()
    stage(store, c, job="job02")
    with pytest.raises(ContractViolation, match="REVIEW_JOB_MISMATCH"):
        approve(store, c, record_id, job="job02")


def test_t15_same_revision_different_copy_content_rejected():
    store, c, _ = reviewed()
    changed = copy.deepcopy(c)
    changed["caption"] += " 다른 내용"
    with pytest.raises(ContractViolation, match="CONFLICTING_COPY_REVISION"):
        stage(store, changed)


def test_t16_concurrent_double_approval_only_one_commits_in_memory():
    store, c, record_id = reviewed()
    def execute(_):
        try:
            return approve(store, c, record_id)
        except ContractViolation as e:
            return str(e)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(execute, range(2)))
    assert results.count(True) == 1
    assert results.count("ALREADY_APPROVED") == 1


def test_t16_review_finishing_after_context_race_rejected():
    store = ReferenceReviewLedger()
    c = fixture("ad_copy_output")
    stage(store, c)
    token, snapshot = store.begin_review(
        "job01", model_version="fake-model", rules_version="rule-v1",
    )
    ctx = context()
    ctx["product_facts"]["features"] = "변경된 주장"
    stage(store, c, ctx=ctx)
    with pytest.raises(ContractViolation, match="REVIEW_INPUT_CHANGED_DURING_REVIEW"):
        store.complete_review(token, fixture("compliance_report_pass"))


def test_cross_version_and_extra_context_invalidate_review():
    store, c, record_id = reviewed()
    ctx = context()
    ctx["source_schema_version"] = "later-owner-v0.6"
    stage(store, c, ctx=ctx)
    with pytest.raises(ContractViolation, match="STALE_REVIEW_CONTEXT"):
        approve(store, c, record_id)


def test_incomplete_context_fails_closed():
    store = ReferenceReviewLedger()
    c = fixture("ad_copy_output")
    ctx = context()
    del ctx["product_facts"]
    with pytest.raises(ContractViolation, match="INCOMPLETE_REVIEW_CONTEXT"):
        stage(store, c, ctx=ctx)


def test_old_untrusted_report_caller_signature_disallowed():
    c = fixture("ad_copy_output")
    with pytest.raises((TypeError, ContractViolation)):
        approval_allowed(c, fixture("compliance_report_pass"),
                         product_name="라움 데일리 크림",
                         copy_revision="copy-r01",
                         reviewed_revision="copy-r01",
                         reviewed_copy_sha256=canonical_copy_hash(c))


def test_canonical_review_input_vectors_stable_and_distinct():
    c = fixture("ad_copy_output")
    ctx = context()
    args = dict(
        job_id="job01", copy_revision="copy-r01", copy_output=c,
        review_context=ctx, model_version="fake-v1", rules_version="rule-v1",
    )
    digest = canonical_review_input_hash(**args)
    assert len(digest) == 64 and digest == canonical_review_input_hash(**copy.deepcopy(args))
    assert digest == "d5d3bc533bc030012267eeda2478c21401a3b99646007548fd3818ef22776899"
    assert canonical_copy_hash(c) == "00e69bd8bc4bdc26c1916c2089ce145bf802327fa7be9d76287d7b2116587847"
    assert canonical_copy_hash(c) != digest
    assert canonical_review_input_hash(**{**args, "review_context": {
        **ctx, "product_name": "제품명 변경",
    }}) != digest


def test_canonical_review_rejects_float_for_portability():
    store = ReferenceReviewLedger()
    c = fixture("ad_copy_output")
    ctx = context()
    ctx["product_facts"]["measured_value"] = 0.25
    with pytest.raises(ContractViolation, match="UNSUPPORTED_CANONICAL_JSON_TYPE"):
        stage(store, c, ctx=ctx)
