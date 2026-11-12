"""Beta-only snapshot typography checks. All images are synthetic, no Provider."""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import shutil

from PIL import Image
import pytest

from demo_staging.live import beta_typography as beta
from demo_staging.live.contracts import digest
from src.image_generation.composition import CompositionInput, CompositionLayout, compose_ad_png
from src.image_generation.contracts import BP18_DUAL_IMAGE_CTA_VERSION, BP18_V3_LAYOUT_VERSION
from src.image_generation.size_selection import resolve_size_choice


ROOT=Path(__file__).resolve().parents[2]
BOXES={
    "3:4":{"headline":(86,86,994,236),"subline":(86,252,994,448),"cta":(86,1264,994,1368)},
    "4:5":{"headline":(86,81,994,231),"subline":(86,247,994,410),"cta":(306,1195,774,1278)},
    "9:16":{"headline":(86,288,610,550),"subline":(86,580,610,830),"cta":(86,900,610,1040)},
}


@pytest.fixture
def config(tmp_path,monkeypatch):
    font=tmp_path/"private-font.ttf";license=tmp_path/"private-license.txt"
    shutil.copyfile(ROOT/"app/node_modules/pretendard/dist/public/variable/PretendardVariable.ttf",font)
    shutil.copyfile(ROOT/"app/node_modules/pretendard/dist/LICENSE.txt",license)
    font.chmod(0o600);license.chmod(0o600)
    monkeypatch.setenv(beta.FLAG,"YES")
    monkeypatch.setenv("IT_TEM_DERIVED_FONT",str(font))
    monkeypatch.setenv("IT_TEM_DERIVED_FONT_LICENSE",str(license))
    return font,license


@pytest.mark.parametrize("choice",["3:4","4:5","9:16"])
def test_all_ratio_policies_pin_real_font_style_and_exact_prompt_geometry(config,choice):
    policy=beta.build_policy(choice,cta_policy_sha="c"*64 if choice=="9:16" else None)
    zone=policy["safe_zone"];layout=policy["layout"]
    assert policy["profile_id"]==beta.PREFIX+choice.replace(":","_")
    assert policy["profile_version"]==beta.VERSION
    assert zone["required_font_sha"]==sha256(config[0].read_bytes()).hexdigest()==beta.FONT_SHA
    assert zone["font_license_sha"]==sha256(config[1].read_bytes()).hexdigest()==beta.LICENSE_SHA
    assert zone["font_policy_sha"]==digest(zone["font_evidence"])
    assert zone["human_visual_acceptance"]=="PENDING"
    selection,profile=resolve_size_choice(choice)
    expected_version={"3:4":selection.version,"4:5":BP18_V3_LAYOUT_VERSION,"9:16":BP18_DUAL_IMAGE_CTA_VERSION}[choice]
    assert zone["layout_selection"]=={**selection.model_dump(mode="json"),"version":expected_version}
    assert digest(layout)==beta.LAYOUT_SHA[choice]
    assert layout["canvas_size"]==list(profile.final)
    assert layout["cta_placement"]=="image"
    assert layout["protected_regions"]==[dict(zip(("left","top","right","bottom"),profile.normalized(profile.product)))]
    for role,box in BOXES[choice].items():
        region=layout["text_regions"][role]
        assert [region[key] for key in ("left","top","right","bottom")]==profile.normalized(box)
        assert region["typography"]["version"]=="display-typography-v1"
        assert region["typography"]["tracking_em"]==-.02
        assert region["typography"]["line_height"]==1.08
    assert layout["text_regions"]["headline"]["background"] is None
    assert layout["text_regions"]["subline"]["background"] is None
    assert layout["text_regions"]["headline"]["min_font_size"]>layout["text_regions"]["subline"]["max_font_size"]
    assert layout["text_regions"]["cta"]["typography"]["background_radius"]==42
    model=CompositionLayout.model_validate({**layout,"canvas_size":profile.final},strict=True)
    # CompositionLayout validates that all three text regions are disjoint from
    # the exact product target, including the separate 9:16 left sidebar.
    assert len(model.text_regions)==3
    assert beta.verify_profile(policy,zone,layout) is True


@pytest.mark.parametrize("choice",["3:4","4:5","9:16"])
def test_synthetic_actual_composition_uses_variable_typography_once(config,choice):
    policy=beta.build_policy(choice,cta_policy_sha="c"*64 if choice=="9:16" else None)
    size=tuple(policy["safe_zone"]["final_size"])
    image=Image.new("RGB",size,"#E5ECEC")
    stream=BytesIO();image.save(stream,"PNG");raw=stream.getvalue()
    copy={"plan":{},"ad_copy":{"headline":"매일의 샴푸 시간","subline":"차분하게 씻어내는","cta":"일상을 만나보세요"},
          "caption":"비과금 합성 테스트입니다.","hashtags":["#샴푸"]}
    layout=CompositionLayout.model_validate({**policy["layout"],"canvas_size":size},strict=True)
    result=compose_ad_png(CompositionInput(job_id="fixture-beta",image_bytes=raw,image_sha256=sha256(raw).hexdigest(),
        copy_revision=1,copy_hash=digest(copy),copy_output=copy,layout=layout),font_path=config[0])
    assert (result.width,result.height)==size
    assert result.receipt["font_sha256"]==beta.FONT_SHA
    assert result.receipt["provider_calls"]==0
    assert result.receipt["renderer"]=="korean-composition-v3"
    assert len(result.receipt["placements"])==3
    assert {key:item["text_sha256"] for key,item in result.receipt["placements"].items()}=={
        key:sha256(text.encode()).hexdigest() for key,text in copy["ad_copy"].items()}


