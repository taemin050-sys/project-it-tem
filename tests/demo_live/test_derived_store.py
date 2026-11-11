"""Atomic, nonbillable state, lease and approval-regression checks."""
from concurrent.futures import ThreadPoolExecutor
import sqlite3

import pytest

from demo_staging.live.contracts import LiveGateError
from demo_staging.live.derived_store import (
    DerivedStore, LOCAL_RENDER_PROTOCOL, migrate_derived_schema,
)


ACTOR = "b_owner"
JOB = "fixture_job"
RECIPE = "1" * 64
CONTEXT = "2" * 64
PREVIEW = "3" * 64


@pytest.fixture
def store(tmp_path):
    database = tmp_path / "live.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE protected_original (name TEXT PRIMARY KEY,body BLOB)")
        connection.execute("INSERT INTO protected_original VALUES ('receipt',?)", (b"original",))
    migrate_derived_schema(database)
    return DerivedStore(database)


def admit(store, **changes):
    args = dict(actor=ACTOR, job_id=JOB, recipe_sha=RECIPE, context_sha=CONTEXT,
                record={"copy_generation": 1, "f09_sha": "4"*64, "epoch": 2},
                reviewer_actor=ACTOR, reviewer_role="owner", scope="fixture_only",
                idempotency_key="admit-original")
    args.update(changes)
    return store.append_admission(**args)


def enqueue(store, grant=None, **changes):
    grant = grant or admit(store)
    args = dict(actor=ACTOR, job_id=JOB, grant_id=grant["grant_id"],
                expected_grant_revision=grant["revision"], recipe_sha=RECIPE,
                context_sha=CONTEXT, payload={"recipe": {"sha": RECIPE}, "context": CONTEXT},
                idempotency_key="render-original")
    args.update(changes)
    return store.enqueue_render(**args)


def rendered(store):
    enqueue(store)
    task = store.claim_render(billing_unknown=False, worker_id="local-one", now=100, lease_seconds=60)
    return store.complete_render(actor=ACTOR, job_id=JOB, derived_id=task["derived_id"],
        expected_revision=task["revision"], lease_token=task["lease_token"], now=110,
        result_sha="5"*64, preview_sha=PREVIEW, local_receipt_sha="6"*64,
        artifacts={"preview": {"sha256": PREVIEW}})


def review(store, render, **changes):
    args = dict(actor=ACTOR, job_id=JOB, derived_id=render["derived_id"],
                expected_revision=render["revision"], preview_sha=PREVIEW,
                recipe_sha=RECIPE, context_sha=CONTEXT, decision="APPROVE",
                record={"source_pixel_preservation": True, "scope": "OFFLINE_FIXTURE"},
                reviewer_actor=ACTOR, reviewer_role="owner", idempotency_key="review-original")
    args.update(changes)
    return store.append_review(**args)


def test_admission_is_atomic_with_caller_same_database_context(store):
    with pytest.raises(RuntimeError):
        with store.transaction() as connection:
            admit(store, c=connection)
            connection.execute("INSERT INTO protected_original VALUES ('new',?)", (b"rollback",))
            raise RuntimeError("abort entire authority check")
    assert store.list_admissions(ACTOR, JOB) == []
    with store.connection(readonly=True) as connection:
        assert connection.execute("SELECT name FROM protected_original").fetchall()[0][0] == "receipt"
        assert connection.execute("SELECT COUNT(*) FROM protected_original").fetchone()[0] == 1


def test_external_connection_must_be_the_same_active_transaction(store, tmp_path):
    with store.connection() as connection:
        with pytest.raises(LiveGateError, match="DERIVED_TRANSACTION_REQUIRED"):
            admit(store, c=connection)
    with sqlite3.connect(tmp_path / "different.sqlite") as connection:
        connection.execute("BEGIN IMMEDIATE")
        with pytest.raises(LiveGateError, match="DERIVED_TRANSACTION_REQUIRED"):
            admit(store, c=connection)


