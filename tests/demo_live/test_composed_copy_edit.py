"""Nonbillable manual copy revision evidence over Signed MockTransport source.

The visual flags below describe only flat-color fixture images, never a human
acceptance of actual product labels or actual commercial advertising.
"""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from demo_staging.live.composed_copy_edit import ComposedCopyEdits, run_composed_copy_edit_once
from demo_staging.live.composed_copy_edit_api import install_composed_copy_edit_routes
from demo_staging.live.contracts import LiveGateError
from tests.demo_live.test_live_dual_mock_transport import (
    ACTOR, OTHER_ACTOR, dual_runtime, signed_env, signed_request, prepare_direct, run_stage, attempts,
)


@pytest.fixture
def case(dual_runtime, monkeypatch):
    root, host, key, app, flow, text = dual_runtime
    monkeypatch.setenv("IT_TEM_COMPOSED_COPY_EDIT_ENABLED", "YES")
    monkeypatch.setenv("IT_TEM_COMPOSED_COPY_EDIT_WORKER_PROTOCOL", "COMPOSED_COPY_EDIT_V1")
    _, _, _, parent, group, calls = prepare_direct(dual_runtime, monkeypatch)
    for _ in range(3):
        assert run_stage(root) == "LIVE_STAGE_COMMITTED"
    # Root's integration may already register these routes in the fixed app.
    if not hasattr(app.state, "composed_copy_edit_service"):
        def auth(request, job_id):
            from fastapi import HTTPException
            ident = app.state.demo_request_identity(request)
            if ident is None:
                raise HTTPException(401, "Login required")
            try:
                flow.state.get(ident[0], job_id)
            except LiveGateError:
                raise HTTPException(404, "Job not found") from None
            return ident[0]
        before_routes = len(app.router.routes)
        install_composed_copy_edit_routes(app, flow, auth, lambda actor: flow.require_live_actor(actor))
        # The fixture already installed the SPA fallback. Place test-only routes
        # before that fallback, matching production registration order.
        added = app.router.routes[before_routes:]
        del app.router.routes[before_routes:]
        app.router.routes[0:0] = added
    return root, host, key, app, flow, text, parent, group["child_job_id"], calls


def body(flow, job, *, key="a"*32, same=False):
    source = flow.state.get(ACTOR, job)
    ad = json.loads(source["copy_json"])["ad_copy"]
    if not same:
        ad["headline"] = "매일의 샴푸 시간"
        ad["subline"] = "차분하게 시작해요"
        ad["cta"] = "제품 만나기"
    return {"expected_image_sha": source["image_sha"], "expected_copy_sha": source["copy_sha"],
        "expected_approval_sha": source["approval_sha"], "ad_copy": ad, "request_key": key}


