"""Signed Live Dual and the real Owner adapter over an in-process mock transport."""
from __future__ import annotations

import base64
from dataclasses import replace
from email import policy
from email.parser import BytesParser
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path

import httpx
from PIL import Image
import pytest
from fastapi.testclient import TestClient

from demo_staging.app import make_demo_app
from demo_staging.live import http_api, pipeline, worker
from demo_staging.live.contracts import LiveGateError, digest
from src.image_generation.ad_resize import resize_ad_png
from src.image_generation.api_image_processor import ExternalImageProcessor
from src.image_generation.assets import LocalAssetStore
from src.image_generation.backend_adapter import BackendImageAdapter
from src.image_generation.openai_images import OpenAIImagesAdapter, OpenAIImagesConfig
from src.image_generation.provider_attempts import ProviderAttemptStore
from tests.demo_live.test_bp18_f09_two_stage import ReceiptedText
from tests.demo_live.test_http_gateway import photo
from tests.demo_live.test_live_contracts import sample_input
from tests.demo_live.test_pipeline import FONT, png
from tests.demo_staging.test_bp18_ux_p1_sso_only import env as signed_env, sign


ACTOR = "a_test_pm"
OTHER_ACTOR = "a_test_fe"
TEXT_MODEL = "f09-fake-model"
RELEASE_SHA = "1" * 40
RUNTIME_POLICY_SHA = "2" * 64


class MockText(ReceiptedText):
    def generate_prompt(self, plan, analysis):
        self.receipt("image_prompt")
        return super().generate_prompt(plan, analysis)


class MockOwnerImage(BackendImageAdapter):
    def generate(self, *args, **kwargs):
        # Exercise Live bookkeeping in this disposable runtime. Only this
        # test wrapper adapts MockTransport's offline marker at the boundary.
        return replace(super().generate(*args, **kwargs), mock=False)


def mock_owner_adapter(root, profile, calls, *, outcome=None):
    def wire(request):
        header = b"Content-Type: " + request.headers["content-type"].encode()
        parts = BytesParser(policy=policy.default).parsebytes(
            header + b"\r\n\r\n" + request.read())
        prompt = next(part.get_payload(decode=True) for part in parts.iter_parts()
                      if part.get_param("name", header="content-disposition") == "prompt")
        calls.append(prompt)
        if outcome:
            failure = outcome(request, len(calls))
            if failure is not None:
                return failure
        raw = png((120 + len(calls), 143, 164), size=(1152, 1440))
        return httpx.Response(200, json={
            "data": [{"b64_json": base64.b64encode(raw).decode()}],
            "usage": {"input_tokens": 8, "output_tokens": 12, "total_tokens": 20}},
            headers={"x-request-id": f"ittem-dual-mock-image-{len(calls)}"})

    transport = OpenAIImagesAdapter(OpenAIImagesConfig(live_calls=False),
                                    transport=httpx.MockTransport(wire))
    processor = ExternalImageProcessor(
        LocalAssetStore(root / "image_assets"), transport,
        ProviderAttemptStore(root / "image_attempts.sqlite"),
        budget_limit_usd="0", reservation_usd="0", monitoring_only=True)
    return MockOwnerImage(processor, root / "image_bindings.sqlite",
                          model=profile["model"], quality=profile["quality"],
                          complexity=profile["complexity"])


@pytest.fixture
def dual_runtime(signed_env, monkeypatch):
    tmp, dist, registry, key, _ = signed_env
    root = tmp / "b-deployment" / "runtime"
    host = http_api.B_TAILNET_HOST
    monkeypatch.setattr(http_api, "B_RUNTIME_ROOT", root)
    for name in ("IT_TEM_LIVE_WEB_QUEUE_ENABLED", "IT_TEM_LIVE_ENABLED",
                 "IT_TEM_LIVE_EXECUTION_APPROVED", "IT_TEM_PROVIDER_READINESS_CONFIRMED",
                 "IT_TEM_BP18_LIVE_DUAL_ENABLED", "IT_TEM_BP18_F11_ENABLED",
                 "IT_TEM_BP18_F09_REQUIRED"):
        monkeypatch.setenv(name, "YES")
    monkeypatch.setenv("IT_TEM_LIVE_COST_POLICY", "MONITOR_ONLY")
    monkeypatch.setenv("IT_TEM_LIVE_APPROVED_ACTORS", ACTOR)
    monkeypatch.setenv("IT_TEM_TAILNET_EXPECTED_HOST", host)
    monkeypatch.setenv("IT_TEM_DEMO_CODE_SHA", RELEASE_SHA)
    monkeypatch.setenv("IT_TEM_BP18_LIVE_RELEASE_SHA", RELEASE_SHA)
    monkeypatch.setenv("IT_TEM_BP18_LIVE_POLICY_SHA", RUNTIME_POLICY_SHA)
    monkeypatch.setenv("IT_TEM_TEXT_MODEL", TEXT_MODEL)
    monkeypatch.setenv("IT_TEM_LIVE_KOREAN_FONT", str(FONT))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    app = make_demo_app(root, registry, dist, secure_cookie=True, code_sha=RELEASE_SHA)
    flow = app.state.live_pipeline
    fake_text = MockText()
    monkeypatch.setattr(pipeline, "OfficialTextProvider", lambda *_: fake_text)
    monkeypatch.setattr(worker, "policy_from_env", lambda path: flow)
    return root, host, key, app, flow, fake_text


