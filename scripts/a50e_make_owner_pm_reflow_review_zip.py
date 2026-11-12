"""A5-0E unsigned Owner/PM revised-layout review bundle, v2 filename only.

Fixed allowlist, deterministic ZIP, fail if destination exists, no font binary,
no operating data/secrets, and NEVER changes A50D v1 ZIP or signed records.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DOCS=ROOT/"docs/integration"
A50=DOCS/"evidence/A50_20261110"
A50D=DOCS/"evidence/A50D_20261110"
E=DOCS/"evidence/A50E_20261110"
SOURCE=[
    (DOCS/"BP18_A50E_CTA_PRODUCT_REFLOW_OWNER_PM_DECISION_V2_20261110.md",
       "README_REVISED_A50E_REVIEW_ONLY.md"),
    (DOCS/"BP18_A50DR1_SIGNED_DECISION_PRESERVATION_CONTRACT_20261110.md",
       "APPROVAL_RECORD_PROTECTION_R1.md"),
    (DOCS/"BP18_A50D_OWNER_PM_PROFILE_V3_DECISION_PACKET_20261110.md",
       "A50D_ORIGINAL_DECISION_DOSSIER.md"),
    (DOCS/"BP18_A50D_OWNER_PM_DECISION_REGISTER_20261110.csv",
       "D50_DECISION_REGISTER_UNSIGNED.csv"),
    (DOCS/"BP18_A50D_PROFILE_V3_REVIEW_ONLY_CONTRACT_20261110.json",
       "D50_PROFILE_V3_DRAFT_NOT_APPROVED.json"),
    (A50D/"A50D_GEOMETRY_AND_DECISION_PREFLIGHT.json",
       "EVIDENCE/BEFORE_A50D_GEOMETRY.json"),
    (A50D/"A50D_EXISTING_FE_PRETENDARD_LICENSE_CANDIDATE.json",
       "EVIDENCE/EXISTING_FE_FONT_CANDIDATE.json"),
    (E/"A50E_REFLOW_DESIGN_MANIFEST.json",
       "EVIDENCE/A50E_REFLOW_DESIGN_MANIFEST.json"),
    (E/"A50E_SYNTHETIC_STRESS_RESULTS.json",
       "EVIDENCE/A50E_SYNTHETIC_STRESS_RESULTS.json"),
    (A50/"A50_OWNER_PM_4UP_COMPARISON.png",
       "VISUALS/ORIGINAL_A_B_C_4UP.png"),
    (A50/"B_EDITORIAL_LEFT.png",
       "VISUALS/B_EDITORIAL_LEFT_ORIGINAL_UNCHANGED.png"),
    (E/"A50E_A_C_BEFORE_AFTER_COMPARISON.png",
       "VISUALS/A_C_BEFORE_AFTER_4UP.png"),
]
for name in ("A_REFLOW_EDITORIAL_CENTER","C_REFLOW_CONTRAST_ACTION"):
    SOURCE.append((E/f"{name}.png",f"VISUALS/{name}.png"))
    for width in (360,390):
        SOURCE.append((E/f"{name}_mobile_{width}.png",
                       f"VISUALS/MOBILE_{width}/{name}.png"))
        SOURCE.append((E/f"{name}_mobile_{width}_crop12_simulation.png",
                       f"VISUALS/MOBILE_{width}_SIMULATED_CROP12/{name}.png"))


def sha(data:bytes)->str:
    return hashlib.sha256(data).hexdigest()


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    out=a.output.expanduser().absolute()
    if out.exists() or out.is_symlink():
        raise SystemExit("A50E_ZIP_EXISTS_OR_SYMLINK_HOLD")
    out.parent.mkdir(parents=True,exist_ok=True)
    payloads=[]
    for filepath,entry in SOURCE:
        assert filepath.is_file() and not filepath.is_symlink()
        assert filepath.resolve().is_relative_to(DOCS.resolve())
        assert not entry.lower().endswith((".ttf",".otf",".woff2",".db",".sqlite",".env",".key"))
        data=filepath.read_bytes()
        assert len(data)>0
        if filepath.suffix in (".md",".csv",".json"):
            text=data.decode("utf-8")
            for forbidden in ("sk-proj-","OPENAI_API_KEY="):
                assert forbidden not in text
        payloads.append((entry,data))
    assert len(payloads)==22,len(payloads)
    # The packet must contain NO actually signed Owner/PM decisions. R1 doc
    # may describe a synthetic TEST signature string in plain text.
    contract=json.loads((DOCS/
       "BP18_A50D_PROFILE_V3_REVIEW_ONLY_CONTRACT_20261110.json").read_text())
    assert contract["owner_pm_signed"] is False
    assert contract["selected_profile"] is None
    with (DOCS/"BP18_A50D_OWNER_PM_DECISION_REGISTER_20261110.csv").open(
            newline="",encoding="utf-8") as handle:
        decisions=list(csv.DictReader(handle))
    assert len(decisions)==9
    assert all(not row["pm_signoff_ref"] and not row["image_owner_signoff_ref"]
               for row in decisions)
    payloads.sort()
    entries_manifest="\n".join(f"{sha(data)}  {name}" for name,data in payloads)+"\n"
    policy={
      "contract":"IT_TEM_P03_A50E_REVISED_UNSIGNED_OWNER_PM_ZIP_V2",
      "previous_review_zip_sha256":"fb8fb89a76a675b994aba9b62d4229a8ff715747b18486c998ea9ab41ef07eff",
      "signed_decision_records":"NOT_CREATED","owner_signoff":"MISSING",
      "pm_signoff":"MISSING","selected_profile":"NONE",
      "review_only":True,"actual_product_image":"SYNTHETIC_ONLY",
      "font_binary_included":False,"real_platform_safe_zone":"NOT_AUDITED",
      "commercial_font_approval":"HOLD",
      "profile_v3_implementation":"NOT_AUTHORIZED",
      "9x16_cta":"DECISION_PENDING_PM_OWNER",
      "gcp_qa":"HOLD","paid_worker":"HOLD","release":"NOT_RELEASE_READY",
      "payload_files":len(payloads),
      "payload_manifest_sha256":sha(entries_manifest.encode("utf-8")),
    }
    payloads += [
       ("SHA256_CONTENT_MANIFEST.txt",entries_manifest.encode("utf-8")),
       ("BUNDLE_CONDITIONS.json",(json.dumps(policy,ensure_ascii=False,
                                         indent=2,sort_keys=True)+"\n").encode("utf-8")),
    ]
    temp=out.with_suffix(out.suffix+".incomplete")
    if temp.exists() or temp.is_symlink():
        raise SystemExit("A50E_ZIP_TEMP_PATH_ALREADY_EXISTS")
    with zipfile.ZipFile(temp,"x",compression=zipfile.ZIP_DEFLATED,compresslevel=9) as zipf:
        for name,data in sorted(payloads):
            zi=zipfile.ZipInfo(name,date_time=(2026,11,10,0,0,0))
            zi.external_attr=0o644<<16
            zipf.writestr(zi,data,compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
    with zipfile.ZipFile(temp) as z:
        assert z.testzip() is None
        assert len(z.namelist())==len(payloads)
        for name,data in payloads:
            assert z.read(name)==data
    if out.exists() or out.is_symlink():
        temp.unlink(missing_ok=True)
        raise SystemExit("A50E_ZIP_DESTINATION_RACED_HOLD")
    temp.rename(out)
    print("A50E_UNSIGNED_OWNER_PM_REVIEW_PACKAGE_V2_READY")
    print("ZIP_PATH",out)
    print("ZIP_SHA256",sha(out.read_bytes()))
    print("CONTENT_FILES",policy["payload_files"],"TOTAL_ENTRIES",len(payloads))
    print("SIGNED_APPROVALS",0,"A5_1_IMPLEMENTATION_HOLD")


if __name__=="__main__":
    main()
