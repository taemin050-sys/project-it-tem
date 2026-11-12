"""Phone MPO → Signed upload → AI input → protected preview; no paid model call."""
from hashlib import sha256
from io import BytesIO
import json

from PIL import Image,ImageCms
import pytest

from tests.demo_live.test_derived_http import runtime, signed_env, request, assert_status, ACTOR
from tests.demo_live.test_pipeline import FakeOwner,png
from tests.demo_live.test_live_contracts import sample_input
from demo_staging.live.derived_store import migrate_derived_schema
from demo_staging.live.derived_worker import run_once
from src.image_generation.backend_adapter import BackendGeneratedImage


def phone_mpo(color=(50,100,150)):
    first=Image.new('RGB',(512,768),color);other=Image.new('RGB',(32,24),(200,40,20))
    exif=Image.Exif();exif[274]=6;exif[315]='PRIVATE_CAMERA_OWNER'
    out=BytesIO();first.save(out,'MPO',save_all=True,append_images=[other],exif=exif,
        icc_profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes(),quality=95)
    return out.getvalue()


@pytest.mark.parametrize('tamper',[False,True],ids=['preview','metadata-tamper-blocked'])
def test_signed_mpo_reaches_protected_worker_with_bound_normalization(runtime,tamper):
    client,key,flow=runtime['client'],runtime['key'],runtime['flow'];original=phone_mpo()
    job=assert_status(request(client,key,'POST','/api/v1/jobs',files=[
        ('product_images',('PHONE.MPO',original,'application/octet-stream')),
        ('product_images',('second.png',png((80,90,100)),'image/png')),
        ('reference_images',('reference.mpo',phone_mpo((120,80,60)),'image/mpo'))]),201)
    jid=job['job_id'];asset=job['assets'][0];provenance=asset['source_provenance']
    assert asset['content_type']=='image/jpeg' and (asset['width'],asset['height'])==(768,512)
    assert provenance['original_sha256']==sha256(original).hexdigest()
    assert provenance['converted_sha256']==asset['sha256']
    source_path,_=flow.jobs.get_asset(jid,asset['asset_id']);before=source_path.read_bytes()
    with Image.open(BytesIO(before)) as im:assert im.format=='JPEG' and not im.getexif() and getattr(im,"n_frames",1)==1
    inputs=sample_input();inputs['product']['reference_image_count']=1
    flow.prepare(ACTOR,jid,inputs);owner=FakeOwner();text=flow.text(ACTOR,jid,owner,offline=True)
    flow.state.approve_copy(ACTOR,jid,text['generation'],text['review_sha']);prompt=flow.prompt(ACTOR,jid,owner,offline=True)
    # VLM/Text and Image DTO consume ordinary decoded primary-photo bytes.
    image_input=flow.image_input(ACTOR,jid)
    assert len(image_input.product_images)==2 and len(image_input.reference_images)==1
    raw=png((224,233,239),size=(1152,1440))
    flow.accept_image_result(ACTOR,jid,BackendGeneratedImage(image_bytes=raw,mime_type='image/png',
        width=1152,height=1440,sha256=sha256(raw).hexdigest(),job_id=jid,copy_revision=prompt['generation'],
        copy_hash=prompt['copy_sha'],mock=True,receipt={'mode':'OFFLINE_MOCK_TRANSPORT','provider_calls':0}),offline=True)
    migrate_derived_schema(flow.state.filename);base=f'/demo/api/live/jobs/{jid}/derived'
    def req(method,suffix='',**kw):return request(client,key,method,base+suffix,**kw)
    snap=assert_status(req('GET'),200);p=snap['proposals'][0]
    a=assert_status(req('POST','/recipes/admit',json={'proposal_id':p['proposal_id'],'expected_recipe_sha':p['recipe_sha'],
        'expected_context_sha':snap['context_sha'],'expected_revision':snap['revision'],'acknowledge_source':True}),200)
    row=assert_status(req('POST','/renders',json={'admission_sha':a['admission_sha'],'expected_recipe_sha':a['recipe_sha'],
        'expected_context_sha':a['context_sha'],'idempotency_key':'b'*64}),202)
    service=runtime['app'].state.derived_service
    if tamper:
        path=flow.jobs.root/jid/'job.json';record=json.loads(path.read_text())
        record['assets'][0]['source_provenance']['original_sha256']='0'*64;path.write_text(json.dumps(record))
    result=run_once(service,worker_id='OFFLINE_MPO_INTEGRATION')
    if tamper:
        assert result['state']=='HOLD' and result['error_code']=='DERIVED_UPLOAD_PROVENANCE_CHANGED'
    else:
        assert result['state']=='REVIEW_REQUIRED',result
        saved=service.store.get_render(ACTOR,jid,row['derived_id'])
        receipt=json.loads(service.registry.read_content(ACTOR,jid,saved['artifacts']['local_receipt']).data)
        assert receipt['source_upload_provenance']==provenance
        assert receipt['source_photo_sha']==asset['sha256'] and receipt['opaque_rgb_mismatches']==0
        assert receipt['provider_calls']==0
    assert source_path.read_bytes()==before
