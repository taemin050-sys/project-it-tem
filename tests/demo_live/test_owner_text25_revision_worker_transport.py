"""LIVE revision HTTP/Queue/Worker routing: zero paid provider, synthetic snapshots.

This test never starts a real worker or imports an OpenAI client.
It tests signed-in Actor/Job ACL, CAS, same request idempotence, and
the dispatch boundary via an explicitly injected FakeFlow.
"""
from __future__ import annotations

import json
import socket
import hashlib

from fastapi.testclient import TestClient
import pytest

from demo_staging.live.contracts import digest,LiveGateError
from demo_staging.live.worker import _run_locked
from tests.demo_live.test_http_gateway import setup,login,photo
from tests.demo_live.test_live_contracts import safe_copy,sample_input


def test_live_copy_revision_queue_http_and_fake_worker_routing(tmp_path,monkeypatch):
    for k in ("IT_TEM_LIVE_WEB_QUEUE_ENABLED","IT_TEM_LIVE_ENABLED",
              "IT_TEM_LIVE_EXECUTION_APPROVED","IT_TEM_PROVIDER_READINESS_CONFIRMED"):
        monkeypatch.setenv(k,"YES")
    monkeypatch.setenv("IT_TEM_LIVE_APPROVED_ACTORS","alice")
    monkeypatch.setenv("IT_TEM_LIVE_COST_POLICY","MONITOR_ONLY")
    monkeypatch.delenv("OPENAI_API_KEY",raising=False)
    def no_network(*a,**k):
        raise AssertionError("NETWORK_CALL_PROHIBITED")
    monkeypatch.setattr(socket.socket,"connect",no_network)
    monkeypatch.setattr(socket.socket,"connect_ex",no_network)
    app,codes=setup(tmp_path)
    with TestClient(app) as a,TestClient(app) as b:
        login(a,codes["alice"])
        login(b,codes["bob"])
        created=a.post("/api/v1/jobs",files=[
            ("product_images",("p1.png",photo((120,130,140)),"image/png")),
            ("product_images",("p2.png",photo((145,150,160)),"image/png"))],
            headers={"Origin":"http://testserver"})
        assert created.status_code==201,created.text
        jid=created.json()["job_id"]
        inp=a.post(f"/demo/api/live/jobs/{jid}/input",json=sample_input(),
                   headers={"Origin":"http://testserver"})
        assert inp.status_code==200,inp.text
        analysis,research,copy,_=safe_copy()
        staged=app.state.live_pipeline.state.store_text(
            "alice",jid,analysis,research,copy,mode="LIVE")
        assert staged["state"]=="COPY_REVIEW_REQUIRED"
        instruction="헤드를 더 산뜻하게"
        expected={"instruction":instruction,
                  "expected_generation":staged["generation"],
                  "expected_review_sha":staged["review_sha"]}
        target=f"/demo/api/live/jobs/{jid}/revise-copy"
        outsider=b.post(target,json=expected,headers={"Origin":"http://testserver"})
        assert outsider.status_code==404
        wrong=a.post(target,json={**expected,"expected_generation":0},
                     headers={"Origin":"http://testserver"})
        assert wrong.status_code==409
        one=a.post(target,json=expected,headers={"Origin":"http://testserver"})
        assert one.status_code==202,one.text
        two=a.post(target,json=expected,headers={"Origin":"http://testserver"})
        assert two.status_code==202 and two.json()["task_id"]==one.json()["task_id"]
        assert two.json()["new"] is False
        different=a.post(target,json={**expected,"instruction":"다른 헤드 요청"},
                         headers={"Origin":"http://testserver"})
        assert different.status_code==409
        assert "task_id" not in str(different.json())
        taskid=one.json()["task_id"]
        task_view=a.get(f"/demo/api/live/tasks/{taskid}")
        assert task_view.status_code==200 and task_view.json()["stage"]=="copy_revision"
        assert "instruction" not in task_view.text
        assert b.get(f"/demo/api/live/tasks/{taskid}").status_code==404
        data=app.state.live_queue.revision_payload(taskid)
        assert data==expected
        # A test-only fake flow validates queue worker plumbing. No real
        # provider call or billing ledger reservation occurs here.
        class FakeFlow:
            def __init__(self):
                self.calls=[]
            def revision_context(self,actor,job_id,text,gen,sha,*,text_model):
                assert actor=="alice" and job_id==jid
                assert text==instruction and sha==expected["expected_review_sha"]
                return app.state.live_pipeline.revision_context(
                    actor,job_id,text,gen,sha,text_model=text_model)
            def revise_copy(self,actor,job_id,text,gen,sha,*,offline,text_model):
                assert offline is False and job_id==jid and text==instruction
                self.calls.append((job_id,text))
                return {"review_sha":"f"*64}
        fake=FakeFlow()
        assert _run_locked(tmp_path/"runtime",fake)=="LIVE_STAGE_COMMITTED"
        assert fake.calls==[(jid,instruction)]
        assert _run_locked(tmp_path/"runtime",fake)=="NO_LIVE_TASK"
        assert app.state.live_queue.read(taskid)["state"]=="SUCCEEDED"
        assert app.state.live_queue.read(taskid)["result_sha"]=="f"*64
        # Synthetic worker did not update the actual Job (intentionally);
        # it verified dispatch routing without claiming real AI success.
        with app.state.live_pipeline.cost.connect() as db:
            assert db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]==0
