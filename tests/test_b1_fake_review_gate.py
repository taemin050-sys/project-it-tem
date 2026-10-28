"""B1-R: opt-in REAL FastAPI copy approval wired to durable Fake reviewer.

All tests use isolated disk, no Text Owner code, model, API key, cloud or new HTTP
operation. B0 stays unchanged when enable_b1_fake_compliance=False.
"""
from __future__ import annotations

import copy
import json
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from src.serving.b1_fake_review import FakeComplianceGate, fake_report
from src.serving.job_store import transition_job
from src.serving.main import create_app


def png(rgb):
    out = BytesIO()
    Image.new("RGB", (64, 70), rgb).save(out, "PNG")
    return out.getvalue()


@pytest.fixture
def rig(tmp_path):
    app = create_app(tmp_path / "jobs", enable_b1_fake_compliance=True)
    with TestClient(app) as http:
        yield app, http, app.state.b1_fake_gate


def setup_job(rig, *, brand="라움", product="데일리 크림"):
    _, http, _ = rig
    response = http.post("/api/v1/jobs", files=[
        ("product_images", ("f1.png", png((20, 50, 80)), "image/png")),
        ("product_images", ("f2.png", png((25, 55, 85)), "image/png")),
    ])
    assert response.status_code == 201
    jid = response.json()["job_id"]
    assert http.post(f"/api/v1/jobs/{jid}/mock/plan",
                     json={"brand_name":brand,"product_name":product}).status_code == 200
    assert http.post(f"/api/v1/jobs/{jid}/mock/copy").status_code == 200
    return jid


def approval(rig, job, **body):
    _, http, _ = rig
    return http.post(f"/api/v1/jobs/{job}/approvals/copy", json={"approved":True, **body})


def ready(rig, job, *, pass_report=True, revision="mock-copy-r01", **context):
    _, _, gate = rig
    gen = gate.stage(job, revision=revision, **context)
    token, snapshot = gate.begin(job)
    record_id = gate.complete(job, token, fake_report(snapshot, passed=pass_report))
    return gen, record_id


def reason(response):
    assert response.status_code == 409, response.text
    return response.json()["detail"]["reason"]


def test_b0_default_still_11_endpoints_and_copy_boolean_approval(tmp_path):
    with TestClient(create_app(tmp_path / "default")) as http:
        assert len([
            (m, p) for p, paths in http.get("/openapi.json").json()["paths"].items()
            for m in paths if m in {"get","post"}
        ]) == 11
        job = setup_job((None,http,None))
        assert http.post(f"/api/v1/jobs/{job}/approvals/copy",
                         json={"approved": True}).status_code == 200


def test_optin_same_11_public_endpoints_no_review_management_http(rig):
    _, http, gate = rig
    api = http.get("/openapi.json").json()
    assert len([(p, m) for p, ms in api["paths"].items()
                for m in ms if m in {"post", "get"}]) == 11
    assert not any("/review" in p or "/ai/" in p for p in api["paths"])
    assert isinstance(gate, FakeComplianceGate)


def test_no_review_approval_failclosed_but_user_can_reject(rig):
    _, http, _ = rig
    j = setup_job(rig)
    assert reason(approval(rig, j)) == "MISSING_OR_INVALID_SERVER_REVIEW"
    assert http.get(f"/api/v1/jobs/{j}").json()["status"] == "COPY_REVIEW_REQUIRED"
    denied = http.post(f"/api/v1/jobs/{j}/approvals/copy", json={"approved":False})
    assert denied.status_code == 200
    assert denied.json()["status"] == "COPY_REJECTED"
    assert http.post(f"/api/v1/jobs/{j}/mock/image").status_code == 409


@pytest.mark.parametrize("value", ["yes", "true", 1, True])
def test_existing_pydantic_bool_coercion_does_not_bypass_server_gate(rig, value):
    _, http, _ = rig
    job = setup_job(rig)
    result = http.post(f"/api/v1/jobs/{job}/approvals/copy", json={"approved":value})
    assert result.status_code == 409
    assert http.get(f"/api/v1/jobs/{job}").json()["status"] == "COPY_REVIEW_REQUIRED"


def test_client_supplied_report_or_hash_rejected_422(rig):
    job = setup_job(rig)
    assert approval(rig, job, report={"passed":True}).status_code == 422
    assert approval(rig, job, review_record_id="untrusted").status_code == 422
    assert approval(rig, job, copy_sha256="caller-forgery").status_code == 422


