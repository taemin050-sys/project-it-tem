"""Signed fixture usage attribution, not live USD or commercial acceptance."""
import json

from fastapi.testclient import TestClient
import pytest

from demo_staging.live.composed_copy_edit import ComposedCopyEdits, run_composed_copy_edit_once
from demo_staging.live.contracts import digest
from demo_staging.live.image_correction import ImageCorrections, run_image_correction_once
from tests.demo_live.test_composed_copy_edit import case, body
from tests.demo_live.test_image_correction import wire_transport
from tests.demo_live.test_live_dual_mock_transport import ACTOR, OTHER_ACTOR, dual_runtime, signed_env, signed_request, attempts


def test_signed_revision_snapshots_and_base_dual_counts_partition_real_ledgers(case,monkeypatch):
    root,host,key,app,flow,text,parent,child,calls=case
    monkeypatch.setenv("IT_TEM_IMAGE_CORRECTION_ENABLED","YES")
    monkeypatch.setenv("IT_TEM_IMAGE_CORRECTION_PROTOCOL","FREEFORM_TEXT_EDIT_V1")
    before={jid:flow.state.get(ACTOR,jid) for jid in (parent,child)}
    initial=attempts(flow)
    source_receipts={jid:(flow.root/"outputs"/jid/"owner_candidate_receipt.json").read_bytes() for jid in (parent,child)}
    manual=ComposedCopyEdits(flow)
    manual.create(ACTOR,parent,body(flow,parent))
    assert run_composed_copy_edit_once(flow)=="COMPOSED_COPY_EDIT_REVIEW_COMMITTED"
    corrections=ImageCorrections(flow)
    job=flow.state.get(ACTOR,child)
    request={"expected_image_sha":job["image_sha"],"expected_copy_sha":job["copy_sha"],
        "expected_approval_sha":job["approval_sha"],"field":"subline","observed_text":"자분하게 시작해요",
        "region":[.1,.2,.8,.3],"request_key":"1"*32,"acknowledge_paid_edit":True}
    edit_calls=[]
    for request_key in ("1"*32,"2"*32):
        corrections.request(ACTOR,child,{**request,"request_key":request_key})
        assert run_image_correction_once(flow,transport=wire_transport(flow,child,edit_calls))=="IMAGE_CORRECTION_REVIEW_REQUIRED"
    assert len(edit_calls)==2
    with TestClient(app,base_url=f"https://{host}") as client:
        base=f"/demo/api/live/jobs/{parent}"
        snapshot=signed_request(client,host,key,"GET",base+"/dual")
        assert snapshot.status_code==200,snapshot.text
        snapshot=snapshot.json()
        assert snapshot["shared_text_cost"]["provider_attempt_count"]==5
        assert snapshot["variants"]["composed"]["cost"]["provider_attempt_count"]==1
        assert snapshot["variants"]["freeform"]["cost"]["provider_attempt_count"]==1
        assert snapshot["variants"]["composed"]["revision_cost"]["provider_attempt_count"]==1
        assert snapshot["variants"]["freeform"]["revision_cost"]["provider_attempt_count"]==2
        cost_ids=[item["attempt_id"] for item in snapshot["shared_text_cost"]["attempts"]]
        for variant in snapshot["variants"].values():
            cost_ids.extend(item["attempt_id"] for item in variant["cost"]["attempts"])
            cost_ids.extend(item["attempt_id"] for item in variant["revision_cost"]["attempts"])
        assert len(set(cost_ids))==len(cost_ids)==len(attempts(flow))==10
        for job_id,path,expected in ((parent,"composed-copy-edits",1),(child,"image-corrections",2)):
            url=f"/demo/api/live/jobs/{job_id}/{path}"
            response=signed_request(client,host,key,"GET",url)
            assert response.status_code==200,response.text
            cost=response.json()["cost_summary"]
            assert cost["provider_attempt_count"]==expected and cost["status"]=="UNPRICED"
            assert cost["actual_usd"] is None
            assert client.get(url).status_code==401
            assert signed_request(client,host,key,"GET",url,actor=OTHER_ACTOR).status_code==404
    assert attempts(flow)[:len(initial)]==initial
    assert {jid:flow.state.get(ACTOR,jid) for jid in (parent,child)}==before
    assert {jid:(flow.root/"outputs"/jid/"owner_candidate_receipt.json").read_bytes() for jid in (parent,child)}==source_receipts


