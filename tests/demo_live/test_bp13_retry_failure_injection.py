"""Isolated, no-provider crash/replay tests for BP13 rejected image recovery."""
import hashlib,json,concurrent.futures
from uuid import uuid4
import pytest
from demo_staging.live.contracts import LiveGateError,digest
from demo_staging.live.queue import LiveQueue
from src.image_generation.backend_adapter import BackendGeneratedImage
from src.image_generation.size_selection import resolve_size_choice
from tests.demo_live.test_bp13_single_image_retry import ready
from tests.demo_live.test_pipeline import FakeOwner,png,prepare_service
from tests.demo_live.test_live_contracts import sample_input


def reject_ready(tmp_path):
    flow,jid,owner,first=ready(tmp_path)
    flow.state.reject_image("alice",jid,first.sha256)
    return flow,jid,owner,first

def request_digest(job,attempt):
    return digest({"approval_sha":job["approval_sha"],"attempt_id":attempt["attempt_id"]})

def retry_fixture(flow,jid):
    job=flow.state.get("alice",jid)
    req=flow.image_input("alice",jid)
    native=resolve_size_choice(json.loads(job["input_json"])["image_size"])[1].native
    data=png((111,140,200),size=native)
    return BackendGeneratedImage(image_bytes=data,mime_type="image/png",
         width=native[0],height=native[1],sha256=hashlib.sha256(data).hexdigest(),
         job_id=jid,copy_revision=req.copy_revision,copy_hash=req.copy_hash,
         mock=True,receipt={"mode":"OFFLINE_FIXTURE","provider_calls":0})

def test_crash_after_state_transition_before_queue_enqueue_has_no_new_attempt(tmp_path):
    flow,jid,owner,first=reject_ready(tmp_path)
    key=uuid4().hex
    first_retry=flow.begin_image_retry("alice",jid,first.sha256,key)
    assert flow.state.get("alice",jid)["state"]=="PROMPT_READY"
    queue=LiveQueue(tmp_path/"queue.sqlite")
    assert queue.claim() is None
    # Same key is an idempotent recovery of the existing attempt, not a billable replay.
    assert flow.begin_image_retry("alice",jid,first.sha256,key)==first_retry
    with pytest.raises(LiveGateError,match="IMAGE_RETRY_STALE_REJECTION"):
        flow.begin_image_retry("alice",jid,first.sha256,uuid4().hex)
    current=flow.state.get("alice",jid)
    ctx=request_digest(current,first_retry)
    task,created=queue.enqueue(actor="alice",job_id=jid,stage="image",context_sha=ctx)
    assert created and task["state"]=="QUEUED"
    again,created=queue.enqueue(actor="alice",job_id=jid,stage="image",context_sha=ctx)
    assert not created and again["id"]==task["id"]
    with pytest.raises(LiveGateError,match="IMAGE_RETRY_OUTSTANDING_OR_UNKNOWN"):
        queue.assert_image_retry_safe("alice",jid)
    assert owner.calls==["analyze","research","copy","prompt"]

def test_parallel_user_retry_requests_single_winner(tmp_path):
    flow,jid,owner,first=reject_ready(tmp_path)
    keys=[uuid4().hex for _ in range(8)]
    def attempt(key):
        try:return "OK",flow.begin_image_retry("alice",jid,first.sha256,key)
        except LiveGateError as e:return e.code,None
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        got=list(executor.map(attempt,keys))
    winners=[row for row in got if row[0]=="OK"]
    assert len(winners)==1,got
    attempts=flow.state.current_image_attempt("alice",jid)
    assert attempts["attempt_version"]==2
    assert attempts["attempt_id"]==winners[0][1]["attempt_id"]
    assert flow.state.get("alice",jid)["state"]=="PROMPT_READY"
    assert owner.calls==["analyze","research","copy","prompt"]

