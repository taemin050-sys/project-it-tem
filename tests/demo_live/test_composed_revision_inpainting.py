"""Approved revised Composed ads reuse the masked final-ad Worker, no paid I/O."""
from hashlib import sha256
from io import BytesIO
import json
import pytest
from PIL import Image,ImageChops,ImageOps
from fastapi.testclient import TestClient
from demo_staging.live.composed_copy_edit import ComposedCopyEdits,run_composed_copy_edit_once
from demo_staging.live.final_inpainting import FinalInpainting,run_final_inpainting_once,decode_selection
from demo_staging.live.contracts import LiveGateError
from tests.demo_live.test_composed_copy_edit import case,body
from tests.demo_live.test_live_dual_mock_transport import dual_runtime,signed_env,ACTOR,OTHER_ACTOR,attempts,signed_request
from tests.demo_live.test_final_inpainting import selection,adapter

CHECKS=dict(product_matches=True,label_matches=True,cta_policy_matches=True,no_extra_text=True,copy_verified=True)

@pytest.fixture
def revision(case,monkeypatch):
    root,host,key,app,flow,_,parent,child,_=case
    monkeypatch.setenv('IT_TEM_IMAGE_CORRECTION_ENABLED','YES')
    monkeypatch.setenv('IT_TEM_IMAGE_CORRECTION_PROTOCOL','FREEFORM_TEXT_EDIT_V1')
    edits=ComposedCopyEdits(flow);r=edits.create(ACTOR,parent,body(flow,parent))
    assert run_composed_copy_edit_once(flow)=='COMPOSED_COPY_EDIT_REVIEW_COMMITTED'
    r=edits.snapshot(ACTOR,parent)['edits'][0]
    return flow,edits,r,parent,child,(host,key,app)

def approve_revision(edits,r,parent):
    r=edits.approve_copy(ACTOR,parent,r['edit_id'],dict(expected_revision=r['revision'],expected_copy_sha=r['copy_sha'],
        expected_review_sha=r['review_sha'],acknowledge_evidence=True))
    return edits.decide(ACTOR,parent,r['edit_id'],dict(expected_revision=r['revision'],expected_preview_sha=r['preview_sha'],
        approve=True,visual_review=CHECKS))

def request_for(s):
    return dict(expected_image_sha=s['source_image_sha'],expected_copy_sha=s['copy_sha'],expected_approval_sha=s['approval_sha'],
        mask_png_base64=selection(tuple(s['source_size'])),prompt='왼쪽 물방울만 지워 주세요.',request_key='d'*32,
        acknowledge_paid_edit=True,source_edit_id=s['source_edit_id'])

def test_revised_final_api_worker_review_download_without_original_image_approval(revision):
    flow,edits,r,parent,child,(host,key,app)=revision;service=FinalInpainting(flow)
    with pytest.raises(LiveGateError):service.snapshot(ACTOR,parent,r['edit_id'])
    r=approve_revision(edits,r,parent)
    assert flow.state.get(ACTOR,parent)['state']=='IMAGE_REVIEW_REQUIRED'
    with pytest.raises(LiveGateError):service.snapshot(ACTOR,parent)
    before={j:flow.state.get(ACTOR,j) for j in (parent,child)};cost=attempts(flow)
    original=edits.artifact(ACTOR,parent,r['edit_id'],'final',r['final_sha'])
    base=f'/demo/api/live/jobs/{parent}/final-inpainting';query='?source_edit_id='+r['edit_id']
    with TestClient(app,base_url=f'https://{host}') as client:
        response=signed_request(client,host,key,'GET',base+query);assert response.status_code==200,response.text
        s=response.json();assert s['source_scope']=='APPROVED_COMPOSED_COPY_EDIT' and s['copy_sha']==r['copy_sha']
        assert s['approved_copy']==r['copy']['ad_copy'] and s['source_image_sha']==r['final_sha']
        png=signed_request(client,host,key,'GET',s['source_artifact']);assert png.status_code==200 and png.content==original
        assert signed_request(client,host,key,'GET',base+query,actor=OTHER_ACTOR).status_code==404
        assert signed_request(client,host,key,'GET',base).status_code==409
        from demo_staging.live.worker import exclusive_live_worker
        with exclusive_live_worker(flow.root.parent):
            posted=signed_request(client,host,key,'POST',base,json=request_for(s))
        assert posted.status_code==202,posted.text
        pending=posted.json();assert attempts(flow)==cost
    assert service.request(ACTOR,parent,request_for(s))==pending
    calls=[];assert run_final_inpainting_once(flow,transport=adapter(calls))=='INPAINT_REVIEW_REQUIRED'
    assert len(calls)==1 and run_final_inpainting_once(flow,transport=adapter(calls))=='NO_FINAL_INPAINT_TASK'
    assert r['copy']['ad_copy']['headline'].encode() in calls[0].read()
    row=service.snapshot(ACTOR,parent,r['edit_id'])['corrections'][0]
    preview,_=service.artifact(ACTOR,parent,row['correction_id'],'preview',row['preview_sha'])
    mask,_=decode_selection(request_for(s)['mask_png_base64'],(1080,1350))
    diff=ImageChops.difference(Image.open(BytesIO(original)).convert('RGB'),Image.open(BytesIO(preview)).convert('RGB'))
    assert diff.getbbox() and ImageChops.multiply(diff,ImageOps.invert(mask).convert('RGB')).getbbox() is None
    done=service.decision(ACTOR,parent,row['correction_id'],dict(expected_revision=row['revision'],expected_preview_sha=row['preview_sha'],approve=True,visual_review=CHECKS))
    for kind in ('final','caption','receipt'):
        raw,_=service.artifact(ACTOR,parent,row['correction_id'],kind,done[kind+'_sha']);assert sha256(raw).hexdigest()==done[kind+'_sha']
    receipt=json.loads(raw);assert receipt['source_context']['source_edit_id']==r['edit_id']
    assert receipt['source_context']['copy_sha']==r['copy_sha']
    assert edits.artifact(ACTOR,parent,r['edit_id'],'final',r['final_sha'])==original
    assert {j:flow.state.get(ACTOR,j) for j in (parent,child)}==before and attempts(flow)[:-1]==cost

@pytest.mark.parametrize('defect',['revoked','receipt','f09','wrong_revision'])
def test_changed_revised_source_cannot_dispatch(revision,defect):
    flow,edits,r,parent,child,_=revision;r=approve_revision(edits,r,parent);service=FinalInpainting(flow)
    s=service.snapshot(ACTOR,parent,r['edit_id']);pending=service.request(ACTOR,parent,request_for(s));cost=attempts(flow)
    if defect=='receipt':edits._artifact_path(r,'receipt').write_bytes(b'tampered')
    else:
        with edits.db() as db:
            row=json.loads(db.execute('SELECT record_json FROM composed_copy_edits').fetchone()[0])
            if defect=='revoked':row['state']='REJECTED'
            elif defect=='f09':row['cost_receipt']['receipt_sha']='0'*64
            else:row['revision']+=1
            edits._save(db,row);db.commit()
    calls=[];assert run_final_inpainting_once(flow,transport=adapter(calls))=='INPAINT_HOLD'
    assert calls==[] and attempts(flow)==cost
