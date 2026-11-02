from fastapi.testclient import TestClient
from tests.demo_live.test_http_gateway import setup,login,photo
from tests.demo_live.test_live_contracts import sample_input

def test_latest_task_owner_scope_reload_and_no_paid_calls(tmp_path):
    app,codes=setup(tmp_path)
    with TestClient(app) as alice,TestClient(app) as bob,TestClient(app) as anon:
        login(alice,codes["alice"])
        login(bob,codes["bob"])
        response=alice.post("/api/v1/jobs",files=[
            ("product_images",("a.png",photo((115,144,160)),"image/png")),
            ("product_images",("b.png",photo((121,155,140)),"image/png"))],
            headers={"Origin":"http://testserver"})
        assert response.status_code==201
        jid=response.json()["job_id"]
        prefix=f"/demo/api/live/jobs/{jid}"
        assert anon.get(prefix+"/task-status").status_code==401
        assert bob.get(prefix+"/task-status").status_code==404
        x=alice.post(prefix+"/input",json=sample_input(),
            headers={"Origin":"http://testserver"})
        assert x.status_code==200
        assert alice.get(prefix+"/task-status").json()["task"] is None
        task,_=app.state.live_queue.enqueue(actor="alice",job_id=jid,
            stage="analysis",context_sha=x.json()["input_sha"],mode="LIVE")
        saved=alice.get(prefix+"/task-status")
        assert saved.status_code==200
        assert saved.json()["task"]["task_id"]==task["id"]
        assert saved.json()["task"]["state"]=="QUEUED"
        assert bob.get(prefix+"/task-status").status_code==404
        assert app.state.live_queue.read(task["id"])["state"]=="QUEUED"
