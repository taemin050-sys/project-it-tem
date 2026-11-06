"""Text Owner #25 offline-only source-first contract + revision/queue safety.

No real model, socket or token acquisition. Results are not Live E2E claims.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest
from fastapi.testclient import TestClient

from demo_staging.live.checkpoints import LiveCheckpoints
from demo_staging.live.contracts import LiveGateError,digest,validate_input
from demo_staging.live.pipeline import LivePipeline
from demo_staging.live.queue import LiveQueue
from src.text_generation.schemas import AdCopyOutput,CopyRevisionOutput
from tests.demo_live.test_live_contracts import assets,sample_input
from tests.demo_live.test_pipeline import FakeOwner,prepare_service
from tests.demo_live.test_http_gateway import setup,login,photo


class FakeRevision(FakeOwner):
    def __init__(self, *, same=False, mismatch=False):
        super().__init__()
        self.same=same
        self.mismatch=mismatch
        self.revisions=0
    def revise_copy(self,product,analysis,research,previous,instruction):
        self.revisions+=1
        assert product.emoji_level in ("없음","보통","많이")
        assert isinstance(previous,AdCopyOutput)
        revised=previous.model_copy(deep=True)
        if not self.same:
            revised.ad_copy.headline="새롭게 산뜻하게" if self.revisions==1 else "매일 더 산뜻하게"
        return CopyRevisionOutput(revised=revised,
            changed_fields=(["caption"] if self.mismatch else [] if self.same else ["headline"]),
            note=("요청한 치료 표현은 광고에 사용할 수 없습니다."
                  if self.same else None))


def create_ready(tmp_path,*,functional=False):
    flow,jid=prepare_service(tmp_path)
    payload=sample_input()
    payload["image_size"]="4:5"
    payload["product"]["emoji_level"]="많이"
    if functional:
        payload["product"]["is_functional"]=True
        payload["product"]["functional_types"]=["자외선차단"]
    j=flow.prepare("alice",jid,payload,template_profile="A")
    fake=FakeRevision()
    original=flow.text("alice",jid,fake,offline=True)
    assert original["mode"]=="OFFLINE_FIXTURE" and original["generation"]==1
    return flow,jid,original,fake


def test_owner_input_is_actual_text_v010_and_bound_to_job(tmp_path):
    flow,jid,job,fake=create_ready(tmp_path, functional=True)
    product=json.loads(flow.state.get("alice",jid)["input_json"])["product"]
    assert product["functional_types"]==["자외선차단"]
    assert product["is_functional"] is True
    assert product["emoji_level"]=="많이"
    assert fake.calls==["analyze","research","copy"]
    assert flow.state.template("alice",jid)["profile_id"]=="OWNER_IMAGE_SIZE_4_5"


@pytest.mark.parametrize("mutate",["invalid_emoji","unauthorized_emoji","unknown_field"])
def test_owner_input_fails_closed_before_job(tmp_path,mutate):
    body=sample_input()
    p=body["product"]
    p["is_functional"]=True
    p["functional_types"]=["자외선차단"]
    p["emoji_level"]="보통"
    if mutate=="invalid_emoji":p["emoji_level"]="적음"
    if mutate=="unauthorized_emoji":p["emoji_level"]=4
    if mutate=="unknown_field":p["live_overrides"]="approve-all"
    with pytest.raises((LiveGateError,ValueError)):
        validate_input(body,assets())


def test_offline_owner_revision_changes_only_requested_field_and_restores(tmp_path):
    flow,jid,job,fake=create_ready(tmp_path, functional=True)
    initial_copy=json.loads(job["copy_json"])
    rev=flow.revise_copy("alice",jid,"헤드를 더 산뜻하게",
       job["generation"],job["review_sha"],provider=fake,offline=True)
    assert fake.revisions==1
    assert rev["state"]=="COPY_REVIEW_REQUIRED" and rev["generation"]==2
    assert rev["copy_sha"]!=job["copy_sha"] and rev["review_sha"]!=job["review_sha"]
    assert rev["approval_sha"] is None
    current=json.loads(rev["copy_json"])
    assert current["ad_copy"]["headline"]!=initial_copy["ad_copy"]["headline"]
    for field in ("subline","cta"):
        assert current["ad_copy"][field]==initial_copy["ad_copy"][field]
    assert current["plan"]==initial_copy["plan"]
    assert current["caption"]==initial_copy["caption"]
    assert current["hashtags"]==initial_copy["hashtags"]
    assert flow.state.revision_feedback("alice",jid)=={
        "note":None,"changed_fields":["headline"],"source":"OWNER_TEXT_V010_OFFLINE"}
    with pytest.raises(LiveGateError,match="STALE_REVIEW_OR_REVISION"):
        flow.revise_copy("alice",jid,"헤드를 더 산뜻하게",
           job["generation"],job["review_sha"],provider=fake,offline=True)
    assert fake.revisions==1
    restored=flow.state.restore_previous_copy("alice",jid,rev["generation"],rev["review_sha"])
    assert restored["generation"]==3 and restored["copy_sha"]==job["copy_sha"]
    assert restored["review_sha"]!=job["review_sha"]
    assert restored["approval_sha"] is None
    assert flow.state.revision_feedback("alice",jid) is None
    # Another distinct revision is allowed in the same Job and receives a
    # distinct immutable copy_revision checkpoint row.
    again=flow.revise_copy("alice",jid,"이번에는 카피를 다르게",
       restored["generation"],restored["review_sha"],provider=fake,offline=True)
    assert again["generation"]==4
    assert fake.revisions==2
    with flow.checkpoints.db() as db:
        assert db.execute("""SELECT COUNT(*) FROM text_revision_checkpoints
            WHERE job_id=? AND stage='copy_revision'""",(jid,)).fetchone()[0]==2


def test_owner_refusal_note_preserves_copy_and_review_generation_without_fake_edit(tmp_path):
    flow,jid,job,fake=create_ready(tmp_path)
    refusing=FakeRevision(same=True)
    rev=flow.revise_copy("alice",jid,"피부 치료 효과가 있다고 써",
       job["generation"],job["review_sha"],provider=refusing,offline=True)
    assert rev["copy_sha"]==job["copy_sha"] and rev["generation"]==job["generation"]
    assert rev["review_sha"]==job["review_sha"]
    assert flow.state.previous_copy_available("alice",jid) is False
    assert flow.state.revision_feedback("alice",jid)=={
        "note":"요청한 치료 표현은 광고에 사용할 수 없습니다.",
        "changed_fields":[],"source":"OWNER_TEXT_V010_OFFLINE"}
    # No change: existing version remains approvable, not a phantom review.
    approved=flow.state.approve_copy("alice",jid,job["generation"],job["review_sha"])
    assert approved["state"]=="COPY_APPROVED"


def test_owner_mismatched_changed_fields_cannot_commit_revision(tmp_path):
    flow,jid,job,_=create_ready(tmp_path)
    bad=FakeRevision(mismatch=True)
    with pytest.raises(LiveGateError,match="REVISION_CHANGED_FIELDS_INVALID"):
        flow.revise_copy("alice",jid,"헤드 변경",
            job["generation"],job["review_sha"],provider=bad,offline=True)
    persisted=flow.state.get("alice",jid)
    assert persisted["generation"]==job["generation"]
    assert persisted["copy_sha"]==job["copy_sha"]
    assert flow.state.revision_feedback("alice",jid) is None


def test_owner_revisions_are_never_an_injected_provider_in_live(tmp_path):
    flow,jid,job,fake=create_ready(tmp_path)
    with pytest.raises(LiveGateError,match="COPY_REVISION_PROVENANCE_MISMATCH"):
        flow.revise_copy("alice",jid,"변경",
             job["generation"],job["review_sha"],provider=fake,offline=False)


def test_revision_queue_20_concurrent_one_task_and_unknown_blocks_replay(tmp_path):
    q=LiveQueue(tmp_path/"queue.sqlite")
    instruction={"instruction":"헤드만 수정","expected_generation":1,
                 "expected_review_sha":"a"*64}
    sha=digest({"request":instruction,"copy_sha":"b"*64})
    def enqueue(_):
        return q.enqueue(actor="alice",job_id="c"*32,stage="copy_revision",
            context_sha=sha,mode="LIVE",revision_payload=instruction)
    with ThreadPoolExecutor(max_workers=10) as pool:
        results=list(pool.map(enqueue,range(20)))
    assert len({x["id"] for x,new in results})==1
    assert sum(new for x,new in results)==1
    assert q.revision_payload(results[0][0]["id"])==instruction
    different={**instruction,"instruction":"다른 수정 요청"}
    with pytest.raises(LiveGateError,match="REVISION_IN_PROGRESS"):
        q.enqueue(actor="alice",job_id="c"*32,stage="copy_revision",
            context_sha=digest({"request":different,"copy_sha":"b"*64}),
            mode="LIVE",revision_payload=different)
    claim=q.claim()
    assert claim["id"]==results[0][0]["id"]
    assert q.reconcile_restart()==1
    assert q.read(claim["id"])["state"]=="BILLING_UNKNOWN"
    assert q.claim() is None
    with pytest.raises(LiveGateError,match="REVISION_IN_PROGRESS"):
        q.enqueue(actor="alice",job_id="c"*32,stage="copy_revision",
            context_sha=digest({"request":different,"copy_sha":"b"*64}),
            mode="LIVE",revision_payload=different)


def test_offline_http_live_revision_disabled_and_acl(tmp_path,monkeypatch):
    monkeypatch.setenv("IT_TEM_LIVE_ENABLED","NO")
    monkeypatch.setenv("IT_TEM_LIVE_EXECUTION_APPROVED","NO")
    monkeypatch.setenv("IT_TEM_LIVE_WEB_QUEUE_ENABLED","NO")
    app,codes=setup(tmp_path)
    with TestClient(app) as alice, TestClient(app) as bob:
        login(alice,codes["alice"]);login(bob,codes["bob"])
        created=alice.post("/api/v1/jobs",files=[
          ("product_images",("a.png",photo((120,130,140)),"image/png")),
          ("product_images",("b.png",photo((160,150,170)),"image/png"))],
          headers={"Origin":"http://testserver"})
        assert created.status_code==201
        jid=created.json()["job_id"]
        path=f"/demo/api/live/jobs/{jid}/revise-copy"
        body={"instruction":"헤드를 수정","expected_generation":1,"expected_review_sha":"a"*64}
        assert alice.post(path,json=body,headers={"Origin":"http://testserver"}).status_code==423
        assert bob.post(path,json=body,headers={"Origin":"http://testserver"}).status_code==404
        assert alice.post(path,json={**body,"instruction":"x"*301},
            headers={"Origin":"http://testserver"}).status_code==422
        with sqlite3.connect(tmp_path/"runtime"/"live"/"queue.sqlite") as db:
            assert db.execute("SELECT COUNT(*) FROM queued_ops").fetchone()[0]==0
        with sqlite3.connect(tmp_path/"runtime"/"live"/"cost.sqlite") as db:
            assert db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]==0



@pytest.mark.parametrize("scenario",["no_type_functional","auto_true","duplicates","missing_default"])
def test_owner_v010_functional_types_optional_and_auto_normalize(scenario):
    p=sample_input()
    p["product"]["is_functional"]=True
    p["product"]["functional_types"]=["자외선차단"]
    if scenario=="no_type_functional":
        p["product"]["functional_types"]=[]
    elif scenario=="auto_true":
        p["product"]["is_functional"]=False
    elif scenario=="duplicates":
        p["product"]["functional_types"]=["자외선차단","자외선차단"]
    else:
        p["product"].pop("functional_types")
        p["product"].pop("emoji_level",None)
    snap,sha=validate_input(p,assets())
    result=snap["product"]
    assert len(sha)==64
    if scenario in ("no_type_functional","missing_default"):
        assert result["is_functional"] is True
        assert result["functional_types"]==[]
    else:
        assert result["is_functional"] is True
        assert result["functional_types"]==["자외선차단"]
    if scenario=="missing_default":
        assert result["emoji_level"]=="없음"