def test_valid_trusted_fake_review_approves_and_unblocks_image(rig):
    _, http, _ = rig
    job = setup_job(rig)
    gen, record_id = ready(rig, job)
    assert gen == 1 and len(record_id) == 32
    result = approval(rig, job)
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "COPY_APPROVED"
    assert http.post(f"/api/v1/jobs/{job}/mock/image").status_code == 200
    assert "b1_fake_review" not in json.dumps(result.json())
    assert "source_review_token" not in json.dumps(http.get(f"/api/v1/jobs/{job}").json())


def test_failed_report_stored_but_cannot_approve_or_generate_image(rig):
    _, http, _ = rig
    job = setup_job(rig)
    ready(rig, job, pass_report=False)
    assert reason(approval(rig, job)) == "COMPLIANCE_BLOCKED"
    assert http.post(f"/api/v1/jobs/{job}/mock/image").status_code == 409


def test_missing_or_invalid_report_never_mints_review_record(rig):
    _, http, gate = rig
    job = setup_job(rig)
    gate.stage(job)
    token, _ = gate.begin(job)
    with pytest.raises(Exception, match="INVALID_COMPLIANCE_REPORT"):
        gate.complete(job, token, {"passed":"yes", "issues":[]})
    assert reason(approval(rig, job)) == "MISSING_TRUSTED_REVIEW_RECORD"
    with pytest.raises(Exception, match="UNTRUSTED_OR_REPLAYED_COMPLETION"):
        gate.complete(job, token, fake_report({"copy_output":{"ad_copy":{"headline":"dummy"}}}))


def test_duplicate_review_completion_cannot_replay(rig):
    _, _, gate = rig
    j = setup_job(rig)
    gate.stage(j)
    token, snapshot = gate.begin(j)
    gate.complete(j, token, fake_report(snapshot))
    with pytest.raises(Exception, match="UNTRUSTED_OR_REPLAYED_COMPLETION"):
        gate.complete(j, token, fake_report(snapshot))


def test_stage_idempotent_and_fingerprint_contains_real_asset_order(rig):
    _, _, gate = rig
    j = setup_job(rig)
    assert gate.stage(j) == 1
    token, snap = gate.begin(j)
    assert gate.stage(j) == 1
    assets = snap["review_context"]["additional_review_inputs"]["fake_consumed_assets"]
    assert [a["ordinal"] for a in assets] == [0, 1]
    assert [a["role"] for a in assets] == ["product", "product"]
    assert len({a["sha256"] for a in assets}) == 2
    assert gate.complete(j, token, fake_report(snap))
    assert approval(rig, j).status_code == 200


def test_completed_record_survives_process_restart_and_approves(tmp_path):
    root = tmp_path / "persist"
    first = create_app(root, enable_b1_fake_compliance=True)
    with TestClient(first) as http:
        rig = first, http, first.state.b1_fake_gate
        job = setup_job(rig)
        ready(rig, job)
    second = create_app(root, enable_b1_fake_compliance=True)
    with TestClient(second) as http:
        rig2 = second, http, second.state.b1_fake_gate
        assert approval(rig2, job).status_code == 200
        assert http.get(f"/api/v1/jobs/{job}").json()["status"] == "COPY_APPROVED"
    third = create_app(root, enable_b1_fake_compliance=True)
    with TestClient(third) as http:
        assert http.get(f"/api/v1/jobs/{job}").json()["status"] == "COPY_APPROVED"
        assert http.post(f"/api/v1/jobs/{job}/approvals/copy",
                         json={"approved":True}).status_code == 409


def test_revision_change_then_restore_invalidates_old_review(rig):
    app, http, gate = rig
    jid = setup_job(rig)
    g1, rid = ready(rig, jid, revision="r01")
    original = copy.deepcopy(app.state.job_store.get_job(jid)["copy_candidate"])
    mutated = {**original, "text":"카피의 의미가 변경된 초안"}
    transition_job(app.state.job_store, jid, expected_status="COPY_REVIEW_REQUIRED",
                   next_status="COPY_REVIEW_REQUIRED", updates={"copy_candidate":mutated})
    assert gate.stage(jid, revision="r02") == g1 + 1
    transition_job(app.state.job_store, jid, expected_status="COPY_REVIEW_REQUIRED",
                   next_status="COPY_REVIEW_REQUIRED", updates={"copy_candidate":original})
    assert gate.stage(jid, revision="r01") == g1 + 2
    assert reason(approval(rig, jid)) == "MISSING_TRUSTED_REVIEW_RECORD"
    # Even a copied old record ID cannot bypass generation.
    with app.state.job_store._lock:
        state = gate._read(jid)
        state["latest_record_id"] = rid
        gate._write(jid, state)
    assert reason(approval(rig, jid)) == "STALE_REVIEW_GENERATION"


