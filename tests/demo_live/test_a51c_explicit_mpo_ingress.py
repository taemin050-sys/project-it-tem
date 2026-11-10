"""A51C experimental explicit-frame MPO ingestion, not production-activated.

All photo material is synthetic. Existing Owner/FE v2 behavior never modified.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from pathlib import Path
import json

from PIL import Image, ImageCms
from pydantic import ValidationError
import pytest

from demo_staging.live.contracts import LiveGateError
from demo_staging.live.a51c_explicit_mpo_ingress import (
    inspect_source,preview_frame,normalize_selected_source,
    CONTRACT,CONFIRM,FrameSelection,
)
from src.serving.job_store import JobStore,ValidatedUpload


def synthetic_mpo(*, colors=((120,25,45),(19,160,80)),exif=None):
    first=Image.new("RGB",(320,220),colors[0])
    second=Image.new("RGB",(310,200),colors[1])
    buffer=BytesIO()
    kws={"format":"MPO","save_all":True,"append_images":[second],"quality":96}
    if exif is not None:kws["exif"]=exif
    first.save(buffer,**kws)
    return buffer.getvalue()


def selection(raw,*,i=0,sha=None,request_sha="a"*64,preview_sha=None):
    source=inspect_source(raw,filename="hidden-mpo.jpg",mime="image/jpeg")
    info=source["candidate_frames"][i]
    return FrameSelection(
        contract=CONTRACT,
        original_sha256=sha or source["original_sha256"],
        source_frame_count=source["source_frame_count"],
        selected_frame_index=i,
        selected_preview_sha256=preview_sha or info["preview_png_sha256"],
        upload_request_sha256=request_sha,
        confirmation=CONFIRM,
    )


@pytest.mark.parametrize("selected_index", [0,1])
def test_mpo_choice_0_and_1_produces_correct_independent_provenance(selected_index):
    raw=synthetic_mpo()
    source=inspect_source(raw,filename="unrecognized-jpg-container.jpg",mime="image/jpeg")
    assert source["source_frame_count"]==2
    assert source["implicit_frame_selected"] is False
    assert source["normalized_output_created"] is False
    assert source["candidate_frames"][0]["decoded_rgb_sha256"]!=source[
        "candidate_frames"][1]["decoded_rgb_sha256"]
    choice=selection(raw,i=selected_index)
    preview=preview_frame(raw,filename="hidden-mpo.jpg",mime="image/jpeg",index=selected_index)
    assert sha256(preview).hexdigest()==choice.selected_preview_sha256
    norm=normalize_selected_source(
        raw,filename="hidden-mpo.jpg",mime="image/jpeg",selected=choice,
        expected_upload_request_sha256="a"*64)
    assert isinstance(norm,ValidatedUpload)
    assert norm.content_type=="image/jpeg"
    assert norm.sha256==sha256(norm.data).hexdigest()
    assert norm.provenance["original_sha256"]==sha256(raw).hexdigest()
    assert norm.provenance["selected_frame"]==selected_index
    assert norm.provenance["normalized_sha256"]==norm.sha256
    assert norm.provenance["external_provider_transfer_permitted"] is False
    with Image.open(BytesIO(norm.data)) as result:
        assert result.format=="JPEG"
        assert result.size==((320,220) if selected_index==0 else (310,200))
        assert getattr(result,"n_frames",1)==1
        assert not result.getexif()
        assert not result.info.get("icc_profile")
    assert raw==synthetic_mpo()


def test_contrast_between_selected_frames_is_not_ignored():
    raw=synthetic_mpo()
    a=normalize_selected_source(raw,filename="hidden-mpo.jpg",mime="image/jpeg",
                                selected=selection(raw,i=0),
                                expected_upload_request_sha256="a"*64)
    b=normalize_selected_source(raw,filename="hidden-mpo.jpg",mime="image/jpeg",
                                selected=selection(raw,i=1),
                                expected_upload_request_sha256="a"*64)
    assert a.sha256!=b.sha256
    assert a.provenance["original_sha256"]==b.provenance["original_sha256"]
    assert a.provenance["selected_frame"]==0
    assert b.provenance["selected_frame"]==1


@pytest.mark.parametrize("attack",[
    "wrong_sha","wrong_preview","wrong_context","bad_confirmation",
    "wrong_frame_count","invalid_index","extra_field",
])
def test_mpo_selection_invalid_or_not_explicit_fails_closed(attack):
    raw=synthetic_mpo()
    base=selection(raw).model_dump()
    if attack=="wrong_sha":base["original_sha256"]="b"*64
    elif attack=="wrong_preview":base["selected_preview_sha256"]="b"*64
    elif attack=="wrong_context":base["upload_request_sha256"]="b"*64
    elif attack=="bad_confirmation":base["confirmation"]="IMPLICIT_DEFAULT_FRAME_ZERO"
    elif attack=="wrong_frame_count":base["source_frame_count"]=3
    elif attack=="invalid_index":base["selected_frame_index"]=2
    elif attack=="extra_field":base["user_says_provider_permission"]="true"
    if attack=="extra_field":
        with pytest.raises(ValidationError):
            FrameSelection.model_validate(base)
        return
    try:choice=FrameSelection.model_validate(base)
    except ValidationError:
        return
    with pytest.raises(LiveGateError,match="A51C_"):
        normalize_selected_source(raw,filename="hidden-mpo.jpg",mime="image/jpeg",
                                  selected=choice,
                                  expected_upload_request_sha256="a"*64)


@pytest.mark.parametrize("fake_name,mime",[
    ("product.png","image/jpeg"),("product.jpg","image/png"),
    ("../photo.jpg","image/jpeg"),("photo.jpg","text/plain"),
])
def test_mpo_pre_ingress_rejects_suffix_mime_or_path_spoof(fake_name,mime):
    raw=synthetic_mpo()
    with pytest.raises(LiveGateError,match="A51C_"):
        inspect_source(raw,filename=fake_name,mime=mime)


def test_frame_selection_is_a_separate_required_argument():
    raw=synthetic_mpo()
    with pytest.raises(TypeError):
        normalize_selected_source(raw,filename="hidden-mpo.jpg",mime="image/jpeg",
                                  expected_upload_request_sha256="a"*64)
    assert inspect_source(raw,filename="hidden-mpo.jpg",mime="image/jpeg")[
        "implicit_frame_selected"] is False


def test_no_duplicate_candidate_job_and_immutable_source_sha_in_b0(tmp_path):
    raw=synthetic_mpo()
    request_key="a"*64
    norm=normalize_selected_source(raw,filename="hidden-mpo.jpg",mime="image/jpeg",
                                   selected=selection(raw,i=1),
                                   expected_upload_request_sha256=request_key)
    photo=Image.new("RGB",(320,220),(50,40,190))
    out=BytesIO();photo.save(out,format="JPEG")
    other=ValidatedUpload("another.jpg","image/jpeg",out.getvalue(),320,220,
                          sha256(out.getvalue()).hexdigest(),None)
    store=JobStore(tmp_path/"isolated-demo-jobstore")
    job=store.create_job([norm,other],[])
    assert job["status"]=="INPUTS_VALIDATED"
    assets=job["assets"]
    assert len(assets)==2
    assert assets[0]["source_provenance"]["selected_frame"]==1
    assert assets[0]["source_provenance"]["upload_request_sha256"]==request_key
    assert assets[0]["source_provenance"]["original_sha256"]==sha256(raw).hexdigest()
    assert assets[0]["source_provenance"]["brand_rights_accepted"] is False
    assert store.get_job(job["job_id"])==job
    assert not any(raw==p.read_bytes() for p in (tmp_path/"isolated-demo-jobstore").rglob("*.jpg"))


def test_wrong_raw_container_jailed_before_any_selection():
    data=BytesIO()
    Image.new("RGB",(100,100)).save(data,format="JPEG")
    with pytest.raises(LiveGateError,match="A51C_"):
        inspect_source(data.getvalue(),filename="misnamed.mpo",mime="image/jpeg")

def test_mpo_exif_rotation_and_icc_normalization_matches_preview_intent():
    exif=Image.Exif()
    exif[274]=6
    exif[315]="PRIVATE_PHOTO_PHOTOGRAPHER_EXIF_NOT_TO_EXPORT"
    first=Image.new("RGB",(320,220),(90,80,30))
    second=Image.new("RGB",(310,200),(30,100,150))
    icc=ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    buf=BytesIO()
    first.save(buf,format="MPO",save_all=True,
               append_images=[second],quality=93,exif=exif,
               icc_profile=icc)
    raw=buf.getvalue()
    info=inspect_source(raw,filename="lookalike.jpg",mime="image/jpeg")
    assert info["source_frame_count"]==2
    choice=selection(raw,i=0)
    encoded=preview_frame(raw,filename="lookalike.jpg",mime="image/jpeg",index=0)
    with Image.open(BytesIO(encoded)) as preview:
        assert preview.size==(220,320)
        assert preview.format=="PNG"
    normalized=normalize_selected_source(
        raw,filename="lookalike.jpg",mime="image/jpeg",
        selected=choice,expected_upload_request_sha256="a"*64)
    with Image.open(BytesIO(normalized.data)) as image:
        assert image.size==(220,320)
        assert image.format=="JPEG"
        assert not image.getexif()
        assert not image.info.get("icc_profile")
    assert normalized.provenance["source_exif_orientation"]==6
    assert normalized.provenance["source_icc_sha256"]==sha256(icc).hexdigest()
    assert normalized.provenance["exif_icc_private_metadata_removed"] is True
    assert b"PRIVATE_PHOTO_PHOTOGRAPHER" not in normalized.data