def test_provider_succeeded_but_candidate_artifact_save_fails_safe(tmp_path,monkeypatch):
    flow,jid,owner,first=reject_ready(tmp_path)
    key=uuid4().hex
    retry=flow.begin_image_retry("alice",jid,first.sha256,key)
    queue=LiveQueue(tmp_path/"queue.sqlite")
    job=flow.state.get("alice",jid)
    task,_=queue.enqueue(actor="alice",job_id=jid,stage="image",
                         context_sha=request_digest(job,retry))
    assert queue.claim()["id"]==task["id"]
    candidate=retry_fixture(flow,jid)
    import demo_staging.live.pipeline as pipeline
    def no_disk(*_args,**_kwargs):raise OSError("INJECTED_STORAGE_FAILURE")
    monkeypatch.setattr(pipeline,"atomic_write",no_disk)
    with pytest.raises(OSError,match="INJECTED_STORAGE_FAILURE"):
        flow.accept_image_result("alice",jid,candidate,offline=True)
    queue.interrupt(task["id"],"ARTIFACT_SAVE_UNCERTAIN")
    assert queue.read(task["id"])["state"]=="BILLING_UNKNOWN"
    with pytest.raises(LiveGateError,match="IMAGE_RETRY_OUTSTANDING_OR_UNKNOWN"):
        queue.assert_image_retry_safe("alice",jid)
    assert flow.state.get("alice",jid)["state"]=="PROMPT_READY"
    assert flow.state.current_image_attempt("alice",jid)["state"]=="REQUESTED"
    assert owner.calls==["analyze","research","copy","prompt"]

def test_freeform_receipt_saved_but_db_commit_fails_no_auto_replay(tmp_path,monkeypatch):
    flow,jid=prepare_service(tmp_path)
    flow.prepare("alice",jid,{**sample_input(),"image_size":"4:5",
                              "generation_mode":"freeform"},template_profile="A")
    owner=FakeOwner();text=flow.text("alice",jid,owner,offline=True)
    flow.state.approve_copy("alice",jid,text["generation"],text["review_sha"])
    flow.prompt("alice",jid,owner,offline=True)
    req=flow.image_input("alice",jid)
    native=resolve_size_choice("4:5")[1].native
    raw=png((171,130,160),size=native)
    def candidate(raw):
        return BackendGeneratedImage(image_bytes=raw,mime_type="image/png",
         width=native[0],height=native[1],sha256=hashlib.sha256(raw).hexdigest(),
         job_id=jid,copy_revision=req.copy_revision,copy_hash=req.copy_hash,
         mock=True,receipt={"state":"succeeded","generation_mode":"freeform",
                            "mode":"OFFLINE_FIXTURE","provider_calls":0})
    initial=candidate(raw)
    flow.accept_image_result("alice",jid,initial,offline=True)
    flow.state.reject_image("alice",jid,initial.sha256)
    retry=flow.begin_image_retry("alice",jid,initial.sha256,uuid4().hex)
    job=flow.state.get("alice",jid)
    queue=LiveQueue(tmp_path/"queue.sqlite")
    task,_=queue.enqueue(actor="alice",job_id=jid,stage="image",
                         context_sha=request_digest(job,retry))
    assert queue.claim()["id"]==task["id"]
    new=png((110,190,145),size=native)
    def fail_db(*_a,**_k):raise LiveGateError("SIMULATED_DB_COMMIT_FAILURE")
    monkeypatch.setattr(flow.state,"store_image_candidate",fail_db)
    with pytest.raises(LiveGateError,match="SIMULATED_DB_COMMIT_FAILURE"):
        flow.accept_image_result("alice",jid,candidate(new),offline=True)
    # Both candidate bytes and receipt may exist, but SQLite remains old.
    assert hashlib.sha256(flow.image_path(jid).read_bytes()).hexdigest()==hashlib.sha256(new).hexdigest()
    assert (flow.root/"outputs"/jid/"owner_candidate_receipt.json").exists()
    assert flow.state.current_image_attempt("alice",jid)["state"]=="REQUESTED"
    assert flow.state.get("alice",jid)["state"]=="PROMPT_READY"
    queue.interrupt(task["id"],"CANDIDATE_DB_UNKNOWN")
    assert queue.read(task["id"])["state"]=="BILLING_UNKNOWN"
    with pytest.raises(LiveGateError,match="IMAGE_RETRY_OUTSTANDING_OR_UNKNOWN"):
        queue.assert_image_retry_safe("alice",jid)
    assert owner.calls==["analyze","research","copy","prompt"]
