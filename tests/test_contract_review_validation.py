"""Contract-level synthetic fixture tests. No model calls; runtime approval unimplemented."""
import copy
import json
from pathlib import Path

import pytest

from docs.contracts.validation import (
    ContractViolation, ReferenceReviewLedger, approval_allowed, canonical_copy_hash,
    validate_compliance,
)

FIX = Path(__file__).resolve().parents[1] / "docs" / "contracts" / "fixtures"


def load(name):
    return json.loads((FIX / (name + ".json")).read_text(encoding="utf-8"))


def good_report():
    return load("compliance_report_pass")


def bad_report():
    return load("compliance_report_block")


def unsafe_copy():
    return load("copy_for_block")


def check(c, r):
    return validate_compliance(c, r, product_name="라움 데일리 크림")


def test_safe_copy_with_empty_issues():
    assert check(load("ad_copy_output"), good_report())


def test_block_risk_in_middle():
    assert check(unsafe_copy(), bad_report()) is False


@pytest.mark.parametrize("headline,offset", [
    ("피부 재생 크림", 0),
    ("오늘의 피부 재생 크림", 4),
    ("크림과 함께 피부 재생", len("크림과 함께 ")),
])
def test_headline_start_middle_end(headline, offset):
    c = unsafe_copy()
    c["ad_copy"]["headline"] = headline
    r = bad_report()
    r["issues"][0]["start"] = offset
    r["issues"][0]["end"] = offset + len("피부 재생")
    assert check(c, r) is False


@pytest.mark.parametrize("start,end", [(0, 5), (4, 8), (-1, 4), (99, 105), (4, 100), (True, 9)])
def test_incorrect_offsets_are_rejected(start, end):
    r = bad_report()
    r["issues"][0].update(start=start, end=end)
    with pytest.raises(ContractViolation, match="INVALID_OFFSET|OFFSET_TEXT_MISMATCH"):
        check(unsafe_copy(), r)


def test_repeated_expression_selects_occurrence():
    c = unsafe_copy()
    c["ad_copy"]["headline"] = "피부 재생, 피부 재생"
    r = bad_report()
    second = c["ad_copy"]["headline"].rindex("피부 재생")
    r["issues"][0].update(start=second, end=second + len("피부 재생"))
    assert check(c, r) is False
    r["issues"][0]["start"] += 1
    r["issues"][0]["end"] += 1
    with pytest.raises(ContractViolation, match="INVALID_OFFSET|OFFSET_TEXT_MISMATCH"):
        check(c, r)


def test_korean_emoji_uses_unicode_codepoints():
    c = unsafe_copy()
    c["ad_copy"]["headline"] = "🧴 오늘의 피부 재생"
    r = bad_report()
    offset = c["ad_copy"]["headline"].index("피부 재생")
    assert offset == len("🧴 오늘의 ")
    r["issues"][0].update(start=offset, end=offset + len("피부 재생"))
    assert check(c, r) is False
    # JS UTF-16 index is different for the leading emoji (converted in React).
    r["issues"][0]["start"] += 1
    r["issues"][0]["end"] += 1
    with pytest.raises(ContractViolation):
        check(c, r)


def test_hashtag_offsets_provisional_space_join():
    c = unsafe_copy()
    c["hashtags"] = ["#기초화장품", "#피부재생", "#화장품"]
    combined = " ".join(c["hashtags"])
    r = bad_report()
    start = combined.index("#피부재생")
    r["issues"][0].update(field="hashtags", text="#피부재생",
                          start=start, end=start + len("#피부재생"))
    assert check(c, r) is False
    r["issues"][0]["start"] = 0
    r["issues"][0]["end"] = len("#피부재생")
    with pytest.raises(ContractViolation):
        check(c, r)


def test_hashtag_issue_cannot_cross_array_items():
    c = unsafe_copy()
    c["hashtags"] = ["#피부", "#재생"]
    r = bad_report()
    full = " ".join(c["hashtags"])
    start, end = 2, len(full)
    r["issues"][0].update(field="hashtags", text=full[start:end], start=start, end=end)
    with pytest.raises(ContractViolation, match="HASHTAG_CROSS_ITEM"):
        check(c, r)


