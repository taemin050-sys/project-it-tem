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