def test_append_only_grant_review_records(store):
    grant = admit(store)
    task = rendered(store)
    approved = review(store, task)
    assert approved["state"] == "APPROVED"
    for table in ("live_derived_recipe_admissions", "live_derived_reviews"):
        for operation in (f"UPDATE {table} SET actor='other'", f"DELETE FROM {table}"):
            with pytest.raises(sqlite3.IntegrityError, match="DERIVED_EVENT_IMMUTABLE"):
                with store.transaction() as connection:
                    connection.execute(operation)
    assert store.get_admission(ACTOR, JOB, grant["grant_id"])["record"]["payload"]["epoch"] == 2


def test_admission_idempotency_preserves_identity_and_rejects_changed_payload(store):
    first = admit(store)
    assert admit(store) == first
    with pytest.raises(LiveGateError, match="DERIVED_IDEMPOTENCY_CONFLICT"):
        admit(store, context_sha="9"*64)
    assert len(store.list_admissions(ACTOR, JOB)) == 1


def test_cross_actor_and_job_reads_never_disclose_records(store):
    grant = admit(store)
    render, _ = enqueue(store, grant)
    for actor, job in (("other", JOB), (ACTOR, "other")):
        with pytest.raises(LiveGateError, match="DERIVED_NOT_FOUND"):
            store.get_admission(actor, job, grant["grant_id"])
        with pytest.raises(LiveGateError, match="DERIVED_NOT_FOUND"):
            store.get_render(actor, job, render["derived_id"])
        assert store.list_admissions(actor, job) == []
        assert store.list_renders(actor, job) == []


def test_revoke_then_regrant_never_revives_old_intent(store):
    grant = admit(store)
    render, _ = enqueue(store, grant)
    revoked = store.revoke_admission(actor=ACTOR, job_id=JOB, grant_id=grant["grant_id"],
        expected_revision=1, reviewer_actor=ACTOR, reviewer_role="owner",
        record={"reason": "copy changed"}, idempotency_key="revoke")
    assert revoked["revision"] == 2
    assert store.get_render(ACTOR, JOB, render["derived_id"])["state"] == "STALE"
    restored = admit(store, grant_id=grant["grant_id"], expected_revision=2,
                     idempotency_key="restored")
    assert restored["revision"] == 3
    with pytest.raises(LiveGateError, match="DERIVED_ADMISSION_STALE"):
        enqueue(store, grant)
    assert store.claim_render(billing_unknown=False, worker_id="local", now=100) is None
    new, created = enqueue(store, restored, idempotency_key="new-revision")
    assert created and new["derived_id"] != render["derived_id"]


def test_same_render_payload_has_single_durable_intent(store):
    grant = admit(store)
    first, created = enqueue(store, grant)
    assert created
    same, created = enqueue(store, grant)
    assert not created and same == first
    alias, created = enqueue(store, grant, idempotency_key="another-key")
    assert not created and alias["derived_id"] == first["derived_id"]
    with pytest.raises(LiveGateError, match="DERIVED_IDEMPOTENCY_CONFLICT"):
        enqueue(store, grant, payload={"changed": True})
    assert len(store.list_renders(ACTOR, JOB)) == 1


def test_concurrent_enqueue_and_claim_are_single_flight(store):
    grant = admit(store)
    with ThreadPoolExecutor(max_workers=2) as pool:
        submissions = list(pool.map(lambda _: enqueue(store, grant), range(2)))
    assert sum(created for _, created in submissions) == 1
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda i: store.claim_render(billing_unknown=False, worker_id=f"worker-{i}", now=100), range(2)))
    assert sum(item is not None for item in claims) == 1
    assert len(store.list_renders(ACTOR, JOB)) == 1


