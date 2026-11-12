"""Isolated database-only tests. No API credentials, network or model requests."""
from demo_staging.live.worker import quarantined_uncertain_jobs,_run_locked
from tests.demo_live.test_a2_worker_authority_billing import prepare
from demo_staging.live.queue import LiveQueue

def test_broken_job_quarantined_without_replay(tmp_path,monkeypatch):
    app,jid,flow,queue=prepare(tmp_path,monkeypatch)
    monkeypatch.setenv("IT_TEM_R6_ISOLATE_UNCERTAIN_JOBS","YES")
    task,_=queue.enqueue(actor="alice",job_id=jid,stage="analysis",
                         context_sha=flow.state.get("alice",jid)["input_sha"])
    queue.claim("LIVE")
    queue.interrupt(task["id"],"PROVIDER_RESULT_UNKNOWN")
    item=flow.cost.reserve(actor="alice",role="live_operator",job_id=jid,
        stage="research",payload={"test":"uncertain"},estimated_usd=0,
        pm_authorized=True)
    flow.cost.dispatch_intent(item["id"])
    flow.cost.mark_billing_unknown(item["id"])
    assert quarantined_uncertain_jobs(queue,flow)=={jid}
    assert _run_locked(tmp_path/"runtime",flow)=="NO_LIVE_TASK"
    assert queue.read(task["id"])["state"]=="BILLING_UNKNOWN"
    assert flow.cost.inspect(item["id"])["status"]=="BILLING_UNKNOWN"

def test_unpaired_uncertain_queue_keeps_worker_closed(tmp_path,monkeypatch):
    app,jid,flow,queue=prepare(tmp_path,monkeypatch)
    monkeypatch.setenv("IT_TEM_R6_ISOLATE_UNCERTAIN_JOBS","YES")
    task,_=queue.enqueue(actor="alice",job_id=jid,stage="analysis",
                         context_sha=flow.state.get("alice",jid)["input_sha"])
    queue.claim("LIVE")
    queue.interrupt(task["id"],"UNKNOWN")
    assert quarantined_uncertain_jobs(queue,flow) is None
    assert _run_locked(tmp_path/"runtime",flow)=="LIVE_WORKER_BILLING_HOLD"

def test_unrelated_user_job_can_finish_without_touching_unknown(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from tests.demo_live.test_http_gateway import login,photo
    from tests.demo_live.test_live_contracts import sample_input
    app,jid,flow,queue=prepare(tmp_path,monkeypatch)
    monkeypatch.setenv("IT_TEM_R6_ISOLATE_UNCERTAIN_JOBS","YES")
    old,_=queue.enqueue(actor="alice",job_id=jid,stage="analysis",
                        context_sha=flow.state.get("alice",jid)["input_sha"])
    queue.claim("LIVE")
    queue.interrupt(old["id"],"PROVIDER_RESULT_UNKNOWN")
    item=flow.cost.reserve(actor="alice",role="live_operator",job_id=jid,
        stage="research",payload={"test":"uncertain"},estimated_usd=0,
        pm_authorized=True)
    flow.cost.dispatch_intent(item["id"])
    flow.cost.mark_billing_unknown(item["id"])
    with TestClient(app) as c:
        login(c,"one-off-alice-evaluation-invite-secret-2026")
        r=c.post("/api/v1/jobs",files=[
            ("product_images",("one.png",photo((10,20,30)),"image/png")),
            ("product_images",("two.png",photo((40,50,60)),"image/png"))
        ],headers={"Origin":"http://testserver"})
        assert r.status_code==201
        other=r.json()["job_id"]
        r=c.post("/demo/api/live/jobs/"+other+"/input",json=sample_input(),
                 headers={"Origin":"http://testserver"})
        assert r.status_code==200
    task,_=queue.enqueue(actor="alice",job_id=other,stage="analysis",
                         context_sha=flow.state.get("alice",other)["input_sha"])
    seen=[]
    def offline_fake(actor,job_id,**kwargs):
        seen.append(job_id)
        return {"copy_sha":"f"*64}
    monkeypatch.setattr(flow,"text",offline_fake)
    assert _run_locked(tmp_path/"runtime",flow)=="LIVE_STAGE_COMMITTED"
    assert seen==[other]
    assert queue.read(task["id"])["state"]=="SUCCEEDED"
    assert queue.read(old["id"])["state"]=="BILLING_UNKNOWN"
    assert flow.cost.inspect(item["id"])["status"]=="BILLING_UNKNOWN"