def test_feature_flag_only_selects_new_policies_and_never_invalidates_existing_snapshot(config,monkeypatch):
    policy=beta.build_policy("4:5")
    monkeypatch.delenv(beta.FLAG)
    assert not beta.is_enabled()
    with pytest.raises(ValueError,match="BETA_TYPOGRAPHY_DISABLED"):beta.build_policy("4:5")
    assert beta.verify_profile(policy,policy["safe_zone"],policy["layout"])


@pytest.mark.parametrize("choice,value",[("9:16",None),("9:16","x"*64),("9:16","c"*63),("4:5","c"*64),("3:4","c"*64)])
def test_cta_policy_is_exact_and_ratio_scoped(config,choice,value):
    with pytest.raises(ValueError,match="BETA_TYPOGRAPHY_.*CTA_POLICY"):beta.build_policy(choice,value)


@pytest.mark.parametrize("field",["font","license"])
def test_mutated_font_or_license_bytes_cannot_claim_known_font_contract(config,field):
    path=config[0 if field=="font" else 1]
    path.write_bytes(path.read_bytes()+b"unreviewed-mutation")
    with pytest.raises(ValueError,match="BETA_TYPOGRAPHY_FONT_OR_LICENSE_CHANGED"):beta.build_policy("4:5")


def test_valid_sha_does_not_replace_required_variable_weight_axis(config,monkeypatch):
    original=beta.TTFont
    def no_weight(*args,**kwargs):
        font=original(*args,**kwargs);del font["fvar"];return font
    monkeypatch.setattr(beta,"TTFont",no_weight)
    with pytest.raises(ValueError,match="BETA_TYPOGRAPHY_VARIABLE_FONT_REQUIRED"):beta.build_policy("4:5")


@pytest.mark.parametrize("mutation",["missing","relative","symlink","writable"])
def test_missing_or_untrusted_server_font_configuration_is_rejected(config,tmp_path,monkeypatch,mutation):
    font=config[0]
    if mutation=="missing":monkeypatch.delenv("IT_TEM_DERIVED_FONT")
    elif mutation=="relative":monkeypatch.setenv("IT_TEM_DERIVED_FONT","relative.ttf")
    elif mutation=="writable":font.chmod(0o666)
    else:
        link=tmp_path/"font-link.ttf";link.symlink_to(font)
        monkeypatch.setenv("IT_TEM_DERIVED_FONT",str(link))
    with pytest.raises(ValueError,match="BETA_TYPOGRAPHY_PRIVATE_FONT_CONFIG_REQUIRED"):beta.build_policy("4:5")


def test_physical_font_relocation_does_not_change_policy_or_layout_identity(config,tmp_path,monkeypatch):
    first=beta.build_policy("4:5")
    relocated=tmp_path/"elsewhere";relocated.mkdir()
    for name,path in zip(("IT_TEM_DERIVED_FONT","IT_TEM_DERIVED_FONT_LICENSE"),config):
        copy=relocated/path.name;shutil.copyfile(path,copy);copy.chmod(0o600);monkeypatch.setenv(name,str(copy))
    assert beta.build_policy("4:5")==first


@pytest.mark.parametrize("mutation",["human","license","font","geometry","profile","version","weight"])
def test_stale_or_tampered_profile_has_no_mutable_factory_reinterpretation(config,mutation):
    policy=deepcopy(beta.build_policy("4:5"));zone=policy["safe_zone"];layout=policy["layout"]
    if mutation=="human":zone["human_visual_acceptance"]="PASS"
    elif mutation=="license":zone["font_license_sha"]="0"*64
    elif mutation=="font":zone["required_font_sha"]="0"*64
    elif mutation=="geometry":layout["text_regions"]["headline"]["bottom"]+=.01
    elif mutation=="profile":policy["profile_id"]="BP18_PROVISIONAL_SIZE_4_5"
    elif mutation=="version":policy["profile_version"]="unregistered-v2"
    else:layout["text_regions"]["headline"]["typography"]["weight"]=400
    with pytest.raises(ValueError,match="BETA_TYPOGRAPHY_PROFILE_INVALID"):beta.verify_profile(policy,zone,layout)


def test_future_factory_change_requires_explicit_new_layout_version(config,monkeypatch):
    original=beta.professional_layout
    def changed(*args,**kwargs):
        value=original(*args,**kwargs)
        value.text_regions["headline"].color="#010101"
        return value
    monkeypatch.setattr(beta,"professional_layout",changed)
    with pytest.raises(ValueError,match="BETA_TYPOGRAPHY_LAYOUT_VERSION_DRIFT"):beta.build_policy("4:5")