def test_context_change_then_restore_invalidates_old_record(rig):
    app, _, gate = rig
    j = setup_job(rig)
    g1, rid = ready(rig, j, user_text="설명 A", extra={"vlm_consumed":{"product_type":"크림"}})
    assert gate.stage(j, user_text="설명 B", extra={"vlm_consumed":{"product_type":"크림"}}) == g1+1
    assert gate.stage(j, user_text="설명 A", extra={"vlm_consumed":{"product_type":"크림"}}) == g1+2
    with app.state.job_store._lock:
        data = gate._read(j)
        data["latest_record_id"] = rid
        gate._write(j, data)
    assert reason(approval(rig, j)) == "STALE_REVIEW_GENERATION"


def test_changed_copy_without_trusted_stage_never_approved(rig):
    app, http, _ = rig
    j = setup_job(rig)
    ready(rig, j)
    transition_job(app.state.job_store, j, expected_status="COPY_REVIEW_REQUIRED",
                   next_status="COPY_REVIEW_REQUIRED", updates={
                       "copy_candidate": {"text":"상태를 바꾼 새 복사본"},
                   })
    assert reason(approval(rig, j)) == "MISSING_TRUSTED_REVIEW_RECORD"
    assert http.get(f"/api/v1/jobs/{j}").json()["status"] == "COPY_REVIEW_REQUIRED"


def test_change_during_pending_review_rejects_completion(rig):
    _, http, gate = rig
    j = setup_job(rig)
    gate.stage(j, user_text="A")
    token, snap = gate.begin(j)
    gate.stage(j, user_text="B")
    with pytest.raises(Exception, match="UNTRUSTED_OR_REPLAYED_COMPLETION"):
        gate.complete(j, token, fake_report(snap))
    assert reason(approval(rig, j)) == "MISSING_TRUSTED_REVIEW_RECORD"


def test_report_tamper_and_provenance_tamper_failclosed(rig):
    app, _, gate = rig
    j = setup_job(rig)
    _, rid = ready(rig, j)
    with app.state.job_store._lock:
        state = gate._read(j)
        state["records"][rid]["report_json"] = json.dumps({"passed":True}, ensure_ascii=False)
        gate._write(j, state)
    assert reason(approval(rig, j)) == "TAMPERED_COMPLIANCE_REPORT"
    with app.state.job_store._lock:
        state = gate._read(j)
        state["records"][rid]["report_json"] = json.dumps(fake_report(
            json.loads(state["snapshot_json"])), ensure_ascii=False, sort_keys=True,
            separators=(",", ":"))
        from hashlib import sha256
        state["records"][rid]["report_sha256"] = sha256(
            state["records"][rid]["report_json"].encode("utf-8")).hexdigest()
        state["runs"].clear()
        gate._write(j, state)
    assert reason(approval(rig, j)) == "UNTRUSTED_REVIEW_PROVENANCE"


def test_reviewer_record_cannot_be_reused_from_another_job(rig):
    app, _, gate = rig
    j1 = setup_job(rig)
    j2 = setup_job(rig)
    _, rid = ready(rig, j1)
    gate.stage(j2)
    with app.state.job_store._lock:
        from_job1 = gate._read(j1)
        to_job2 = gate._read(j2)
        to_job2["records"][rid] = from_job1["records"][rid]
        to_job2["latest_record_id"] = rid
        gate._write(j2, to_job2)
    assert reason(approval(rig, j2)) == "UNTRUSTED_REVIEW_PROVENANCE"


def test_corrupted_record_fails_closed_and_is_not_reinitialized(rig):
    app, _, gate = rig
    j = setup_job(rig)
    ready(rig, j)
    path = gate._file(j)
    path.write_text("{invalid", encoding="utf-8")
    assert reason(approval(rig, j)) == "MISSING_OR_INVALID_SERVER_REVIEW"
    with pytest.raises(Exception, match="MISSING_OR_INVALID_SERVER_REVIEW"):
        gate.stage(j)
    assert path.read_text() == "{invalid"


