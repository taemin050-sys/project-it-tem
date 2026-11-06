import sqlite3
import pytest
from demo_staging.live.contracts import LiveGateError,digest
from demo_staging.live.checkpoints import LiveCheckpoints
from tests.demo_live.test_pipeline import FakeOwner,prepare_service
from tests.demo_live.test_live_contracts import sample_input
from src.text_generation.schemas import ProductAnalysisResult

def test_resume_offline_after_research_exception_without_new_vision(tmp_path):
    flow,jid=prepare_service(tmp_path)
    flow.prepare("alice",jid,sample_input())
    class Interrupted(FakeOwner):
        def research(self,product,analysis):
            self.calls.append("research-failure")
            raise RuntimeError("simulated crash after VLM result persisted")
    interrupted=Interrupted()
    with pytest.raises(RuntimeError,match="simulated crash"):
        flow.text("alice",jid,interrupted,offline=True)
    assert interrupted.calls==["analyze","research-failure"]
    saved=flow.checkpoints.load("alice",jid,"vision",
        digest({"input_sha":flow.state.get("alice",jid)["input_sha"],
                "assets":[a["sha256"] for a in
                    __import__("json").loads(flow.state.get("alice",jid)["input_json"])["ordered_asset_hashes"]],
                "model":"gpt-6-luna"}),"OFFLINE_FIXTURE",ProductAnalysisResult)
    assert saved.analysis_succeeded
    resumed=FakeOwner()
    flow_again=type(flow)(flow.root,flow.jobs)
    row=flow_again.text("alice",jid,resumed,offline=True)
    assert row["state"]=="COPY_REVIEW_REQUIRED"
    assert resumed.calls==["research","copy"]
    assert row["mode"]=="OFFLINE_FIXTURE"

def test_immutable_checkpoint_blocks_actor_context_mode_and_tamper(tmp_path):
    store=LiveCheckpoints(tmp_path/"checkpoint.sqlite")
    obj=FakeOwner().analyze([b"one",b"two"])
    sha=digest({"stage":"vision","model":"test"})
    store.commit("alice","a"*32,"vision",sha,"OFFLINE_FIXTURE",obj,ProductAnalysisResult)
    assert store.load("alice","a"*32,"vision",sha,"OFFLINE_FIXTURE",ProductAnalysisResult)==obj
    with pytest.raises(LiveGateError,match="CHECKPOINT_CONTEXT_CONFLICT"):
        store.load("alice","a"*32,"vision",sha,"LIVE",ProductAnalysisResult)
    with pytest.raises(LiveGateError,match="CHECKPOINT_CONTEXT_CONFLICT"):
        store.load("bob","a"*32,"vision",sha,"OFFLINE_FIXTURE",ProductAnalysisResult)
    with store.db() as db:
        db.execute("UPDATE text_checkpoints SET payload_sha=? WHERE job_id=?",("0"*64,"a"*32))
    with pytest.raises(LiveGateError,match="CHECKPOINT_INTEGRITY_FAILURE"):
        store.load("alice","a"*32,"vision",sha,"OFFLINE_FIXTURE",ProductAnalysisResult)

def test_checkpoint_immutable_new_result_denied(tmp_path):
    store=LiveCheckpoints(tmp_path/"checkpoint.sqlite")
    obj=FakeOwner().analyze([b"one",b"two"])
    sha=digest({"v":1})
    store.commit("alice","a"*32,"vision",sha,"OFFLINE_FIXTURE",obj,ProductAnalysisResult)
    obj.analysis.colors.append("RED")
    with pytest.raises(LiveGateError,match="CHECKPOINT_REWRITE_DENIED"):
        store.commit("alice","a"*32,"vision",sha,"OFFLINE_FIXTURE",obj,ProductAnalysisResult)
