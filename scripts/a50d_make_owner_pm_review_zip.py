"""Deterministic non-executable A5-0D Owner/PM decision handoff bundle.

Only allowlisted public synthetic QA PNG and review documents.
No font files, tokens, databases, source code, credentials or server configs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DOCS=ROOT/"docs/integration"
M=DOCS/"evidence/A50_20261110"
E=DOCS/"evidence/A50D_20261110"
ALLOW=[
    (DOCS/"BP18_A50D_OWNER_PM_PROFILE_V3_DECISION_PACKET_20261110.md","README_REVIEW_ONLY.md"),
    (DOCS/"BP18_A50D_OWNER_PM_DECISION_REGISTER_20261110.csv","OWNER_PM_DECISION_REGISTER.csv"),
    (DOCS/"BP18_A50D_PROFILE_V3_REVIEW_ONLY_CONTRACT_20261110.json","PROFILE_V3_DRAFT_NOT_APPROVED.json"),
    (E/"A50D_GEOMETRY_AND_DECISION_PREFLIGHT.json","EVIDENCE/GEOMETRY_AND_REVIEW_PREFLIGHT.json"),
    (E/"A50D_EXISTING_FE_PRETENDARD_LICENSE_CANDIDATE.json","EVIDENCE/EXISTING_FE_FONT_LICENSE_CANDIDATE.json"),
    (M/"A50_OWNER_PM_4UP_COMPARISON.png","VISUALS/00_ORIGINAL_AND_A_B_C_4UP.png"),
    (M/"A41_ORIGINAL_WITHOUT_CTA.png","VISUALS/01_ORIGINAL_V2_NO_CTA.png"),
]
for label in ("A_EDITORIAL_CENTER","B_EDITORIAL_LEFT","C_CONTRAST_ACTION"):
    ALLOW.append((M/f"{label}.png",f"VISUALS/{label}.png"))
    for width in (360,390):
        ALLOW.append((M/f"{label}_mobile_{width}.png",
                      f"VISUALS/MOBILE_{width}/{label}.png"))

def sha(data:bytes)->str:return hashlib.sha256(data).hexdigest()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    dest=args.output
    dest.parent.mkdir(parents=True,exist_ok=True)
    assert len(ALLOW)==16
    assert not dest.exists(), "A50D_REVIEW_BUNDLE_IMMUTABLE_EXISTS"
    entries=[]
    for src,entry in ALLOW:
        assert src.is_file() and not src.is_symlink(), f"MISSING_OR_LINK:{src}"
        assert src.resolve().is_relative_to(DOCS.resolve()),"OUTSIDE_TRACK_A_DOCS"
        assert not entry.lower().endswith((".ttf",".otf",".woff2",".sqlite",".db",".env",".key"))
        data=src.read_bytes()
        assert data
        if src.suffix in (".md",".csv",".json"):
            text=data.decode("utf-8")
            assert "OPENAI_API_KEY=" not in text
            assert "sk-proj-" not in text
        entries.append((entry,data))
    entries.sort(key=lambda x:x[0])
    manifest="\n".join(f"{sha(data)}  {name}" for name,data in entries)+"\n"
    policy={
        "bundle_type":"IT_TEM_A5_0D_OWNER_PM_REVIEW_ONLY_V1",
        "source_c_audit_accepted_head":"3842db04123fc8a8c681a2bf50c90dc82464c143",
        "owner_signoff":"MISSING",
        "pm_signoff":"MISSING",
        "profile_v3_implementation":"NOT_AUTHORIZED",
        "mock_images_are_synthetic":True,
        "real_product_quality":"NOT_AUDITED",
        "commercial_font_approval":"HOLD",
        "cta_9x16_policy":"DECISION_PENDING_PM_OWNER",
        "gcp_deploy":"HOLD",
        "paid_worker":"HOLD",
        "release":"NOT_RELEASE_READY",
        "content_manifest_sha256":sha(manifest.encode()),
        "file_count":len(entries),
    }
    entries += [
        ("SHA256_CONTENT_MANIFEST.txt",manifest.encode("utf-8")),
        ("BUNDLE_CONDITIONS.json",
          (json.dumps(policy,ensure_ascii=False,indent=2,sort_keys=True)+"\n").encode("utf-8")),
    ]
    tmp=dest.with_suffix(".zip.incomplete")
    assert not tmp.exists()
    with zipfile.ZipFile(tmp,mode="x",compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,data in sorted(entries):
            zi=zipfile.ZipInfo(name,date_time=(2026,11,10,0,0,0))
            zi.compress_type=zipfile.ZIP_DEFLATED
            zi.external_attr=0o644<<16
            z.writestr(zi,data,compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
    with zipfile.ZipFile(tmp) as z:
        assert z.testzip() is None
        names=set(z.namelist())
        assert "BUNDLE_CONDITIONS.json" in names
        assert len(names)==18
        for name,data in entries:
            assert z.read(name)==data
    tmp.rename(dest)
    print("A50D_OWNER_PM_BUNDLE_REVIEW_ONLY_READY")
    print("ZIP_PATH",dest.resolve())
    print("ZIP_SHA256",sha(dest.read_bytes()))
    print("BUNDLE_FILES",len(entries),"SIGNED_APPROVALS",0)
if __name__=="__main__":main()