def test_missing_user_text_source_must_fail():
    r = bad_report()
    r["issues"][0]["field"] = "user_text"
    with pytest.raises(ContractViolation, match="UNRESOLVED_COPY_FIELD"):
        check(unsafe_copy(), r)


def _trusted_context():
    # Reference-only review scope; owner must confirm actual inputs before Live.
    return {
        "product_name": "라움 데일리 크림",
        "user_text": "매일 쓰는 부드러운 화장품",
        "product_facts": {"features": "부드러운 사용감", "ad_purpose": "소개"},
        "source_schema_version": "meeting-v0.5-unverified",
        "additional_review_inputs": {},
    }


def _reviewed_ledger(c=None, r=None):
    c = c if c is not None else load("ad_copy_output")
    r = r if r is not None else good_report()
    store = ReferenceReviewLedger()
    store.stage_job(job_id="job01", copy_revision="copy-r01", copy_output=c,
                    review_context=_trusted_context())
    token, _ = store.begin_review(
        "job01", model_version="fake-no-provider", rules_version="fake-rule01",
    )
    record_id = store.complete_review(token, r)
    return store, record_id, c


def _approve(store, record_id, c, *, revision="copy-r01", job="job01"):
    return approval_allowed(
        store, job_id=job, review_record_id=record_id,
        requested_copy_revision=revision, requested_copy_sha256=canonical_copy_hash(c),
    )


def test_revision_and_digest_check():
    store, rec, c = _reviewed_ledger()
    assert _approve(store, rec, c)
    other, old_record, original = _reviewed_ledger()
    changed = copy.deepcopy(original)
    changed["ad_copy"]["headline"] += "!"
    with pytest.raises(ContractViolation, match="CONFLICTING_COPY_REVISION"):
        other.stage_job(job_id="job01", copy_revision="copy-r01", copy_output=changed,
                        review_context=_trusted_context())
    other.stage_job(job_id="job01", copy_revision="copy-r02", copy_output=changed,
                    review_context=_trusted_context())
    with pytest.raises(ContractViolation, match="STALE_REVIEW_COPY"):
        _approve(other, old_record, changed, revision="copy-r02")


def test_report_missing_or_review_missing_fails_closed():
    c = load("ad_copy_output")
    store = ReferenceReviewLedger()
    store.stage_job(job_id="job01", copy_revision="copy-r01", copy_output=c,
                    review_context=_trusted_context())
    with pytest.raises(ContractViolation, match="MISSING_TRUSTED_REVIEW_RECORD"):
        _approve(store, "untrusted-client-id", c)
    token, _ = store.begin_review(
        "job01", model_version="fake-no-provider", rules_version="fake-rule01",
    )
    with pytest.raises(ContractViolation, match="MISSING_COMPLIANCE"):
        store.complete_review(token, None)
    with pytest.raises(ContractViolation, match="UNTRUSTED_REVIEW_STORE"):
        approval_allowed(None, job_id="job01", review_record_id="fake",
                         requested_copy_revision="copy-r01",
                         requested_copy_sha256=canonical_copy_hash(c))


def test_violating_copy_approval_denied():
    store, rec, c = _reviewed_ledger(unsafe_copy(), bad_report())
    with pytest.raises(ContractViolation, match="COMPLIANCE_BLOCKED"):
        _approve(store, rec, c)


def test_auto_revised_copy_needs_fresh_review():
    store, rec, old_copy = _reviewed_ledger(unsafe_copy(), bad_report())
    fixed = copy.deepcopy(old_copy)
    fixed["ad_copy"]["headline"] = bad_report()["revised_fields"]["headline"]
    store.stage_job(job_id="job01", copy_revision="copy-r02", copy_output=fixed,
                    review_context=_trusted_context())
    with pytest.raises(ContractViolation, match="STALE_REVIEW_COPY"):
        _approve(store, rec, fixed, revision="copy-r02")


def test_passed_flag_conflict_rejected():
    r = bad_report()
    r["passed"] = True
    with pytest.raises(ContractViolation, match="PASSED_RISK_CONTRADICTION"):
        check(unsafe_copy(), r)


def test_no_issues_but_failed_flag_rejected():
    r = good_report()
    r["passed"] = False
    with pytest.raises(ContractViolation, match="PASSED_RISK_CONTRADICTION"):
        check(load("ad_copy_output"), r)
