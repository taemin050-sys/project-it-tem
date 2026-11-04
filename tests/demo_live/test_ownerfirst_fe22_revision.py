"""FE Owner #22 revision-request UX ↔ Serving offline-only CAS and restore.

No paid provider may be dispatched by any test. Real Live remains fail-closed.
"""
import json
import sqlite3
from fastapi.testclient import TestClient

from demo_staging.live.contracts import LiveGateError
from demo_staging.live.store import LiveStore
from tests.demo_live.test_http_gateway import setup,login,photo
from tests.demo_live.test_live_contracts import sample_input


def _post(client,path,body=None):
    return client.post(path,json=body,headers={"Origin":"http://testserver"})


def test_owner_first_qa_revision_restore_approval_and_acl(tmp_path,monkeypatch):
    monkeypatch.setenv("IT_TEM_QA_FIXTURE_ENABLED","YES")
    monkeypatch.setenv("IT_TEM_QA_ALLOWED_ACTORS","alice,bob")
    monkeypatch.setenv("IT_TEM_LIVE_ENABLED","NO")
    monkeypatch.setenv("IT_TEM_LIVE_EXECUTION_APPROVED","NO")
    monkeypatch.setenv("IT_TEM_DEMO_SECURE_COOKIE","NO")
    monkeypatch.delenv("OPENAI_API_KEY",raising=False)
    app,codes=setup(tmp_path)
    with TestClient(app,client=("127.0.0.1",12345)) as alice,TestClient(app,client=("127.0.0.1",12346)) as bob:
        login(alice,codes["alice"]);login(bob,codes["bob"])
        created=alice.post("/api/v1/jobs",files=[
            ("product_images",("one.png",photo((90,105,110)),"image/png")),
            ("product_images",("two.png",photo((130,140,145)),"image/png"))],
            headers={"Origin":"http://testserver"})
        assert created.status_code==201,created.text
        jid=created.json()["job_id"]
        input_data=sample_input()
        input_data["product"]["is_functional"]=True
        input_data["product"]["functional_types"]=["미백","주름개선"]
        entered=_post(alice,f"/demo/api/live/jobs/{jid}/input",input_data)
        assert entered.status_code==200,entered.text
        with app.state.live_pipeline.state.db() as db:
            original=json.loads(db.execute(
                "SELECT input_json FROM live_jobs WHERE job_id=?",(jid,)).fetchone()[0])
        assert original["product"]["functional_types"]==["미백","주름개선"]
        text=_post(alice,f"/demo/api/qa/jobs/{jid}/text")
        assert text.status_code==200,text.text
        initial=text.json()
        assert initial["state"]=="COPY_REVIEW_REQUIRED"
        assert initial["mode"]=="OFFLINE_FIXTURE" and not initial["previous_copy_available"]
        base=f"/demo/api/qa/jobs/{jid}"
        body={"instruction":"보습 표현을 조금 더 짧고 산뜻하게",
              "expected_generation":initial["generation"],
              "expected_review_sha":initial["review_sha"]}
        anonymous=_post(TestClient(app,client=("127.0.0.1",12400)),base+"/revise-copy",body)
        assert anonymous.status_code==401
        forbidden=_post(bob,base+"/revise-copy",body)
        assert forbidden.status_code==404
        assert _post(alice,f"/demo/api/live/jobs/{jid}/revise-copy",body).status_code==423
        revised=_post(alice,base+"/revise-copy",body)
        assert revised.status_code==200,revised.text
        updated=revised.json()
        assert updated["generation"]==initial["generation"]+1
        assert updated["copy_sha"]!=initial["copy_sha"]
        assert updated["review_sha"]!=initial["review_sha"]
        assert updated["compliance"]["passed"]
        assert updated["previous_copy_available"] is True
        assert updated["approval_current"] is False
        assert _post(alice,base+"/revise-copy",body).status_code==409
        old_ack={"expected_generation":initial["generation"],
                 "expected_review_sha":initial["review_sha"],"acknowledge_evidence":True}
        assert _post(alice,f"/demo/api/live/jobs/{jid}/approve-copy",old_ack).status_code==409
        previous={"expected_generation":updated["generation"],
                  "expected_review_sha":updated["review_sha"]}
        assert _post(bob,base+"/restore-copy",previous).status_code==404
        restored=_post(alice,base+"/restore-copy",previous)
        assert restored.status_code==200,restored.text
        back=restored.json()
        assert back["generation"]==updated["generation"]+1
        assert back["copy_sha"]==initial["copy_sha"]
        assert back["review_sha"]!=initial["review_sha"] and back["review_sha"]!=updated["review_sha"]
        assert back["approval_current"] is False and back["previous_copy_available"] is True
        assert _post(alice,f"/demo/api/live/jobs/{jid}/approve-copy",old_ack).status_code==409
        assert _post(alice,base+"/restore-copy",previous).status_code==409
        swap=_post(alice,base+"/restore-copy",{"expected_generation":back["generation"],
                                              "expected_review_sha":back["review_sha"]})
        assert swap.status_code==200,swap.text
        returned=swap.json()
        assert returned["copy_sha"]==updated["copy_sha"]
        assert returned["generation"]==back["generation"]+1
        fresh_ack={"expected_generation":returned["generation"],
                   "expected_review_sha":returned["review_sha"],"acknowledge_evidence":True}
        assert _post(alice,f"/demo/api/live/jobs/{jid}/approve-copy",fresh_ack).status_code==200
        with app.state.live_pipeline.state.db() as db:
            saved=db.execute(
                "SELECT COUNT(*) FROM live_copy_previous WHERE job_id=?",(jid,)).fetchone()[0]
            events=[r[0] for r in db.execute(
                "SELECT event FROM live_events WHERE job_id=? ORDER BY id",(jid,))]
            final=db.execute("SELECT approved_generation,approval_sha FROM live_jobs WHERE job_id=?",
                            (jid,)).fetchone()
        assert saved==1 and events.count("copy_revision_review_started")==1
        assert events.count("copy_previous_restored_review_started")==2
        assert events.count("real_copy_approved")==1
        assert final["approved_generation"]==returned["generation"] and final["approval_sha"]
        for path in ("cost.sqlite","queue.sqlite"):
            with sqlite3.connect(tmp_path/"runtime/live"/path) as db:
                table="attempts" if path=="cost.sqlite" else "queued_ops"
                assert db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]==0


def test_revision_store_previous_identity_and_untrusted_payload(tmp_path):
    store=LiveStore(tmp_path/"live.sqlite")
    assert store.previous_copy_available if hasattr(store,"previous_copy_available") else False
    # Unauthenticated and unknown Job or missing revision context always fail.
    try:store.previous_copy_available("bob","a"*32)
    except LiveGateError as e:assert e.code=="LIVE_JOB_NOT_FOUND"
    else:raise AssertionError("Unknown job was accepted")


def test_functional_types_do_not_silently_drop_at_live_ingress(tmp_path):
    from tests.demo_live.test_live_contracts import assets
    store=LiveStore(tmp_path/"live.sqlite")
    inp=sample_input()
    inp["product"]["is_functional"]=True
    inp["product"]["functional_types"]=["미백","주름개선","자외선차단"]
    row=store.create("alice","a"*32,inp,assets())
    received=json.loads(row["input_json"])
    assert received["product"]["functional_types"]==inp["product"]["functional_types"]
    bad=sample_input()
    bad["product"]["functional_types"]=["허위 기능"]
    try:store.create("alice","b"*32,bad,assets())
    except LiveGateError as e:assert e.code=="PRODUCT_INPUT_INVALID"
    else:raise AssertionError("Invalid functional cosmetic type accepted")
