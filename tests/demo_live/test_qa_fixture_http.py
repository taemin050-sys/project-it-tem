"""QA-only offline HTTP proof. No secrets, network or fake-LIVE provenance."""
import hashlib
from pathlib import Path
from fastapi.testclient import TestClient
from tests.demo_live.test_http_gateway import setup,login,photo
from tests.demo_live.test_live_contracts import sample_input


def test_qa_hard_disabled_even_with_logged_in_user(tmp_path,monkeypatch):
    monkeypatch.delenv("IT_TEM_QA_FIXTURE_ENABLED",raising=False)
    app,codes=setup(tmp_path)
    with TestClient(app,client=("127.0.0.1",12121)) as client:
        login(client,codes["alice"])
        assert client.post("/demo/api/qa/jobs/"+"0"*32+"/text",
                    headers={"Origin":"http://testserver"}).status_code==404


def test_real_qa_http_offline_full_image_composition_and_acl(tmp_path,monkeypatch):
    monkeypatch.setenv("IT_TEM_QA_FIXTURE_ENABLED","YES")
    monkeypatch.setenv("IT_TEM_LIVE_ENABLED","NO")
    monkeypatch.setenv("IT_TEM_LIVE_EXECUTION_APPROVED","NO")
    monkeypatch.setenv("IT_TEM_DEMO_SECURE_COOKIE","NO")
    monkeypatch.setenv("IT_TEM_QA_ALLOWED_ACTORS","alice,bob")
    monkeypatch.delenv("OPENAI_API_KEY",raising=False)
    from tests.demo_live.test_pipeline import FONT
    monkeypatch.setenv("IT_TEM_LIVE_KOREAN_FONT",str(FONT))
    app,codes=setup(tmp_path)
    with TestClient(app,client=("127.0.0.1",12121)) as user, \
         TestClient(app,client=("127.0.0.1",12122)) as peer:
        login(user,codes["alice"]);login(peer,codes["bob"])
        created=user.post("/api/v1/jobs",files=[
            ("product_images",("a.png",photo((120,130,140)),"image/png")),
            ("product_images",("b.png",photo((150,160,170)),"image/png"))],
            headers={"Origin":"http://testserver"})
        assert created.status_code==201
        jid=created.json()["job_id"]
        base=f"/demo/api/live/jobs/{jid}"
        qa=f"/demo/api/qa/jobs/{jid}"
        input_=user.post(base+"/input",json=sample_input(),
                         headers={"Origin":"http://testserver"})
        assert input_.status_code==200
        assert input_.json()["template_profile"]=="A_CENTERED"
        assert user.get(qa+"/artifacts/final").status_code==409
        denied=peer.post(qa+"/text",headers={"Origin":"http://testserver"})
        assert denied.status_code==404
        text=user.post(qa+"/text",headers={"Origin":"http://testserver"})
        assert text.status_code==200,text.text
        first=text.json()
        assert first["state"]=="COPY_REVIEW_REQUIRED"
        assert first["mode"]=="OFFLINE_FIXTURE"
        assert first["compliance"]["passed"] is True
        assert user.post(base+"/queue-text",headers={"Origin":"http://testserver"}).status_code==423
        approved=user.post(base+"/approve-copy",json={
            "expected_generation":first["generation"],
            "expected_review_sha":first["review_sha"]},
            headers={"Origin":"http://testserver"})
        assert approved.status_code==200,approved.text
        candidate=user.post(qa+"/prompt-image",headers={"Origin":"http://testserver"})
        assert candidate.status_code==200,candidate.text
        img=candidate.json()
        assert img["mode"]=="OFFLINE_FIXTURE"
        assert img["state"]=="IMAGE_REVIEW_REQUIRED"
        assert img["image_sha"]
        raw=user.get(qa+"/artifacts/candidate")
        assert raw.status_code==200
        assert raw.headers["x-it-tem-provenance"]=="OFFLINE_FIXTURE"
        assert hashlib.sha256(raw.content).hexdigest()==img["image_sha"]
        assert peer.get(qa+"/artifacts/candidate").status_code==404
        image_ok=user.post(base+"/approve-image",json={"image_sha":img["image_sha"]},
                           headers={"Origin":"http://testserver"})
        assert image_ok.status_code==200
        assert user.post(base+"/compose",json={},headers={"Origin":"http://testserver"}).status_code==423
        compose=user.post(qa+"/compose",json={},headers={"Origin":"http://testserver"})
        assert compose.status_code==200,compose.text
        finished=compose.json()
        assert finished["state"]=="COMPLETED"
        assert finished["mode"]=="OFFLINE_FIXTURE"
        for name,sha in (("final",finished["final_sha"]),
                         ("caption",finished["caption_sha"])):
            artifact=user.get(qa+"/artifacts/"+name)
            assert artifact.status_code==200
            assert artifact.headers["x-it-tem-provenance"]=="OFFLINE_FIXTURE"
            assert hashlib.sha256(artifact.content).hexdigest()==sha
            assert peer.get(qa+"/artifacts/"+name).status_code==404
        assert user.get(base+"/artifacts/final").status_code==409
        assert user.post(base+"/share",headers={"Origin":"http://testserver"}).status_code==409
        assert user.post(base+"/queue-image",headers={"Origin":"http://testserver"}).status_code==423
        assert user.post(qa+"/prompt-image",headers={"Origin":"http://testserver"}).status_code in (409,422)
        manifest=app.state.live_pipeline.state.read_manifest("alice",jid)
        assert manifest["receipt"]["provider_calls"]==0
        with app.state.live_pipeline.cost.connect() as c:
            assert c.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]==0


def test_qa_nonloopback_client_rejected(tmp_path,monkeypatch):
    monkeypatch.setenv("IT_TEM_QA_FIXTURE_ENABLED","YES")
    monkeypatch.setenv("IT_TEM_LIVE_ENABLED","NO")
    monkeypatch.setenv("IT_TEM_LIVE_EXECUTION_APPROVED","NO")
    monkeypatch.setenv("IT_TEM_DEMO_SECURE_COOKIE","NO")
    monkeypatch.setenv("IT_TEM_QA_ALLOWED_ACTORS","alice")
    app,codes=setup(tmp_path)
    with TestClient(app,client=("198.51.100.1",12121)) as client:
        login(client,codes["alice"])
        assert client.post("/demo/api/qa/jobs/"+"0"*32+"/text",
                           headers={"Origin":"http://testserver"}).status_code==404