def test_concurrent_http_approvals_exactly_one_commits(rig):
    _, http, _ = rig
    j = setup_job(rig)
    ready(rig, j)
    with ThreadPoolExecutor(max_workers=6) as executor:
        responses = list(executor.map(lambda _: approval(rig, j).status_code, range(6)))
    assert responses.count(200) == 1
    assert responses.count(409) == 5
    assert http.get(f"/api/v1/jobs/{j}").json()["status"] == "COPY_APPROVED"


def test_stage_vs_approve_same_process_race_never_approves_unreviewed_context(rig):
    app, http, gate = rig
    j = setup_job(rig)
    ready(rig, j)
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(lambda: approval(rig, j).status_code)
        b = pool.submit(lambda: (gate.stage(j, user_text="new review input"), "staged"))
        try:
            changed = b.result()
        except Exception as exc:
            changed = type(exc).__name__
        response = a.result()
    assert response in {200, 409}
    assert http.get(f"/api/v1/jobs/{j}").json()["status"] in {
        "COPY_REVIEW_REQUIRED", "COPY_APPROVED",
    }
    if response == 200:
        assert changed != (2, "staged"), "must not stage unreviewed input after approval"
    else:
        assert reason(approval(rig, j)) in {
            "MISSING_TRUSTED_REVIEW_RECORD", "STALE_REVIEW_GENERATION",
        }


def test_fake_review_has_no_billing_or_external_http_routes(rig):
    app, http, gate = rig
    j = setup_job(rig)
    ready(rig, j)
    assert not hasattr(app.state, "openai_client")
    assert not hasattr(app.state, "text_provider")
    assert not any("/ai/" in p for p in http.get("/openapi.json").json()["paths"])


def test_copy_change_restore_without_intermediate_stage_revokes_review(rig):
    """P0-04R: actual trusted mutation events, not caller restaging, own epoch."""
    app, http, gate = rig
    j = setup_job(rig)
    g1, rid = ready(rig, j)
    original = copy.deepcopy(app.state.job_store.get_job(j)["copy_candidate"])
    changed = {**original, "text":"기존과 다른 초안"}
    transition_job(app.state.job_store, j, expected_status="COPY_REVIEW_REQUIRED",
                   next_status="COPY_REVIEW_REQUIRED", updates={"copy_candidate":changed})
    transition_job(app.state.job_store, j, expected_status="COPY_REVIEW_REQUIRED",
                   next_status="COPY_REVIEW_REQUIRED", updates={"copy_candidate":original})
    state = gate._read(j)
    assert state["generation"] == g1 + 2
    assert gate._snapshot(app.state.job_store.get_job(j), state) == json.loads(state["snapshot_json"])
    assert state["dirty"] is True
    assert reason(approval(rig, j)) == "MISSING_TRUSTED_REVIEW_RECORD"
    with app.state.job_store._lock:
        state["latest_record_id"] = rid  # simulated stale trusted record reuse
        gate._write(j, state)
    assert reason(approval(rig, j)) == "STALE_REVIEW_GENERATION"


def test_after_unreviewed_copy_change_fresh_stage_review_required(rig):
    app, http, gate = rig
    j = setup_job(rig)
    ready(rig, j, revision="r01")
    original = copy.deepcopy(app.state.job_store.get_job(j)["copy_candidate"])
    changed = {**original, "text":"검수가 다시 필요한 초안"}
    transition_job(app.state.job_store, j, expected_status="COPY_REVIEW_REQUIRED",
                   next_status="COPY_REVIEW_REQUIRED", updates={"copy_candidate":changed})
    assert reason(approval(rig, j)) == "MISSING_TRUSTED_REVIEW_RECORD"
    assert gate.stage(j, revision="r02") == 2
    token, snap = gate.begin(j)
    gate.complete(j, token, fake_report(snap))
    assert approval(rig, j).status_code == 200


def test_mutation_after_approval_is_blocked_by_observer(rig):
    app, http, _ = rig
    j = setup_job(rig)
    ready(rig, j)
    assert approval(rig, j).status_code == 200
    with pytest.raises(Exception, match="APPROVED_INPUT_IMMUTABLE"):
        transition_job(app.state.job_store, j, expected_status="COPY_APPROVED",
                       next_status="COPY_APPROVED",
                       updates={"copy_candidate": {"text":"승인 후 검수 없이 변경"}})
    assert http.get(f"/api/v1/jobs/{j}").json()["status"] == "COPY_APPROVED"