def test_unknown_billing_and_unsupported_protocol_cannot_claim(store):
    enqueue(store)
    assert store.claim_render(billing_unknown=True, worker_id="local", now=100) is None
    with pytest.raises(LiveGateError, match="DERIVED_PROTOCOL_UNSUPPORTED"):
        store.claim_render(billing_unknown=False, worker_id="old", protocol="LIVE_DUAL_V1", now=100)
    with pytest.raises(LiveGateError, match="DERIVED_RENDER_REQUEST_INVALID"):
        enqueue(store, protocol="LIVE_DUAL_V1")
    assert store.claim_render(billing_unknown=False, worker_id="local", now=100)["protocol"] == LOCAL_RENDER_PROTOCOL


def test_expired_lease_is_fenced_and_late_result_cannot_commit(store):
    enqueue(store)
    first = store.claim_render(billing_unknown=False, worker_id="first", lease_seconds=10, now=100)
    assert store.claim_render(billing_unknown=False, worker_id="second", now=109) is None
    second = store.claim_render(billing_unknown=False, worker_id="second", now=111)
    assert second["derived_id"] == first["derived_id"]
    assert second["lease_token"] != first["lease_token"]
    assert second["revision"] > first["revision"]
    values = dict(actor=ACTOR, job_id=JOB, derived_id=first["derived_id"],
                  result_sha="5"*64, preview_sha=PREVIEW, local_receipt_sha="6"*64, artifacts={})
    with pytest.raises(LiveGateError, match="DERIVED_LEASE_STALE"):
        store.complete_render(**values, expected_revision=first["revision"],
                              lease_token=first["lease_token"], now=112)
    result = store.complete_render(**values, expected_revision=second["revision"],
                                   lease_token=second["lease_token"], now=112)
    assert result["state"] == "REVIEW_REQUIRED"


def test_renew_lease_preserves_cas_and_expired_worker_cannot_renew(store):
    enqueue(store)
    item = store.claim_render(billing_unknown=False, worker_id="local", lease_seconds=10, now=100)
    args = dict(actor=ACTOR, job_id=JOB, derived_id=item["derived_id"],
                expected_revision=item["revision"], lease_token=item["lease_token"])
    renewed = store.renew_lease(**args, lease_seconds=20, now=105)
    assert renewed["revision"] == item["revision"]
    assert renewed["lease_expires_at"] == 125
    with pytest.raises(LiveGateError, match="DERIVED_LEASE_STALE"):
        store.renew_lease(**args, now=125)


def test_holding_failed_render_does_not_requeue_or_touch_sibling(store):
    grant = admit(store)
    first, _ = enqueue(store, grant)
    second_grant = admit(store, job_id="sibling", idempotency_key="sibling-grant")
    sibling, _ = enqueue(store, second_grant, job_id="sibling", idempotency_key="sibling-render")
    item = store.claim_render(billing_unknown=False, worker_id="local", now=100)
    # Creation order is stable but use the actual claim's identity.
    result = store.fail_render(actor=item["actor"], job_id=item["job_id"],
        derived_id=item["derived_id"], expected_revision=item["revision"],
        lease_token=item["lease_token"], error_code="LABEL_HOLD", hold=True, now=101)
    assert result["state"] == "HOLD"
    remaining = store.claim_render(billing_unknown=False, worker_id="local", now=102)
    assert remaining is not None and remaining["derived_id"] != item["derived_id"]
    assert {first["derived_id"], sibling["derived_id"]} == {item["derived_id"], remaining["derived_id"]}


def test_explicit_local_retry_reuses_intent_and_rechecks_admission(store):
    enqueue(store)
    item = store.claim_render(billing_unknown=False, worker_id="local", now=100)
    failed = store.fail_render(actor=ACTOR, job_id=JOB, derived_id=item["derived_id"],
        expected_revision=item["revision"], lease_token=item["lease_token"],
        error_code="LOCAL_FILE_WRITE_FAILED", now=101)
    assert store.claim_render(billing_unknown=False, worker_id="local", now=102) is None
    queued = store.retry_render(actor=ACTOR, job_id=JOB, derived_id=item["derived_id"],
                                expected_revision=failed["revision"])
    assert queued["state"] == "QUEUED" and queued["derived_id"] == item["derived_id"]
    assert store.claim_render(billing_unknown=False, worker_id="local", now=103)["derived_id"] == item["derived_id"]
    assert len(store.list_renders(ACTOR, JOB)) == 1


