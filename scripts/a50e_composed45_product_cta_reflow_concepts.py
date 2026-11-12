"""A5-0E: synthetic, unpaid revised 4:5 Composed CTA/Product reflow proposals.

NO Owner/PM approval, no production source changes, no real product detection,
no provider calls. Reuses the exact previous fixed synthetic QA background and
the installed FE Pretendard font (font bytes are never bundled).
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
A50=ROOT/"docs/integration/evidence/A50_20261110"
PRETENDARD=ROOT/"app/node_modules/pretendard/dist/public/variable/PretendardVariable.ttf"
LICENSE=ROOT/"app/node_modules/pretendard/dist/LICENSE.txt"
FONT_EXPECTED="3090ccde0442bb347aa7685d9ba8b17436a60682df6e8f92a9a670de14056e22"
LICENSE_EXPECTED="b04538c9abec39a3db75108cf0af0fd9c77032fe8aa2cf38345b4d250e98e38e"
SIZE=(1080,1350)
SAFE=(64,64,1016,1286)
OLD_TARGET=(466,418,611,1183)
COPY={"headline":"데일리 크림","subline":"매일 촉촉한 사용감",
      "cta":"지금 만나보세요"}
# Proposal thresholds only, NOT PM/Owner policy.
GOALS={"cta_min_font_at_360":16,"safe_bottom_inset_360":12,
       "cta_text_bg_contrast":4.5}
# All geometry coordinates are LTRB native px. Not authoritative layout.
NEW={
 "A_REFLOW_EDITORIAL_CENTER":{
   "regions":{"headline":(86,82,994,223),
              "subline":(86,245,994,382),
              "cta":(218,1108,862,1238)},
   "product_target":(436,410,644,1045),
   "synthetic_mask":(466,518,614,1025),
   "font_size":{"headline":116,"subline":75,"cta":60},
   "cta_bg":"#253F55","cta_fg":"#FFFFFF","cta_style":"pill",
   "headline_color":"#263944","subline_color":"#4C6470",
   "recommendation":"Default-direction revised layout; product target reflow, not translation only",
 },
 "C_REFLOW_CONTRAST_ACTION":{
   "regions":{"headline":(86,82,994,223),
              "subline":(86,245,994,382),
              "cta":(80,1094,1000,1236)},
   "product_target":(436,405,644,1035),
   "synthetic_mask":(466,513,614,1018),
   "font_size":{"headline":112,"subline":75,"cta":60},
   "cta_bg":"#503B58","cta_fg":"#FFFFFF","cta_style":"action_bar",
   "headline_color":"#463447","subline_color":"#6A526A",
   "recommendation":"Optional action-forward revised layout; product target reflow",
 }
}


def digest(path:Path)->str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha_text(text:str)->str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def overlap(a,b)->bool:
    return a[0]<b[2] and a[2]>b[0] and a[1]<b[3] and a[3]>b[1]


def intersects_any(box, masks)->bool:
    return any(overlap(box,m) for m in masks)


def fully_inside(inner,outer)->bool:
    return all((
        outer[0]<=inner[0]<inner[2]<=outer[2],
        outer[1]<=inner[1]<inner[3]<=outer[3],
    ))


def verify_reflow_geometry(design:dict, masks:list|None, *,
                           require_real_mask:bool=False) -> None:
    if masks is None and require_real_mask:
        raise ValueError("A50E_REAL_PRODUCT_MASK_REQUIRED_FAIL_CLOSED")
    if masks is None:  # synthetic fixtures only
        masks=[design["synthetic_mask"]]
    pt=design["product_target"]
    if not fully_inside(pt,SAFE):
        raise ValueError("A50E_PRODUCT_TARGET_OUT_OF_SAFE")
    for mask in masks:
        if not fully_inside(mask,pt):
            raise ValueError("A50E_PROTECTED_MASK_OUTSIDE_TARGET")
    reg=design["regions"]
    assert set(reg)=={"headline","subline","cta"}
    if any(not fully_inside(region,SAFE) for region in reg.values()):
        raise ValueError("A50E_TEXT_BOX_OUT_OF_SAFE")
    if any(overlap(a,b) for i,a in enumerate(reg.values())
           for b in list(reg.values())[i+1:]):
        raise ValueError("A50E_REGIONS_OVERLAP")
    if any(intersects_any(region,masks) for region in reg.values()):
        raise ValueError("A50E_TEXT_PROTECTED_OBJECT_COLLISION")
    if (SAFE[3]-reg["cta"][3])/3 < GOALS["safe_bottom_inset_360"]:
        raise ValueError("A50E_PROPOSED_BOTTOM_MARGIN_HOLD")
    if design["font_size"]["cta"]/3 < GOALS["cta_min_font_at_360"]:
        raise ValueError("A50E_PROPOSED_CTA_SIZE_HOLD")


def font_at(fontpath:Path,size:int,weight:int) -> ImageFont.FreeTypeFont:
    ft=ImageFont.truetype(str(fontpath),size)
    if hasattr(ft,"set_variation_by_axes"):
        ft.set_variation_by_axes([weight])
    return ft


def fit_text(text:str, box:tuple, *, fontpath:Path, size:int,
             minimum:int, weight:int, allow_two_lines:bool=False):
    if not text.strip() or "\t" in text or "\r" in text:
        raise ValueError("A50E_INVALID_COPY")
    lines=text.split("\n")
    if len(lines)>1 and not allow_two_lines:
        raise ValueError("A50E_CTA_MULTILINE_REQUIRES_PROFILE_APPROVAL")
    if len(lines)>2 or any(not line.strip() for line in lines):
        raise ValueError("A50E_UNSUPPORTED_LINE_COUNT")
    gap=8 if len(lines)>1 else 0
    for px in range(size,minimum-1,-1):
        ft=font_at(fontpath,px,weight)
        glyphs=[ft.getbbox(line) for line in lines]
        widths=[max(1,round(ft.getlength(line))) for line in lines]
        heights=[max(1,g[3]-g[1]) for g in glyphs]
        total=sum(heights)+(len(lines)-1)*gap
        if max(widths)+24>box[2]-box[0] or total+24>box[3]-box[1]:
            continue
        y=box[1]+((box[3]-box[1])-total)/2
        positions=[]
        for line,g,w,h in zip(lines,glyphs,widths,heights):
            x=box[0]+((box[2]-box[0])-w)/2-g[0]
            positions.append((line,ft,(round(x),round(y-g[1]))))
            y+=h+gap
        return positions,px
    raise ValueError("A50E_COPY_OVERFLOW_FAIL_CLOSED")


def draw_synthetic_bottle(draw:ImageDraw.ImageDraw, design:dict):
    """Identical fake object category in both variants, always fully in mask."""
    x1,y1,x2,y2=design["synthetic_mask"]
    assert fully_inside((x1,y1,x2,y2),design["product_target"])
    # All pixels representing fake product remain in synthetic mask.
    draw.ellipse((x1+4,y2-26,x2-4,y2-6),fill="#CED3D0")
    draw.rounded_rectangle((x1+42,y1+2,x2-42,y1+70),radius=10,
                           fill="#7D9796",outline="#5C7374",width=3)
    draw.rounded_rectangle((x1+17,y1+58,x2-17,y2-14),radius=28,
                           fill="#F1F0E9",outline="#9DB0AC",width=4)
    # Decorative blank label; not an actual brand, logo or product claim.
    draw.rounded_rectangle((x1+27,y1+175,x2-27,y1+310),radius=9,
                           fill="#FCFCF8",outline="#CBD2CE",width=2)
    draw.rectangle((x1+42,y1+207,x2-42,y1+210),fill="#DCE3DD")


def contrast(a:str,b:str)->float:
    def lum(col):
        nums=[int(col[i:i+2],16)/255 for i in (1,3,5)]
        nums=[x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4 for x in nums]
        return sum(p*n for p,n in zip((.2126,.7152,.0722),nums))
    la,lb=sorted((lum(a),lum(b)),reverse=True)
    return round((la+.05)/(lb+.05),3)


def render_variant(name:str,design:dict,background:Image.Image,
                   fontpath:Path,output:Path) -> dict:
    verify_reflow_geometry(design,masks=[design["synthetic_mask"]])
    assert background.size==SIZE
    im=background.copy().convert("RGB")
    dr=ImageDraw.Draw(im)
    # Diffuse editorial floor, no proprietary product visuals.
    dr.ellipse((260,940,810,1088),fill="#E4E6E2")
    draw_synthetic_bottle(dr,design)
    cta=design["regions"]["cta"]
    if design["cta_style"]=="pill":
        dr.rounded_rectangle(cta,radius=50,fill=design["cta_bg"])
    else:
        dr.rounded_rectangle(cta,radius=24,fill=design["cta_bg"])
    rendered={}
    for field in ("headline","subline","cta"):
        bounds=design["regions"][field]
        desired=design["font_size"][field]
        minimum={"headline":64,"subline":54,"cta":48}[field]
        weight={"headline":700,"subline":500,"cta":700}[field]
        positions,px=fit_text(COPY[field],bounds,fontpath=fontpath,size=desired,
                               minimum=minimum,weight=weight)
        ink=design["cta_fg"] if field=="cta" else design[field+"_color"]
        for text,font,xy in positions:
            dr.text(xy,text,font=font,fill=ink)
        rendered[field]={
            "text":COPY[field],"text_sha256":sha_text(COPY[field]),
            "rect":list(bounds),"font_px_native":px,
            "font_px_on_360":round(px/3,2),
            "render_instruction_count":len(positions),
            "weight_variable_axis":weight,
        }
    assert rendered["cta"]["render_instruction_count"]==1
    path=output/(name+".png")
    im.save(path,format="PNG",optimize=True)
    mobiles={}
    for width in (360,390):
        scaled=im.resize((width,round(SIZE[1]*width/SIZE[0])),
                         Image.Resampling.LANCZOS)
        src=output/f"{name}_mobile_{width}.png"
        scaled.save(src,format="PNG",optimize=True)
        # Synthetic crop test: cut bottom 12 DISPLAY pixels, not certified
        # Instagram UI chrome/crop rule.
        cropped=scaled.crop((0,0,width,scaled.height-12))
        crop_path=output/f"{name}_mobile_{width}_crop12_simulation.png"
        cropped.save(crop_path,format="PNG",optimize=True)
        mobiles[str(width)]={
          "png":src.name,"sha256":digest(src),"pixels":list(scaled.size),
          "crop_simulation_12px":crop_path.name,
          "crop_simulation_sha256":digest(crop_path),
          "cta_bottom_remains_above_crop_px":
              round(cropped.height-cta[3]*width/SIZE[0],2),
        }
    return {
        "design_id":name,"png":path.name,"sha256":digest(path),
        "pixels":[*SIZE],"copy":rendered,
        "cta_background":design["cta_bg"],"cta_text_color":design["cta_fg"],
        "cta_foreground_background_contrast":contrast(design["cta_fg"],design["cta_bg"]),
        "cta_safe_bottom_native":SAFE[3]-cta[3],
        "cta_safe_bottom_360":round((SAFE[3]-cta[3])/3,2),
        "cta_to_fake_product_target_gap_native":cta[1]-design["product_target"][3],
        "fake_protected_target":list(design["product_target"]),
        "fake_object_mask":list(design["synthetic_mask"]),
        "mobile":mobiles,
        "object_coverage":"SYNTHETIC_MASK_ONLY_NOT_REAL_BRAND_LABEL",
        "platform_crop":"SIMULATION_ONLY_NOT_PLATFORM_CERTIFIED",
        "owner_pm_decision":"PENDING","commercial_font_approval":"HOLD",
        "recommended_role":design["recommendation"],
    }


def negative_stress_tests(fontpath:Path) -> dict:
    a=NEW["A_REFLOW_EDITORIAL_CENTER"]
    cases={}
    def check_reject(label, fn, expected):
        try:
            fn()
        except ValueError as e:
            assert str(e)==expected,(label,e)
            cases[label]={"status":"REJECTED_AS_EXPECTED","reason":str(e)}
        else:
            raise AssertionError(f"A50E_UNSAFE_ACCEPT:{label}")
    check_reject("actual_object_mask_missing",lambda:verify_reflow_geometry(
        a,None,require_real_mask=True),"A50E_REAL_PRODUCT_MASK_REQUIRED_FAIL_CLOSED")
    check_reject("large_packaging_into_cta",lambda:verify_reflow_geometry(
        a,[(440,520,642,1160)]),"A50E_PROTECTED_MASK_OUTSIDE_TARGET")
    bad={**a,"regions":{**a["regions"],"cta":(218,997,862,1135)}}
    check_reject("cta_overlap_fake_mask",lambda:verify_reflow_geometry(
        bad,[(466,518,614,1025)]),"A50E_TEXT_PROTECTED_OBJECT_COLLISION")
    check_reject("overlong_korean_headline",lambda:fit_text(
        "한국어 제품 광고 문구가 매우 길어졌을 때 안전한 영역에서 무리하게 축소하거나 자르지 않는다는 점을 확인하기 위한 장문"*3,
        a["regions"]["headline"],fontpath=fontpath,size=116,
        minimum=64,weight=700),"A50E_COPY_OVERFLOW_FAIL_CLOSED")
    check_reject("long_cta_no_truncation",lambda:fit_text(
        "지금 만나보세요 그리고 공식몰에서 다양한 할인 혜택을 특별한 가격으로 확인하세요"*3,
        a["regions"]["cta"],fontpath=fontpath,size=60,minimum=48,weight=700),
        "A50E_COPY_OVERFLOW_FAIL_CLOSED")
    check_reject("multiline_cta_unapproved",lambda:fit_text(
        "지금 만나보세요\n오늘만 특별 혜택",a["regions"]["cta"],
        fontpath=fontpath,size=54,minimum=48,weight=700),
        "A50E_CTA_MULTILINE_REQUIRES_PROFILE_APPROVAL")
    check_reject("three_line_cta_disallowed",lambda:fit_text(
        "지금\n만나보세요\n오늘 할인",a["regions"]["cta"],
        fontpath=fontpath,size=54,minimum=48,weight=700,allow_two_lines=True),
        "A50E_UNSUPPORTED_LINE_COUNT")
    good,px=fit_text("지금 만나보세요\n오늘만 특별 혜택",
                     a["regions"]["cta"],fontpath=fontpath,size=54,
                     minimum=48,weight=700,allow_two_lines=True)
    assert len(good)==2 and px>=48
    cases["two_line_cta_explicit_simulation"]={
        "status":"SYNTHETIC_LAYOUT_FEASIBLE_NOT_PROFILE_APPROVED",
        "lines":len(good),"native_font_px":px,
    }
    smaller={**a,"synthetic_mask":(494,540,586,955),
             "product_target":(466,430,614,1000)}
    verify_reflow_geometry(smaller,[smaller["synthetic_mask"]])
    cases["small_package_synthetic_mask"]={
        "status":"SYNTHETIC_GEOMETRY_PASS_NOT_REAL_DETECTION",
        "mask":list(smaller["synthetic_mask"]),
    }
    return cases


def make_comparison(output:Path,fontpath:Path):
    from PIL import ImageFont
    cols=[
        ("A · PREVIOUS",A50/"A_EDITORIAL_CENTER.png"),
        ("A · REFLOW",output/"A_REFLOW_EDITORIAL_CENTER.png"),
        ("C · PREVIOUS",A50/"C_CONTRAST_ACTION.png"),
        ("C · REFLOW",output/"C_REFLOW_CONTRAST_ACTION.png"),
    ]
    colw=350; gap=18; margin=26; top=64
    width=margin*2+4*colw+3*gap
    height=top+438+28
    im=Image.new("RGB",(width,height),"#F7F7F5")
    dr=ImageDraw.Draw(im)
    font=font_at(fontpath,20,600)
    for i,(label,path) in enumerate(cols):
        x=margin+i*(colw+gap)
        dr.text((x,20),label,font=font,fill="#293947")
        src=Image.open(path).convert("RGB")
        assert src.size==SIZE
        im.paste(src.resize((colw,round(1350*colw/1080)),
                            Image.Resampling.LANCZOS),(x,top))
    dest=output/"A50E_A_C_BEFORE_AFTER_COMPARISON.png"
    im.save(dest,format="PNG",optimize=True)
    return dest


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    dest=args.out
    if dest.exists() and any(dest.iterdir()):
        raise SystemExit("A50E_EXISTING_OUTPUT_HOLD")
    dest.mkdir(parents=True,exist_ok=True)
    assert digest(PRETENDARD)==FONT_EXPECTED
    assert digest(LICENSE)==LICENSE_EXPECTED
    source=A50/"fixture_base_1080x1350.png"
    base=Image.open(source).convert("RGB")
    assert base.size==SIZE
    results={}
    for name,design in NEW.items():
        results[name]=render_variant(name,design,base,PRETENDARD,dest)
    sheet=make_comparison(dest,PRETENDARD)
    tests=negative_stress_tests(PRETENDARD)
    stress=dest/"A50E_SYNTHETIC_STRESS_RESULTS.json"
    stress.write_text(json.dumps(tests,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    old=json.loads((A50/"A50_DESIGN_PROPOSALS_MANIFEST.json").read_text())
    report={
        "contract":"IT_TEM_P03_A50E_CTAPRODUCT_REFLOW_DESIGN_PROPOSAL_V1",
        "source_prior_a50_manifest_sha256":digest(A50/"A50_DESIGN_PROPOSALS_MANIFEST.json"),
        "old_owner_v2_product_target":list(OLD_TARGET),
        "old_a50_original_candidates_sha256":{
            k:v["sha256"] for k,v in old["candidates"].items()},
        "unchanged_b_editorial_sha256":old["candidates"]["B_EDITORIAL_LEFT"]["sha256"],
        "source_background_sha256":digest(source),
        "font_family":"Pretendard Variable",
        "font_package_version":"1.3.9",
        "local_font_sha256_not_bundled":digest(PRETENDARD),
        "license_sha256_no_binary_in_evidence":digest(LICENSE),
        "font_server_license_approval":"HOLD",
        "safe_frame_internal_v2_target":list(SAFE),
        "proposed_rules_not_approved":GOALS,
        "variants":results,
        "comparison_sha256":digest(sheet),
        "comparison_png":sheet.name,
        "stress_sha256":digest(stress),
        "stress_scenarios":tests,
        "real_product_object_detection":"NOT_AUDITED",
        "source_silhouette":"SYNTHETIC_NO_BRAND",
        "platform_safezone":"NOT_CERTIFIED",
        "owner_pm_approved":False,
        "a5_1_implementation_authorized":False,
        "9x16_cta_policy":"DECISION_PENDING_PM_OWNER",
        "gcp_qa_deployment":"HOLD","paid_worker":"HOLD",
        "real_provider":"NOT_AUDITED","release":"NOT_RELEASE_READY",
    }
    manifest=dest/"A50E_REFLOW_DESIGN_MANIFEST.json"
    manifest.write_text(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print("A50E_SYNTHETIC_REFLOW_2_OF_2_GENERATED")
    for n,v in results.items():
        print(n,"PNG_SHA",v["sha256"],"CTA_FONT360",
              v["copy"]["cta"]["font_px_on_360"],"SAFE_BOTTOM360",
              v["cta_safe_bottom_360"],"GAP_NATIVE",
              v["cta_to_fake_product_target_gap_native"])
    print("A50E_STRESS",len(tests),"NO_REAL_PRODUCT_OR_OWNER_PM_APPROVAL")


if __name__=="__main__":
    main()
