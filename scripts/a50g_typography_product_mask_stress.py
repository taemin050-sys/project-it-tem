"""A5-0G nonbillable typography + synthetic package-mask stress evidence.

Reuses pinned A50E A/C DESIGN proposal assets. Never a real segmentation,
platform crop certification, commercial font approval, or Owner/PM signoff.
Reads installed FE font bytes but never exports those binaries.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont

ROOT=Path(__file__).resolve().parents[1]
E50=ROOT/"docs/integration/evidence/A50E_20261110"
TYPES=("A_REFLOW_EDITORIAL_CENTER","C_REFLOW_CONTRAST_ACTION")
COPY_FIELDS=("headline","subline","cta")
FONT_HASH="3090ccde0442bb347aa7685d9ba8b17436a60682df6e8f92a9a670de14056e22"


def sha(p:Path)->str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load_design():
    spec=importlib.util.spec_from_file_location(
        "a50g_a50e_source",ROOT/"scripts/a50e_composed45_product_cta_reflow_concepts.py")
    assert spec and spec.loader
    obj=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def box_intersects(a,b)->bool:
    return a[0]<b[2] and a[2]>b[0] and a[1]<b[3] and a[3]>b[1]


def verify_ink_bbox(text,font,at,limit)->dict:
    x,y=at
    bbox=ImageDraw.Draw(Image.new("L",(1,1))).textbbox((x,y),text,font=font)
    return {"ink_bbox":list(bbox),
            "inside_assigned_region":all((
                limit[0]<=bbox[0]<bbox[2]<=limit[2],
                limit[1]<=bbox[1]<bbox[3]<=limit[3],
            ))}


def synthetic_masks(design:dict)->dict:
    x1,y1,x2,y2=design["product_target"]
    cx=(x1+x2)//2
    cta=design["regions"]["cta"]
    return {
        "compact_bottle":[(x1+30,y1+55,x2-30,y2-25)],
        "two_short_products":[(x1+8,y1+75,cx-6,y2-40),
                              (cx+6,y1+75,x2-8,y2-40)],
        "tall_package_into_cta":[(x1+25,y1+35,x2-25,cta[1]+55)],
        "wide_package_beyond_target":[(x1-55,y1+35,x2+55,y2-40)],
        "headline_overlap":[(x1+25,design["regions"]["headline"][1]+10,
                              x2-25,design["regions"]["headline"][3]-12)],
    }


def measure_masks(design):
    tests={}
    for scenario,boxes in synthetic_masks(design).items():
        target=design["product_target"]
        reasons=[]
        for box in boxes:
            if not all((target[0]<=box[0]<box[2]<=target[2],
                        target[1]<=box[1]<box[3]<=target[3])):
                reasons.append("OUTSIDE_SYNTHETIC_PRODUCT_TARGET")
            for field in COPY_FIELDS:
                if box_intersects(box,design["regions"][field]):
                    reasons.append("MASK_INTERSECTS_"+field.upper())
        expected="SYNTHETIC_NO_COLLISION" if not reasons else "GEOMETRIC_HOLD"
        tests[scenario]={
            "boxes":[list(x) for x in boxes],
            "model_data":False,
            "status":expected,
            "reasons":sorted(set(reasons)),
            "brand_label_detected":False,
        }
    assert tests["compact_bottle"]["status"]=="SYNTHETIC_NO_COLLISION"
    assert tests["two_short_products"]["status"]=="SYNTHETIC_NO_COLLISION"
    for rejected in ("tall_package_into_cta","wide_package_beyond_target",
                     "headline_overlap"):
        assert tests[rejected]["status"]=="GEOMETRIC_HOLD"
    return tests


def glyph_coverage(fontpath:Path,text:str)->dict:
    face=TTFont(str(fontpath))
    try:
        chars=set().union(*(set(table.cmap) for table in face["cmap"].tables))
    finally:
        face.close()
    needed=set(text)
    missing=sorted(x for x in needed if ord(x) not in chars)
    return {"unique_codepoints":len(needed),
            "supported":len(needed)-len(missing),
            "missing_codepoints":[f"U+{ord(c):04X}" for c in missing],
            "pass":not missing}


def measure_typography(mod,design):
    manifest={}
    for field in COPY_FIELDS:
        desired=design["font_size"][field]
        minsize={"headline":64,"subline":54,"cta":48}[field]
        weight={"headline":700,"subline":500,"cta":700}[field]
        rect=design["regions"][field]
        positions,actual=mod.fit_text(mod.COPY[field],rect,
                                     fontpath=mod.PRETENDARD,size=desired,
                                     minimum=minsize,weight=weight)
        assert len(positions)==1
        metrics=verify_ink_bbox(*positions[0],rect)
        assert metrics["inside_assigned_region"],(field,metrics)
        manifest[field]={
            "text_sha256":mod.sha_text(mod.COPY[field]),
            "font_size_native":actual,"font_size_360":round(actual/3,2),
            "font_size_390":round(actual*390/1080,2),
            "region":list(rect),
            "ink_bbox":metrics["ink_bbox"],
            "glyph_coverage":glyph_coverage(mod.PRETENDARD,mod.COPY[field]),
            "render_instructions":len(positions),
        }
        assert manifest[field]["glyph_coverage"]["pass"]
    return manifest


def render_mask_overlay(candidate:str,design:dict,tests:dict,out:Path):
    # Overlay geometry on the already accepted synthetic A/C PNG.
    # Pixels must never be treated as a real packaging segmentation.
    src=E50/(candidate+".png")
    image=Image.open(src).convert("RGB")
    assert image.size==(1080,1350)
    for scenario in ("compact_bottle","tall_package_into_cta"):
        preview=image.copy()
        dr=ImageDraw.Draw(preview)
        r=design["regions"]
        dr.rectangle(design["product_target"],outline="#337A95",width=8)
        for field,region in r.items():
            dr.rectangle(region,outline=("#A85287" if field=="cta" else "#53677B"),width=5)
        for box in tests[scenario]["boxes"]:
            dr.rectangle(box,outline=("#A13131" if tests[scenario]["status"]=="GEOMETRIC_HOLD"
                                      else "#28754E"),width=10)
        # The title explicitly marks this as synthetic geometry, not photo QA.
        title=(
            "SYNTHETIC MASK ONLY / NOT BRAND-LABEL QA / "+
            ("GEOMETRIC HOLD" if tests[scenario]["status"]=="GEOMETRIC_HOLD"
             else "NONOVERLAP ONLY")
        )
        dr.rectangle((0,1280,1080,1350),fill="#FFFFFF")
        f=ImageFont.truetype(str(design["__font_path"]),22)
        dr.text((25,1300),title,font=f,fill="#172D3A")
        dest=out/f"{candidate}_{scenario}_synthetic_mask_overlay.png"
        preview.save(dest,format="PNG",optimize=True)
        tests[scenario]["overlay_png"]=dest.name
        tests[scenario]["overlay_sha256"]=sha(dest)


def make_report(out:Path):
    if out.exists() and any(out.iterdir()):
        raise SystemExit("A50G_OUTPUT_EXISTS_HOLD")
    out.mkdir(parents=True,exist_ok=True)
    mod=load_design()
    assert sha(mod.PRETENDARD)==FONT_HASH
    original=json.loads((E50/"A50E_REFLOW_DESIGN_MANIFEST.json").read_text())
    assert set(original["variants"])==set(TYPES)
    assert original["owner_pm_approved"] is False
    original_unchanged_sha=sha(E50/"A50E_REFLOW_DESIGN_MANIFEST.json")
    entries={}
    for name in TYPES:
        profile=mod.NEW[name]
        profile_with_font={**profile,"__font_path":mod.PRETENDARD}
        mod.verify_reflow_geometry(profile, [profile["synthetic_mask"]])
        typ=measure_typography(mod,profile)
        masks=measure_masks(profile)
        render_mask_overlay(name,profile_with_font,masks,out)
        # Bad headline/CTA/long two line remains a rejection in accepted A50E.
        two_line,px=mod.fit_text("지금 만나보세요\n오늘만 특별 혜택",
             profile["regions"]["cta"],fontpath=mod.PRETENDARD,
             size=54,minimum=48,weight=700,allow_two_lines=True)
        # This only tests physical room, not permission to print 2-line CTA.
        entries[name]={
            "original_png_sha256":original["variants"][name]["sha256"],
            "typography":typ,
            "synthetic_product_cases":masks,
            "proposed_360_cta_font_min_px":16,
            "proposed_360_safe_bottom_min_px":12,
            "cta_display_font_360":typ["cta"]["font_size_360"],
            "cta_native_to_safe_bottom":mod.SAFE[3]-profile["regions"]["cta"][3],
            "synthetic_two_line_cta_geometry_only":{
                "line_count":len(two_line),"font_px":px,
                "approved_for_image":False,
            },
        }
        assert typ["cta"]["font_size_360"]>=16
        assert (mod.SAFE[3]-profile["regions"]["cta"][3])/3>=12
    data={
        "contract":"IT_TEM_P03_A50G_SYNTHETIC_TYPOGRAPHY_PACKAGE_MASK_PRECHECK_V1",
        "prior_a50e_manifest_sha256":original_unchanged_sha,
        "font_file_sha256_read_only_not_bundled":FONT_HASH,
        "font_package":"Pretendard 1.3.9 - candidate only",
        "licensing_signed":False,
        "owner_pm_design_approved":False,
        "product_policy":"PRODUCT_POLICY_APPROVED",
        "composed_4x5_design_profile":"DESIGN_PROFILE_V3_PENDING",
        "cases":entries,
        "rights_cleared_real_product_count":0,
        "actual_product_identity_mask":"NOT_AUDITED",
        "actual_platform_crop":"NOT_AUDITED",
        "360_390_human_visual":"NOT_AUDITED",
        "new_runtime_profile":"NOT_IMPLEMENTED",
        "d50_08_cta_9x16":"DECISION_PENDING_PM_OWNER",
        "a5_1":"HOLD","gcp_qa":"HOLD","paid_worker":"HOLD",
        "release":"NOT_RELEASE_READY",
    }
    p=out/"A50G_SYNTHETIC_TYPOGRAPHY_MASK_STRESS_REPORT.json"
    p.write_text(json.dumps(data,ensure_ascii=False,indent=2,sort_keys=True)+"\n")
    print("A50G_SYNTHETIC_STRESS_PREPARED")
    for name,v in entries.items():
        print(name,"FONT360",v["cta_display_font_360"],
              "MASK_SCENARIOS",len(v["synthetic_product_cases"]),
              "GEOMETRIC_HOLDS",sum(x["status"]=="GEOMETRIC_HOLD"
                                    for x in v["synthetic_product_cases"].values()))
    print("REAL_PRODUCT_BRAND_FONT_LICENSE_HUMAN_ACCEPTANCE=NOT_AUDITED")


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",required=True,type=Path)
    options=parser.parse_args()
    make_report(options.out)