def signed_request(client, host, key, method, path, actor=ACTOR, **kwargs):
    headers = sign(key, actor, method=method, target=path, host=host)
    headers["Origin"] = f"https://{host}"
    return client.request(method, path, headers=headers, **kwargs)


def upload(client, host, key):
    response = signed_request(client, host, key, "POST", "/api/v1/jobs", files=[
        ("product_images", ("a.png", photo((120,130,140)), "image/png")),
        ("product_images", ("b.png", photo((150,160,170)), "image/png")),
    ])
    assert response.status_code == 201, response.text
    return response.json()["job_id"]


def attempts(flow):
    with flow.cost.connect() as c:
        return [dict(row) for row in c.execute("SELECT * FROM attempts ORDER BY rowid")]


def reviewed(flow, job_id):
    flow.prepare(ACTOR, job_id, {**sample_input(), "image_size": "4:5",
                 "generation_mode": "composed"}, template_profile="A", live_dual=True)
    return flow.text(ACTOR, job_id, text_model=TEXT_MODEL)


def approve(flow, job_id, review, execution_profile):
    return flow.state.start_live_dual(
        ACTOR, job_id, expected_generation=review["generation"],
        expected_review_sha=review["review_sha"], execution_profile=execution_profile,
        acknowledge_two_images=True)


def install_images(monkeypatch, flow, calls, *, outcome=None):
    from demo_staging.live.image_runtime_profile import effective_image_profile
    monkeypatch.setattr(worker, "live_image_adapter",
        lambda root, request: mock_owner_adapter(root, effective_image_profile(), calls, outcome=outcome))


def run_stage(root):
    return worker.run_once(root)


