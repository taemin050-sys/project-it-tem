"""Final-ad inpainting: real multipart adapter, local MockTransport, no paid I/O."""
from email import policy
from email.parser import BytesParser
from hashlib import sha256
from io import BytesIO
import base64
import json

import httpx
from PIL import Image,ImageDraw,ImageChops
import pytest
from fastapi import FastAPI,HTTPException
from fastapi.testclient import TestClient

from demo_staging.live.contracts import LiveGateError
from demo_staging.live.final_inpainting import FinalInpainting,decode_selection,run_final_inpainting_once,merge_selected
from demo_staging.live.image_correction_api import install_image_correction_routes,InpaintingRequest
from demo_staging.live.revision_costs import revision_cost_summary
from src.image_generation.openai_images import OpenAIImagesAdapter,OpenAIImagesConfig
from tests.demo_live.test_live_dual_mock_transport import (
    ACTOR,OTHER_ACTOR,dual_runtime,signed_env,prepare_direct,run_stage,visual_approval,attempts,
)


def png(im):
    out=BytesIO();im.save(out,'PNG');return out.getvalue()


def selection(size):
    mask=Image.new('RGBA',size,(0,0,0,0));draw=ImageDraw.Draw(mask)
    draw.ellipse((20,20,160,180),fill=(255,0,90,255))
    draw.rectangle((60,70,90,100),fill=(0,0,0,0)) # eraser hole must stay untouched
    return base64.b64encode(png(mask)).decode()


@pytest.fixture
def final_ad(dual_runtime,monkeypatch):
    root,_,flow,parent,group,_=prepare_direct(dual_runtime,monkeypatch)
    for _ in range(3):assert run_stage(root)=='LIVE_STAGE_COMMITTED'
    child=group['child_job_id']
    visual_approval(flow,parent);visual_approval(flow,child)
    monkeypatch.setenv('IT_TEM_IMAGE_CORRECTION_ENABLED','YES')
    monkeypatch.setenv('IT_TEM_IMAGE_CORRECTION_PROTOCOL','FREEFORM_TEXT_EDIT_V1')
    return flow,FinalInpainting(flow),parent,child


def body_for(service,jid,key='1'*32):
    snapshot=service.snapshot(ACTOR,jid)
    return dict(expected_image_sha=snapshot['source_image_sha'],expected_copy_sha=snapshot['copy_sha'],
        expected_approval_sha=snapshot['approval_sha'],mask_png_base64=selection(tuple(snapshot['source_size'])),
        prompt='왼쪽 배경의 물방울만 지워 주세요.',request_key=key,acknowledge_paid_edit=True)


def adapter(calls,fail=False):
    def wire(req):
        calls.append(req)
        parts=BytesParser(policy=policy.default).parsebytes(b'Content-Type: '+req.headers['content-type'].encode()+b'\r\n\r\n'+req.read())
        data={p.get_param('name',header='content-disposition'):p.get_payload(decode=True) for p in parts.iter_parts()}
        assert req.url.path=='/v1/images/edits' and data['n']==b'1'
        with Image.open(BytesIO(data['image[]'])) as source,Image.open(BytesIO(data['mask'])) as mask:
            assert source.size==mask.size==(1088,1408)
            assert mask.getpixel((75,80))[3]==255 # eraser hole is protected
            assert mask.getpixel((40,90))[3]==0
        if fail:raise httpx.ReadTimeout('unknown submission',request=req)
        raw=png(Image.new('RGBA',(1088,1408),(240,130,20,255)))
        return httpx.Response(200,json={'data':[{'b64_json':base64.b64encode(raw).decode()}],
            'usage':{'input_tokens':5,'output_tokens':7,'total_tokens':12}},headers={'x-request-id':'mock-final-inpainting'})
    return OpenAIImagesAdapter(OpenAIImagesConfig(live_calls=False),transport=httpx.MockTransport(wire))


