"""BP14 contract: one selected freeform or composed candidate, immutable copy and SHA."""
import hashlib
import json
from io import BytesIO

import pytest
from PIL import Image

from demo_staging.live.contracts import LiveGateError
from src.image_generation.backend_adapter import BackendGeneratedImage
from src.image_generation.size_selection import resolve_size_choice
from tests.demo_live.test_live_contracts import sample_input
from tests.demo_live.test_pipeline import FONT,FakeOwner,png,prepare_service


@pytest.mark.parametrize("selected",["composed","freeform"])
@pytest.mark.parametrize("ratio",["3:4","4:5","9:16"])
def test_single_image_mode_freezes_and_exports_with_no_double_text(tmp_path,selected,ratio):
    flow,jid=prepare_service(tmp_path)
    inputs={**sample_input(),"image_size":ratio,"generation_mode":selected}
    flow.prepare("alice",jid,inputs,template_profile="A")
    owner=FakeOwner()
    text=flow.text("alice",jid,owner,offline=True)
    flow.state.approve_copy("alice",jid,text["generation"],text["review_sha"])
    flow.prompt("alice",jid,owner,offline=True)
    req=flow.image_input("alice",jid)
    assert req.copy_hash==text["copy_sha"] and req.copy_revision==text["generation"]
    assert req.layout_selection.aspect_ratio==ratio
    if selected=="freeform":
        assert req.generation_mode=="freeform" and req.copy_output==json.loads(text["copy_json"])
        assert req.safe_zone is None
    else:
        assert req.generation_mode is None
    native=resolve_size_choice(ratio)[1].native
    raw=png((177,201,220),size=native)
    receipt={"mode":"OFFLINE_FIXTURE","provider_calls":0}
    if selected=="freeform":
        receipt.update({"state":"succeeded","generation_mode":"freeform"})
    generated=BackendGeneratedImage(image_bytes=raw,mime_type="image/png",
        width=native[0],height=native[1],sha256=hashlib.sha256(raw).hexdigest(),
        job_id=jid,copy_revision=req.copy_revision,copy_hash=req.copy_hash,
        mock=True,receipt=receipt)
    candidate=flow.accept_image_result("alice",jid,generated,offline=True)
    assert candidate["state"]=="IMAGE_REVIEW_REQUIRED"
    flow.state.approve_image("alice",jid,generated.sha256)
    if selected=="freeform":
        with pytest.raises(LiveGateError,match="FREEFORM_MUST_NOT_COMPOSE_TEXT"):
            flow.compose("alice",jid,font_path=FONT,layout={"text_regions":{}})
    completed=flow.compose("alice",jid,font_path=None if selected=="freeform" else FONT)
    assert completed["state"]=="COMPLETED"
    assert completed["final_sha"]!=None and completed["caption_sha"]!=None
    assert flow.validate_final_artifacts("alice",jid)==completed
    manifest=flow.state.read_manifest("alice",jid)
    assert manifest["receipt"].get("generation_mode","composed")==selected
    if selected=="freeform":
        assert manifest["receipt"]["rendering"]=="provider_drawn_text"
        assert manifest["receipt"].get("font_sha256") is None
    else:
        assert manifest["receipt"]["font_sha256"]
    target=flow.root/"outputs"/jid/"final.png"
    with Image.open(BytesIO(target.read_bytes())) as im:
        assert im.size==resolve_size_choice(ratio)[1].final
    assert owner.calls==["analyze","research","copy","prompt"]


def test_freeform_rejects_candidate_lacking_owner_mode_receipt(tmp_path):
    flow,jid=prepare_service(tmp_path)
    flow.prepare("alice",jid,{**sample_input(),"image_size":"4:5",
                              "generation_mode":"freeform"},template_profile="A")
    owner=FakeOwner()
    review=flow.text("alice",jid,owner,offline=True)
    flow.state.approve_copy("alice",jid,review["generation"],review["review_sha"])
    flow.prompt("alice",jid,owner,offline=True)
    req=flow.image_input("alice",jid)
    raw=png((180,200,225),size=resolve_size_choice("4:5")[1].native)
    candidate=BackendGeneratedImage(image_bytes=raw,mime_type="image/png",
        width=1152,height=1440,sha256=hashlib.sha256(raw).hexdigest(),
        job_id=jid,copy_revision=req.copy_revision,copy_hash=req.copy_hash,
        mock=True,receipt={"mode":"OFFLINE_FIXTURE","provider_calls":0})
    with pytest.raises(LiveGateError,match="FREEFORM_OWNER_RECEIPT_UNVERIFIED"):
        flow.accept_image_result("alice",jid,candidate,offline=True)
