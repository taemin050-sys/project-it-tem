"""BP13 single-image retry: immutable rejected artifact, current approval, no Text replay."""
import hashlib
import json
from pathlib import Path
from uuid import uuid4
import pytest

from demo_staging.live.contracts import LiveGateError,digest
from demo_staging.live.queue import LiveQueue
from src.image_generation.backend_adapter import BackendGeneratedImage
from src.image_generation.size_selection import resolve_size_choice
from tests.demo_live.test_pipeline import FakeOwner,FONT,png,prepare_service
from tests.demo_live.test_live_contracts import sample_input


def ready(tmp_path):
    flow,jid=prepare_service(tmp_path)
    flow.prepare("alice",jid,{**sample_input(),"image_size":"4:5"},template_profile="A")
    owner=FakeOwner()
    text=flow.text("alice",jid,owner,offline=True)
    flow.state.approve_copy("alice",jid,text["generation"],text["review_sha"])
    flow.prompt("alice",jid,owner,offline=True)
    request=flow.image_input("alice",jid)
    native=resolve_size_choice("4:5")[1].native
    raw=png((190,180,170),size=native)
    candidate=BackendGeneratedImage(image_bytes=raw,mime_type="image/png",
        width=native[0],height=native[1],sha256=hashlib.sha256(raw).hexdigest(),
        job_id=jid,copy_revision=request.copy_revision,copy_hash=request.copy_hash,
        mock=True,receipt={"mode":"OFFLINE_FIXTURE","provider_calls":0})
    first=flow.accept_image_result("alice",jid,candidate,offline=True)
    assert first["state"]=="IMAGE_REVIEW_REQUIRED"
    return flow,jid,owner,candidate


def test_reject_then_retry_new_attempt_same_copy_and_no_text_call(tmp_path):
    flow,jid,owner,first=ready(tmp_path)
    rejected=flow.state.reject_image("alice",jid,first.sha256)
    assert rejected["state"]=="IMAGE_REJECTED"
    prior=flow.state.current_image_attempt("alice",jid)
    assert prior["attempt_version"]==1 and prior["state"]=="REJECTED"
    key=uuid4().hex
    retry=flow.begin_image_retry("alice",jid,first.sha256,key)
    second=flow.state.get("alice",jid)
    assert retry["attempt_version"]==2 and retry["state"]=="REQUESTED"
    assert second["state"]=="PROMPT_READY"
    for field in ("copy_sha","review_sha","approval_sha","analysis_json",
                  "research_json","copy_json","prompt_json","generation"):
        assert second[field]==rejected[field]
    archived=flow.root/"outputs"/jid/"attempts"/f"v1-{first.sha256}.png"
    assert archived.is_file() and hashlib.sha256(archived.read_bytes()).hexdigest()==first.sha256
    assert flow.begin_image_retry("alice",jid,first.sha256,key)==retry
    with pytest.raises(LiveGateError,match="IMAGE_RETRY_STALE_REJECTION"):
        flow.begin_image_retry("alice",jid,first.sha256,uuid4().hex)
    bytes_=png((111,142,177),size=resolve_size_choice("4:5")[1].native)
    request=flow.image_input("alice",jid)
    new=BackendGeneratedImage(image_bytes=bytes_,mime_type="image/png",
        width=request.layout_selection and 1152,height=1440,
        sha256=hashlib.sha256(bytes_).hexdigest(),job_id=jid,
        copy_revision=request.copy_revision,copy_hash=request.copy_hash,mock=True,
        receipt={"mode":"OFFLINE_FIXTURE","provider_calls":0})
    fresh=flow.accept_image_result("alice",jid,new,offline=True)
    assert fresh["image_sha"]!=first.sha256
    assert flow.state.current_image_attempt("alice",jid)["attempt_version"]==2
    flow.state.approve_image("alice",jid,new.sha256)
    done=flow.compose("alice",jid,font_path=FONT)
    assert done["state"]=="COMPLETED"
    assert flow.state.current_image_attempt("alice",jid)["state"]=="COMPLETED"
    assert archived.read_bytes()==first.image_bytes
    assert owner.calls==["analyze","research","copy","prompt"]