@pytest.mark.parametrize('mode',['composed','freeform'])
def test_final_source_is_independent_one_call_exact_mask_and_human_export(final_ad,mode):
    flow,service,parent,child=final_ad;jid=parent if mode=='composed' else child
    before={j:flow.state.get(ACTOR,j) for j in (parent,child)}
    old=attempts(flow); original=(flow.root/'outputs'/jid/'final.png').read_bytes()
    body=body_for(service,jid);row=service.request(ACTOR,jid,body)
    assert service.request(ACTOR,jid,body)==row
    calls=[]
    assert run_final_inpainting_once(flow,transport=adapter(calls))=='INPAINT_REVIEW_REQUIRED'
    assert run_final_inpainting_once(flow,transport=adapter(calls))=='NO_FINAL_INPAINT_TASK'
    assert len(calls)==1
    current=service.snapshot(ACTOR,jid)['corrections'][0]
    assert current['source_scope']=='APPROVED_FINAL_AD' and current['source_mode']==mode
    preview,_=service.artifact(ACTOR,jid,row['correction_id'],'preview',current['preview_sha'])
    mask,_=decode_selection(body['mask_png_base64'],(1080,1350))
    with Image.open(BytesIO(original)) as a,Image.open(BytesIO(preview)) as b:
        difference=ImageChops.difference(a.convert('RGB'),b.convert('RGB'))
        assert difference.getbbox()
        assert ImageChops.multiply(difference,Image.eval(mask,lambda v:255-v).convert('RGB')).getbbox() is None
        assert a.getpixel((75,80))==b.getpixel((75,80)) # erased part not edited
    with pytest.raises(LiveGateError,match='ARTIFACT_STATE'):
        service.artifact(ACTOR,jid,row['correction_id'],'final','0'*64)
    checks=dict(product_matches=True,label_matches=True,cta_policy_matches=True,no_extra_text=True,
        observed_copy=service.snapshot(ACTOR,jid)['approved_copy'])
    decision=dict(expected_revision=current['revision'],expected_preview_sha=current['preview_sha'],approve=True,visual_review=checks)
    result=service.decision(ACTOR,jid,row['correction_id'],decision)
    assert result['state']=='COMPLETED'
    for kind in ('final','caption','receipt'):
        raw,_=service.artifact(ACTOR,jid,row['correction_id'],kind,result[kind+'_sha'])
        assert sha256(raw).hexdigest()==result[kind+'_sha']
    receipt=json.loads(raw)
    assert receipt['protocol']=='FINAL_AD_INPAINT_V1' and receipt['human_review']['protocol']=='FINAL_AD_INPAINT_V1'
    assert receipt['outside_region_preserved'] and receipt['provider_calls']==1
    assert {j:flow.state.get(ACTOR,j) for j in(parent,child)}==before
    assert (flow.root/'outputs'/jid/'final.png').read_bytes()==original and attempts(flow)[:-1]==old
    cost=revision_cost_summary(flow,ACTOR,jid)
    assert cost['provider_attempt_count']==1 and cost['revisions'][0]['kind']=='final_inpainting'
    assert cost['excluded_attempt_ids']==[attempts(flow)[-1]['id']]
    with pytest.raises(LiveGateError):service.decision(ACTOR,jid,row['correction_id'],decision)


def test_unknown_submission_never_automatically_retries_across_namespaces(final_ad):
    flow,service,parent,child=final_ad
    service.request(ACTOR,parent,body_for(service,parent));calls=[]
    assert run_final_inpainting_once(flow,transport=adapter(calls,True))=='INPAINT_BILLING_UNKNOWN'
    assert run_final_inpainting_once(flow,transport=adapter(calls))=='INPAINT_BILLING_UNKNOWN'
    from demo_staging.live.result_revision_worker import run_result_revision_once
    assert 'BILLING_UNKNOWN' in run_result_revision_once(flow)
    assert len(calls)==1
    with pytest.raises(LiveGateError):service.request(ACTOR,child,body_for(service,child,'2'*32))


