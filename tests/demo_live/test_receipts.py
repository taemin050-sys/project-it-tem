from pathlib import Path
import json

import pytest

from demo_staging.live.provider_receipts import collect_receipts,record_owner_response
from demo_staging.live.pipeline import LivePipeline
from demo_staging.live_safety import LiveNotAuthorized
from demo_staging.live.contracts import LiveGateError
from src.serving.job_store import JobStore

def fake_response():
    return {"status":"completed","id":"resp_fake_offline_only",
            "model":"gpt-6-luna",
            "usage":{"input_tokens":15,"output_tokens":29,"total_tokens":44}}

def test_receipt_capture_exact_metadata_not_payload():
    assert "src.text_generation.llm_client" not in __import__("sys").modules
    with collect_receipts() as sink:
        record_owner_response(dict(fake_response(),output=[{"text":"private product claim"}]))
        assert len(sink.events)==1
        assert "private product claim" not in json.dumps(sink.events)
        assert sink.events[0]["usage"]["total_tokens"]==44
        assert sink.events[0]["billing_status"]=="UNPRICED_RESERVATION_HELD"
    with collect_receipts() as sink:
        record_owner_response(dict(fake_response(),status="incomplete"))
        record_owner_response({"status":"completed","id":"resp_fake","model":"gpt-6-luna"})
        assert sink.events==[]

def test_pipeline_provider_usage_receipt_held_with_no_dollar_fabrication(tmp_path):
    p=LivePipeline(tmp_path/"l",JobStore(tmp_path/"jobs"),live_enabled=True,
        pm_authorized=True,budget_limit_usd=1,text_reservation_usd=.3,request_limit=3)
    def fake():
        record_owner_response(fake_response())
        return {"confirmed":"schema-only"}
    result=p._guarded("alice","a"*32,"vision",{"img":"s"*64},fake)
    assert result=={"confirmed":"schema-only"}
    with p.cost.connect() as db:
        row=db.execute("SELECT * FROM attempts").fetchone()
    assert row["status"]=="SUCCEEDED_USAGE_UNPRICED"
    assert row["cost_microusd"] is None
    assert row["reserved_microusd"]==300000
    assert row["billing_unknown"]==0
    assert json.loads(row["receipt"])["usage"]["input_tokens"]==15
    with pytest.raises(LiveNotAuthorized,match="ATTEMPT_EXISTS"):
        p._guarded("alice","a"*32,"vision",{"img":"s"*64},fake)

def test_missing_usage_blocks_followup_never_retries(tmp_path):
    p=LivePipeline(tmp_path/"l",JobStore(tmp_path/"jobs"),live_enabled=True,
        pm_authorized=True,budget_limit_usd=1,text_reservation_usd=.3,request_limit=2)
    def no_usage():
        record_owner_response({"status":"completed","id":"resp_foo","model":"gpt-6-luna"})
        return object()
    with pytest.raises(LiveGateError,match="PROVIDER_BILLING_RECONCILIATION_REQUIRED"):
        p._guarded("alice","a"*32,"vision",{"img":"x"*64},no_usage)
    with p.cost.connect() as db:
        row=db.execute("SELECT * FROM attempts").fetchone()
    assert row["status"]=="BILLING_UNKNOWN" and row["billing_unknown"]==1
    with pytest.raises(LiveNotAuthorized,match="ATTEMPT_EXISTS"):
        p._guarded("alice","a"*32,"vision",{"img":"x"*64},no_usage)

def test_actual_owner_llm_code_exports_usage_hook_without_network(tmp_path):
    """Run in isolated subprocess to avoid influencing older S4 no-import assertions."""
    import subprocess
    import sys
    import os
    code=r'''
import socket
import types
import sys
from types import SimpleNamespace
# Import the actual owner source with an isolated SDK import stub. No real
# key, API client or socket can possibly be reached by this subprocess.
stub=types.ModuleType("openai")
class StubOpenAIError(Exception):pass
stub.OpenAIError=StubOpenAIError
stub.OpenAI=lambda **kwargs:SimpleNamespace()
sys.modules["openai"]=stub
from src.text_generation import llm_client
from src.text_generation.schemas import ProductAnalysis
from demo_staging.live.provider_receipts import collect_receipts
def block(*a,**kw):raise AssertionError("NO_NETWORK_ALLOWED")
socket.socket.connect=block
socket.socket.connect_ex=block
socket.create_connection=block
expected=ProductAnalysis(is_cosmetic=True,product_type="스킨케어",container_type="병",
                         colors=["흰색"],label_text=["RAUM"],mood=["청량"],is_transparent=False)
class Stub:
 def parse(self,**kw):
  return SimpleNamespace(http_response=SimpleNamespace(
   json=lambda:{"status":"completed","id":"resp_test_local_only","model":"gpt-6-luna",
     "usage":{"input_tokens":10,"output_tokens":20,"total_tokens":30}},
   headers={"x-request-id":"req_local_fake"}),parse=lambda:SimpleNamespace(output_parsed=expected))
llm_client.client=SimpleNamespace(responses=SimpleNamespace(with_raw_response=Stub()))
with collect_receipts() as sink:
 out=llm_client.call_structured("safe input",ProductAnalysis,model="gpt-6-luna")
 assert out==expected
 assert len(sink.events)==1
 assert sink.events[0]["usage"]["total_tokens"]==30
print("OFFICIAL_OWNER_RESPONSE_USAGE_CAPTURE_PASS_NO_NETWORK")
'''
    env={**os.environ,"OPENAI_API_KEY":"test-not-real-key-do-not-use"}
    result=subprocess.run([sys.executable,"-c",code],env=env,
        capture_output=True,text=True,check=False,timeout=15)
    assert result.returncode==0,result.stderr
    assert "OFFICIAL_OWNER_RESPONSE_USAGE_CAPTURE_PASS_NO_NETWORK" in result.stdout