def test_unrelated_metadata_does_not_invalidate_review(rig):
    app, _, gate = rig
    j = setup_job(rig)
    gen, _ = ready(rig, j)
    transition_job(app.state.job_store, j, expected_status="COPY_REVIEW_REQUIRED",
                   next_status="COPY_REVIEW_REQUIRED", updates={"unrelated_qa_note":"not reviewer input"})
    assert gate._read(j)["generation"] == gen
    assert approval(rig, j).status_code == 200


def test_failed_job_ledger_write_cannot_publish_approval(rig, monkeypatch):
    """A failed atomic Job ledger replace must never expose COPY_APPROVED."""
    import os
    from src.serving import job_store
    app, http, gate = rig
    j = setup_job(rig)
    ready(rig, j)
    original_replace = os.replace

    def fail_job_commit(src, dst):
        if str(dst).endswith("/job.json"):
            raise OSError("simulated job.json commit failure")
        return original_replace(src, dst)

    with monkeypatch.context() as patch:
        patch.setattr(job_store.os, "replace", fail_job_commit)
        with pytest.raises(OSError, match="simulated job.json commit failure"):
            approval(rig, j)
    assert http.get(f"/api/v1/jobs/{j}").json()["status"] == "COPY_REVIEW_REQUIRED"
    assert approval(rig, j).status_code == 200


def test_fake_review_sidecar_file_mode_and_not_public(rig):
    app, http, gate = rig
    job = setup_job(rig)
    ready(rig, job)
    f = gate._file(job)
    assert f.is_file() and not f.is_symlink()
    assert f.stat().st_mode & 0o077 == 0
    assert http.get(f"/api/v1/jobs/{job}/artifacts/b1_fake_review").status_code == 404
    assert f.name not in http.get(f"/api/v1/jobs/{job}").text


def test_pending_token_becomes_invalid_after_copy_mutation(rig):
    app, _, gate = rig
    j = setup_job(rig)
    gate.stage(j)
    token, snap = gate.begin(j)
    transition_job(app.state.job_store, j, expected_status="COPY_REVIEW_REQUIRED",
                   next_status="COPY_REVIEW_REQUIRED",
                   updates={"copy_candidate":{"text":"new unreviewed copy"}})
    with pytest.raises(Exception, match="UNTRUSTED_OR_REPLAYED_COMPLETION"):
        gate.complete(j, token, fake_report(snap))
    assert reason(approval(rig, j)) == "MISSING_TRUSTED_REVIEW_RECORD"


def test_fake_review_rejects_contradictory_passed_and_risk_level(rig):
    _, _, gate = rig
    j = setup_job(rig)
    gate.stage(j)
    token, snap = gate.begin(j)
    invalid = fake_report(snap, passed=False)
    invalid["passed"] = True  # risk_level=위반 의심 contradicts passed=true
    with pytest.raises(Exception, match="INVALID_COMPLIANCE_REPORT"):
        gate.complete(j, token, invalid)
    assert reason(approval(rig, j)) == "MISSING_TRUSTED_REVIEW_RECORD"


def test_real_os_subprocess_completed_review_is_durable_for_http_approval(rig):
    """Review is persisted by a separate Python interpreter, not shared memory."""
    import subprocess
    import sys
    from pathlib import Path
    app, http, _ = rig
    j = setup_job(rig)
    root = str(app.state.job_store.root)
    script = """
import sys
from pathlib import Path
from src.serving.main import create_app
from src.serving.b1_fake_review import fake_report
app=create_app(Path(sys.argv[1]), enable_b1_fake_compliance=True)
gate=app.state.b1_fake_gate
job=sys.argv[2]
assert gate.stage(job)==1
token,snapshot=gate.begin(job)
record=gate.complete(job,token,fake_report(snapshot))
assert len(record)==32
"""
    work_dir = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-c", script, root, j],
        cwd=work_dir, capture_output=True, text=True, check=False, timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert approval(rig, j).status_code == 200
    assert http.get(f"/api/v1/jobs/{j}").json()["status"] == "COPY_APPROVED"


