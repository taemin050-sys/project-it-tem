import hashlib
from fastapi.testclient import TestClient
from PIL import Image
from demo_staging.app import make_demo_app
from tests.demo_live.test_http_gateway import setup,login,photo
from tests.demo_live.test_live_contracts import sample_input,safe_copy
from src.text_generation.schemas import (
    ProductAnalysisResult,ResearchResult,AdCopyOutput,ImagePromptOutput
)

def test_final_live_ad_shared_only_by_owner_and_reviewable_by_another_actor(tmp_path):
    app,codes=setup(tmp_path)
    with TestClient(app) as creator,TestClient(app) as bob,TestClient(app) as unauth:
        login(creator,codes["alice"]);login(bob,codes["bob"])
        upload=creator.post("/api/v1/jobs",files=[
            ("product_images",("a.png",photo((110,150,120)),"image/png")),
            ("product_images",("b.png",photo((120,140,140)),"image/png"))],
            headers={"Origin":"http://testserver"})
        assert upload.status_code==201
        jid=upload.json()["job_id"]
        store=app.state.live_pipeline.state
        app.state.live_pipeline.prepare("alice",jid,sample_input())
        a,r,c,p=safe_copy()
        stage=store.store_text("alice",jid,
            ProductAnalysisResult.model_validate(a),ResearchResult.model_validate(r),
            AdCopyOutput.model_validate(c),mode="LIVE")
        store.approve_copy("alice",jid,stage["generation"],stage["review_sha"])
        store.store_prompt("alice",jid,ImagePromptOutput.model_validate(p))
        candidate_sha="a"*64
        store.store_image_candidate("alice",jid,candidate_sha)
        store.approve_image("alice",jid,candidate_sha)
        final=photo((160,190,195))
        caption=b"Example Live evaluator-only artifact"
        folder=app.state.live_pipeline.root/"outputs"/jid
        folder.mkdir(parents=True)
        (folder/"final.png").write_bytes(final)
        (folder/"caption.txt").write_bytes(caption)
        f_sha=hashlib.sha256(final).hexdigest()
        cap_sha=hashlib.sha256(caption).hexdigest()
        store.composed("alice",jid,f_sha,cap_sha)
        base="/demo/api/live"
        assert bob.get(base+"/jobs/"+jid).status_code==404
        assert bob.get(base+"/shared/"+jid+"/artifacts/final").status_code==404
        assert unauth.get(base+"/shared").status_code==401
        shared=creator.post(base+"/jobs/"+jid+"/share",
                            headers={"Origin":"http://testserver"})
        assert shared.status_code==200,shared.text
        assert shared.json()["raw_product_images_shared"] is False
        visible=bob.get(base+"/shared").json()["jobs"]
        assert len(visible)==1 and visible[0]["final_sha"]==f_sha
        from demo_staging.live.reviews import LiveShares
        raw = LiveShares(tmp_path / "runtime/live/shares.sqlite").item(jid)["shared_at"]
        assert visible[0]["shared_at"] == raw
        assert visible[0]["shared_at_utc"] == LiveShares.utc_iso8601(raw)
        assert visible[0]["shared_at_utc"].endswith("Z")
        assert bob.get(base+"/shared/"+jid+"/artifacts/final").content==final
        assert bob.get(base+"/shared/"+jid+"/artifacts/caption").content==caption
        rating=bob.post(base+"/shared/"+jid+"/evaluations",
            json={"job_id":jid,"scenario_id":"UC-01","category":"image_fidelity",
                  "score":4,"needs_improvement":False,"comment":"깔끔한 합성"},
            headers={"Origin":"http://testserver"})
        assert rating.status_code==200,rating.text
        assert rating.json()["artifact_sha256"]==f_sha
        history=bob.get(base+"/shared/"+jid+"/evaluations").json()["reviews"]
        assert len(history)==1 and history[0]["score"]==4
        assert bob.get("/api/v1/jobs/"+jid).status_code==404
        # Changing final bytes must not expose tampered content.
        (folder/"final.png").write_bytes(b"tampered")
        assert bob.get(base+"/shared/"+jid+"/artifacts/final").status_code==503