def test_signed_live_dual_mock_wire_and_independent_downloads(dual_runtime, monkeypatch):
    from demo_staging.live.dual_worker import live_dual_lease
    root, host, key, app, flow, text = dual_runtime
    calls = []
    install_images(monkeypatch, flow, calls)
    with TestClient(app, base_url=f"https://{host}") as client:
        job = upload(client, host, key)
        base = f"/demo/api/live/jobs/{job}"
        dual = base + "/dual"

        def request(method, path, **kwargs):
            return signed_request(client, host, key, method, path, **kwargs)

        assert client.get(dual).status_code == 401
        with worker.exclusive_live_worker(root), live_dual_lease(root):
            cta_hold = request("POST", dual+"/input", json={
                **sample_input(), "image_size":"9:16", "generation_mode":"composed"})
            assert cta_hold.status_code == 423, cta_hold.text
            prepared = request("POST", dual+"/input", json={
                **sample_input(), "image_size":"4:5", "generation_mode":"composed"})
            assert prepared.status_code == 200, prepared.text
            assert prepared.json()["dual_provenance"] == "LIVE_DUAL"
            queued = request("POST", base+"/queue-text")
            assert queued.status_code == 202, queued.text
            task = app.state.live_queue.read(queued.json()["task_id"])
            assert task["mode"] == "LIVE_DUAL_V1"
            assert app.state.live_queue.claim("LIVE") is None
        assert run_stage(root) == "LIVE_STAGE_COMMITTED"
        snapshot = request("GET", base).json()
        proof = json.loads(flow.state.get(ACTOR,job)["compliance_json"])["llm_review"]
        assert len(attempts(flow)) == 4
        assert text.calls == ["analyze","research","copy","review"]

        approval = {"expected_generation":snapshot["generation"],
                    "expected_review_sha":snapshot["review_sha"],
                    "acknowledge_two_images":True}
        with worker.exclusive_live_worker(root), live_dual_lease(root):
            denied = request("POST", dual+"/start", json={**approval,"acknowledge_two_images":False})
            assert denied.status_code in (409,422), denied.text
            response = request("POST", dual+"/start", json=approval)
            assert response.status_code == 202, response.text
            assert request("POST", dual+"/start", json=approval).json() == response.json()
        group = flow.state.live_dual_group(ACTOR,job)
        child = flow.state.get(ACTOR,group["child_job_id"])
        report = json.loads(child["compliance_json"])
        assert "llm_review" not in report
        assert report["live_dual_f09_parent"]["attempt_id"] == proof["attempt_id"]
        assert child["copy_sha"] == snapshot["copy_sha"]
        assert child["approval_sha"] != flow.state.get(ACTOR,job)["approval_sha"]
        assert run_stage(root) == "LIVE_STAGE_COMMITTED"
        assert len(attempts(flow)) == 5
        for _ in range(2):
            assert run_stage(root) == "LIVE_STAGE_COMMITTED"
        assert run_stage(root) == "NO_LIVE_TASK"
        assert len(calls) == 2 and len(attempts(flow)) == 7
        pending = request("GET", dual).json()
        assert pending["state"] == "REVIEW_REQUIRED"
        ad_copy = json.loads(flow.state.get(ACTOR,job)["copy_json"])["ad_copy"]
        finals = {}
        for mode in ("composed","freeform"):
            variant = pending["variants"][mode]
            assert variant["provider_evidence"]
            wrong_actor = signed_request(client,host,key,"GET",dual,actor=OTHER_ACTOR)
            assert wrong_actor.status_code == 404
            candidate = request("GET",variant["artifacts"]["candidate"])
            assert candidate.status_code == 200, candidate.text
            assert sha256(candidate.content).hexdigest() == variant["candidate_sha"]
            checks = {"product_matches":True,"label_matches":True,"cta_policy_matches":True}
            if mode == "freeform":
                checks.update(observed_copy=ad_copy,no_extra_text=True)
            bad = request("POST",dual+f"/{mode}/decision",json={
                "image_sha":variant["candidate_sha"],"approve":True})
            assert bad.status_code in (409,422), bad.text
            result = request("POST",dual+f"/{mode}/decision",json={
                "image_sha":variant["candidate_sha"],"approve":True,"visual_review":checks})
            assert result.status_code == 200,result.text
            assert result.json()["state"] == ("PARTIAL" if mode=="composed" else "COMPLETED")
            final = result.json()["variants"][mode]
            files = {}
            for name in ("final","caption","receipt"):
                artifact = request("GET",final["artifacts"][name])
                assert artifact.status_code == 200,artifact.text
                assert sha256(artifact.content).hexdigest() == final[f"{name}_sha"]
                files[name] = artifact.content
            assert Image.open(BytesIO(files["final"])).size == (1080,1350)
            if mode == "freeform":
                assert files["final"] == resize_ad_png(candidate.content).image_bytes
            finals[mode] = final
        assert finals["composed"]["provider_evidence"]["provider_request_sha"] != finals["freeform"]["provider_evidence"]["provider_request_sha"]
        assert finals["composed"]["provider_evidence"]["provider_prompt_sha"] != finals["freeform"]["provider_evidence"]["provider_prompt_sha"]
        selected = request("POST",dual+"/selection",json={
            "mode":"freeform","final_sha":finals["freeform"]["final_sha"]})
        assert selected.status_code == 200,selected.text
        assert request("GET",dual).json()["preferred_variant"] == "freeform"
        assert len(calls) == 2
        assert all(row["status"]=="SUCCEEDED_USAGE_UNPRICED" and row["cost_microusd"] is None
                   for row in attempts(flow))


def prepare_direct(dual_runtime, monkeypatch):
    from demo_staging.live.dual_worker import live_dual_profile
    root, host, key, app, flow, _ = dual_runtime
    calls = []
    install_images(monkeypatch, flow, calls)
    with TestClient(app, base_url=f"https://{host}") as client:
        job = upload(client, host, key)
    review = reviewed(flow, job)
    flow.verify_live_dual_f09(ACTOR, job)
    group = approve(flow, job, review, live_dual_profile())
    return root, app.state.live_queue, flow, job, group, calls


