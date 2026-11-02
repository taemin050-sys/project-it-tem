import pytest
from demo_staging.live.queue import LiveQueue
from demo_staging.live.contracts import LiveGateError

def args():
    return dict(actor="alice",job_id="a"*32,stage="analysis",context_sha="b"*64)

def test_queue_idempotency_worker_single_claim_and_finish(tmp_path):
    q=LiveQueue(tmp_path/"tasks.sqlite")
    t,created=q.enqueue(**args())
    assert created and t["state"]=="QUEUED"
    duplicate,created=q.enqueue(**args())
    assert not created and duplicate["id"]==t["id"]
    claimed=q.claim()
    assert claimed["id"]==t["id"] and claimed["state"]=="RUNNING"
    assert q.claim() is None
    q.complete(t["id"],"c"*64)
    assert q.read(t["id"])["state"]=="SUCCEEDED"
    assert q.claim() is None

def test_worker_restart_unknown_never_claim_again(tmp_path):
    f=tmp_path/"tasks.sqlite";q=LiveQueue(f)
    t,_=q.enqueue(**args())
    assert q.claim()["id"]==t["id"]
    fresh=LiveQueue(f)
    assert fresh.reconcile_restart()==1
    assert fresh.claim() is None
    old,created=fresh.enqueue(**args())
    assert not created and old["state"]=="BILLING_UNKNOWN"
    with pytest.raises(LiveGateError):
        fresh.complete(t["id"],"d"*64)

def test_queue_separate_offline_mode_unclaimable_live(tmp_path):
    q=LiveQueue(tmp_path/"tasks.sqlite")
    t,_=q.enqueue(**dict(args(),mode="OFFLINE_FIXTURE"))
    assert q.claim(worker_mode="LIVE") is None
    assert q.claim(worker_mode="OFFLINE_FIXTURE")["id"]==t["id"]
    q.interrupt(t["id"],"OFFLINE_FIXTURE_FAILURE")
    assert q.read(t["id"])["state"]=="BILLING_UNKNOWN"