@pytest.mark.parametrize('checkbox_only',[False,True])
def test_signed_manual_edit_separate_f09_two_approvals_and_downloads(case,checkbox_only):
    root, host, key, app, flow, text, parent, child, calls = case
    before = {j: flow.state.get(ACTOR, j) for j in (parent, child)}
    old_cost = attempts(flow)
    raw = {j: flow.image_path(j).read_bytes() for j in (parent, child)}
    receipts = {j: (flow.root/"outputs"/j/"owner_candidate_receipt.json").read_bytes() for j in (parent, child)}
    with TestClient(app, base_url=f"https://{host}") as client:
        base = f"/demo/api/live/jobs/{parent}/composed-copy-edits"
        def req(method, suffix="", **kwargs):
            from demo_staging.live.worker import exclusive_live_worker
            with exclusive_live_worker(root):
                return signed_request(client, host, key, method, base+suffix, **kwargs)
        listing = req("GET")
        assert listing.status_code == 200, listing.text
        assert listing.json()["approved_copy"] == json.loads(before[parent]["copy_json"])["ad_copy"]
        assert client.get(base).status_code == 401
        assert req("GET", actor=OTHER_ACTOR).status_code == 404
        created = req("POST", json=body(flow, parent))
        assert created.status_code == 202, created.text
        revision = created.json()
        assert revision["state"] == "QUEUED_REVIEW" and revision["artifacts"] == {}
        assert len(attempts(flow)) == len(old_cost), "HTTP must not invoke any Provider"
        assert req("POST", json=body(flow, parent)).json()["edit_id"] == revision["edit_id"]
        conflict = body(flow, parent); conflict["ad_copy"]["cta"] = "다른 문구"
        assert req("POST", json=conflict).status_code == 409
        assert run_composed_copy_edit_once(flow) == "COMPOSED_COPY_EDIT_REVIEW_COMMITTED"
        assert run_composed_copy_edit_once(flow) == "NO_COMPOSED_COPY_EDIT"
        ready = req("GET").json()["edits"][0]
        assert ready["state"] == "COPY_REVIEW_REQUIRED"
        assert ready["report"]["llm_review"]["attempt_id"] == ready["cost_receipt"]["attempt_id"]
        assert ready["copy"]["caption"] == json.loads(before[parent]["copy_json"])["caption"]
        assert ready["copy"]["hashtags"] == json.loads(before[parent]["copy_json"])["hashtags"]
        suffix = "/"+ready["edit_id"]
        approval = {"expected_revision": ready["revision"], "expected_copy_sha": ready["copy_sha"],
                    "expected_review_sha": ready["review_sha"], "acknowledge_evidence": True}
        pending = req("POST", suffix+"/copy-approval", json=approval)
        assert pending.status_code == 200, pending.text
        pending = pending.json()
        assert pending["state"] == "IMAGE_REVIEW_REQUIRED"
        assert pending["approval_sha"] != before[parent]["approval_sha"]
        image = signed_request(client, host, key, "GET", pending["artifacts"]["preview"])
        assert image.status_code == 200
        assert sha256(image.content).hexdigest() == pending["preview_sha"]
        assert Image.open(BytesIO(image.content)).size == (1080,1350)
        assert req("GET", suffix+"/artifacts/final?sha256="+pending["preview_sha"]).status_code == 409
        checks = {"product_matches": True, "label_matches": True, "cta_policy_matches": True,
                  "no_extra_text": True, "observed_copy": ready["copy"]["ad_copy"]}
        decision = {"expected_revision": pending["revision"], "expected_preview_sha": pending["preview_sha"],
                    "approve": True, "visual_review": checks}
        typo = deepcopy(decision); typo["visual_review"]["observed_copy"]["subline"] = "자분하게 시작해요"
        assert req("POST", suffix+"/decision", json=typo).status_code == 409
        if checkbox_only:
            del checks['observed_copy'];checks['copy_verified']=True
        completed = req("POST", suffix+"/decision", json=decision)
        assert completed.status_code == 200, completed.text
        record = completed.json()
        assert record["state"] == "COMPLETED"
        assert req("POST", suffix+"/copy-approval", json=approval).status_code == 409
        for kind in ("final", "caption", "receipt"):
            downloaded = signed_request(client, host, key, "GET", record["artifacts"][kind])
            assert downloaded.status_code == 200
            assert sha256(downloaded.content).hexdigest() == record[kind+"_sha"]
        receipt = signed_request(client, host, key, "GET", record["artifacts"]["receipt"]).json()
        assert receipt["image_provider_calls"] == 0 and receipt["text_provider_calls"] == 1
        assert receipt["actual_usd"] is None and receipt["source_image_approval_inherited"] is False
    assert {j: flow.state.get(ACTOR,j) for j in (parent,child)} == before
    assert {j: flow.image_path(j).read_bytes() for j in (parent,child)} == raw
    assert {j: (flow.root/"outputs"/j/"owner_candidate_receipt.json").read_bytes() for j in (parent,child)} == receipts
    assert attempts(flow)[:len(old_cost)] == old_cost
    assert len(attempts(flow)) == len(old_cost)+1 and len(calls) == 2


def test_same_copy_requires_fresh_approval_without_new_provider(case):
    _, _, _, _, flow, _, parent, _, calls = case
    service = ComposedCopyEdits(flow)
    old = attempts(flow)
    record = service.create(ACTOR, parent, body(flow,parent,same=True))
    assert record["state"] == "COPY_REVIEW_REQUIRED"
    assert record["review_origin"] == "SOURCE_F09_EXACT_COPY" and record["approval_sha"] is None
    assert run_composed_copy_edit_once(flow) == "NO_COMPOSED_COPY_EDIT"
    assert attempts(flow) == old and len(calls) == 2


def test_edit_rule_failure_never_queues_provider(case):
    _, _, _, _, flow, _, parent, _, _ = case
    payload = body(flow,parent)
    payload["ad_copy"]["headline"] = "탈모 치료 100% 보장"
    service = ComposedCopyEdits(flow)
    old = attempts(flow)
    record = service.create(ACTOR,parent,payload)
    assert record["state"] == "RULE_BLOCKED" and not record["report"]["passed"]
    assert run_composed_copy_edit_once(flow) == "NO_COMPOSED_COPY_EDIT"
    assert attempts(flow) == old


def test_stale_source_and_actor_and_wrong_mode_rejected(case):
    _, _, _, _, flow, _, parent, child, _ = case
    service = ComposedCopyEdits(flow)
    payload = body(flow,parent)
    payload["expected_approval_sha"] = "0"*64
    with pytest.raises(LiveGateError,match="STALE"):
        service.create(ACTOR,parent,payload)
    from demo_staging.live_safety import LiveNotAuthorized
    with pytest.raises(LiveNotAuthorized):
        service.create(OTHER_ACTOR,parent,body(flow,parent))
    with pytest.raises(LiveGateError,match="SOURCE_REQUIRED"):
        service.create(ACTOR,child,body(flow,child))


