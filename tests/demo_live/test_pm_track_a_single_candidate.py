"""PM Track A hard gate: FE #26 mode selection, one image, no unapproved batch.

Zero external provider calls. Real FastAPI/SQLite Job/QA fixture/Worker surfaces.
"""
from __future__ import annotations

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from demo_staging.live.contracts import LiveGateError, assert_single_image_scope
from tests.demo_live.test_http_gateway import setup, login, photo
from tests.demo_live.test_live_contracts import sample_input
from tests.demo_live.test_pipeline import FakeOwner, FONT, prepare_service
from src.image_generation.size_selection import resolve_size_choice

ORIGIN = {"Origin": "http://testserver"}


def configure_qa(monkeypatch):
    monkeypatch.setenv("IT_TEM_QA_FIXTURE_ENABLED", "YES")
    monkeypatch.setenv("IT_TEM_LIVE_ENABLED", "NO")
    monkeypatch.setenv("IT_TEM_LIVE_EXECUTION_APPROVED", "NO")
    monkeypatch.setenv("IT_TEM_DEMO_SECURE_COOKIE", "NO")
    monkeypatch.setenv("IT_TEM_QA_ALLOWED_ACTORS", "alice")
    monkeypatch.setenv("IT_TEM_LIVE_KOREAN_FONT", str(FONT))
    for secret in ("OPENAI_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(secret, raising=False)


def new_job(client):
    r = client.post("/api/v1/jobs", files=[
        ("product_images", ("a.png", photo((120, 130, 140)), "image/png")),
        ("product_images", ("b.png", photo((150, 160, 170)), "image/png")),
    ], headers=ORIGIN)
    assert r.status_code == 201, r.text
    return r.json()["job_id"]


@pytest.mark.parametrize("mode", ("composed", "freeform"))
@pytest.mark.parametrize("ratio", ("3:4", "4:5", "9:16"))
def test_fe_single_selected_mode_ratio_qa_e2e_with_one_candidate_no_paid_calls(
    tmp_path, monkeypatch, mode, ratio,
):
    configure_qa(monkeypatch)
    app, codes = setup(tmp_path)
    with TestClient(app, client=("127.0.0.1", 12121)) as client:
        login(client, codes["alice"])
        capabilities = client.get("/demo/api/live/capabilities").json()["image_generation"]
        assert capabilities == {
            "candidate_count": 1,
            "batch_supported": False,
            "generation_modes": ["composed", "freeform"],
            "image_ratios": ["3:4", "4:5", "9:16"],
        }
        jid = new_job(client)
        base = "/demo/api/live/jobs/" + jid
        qa = "/demo/api/qa/jobs/" + jid
        r = client.post(base + "/input", json={
            **sample_input(), "image_size": ratio, "generation_mode": mode
        }, headers=ORIGIN)
        assert r.status_code == 200, r.text
        assert r.json()["generation_mode"] == mode and r.json()["image_size"] == ratio
        review = client.post(qa + "/text", headers=ORIGIN)
        assert review.status_code == 200, review.text
        review = review.json()
        approved = client.post(base + "/approve-copy", json={
            "expected_generation": review["generation"],
            "expected_review_sha": review["review_sha"],
        }, headers=ORIGIN)
        assert approved.status_code == 200, approved.text
        image = client.post(qa + "/prompt-image", headers=ORIGIN)
        assert image.status_code == 200, image.text
        image = image.json()
        assert image["state"] == "IMAGE_REVIEW_REQUIRED"
        assert image["generation_mode"] == mode
        assert image["image_attempt_version"] == 1
        raw = client.get(qa + "/artifacts/candidate")
        assert raw.status_code == 200
        assert hashlib.sha256(raw.content).hexdigest() == image["image_sha"]
        assert client.post(qa + "/prompt-image", headers=ORIGIN).status_code in (409, 422)
        assert client.post(base + "/approve-image", json={
            "image_sha": image["image_sha"]
        }, headers=ORIGIN).status_code == 200
        final = client.post(qa + "/compose", json={}, headers=ORIGIN)
        assert final.status_code == 200, final.text
        done = final.json()
        assert done["state"] == "COMPLETED"
        final_png = client.get(qa + "/artifacts/final")
        caption = client.get(qa + "/artifacts/caption")
        assert final_png.status_code == 200 and caption.status_code == 200
        assert hashlib.sha256(final_png.content).hexdigest() == done["final_sha"]
        assert hashlib.sha256(caption.content).hexdigest() == done["caption_sha"]
        assert done["output_size"] == dict(zip(("width", "height"),
                                               resolve_size_choice(ratio)[1].final))
        receipt = app.state.live_pipeline.state.read_manifest("alice", jid)["receipt"]
        assert receipt.get("generation_mode", "composed") == mode
        assert (receipt.get("font_sha256") is None) == (mode == "freeform")
        if mode == "freeform":
            assert receipt.get("rendering") == "provider_drawn_text"
        with app.state.live_pipeline.cost.connect() as c:
            assert c.execute("select count(*) from attempts").fetchone()[0] == 0
        with app.state.live_queue.db() as c:
            assert c.execute("select count(*) from queued_ops").fetchone()[0] == 0
        with app.state.live_pipeline.state.db() as c:
            assert c.execute("select count(*) from live_image_attempts where job_id=?",
                             (jid,)).fetchone()[0] == 1


@pytest.mark.parametrize("bad", (
    {"candidate_count": 2}, {"candidate_count": 3}, {"candidate_count": 4},
    {"freeform_count": 2, "composed_count": 1},
    {"image_modes": ["freeform", "composed"]},
    {"batch": True}, {"generation_mode": "batch"},
    {"generation_mode": "free-1+composed-1"},
))
def test_multi_image_inputs_rejected_before_any_job_or_cost(
    tmp_path, monkeypatch, bad,
):
    configure_qa(monkeypatch)
    app, codes = setup(tmp_path)
    with TestClient(app, client=("127.0.0.1", 12121)) as client:
        login(client, codes["alice"])
        jid = new_job(client)
        payload = {**sample_input(), "image_size": "4:5",
                   "generation_mode": "composed", **bad}
        response = client.post("/demo/api/live/jobs/" + jid + "/input",
                               json=payload, headers=ORIGIN)
        assert response.status_code == 422, response.text
        with pytest.raises(LiveGateError, match="LIVE_JOB_NOT_FOUND"):
            app.state.live_pipeline.state.get("alice", jid)
        with app.state.live_pipeline.cost.connect() as c:
            assert c.execute("select count(*) from attempts").fetchone()[0] == 0


@pytest.mark.parametrize("count", (2, 3, 4))
def test_http_queue_and_qa_reject_batch_options_without_replay(
    tmp_path, monkeypatch, count,
):
    configure_qa(monkeypatch)
    app, codes = setup(tmp_path)
    with TestClient(app, client=("127.0.0.1", 12121)) as client:
        login(client, codes["alice"])
        jid = new_job(client)
        base = "/demo/api/live/jobs/" + jid
        qa = "/demo/api/qa/jobs/" + jid
        assert client.post(base + "/input", json={
            **sample_input(), "image_size": "4:5", "generation_mode": "freeform"
        }, headers=ORIGIN).status_code == 200
        r = client.post(base + "/queue-image",
                        json={"candidate_count": count}, headers=ORIGIN)
        assert r.status_code == 422 and "PM_IMAGE_" in r.text
        r = client.post(base + "/queue-image?candidate_count=" + str(count),
                        headers=ORIGIN)
        assert r.status_code == 422
        assert client.post(qa + "/prompt-image", json={
            "freeform_count": count
        }, headers=ORIGIN).status_code == 422
        assert client.post(qa + "/prompt-image?batch=yes",
                           headers=ORIGIN).status_code == 422
        assert client.post(qa + "/prompt-image",
                           headers=ORIGIN).status_code in (409, 422)
        with app.state.live_pipeline.cost.connect() as c:
            assert c.execute("select count(*) from attempts").fetchone()[0] == 0
        with app.state.live_queue.db() as c:
            assert c.execute("select count(*) from queued_ops").fetchone()[0] == 0


def test_worker_rejects_tampered_multi_image_job_before_provider(
    tmp_path, monkeypatch,
):
    from demo_staging.live import worker
    flow, jid = prepare_service(tmp_path)
    flow.prepare("alice", jid, {
        **sample_input(), "image_size": "4:5", "generation_mode": "freeform"
    }, template_profile="A")
    owner = FakeOwner()
    review = flow.text("alice", jid, owner, offline=True)
    flow.state.approve_copy("alice", jid, review["generation"], review["review_sha"])
    flow.prompt("alice", jid, owner, offline=True)
    approved = flow.state.get("alice", jid)
    with flow.state.db() as c:
        payload = json.loads(approved["input_json"])
        payload["candidate_count"] = 3
        c.execute("update live_jobs set input_json=? where job_id=?",
                  (json.dumps(payload), jid))
    with pytest.raises(LiveGateError, match="PM_IMAGE_MULTICANDIDATE_SCOPE_NOT_APPROVED"):
        flow.image_input("alice", jid)

    from demo_staging.app import DemoLedger
    from demo_staging.live.queue import LiveQueue
    # Model a properly owned LIVE job in isolated SQLite, then tamper its
    # persisted candidate scope. No credential or network is available.
    DemoLedger(tmp_path/"demo.sqlite3").claim("alice",jid)
    flow.live_enabled=True
    flow.pm_authorized=True
    flow.approved_actors=frozenset({"alice"})
    for flag in ("IT_TEM_LIVE_ENABLED","IT_TEM_LIVE_EXECUTION_APPROVED",
                 "IT_TEM_PROVIDER_READINESS_CONFIRMED"):
        monkeypatch.setenv(flag,"YES")
    monkeypatch.setenv("IT_TEM_LIVE_COST_POLICY","MONITOR_ONLY")
    monkeypatch.setenv("IT_TEM_LIVE_APPROVED_ACTORS","alice")
    with flow.state.db() as c:
        c.execute("update live_jobs set mode='LIVE' where job_id=?",(jid,))
    queue=LiveQueue(tmp_path/"live"/"queue.sqlite")
    task,_=queue.enqueue(actor="alice",job_id=jid,stage="image",
        context_sha=approved["approval_sha"])
    monkeypatch.setattr(worker, "live_image_adapter",
                        lambda *_: pytest.fail("No image adapter/provider call permitted"))
    assert worker._run_locked(tmp_path, flow) == "LIVE_STAGE_HELD_FOR_RECONCILIATION"
    assert queue.read(task["id"])["state"]=="BILLING_UNKNOWN"
    assert queue.read(task["id"])["error_code"]=="PM_IMAGE_MULTICANDIDATE_SCOPE_NOT_APPROVED"
    with flow.cost.connect() as c:
        assert c.execute("select count(*) from attempts").fetchone()[0] == 0


@pytest.mark.parametrize("snapshot", [
    {"generation_mode": "composed", "image_size": "4:5", "candidate_count": 2},
    {"generation_mode": "batch", "image_size": "4:5"},
    {"generation_mode": "freeform"},
    {"generation_mode": "composed", "image_size": "1:1"},
])
def test_snapshot_gate_rejects_unknown_and_multi_image_contract(snapshot):
    with pytest.raises(LiveGateError):
        assert_single_image_scope(snapshot)


@pytest.mark.parametrize("count", (2, 3, 4))
def test_explicit_single_regeneration_refuses_unapproved_batch_then_one_qa_attempt(
    tmp_path, monkeypatch, count,
):
    from uuid import uuid4

    configure_qa(monkeypatch)
    app, codes = setup(tmp_path)
    with TestClient(app, client=("127.0.0.1", 12121)) as client:
        login(client, codes["alice"])
        jid = new_job(client)
        base = "/demo/api/live/jobs/" + jid
        qa = "/demo/api/qa/jobs/" + jid
        assert client.post(base + "/input", json={
            **sample_input(), "image_size": "9:16", "generation_mode": "freeform"
        }, headers=ORIGIN).status_code == 200
        reviewed = client.post(qa + "/text", headers=ORIGIN)
        assert reviewed.status_code == 200, reviewed.text
        text = reviewed.json()
        assert client.post(base + "/approve-copy", json={
            "expected_generation": text["generation"],
            "expected_review_sha": text["review_sha"]
        }, headers=ORIGIN).status_code == 200
        image = client.post(qa + "/prompt-image", headers=ORIGIN).json()
        assert image["state"] == "IMAGE_REVIEW_REQUIRED"
        assert client.post(base + "/reject-image", json={
            "image_sha": image["image_sha"]
        }, headers=ORIGIN).status_code == 200
        request = {"expected_image_sha": image["image_sha"],
                   "request_key": uuid4().hex}
        bad = client.post(qa + "/regenerate-image",
                          json={**request, "candidate_count": count}, headers=ORIGIN)
        assert bad.status_code == 422, bad.text
        with app.state.live_pipeline.state.db() as c:
            assert c.execute("select count(*) from live_image_attempts where job_id=?",
                             (jid,)).fetchone()[0] == 1
        next_image = client.post(qa + "/regenerate-image",
                                 json=request, headers=ORIGIN)
        assert next_image.status_code == 200, next_image.text
        next_image = next_image.json()
        assert next_image["image_attempt_version"] == 2
        assert next_image["state"] == "IMAGE_REVIEW_REQUIRED"
        assert next_image["image_sha"] != image["image_sha"]
        assert next_image["copy_sha"] == image["copy_sha"]
        assert next_image["review_sha"] == image["review_sha"]
        with app.state.live_pipeline.state.db() as c:
            assert c.execute("select count(*) from live_image_attempts where job_id=?",
                             (jid,)).fetchone()[0] == 2
        with app.state.live_pipeline.cost.connect() as c:
            assert c.execute("select count(*) from attempts").fetchone()[0] == 0


def test_openapi_exposes_no_multi_candidate_batch_or_gallery_post(tmp_path):
    app, _ = setup(tmp_path)
    routes = app.openapi()["paths"]
    image_posts = [
        path for path, methods in routes.items()
        if "post" in methods and path.startswith("/demo/api/")
        and any(word in path for word in ("image", "candidate", "batch", "gallery"))
    ]
    assert any(path.endswith("/queue-image") for path in image_posts)
    assert any(path.endswith("/regenerate-image") for path in image_posts)
    assert not any(word in path for path in image_posts
                   for word in ("/batch", "/candidates", "/gallery", "/variants"))
