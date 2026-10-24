"""Persistent reservation, replay and provider-failure tests; zero network."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.serving.p4_cost_guard import (
    P4CostGuard, ProviderTimeout, ProviderRateLimited, ProviderUnavailable,
    ProviderInvalidResponse, fingerprint,
)


def fresh(tmp_path, budget=1000):
    return P4CostGuard(tmp_path / "private" / "billing.sqlite3",
                       max_budget_micro_usd=budget, enable_billable=True)


def execute(guard, *, job=None, phase="planning", key="attempt_001", price=200, data=None,
            call=lambda: "done"):
    return guard.execute(job_id=job or "a" * 32, phase=phase,
                         operation_key=key, request_hash=fingerprint(data or {"version": 1}),
                         max_cost_micro_usd=price, call=call)


def test_success_blocks_duplicate_after_restart(tmp_path):
    guard = fresh(tmp_path)
    result = execute(guard)
    assert result.value == "done" and result.billing_state == "unknown"
    again = fresh(tmp_path)
    called = []
    with pytest.raises(HTTPException) as e:
        execute(again, call=lambda: called.append("paid twice"))
    assert e.value.status_code == 409 and e.value.detail == "OPERATION_ALREADY_RECORDED"
    assert called == [] and len(again.snapshot()) == 1


def test_changed_payload_or_key_rejected_on_same_stage(tmp_path):
    guard = fresh(tmp_path)
    execute(guard)
    for change in [{"key": "attempt_002"}, {"data": {"version": 2}}]:
        with pytest.raises(HTTPException) as e:
            execute(guard, **change)
        assert e.value.status_code == 409 and e.value.detail == "OPERATION_CONFLICT"


def test_budget_guard_prevents_dispatch(tmp_path):
    guard = fresh(tmp_path, 250)
    execute(guard, price=200)
    dispatched = []
    with pytest.raises(HTTPException) as e:
        execute(guard, job="b"*32, phase="image", key="attempt_002", price=100,
                call=lambda: dispatched.append("called"))
    assert e.value.status_code == 429 and not dispatched
    assert len(guard.snapshot()) == 1


@pytest.mark.parametrize("exception,http,code", [
    (ProviderTimeout(), 504, "PROVIDER_TIMEOUT_BILLING_UNCERTAIN"),
    (TimeoutError(), 504, "PROVIDER_TIMEOUT_BILLING_UNCERTAIN"),
    (ProviderRateLimited(), 429, "PROVIDER_RATE_LIMITED"),
    (ProviderUnavailable(), 503, "PROVIDER_UNAVAILABLE"),
    (ProviderInvalidResponse(), 502, "PROVIDER_FAILED_BILLING_UNCERTAIN"),
    (RuntimeError("secret-should-not-leak"), 502, "PROVIDER_FAILED_BILLING_UNCERTAIN"),
])
def test_failure_is_unknown_no_retry(tmp_path, exception, http, code):
    guard = fresh(tmp_path)

    def bad():
        raise exception

    with pytest.raises(HTTPException) as e:
        execute(guard, call=bad)
    assert e.value.status_code == http and e.value.detail == code
    assert "secret" not in str(e.value.detail)
    entry, = fresh(tmp_path).snapshot()
    assert entry["status"] == "unknown" and entry["billing_state"] == "unknown"
    with pytest.raises(HTTPException) as duplicate:
        execute(guard)
    assert duplicate.value.status_code == 409


def test_crash_reserved_state_blocks_replay(tmp_path):
    guard = fresh(tmp_path)
    guard._reserve(job_id="a"*32, phase="image", operation_key="attempt_001",
                   request_hash=fingerprint({"x": 1}), max_cost_micro_usd=250)
    other = fresh(tmp_path)
    with pytest.raises(HTTPException) as e:
        execute(other, phase="image", key="attempt_001", data={"x": 1})
    assert e.value.status_code == 409
    assert other.snapshot()[0]["status"] == "reserved"


def test_fake_call_not_recorded_as_billed(tmp_path):
    guard = fresh(tmp_path)
    out = execute(guard, price=0)
    assert out.billing_state == "not_called"
    row, = guard.snapshot()
    assert row["billing_state"] == "not_called" and row["reserved_micro_usd"] == 0


def test_guard_checks_input_before_any_dispatch(tmp_path):
    guard = fresh(tmp_path)
    for kw in [{"job": "../../bad"}, {"phase": "typo"}, {"key": "!"}, {"price": 2000}]:
        with pytest.raises((ValueError, HTTPException)):
            execute(guard, **kw)
    assert guard.snapshot() == []


def test_parallel_instances_cannot_dispatch_same_stage_twice(tmp_path):
    guard = fresh(tmp_path)
    def one(_):
        try:
            return execute(fresh(tmp_path), price=1).value
        except HTTPException as e:
            return e.status_code
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(one, range(16)))
    assert results.count("done") == 1 and results.count(409) == 15
    assert len(guard.snapshot()) == 1


def test_fingerprint_ignores_key_order_and_never_stores_payload(tmp_path):
    assert fingerprint({"a": 1, "b": 2}) == fingerprint({"b": 2, "a": 1})
    guard = fresh(tmp_path)
    execute(guard, data={"secret": "not-for-sqlite"})
    db = (tmp_path / "private" / "billing.sqlite3").read_bytes()
    assert b"not-for-sqlite" not in db


def test_billable_dispatch_disabled_by_default(tmp_path):
    guard = P4CostGuard(tmp_path / "billing.sqlite3", max_budget_micro_usd=1000)
    called = []
    with pytest.raises(HTTPException) as e:
        execute(guard, call=lambda: called.append("would-call"))
    assert e.value.status_code == 503 and e.value.detail == "P4_BILLABLE_CALLS_DISABLED"
    assert not called and not guard.snapshot()
