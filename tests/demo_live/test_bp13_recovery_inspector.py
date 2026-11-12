"""Operator read-only inspector must not mistake archived rejected bytes for new results."""
from uuid import uuid4
from scripts.bp13_image_recovery_audit_readonly import inspect
from demo_staging.live.queue import LiveQueue
from demo_staging.live.contracts import digest
from tests.demo_live.test_bp13_single_image_retry import ready

def test_readonly_classifies_orphan_and_uncertain_without_replay(tmp_path):
    flow,jid,owner,first=ready(tmp_path)
    flow.state.reject_image("alice",jid,first.sha256)
    retry=flow.begin_image_retry("alice",jid,first.sha256,uuid4().hex)
    root=flow.root
    before=inspect(root,jid)
    assert before["read_only"] and before["automatic_replay_permitted"] is False
    assert before["verdict"]=="ORPHAN_ATTEMPT_REQUIRES_MANUAL_TASK_RECONCILIATION"
    q=LiveQueue(root/"queue.sqlite")
    job=flow.state.get("alice",jid)
    request=digest({"approval_sha":job["approval_sha"],"attempt_id":retry["attempt_id"]})
    row,new=q.enqueue(actor="alice",job_id=jid,stage="image",context_sha=request)
    assert new
    during=inspect(root,jid)
    assert during["verdict"]=="HOLD_INFLIGHT_NO_REQUEUE"
    q.claim()
    q.interrupt(row["id"],"PROVIDER_SUBMISSION_UNCERTAIN")
    after=inspect(root,jid)
    assert after["verdict"]=="HOLD_MANUAL_PROVIDER_AND_ARTIFACT_RECONCILIATION"
    assert after["queue_image_tasks"][-1]["state"]=="BILLING_UNKNOWN"
    assert flow.state.get("alice",jid)["state"]=="PROMPT_READY"
    assert owner.calls==["analyze","research","copy","prompt"]