def test_restarted_claim_has_no_second_send(final_ad):
    flow,service,parent,_=final_ad
    service.request(ACTOR,parent,body_for(service,parent))
    with service.db() as db:db.execute("UPDATE image_corrections SET state='RUNNING'")
    calls=[]
    assert run_final_inpainting_once(flow,transport=adapter(calls))=='INPAINT_BILLING_UNKNOWN'
    assert calls==[]


def test_api_actor_cas_tamper_rejection_and_completed_gate(final_ad):
    flow,service,parent,child=final_ad
    app=FastAPI()
    app.state.demo_request_identity=lambda req:(req.headers.get('x-actor',ACTOR),'evaluator')
    def authorized(req,jid=None):
        actor=req.headers.get('x-actor',ACTOR)
        if actor!=ACTOR:raise HTTPException(404,'Job not found')
        return actor
    install_image_correction_routes(app,flow,authorized,lambda _:None,service_type=FinalInpainting,
        namespace='final-inpainting',request_model=InpaintingRequest)
    base=f'/demo/api/live/jobs/{parent}/final-inpainting'
    with TestClient(app) as client:
        body=body_for(service,parent)
        assert client.get(base,headers={'x-actor':OTHER_ACTOR}).status_code==404
        assert client.post(base,json={**body,'extra':True}).status_code==422
        assert client.post(base,json={**body,'expected_image_sha':'0'*64}).status_code==409
        admitted=client.post(base,json=body)
        assert admitted.status_code==202,admitted.text
        assert client.post(base,json={**body,'prompt':'다른 요청입니다'}).status_code==409
        calls=[];run_final_inpainting_once(flow,transport=adapter(calls))
        row=client.get(base).json()['corrections'][0]
        assert client.post(base+f'/{row["correction_id"]}/decision',json=dict(
            expected_revision=row['revision'],expected_preview_sha=row['preview_sha'],approve=True)).status_code==409
        assert client.post(base+f'/{row["correction_id"]}/decision',json=dict(
            expected_revision=row['revision'],expected_preview_sha=row['preview_sha'],approve=False)).status_code==200
        assert client.get(row['artifacts']['preview']).status_code==409
    with service.db() as db:db.execute("UPDATE image_corrections SET payload_json=replace(payload_json,'물방울','다른말')")
    with pytest.raises(LiveGateError):service.snapshot(ACTOR,parent)


@pytest.mark.parametrize('size',[(1080,1440),(1080,1350),(1080,1920)])
def test_all_ratios_mask_pixel_coordinates_transparent_output(size):
    mask,count=decode_selection(selection(size),size)
    original=png(Image.new('RGB',size,(80,160,220)))
    generated=png(Image.new('RGBA',size,(0,0,0,0)))
    result=merge_selected(original,generated,mask)
    assert Image.open(BytesIO(result)).tobytes()==Image.open(BytesIO(original)).tobytes()
    assert count>0 and mask.getpixel((75,80))==0


@pytest.mark.parametrize('bad',['not-base64','',base64.b64encode(png(Image.new('RGBA',(100,100)))).decode(),
    base64.b64encode(png(Image.new('RGBA',(1080,1350),(255,255,255,255)))).decode(),
    base64.b64encode(png(Image.new('RGB',(1080,1350)))).decode(),
    base64.b64encode(png(Image.new('RGBA',(1080,1350)))).decode()])
def test_invalid_empty_wrong_size_or_whole_image_masks_rejected(bad):
    with pytest.raises(LiveGateError):decode_selection(bad,(1080,1350))


def test_revoked_source_f09_or_mask_tamper_cannot_dispatch(final_ad):
    flow,service,parent,_=final_ad
    row=service.request(ACTOR,parent,body_for(service,parent))
    before=len(attempts(flow))
    with flow.state.db() as db:db.execute("UPDATE live_jobs SET review_sha=? WHERE job_id=?",('0'*64,parent))
    calls=[]
    assert run_final_inpainting_once(flow,transport=adapter(calls))=='INPAINT_HOLD'
    assert calls==[] and len(attempts(flow))==before