def test_durable_intent_projection_recovers_after_queue_insert_before_attach(dual_runtime, monkeypatch):
    from demo_staging.live.dual_worker import project_intents
    root, queue, flow, job, group, calls = prepare_direct(dual_runtime, monkeypatch)
    original = flow.state.attach_live_dual_task
    def interrupt(*args):
        raise OSError("test crash after queue insert")
    monkeypatch.setattr(flow.state, "attach_live_dual_task", interrupt)
    with pytest.raises(OSError):
        project_intents(flow, queue)
    monkeypatch.setattr(flow.state, "attach_live_dual_task", original)
    project_intents(flow, queue)
    project_intents(flow, queue)
    with queue.db() as c:
        assert c.execute("SELECT COUNT(*) FROM queued_ops").fetchone()[0] == 1
    assert run_stage(root) == "LIVE_STAGE_COMMITTED"
    assert run_stage(root) == "LIVE_STAGE_COMMITTED"
    assert run_stage(root) == "LIVE_STAGE_COMMITTED"
    assert len(calls) == 2


def test_possible_dispatch_and_lost_response_stay_held_across_restarts(dual_runtime, monkeypatch):
    root, queue, flow, job, group, calls = prepare_direct(dual_runtime, monkeypatch)
    assert run_stage(root) == "LIVE_STAGE_COMMITTED"
    def lost(request, count):
        raise httpx.ReadTimeout("test response lost", request=request)
    install_images(monkeypatch, flow, calls, outcome=lost)
    assert run_stage(root) == "LIVE_STAGE_HELD_FOR_RECONCILIATION"
    assert run_stage(root) == "LIVE_STAGE_HELD_FOR_RECONCILIATION"
    assert run_stage(root) == "LIVE_STAGE_HELD_FOR_RECONCILIATION"
    assert len(calls) == 1
    assert flow.state.live_dual_group(ACTOR,job)["hold_code"]
    image_attempts = [row for row in attempts(flow) if row["stage"]=="image"]
    assert len(image_attempts) == 1 and image_attempts[0]["status"]=="BILLING_UNKNOWN"


def test_crash_after_claim_before_send_never_renders_abandoned_variant(dual_runtime, monkeypatch):
    from demo_staging.live.dual_worker import project_intents
    root, queue, flow, job, group, calls = prepare_direct(dual_runtime, monkeypatch)
    assert run_stage(root) == "LIVE_STAGE_COMMITTED"
    project_intents(flow, queue)
    abandoned = queue.claim("LIVE", include_dual=True)
    assert abandoned["stage"] == "image"
    assert run_stage(root) == "LIVE_STAGE_COMMITTED"
    assert len(calls) == 1
    assert queue.read(abandoned["id"])["state"] == "FAILED"
    assert run_stage(root) == "NO_LIVE_TASK"
    assert len(calls) == 1


def test_completed_candidate_recovers_queue_commit_without_second_model_call(dual_runtime, monkeypatch):
    from demo_staging.live import dual_worker
    root, queue, flow, job, group, calls = prepare_direct(dual_runtime, monkeypatch)
    assert run_stage(root) == "LIVE_STAGE_COMMITTED"
    original = dual_worker._complete
    def interrupted(*args):
        raise OSError("test crash before queue commit")
    monkeypatch.setattr(dual_worker,"_complete",interrupted)
    with pytest.raises(OSError):
        run_stage(root)
    assert len(calls) == 1
    monkeypatch.setattr(dual_worker,"_complete",original)
    assert run_stage(root) == "LIVE_STAGE_COMMITTED"
    assert len(calls) == 2
    assert run_stage(root) == "NO_LIVE_TASK"
    assert len(calls) == 2


@pytest.mark.parametrize("target",["f09_receipt","parent_copy","child_copy","policy_epoch","actor"])
def test_changed_authority_fails_before_image_dispatch(dual_runtime, monkeypatch, target):
    root, queue, flow, job, group, calls = prepare_direct(dual_runtime, monkeypatch)
    child = group["child_job_id"]
    if target == "f09_receipt":
        proof = json.loads(flow.state.get(ACTOR,job)["compliance_json"])["llm_review"]
        with flow.cost.connect() as c:
            c.execute("UPDATE attempts SET receipt=? WHERE id=?",("{}",proof["attempt_id"]))
    elif target == "policy_epoch":
        with flow.state.db() as c:
            c.execute("UPDATE live_policy_activation SET epoch=epoch+1")
    elif target == "actor":
        flow.approved_actors = frozenset({OTHER_ACTOR})
    else:
        victim = job if target=="parent_copy" else child
        with flow.state.db() as c:
            c.execute("UPDATE live_jobs SET copy_sha=? WHERE job_id=?",("f"*64,victim))
    assert run_stage(root) in ("LIVE_DUAL_STAGE_FAILED","LIVE_STAGE_HELD_FOR_RECONCILIATION")
    assert calls == []
    assert len(attempts(flow)) == 4


