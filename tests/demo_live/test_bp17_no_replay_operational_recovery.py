"""BP17 operational replay boundary. Mock provider only, NO billable calls."""
from uuid import uuid4
import hashlib
import pytest
from demo_staging.live.queue import LiveQueue
from demo_staging.live.contracts import LiveGateError
from scripts.bp13_image_recovery_audit_readonly import inspect
from tests.demo_live.test_bp13_retry_failure_injection import reject_ready,request_digest

def test_simulated_worker_process_restart_keeps_image_attempt_blocked(tmp_path):
    flow,jid,owner,first=reject_ready(tmp_path)
    copy=flow.state.get("alice",jid)
    before={k:copy[k] for k in ("approval_sha","copy_sha","review_sha","generation")}
    prior_image=flow.image_path(jid)
    assert hashlib.sha256(prior_image.read_bytes()).hexdigest()==first.sha256
    retry=flow.begin_image_retry("alice",jid,first.sha256,uuid4().hex)
    current=flow.state.get("alice",jid)
    ctx=request_digest(current,retry)
    queue=LiveQueue(flow.root/"queue.sqlite")
    task,created=queue.enqueue(actor="alice",job_id=jid,stage="image",
                               context_sha=ctx)
    assert created and task["state"]=="QUEUED"
    assert queue.claim()["id"]==task["id"]
    # Simulated unexpected worker death; new queue instance is the restarted process.
    restarted=LiveQueue(flow.root/"queue.sqlite")
    assert restarted.reconcile_restart()==1
    assert restarted.read(task["id"])["state"]=="BILLING_UNKNOWN"
    assert restarted.claim() is None
    old,created=restarted.enqueue(actor="alice",job_id=jid,stage="image",
                                  context_sha=ctx)
    assert not created and old["id"]==task["id"]
    with pytest.raises(LiveGateError,match="IMAGE_RETRY_OUTSTANDING_OR_UNKNOWN"):
        restarted.assert_image_retry_safe("alice",jid)
    with pytest.raises(LiveGateError,match="IMAGE_RETRY_STALE_REJECTION"):
        flow.begin_image_retry("alice",jid,first.sha256,uuid4().hex)
    report=inspect(flow.root,jid)
    assert report["verdict"]=="HOLD_MANUAL_PROVIDER_AND_ARTIFACT_RECONCILIATION"
    assert report["automatic_replay_permitted"] is False
    assert report["queue_image_tasks"][-1]["state"]=="BILLING_UNKNOWN"
    assert flow.state.current_image_attempt("alice",jid)["attempt_id"]==retry["attempt_id"]
    after=flow.state.get("alice",jid)
    assert {k:after[k] for k in before}==before
    assert hashlib.sha256(prior_image.read_bytes()).hexdigest()==first.sha256
    assert owner.calls==["analyze","research","copy","prompt"]

def test_unenqueued_attempt_is_orphan_not_new_paid_generation(tmp_path):
    flow,jid,owner,first=reject_ready(tmp_path)
    request_key=uuid4().hex
    attempt=flow.begin_image_retry("alice",jid,first.sha256,request_key)
    before=flow.state.get("alice",jid)
    report=inspect(flow.root,jid)
    assert report["verdict"]=="ORPHAN_ATTEMPT_REQUIRES_MANUAL_TASK_RECONCILIATION"
    assert report["automatic_replay_permitted"] is False
    assert flow.begin_image_retry("alice",jid,first.sha256,request_key)==attempt
    with pytest.raises(LiveGateError,match="IMAGE_RETRY_STALE_REJECTION"):
        flow.begin_image_retry("alice",jid,first.sha256,uuid4().hex)
    after=flow.state.get("alice",jid)
    assert after["input_sha"]==before["input_sha"]
    assert after["approval_sha"]==before["approval_sha"]
    assert after["copy_sha"]==before["copy_sha"]
    assert after["review_sha"]==before["review_sha"]
    assert after["generation"]==before["generation"]
    assert owner.calls==["analyze","research","copy","prompt"]
