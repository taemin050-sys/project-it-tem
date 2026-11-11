"""Portable recipe identity is content based and grants no access authority."""
from copy import deepcopy
import json
import shutil
import subprocess

import pytest

from src.image_generation.protected_recipe import (
    ContentRef, Geometry, PortableRecipe, canonical_bytes, canonical_sha, checked_recipe,
    content_ref, load_recipe_json, recipe_content_sha, result_binding_sha,
)


def recipe():
    media = {"source_photo":"image/png", "product_mask":"image/png", "font":"font/ttf",
             "font_license":"text/plain", "copy_snapshot":"application/json", "layout":"application/json"}
    return {
        "schema":"bp18-portable-render-recipe-v1", "render_mode":"composed_protected_product",
        "assets":{role:content_ref(role.encode(),kind).model_dump() for role,kind in media.items()},
        "code_sha256":{role:"a"*64 for role in ("study_adapter","base_adapter","composition","typography","resize")},
        "source_tree_sha":"b"*40, "source_icc_sha256":None, "roi_spec_sha256":"c"*64,
        "copy_sha256":"d"*64, "geometry":{"source_size":[1200,1500], "source_crop":[0,0,1200,1500],
            "registered_size":[1080,1350], "output_offset":[0,0], "output_size":[1080,1350],
            "resampler":"LANCZOS_RGB_AND_ALPHA"}, "design_id":"waterline-v1",
        "layer_spec_sha256":"e"*64, "alpha_rule":"combined_single_pass_photo_v1",
    }


def test_content_identity_has_no_file_or_upload_alias_and_preserves_strings():
    body=recipe()
    assert checked_recipe(body)==body
    assert recipe_content_sha(body)==recipe_content_sha(dict(reversed(list(body.items()))))
    assert canonical_sha({"copy":"가 "})!=canonical_sha({"copy":"가"})
    assert canonical_sha({"copy":"가"})!=canonical_sha({"copy":"가"})
    for name in ("preview_path","source_path","actor","upload_asset_id"):
        with pytest.raises(ValueError): checked_recipe(dict(body,**{name:"not-semantic"}))


def test_result_identity_separates_output_from_render_input():
    body=recipe(); before=recipe_content_sha(body)
    assert result_binding_sha(before,b"one")!=result_binding_sha(before,b"two")
    assert recipe_content_sha(body)==before


def test_content_id_cannot_lie_about_bytes():
    ref=content_ref(b"original","image/png")
    with pytest.raises(ValueError): ContentRef.model_validate(dict(ref.model_dump(),asset_id="sha256:"+"0"*64))
    with pytest.raises(ValueError): ContentRef.model_validate(dict(ref.model_dump(),asset_id="../a"))
    with pytest.raises(ValueError): content_ref(b"","image/png")


@pytest.mark.parametrize("field,value",[("source_icc_sha256","f"*64),("copy_sha256","f"*64),
    ("layer_spec_sha256","f"*64),("roi_spec_sha256","f"*64)])
def test_effective_semantic_change_changes_digest(field,value):
    body=recipe(); changed=deepcopy(body);changed[field]=value
    assert recipe_content_sha(body)!=recipe_content_sha(changed)


def test_models_with_unvalidated_copy_updates_are_revalidated():
    body=PortableRecipe.model_validate(recipe())
    changed=body.model_copy(update={"design_id":"../escape"})
    with pytest.raises(ValueError): recipe_content_sha(changed)


@pytest.mark.parametrize("field,value",[("output_offset",[True,0]),("output_offset",[0.0,0]),
    ("output_offset",[9007199254740992,0]),("registered_size",[1080,1300]),
    ("registered_size",[2400,3000]),("source_crop",[0,0,1201,1500]),("output_offset",[1,0])])
def test_geometry_rejects_unsupported_registration(field,value):
    geometry=recipe()["geometry"]
    with pytest.raises(ValueError): Geometry.model_validate(dict(geometry,**{field:value}))


def test_hybrid_has_distinct_no_server_type_roles():
    body=recipe();body["render_mode"]="freeform_protected_product_hybrid"
    with pytest.raises(ValueError): checked_recipe(body)
    body["assets"]={k:v for k,v in body["assets"].items() if k in {"source_photo","product_mask","copy_snapshot"}}
    body["assets"]["raw_candidate"]=content_ref(b"raw","image/png").model_dump()
    body["assets"]["scene_review_spec"]=content_ref(b"{}","application/json").model_dump()
    body["code_sha256"]={k:"f"*64 for k in ("study_adapter","resize","color_management")}
    assert checked_recipe(body)["render_mode"]=="freeform_protected_product_hybrid"


@pytest.mark.parametrize("data",['{"schema":1,"schema":2}','{"value":NaN}','{"value":Infinity}',"[]",'"x"'])
def test_json_boundary_rejects_ambiguous_payloads(data):
    with pytest.raises(ValueError): load_recipe_json(data)


def test_real_json_boundary_and_canonical_limits():
    assert load_recipe_json(canonical_bytes(recipe()))==recipe()
    with pytest.raises(ValueError):load_recipe_json(b" "*(128*1024+1))
    for value in ({"float":.2},{"huge":2**60},{"bad":{2:"integer key"}}):
        with pytest.raises(ValueError):canonical_bytes(value)


def test_node_python_golden_canonical_bytes_agree():
    node=shutil.which("node")
    if node is None:pytest.skip("Node not installed")
    body={"recipe":recipe(),"한글":"승인 카피  "}
    program="""const fs=require('node:fs'),crypto=require('node:crypto');
const value=JSON.parse(fs.readFileSync(0,'utf8'));
function stable(x){if(Array.isArray(x))return x.map(stable);
if(x!==null&&typeof x==='object')return Object.fromEntries(Object.keys(x).sort().map(k=>[k,stable(x[k])]));return x;}
process.stdout.write(crypto.createHash('sha256').update(JSON.stringify(stable(value)),'utf8').digest('hex'));"""
    actual=subprocess.check_output([node,"-e",program],input=canonical_bytes(body)).decode()
    assert actual==canonical_sha(body)
