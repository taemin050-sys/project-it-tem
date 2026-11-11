"""Original-byte registry rejects cross-Job aliases and normalized substitutes."""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path

from PIL import Image,ImageCms
import pytest

from demo_staging.live.contracts import LiveGateError
from demo_staging.live.derived_assets import DerivedAssetRegistry,inspect_image
from src.image_generation.protected_recipe import content_ref
from src.serving.job_store import JobStore,ValidatedUpload


def encoded(color="red",size=(12,9),mode="RGBA",**kwargs):
    out=BytesIO();Image.new(mode,size,color).save(out,"PNG",**kwargs);return out.getvalue()


def make_registry(tmp_path,**options):
    profile=ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    exif=Image.Exif();exif[274]=6
    first=encoded("red",icc_profile=profile,exif=exif)
    second=encoded("blue")
    jobs=JobStore(tmp_path/"jobs")
    job=jobs.create_job([ValidatedUpload(name,"image/png",raw,12,9,sha256(raw).hexdigest())
        for name,raw in [("one.png",first),("two.png",second)]],[])
    allowed={job["job_id"]:"alice"}
    registry=DerivedAssetRegistry(tmp_path/"derived",jobs,
                                  lambda actor,jid:allowed.get(jid)==actor,**options)
    return registry,jobs,job,first,profile


def test_original_byte_icc_orientation_preserved(tmp_path):
    registry,jobs,job,raw,profile=make_registry(tmp_path)
    jid=job["job_id"];aid=job["assets"][0]["asset_id"]
    original=registry.resolve_upload("alice",jid,aid)
    assert original.data==raw and original.image.orientation==6
    assert original.image.upright_size==(9,12)
    assert original.image.icc_sha256==sha256(profile).hexdigest()
    assert original.ref.sha256==job["assets"][0]["sha256"]
    assert registry.register_upload("alice",jid,aid)==original
    assert registry.read_content("alice",jid,original.ref).data==raw
    assert jobs.get_asset(jid,aid)[0].read_bytes()==raw


def test_content_match_does_not_grant_cross_actor_access(tmp_path):
    registry,jobs,job,_,_=make_registry(tmp_path)
    jid=job["job_id"];aid=job["assets"][0]["asset_id"]
    ref=registry.register_upload("alice",jid,aid).ref
    for action in (lambda:registry.resolve_upload("bob",jid,aid),
                   lambda:registry.read_content("bob",jid,ref),
                   lambda:registry.put_content("bob",jid,b"note","text/plain",kind="caption")):
        with pytest.raises(LiveGateError) as exc:action()
        assert exc.value.code=="DERIVED_ASSET_NOT_FOUND"


def test_original_bytes_or_metadata_changed_fail_closed(tmp_path):
    registry,jobs,job,_,_=make_registry(tmp_path)
    jid=job["job_id"];aid=job["assets"][0]["asset_id"]
    path,_=jobs.get_asset(jid,aid)
    path.write_bytes(encoded("green"))
    with pytest.raises(LiveGateError,match="DERIVED_ORIGINAL_ASSET_CHANGED"):
        registry.resolve_upload("alice",jid,aid)


def test_parent_directory_symlink_is_refused(tmp_path):
    registry,jobs,job,_,_=make_registry(tmp_path)
    jid=job["job_id"];aid=job["assets"][0]["asset_id"]
    original=jobs.root/jid;other=tmp_path/"moved-job";original.rename(other);original.symlink_to(other,target_is_directory=True)
    with pytest.raises(LiveGateError,match="DERIVED_ASSET_INTEGRITY"):
        registry.resolve_upload("alice",jid,aid)


def test_content_symlink_tamper_and_same_sha_wrong_media_are_refused(tmp_path):
    registry,jobs,job,_,_=make_registry(tmp_path)
    jid=job["job_id"]
    ref=registry.put_content("alice",jid,b"caption","text/plain",kind="caption")
    path=registry.root/jid/(ref.sha256+".blob")
    path.unlink();outside=tmp_path/"outside";outside.write_bytes(b"caption");path.symlink_to(outside)
    with pytest.raises(LiveGateError,match="DERIVED_ASSET_INTEGRITY"):
        registry.read_content("alice",jid,ref)
    with pytest.raises(LiveGateError,match="DERIVED_ASSET_INTEGRITY"):
        registry.put_content("alice",jid,b"caption","text/plain",kind="caption")


