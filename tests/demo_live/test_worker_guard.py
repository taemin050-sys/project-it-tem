import pytest
from demo_staging.live.worker import run_once,policy_from_env
from demo_staging.live.queue import LiveQueue
from demo_staging.live_safety import LiveNotAuthorized

def test_worker_denied_by_default_and_does_not_consume_queue(tmp_path,monkeypatch):
    for key in ("IT_TEM_LIVE_ENABLED","IT_TEM_LIVE_EXECUTION_APPROVED",
                "IT_TEM_PROVIDER_READINESS_CONFIRMED","OPENAI_API_KEY"):
        monkeypatch.delenv(key,raising=False)
    task,_=LiveQueue(tmp_path/"live"/"queue.sqlite").enqueue(
        actor="alice",job_id="a"*32,stage="analysis",context_sha="b"*64)
    with pytest.raises(LiveNotAuthorized):
        run_once(tmp_path)
    assert LiveQueue(tmp_path/"live"/"queue.sqlite").read(task["id"])["state"]=="QUEUED"

def test_key_alone_never_grants_billing_permission(tmp_path,monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY","TEST_ONLY_NO_REAL_CALL")
    monkeypatch.setenv("IT_TEM_LIVE_ENABLED","YES")
    monkeypatch.delenv("IT_TEM_LIVE_EXECUTION_APPROVED",raising=False)
    with pytest.raises(LiveNotAuthorized):
        policy_from_env(tmp_path)

def test_owner_client_never_imported_when_worker_denied(tmp_path,monkeypatch):
    import sys
    monkeypatch.setenv("OPENAI_API_KEY","TEST_ONLY_NO_REAL_CALL")
    monkeypatch.delenv("IT_TEM_LIVE_ENABLED",raising=False)
    with pytest.raises(LiveNotAuthorized):
        run_once(tmp_path)
    assert "src.text_generation.llm_client" not in sys.modules

def test_second_worker_must_not_reconcile_active_attempt(tmp_path,monkeypatch):
    from demo_staging.live.worker import exclusive_live_worker
    from demo_staging.live.queue import LiveQueue
    from demo_staging.live_safety import LiveNotAuthorized
    flags={
        "IT_TEM_LIVE_ENABLED":"YES",
        "IT_TEM_LIVE_EXECUTION_APPROVED":"YES",
        "IT_TEM_PROVIDER_READINESS_CONFIRMED":"YES",
        "OPENAI_API_KEY":"FAKE_TEST_KEY_NOT_USED",
        "IT_TEM_LIVE_BUDGET_USD":"3",
        "IT_TEM_TEXT_RESERVATION_USD":"0.5",
        "IT_TEM_IMAGE_RESERVATION_USD":"1",
        "IT_TEM_LIVE_REQUEST_LIMIT":"3",
        "IT_TEM_LIVE_APPROVED_ACTORS":"alice",
        "IT_TEM_LIVE_COST_POLICY":"MONITOR_ONLY",
    }
    for key,value in flags.items():monkeypatch.setenv(key,value)
    queue=LiveQueue(tmp_path/"live"/"queue.sqlite")
    task,_=queue.enqueue(actor="alice",job_id="a"*32,stage="analysis",
                         context_sha="b"*64)
    claimed=queue.claim()
    assert claimed["state"]=="RUNNING"
    with exclusive_live_worker(tmp_path):
        with pytest.raises(LiveNotAuthorized,match="LIVE_WORKER_ALREADY_RUNNING"):
            run_once(tmp_path)
        # Crucial: another worker does NOT mark a running request UNKNOWN.
        assert queue.read(task["id"])["state"]=="RUNNING"
    assert queue.reconcile_restart()==1
    assert queue.read(task["id"])["state"]=="BILLING_UNKNOWN"