def test_worker_crash_never_replays_and_globally_blocks_edit_claim(case):
    _, _, _, _, flow, _, parent, _, _ = case
    service = ComposedCopyEdits(flow)
    row = service.create(ACTOR,parent,body(flow,parent))
    old = attempts(flow)
    with service.db() as c:
        record = service._read(c,ACTOR,parent,row["edit_id"])
        record["state"] = "RUNNING"; service._save(c,record); c.commit()
    assert run_composed_copy_edit_once(flow) == "COMPOSED_COPY_EDIT_BILLING_UNKNOWN"
    assert run_composed_copy_edit_once(flow) == "COMPOSED_COPY_EDIT_BILLING_UNKNOWN"
    assert attempts(flow) == old
    with pytest.raises(LiveGateError,match="BILLING_UNKNOWN"):
        service.create(ACTOR,parent,body(flow,parent,key="b"*32))


def test_source_rejection_cannot_reactivate_revision_or_artifacts(case):
    _, _, _, _, flow, _, parent, child, _ = case
    service = ComposedCopyEdits(flow)
    row = service.create(ACTOR,parent,body(flow,parent,same=True))
    pending = service.approve_copy(ACTOR,parent,row["edit_id"],{
        "expected_revision":row["revision"],"expected_copy_sha":row["copy_sha"],
        "expected_review_sha":row["review_sha"],"acknowledge_evidence":True})
    sibling = flow.state.get(ACTOR,child)
    flow.state.reject_image(ACTOR,parent,flow.state.get(ACTOR,parent)["image_sha"])
    with pytest.raises(LiveGateError,match="SOURCE_IMAGE_REJECTED"):
        service.artifact(ACTOR,parent,row["edit_id"],"preview",pending["preview_sha"])
    with pytest.raises(LiveGateError,match="SOURCE_IMAGE_REJECTED"):
        service.snapshot(ACTOR,parent)
    assert flow.state.get(ACTOR,child) == sibling


def test_preview_file_tamper_blocks_approval_and_download(case):
    _, _, _, _, flow, _, parent, _, _ = case
    service = ComposedCopyEdits(flow)
    row = service.create(ACTOR,parent,body(flow,parent,same=True))
    pending = service.approve_copy(ACTOR,parent,row["edit_id"],{
        "expected_revision":row["revision"],"expected_copy_sha":row["copy_sha"],
        "expected_review_sha":row["review_sha"],"acknowledge_evidence":True})
    with service.db() as c:
        stored = service._read(c,ACTOR,parent,row["edit_id"])
    service._artifact_path(stored,"preview").write_bytes(b"tampered")
    with pytest.raises(LiveGateError,match="ARTIFACT_INTEGRITY"):
        service.artifact(ACTOR,parent,row["edit_id"],"preview",pending["preview_sha"])


def test_recovery_scan_never_claims_a_queued_paid_edit(case):
    _, _, _, _, flow, _, parent, _, _ = case
    service = ComposedCopyEdits(flow)
    row = service.create(ACTOR,parent,body(flow,parent))
    old = attempts(flow)
    assert run_composed_copy_edit_once(flow,recover_only=True) == "NO_COMPOSED_COPY_EDIT"
    assert service.snapshot(ACTOR,parent)["edits"][0]["state"] == "QUEUED_REVIEW"
    assert attempts(flow) == old


@pytest.mark.parametrize("target",["copy", "report", "approval"])
def test_revision_database_mutation_fails_closed(case,target):
    _, _, _, _, flow, _, parent, _, _ = case
    service = ComposedCopyEdits(flow)
    row = service.create(ACTOR,parent,body(flow,parent,same=True))
    if target == "approval":
        row = service.approve_copy(ACTOR,parent,row["edit_id"],{
            "expected_revision":row["revision"],"expected_copy_sha":row["copy_sha"],
            "expected_review_sha":row["review_sha"],"acknowledge_evidence":True})
    with service.db() as c:
        record = service._read(c,ACTOR,parent,row["edit_id"])
        if target == "copy":
            record["copy"]["ad_copy"]["cta"] = "변조"
        elif target == "report":
            record["report"]["passed"] = not record["report"]["passed"]
        else:
            record["approval_sha"] = "0"*64
        service._save(c,record);c.commit()
    with pytest.raises(LiveGateError,match="INTEGRITY"):
        service.approve_copy(ACTOR,parent,row["edit_id"],{
            "expected_revision":row["revision"],"expected_copy_sha":row["copy_sha"],
            "expected_review_sha":row["review_sha"],"acknowledge_evidence":True})
