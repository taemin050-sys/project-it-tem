"""A2 P0-01/02: real actor ledger + queue + provider cost ledger, no network."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from demo_staging.live.worker import (_run_locked,authorize_worker_item,
    reconcile_worker_ledgers,exclusive_live_worker)
from demo_staging.live.queue import LiveQueue
from demo_staging.live_safety import LiveNotAuthorized,AttemptLedger
from demo_staging.live.contracts import LiveGateError
from tests.demo_live.test_http_gateway import setup,login,photo
from tests.demo_live.test_live_contracts import sample_input


ORIGIN={"Origin":"http://testserver"}


def prepare(tmp_path,monkeypatch):
    for key in ("IT_TEM_LIVE_ENABLED","IT_TEM_LIVE_WEB_QUEUE_ENABLED",
                "IT_TEM_LIVE_EXECUTION_APPROVED","IT_TEM_PROVIDER_READINESS_CONFIRMED"):
        monkeypatch.setenv(key,"YES")
    monkeypatch.setenv("IT_TEM_LIVE_COST_POLICY","MONITOR_ONLY")
    monkeypatch.setenv("IT_TEM_LIVE_APPROVED_ACTORS","alice")
    monkeypatch.delenv("OPENAI_API_KEY",raising=False)
    app,codes=setup(tmp_path)
    with TestClient(app) as c:
        login(c,codes["alice"])
        created=c.post("/api/v1/jobs",files=[
            ("product_images",("a.png",photo((120,130,140)),"image/png")),
            ("product_images",("b.png",photo((150,160,170)),"image/png")),
        ],headers=ORIGIN)
        assert created.status_code==201,created.text
        jid=created.json()["job_id"]
        initial=c.post("/demo/api/live/jobs/"+jid+"/input",
                       json=sample_input(),headers=ORIGIN)
        assert initial.status_code==200,initial.text
    queue=app.state.live_queue
    flow=app.state.live_pipeline
    assert flow.approved_actors==frozenset({"alice"})
    return app,jid,flow,queue


@pytest.mark.parametrize("reason",("revoked_after_queue","foreign_actor","stale_allowlist",
                                  "disabled_execution","invalid_stage","cancelled_job"))
def test_revocation_ownership_stage_cancel_block_before_provider(
    tmp_path,monkeypatch,reason,
):
    app,jid,flow,queue=prepare(tmp_path,monkeypatch)
    actor="bob" if reason=="foreign_actor" else "alice"
    item,_=queue.enqueue(actor=actor,job_id=jid,
                         stage="image_prompt" if reason=="invalid_stage" else "analysis",
                         context_sha=(flow.state.get("alice",jid)["input_sha"]))
    if reason=="revoked_after_queue":
        monkeypatch.setenv("IT_TEM_LIVE_APPROVED_ACTORS","bob")
    if reason=="stale_allowlist":
        flow.approved_actors=frozenset({"bob"})
    if reason=="disabled_execution":
        monkeypatch.setenv("IT_TEM_LIVE_EXECUTION_APPROVED","NO")
    if reason=="cancelled_job":
        file=flow.jobs.root/jid/"job.json"
        record=json.loads(file.read_text())
        record["status"]="CANCELLED"
        file.write_text(json.dumps(record))
    calls=[]
    monkeypatch.setattr(flow,"text",lambda *_args,**_kwargs:calls.append("PROVIDER"))
    assert _run_locked(tmp_path/"runtime",flow)=="LIVE_STAGE_HELD_FOR_RECONCILIATION"
    assert calls==[]
    task=queue.read(item["id"])
    assert task["state"]=="BILLING_UNKNOWN"
    with flow.cost.connect() as db:
        assert db.execute("SELECT count(*) FROM attempts").fetchone()[0]==0


def test_live_actor_and_owned_input_allow_exactly_one_claim(tmp_path,monkeypatch):
    app,jid,flow,queue=prepare(tmp_path,monkeypatch)
    job=flow.state.get("alice",jid)
    item,_=queue.enqueue(actor="alice",job_id=jid,stage="analysis",
                         context_sha=job["input_sha"])
    calls=[]
    def fake_text(actor,jid,*,offline,text_model,vision_model):
        assert actor=="alice" and offline is False
        calls.append((actor,jid))
        return {"copy_sha":"f"*64}
    monkeypatch.setattr(flow,"text",fake_text)
    assert _run_locked(tmp_path/"runtime",flow)=="LIVE_STAGE_COMMITTED"
    assert calls==[("alice",jid)]
    assert queue.read(item["id"])["state"]=="SUCCEEDED"
    assert _run_locked(tmp_path/"runtime",flow)=="NO_LIVE_TASK"
    with flow.cost.connect() as db:
        assert db.execute("SELECT count(*) FROM attempts").fetchone()[0]==0


def test_revoke_immediately_at_billable_provider_boundary(tmp_path,monkeypatch):
    app,jid,flow,queue=prepare(tmp_path,monkeypatch)
    job=flow.state.get("alice",jid)
    item,_=queue.enqueue(actor="alice",job_id=jid,stage="analysis",
                         context_sha=job["input_sha"])
    flow._worker_claim={**item,"mode":"LIVE"}
    executed=[]
    monkeypatch.setenv("IT_TEM_LIVE_APPROVED_ACTORS","bob")
    try:
        with pytest.raises(LiveGateError,match="WORKER_ACTOR_REVOKED"):
            flow._guarded("alice",jid,"vision",{"image_sha":"x"},lambda:executed.append(1))
    finally:
        del flow._worker_claim
    assert executed==[]
    with flow.cost.connect() as db:
        assert db.execute("SELECT count(*) FROM attempts").fetchone()[0]==0


def test_worker_restart_reconciles_both_sqlites_no_replay_and_idempotent(
    tmp_path,monkeypatch,
):
    app,jid,flow,queue=prepare(tmp_path,monkeypatch)
    job=flow.state.get("alice",jid)
    task,_=queue.enqueue(actor="alice",job_id=jid,stage="analysis",
                         context_sha=job["input_sha"])
    claimed=queue.claim("LIVE")
    assert claimed["state"]=="RUNNING"
    attempt=flow.cost.reserve(actor="alice",role="live_operator",
        job_id=jid,stage="vision",payload={"crash":"after-dispatch"},
        estimated_usd=0,pm_authorized=True)
    flow.cost.dispatch_intent(attempt["id"])
    with flow.cost.connect() as c:
        assert c.execute("SELECT status FROM attempts").fetchone()[0]=="DISPATCHED"
    assert reconcile_worker_ledgers(queue,flow) is True
    assert queue.read(task["id"])["state"]=="BILLING_UNKNOWN"
    first=flow.cost.inspect(attempt["id"])
    assert first["status"]=="BILLING_UNKNOWN" and first["billing_unknown"]==1
    # Same ambiguous WorkItem remains blocked even after restart/repeated scans.
    for _ in range(3):
        assert reconcile_worker_ledgers(queue,flow) is True
        assert _run_locked(tmp_path/"runtime",flow)=="LIVE_WORKER_BILLING_HOLD"
    with flow.cost.connect() as c:
        assert c.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]==1
    with pytest.raises(LiveNotAuthorized,match="ATTEMPT_EXISTS"):
        flow._guarded("alice",jid,"vision",{"crash":"after-dispatch"},
                      lambda:pytest.fail("No second paid invocation permitted"))


@pytest.mark.parametrize("interruption",("reserved","dispatched","usage-recorded"))
def test_crash_stages_remain_conservatively_non_replayable(
    tmp_path,monkeypatch,interruption,
):
    app,jid,flow,queue=prepare(tmp_path,monkeypatch)
    task,_=queue.enqueue(actor="alice",job_id=jid,stage="analysis",
        context_sha=flow.state.get("alice",jid)["input_sha"])
    queue.claim("LIVE")
    attempt=flow.cost.reserve(actor="alice",role="live_operator",
        job_id=jid,stage="vision",payload={"case":interruption},
        estimated_usd=0,pm_authorized=True)
    if interruption!="reserved":
        flow.cost.dispatch_intent(attempt["id"])
    if interruption=="usage-recorded":
        receipt={"provider_response_id":"resp-fake-001","billing_status":"UNPRICED_RESERVATION_HELD",
                 "provider":"openai","model":"test",
                 "usage":{"input_tokens":1,"output_tokens":1,"total_tokens":2}}
        flow.cost.confirm_usage_unpriced(attempt["id"],receipt)
    before=flow.cost.inspect(attempt["id"])
    assert reconcile_worker_ledgers(queue,flow) is True
    after=flow.cost.inspect(attempt["id"])
    assert queue.read(task["id"])["state"]=="BILLING_UNKNOWN"
    if interruption=="dispatched":
        assert after["status"]=="BILLING_UNKNOWN"
    else:
        assert after["status"]==before["status"]
        assert after["receipt"]==before["receipt"]
    assert _run_locked(tmp_path/"runtime",flow)=="LIVE_WORKER_BILLING_HOLD"
    with flow.cost.connect() as c:
        assert c.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]==1


def test_host_singleflight_prevents_second_worker_reconciliation(tmp_path,monkeypatch):
    app,jid,flow,queue=prepare(tmp_path,monkeypatch)
    with exclusive_live_worker(tmp_path/"runtime"):
        with pytest.raises(LiveNotAuthorized,match="LIVE_WORKER_ALREADY_RUNNING"):
            with exclusive_live_worker(tmp_path/"runtime"):
                pass


def test_owner_image_attempt_submitting_blocks_all_new_paid_worker_claims(
    tmp_path,monkeypatch,
):
    from uuid import uuid4
    from src.image_generation.provider_attempts import ProviderAttemptStore
    app,jid,flow,queue=prepare(tmp_path,monkeypatch)
    provider_root=flow.root/"owner_image"
    attempts=ProviderAttemptStore(provider_root/"image_attempts.sqlite")
    # No provider transport: begin() writes one durable 'submitting' slot.
    attempt_id=attempts.begin(uuid4(),uuid4(),"e"*64,
                              budget_limit_usd="0",reservation_usd="0",
                              monitoring_only=True)
    assert attempt_id
    assert reconcile_worker_ledgers(queue,flow) is True
    assert _run_locked(tmp_path/"runtime",flow)=="LIVE_WORKER_BILLING_HOLD"
    with flow.cost.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]==0
    with attempts._connection() as db:
        assert db.execute("SELECT state FROM provider_attempts").fetchone()[0]=="submitting"


def test_cross_ledger_read_error_fails_closed(tmp_path,monkeypatch):
    app,jid,flow,queue=prepare(tmp_path,monkeypatch)
    target=flow.root/"owner_image"
    target.mkdir()
    # Present corrupt/unrecognized Provider DB. A new paid call must not
    # proceed based on a false claim that the ledger is simply empty.
    (target/"image_attempts.sqlite").write_bytes(b"not-an-SQLite-DB")
    assert reconcile_worker_ledgers(queue,flow) is True
    assert _run_locked(tmp_path/"runtime",flow)=="LIVE_WORKER_BILLING_HOLD"


def test_queued_prompt_rejects_new_policy_epoch_before_provider(
    tmp_path,monkeypatch,
):
    from demo_staging.live.contracts import digest
    from tests.demo_live.test_live_contracts import safe_copy
    app,jid,flow,queue=prepare(tmp_path,monkeypatch)
    analysis,research,copy,_=safe_copy()
    staged=flow.state.store_text("alice",jid,analysis,research,copy,mode="LIVE")
    approved=flow.state.approve_copy("alice",jid,staged["generation"],staged["review_sha"])
    frozen=digest(flow.state.prompt_context("alice",jid))
    task,_=queue.enqueue(actor="alice",job_id=jid,stage="image_prompt",context_sha=frozen)
    monkeypatch.setenv("IT_TEM_REVIEW_POLICY_EPOCH","different-policy")
    called=[]
    monkeypatch.setattr(flow,"prompt",lambda *_args,**_kwargs:called.append(True))
    assert _run_locked(tmp_path/"runtime",flow)=="LIVE_STAGE_HELD_FOR_RECONCILIATION"
    assert called==[]
    assert queue.read(task["id"])["error_code"]=="PROMPT_APPROVAL_POLICY_EPOCH_CHANGED"
    with flow.cost.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]==0
