"""Read-only resume catalog does not disclose another Actor or shared-only jobs."""
from fastapi.testclient import TestClient
from tests.demo_live.test_http_gateway import setup,login,photo
from tests.demo_live.test_live_contracts import sample_input


def upload(client, color):
    response=client.post("/api/v1/jobs",files=[
        ("product_images",("one.png",photo(color),"image/png")),
        ("product_images",("two.png",photo((101,121,141)),"image/png")),
    ],headers={"Origin":"http://testserver"})
    assert response.status_code==201,response.text
    return response.json()["job_id"]


def test_actor_private_catalog_and_upload_only_not_resumable(tmp_path):
    app,codes=setup(tmp_path)
    prefix="/demo/api/live"
    with TestClient(app) as alice,TestClient(app) as bob,TestClient(app) as anon:
        assert anon.get(prefix+"/jobs").status_code==401
        login(alice,codes["alice"])
        login(bob,codes["bob"])
        assert alice.get(prefix+"/jobs").json()=={"jobs":[]}
        aid=upload(alice,(110,120,130))
        not_ready=upload(alice,(111,121,131))
        bid=upload(bob,(145,155,165))
        a=alice.post(prefix+"/jobs/"+aid+"/input",json=sample_input(),
            headers={"Origin":"http://testserver"})
        assert a.status_code==200,a.text
        assert a.json()["state"]=="INPUT_STORED"
        b=bob.post(prefix+"/jobs/"+bid+"/input",json=sample_input(),
            headers={"Origin":"http://testserver"})
        assert b.status_code==200,b.text
        mine=alice.get(prefix+"/jobs")
        assert mine.status_code==200,mine.text
        rows=mine.json()["jobs"]
        assert len(rows)==1 and rows[0]["job_id"]==aid
        assert rows[0]["state"]=="INPUT_STORED"
        assert rows[0]["image_size"]=="4:5"
        assert rows[0]["generation_mode"]=="composed"
        assert "created_at" in rows[0] and rows[0]["product_name"]
        assert bid not in str(rows) and not_ready not in str(rows)
        assert not any(k in str(rows) for k in ("original_filename","asset_id","input_json","reference_images"))
        assert bob.get(prefix+"/jobs").json()["jobs"][0]["job_id"]==bid
        assert bob.get(prefix+"/jobs/"+aid).status_code==404
        assert anon.get(prefix+"/jobs").status_code==401
        assert alice.get(prefix+"/jobs").json()["jobs"]==rows