def test_file_failure_after_billed_response_is_hold_without_replay(final_ad,monkeypatch):
    from demo_staging.live import final_inpainting as module
    flow,service,parent,_=final_ad
    service.request(ACTOR,parent,body_for(service,parent));original=module.atomic_write
    def fail(path,raw):
        if path.name=='preview.png':raise OSError('simulated publication crash')
        return original(path,raw)
    monkeypatch.setattr(module,'atomic_write',fail);calls=[]
    assert run_final_inpainting_once(flow,transport=adapter(calls))=='INPAINT_HOLD'
    assert run_final_inpainting_once(flow,transport=adapter(calls))=='NO_FINAL_INPAINT_TASK'
    assert len(calls)==1 and attempts(flow)[-1]['status']=='SUCCEEDED_USAGE_UNPRICED'
    row=service.snapshot(ACTOR,parent)['corrections'][0]
    assert row['state']=='HOLD' and not row['artifacts']


def test_legacy_hard_edge_refinement_is_nonbillable_cas_and_preserves_both_versions(final_ad):
    from demo_staging.live.contracts import digest
    flow,service,parent,_=final_ad
    admitted=service.request(ACTOR,parent,body_for(service,parent))
    # Historical v1 rows did not contain the opt-in postprocess version. Keep
    # their exact old request shape in this isolated store, never production.
    with service.db() as db:
        row=dict(db.execute('SELECT * FROM image_corrections').fetchone());payload=json.loads(row['payload_json']);payload.pop('edge_blend_version')
        db.execute('UPDATE image_corrections SET payload_json=?,request_sha=?',(json.dumps(payload),digest(payload)))
    calls=[];assert run_final_inpainting_once(flow,transport=adapter(calls))=='INPAINT_REVIEW_REQUIRED'
    old=service.snapshot(ACTOR,parent)['corrections'][0];assert not old['edge_blend_applied']
    old_preview=service.artifact(ACTOR,parent,old['correction_id'],'preview',old['preview_sha'])[0]
    old_receipt=service.artifact(ACTOR,parent,old['correction_id'],'receipt',old['receipt_sha'])[0]
    cost_before=attempts(flow)
    checks=dict(product_matches=True,label_matches=True,cta_policy_matches=True,no_extra_text=True,observed_copy=service.snapshot(ACTOR,parent)['approved_copy'])
    with pytest.raises(LiveGateError,match='EDGE_BLEND_REQUIRED'):
        service.decision(ACTOR,parent,old['correction_id'],dict(expected_revision=old['revision'],expected_preview_sha=old['preview_sha'],approve=True,visual_review=checks))
    new=service.blend_edges(ACTOR,parent,old['correction_id'],dict(expected_revision=old['revision'],expected_preview_sha=old['preview_sha']))
    assert new['edge_blend_applied'] and new['preview_sha']!=old['preview_sha'] and new['revision']==old['revision']+1
    folder=service.root/old['correction_id']
    assert (folder/'preview.png').read_bytes()==old_preview and (folder/'receipt.json').read_bytes()==old_receipt
    assert attempts(flow)==cost_before and len(calls)==1
    with pytest.raises(LiveGateError):service.artifact(ACTOR,parent,old['correction_id'],'preview',old['preview_sha'])
    final=service.decision(ACTOR,parent,new['correction_id'],dict(expected_revision=new['revision'],expected_preview_sha=new['preview_sha'],approve=True,visual_review=checks))
    for kind in ('final','caption','receipt'):assert service.artifact(ACTOR,parent,new['correction_id'],kind,final[kind+'_sha'])[0]
    assert revision_cost_summary(flow,ACTOR,parent)['provider_attempt_count']==1


def test_edge_feather_preserves_a_deliberate_one_pixel_selection_and_exact_outside():
    source=png(Image.new('RGB',(30,30),(120,140,150)));generated=png(Image.new('RGB',(30,30),(30,50,60)))
    mask=Image.new('L',(30,30));mask.putpixel((15,15),255)
    result=Image.open(BytesIO(merge_selected(source,generated,mask,feather=True)))
    assert result.getpixel((15,15))==(30,50,60)
    assert result.getpixel((14,15))==(120,140,150)
