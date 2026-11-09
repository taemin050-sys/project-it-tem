"""A5-0 ONLY: reproducible unpaid 4:5 Composed design proposal mockups.

Owner/PM NON-APPROVED. No production layout, composition module, receipts,
GCP, provider calls, product photos, font binaries, or live DB modifications.
Synthetic approved Copy from A4-1, identical among all 3 alternatives.
"""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
W,H=1080,1350
COPY={
  "headline":"데일리 크림",
  "subline":"매일 촉촉한 사용감",
  "cta":"지금 만나보세요",
}
# Owner v2 "product" is an unverified composition target, never real detection.
PROTECTED_PRODUCT_TARGET=(466,418,611,1183)
SAFE_FRAME=(64,64,1016,1286)
# Owner/PM have NOT approved these 3 alternatives or their pixel coordinates.
CANDIDATES={
  "A_EDITORIAL_CENTER":{
    "head":(86,86,994,218),"sub":(86,246,994,390),
    "cta":(244,1200,836,1280),"font_px":(116,74,47),
    "alignment":"center","cta_style":"filled_pill",
    "heading_ink":"#263944","sub_ink":"#4C6470",
    "action_ink":"#FFFFFF","action_bg":"#253F55",
    "rationale":"중앙 정렬·직관적 1차 메시지; 하단 명확한 CTA 버튼",
  },
  "B_EDITORIAL_LEFT":{
    "head":(96,90,970,216),"sub":(96,242,960,392),
    "cta":(94,1200,810,1280),"font_px":(110,75,49),
    "alignment":"left","cta_style":"outline",
    "heading_ink":"#243F40","sub_ink":"#596B63",
    "action_ink":"#22554C","action_bg":"#DDE8E3",
    "rationale":"좌측 정렬·여백 중심 에디토리얼 구조; 브랜드 톤을 담는 아웃라인 CTA",
  },
  "C_CONTRAST_ACTION":{
    "head":(78,84,1002,215),"sub":(84,245,996,392),
    "cta":(68,1198,1012,1282),"font_px":(105,72,50),
    "alignment":"center","cta_style":"full_action_bar",
    "heading_ink":"#463447","sub_ink":"#6A526A",
    "action_ink":"#FFFFFF","action_bg":"#503B58",
    "rationale":"고대비 하단 액션 바와 단정한 상단 위계, 시선 유도 우선",
  },
}
def sha(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def overlap(a,b):
    return a[0]<b[2] and a[2]>b[0] and a[1]<b[3] and a[3]>b[1]
def text_bbox(font:ImageFont.FreeTypeFont, txt:str):
    return font.getbbox(txt)
def fit(draw,txt,face,desired,box,*,align="center",min_px=40,pad=12):
    availw=box[2]-box[0]-2*pad
    availh=box[3]-box[1]-2*pad
    for size in range(desired,min_px-1,-1):
        f=ImageFont.truetype(str(face),size)
        bb=text_bbox(f,txt)
        if bb[2]-bb[0] <= availw and bb[3]-bb[1] <= availh:
            w=bb[2]-bb[0];h=bb[3]-bb[1]
            if align=="center":
                x=box[0]+(box[2]-box[0]-w)/2-bb[0]
            else:
                x=box[0]+pad-bb[0]
            y=box[1]+(box[3]-box[1]-h)/2-bb[1]
            return f,(round(x),round(y)),size
    raise RuntimeError("A50_COPY_OVERFLOW_FAIL_CLOSED:"+txt)
def draw_fixture_target(d:ImageDraw.ImageDraw):
    # Same abstract QA-only bottle silhouette in all variants,
    # bounded strictly inside unverified product target. Not a model/photo.
    x1,y1,x2,y2=(493,595,584,1090)
    assert x1>PROTECTED_PRODUCT_TARGET[0] and x2<PROTECTED_PRODUCT_TARGET[2]
    assert y1>PROTECTED_PRODUCT_TARGET[1] and y2<PROTECTED_PRODUCT_TARGET[3]
    d.rounded_rectangle((513,573,565,640),radius=9,fill="#A8AFB4")
    d.rounded_rectangle((x1,628,x2,y2),radius=24,
                        fill="#E8E7E3",outline="#899FA1",width=4)
    d.rounded_rectangle((502,773,575,893),radius=8,
                        fill="#F2F2EF",outline="#B6BEBD",width=2)
    # Never add product brand/label/logo or factual efficacy assertions.
def render(output:Path,face:Path,background:Image.Image):
    assert background.size==(W,H)
    files={}
    results=[]
    for name,contract in CANDIDATES.items():
        im=background.copy().convert("RGB")
        d=ImageDraw.Draw(im)
        draw_fixture_target(d)
        for region in ("head","sub","cta"):
            box=contract[region]
            assert SAFE_FRAME[0]<=box[0]<box[2]<=SAFE_FRAME[2] and SAFE_FRAME[1]<=box[1]<box[3]<=SAFE_FRAME[3]
            assert not overlap(box,PROTECTED_PRODUCT_TARGET),(name,region)
            assert 0<=box[0] and box[2]<=W and box[3]<=H
        # all three concepts share approved Korean Copy with no truncation
        text_placed={}
        for idx,field in enumerate(("headline","subline")):
            region="head" if field=="headline" else "sub"
            txt=COPY[field]
            f,pos,real_size=fit(d,txt,face,contract["font_px"][idx],
                               contract[region],align=contract["alignment"])
            d.text(pos,txt,font=f,fill=contract["heading_ink" if idx==0 else "sub_ink"])
            text_placed[field]={"text":txt,"text_sha256":hashlib.sha256(txt.encode()).hexdigest(),
                "font_px":real_size,"region":contract[region]}
        # One and only one CTA rendering instruction, no duplicated text.
        box=contract["cta"]
        if contract["cta_style"]=="outline":
            d.rounded_rectangle(box,radius=23,fill=contract["action_bg"],
                                outline=contract["action_ink"],width=4)
        elif contract["cta_style"]=="full_action_bar":
            d.rounded_rectangle(box,radius=14,fill=contract["action_bg"])
        else:
            d.rounded_rectangle(box,radius=44,fill=contract["action_bg"])
        f,pos,size=fit(d,COPY["cta"],face,contract["font_px"][2],box,
                      min_px=44)
        d.text(pos,COPY["cta"],font=f,fill=contract["action_ink"])
        text_placed["cta"]={"text":COPY["cta"],"text_sha256":hashlib.sha256(COPY["cta"].encode()).hexdigest(),
                "font_px":size,"region":box,"render_count":1}
        assert len(text_placed)==3
        png=output/(name+".png")
        im.save(png,format="PNG",optimize=True)
        ims={}
        for w in (390,360):
            scaled=im.resize((w,round(H*w/W)),Image.Resampling.LANCZOS)
            scaled_path=output/f"{name}_mobile_{w}.png"
            scaled.save(scaled_path,format="PNG",optimize=True)
            ims[str(w)]={"file":scaled_path.name,"sha256":sha(scaled_path),
                         "pixels":list(scaled.size),
                         "cta_text_scaled_px":round(size*w/W,2)}
        files[name]={
          "png":png.name,"sha256":sha(png),
          "pixels":[W,H],
          "cta_policy":"on_image_PROPOSAL_ONLY",
          "protected_target_unverified":PROTECTED_PRODUCT_TARGET,
          "CTA_one_instruction":True,
          "text":text_placed,
          "mobile":ims,
          "design_rationale":contract["rationale"],
          "decision":"PENDING_IMAGE_OWNER_AND_PM",
          "visual_quality":"NOT_HUMAN_ACCEPTED",
        }
        results.append((name,png.name))
    return files
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--candidate-base",type=Path,required=True)
    ap.add_argument("--original-a41",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    ap.add_argument("--font",type=Path,required=True)
    a=ap.parse_args()
    a.out.mkdir(parents=True,exist_ok=True)
    assert a.font.is_file() and a.original_a41.is_file()
    # Fixed, user-approved QA copy SHA from the real A4-1 source/receipt.
    assert {k:hashlib.sha256(v.encode("utf-8")).hexdigest() for k,v in COPY.items()} == {
      "headline":"fed16d23a8dc3a78ffa55d4412e11866dc687b469f311d153779e67198bff807",
      "subline":"ba116b354fb1441d0b11556547acc165d155f5389046a978ff814431248a28e6",
      "cta":"29f1185e55a4d3499794d36ada72dda3556cb88a0bd220690a9e0811a5fbc0be"
    }
    base=Image.open(a.candidate_base).convert("RGB")
    assert base.size==(1152,1440)
    # 100% original QA fixture background (uniform flat). No real product photo.
    scaled=base.resize((W,H),Image.Resampling.LANCZOS)
    base_file=a.out/"fixture_base_1080x1350.png";scaled.save(base_file,optimize=True)
    orig=Image.open(a.original_a41)
    assert orig.size==(W,H) and sha(a.original_a41)=="a43bd648a8803a875d7199b9ca10af70fb585e9f2ed29431d5c516fa62e50179"
    original_file=a.out/"A41_ORIGINAL_WITHOUT_CTA.png"
    original_file.write_bytes(a.original_a41.read_bytes())
    result=render(a.out,a.font,scaled)
    # Separate 4-column Owner/PM review sheet; master candidates remain
    # separate 1080x1350 PNG with 360/390 responsive previews.
    labels=(("CURRENT V2 — NO CTA",original_file),
            *[(name,a.out/(name+".png")) for name in CANDIDATES])
    sw,sh,margin,gap=365,480,30,20
    sheet=Image.new("RGB",(margin*2+sw*4+gap*3,sh+92),"#F6F7F7")
    sd=ImageDraw.Draw(sheet)
    labelfont=ImageFont.truetype(str(a.font),20)
    for i,(label,src) in enumerate(labels):
        xx=margin+i*(sw+gap)
        sd.text((xx,20),label,font=labelfont,fill="#25343C")
        img=Image.open(src).convert("RGB").resize((sw,round(sw*H/W)),Image.Resampling.LANCZOS)
        sheet.paste(img,(xx,60))
    sheet_path=a.out/"A50_OWNER_PM_4UP_COMPARISON.png"
    sheet.save(sheet_path,optimize=True)
    result_meta={
      "contract":"IT_TEM_P03_A5_0_DESIGN_PROPOSALS_NOT_OWNER_APPROVED_V1",
      "canvas":[W,H],"copy":COPY,
      "copy_sha256":{k:hashlib.sha256(v.encode()).hexdigest() for k,v in COPY.items()},
      "actual_a41_png_sha256":sha(original_file),
      "four_up_comparison_sha256":sha(sheet_path),
      "candidate_base_original_1152_sha256":sha(a.candidate_base),
      "fixture_base_scaled_sha256":sha(base_file),
      "font_source_path":str(a.font),
      "font_sha256":sha(a.font),
      "font_license":"MACOS_LOCAL_INTERNAL_DESIGN_ONLY_NOT_COMMERCIAL_CLEARANCE",
      "product_region_status":"OWNER_LAYOUT_TARGET_ONLY_NOT_REAL_PRODUCT_SEGMENTATION",
      "candidates":result,
      "owner_pm_approval":"DECISION_PENDING",
      "runtime_profile_implementation":"NOT_PERFORMED",
      "9x16_cta_policy":"DECISION_PENDING_PM_OWNER",
      "real_provider":"NOT_AUDITED",
    }
    (a.out/"A50_DESIGN_PROPOSALS_MANIFEST.json").write_text(
        json.dumps(result_meta,ensure_ascii=False,indent=2,sort_keys=True)+"\n")
    print("A50_CONCEPTS_GENERATED",len(result))
    for name,v in result.items():print(name,v["sha256"],v["text"]["cta"]["font_px"])
    print("A50_ORIGINAL_SHA",sha(original_file))
    print("A50_OWNER_PM_DECISION_PENDING")
if __name__=="__main__":main()
