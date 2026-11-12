"""A51B MPO/JPEG source-frame fingerprint inventory. READ ONLY.

This deliberately never picks a frame or converts/writes image bytes.
Image Owner #24 must approve frame-selection and normalization before beta
Provider import, and legal-use rights remain independently required.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import unicodedata
from pathlib import Path

from PIL import Image, ImageCms, ImageOps

CONTRACT="IT_TEM_P03_A51BR1_MPO_FRAME_READ_ONLY_PROVENANCE_V1"


def _digest(raw:bytes)->str:
    return hashlib.sha256(raw).hexdigest()


def inspect_file(path:Path)->dict:
    path=Path(path)
    if not path.is_file() or path.is_symlink():
        raise ValueError("MPO_SOURCE_FILE_INVALID")
    original=path.read_bytes()
    if not original or len(original)>100*1024*1024:
        raise ValueError("MPO_SOURCE_BYTES_OUT_OF_BOUNDS")
    with Image.open(path) as im:
        if im.format not in ("JPEG","MPO"):
            raise ValueError("MPO_SOURCE_IMAGE_FORMAT_NOT_SUPPORTED")
        fmt=im.format
        count=getattr(im,"n_frames",1)
        if count<1 or count>16:
            raise ValueError("MPO_SOURCE_FRAME_COUNT_UNSUPPORTED")
        exif_orientation=im.getexif().get(274,1)
        icc=im.info.get("icc_profile")
        icc_sha=_digest(icc) if icc else None
        frames=[]
        for i in range(count):
            im.seek(i)
            im.load()
            if im.width*im.height>40_000_000:
                raise ValueError("MPO_FRAME_PIXEL_LIMIT_EXCEEDED")
            # Hash decoded RGB identity WITHOUT exporting any frame;
            # no implicit frame 0 selection or unapproved sRGB conversion.
            decoded=im.convert("RGB")
            frames.append({
                "index":i,
                "width_px":im.width,
                "height_px":im.height,
                "decoded_rgb_pixel_sha256":_digest(decoded.tobytes()),
            })
    return {
        "filename":unicodedata.normalize("NFC",path.name),
        "original_sha256":_digest(original),
        "original_bytes":len(original),
        "actual_container":fmt,
        "source_frame_count":count,
        "source_exif_orientation":exif_orientation,
        "source_icc_sha256":icc_sha,
        "decoded_source_frames":frames,
        "selected_frame":None,
        "conversion_version":None,
        "normalized_image_sha256":None,
        "frame_user_confirmation":"REQUIRED_FOR_MPO_AND_NOT_RECEIVED" if fmt=="MPO" else "SINGLE_FRAME_NO_SELECTION_REQUIRED",
        "frontend_input_policy":"MPO_PENDING_IMAGE_OWNER_PM_VERSIONED_CONTRACT" if fmt=="MPO" else "JPEG_SOURCE_MIME_CHECK_REQUIRED",
        "original_file_mutated":False,
        "source_image_bytes_exported":False,
        "provider_upload_authorized":False,
        "rights_and_product_identity":"NOT_AUDITED",
    }


def inspect_root(root:Path)->dict:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("MPO_ROOT_INVALID")
    paths=sorted((p for p in root.iterdir() if p.is_file() and
                  p.suffix.lower() in (".jpg",".jpeg",".mpo")),key=lambda p:p.name)
    result=[inspect_file(p) for p in paths]
    return {
        "contract":CONTRACT,
        "total_files":len(result),
        "actual_jpeg":sum(x["actual_container"]=="JPEG" for x in result),
        "actual_mpo":sum(x["actual_container"]=="MPO" for x in result),
        "total_decoded_frames":sum(x["source_frame_count"] for x in result),
        "files":result,
        "explicit_mpo_frame_selections_made":0,
        "normalized_image_outputs_created":0,
        "actual_customer_rights_approved":False,
        "external_provider_requests":0,
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    ns=p.parse_args()
    if ns.out.exists() or ns.out.is_symlink():
        raise SystemExit("MPO_OUTPUT_EXISTS")
    source=ns.source.resolve(strict=True)
    dest=ns.out.resolve()
    if dest.is_relative_to(source):
        raise SystemExit("MPO_OUTPUT_INSIDE_SOURCE_FORBIDDEN")
    record=inspect_root(source)
    ns.out.parent.mkdir(parents=True,exist_ok=True)
    ns.out.write_text(json.dumps(record,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf8")
    print("MPO_READ_ONLY_FRAME_PROBE_PASS",record["total_files"],
          record["actual_jpeg"],record["actual_mpo"],record["total_decoded_frames"])
    print("SELECTED_FRAMES=0 EXPORTED_IMAGES=0 PROVIDER_CALLS=0")


if __name__=="__main__":
    main()