def test_new_copy_request_freezes_model_and_changed_policy_never_dispatches(case,monkeypatch):
    _,_,_,_,flow,_,parent,_,_=case
    service=ComposedCopyEdits(flow)
    row=service.create(ACTOR,parent,body(flow,parent))
    with service.db() as c:
        stored=service._read(c,ACTOR,parent,row["edit_id"])
    assert stored["review_model"]=="f09-fake-model"
    assert stored["review_model_sha"]==digest({"request_sha":stored["request_sha"],"model":"f09-fake-model"})
    initial=attempts(flow)
    monkeypatch.setenv("IT_TEM_TEXT_MODEL","another-model")
    assert run_composed_copy_edit_once(flow)=="COMPOSED_COPY_EDIT_HELD"
    assert attempts(flow)==initial
    with service.db() as c:
        failed=service._read(c,ACTOR,parent,row["edit_id"])
    assert failed["error_code"] in ("COMPOSED_EDIT_REVIEW_MODEL_CHANGED", "REVIEW_POLICY_RUNTIME_VERSION_CHANGED")


def test_old_unmodified_copy_revision_without_model_freeze_preserves_binding(case):
    _,_,_,_,flow,_,parent,_,_=case
    service=ComposedCopyEdits(flow)
    row=service.create(ACTOR,parent,body(flow,parent))
    with service.db() as c:
        legacy=service._read(c,ACTOR,parent,row["edit_id"])
        legacy.pop("review_model");legacy.pop("review_model_sha")
        service._save(c,legacy);c.commit()
    assert run_composed_copy_edit_once(flow)=="COMPOSED_COPY_EDIT_REVIEW_COMMITTED"
    snapshot=service.snapshot(ACTOR,parent)
    assert snapshot["cost_summary"]["provider_attempt_count"]==1
    assert snapshot["cost_summary"]["classification_status"]=="COMPLETE"
    with service.db() as c:
        preserved=service._read(c,ACTOR,parent,row["edit_id"])
    assert "review_model" not in preserved and preserved["request_sha"]==legacy["request_sha"]


def test_frozen_pending_model_still_classifies_dispatch_after_environment_change(case,monkeypatch):
    _,_,_,_,flow,_,parent,_,_=case
    from demo_staging.live.revision_costs import revision_cost_summary
    service=ComposedCopyEdits(flow)
    row=service.create(ACTOR,parent,body(flow,parent))
    with service.db() as c:
        stored=service._read(c,ACTOR,parent,row["edit_id"])
        stored["state"]="RUNNING";service._save(c,stored);c.commit()
    fingerprint={"protocol":"COMPOSED_COPY_EDIT_V1","edit_id":row["edit_id"],
        "source_context_sha":stored["source_context_sha"],"copy_sha":stored["copy_sha"],"model":stored["review_model"]}
    reserved=flow.cost.reserve(actor=ACTOR,role="live_operator",job_id=parent,stage="copy_review",payload=fingerprint,
        estimated_usd=0,pm_authorized=True)
    flow.cost.dispatch_intent(reserved["id"])
    monkeypatch.setenv("IT_TEM_TEXT_MODEL","another-model")
    summary=revision_cost_summary(flow,ACTOR,parent)
    assert summary["excluded_attempt_ids"]==[reserved["id"]]
    assert summary["status"]=="AWAITING_RECEIPT" and summary["provider_attempt_count"]==1
