"""BP18 F11/S03 HTTP ACTOR/CSRF/CAS + explicit policy re-review.

Real FastAPI TestClient, genuine SQLite + official DTOs, no paid calls.
"""
from fastapi.testclient import TestClient
from tests.demo_live.test_http_gateway import setup,login,photo
from tests.demo_live.test_live_contracts import sample_input


def test_policy_version_flip_get_approved_stale_and_http_revalidation(
    tmp_path,monkeypatch
):
    monkeypatch.setenv("IT_TEM_BP18_F11_ENABLED","YES")
    monkeypatch.setenv("IT_TEM_BP18_REVIEW_POLICY_ID","bp18-f11-browser-v1")
    monkeypatch.setenv("IT_TEM_QA_FIXTURE_ENABLED","YES")
    monkeypatch.setenv("IT_TEM_QA_ALLOWED_ACTORS","alice,bob")
    monkeypatch.setenv("IT_TEM_LIVE_ENABLED","NO")
    monkeypatch.setenv("IT_TEM_LIVE_EXECUTION_APPROVED","NO")
    monkeypatch.setenv("IT_TEM_DEMO_SECURE_COOKIE","NO")
    monkeypatch.delenv("OPENAI_API_KEY",raising=False)
    app,codes=setup(tmp_path)
    head={"Origin":"http://testserver"}
    with TestClient(app,client=("127.0.0.1",11223)) as alice, \
         TestClient(app,client=("127.0.0.1",11224)) as bob, \
         TestClient(app,client=("127.0.0.1",11225)) as guest:
        login(alice,codes["alice"]);login(bob,codes["bob"])
        base="/demo/api/live/jobs/"
        p=alice.post("/api/v1/jobs",files=[
            ("product_images",("a.png",photo((130,150,160)),"image/png")),
            ("product_images",("b.png",photo((155,175,195)),"image/png")),
        ],headers=head)
        assert p.status_code==201,p.text
        jid=p.json()["job_id"]
        url=base+jid
        inp=sample_input()
        inp["image_size"]="4:5"
        inp["generation_mode"]="composed"
        created=alice.post(url+"/input",json=inp,headers=head)
        assert created.status_code==200,created.text
        text=alice.post("/demo/api/qa/jobs/"+jid+"/text",headers=head)
        assert text.status_code==200,text.text
        old=text.json()
        assert old["review_policy"]["status"]=="CURRENT"
        assert old["review_policy"]["sha"] and len(old["review_policy"]["sha"])==64
        body={"expected_generation":old["generation"],
              "expected_review_sha":old["review_sha"]}
        revalidate=url+"/revalidate-policy"
        assert guest.post(revalidate,json=body,headers=head).status_code==401
        assert bob.post(revalidate,json=body,headers=head).status_code==404
        assert alice.post(revalidate,json=body,
                          headers={"Origin":"http://untrusted.invalid"}).status_code==403
        # No policy change: it MUST not fabricate a new Review Generation.
        assert alice.post(revalidate,json=body,headers=head).status_code==409
        monkeypatch.setenv("IT_TEM_BP18_REVIEW_POLICY_ID","bp18-f11-browser-v2")
        from demo_staging.live.store import LiveStore
        flow=app.state.live_pipeline
        flow.state=LiveStore(flow.state.filename)
        stale=alice.get(url)
        assert stale.status_code==200,stale.text
        assert stale.json()["review_policy"]["status"]=="REVALIDATION_REQUIRED"
        assert not stale.json()["approval_current"]
        assert alice.post(url+"/approve-copy",json={
            **body,"acknowledge_evidence":True},headers=head).status_code==409
        changed=alice.post(revalidate,json=body,headers=head)
        assert changed.status_code==200,changed.text
        new=changed.json()
        assert new["generation"]==old["generation"]+1
        assert new["copy_sha"]==old["copy_sha"]
        assert new["review_sha"]!=old["review_sha"]
        assert new["approval_current"] is False
        assert new["review_policy"]["status"]=="CURRENT"
        assert alice.post(revalidate,json=body,headers=head).status_code==409
        assert alice.post(url+"/approve-copy",json={
            **body,"acknowledge_evidence":True},headers=head).status_code==409
        valid=alice.post(url+"/approve-copy",json={
            "expected_generation":new["generation"],
            "expected_review_sha":new["review_sha"],
            "acknowledge_evidence":True},headers=head)
        assert valid.status_code==200,valid.text
        assert valid.json()["approval_current"] is True
        assert bob.get(url).status_code==404
        with app.state.live_pipeline.cost.connect() as db:
            assert db.execute("select count(*) from attempts").fetchone()[0]==0
        with app.state.live_queue.db() as db:
            assert db.execute("select count(*) from queued_ops").fetchone()[0]==0
