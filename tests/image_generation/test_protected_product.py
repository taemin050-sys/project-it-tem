"""Synthetic protected-render contracts, independent of real Provider evidence.

``protected_fixture`` is reusable by derived API/Worker tests. Its raw candidate
is explicitly hand-drawn local fixture data, never a real model result.
"""
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps
import pytest

from src.image_generation.contracts import content_hash
from src.image_generation.protected_recipe import content_ref,recipe_content_sha,result_binding_sha
from src.image_generation import protected_product
from src.image_generation.protected_product import professional_layout,render_protected_product

FONT=Path(__file__).resolve().parents[2]/"app/node_modules/pretendard/dist/public/variable/PretendardVariable.ttf"
LICENSE=Path(__file__).resolve().parents[2]/"app/node_modules/pretendard/dist/LICENSE.txt"


def encoded(image,**kwargs):
    stream=BytesIO();image.save(stream,"PNG",**kwargs);return stream.getvalue()


def json_bytes(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()


@dataclass
class ProtectedFixture:
    recipe: dict
    contents: dict
    layer_spec: dict
    roi_spec: dict
    background_bytes: bytes
    font_path: Path

    def render(self,**overrides):
        arguments={"layer_spec":self.layer_spec,"roi_spec":self.roi_spec,
                   "job_id":"fixture-protected-render","copy_revision":1,
                   "font_path":self.font_path,"background_bytes":self.background_bytes}
        arguments.update(overrides)
        return render_protected_product(self.recipe,self.contents,**arguments)

    def rebind(self):
        """Use only for a new, intentionally changed synthetic recipe."""
        for role,data in self.contents.items():
            self.recipe["assets"][role]=content_ref(data,self.recipe["assets"][role]["media_type"]).model_dump()
        self.recipe["layer_spec_sha256"]=content_hash(self.layer_spec)
        self.recipe["roi_spec_sha256"]=content_hash(self.roi_spec)


def protected_fixture(*,size=(1080,1350),mode="composed_protected_product"):
    """Return a fresh mutable fixture. No Job DB, credentials or API calls."""
    source=Image.new("RGB",(200,400),"#e5ecee")
    draw=ImageDraw.Draw(source)
    draw.rectangle((20,10,179,389),fill="#eee5cd")
    draw.rectangle((50,110,150,185),fill="#2c4e64")
    draw.rectangle((90,250,140,300),fill="#92cadb")
    draw.line((25,200,170,215),fill="#102b40",width=4)
    mask=Image.new("L",source.size)
    ImageDraw.Draw(mask).rectangle((20,10,179,389),fill=255)
    copy={"plan":{"tone":"calm"},"ad_copy":{"headline":"승인된 샴푸 시간","subline":"일상의 세정 루틴","cta":"제품 만나보기"},
          "caption":"승인된 게시글입니다.","hashtags":["#샴푸","#브랜드"]}
    top=round(size[1]*.30)
    background=Image.new("RGB",size,"#cfd9dd")
    exclusions=[]
    raw_draw=ImageDraw.Draw(background)
    # Stand-in for Provider-drawn text. Exact raster preservation is asserted.
    font=ImageFont.truetype(str(FONT),44)
    for box,text in [([100,80,980,160],copy["ad_copy"]["headline"]),
                     ([100,180,980,250],copy["ad_copy"]["subline"]),
                     ([280,size[1]-150,800,size[1]-70],copy["ad_copy"]["cta"])]:
        raw_draw.text((box[0]+10,box[1]+5),text,font=font,fill="#102c40")
        exclusions.append(box)
    raw=encoded(background)
    roi={"primary_brand_and_product_name":[50,110,150,185],"cyan_circular_seal":[90,250,140,300]}
    layer={"raw_candidate_sha":sha256(raw).hexdigest(),"model_regions":[],"copy_exclusions":[]}
    content={"source_photo":encoded(source),"product_mask":encoded(mask),"copy_snapshot":json_bytes(copy)}
    types={"source_photo":"image/png","product_mask":"image/png","copy_snapshot":"application/json"}
    if mode=="composed_protected_product":
        layout=professional_layout(copy,size)
        content.update(font=FONT.read_bytes(),font_license=LICENSE.read_bytes(),layout=json_bytes(layout.model_dump(mode="json")))
        types.update(font="font/ttf",font_license="text/plain",layout="application/json")
        code_roles=("study_adapter","base_adapter","composition","typography","resize")
    else:
        review={"schema":"fixture-hybrid-review-v1","candidate_sha256":sha256(raw).hexdigest(),"reviewed":True}
        content.update(raw_candidate=raw,scene_review_spec=json_bytes(review))
        types.update(raw_candidate="image/png",scene_review_spec="application/json")
        layer.update(model_regions=[[410,top-10,670,top+410]],copy_exclusions=exclusions,
                     scene_review_sha=content_hash(review))
        code_roles=("study_adapter","resize","color_management")
    body={"schema":"bp18-portable-render-recipe-v1","render_mode":mode,
          "assets":{role:content_ref(data,types[role]).model_dump() for role,data in content.items()},
          "code_sha256":{role:"1"*64 for role in code_roles},"source_tree_sha":"2"*40,
          "source_icc_sha256":None,"roi_spec_sha256":content_hash(roi),"copy_sha256":content_hash(copy),
          "geometry":{"source_size":[200,400],"source_crop":[0,0,200,400],"registered_size":[200,400],
                      "output_offset":[440,top],"output_size":list(size),"resampler":"NONE"},
          "design_id":"synthetic-protected-v1","layer_spec_sha256":content_hash(layer),
          "alpha_rule":"combined_single_pass_photo_v1"}
    return ProtectedFixture(body,content,layer,roi,raw,FONT)


@pytest.mark.parametrize("size",[(1080,1350),(1080,1440),(1080,1920)])
@pytest.mark.parametrize("mode",["composed_protected_product","freeform_protected_product_hybrid"])
def test_all_ratios_modes_preserve_original_product_pixels_and_receipt(size,mode):
    f=protected_fixture(size=size,mode=mode)
    result=f.render()
    final=Image.open(BytesIO(result.image_bytes)).convert("RGB")
    assert final.size==size
    source=Image.open(BytesIO(f.contents["source_photo"])).convert("RGB")
    x,y=f.recipe["geometry"]["output_offset"]
    for name,box in f.roi_spec.items():
        actual_box=(box[0]+x,box[1]+y,box[2]+x,box[3]+y)
        assert final.crop(actual_box).tobytes()==source.crop(box).tobytes()
        assert result.receipt["protected_rois"][name]["rgb_sha256"]==sha256(source.crop(box).tobytes()).hexdigest()
    assert result.receipt["opaque_rgb_mismatches"]==0
    assert result.receipt["recipe_content_sha"]==recipe_content_sha(f.recipe)
    assert result.receipt["result_binding_sha"]==result_binding_sha(recipe_content_sha(f.recipe),result.image_bytes)
    assert result.receipt["provider_calls"]==result.receipt["provider_billing_events"]==0
    assert result.receipt["literal_label_ground_truth"]=="PENDING"
    assert result.receipt["needs_manual_check"] is True
    assert result.caption_bytes.decode()=="승인된 게시글입니다.\n\n#샴푸 #브랜드"


def test_composed_exactly_one_placement_per_approved_copy_role():
    f=protected_fixture();result=f.render()
    approved=json.loads(f.contents["copy_snapshot"])["ad_copy"]
    assert set(result.receipt["placements"])==set(approved)
    for role,text in approved.items():
        placement=result.receipt["placements"][role]
        assert "".join(placement["typography"]["lines"])==text
        assert placement["text_sha256"]==sha256(text.encode()).hexdigest()
    assert f.render().image_bytes==result.image_bytes


def test_hybrid_model_copy_is_unchanged_and_server_typography_never_runs(monkeypatch):
    f=protected_fixture(mode="freeform_protected_product_hybrid")
    def forbidden(*args,**kwargs):
        raise AssertionError("Hybrid must not call server copy compositor")
    monkeypatch.setattr(protected_product,"compose_ad_png",forbidden)
    result=f.render(font_path=None)
    final=Image.open(BytesIO(result.image_bytes)).convert("RGB")
    model=Image.open(BytesIO(f.background_bytes)).convert("RGB")
    assert result.receipt["placements"]=={}
    for box in f.layer_spec["copy_exclusions"]:
        assert final.crop(box).tobytes()==model.crop(box).tobytes()


@pytest.mark.parametrize("role",["source_photo","product_mask","copy_snapshot","font","layout"])
def test_changed_content_without_new_recipe_is_rejected(role):
    f=protected_fixture();f.contents[role]+=b"changed"
    with pytest.raises(ValueError,match="PROTECTED_RENDER_CONTENT_CHANGED"):f.render()


def test_supplied_roi_or_layer_spec_hash_mismatch_rejected():
    f=protected_fixture()
    with pytest.raises(ValueError,match="PROTECTED_RENDER_SPEC_CHANGED"):
        f.render(roi_spec={"changed":[1,1,2,2]})
    with pytest.raises(ValueError,match="PROTECTED_RENDER_SPEC_CHANGED"):
        f.render(layer_spec=dict(f.layer_spec,copy_exclusions=[[1,1,2,2]]))


def test_mask_hole_inside_label_rejected_even_if_new_content_hash_matches():
    f=protected_fixture()
    mask=Image.open(BytesIO(f.contents["product_mask"])).copy();mask.putpixel((100,270),254)
    f.contents["product_mask"]=encoded(mask);f.rebind()
    with pytest.raises(ValueError,match="PROTECTED_ROI_CHANGED"):f.render()


def test_label_region_outside_crop_is_rejected():
    f=protected_fixture();f.roi_spec["cyan_circular_seal"]=[90,250,250,300];f.rebind()
    with pytest.raises(ValueError,match="PROTECTED_REGION_BOUNDS"):f.render()


def test_background_font_and_source_icc_changes_rejected():
    f=protected_fixture()
    with pytest.raises(ValueError,match="PROTECTED_BACKGROUND_CHANGED"):
        f.render(background_bytes=encoded(Image.new("RGB",(1080,1350),"red")))
    with pytest.raises(ValueError,match="PROTECTED_FONT_CHANGED"):
        f.render(font_path=LICENSE)
    f.recipe["source_icc_sha256"]="f"*64
    with pytest.raises(ValueError,match="PROTECTED_SOURCE_ICC_CHANGED"):f.render()


def test_hybrid_product_cannot_cover_model_copy():
    f=protected_fixture(mode="freeform_protected_product_hybrid")
    x,y=f.recipe["geometry"]["output_offset"]
    f.layer_spec["copy_exclusions"]=[[x+20,y+20,x+80,y+80]]
    f.layer_spec["model_regions"]=[[800,500,900,700]];f.rebind()
    with pytest.raises(ValueError,match="HYBRID_COPY_PRODUCT_OVERLAP"):f.render()


def test_hybrid_scene_repair_cannot_cover_model_copy():
    f=protected_fixture(mode="freeform_protected_product_hybrid")
    f.layer_spec["model_regions"]=[f.layer_spec["copy_exclusions"][0]];f.rebind()
    with pytest.raises(ValueError,match="HYBRID_REPAIR_COPY_OVERLAP"):f.render()


def test_scene_review_cannot_use_other_candidate():
    f=protected_fixture(mode="freeform_protected_product_hybrid")
    review=json.loads(f.contents["scene_review_spec"]);review["candidate_sha256"]="e"*64
    f.contents["scene_review_spec"]=json_bytes(review);f.layer_spec["scene_review_sha"]=content_hash(review);f.rebind()
    with pytest.raises(ValueError,match="HYBRID_SCENE_REVIEW_CHANGED"):f.render()


def test_unreviewed_scene_requires_explicit_review():
    f=protected_fixture(mode="freeform_protected_product_hybrid")
    review=json.loads(f.contents["scene_review_spec"]);review["reviewed"]=False
    f.contents["scene_review_spec"]=json_bytes(review);f.layer_spec["scene_review_sha"]=content_hash(review);f.rebind()
    with pytest.raises(ValueError,match="HYBRID_SCENE_REVIEW_REQUIRED"):f.render()


@pytest.mark.parametrize("mutation",[{"resampler":"SHARPEN"},{"output_offset":[True,0]},
    {"registered_size":[200,399]},{"registered_size":[400,800]}])
def test_unsupported_geometry_or_transform_rejected(mutation):
    f=protected_fixture();f.recipe["geometry"].update(mutation)
    with pytest.raises(ValueError):f.render()


def test_source_exif_rotation_must_match_frozen_layer_orientation():
    f=protected_fixture();source=Image.open(BytesIO(f.contents["source_photo"])).copy()
    exif=Image.Exif();exif[274]=6;f.contents["source_photo"]=encoded(source,exif=exif);f.rebind()
    with pytest.raises(ValueError,match="PROTECTED_SOURCE_ORIENTATION_CHANGED"):
        f.render()


def test_source_exif6_transpose_is_explicit_and_original_byte_sha_survives():
    f=protected_fixture()
    source=Image.open(BytesIO(f.contents["source_photo"])).copy()
    exif=Image.Exif();exif[274]=6
    raw=encoded(source,exif=exif)
    f.contents["source_photo"]=raw
    upright=ImageOps.exif_transpose(Image.open(BytesIO(raw))).convert("RGB")
    assert upright.size==(400,200)
    f.contents["product_mask"]=encoded(Image.new("L",upright.size,255))
    f.recipe["geometry"].update(source_size=[400,200],source_crop=[0,0,400,200],
                                 registered_size=[400,200],output_offset=[340,405])
    f.layer_spec["source_orientation"]=6
    f.roi_spec={"primary_brand_and_product_name":[215,50,290,150],"cyan_circular_seal":[100,90,150,140]}
    f.rebind()
    result=f.render()
    final=Image.open(BytesIO(result.image_bytes)).convert("RGB")
    for box in f.roi_spec.values():
        actual=(box[0]+340,box[1]+405,box[2]+340,box[3]+405)
        assert final.crop(actual).tobytes()==upright.crop(box).tobytes()
    assert f.contents["source_photo"]==raw
    assert result.receipt["source_photo_sha"]==sha256(raw).hexdigest()
