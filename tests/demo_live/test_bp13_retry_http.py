"""BP13 actual FastAPI offline fixture: reject -> explicit attempt v2 -> finish."""
import hashlib
from uuid import uuid4
from fastapi.testclient import TestClient
from tests.demo_live.test_http_gateway import setup,login,photo
from tests.demo_live.test_live_contracts import sample_input

ORIGIN={"Origin":"http://testserver"}


def test_qa_reject_regenerate_preserves_copy_and_old_png(tmp_path,monkeypatch):
    monkeypatch.setenv("IT_TEM_QA_FIXTURE_ENABLED","YES")
    monkeypatch.setenv("IT_TEM_LIVE_ENABLED","NO")
    monkeypatch.setenv("IT_TEM_LIVE_EXECUTION_APPROVED","NO")
    monkeypatch.setenv("IT_TEM_DEMO_SECURE_COOKIE","NO")
    monkeypatch.setenv("IT_TEM_QA_ALLOWED_ACTORS","alice,bob")
    from tests.demo_live.test_pipeline import FONT
    monkeypatch.setenv("IT_TEM_LIVE_KOREAN_FONT",str(FONT))
    app,codes=setup(tmp_path)
    with TestClient(app,client=("127.0.0.1",12121)) as client,\
         TestClient(app,client=("127.0.0.1",12222)) as peer:
        login(client,codes["alice"]);login(peer,codes["bob"])
        created=client.post("/api/v1/jobs",files=[
            ("product_images",("a.png",photo((112,113,114)),"image/png")),
            ("product_images",("b.png",photo((131,132,133)),"image/png"))],headers=ORIGIN)
        assert created.status_code==201,created.text
        jid=created.json()["job_id"]
        root="/demo/api/live/jobs/"+jid
        qa="/demo/api/qa/jobs/"+jid
        i=client.post(root+"/input",json={**sample_input(),"image_size":"4:5"},headers=ORIGIN)
        assert i.status_code==200,i.text
        first=client.post(qa+"/text",headers=ORIGIN)
        assert first.status_code==200,first.text
        copy=first.json()
        p=client.post(root+"/approve-copy",json={"expected_generation":copy["generation"],
            "expected_review_sha":copy["review_sha"]},headers=ORIGIN)
        assert p.status_code==200,p.text
        img=client.post(qa+"/prompt-image",headers=ORIGIN)
        assert img.status_code==200,img.text
        one=img.json()
        before=client.get(qa+"/artifacts/candidate").content
        assert hashlib.sha256(before).hexdigest()==one["image_sha"]
        blocked=peer.post(qa+"/regenerate-image",json={
            "expected_image_sha":one["image_sha"],"request_key":uuid4().hex},headers=ORIGIN)
        assert blocked.status_code==404
        rejected=client.post(root+"/reject-image",json={"image_sha":one["image_sha"]},headers=ORIGIN)
        assert rejected.status_code==200,rejected.text
        assert rejected.json()["state"]=="IMAGE_REJECTED"
        key=uuid4().hex
        recovered=client.post(qa+"/regenerate-image",json={
            "expected_image_sha":one["image_sha"],"request_key":key},headers=ORIGIN)
        assert recovered.status_code==200,recovered.text
        other=recovered.json()
        assert other["state"]=="IMAGE_REVIEW_REQUIRED"
        assert other["image_attempt_version"]==2
        assert other["image_sha"]!=one["image_sha"]
        assert other["copy_sha"]==one["copy_sha"]
        assert other["review_sha"]==one["review_sha"]
        assert other["approval_current"] is True
        historical=app.state.live_pipeline.root/"outputs"/jid/"attempts"/f"v1-{one['image_sha']}.png"
        assert historical.read_bytes()==before
        duplicate=client.post(qa+"/regenerate-image",json={
            "expected_image_sha":one["image_sha"],"request_key":key},headers=ORIGIN)
        assert duplicate.status_code in (409,422)
        approve=client.post(root+"/approve-image",json={"image_sha":other["image_sha"]},headers=ORIGIN)
        assert approve.status_code==200,approve.text
        composed=client.post(qa+"/compose",json={},headers=ORIGIN)
        assert composed.status_code==200,composed.text
        finished=composed.json()
        assert finished["state"]=="COMPLETED"
        for kind,field in [("final","final_sha"),("caption","caption_sha")]:
            art=client.get(qa+"/artifacts/"+kind)
            assert art.status_code==200
            assert hashlib.sha256(art.content).hexdigest()==finished[field]
        with app.state.live_pipeline.cost.connect() as c:
            assert c.execute("select count(*) from attempts").fetchone()[0]==0
        with app.state.live_queue.db() as c:
            assert c.execute("select count(*) from queued_ops").fetchone()[0]==0
