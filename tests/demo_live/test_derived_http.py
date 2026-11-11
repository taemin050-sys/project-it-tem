"""Signed HTTP protected-product flow over a disposable OFFLINE_FIXTURE Job.

These checks do not assert a real PM review, a real label ground truth, or any
Provider success. Network Provider constructors are blocked and all rendering
is credential-free local work over explicitly migrated sandbox state.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from demo_staging.app import make_demo_app
from demo_staging.live import pipeline, worker
from demo_staging.live.derived_store import migrate_derived_schema
from demo_staging.live.derived_worker import run_once
from src.image_generation.backend_adapter import BackendGeneratedImage
from tests.demo_live.test_live_contracts import sample_input
from tests.demo_live.test_pipeline import FakeOwner, png
from tests.demo_staging.test_bp18_ux_p1_sso_only import env as signed_env, sign


ACTOR = "a_test_pm"
OTHER_ACTOR = "a_test_fe"
HOST = "my-tailnet.example.ts.net:10500"
REPO = Path(__file__).resolve().parents[2]
FONT = REPO / "app/node_modules/pretendard/dist/public/variable/PretendardVariable.ttf"
LICENSE = REPO / "app/node_modules/pretendard/dist/LICENSE.txt"


def request(client, key, method, path, *, actor=ACTOR, origin=True, **kwargs):
    headers = sign(key, actor, method=method, target=path, host=HOST)
    if origin:
        headers["Origin"] = f"https://{HOST}"
    headers.update(kwargs.pop("headers", {}))
    return client.request(method, path, headers=headers, **kwargs)


def assert_status(response, status):
    assert response.status_code == status, response.text
    return response.json()


@pytest.fixture
def runtime(signed_env, monkeypatch):
    tmp, dist, registry, key, _ = signed_env
    root = tmp / "derived-runtime"
    authority = tmp / "derived-authority.json"
    authority.write_text(json.dumps({"schema": "bp18-derived-authority-v1", "revision": 1,
        "business_roles": {ACTOR: "owner", OTHER_ACTOR: "pm"}, "delegations": []}))
    authority.chmod(0o600)
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY",
                 "CREDENTIALS_DIRECTORY", "IT_TEM_BP18_F11_ENABLED", "IT_TEM_BP18_F09_REQUIRED",
                 "IT_TEM_BP18_REVIEW_POLICY_REQUIRED", "IT_TEM_REVIEW_POLICY_VERSION",
                 "IT_TEM_REVIEW_POLICY_SHA"):
        monkeypatch.delenv(name, raising=False)
    for name, value in {"IT_TEM_DERIVED_ENABLED": "YES", "IT_TEM_DERIVED_AUTHORITY_FILE": str(authority),
                        "IT_TEM_DERIVED_ROOT": str(root / "protected"), "IT_TEM_DERIVED_FONT": str(FONT),
                        "IT_TEM_DERIVED_FONT_LICENSE": str(LICENSE),
                        "IT_TEM_DERIVED_SOURCE_TREE_SHA": "1" * 40}.items():
        monkeypatch.setenv(name, value)

    def no_provider(*_args, **_kwargs):
        pytest.fail("This signed HTTP fixture must not initialize a Provider")

    monkeypatch.setattr(pipeline, "OfficialTextProvider", no_provider)
    monkeypatch.setattr(worker, "live_image_adapter", no_provider)
    app = make_demo_app(root, registry, dist, secure_cookie=True, code_sha="1" * 40)
    with TestClient(app, base_url=f"https://{HOST}") as client:
        uploaded = assert_status(request(client, key, "POST", "/api/v1/jobs", files=[
            ("product_images", ("original-a.png", png((120, 130, 140)), "image/png")),
            ("product_images", ("original-b.png", png((150, 160, 170)), "image/png")),
        ]), 201)
        job = uploaded["job_id"]
        flow = app.state.live_pipeline
        assert app.state.demo_ledger.owns(ACTOR, job)
        flow.prepare(ACTOR, job, sample_input())
        owner = FakeOwner()
        reviewed = flow.text(ACTOR, job, owner, offline=True)
        flow.state.approve_copy(ACTOR, job, reviewed["generation"], reviewed["review_sha"])
        prompt = flow.prompt(ACTOR, job, owner, offline=True)
        raw = png((224, 233, 239), size=(1152, 1440))
        flow.accept_image_result(ACTOR, job, BackendGeneratedImage(
            image_bytes=raw, mime_type="image/png", width=1152, height=1440,
            sha256=sha256(raw).hexdigest(), job_id=job, copy_revision=prompt["generation"],
            copy_hash=prompt["copy_sha"], mock=True,
            receipt={"mode": "OFFLINE_MOCK_TRANSPORT", "provider_calls": 0}), offline=True)
        yield {"app": app, "client": client, "key": key, "job": job, "flow": flow,
               "root": root, "base": f"/demo/api/live/jobs/{job}/derived", "authority": authority}


def migrated(runtime):
    migrate_derived_schema(runtime["flow"].state.filename)
    return runtime


def call(runtime, method, suffix="", **kwargs):
    return request(runtime["client"], runtime["key"], method, runtime["base"] + suffix, **kwargs)


def admission_body(snapshot):
    proposal = snapshot["proposals"][0]
    return {"proposal_id": proposal["proposal_id"], "expected_recipe_sha": proposal["recipe_sha"],
            "expected_context_sha": snapshot["context_sha"], "expected_revision": snapshot["revision"],
            "acknowledge_source": True}


def prepare(runtime):
    snapshot = assert_status(call(runtime, "GET"), 200)
    admitted = assert_status(call(runtime, "POST", "/recipes/admit", json=admission_body(snapshot)), 200)
    body = {"admission_sha": admitted["admission_sha"], "expected_recipe_sha": admitted["recipe_sha"],
            "expected_context_sha": admitted["context_sha"], "idempotency_key": "a" * 64}
    row = assert_status(call(runtime, "POST", "/renders", json=body), 202)
    return row, body


def render_preview(runtime):
    row, _ = prepare(runtime)
    result = run_once(runtime["app"].state.derived_service, worker_id="signed-http-offline")
    assert result["state"] == "REVIEW_REQUIRED", result
    return assert_status(call(runtime, "GET", "/renders/" + row["derived_id"]), 200)


def review_body(runtime, row, *, truth=True):
    copy = json.loads(runtime["flow"].state.get(ACTOR, runtime["job"])["copy_json"])["ad_copy"]
    checks = {name: True for name in ("source_pixels_preserved", "edges_acceptable", "no_duplicate_product",
        "no_ghost_product", "no_copy_occlusion", "cta_policy_matches", "mobile_readable")}
    checks.update(label_ground_truth_confirmed=truth, observed_copy=copy)
    return {"expected_revision": row["revision"], "expected_preview_sha": row["preview_sha"],
            "expected_recipe_sha": row["recipe_sha"], "expected_context_sha": row["context_sha"],
            "approve": True, "visual_review": checks}


def test_signed_full_local_flow_downloads_exact_sha_and_keeps_raw_and_cost(runtime):
    migrated(runtime)
    flow, job = runtime["flow"], runtime["job"]
    raw_before = flow.state.get(ACTOR, job)
    original_files = {p.name: p.read_bytes() for p in (flow.root / "outputs" / job).iterdir() if p.is_file()}
    with flow.cost.connect() as c:
        costs_before = c.execute("SELECT * FROM attempts ORDER BY rowid").fetchall()
    row, body = prepare(runtime)
    assert row["state"] == "QUEUED"
    replay = assert_status(call(runtime, "POST", "/renders", json=body), 202)
    assert replay["derived_id"] == row["derived_id"]
    assert run_once(runtime["app"].state.derived_service, worker_id="signed-http-offline")["state"] == "REVIEW_REQUIRED"
    row = assert_status(call(runtime, "GET", "/renders/" + row["derived_id"]), 200)
    assert row["approval_sha"] is None and row["final_sha"] is None
    preview = request(runtime["client"], runtime["key"], "GET", row["artifacts"]["preview"])
    assert preview.status_code == 200, preview.text
    assert sha256(preview.content).hexdigest() == row["preview_sha"]
    with Image.open(BytesIO(preview.content)) as image:
        assert image.size == (1080, 1350)
    endpoint = "/renders/" + row["derived_id"]
    reviewed = assert_status(call(runtime, "POST", endpoint + "/decision", json=review_body(runtime, row)), 200)
    final_body = {"expected_revision": reviewed["revision"], "expected_approval_sha": reviewed["approval_sha"],
                  "expected_preview_sha": reviewed["preview_sha"]}
    final = assert_status(call(runtime, "POST", endpoint + "/finalize", json=final_body), 200)
    assert final["state"] == "COMPLETED" and final["final_sha"] == row["preview_sha"]
    saved = {}
    for kind in ("final", "caption", "receipt"):
        response = request(runtime["client"], runtime["key"], "GET", final["artifacts"][kind])
        assert response.status_code == 200, response.text
        assert sha256(response.content).hexdigest() == final[kind + "_sha"]
        assert "attachment;" in response.headers["content-disposition"]
        assert response.headers["x-it-tem-provenance"] == "DERIVED_PROTECTED_PRODUCT"
        saved[kind] = response.content
    assert saved["final"] == preview.content
    saved["caption"].decode("utf-8")
    receipt = json.loads(saved["receipt"])
    assert receipt["provider_calls"] == 0 and receipt["actual_provider_usd"] is None
    assert receipt["billing_status"] == "USD_UNRECONCILED"
    assert receipt["raw_provider_reference"]["mode"] == "OFFLINE_FIXTURE"
    selected = assert_status(call(runtime, "POST", "/selection", json={"derived_id": final["derived_id"],
        "expected_final_sha": final["final_sha"], "expected_approval_sha": final["approval_sha"]}), 200)
    assert selected["selected_derived_id"] == final["derived_id"]
    assert flow.state.get(ACTOR, job) == raw_before
    assert {p.name: p.read_bytes() for p in (flow.root / "outputs" / job).iterdir() if p.is_file()} == original_files
    with flow.cost.connect() as c:
        assert c.execute("SELECT * FROM attempts ORDER BY rowid").fetchall() == costs_before
    assert run_once(runtime["app"].state.derived_service, worker_id="empty-queue") is None


def test_signed_authority_and_origin_fail_closed(runtime):
    migrated(runtime)
    assert runtime["client"].get(runtime["base"]).status_code == 401
    assert call(runtime, "GET", actor=OTHER_ACTOR).status_code == 404
    snapshot = assert_status(call(runtime, "GET"), 200)
    body = admission_body(snapshot)
    assert call(runtime, "POST", "/recipes/admit", json=body, actor=OTHER_ACTOR).status_code == 404
    assert call(runtime, "POST", "/recipes/admit", json=body, origin=False).status_code == 403
    assert call(runtime, "POST", "/recipes/admit", json=body,
                headers={"Origin": "https://different.example"}).status_code == 403
    policy = json.loads(runtime["authority"].read_text())
    policy["business_roles"] = {}
    policy["revision"] += 1
    runtime["authority"].write_text(json.dumps(policy))
    read_only = assert_status(call(runtime, "GET"), 200)
    assert not read_only["can_admit"] and not read_only["can_review"]
    assert call(runtime, "POST", "/recipes/admit", json=admission_body(read_only)).status_code == 403


def test_admission_context_revision_rights_and_unknown_fields_fail_closed(runtime):
    migrated(runtime)
    body = admission_body(assert_status(call(runtime, "GET"), 200))
    for changed in ({"expected_context_sha": "0" * 64}, {"expected_recipe_sha": "0" * 64},
                    {"expected_revision": body["expected_revision"] + 1}, {"acknowledge_source": False}):
        assert call(runtime, "POST", "/recipes/admit", json={**body, **changed}).status_code == 409
    assert call(runtime, "POST", "/recipes/admit", json={**body, "actor": OTHER_ACTOR}).status_code == 422
    assert call(runtime, "POST", "/recipes/admit", json={**body, "expected_revision": True}).status_code == 422
    assert assert_status(call(runtime, "GET"), 200)["renders"] == []


@pytest.mark.parametrize("suffix,content", [
    ("/recipes/admit", '{"proposal_id":"a","proposal_id":"b"}'),
    ("/recipes/admit", '{"expected_revision":NaN}'),
    ("/renders", '{"expected_revision":1,"expected_revision":2}'),
    ("/renders/" + "a" * 32 + "/decision", '{"visual_review":{"approve":true,"approve":false}}'),
])
def test_duplicate_and_nonfinite_json_are_rejected(runtime, suffix, content):
    migrated(runtime)
    response = call(runtime, "POST", suffix, content=content, headers={"Content-Type": "application/json"})
    assert response.status_code == 422, response.text
    assert response.json()["detail"] == "DERIVED_JSON_INVALID"


def test_review_requires_all_checks_exact_copy_and_current_preview_cas(runtime):
    migrated(runtime)
    row = render_preview(runtime)
    endpoint = "/renders/" + row["derived_id"]
    assert call(runtime, "POST", endpoint + "/decision", json=review_body(runtime, row, truth=False)).status_code == 409
    wrong_copy = review_body(runtime, row)
    wrong_copy["visual_review"]["observed_copy"]["headline"] += " 변조"
    assert call(runtime, "POST", endpoint + "/decision", json=wrong_copy).status_code == 409
    for changed in ({"expected_revision": row["revision"] + 1}, {"expected_preview_sha": "0" * 64},
                    {"expected_recipe_sha": "0" * 64}, {"expected_context_sha": "0" * 64}):
        assert call(runtime, "POST", endpoint + "/decision", json={**review_body(runtime, row), **changed}).status_code == 409
    final = call(runtime, "POST", endpoint + "/finalize", json={"expected_revision": row["revision"],
        "expected_approval_sha": "0" * 64, "expected_preview_sha": row["preview_sha"]})
    assert final.status_code == 409
    current = assert_status(call(runtime, "GET", endpoint), 200)
    assert current["state"] == "REVIEW_REQUIRED" and current["approval_sha"] is None
    assert call(runtime, "GET", endpoint + "/artifacts/preview?sha256=" + "0" * 64).status_code == 409
    assert call(runtime, "GET", endpoint + "/artifacts/final?sha256=" + row["preview_sha"]).status_code == 409
    assert call(runtime, "GET", endpoint, actor=OTHER_ACTOR).status_code == 404
    assert call(runtime, "GET", "/renders/" + "0" * 32).status_code == 404


def test_uploaded_mask_and_configured_recipe_survive_listing_refresh(runtime):
    migrated(runtime)
    snapshot = assert_status(call(runtime, "GET"), 200)
    source = snapshot["source_assets"][1]
    mask = BytesIO()
    Image.new("L", (source["width"], source["height"]), 255).save(mask, "PNG")
    mask_ref = assert_status(call(runtime, "POST", "/assets", files={"file": ("mask.png", mask.getvalue(), "image/png")},
        data={"kind": "product_mask"}), 200)
    assert mask_ref["sha256"] == sha256(mask.getvalue()).hexdigest()
    proposal = assert_status(call(runtime, "POST", "/proposals", json={"source_asset_id": source["asset_id"],
        "mask_ref": mask_ref, "model_regions": [], "copy_exclusions": [], "acknowledge_regions": False}), 200)
    refreshed = assert_status(call(runtime, "GET"), 200)
    assert proposal in refreshed["proposals"]
    assert proposal["source_asset_id"] == source["asset_id"]
    assert proposal["proposal_id"] != snapshot["proposals"][0]["proposal_id"]
    invalid_upload = call(runtime, "POST", "/assets", files={"file": ("mask.png", mask.getvalue(), "image/png")},
        data={"kind": "source_photo"})
    assert invalid_upload.status_code == 422


def test_disabled_capability_does_not_admit_or_create_derived_schema(runtime, monkeypatch):
    monkeypatch.setenv("IT_TEM_DERIVED_ENABLED", "NO")
    snapshot = assert_status(call(runtime, "GET"), 200)
    assert not snapshot["available"] and snapshot["proposals"] == []
    valid = {"proposal_id": "a" * 64, "expected_recipe_sha": "a" * 64, "expected_context_sha": "b" * 64,
             "expected_revision": 0, "acknowledge_source": True}
    assert call(runtime, "POST", "/recipes/admit", json=valid).status_code == 404
    assert call(runtime, "GET", actor=OTHER_ACTOR).status_code == 404
    with sqlite3.connect(runtime["flow"].state.filename) as c:
        assert not c.execute("SELECT name FROM sqlite_master WHERE name LIKE 'live_derived_%'").fetchall()


def test_missing_explicit_migration_fails_closed_without_schema_writes(runtime):
    database = runtime["flow"].state.filename
    with sqlite3.connect(database) as c:
        before = c.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name").fetchall()
    response = call(runtime, "GET")
    assert response.status_code == 503, response.text
    assert response.json()["detail"] == "DERIVED_SCHEMA_NOT_MIGRATED"
    with sqlite3.connect(database) as c:
        assert c.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name").fetchall() == before