def visual_approval(flow, job_id):
    job = flow.state.get(ACTOR,job_id)
    checks = {"product_matches":True,"label_matches":True,"cta_policy_matches":True}
    if json.loads(job["input_json"])["generation_mode"]=="freeform":
        checks.update(no_extra_text=True,observed_copy=json.loads(job["copy_json"])["ad_copy"])
    flow.state.approve_image(ACTOR,job_id,job["image_sha"],visual_review=checks,reviewer_role="evaluator")
    return flow.compose(ACTOR,job_id,font_path=FONT)


def test_receipt_loss_holds_without_automatic_provider_replay(dual_runtime, monkeypatch):
    root, queue, flow, job, group, calls = prepare_direct(dual_runtime,monkeypatch)
    assert run_stage(root) == "LIVE_STAGE_COMMITTED"
    original = MockOwnerImage.generate
    def missing(self, *args, **kwargs):
        return replace(original(self,*args,**kwargs),receipt={})
    monkeypatch.setattr(MockOwnerImage,"generate",missing)
    assert run_stage(root) == "LIVE_STAGE_HELD_FOR_RECONCILIATION"
    assert run_stage(root) == "LIVE_STAGE_HELD_FOR_RECONCILIATION"
    assert len(calls)==1
    assert flow.state.live_dual_group(ACTOR,job)["hold_code"]


def test_one_rejected_variant_keeps_other_download_and_historical_receipt(dual_runtime, monkeypatch):
    root, queue, flow, job, group, calls = prepare_direct(dual_runtime,monkeypatch)
    for _ in range(3):
        assert run_stage(root) == "LIVE_STAGE_COMMITTED"
    child = flow.state.get(ACTOR,group["child_job_id"])
    flow.state.reject_image(ACTOR,child["job_id"],child["image_sha"])
    final = visual_approval(flow,job)
    before = (flow.root/"outputs"/job/"final.png").read_bytes()
    assert flow.validate_final_artifacts(ACTOR,job)["final_sha"] == sha256(before).hexdigest()
    with flow.state.db() as c:
        c.execute("UPDATE live_policy_activation SET epoch=epoch+1")
    assert flow.validate_final_artifacts(ACTOR,job)["final_sha"] == final["final_sha"]
    assert (flow.root/"outputs"/job/"final.png").read_bytes() == before
    assert len(calls)==2


def test_corrupt_variant_receipt_preserves_completed_sibling(dual_runtime, monkeypatch):
    root, queue, flow, job, group, calls = prepare_direct(dual_runtime,monkeypatch)
    for _ in range(3):
        assert run_stage(root) == "LIVE_STAGE_COMMITTED"
    child = group["child_job_id"]
    visual_approval(flow,job)
    visual_approval(flow,child)
    path = flow.root/"outputs"/child/"owner_candidate_receipt.json"
    path.write_text("{}")
    with pytest.raises(LiveGateError):
        flow.validate_final_artifacts(ACTOR,child)
    flow.validate_final_artifacts(ACTOR,job)
    assert len(calls)==2


def test_mock_invoice_reconciliation_preserves_original_download(dual_runtime,monkeypatch):
    root, queue, flow, job, group, calls = prepare_direct(dual_runtime,monkeypatch)
    for _ in range(3):
        assert run_stage(root) == "LIVE_STAGE_COMMITTED"
    final = visual_approval(flow,job)
    binding = flow.live_dual_candidate_receipt(ACTOR,job)
    with flow.cost.connect() as c:
        c.execute("UPDATE attempts SET status='SUCCEEDED',cost_microusd=123456 WHERE id=?",
                  (binding["cost_receipt"]["attempt_id"],))
    assert flow.validate_final_artifacts(ACTOR,job)["final_sha"] == final["final_sha"]
    assert len(calls) == 2


def test_native_owner_binding_tamper_is_detected_independently(dual_runtime,monkeypatch):
    import sqlite3
    root, queue, flow, job, group, calls = prepare_direct(dual_runtime,monkeypatch)
    for _ in range(3):
        assert run_stage(root) == "LIVE_STAGE_COMMITTED"
    visual_approval(flow,job)
    child = group["child_job_id"]
    with sqlite3.connect(flow.root/"owner_image"/"image_bindings.sqlite") as c:
        c.execute("UPDATE backend_image_bindings SET request_hash=? WHERE service_job_id=?",("0"*64,job))
    with pytest.raises(LiveGateError,match="LIVE_DUAL_PROVIDER_RECEIPT_MISMATCH"):
        flow.validate_final_artifacts(ACTOR,job)
    flow.live_dual_candidate_receipt(ACTOR,child)
    assert len(calls) == 2