@pytest.mark.parametrize("mutation", ["missing_records", "missing_report_sha", "invalid_generation"])
def test_broken_persisted_record_schema_yields_safe_409_not_500(rig, mutation):
    app, _, gate = rig
    j = setup_job(rig)
    _, rid = ready(rig, j)
    with app.state.job_store._lock:
        state = gate._read(j)
        if mutation == "missing_records":
            del state["records"]
        elif mutation == "missing_report_sha":
            del state["records"][rid]["report_sha256"]
        else:
            state["generation"] = "invalid-string"
        gate._write(j, state)
    assert reason(approval(rig, j)) == "INVALID_SERVER_REVIEW_RECORD"

# B1R-P1-01: malformed persisted records MUST return HTTP 409, NEVER 500.
# Each case starts from a real server-completed Fake review. Mutation happens
# directly to the private on-disk sidecar, then the public approval API is used.
@pytest.mark.parametrize("corruption", [
    "report_json_list", "report_json_dict", "report_json_null",
    "report_json_number", "report_json_invalid_text", "report_json_array_text",
    "report_sha256_list", "report_sha256_missing", "report_sha256_number",
    "report_sha256_invalid_hex", "latest_record_id_list",
    "latest_record_id_object", "latest_record_id_invalid_id",
    "latest_record_id_missing", "pending_list", "pending_number",
    "pending_missing", "pending_partial", "pending_bad_generation",
    "pending_bad_snapshot", "pending_bad_hash",
    "runs_list", "runs_missing", "runs_not_a_list", "runs_short_list",
    "runs_bad_record_id", "runs_bad_hash", "runs_bad_generation",
    "runs_bad_token_key", "records_not_a_dict", "records_missing_field",
    "records_bad_token", "records_bad_generation", "records_bad_snapshot",
    "records_bad_model_version", "root_bad_product_facts", "root_bad_extra",
    "root_bad_snapshot", "root_bad_dirty",
    "report_json_nan_text", "report_json_float_text",
    "root_bad_fact_float", "root_bad_extra_large_int",
    "root_bad_user_text_type", "pending_bad_json_text",
    "runs_bad_nested_hash", "records_wrong_record_id",
])
def test_b1r_p1_malformed_disk_record_returns_safe_409_without_job_mutation(rig, corruption):
    """No internal exception may escape as HTTP 500; no copy approval bypass."""
    app, http, gate = rig
    job = setup_job(rig)
    _, review_id = ready(rig, job)
    good_job = http.get(f"/api/v1/jobs/{job}").json()
    assert good_job["status"] == "COPY_REVIEW_REQUIRED"
    with app.state.job_store._lock:
        disk = gate._read(job)
        review = disk["records"][review_id]
        token = review["source_review_token"]
        mutations = {
            "report_json_list": lambda: review.__setitem__("report_json", []),
            "report_json_dict": lambda: review.__setitem__("report_json", {"passed": True}),
            "report_json_null": lambda: review.__setitem__("report_json", None),
            "report_json_number": lambda: review.__setitem__("report_json", 7),
            "report_json_invalid_text": lambda: review.__setitem__("report_json", "{malformed"),
            "report_json_array_text": lambda: review.__setitem__("report_json", "[]"),
            "report_sha256_list": lambda: review.__setitem__("report_sha256", []),
            "report_sha256_missing": lambda: review.pop("report_sha256"),
            "report_sha256_number": lambda: review.__setitem__("report_sha256", 44),
            "report_sha256_invalid_hex": lambda: review.__setitem__("report_sha256", "bad"),
            "latest_record_id_list": lambda: disk.__setitem__("latest_record_id", []),
            "latest_record_id_object": lambda: disk.__setitem__("latest_record_id", {}),
            "latest_record_id_invalid_id": lambda: disk.__setitem__("latest_record_id", "wrong"),
            "latest_record_id_missing": lambda: disk.pop("latest_record_id"),
            "pending_list": lambda: disk.__setitem__("pending", []),
            "pending_number": lambda: disk.__setitem__("pending", 3),
            "pending_missing": lambda: disk.pop("pending"),
            "pending_partial": lambda: disk.__setitem__("pending", {"token": token}),
            "pending_bad_generation": lambda: disk.__setitem__("pending", {
                "token": token, "generation": True, "snapshot_json": disk["snapshot_json"],
                "input_sha256": review["review_input_sha256"],
            }),
            "pending_bad_snapshot": lambda: disk.__setitem__("pending", {
                "token": token, "generation": 1, "snapshot_json": [],
                "input_sha256": review["review_input_sha256"],
            }),
            "pending_bad_hash": lambda: disk.__setitem__("pending", {
                "token": token, "generation": 1, "snapshot_json": disk["snapshot_json"],
                "input_sha256": [],
            }),
            "runs_list": lambda: disk.__setitem__("runs", []),
            "runs_missing": lambda: disk.pop("runs"),
            "runs_not_a_list": lambda: disk["runs"].__setitem__(token, {}),
            "runs_short_list": lambda: disk["runs"].__setitem__(token, [review_id]),
            "runs_bad_record_id": lambda: disk["runs"].__setitem__(
                token, [[], review["review_input_sha256"], 1],
            ),
            "runs_bad_hash": lambda: disk["runs"].__setitem__(token, [review_id, 1, 1]),
            "runs_bad_generation": lambda: disk["runs"].__setitem__(
                token, [review_id, review["review_input_sha256"], False],
            ),
            "runs_bad_token_key": lambda: disk["runs"].__setitem__(
                "not-an-id", [review_id, review["review_input_sha256"], 1],
            ),
            "records_not_a_dict": lambda: disk.__setitem__("records", []),
            "records_missing_field": lambda: review.pop("report_json"),
            "records_bad_token": lambda: review.__setitem__("source_review_token", []),
            "records_bad_generation": lambda: review.__setitem__("reviewed_job_generation", 1.5),
            "records_bad_snapshot": lambda: review.__setitem__("reviewed_snapshot_json", []),
            "records_bad_model_version": lambda: review.__setitem__("model_version", {}),
            "root_bad_product_facts": lambda: disk.__setitem__("product_facts", []),
            "root_bad_extra": lambda: disk.__setitem__("extra", 7),
            "root_bad_snapshot": lambda: disk.__setitem__("snapshot_json", []),
            "root_bad_dirty": lambda: disk.__setitem__("dirty", "False"),
            "report_json_nan_text": lambda: review.__setitem__(
                "report_json", '{"passed":NaN}',
            ),
            "report_json_float_text": lambda: review.__setitem__(
                "report_json", '{"passed":1.2}',
            ),
            "root_bad_fact_float": lambda: disk["product_facts"].update({
                "fake_fact": {"numeric": 1.2},
            }),
            "root_bad_extra_large_int": lambda: disk["extra"].update({
                "unsafe_integer": 2 ** 60,
            }),
            "root_bad_user_text_type": lambda: disk.__setitem__("user_text", []),
            "pending_bad_json_text": lambda: disk.__setitem__("pending", {
                "token": token, "generation": 1, "snapshot_json": "[1,2]",
                "input_sha256": review["review_input_sha256"],
            }),
            "runs_bad_nested_hash": lambda: disk["runs"].__setitem__(
                token, [review_id, [], 1],
            ),
            "records_wrong_record_id": lambda: review.__setitem__(
                "review_record_id", "0" * 32,
            ),
        }
        mutations[corruption]()
        # Trusted internal test hook permits malformed on-disk JSON.
        gate._write(job, disk)

    from fastapi.testclient import TestClient
    with TestClient(app, raise_server_exceptions=False) as network:
        response = network.post(
            f"/api/v1/jobs/{job}/approvals/copy", json={"approved": True},
        )
        observed = network.get(f"/api/v1/jobs/{job}")
        assert response.status_code == 409, (
            f"{corruption}: expected fail-closed HTTP 409, received "
            f"{response.status_code} {response.text[:120]}"
        )
        assert response.json()["detail"]["error"] == "B1_FAKE_COMPLIANCE_BLOCKED"
        assert response.json()["detail"]["reason"] == "INVALID_SERVER_REVIEW_RECORD"
        assert observed.status_code == 200
        assert observed.json() == good_job
        assert observed.json()["status"] == "COPY_REVIEW_REQUIRED"
        assert observed.json().get("copy_approved") is not True



def test_b1r_p1_valid_empty_user_text_remains_backward_compatible(rig):
    """The proposed review contract allows an explicitly empty user_text."""
    _, http, gate = rig
    job = setup_job(rig)
    assert gate.stage(job, user_text="") == 1
    token, snapshot = gate.begin(job)
    gate.complete(job, token, fake_report(snapshot))
    assert approval(rig, job).status_code == 200
    assert http.get(f"/api/v1/jobs/{job}").json()["status"] == "COPY_APPROVED"
