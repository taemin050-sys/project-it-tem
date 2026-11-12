"""BP13 real decoder contract: MPO primary frame, MIME, metadata, limits and provenance."""
from io import BytesIO
import hashlib

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageCms

from src.serving.main import create_app


def mpo(*,exif=None,icc=None):
    first=Image.new("RGB",(13,9),(180,35,65))
    second=Image.new("RGB",(7,5),(15,150,210))
    target=BytesIO()
    kwargs={"format":"MPO","save_all":True,"append_images":[second],"quality":95}
    if exif is not None:kwargs["exif"]=exif
    if icc is not None:kwargs["icc_profile"]=icc
    first.save(target,**kwargs)
    return target.getvalue()


def create(client,data,name="TEST.MPO",mime="application/octet-stream"):
    valid=BytesIO()
    Image.new("RGB",(16,12),(30,70,90)).save(valid,format="PNG")
    return client.post("/api/v1/jobs",files=[
        ("product_images",(name,data,mime)),
        ("product_images",("b.png",valid.getvalue(),"image/png")),
    ])


@pytest.mark.parametrize("name,mime",[
    ("photo.MPO","image/jpeg"),("photo.mpo","image/mpo"),
    ("photo.MpO","application/octet-stream"),("photo.mpo",""),
])
def test_mpo_primary_as_jpeg_with_source_provenance(tmp_path,name,mime):
    raw=mpo()
    with TestClient(create_app(storage_root=tmp_path/"jobs")) as client:
        result=create(client,raw,name,mime)
        assert result.status_code==201,result.text
        first=result.json()["assets"][0]
        assert first["content_type"]=="image/jpeg"
        assert first["original_filename"]==name
        p=first["source_provenance"]
        assert p["selected_frame"]==0 and p["source_frame_count"]==2
        assert p["original_sha256"]==hashlib.sha256(raw).hexdigest()
        assert p["converted_sha256"]==first["sha256"]
        binary=client.get("/api/v1/jobs/"+result.json()["job_id"]+
                           "/assets/"+first["asset_id"]).content
        assert hashlib.sha256(binary).hexdigest()==first["sha256"]
        with Image.open(BytesIO(binary)) as pic:
            assert pic.format=="JPEG" and pic.size==(13,9)
            assert pic.getexif().get(274) is None
            assert getattr(pic,"n_frames",1)==1


def test_mpo_orientation_and_srgb_without_private_exif(tmp_path):
    exif=Image.Exif();exif[274]=6;exif[315]="PRIVATE_NAME"
    icc=ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    with TestClient(create_app(storage_root=tmp_path/"jobs")) as client:
        result=create(client,mpo(exif=exif,icc=icc))
        assert result.status_code==201,result.text
        first=result.json()["assets"][0]
        assert first["width"]==9 and first["height"]==13
        assert first["source_provenance"]["source_orientation"]==6
        assert len(first["source_provenance"]["source_icc_sha256"])==64
        raw=client.get("/api/v1/jobs/"+result.json()["job_id"]+
                       "/assets/"+first["asset_id"]).content
        with Image.open(BytesIO(raw)) as image:
            assert image.size==(9,13) and not image.getexif()
            assert not image.info.get("icc_profile")


@pytest.mark.parametrize("name,content,mime",[
    ("fake.mpo",b"fake","image/mpo"),
    ("fake.MPO",b"\xff\xd8random","image/jpeg"),
    ("photo.png",mpo(),"image/png"),
    ("photo.mpo",mpo()[:100],"image/jpeg"),
    ("photo.jpg",mpo(),"image/jpeg"),
    ("photo.mpo",mpo(),"image/png"),
])
def test_mpo_spoof_and_corruption_rejected(tmp_path,name,content,mime):
    with TestClient(create_app(storage_root=tmp_path/"jobs")) as client:
        result=create(client,content,name,mime)
        assert result.status_code==422
        assert not list((tmp_path/"jobs").iterdir())


def test_mpo_pixel_and_byte_boundaries(tmp_path,monkeypatch):
    import src.serving.job_api as endpoint
    raw=mpo()
    with monkeypatch.context() as patch:
        patch.setattr(endpoint,"MAX_FILE_BYTES",len(raw)-1)
        with TestClient(create_app(storage_root=tmp_path/"first")) as client:
            assert create(client,raw).status_code==413
    with monkeypatch.context() as patch:
        patch.setattr(endpoint,"MAX_PIXELS",13*9-1)
        with TestClient(create_app(storage_root=tmp_path/"second")) as client:
            assert create(client,raw).status_code==422