def test_review_rejects_stale_revision_or_wrong_context(store):
    item = rendered(store)
    for changes in ({"expected_revision": item["revision"]-1}, {"preview_sha": "9"*64},
                    {"context_sha": "9"*64}, {"recipe_sha": "9"*64}):
        with pytest.raises(LiveGateError, match="DERIVED_REVIEW_STALE"):
            review(store, item, **changes)
    assert store.get_render(ACTOR, JOB, item["derived_id"])["state"] == "REVIEW_REQUIRED"


def test_review_revoke_prevents_approval_reactivation(store):
    item = rendered(store)
    approved = review(store, item)
    assert store.require_approval(ACTOR, JOB, item["derived_id"])["approval_sha"] == approved["approval_sha"]
    revoked = review(store, approved, decision="REVOKE", idempotency_key="review-revoke",
                     record={"reason": "human withdrew"})
    assert revoked["state"] == "REVOKED" and revoked["approval_sha"] is None
    assert revoked["latest_review"]["revision"] == 2
    with pytest.raises(LiveGateError, match="DERIVED_APPROVAL_REQUIRED"):
        store.require_approval(ACTOR, JOB, item["derived_id"])
    with pytest.raises(LiveGateError, match="DERIVED_REVIEW_STATE_INVALID"):
        review(store, revoked, idempotency_key="reapprove-without-new-render")
    replayed = review(store, item)
    assert replayed["state"] == "REVOKED"
    assert replayed["latest_review"]["event_kind"] == "REVOKE"


def test_final_bytes_must_equal_exact_approved_preview_and_selection(store):
    item = rendered(store)
    approved = review(store, item)
    args = dict(actor=ACTOR, job_id=JOB, derived_id=item["derived_id"],
                expected_revision=approved["revision"], approval_sha=approved["approval_sha"],
                preview_sha=PREVIEW, final_sha=PREVIEW, caption_sha="7"*64,
                receipt_sha="8"*64, artifacts={"final": {"sha256": PREVIEW}})
    with pytest.raises(LiveGateError, match="DERIVED_FINALIZE_STALE"):
        store.finalize_render(**(args | {"final_sha": "9"*64}))
    final = store.finalize_render(**args)
    assert final["state"] == "COMPLETED"
    assert store.finalize_render(**args) == final
    selected = store.select_render(actor=ACTOR, job_id=JOB, derived_id=item["derived_id"],
                                  expected_revision=final["revision"], expected_final_sha=PREVIEW)
    assert selected["selected"] == 1
    revoked = review(store, selected, decision="REVOKE", idempotency_key="revoke-final")
    assert revoked["final_sha"] == PREVIEW
    assert revoked["selected"] == 0
    with pytest.raises(LiveGateError, match="DERIVED_APPROVAL_REQUIRED"):
        store.require_approval(ACTOR, JOB, item["derived_id"])
    with store.connection(readonly=True) as connection:
        assert connection.execute("SELECT body FROM protected_original WHERE name='receipt'").fetchone()[0] == b"original"


def test_no_provider_attempt_or_cost_tables_are_created(store):
    rendered(store)
    with store.connection(readonly=True) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert tables == {"protected_original", "live_derived_recipe_admissions", "live_derived_renders", "live_derived_reviews"}


def test_changed_payload_is_not_consumed_by_worker(store):
    task, _ = enqueue(store)
    with store.transaction() as connection:
        connection.execute("UPDATE live_derived_renders SET payload_json=? WHERE derived_id=?",
                           ('{"forged":true}', task["derived_id"]))
    with pytest.raises(LiveGateError, match="DERIVED_RECORD_CORRUPT"):
        store.claim_render(billing_unknown=False, worker_id="local", now=100)