def test_immutable_concurrent_content_registration(tmp_path):
    registry,jobs,job,_,_=make_registry(tmp_path)
    jid=job["job_id"]
    def publish(_):return registry.put_content("alice",jid,b"caption","text/plain",kind="caption")
    with ThreadPoolExecutor(max_workers=4) as pool:refs=list(pool.map(publish,range(8)))
    assert len({ref.sha256 for ref in refs})==1
    assert registry.read_content("alice",jid,refs[0]).data==b"caption"
    assert not list((registry.root/jid).glob(".pending-*"))


def test_registration_is_bounded_and_documents_strict(tmp_path):
    registry,jobs,job,_,_=make_registry(tmp_path,max_bytes=2048)
    jid=job["job_id"]
    for data,media,kind in [(b"a"*2049,"text/plain","caption"),
                           (b'{"a":1,"a":2}',"application/json","layout"),
                           (b'{"a":NaN}',"application/json","layout"),
                           (b"not a font","font/ttf","font"),
                           (encoded(),"image/png","font")]:
        with pytest.raises((LiveGateError,ValueError)):
            registry.put_content("alice",jid,data,media,kind=kind)


def test_mask_requires_native_gray_and_image_format_matches(tmp_path):
    registry,jobs,job,_,_=make_registry(tmp_path)
    jid=job["job_id"]
    with pytest.raises(LiveGateError,match="DERIVED_MASK_FORMAT"):
        registry.put_content("alice",jid,encoded(),"image/png",kind="product_mask")
    data=encoded(255,mode="L")
    ref=registry.put_content("alice",jid,data,"image/png",kind="product_mask")
    assert registry.read_content("alice",jid,ref).image.mode=="L"
    with pytest.raises(LiveGateError,match="DERIVED_ASSET_IMAGE_FORMAT"):
        inspect_image(data,"image/jpeg")
    with pytest.raises(LiveGateError,match="DERIVED_ASSET_PIXEL_LIMIT"):
        inspect_image(data,"image/png",max_pixels=100)


def test_traversal_upload_alias_and_missing_original_binding_rejected(tmp_path):
    registry,jobs,job,_,_=make_registry(tmp_path)
    with pytest.raises(LiveGateError,match="DERIVED_ASSET_NOT_FOUND"):
        registry.resolve_upload("alice",job["job_id"],"../other")


def test_corrupt_registered_bytes_are_not_repaired_on_read(tmp_path):
    registry,jobs,job,_,_=make_registry(tmp_path)
    jid=job["job_id"]
    ref=registry.put_content("alice",jid,b"caption","text/plain",kind="caption")
    path=registry.root/jid/(ref.sha256+".blob");path.write_bytes(b"changed")
    with pytest.raises(LiveGateError,match="DERIVED_ASSET_INTEGRITY"):
        registry.read_content("alice",jid,ref)
    assert path.read_bytes()==b"changed"


def recipe_assets(registry, job):
    from src.image_generation.protected_recipe import canonical_bytes,canonical_sha
    jid=job["job_id"];aid=job["assets"][0]["asset_id"]
    original=registry.register_upload("alice",jid,aid)
    refs={"source_photo":original.ref.model_dump()}
    copy={"plan":{},"ad_copy":{"headline":"승인 제목","subline":"서브","cta":"보기"},"caption":"글","hashtags":[]}
    contents={
        "product_mask":(encoded(255,size=(9,12),mode="L"),"image/png"),
        "raw_candidate":(encoded("green"),"image/png"),
        "copy_snapshot":(canonical_bytes(copy),"application/json"),
    }
    for role,(data,media) in contents.items():
        refs[role]=registry.put_content("alice",jid,data,media,kind=role).model_dump()
    scene=canonical_bytes({"candidate_sha256":refs["raw_candidate"]["sha256"],"regions":{}})
    refs["scene_review_spec"]=registry.put_content("alice",jid,scene,"application/json",kind="scene_review_spec").model_dump()
    return {
        "schema":"bp18-portable-render-recipe-v1", "render_mode":"freeform_protected_product_hybrid",
        "assets":refs,"code_sha256":{role:"a"*64 for role in ("study_adapter","resize","color_management")},
        "source_tree_sha":"b"*40,"source_icc_sha256":original.image.icc_sha256,
        "roi_spec_sha256":"c"*64,"copy_sha256":canonical_sha(copy),
        "geometry":{"source_size":[9,12],"source_crop":[0,0,9,12],"registered_size":[9,12],
                    "output_offset":[0,0],"output_size":[1080,1350],"resampler":"NONE"},
        "design_id":"hybrid-test-v1","layer_spec_sha256":"d"*64,"alpha_rule":"combined_single_pass_photo_v1",
    },{"source_photo":aid}


