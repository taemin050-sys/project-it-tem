"""A5-1B local product-candidate metadata audit, read-only, rights HOLD.

No source photo or derivative thumbnail is copied to the repository, ZIP,
external Provider or GCP. Filename grouping is NOT identity/rights proof.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

from PIL import Image

CONTRACT="IT_TEM_P03_A51B_LOCAL_PRODUCT_GROUP_METADATA_ONLY_V1"
SUFFIX=re.compile(r"\s*-\d+(?:\s*\(\d+\))?$")


def normalize(s):
    return unicodedata.normalize("NFC",s)


def analyze(root:Path) -> dict:
    if not root.is_dir() or root.is_symlink():
        raise ValueError("LOCAL_PRODUCT_FOLDER_UNAVAILABLE")
    files=sorted((p for p in root.iterdir() if p.is_file()
                  and p.suffix.lower() in (".jpg",".jpeg")),
                 key=lambda p:normalize(p.name))
    if not files:
        raise ValueError("LOCAL_PRODUCT_JPG_COLLECTION_EMPTY")
    seen={}
    groups=defaultdict(list)
    errors=[]
    duplicates=[]
    for p in files:
        if p.is_symlink():
            errors.append("SYMLINK_BLOCKED")
            continue
        name=normalize(p.stem)
        key=SUFFIX.sub("",name).strip()
        if key==name or not key:
            errors.append("UNRECOGNIZED_PRODUCT_FILENAME")
            continue
        try:
            raw=p.read_bytes()
            digest=hashlib.sha256(raw).hexdigest()
            with Image.open(p) as image:
                image.verify()
            with Image.open(p) as image:
                image.load()
                detected_format=image.format
                if detected_format not in ("JPEG","MPO"):
                    raise ValueError
                width,height=image.size
                n_frames=getattr(image,"n_frames",1)
                if width<480 or height<480 or width>16000 or height>16000:
                    raise ValueError
        except (OSError,ValueError):
            errors.append("UNREADABLE_OR_INVALID_JPEG")
            continue
        if digest in seen:
            duplicates.append({
                "filename":normalize(p.name),
                "byte_duplicate_of":seen[digest],
                "sha256":digest,
            })
        else:
            seen[digest]=normalize(p.name)
        groups[key].append({
            "filename":normalize(p.name),
            "sha256":digest,
            "width_px":width,"height_px":height,
            "container_format_detected":detected_format,
            "container_frame_count":n_frames,
            "provider_input_media_gate":(
                "JPEG_CONTAINER_FORMAT_OK_RIGHTS_AND_MODEL_GATE_PENDING"
                if detected_format=="JPEG" else
                "MULTIFRAME_MPO_EXPLICIT_FRAME_SELECTION_AND_OWNER_NORMALIZATION_REQUIRED"),
            "bytes":len(raw),
            "byte_duplicate":digest in seen and seen[digest]!=normalize(p.name),
        })
    result=[]
    for group,items in sorted(groups.items()):
        unique=[]
        hashes=set()
        for item in items:
            if item["sha256"] not in hashes:
                hashes.add(item["sha256"])
                unique.append(item)
        result.append({
            "group":group,
            "filename_assumed_single_product":True,
            "independent_product_identity_verified":False,
            "jpeg_count":len(items),
            "unique_images":len(unique),
            "suggested_2_to_5_photo_filenames":[x["filename"] for x in unique[:5]]
                if len(unique)>=2 else [],
            "all_images":items,
            "rights_evidence_found_in_folder":False,
            "actual_brand_label_mask_verified":False,
            "visual_source_quality":"REVIEW_PENDING",
            "provider_upload_authorized":False,
            "team_beta_distribution_authorized":False,
            "scope":"LOCAL_READ_ONLY_QA_CANDIDATE",
            "gate":"LOCAL_REVIEW_CANDIDATE_ONLY" if len(unique)>=2
                else "INSUFFICIENT_DISTINCT_PHOTOS",
        })
    return {
        "contract":CONTRACT,
        "file_count":len(files),
        "groups_total":len(result),
        "duplicate_bytes_pairs":len(duplicates),
        "duplicates":duplicates,
        "readable_unique_photo_count":len(seen),
        "file_container_counts":{
            fmt:sum(1 for items in groups.values() for x in items
                    if x["container_format_detected"]==fmt)
            for fmt in ("JPEG","MPO")
        },
        "multi_frame_mpo_files":sum(
            1 for items in groups.values() for x in items
            if x["container_format_detected"]=="MPO"
            and x["container_frame_count"]>1
        ),
        "mpo_first_frame_automatically_selected":False,
        "mpo_canonicalized_or_exported":False,
        "invalid_files":errors,
        "groups":result,
        "grouping_basis":"NORMALIZED_FILENAME_ONLY_NOT_IDENTITY_VERIFICATION",
        "copyright_and_brand_use":"NOT_AUDITED",
        "source_image_copies_exported":False,
        "actual_brand_mask_verified":False,
        "external_provider_allowed":False,
        "team_broadcast_allowed":False,
        "full_feature_beta_visual_acceptance":"HOLD",
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path)
    args=p.parse_args()
    source=args.source.expanduser().resolve(strict=True)
    if args.out.exists() or args.out.is_symlink():
        raise SystemExit("A51B_OUTPUT_EXISTS_HOLD")
    if args.out.resolve().is_relative_to(source):
        raise SystemExit("A51B_OUTPUT_INSIDE_SOURCE_FORBIDDEN")
    record=analyze(source)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(
        record,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf8")
    print("A51B_METADATA_ONLY_LOCAL_QA_COMPLETE")
    print("JPG",record["file_count"],"PRODUCT_NAME_GROUPS",record["groups_total"],
          "BYTE_DUPLICATE_PAIRS",record["duplicate_bytes_pairs"])
    print("LOCAL_GROUPS_WITH_2_TO_5_DISTINCT",sum(
        x["unique_images"]>=2 for x in record["groups"]))
    print("NO_IMAGES_EXPORTED; NO_RIGHTS_VERIFIED; NO_PROVIDER_TRANSFER")


if __name__=="__main__":
    main()