def test_image_retry_ledger_rejects_ambiguous_queue(tmp_path):
    flow,jid,_,first=ready(tmp_path)
    flow.state.reject_image("alice",jid,first.sha256)
    q=LiveQueue(tmp_path/"queue.sqlite")
    payload=digest({"approved":first.sha256})
    row,new=q.enqueue(actor="alice",job_id=jid,stage="image",
                      context_sha=payload,mode="LIVE")
    assert new
    with pytest.raises(LiveGateError,match="IMAGE_RETRY_OUTSTANDING_OR_UNKNOWN"):
        q.assert_image_retry_safe("alice",jid)
    claimed=q.claim()
    assert claimed["id"]==row["id"]
    q.interrupt(row["id"],"UNSURE")
    with pytest.raises(LiveGateError,match="IMAGE_RETRY_OUTSTANDING_OR_UNKNOWN"):
        q.assert_image_retry_safe("alice",jid)


def test_freeform_retry_archives_original_owner_receipt_and_image(tmp_path):
    flow,jid=prepare_service(tmp_path)
    flow.prepare("alice",jid,{**sample_input(),"image_size":"3:4",
                              "generation_mode":"freeform"},template_profile="A")
    owner=FakeOwner()
    text=flow.text("alice",jid,owner,offline=True)
    flow.state.approve_copy("alice",jid,text["generation"],text["review_sha"])
    flow.prompt("alice",jid,owner,offline=True)
    request=flow.image_input("alice",jid)
    native=resolve_size_choice("3:4")[1].native
    raw=png((95,115,135),size=native)
    first=BackendGeneratedImage(
        image_bytes=raw,mime_type="image/png",width=native[0],height=native[1],
        sha256=hashlib.sha256(raw).hexdigest(),job_id=jid,
        copy_revision=request.copy_revision,copy_hash=request.copy_hash,
        mock=True,receipt={"state":"succeeded","generation_mode":"freeform",
                           "mode":"OFFLINE_FIXTURE","provider_calls":0})
    flow.accept_image_result("alice",jid,first,offline=True)
    current=flow.state.current_image_attempt("alice",jid)
    assert current["candidate_receipt_sha"] is not None
    owner_receipt=(flow.root/"outputs"/jid/"owner_candidate_receipt.json").read_bytes()
    assert hashlib.sha256(owner_receipt).hexdigest()==current["candidate_receipt_sha"]
    flow.state.reject_image("alice",jid,first.sha256)
    retry=flow.begin_image_retry("alice",jid,first.sha256,uuid4().hex)
    assert retry["attempt_version"]==2
    assert (flow.root/"outputs"/jid/"attempts"/"v1-receipt.json").read_bytes()==owner_receipt
    assert hashlib.sha256((flow.root/"outputs"/jid/"attempts"/f"v1-{first.sha256}.png").read_bytes()).hexdigest()==first.sha256
    new_raw=png((150,111,120),size=native)
    second=BackendGeneratedImage(image_bytes=new_raw,mime_type="image/png",
       width=native[0],height=native[1],sha256=hashlib.sha256(new_raw).hexdigest(),
       job_id=jid,copy_revision=request.copy_revision,copy_hash=request.copy_hash,
       mock=True,receipt={"state":"succeeded","generation_mode":"freeform",
                           "mode":"OFFLINE_FIXTURE","provider_calls":0})
    flow.accept_image_result("alice",jid,second,offline=True)
    assert flow.state.current_image_attempt("alice",jid)["candidate_receipt_sha"]!=current["candidate_receipt_sha"]
    flow.state.approve_image("alice",jid,second.sha256)
    done=flow.compose("alice",jid,font_path=None)
    assert done["state"]=="COMPLETED"
    assert flow.state.read_manifest("alice",jid)["receipt"]["generation_mode"]=="freeform"
    assert (flow.root/"outputs"/jid/"attempts"/"v1-receipt.json").read_bytes()==owner_receipt