def test_recipe_resolution_uses_jobstore_origin_and_distinct_upright_mask(tmp_path):
    registry,jobs,job,raw,_=make_registry(tmp_path)
    body,bindings=recipe_assets(registry,job)
    assets=registry.resolve_recipe("alice",job["job_id"],body,upload_bindings=bindings)
    assert assets["source_photo"].data==raw
    assert assets["source_photo"].image.orientation==6
    assert assets["product_mask"].image.upright_size==(9,12)
    with pytest.raises(LiveGateError,match="DERIVED_ORIGINAL_BINDING_REQUIRED"):
        registry.resolve_recipe("alice",job["job_id"],body)


def test_recipe_context_mismatches_cannot_be_hidden_by_new_semantic_digest(tmp_path):
    from copy import deepcopy
    registry,jobs,job,_,_=make_registry(tmp_path)
    body,bindings=recipe_assets(registry,job)
    for field,value,code in [("copy_sha256","f"*64,"DERIVED_RECIPE_COPY_MISMATCH"),
                             ("source_icc_sha256",None,"DERIVED_RECIPE_SOURCE_CONTEXT_MISMATCH")]:
        changed=deepcopy(body);changed[field]=value
        with pytest.raises(LiveGateError,match=code):
            registry.resolve_recipe("alice",job["job_id"],changed,upload_bindings=bindings)
    changed=deepcopy(body)
    changed["assets"]["scene_review_spec"]=registry.put_content("alice",job["job_id"],
        b'{"candidate_sha256":"wrong"}',"application/json",kind="scene_review_spec").model_dump()
    with pytest.raises(LiveGateError,match="DERIVED_RECIPE_SCENE_CONTEXT_MISMATCH"):
        registry.resolve_recipe("alice",job["job_id"],changed,upload_bindings=bindings)


def test_same_actor_cannot_resolve_upload_alias_from_other_job(tmp_path):
    from fastapi import HTTPException
    registry,jobs,job,_,_=make_registry(tmp_path)
    other=jobs.create_job([ValidatedUpload(name,"image/png",raw,12,9,sha256(raw).hexdigest())
        for name,raw in [("green.png",encoded("green")),("yellow.png",encoded("yellow"))]],[])
    registry.owns=lambda actor,jid: actor=="alice" and jid in {job["job_id"],other["job_id"]}
    with pytest.raises(HTTPException) as exc:
        registry.resolve_upload("alice",other["job_id"],job["assets"][0]["asset_id"])
    assert exc.value.status_code==404


def test_source_binding_cannot_use_reference_image_even_with_same_job_acl(tmp_path):
    registry,jobs,job,_,_=make_registry(tmp_path)
    body,_=recipe_assets(registry,job)
    metadata_path=jobs.root/job["job_id"]/"job.json"
    metadata=json.loads(metadata_path.read_text())
    metadata["assets"][0]["role"]="reference"
    metadata_path.write_text(json.dumps(metadata))
    with pytest.raises(LiveGateError,match="DERIVED_ORIGINAL_BINDING_INVALID"):
        registry.resolve_recipe("alice",job["job_id"],body,
            upload_bindings={"source_photo":job["assets"][0]["asset_id"]})
