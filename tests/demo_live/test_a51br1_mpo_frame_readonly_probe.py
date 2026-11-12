"""A51B-R1 actual MPO frame-index audit; no media conversion."""
from __future__ import annotations
import hashlib
from io import BytesIO
from pathlib import Path
import importlib.util

import pytest
from PIL import Image

ROOT=Path(__file__).resolve().parents[2]


def module():
    spec=importlib.util.spec_from_file_location(
        "a51br1_mpo_frame_readonly_probe",
        ROOT/"scripts/a51br1_mpo_frame_readonly_probe.py")
    obj=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def mpo_file(path:Path):
    first=Image.new("RGB",(320,240),(200,40,50))
    second=Image.new("RGB",(320,240),(20,200,90))
    first.save(path,format="MPO",save_all=True,append_images=[second],quality=96)


def test_mpo_two_frames_have_distinct_pixel_sha_and_no_selection(tmp_path):
    p=tmp_path/"misleading.jpg"
    mpo_file(p)
    raw=p.read_bytes()
    out=module().inspect_file(p)
    assert out["actual_container"]=="MPO"
    assert out["source_frame_count"]==2
    assert out["original_sha256"]==hashlib.sha256(raw).hexdigest()
    assert out["decoded_source_frames"][0]["decoded_rgb_pixel_sha256"]!=out[
        "decoded_source_frames"][1]["decoded_rgb_pixel_sha256"]
    assert out["selected_frame"] is None
    assert out["normalized_image_sha256"] is None
    assert out["provider_upload_authorized"] is False
    assert p.read_bytes()==raw


def test_read_only_two_formats_and_no_images_exported(tmp_path):
    p=tmp_path/"B-1.jpg"
    mpo_file(p)
    Image.new("RGB",(320,240),(10,20,40)).save(tmp_path/"A-1.jpg","JPEG")
    original={x.name:hashlib.sha256(x.read_bytes()).hexdigest()
              for x in tmp_path.iterdir()}
    observed=module().inspect_root(tmp_path)
    assert observed["total_files"]==2
    assert observed["actual_jpeg"]==1 and observed["actual_mpo"]==1
    assert observed["total_decoded_frames"]==3
    assert observed["explicit_mpo_frame_selections_made"]==0
    assert observed["normalized_image_outputs_created"]==0
    assert observed["external_provider_requests"]==0
    assert original=={x.name:hashlib.sha256(x.read_bytes()).hexdigest()
                     for x in tmp_path.iterdir()}


def test_invalid_filename_mime_is_not_implicit_frame_confirmation(tmp_path):
    p=tmp_path/"no-frame-selection.jpg"
    mpo_file(p)
    x=module().inspect_file(p)
    assert x["frame_user_confirmation"]=="REQUIRED_FOR_MPO_AND_NOT_RECEIVED"
    assert x["frontend_input_policy"]=="MPO_PENDING_IMAGE_OWNER_PM_VERSIONED_CONTRACT"


def test_unreadable_image_refused_and_no_source_changes(tmp_path):
    p=tmp_path/"invalid.jpg"
    p.write_bytes(b"not a photo")
    before=p.read_bytes()
    with pytest.raises(Exception):
        module().inspect_file(p)
    assert p.read_bytes()==before


def test_symlink_as_source_is_rejected(tmp_path):
    p=tmp_path/"valid.jpg"
    Image.new("RGB",(320,240)).save(p,"JPEG")
    link=tmp_path/"shortcut.jpg"
    link.symlink_to(p)
    with pytest.raises(ValueError,match="MPO_SOURCE_FILE_INVALID"):
        module().inspect_file(link)
