"""Bounded correction tests use an in-process wire fixture; never a real model."""
from email import policy
from email.parser import BytesParser
from hashlib import sha256
from io import BytesIO
import base64
import json

import httpx
from PIL import Image
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from demo_staging.live.contracts import LiveGateError
from demo_staging.live.image_correction import ImageCorrections, run_image_correction_once
from demo_staging.live.image_correction_api import install_image_correction_routes
from src.image_generation.openai_images import OpenAIImagesAdapter, OpenAIImagesConfig
from tests.demo_live.test_live_dual_mock_transport import (
    ACTOR, OTHER_ACTOR, dual_runtime, signed_env, prepare_direct, run_stage, attempts,
)


@pytest.fixture
def repair(dual_runtime,monkeypatch):
    root,host,key,app,flow,text=dual_runtime
    _,queue,_,parent,group,calls=prepare_direct(dual_runtime,monkeypatch)
    for _ in range(3): assert run_stage(root)=="LIVE_STAGE_COMMITTED"
    child=group["child_job_id"]
    flow.state.reject_image(ACTOR,child,flow.state.get(ACTOR,child)["image_sha"])
    monkeypatch.setenv("IT_TEM_IMAGE_CORRECTION_ENABLED","YES")
    monkeypatch.setenv("IT_TEM_IMAGE_CORRECTION_PROTOCOL","FREEFORM_TEXT_EDIT_V1")
    service=ImageCorrections(flow)
    job=flow.state.get(ACTOR,child)
    body={"expected_image_sha":job["image_sha"],"expected_copy_sha":job["copy_sha"],
        "expected_approval_sha":job["approval_sha"],"field":"subline","observed_text":"자분하게 시작해요",
        "region":[.1,.2,.8,.3],"request_key":"1"*32,"acknowledge_paid_edit":True}
    return flow,service,parent,child,body


def wire_transport(flow,child,calls,*,failure=None):
    with Image.open(flow.image_path(child)) as im:size=im.size
    out=BytesIO();Image.new("RGB",size,(4,190,90)).save(out,"PNG")
    def wire(request):
        calls.append(request)
        assert request.url.path=="/v1/images/edits"
        parts=BytesParser(policy=policy.default).parsebytes(
            b"Content-Type: "+request.headers["content-type"].encode()+b"\r\n\r\n"+request.read())
        data={part.get_param("name",header="content-disposition"):part.get_payload(decode=True)
              for part in parts.iter_parts()}
        assert "mask" in data and "image[]" in data
        with Image.open(BytesIO(data["mask"])) as matte, Image.open(BytesIO(data["image[]"])) as source:
            assert matte.getchannel("A").getextrema()==(0,255)
            assert matte.convert("RGB").tobytes()==source.convert("RGB").tobytes()
        assert "사각형" in data["prompt"].decode("utf-8")
        assert any(key in data["prompt"].decode("utf-8") for key in ("approved_full_field_context", '"correct"'))
        if failure:
            response=failure(request)
            if response is not None:return response
        return httpx.Response(200,json={"data":[{"b64_json":base64.b64encode(out.getvalue()).decode()}],
            "usage":{"input_tokens":5,"output_tokens":7,"total_tokens":12}},headers={"x-request-id":"mock-text-repair-1"})
    return OpenAIImagesAdapter(OpenAIImagesConfig(live_calls=False),transport=httpx.MockTransport(wire))


def test_rejected_source_repair_one_call_preserves_outside_region_and_old_ledgers(repair):
    flow,service,parent,child,body=repair
    old_states={jid:flow.state.get(ACTOR,jid) for jid in(parent,child)}
    old_cost=attempts(flow)
    source=flow.image_path(child).read_bytes()
    old_receipt=(flow.root/"outputs"/child/"owner_candidate_receipt.json").read_bytes()
    admitted=service.request(ACTOR,child,body)
    assert service.request(ACTOR,child,body)==admitted
    calls=[]
    assert run_image_correction_once(flow,transport=wire_transport(flow,child,calls))=="IMAGE_CORRECTION_REVIEW_REQUIRED"
    assert len(calls)==1
    assert run_image_correction_once(flow,transport=wire_transport(flow,child,calls))=="NO_IMAGE_CORRECTION_TASK"
    result=service.snapshot(ACTOR,child)["corrections"][0]
    assert result["state"]=="REVIEW_REQUIRED" and result["render_mode"]=="freeform_model_text_corrected_v1"
    assert result["approved_copy"]["subline"]==result["target_text"]
    preview,_=service.artifact(ACTOR,child,result["correction_id"],"preview",result["preview_sha"])
    receipt_raw,_=service.artifact(ACTOR,child,result["correction_id"],"receipt",result["receipt_sha"])
    receipt=json.loads(receipt_raw)
    assert receipt["outside_region_preserved"] and receipt["server_text_overlay"] is False
    assert receipt["visual_text_fidelity"]=="HUMAN_REVIEW_PENDING" and receipt["provider_calls"]==1
    box=receipt["region_pixels"]
    with Image.open(BytesIO(source)) as original,Image.open(BytesIO(preview)) as corrected:
        assert original.getpixel((0,0))==corrected.getpixel((0,0))
        assert original.getpixel((box[0],box[1]))!=corrected.getpixel((box[0],box[1]))
        assert original.getpixel((box[2],box[3]))==corrected.getpixel((box[2],box[3]))
    assert flow.image_path(child).read_bytes()==source
    assert (flow.root/"outputs"/child/"owner_candidate_receipt.json").read_bytes()==old_receipt
    assert {jid:flow.state.get(ACTOR,jid) for jid in(parent,child)}==old_states
    assert attempts(flow)[:-1]==old_cost and attempts(flow)[-1]["status"]=="SUCCEEDED_USAGE_UNPRICED"
    with pytest.raises(LiveGateError,match="ARTIFACT_STATE"):
        service.artifact(ACTOR,child,result["correction_id"],"final","0"*64)


@pytest.mark.parametrize("patch,code",[
    ({"expected_copy_sha":"0"*64},"STALE"),
    ({"expected_image_sha":"0"*64},"STALE"),
    ({"expected_approval_sha":"0"*64},"STALE"),
    ({"region":[0,0,1,1]},"REGION"),
    ({"region":[0,.4,float("nan"),.5]},"REGION"),
    ({"region":[.8,.3,.1,.2]},"REGION"),
    ({"acknowledge_paid_edit":False},"REQUEST"),
    ({"field":"caption"},"REQUEST"),
])
def test_invalid_request_never_reserves_cost(repair,patch,code):
    flow,service,parent,child,body=repair
    before=attempts(flow)
    with pytest.raises(LiveGateError,match=code):service.request(ACTOR,child,{**body,**patch})
    assert attempts(flow)==before


def test_actor_cross_scope_and_duplicate_body_conflict(repair):
    flow,service,parent,child,body=repair
    with pytest.raises(LiveGateError):service.snapshot(OTHER_ACTOR,child)
    service.request(ACTOR,child,body)
    with pytest.raises(LiveGateError,match="IDEMPOTENCY_CONFLICT"):
        service.request(ACTOR,child,{**body,"observed_text":"a different typo"})
    with pytest.raises(LiveGateError,match="OUTSTANDING"):
        service.request(ACTOR,child,{**body,"request_key":"2"*32})


def test_timeout_is_unknown_and_blocks_new_request_and_worker_replay(repair):
    flow,service,parent,child,body=repair
    service.request(ACTOR,child,body)
    calls=[]
    transport=wire_transport(flow,child,calls,failure=lambda req:(_ for _ in()).throw(httpx.ReadTimeout("wire",request=req)))
    assert run_image_correction_once(flow,transport=transport)=="IMAGE_CORRECTION_BILLING_UNKNOWN"
    assert run_image_correction_once(flow,transport=transport)=="IMAGE_CORRECTION_BILLING_UNKNOWN"
    assert len(calls)==1 and attempts(flow)[-1]["billing_unknown"]==1
    with pytest.raises(LiveGateError,match="OUTSTANDING"):
        service.request(ACTOR,child,{**body,"request_key":"2"*32})


def test_restart_never_reclaims_running_correction(repair):
    flow,service,parent,child,body=repair
    service.request(ACTOR,child,body)
    with service.db() as db:db.execute("UPDATE image_corrections SET state='RUNNING'")
    calls=[]
    assert run_image_correction_once(flow,transport=wire_transport(flow,child,calls))=="IMAGE_CORRECTION_BILLING_UNKNOWN"
    assert calls==[] and len(attempts(flow))==7


def test_source_changed_before_execution_holds_without_provider(repair):
    flow,service,parent,child,body=repair
    service.request(ACTOR,child,body)
    flow.image_path(child).write_bytes(b"tampered")
    calls=[]
    assert run_image_correction_once(flow,transport=object())=="IMAGE_CORRECTION_HOLD"
    assert calls==[] and len(attempts(flow))==7


def test_approval_is_new_exact_review_and_output_size(repair):
    flow,service,parent,child,body=repair
    result=service.request(ACTOR,child,body)
    calls=[];run_image_correction_once(flow,transport=wire_transport(flow,child,calls))
    result=service.snapshot(ACTOR,child)["corrections"][0]
    checks={"product_matches":True,"label_matches":True,"cta_policy_matches":True,"no_extra_text":True,
        "observed_copy":{**result["approved_copy"],"subline":body["observed_text"]}}
    decision={"expected_preview_sha":result["preview_sha"],"expected_revision":result["revision"],"approve":True,"visual_review":checks}
    with pytest.raises(LiveGateError,match="VISUAL_REVIEW_REQUIRED"):
        service.decision(ACTOR,child,result["correction_id"],decision)
    checks["observed_copy"]=result["approved_copy"]
    completed=service.decision(ACTOR,child,result["correction_id"],decision)
    assert completed["state"]=="COMPLETED" and completed["approval_sha"]!=body["expected_approval_sha"]
    raw,_=service.artifact(ACTOR,child,completed["correction_id"],"final",completed["final_sha"])
    assert Image.open(BytesIO(raw)).size==(1080,1350)
    with pytest.raises(LiveGateError,match="STATE_CONFLICT"):
        service.decision(ACTOR,child,result["correction_id"],decision)
    assert len(calls)==1 and flow.state.get(ACTOR,child)["state"]=="IMAGE_REJECTED"


def test_feature_off_no_new_files(repair,monkeypatch):
    flow,service,parent,child,body=repair
    monkeypatch.setenv("IT_TEM_IMAGE_CORRECTION_ENABLED","NO")
    assert run_image_correction_once(flow)=="NO_IMAGE_CORRECTION_TASK"
    with pytest.raises(LiveGateError,match="DISABLED"):service.request(ACTOR,child,body)
    assert not service.file.exists()


def test_signed_api_parent_acl_source_is_for_correction_only(repair,dual_runtime,monkeypatch):
    flow,service,parent,child,body=repair
    root,host,key,app,_,_=dual_runtime
    from demo_staging.live import http_api
    from tests.demo_live.test_live_dual_mock_transport import signed_request
    monkeypatch.setattr(http_api,"_worker_holds_lock",lambda _:True)
    if not hasattr(app.state,"image_corrections"):
        def authorized(request,job_id=None):
            identity=app.state.demo_request_identity(request)
            if not identity:raise HTTPException(401,"Login required")
            actor=identity[0]
            # The fake test boundary deliberately mirrors the parent-only ACL.
            if job_id and not (actor==ACTOR and job_id==parent):raise HTTPException(404,"Job not found")
            return actor
        install_image_correction_routes(app,flow,authorized,lambda _:None)
    with TestClient(app,base_url=f"https://{host}") as client:
        base=f"/demo/api/live/jobs/{child}/image-corrections"
        assert client.get(base).status_code==401
        assert signed_request(client,host,key,"GET",base,actor=OTHER_ACTOR).status_code==404
        listing=signed_request(client,host,key,"GET",base)
        assert listing.status_code==200,listing.text
        snapshot=listing.json()
        source=signed_request(client,host,key,"GET",snapshot["source_artifact"])
        assert source.status_code==200 and source.headers["x-it-tem-review"]=="SOURCE_FOR_CORRECTION_ONLY"
        assert sha256(source.content).hexdigest()==body["expected_image_sha"]
        request=signed_request(client,host,key,"POST",base,json=body)
        assert request.status_code==202,request.text
        assert request.json()["state"]=="QUEUED"
        monkeypatch.setenv("IT_TEM_IMAGE_CORRECTION_ENABLED","NO")
        off=signed_request(client,host,key,"GET",base)
        assert off.status_code==200 and off.json()["available"] is False


def test_missing_visual_review_does_not_approve(repair):
    flow,service,parent,child,body=repair
    service.request(ACTOR,child,body)
    run_image_correction_once(flow,transport=wire_transport(flow,child,[]))
    result=service.snapshot(ACTOR,child)["corrections"][0]
    with pytest.raises(LiveGateError,match="VISUAL_REVIEW_REQUIRED"):
        service.decision(ACTOR,child,result["correction_id"],{"expected_revision":0,
            "expected_preview_sha":result["preview_sha"],"approve":True,"visual_review":None})
    assert service.snapshot(ACTOR,child)["corrections"][0]["state"]=="REVIEW_REQUIRED"


def test_receipt_tamper_blocks_new_approval(repair):
    flow,service,parent,child,body=repair
    service.request(ACTOR,child,body)
    run_image_correction_once(flow,transport=wire_transport(flow,child,[]))
    result=service.snapshot(ACTOR,child)["corrections"][0]
    (service.root/result["correction_id"]/"receipt.json").write_text('{}')
    with pytest.raises(LiveGateError,match="RECEIPT_INTEGRITY"):
        service.decision(ACTOR,child,result["correction_id"],{"expected_revision":0,
            "expected_preview_sha":result["preview_sha"],"approve":True,"visual_review":{
                "product_matches":True,"label_matches":True,"cta_policy_matches":True,"no_extra_text":True,
                "observed_copy":result["approved_copy"]}})


def test_after_paid_response_stale_approval_holds_without_replay(repair):
    flow,service,parent,child,body=repair
    service.request(ACTOR,child,body)
    calls=[]
    def tamper(_):
        with flow.state.db() as db:db.execute("UPDATE live_jobs SET approval_sha=? WHERE job_id=?",("0"*64,child))
    transport=wire_transport(flow,child,calls,failure=tamper)
    assert run_image_correction_once(flow,transport=transport)=="IMAGE_CORRECTION_HOLD"
    assert len(calls)==1 and attempts(flow)[-1]["status"]=="SUCCEEDED_USAGE_UNPRICED"
    assert run_image_correction_once(flow,transport=transport)=="NO_IMAGE_CORRECTION_TASK"
    assert len(calls)==1


def test_recover_only_blocks_unknown_without_claiming_queued(repair):
    flow,service,parent,child,body=repair
    service.request(ACTOR,child,body)
    calls=[]
    assert run_image_correction_once(flow,transport=wire_transport(flow,child,calls),recover_only=True)=="NO_IMAGE_CORRECTION_TASK"
    assert service.snapshot(ACTOR,child)["corrections"][0]["state"]=="QUEUED" and calls==[]


@pytest.mark.parametrize('field,value', [('region',[0,0,1,1]),('target_text','다른 문구'),
    ('approved_copy',{'headline':'변조','subline':'변조','cta':'변조'})])
def test_payload_mutation_is_held_before_any_billed_call(repair,field,value):
    flow,service,_,child,body=repair
    row=service.request(ACTOR,child,body)
    with service.db() as db:
        payload=json.loads(db.execute('SELECT payload_json FROM image_corrections').fetchone()[0])
        payload[field]=value
        db.execute('UPDATE image_corrections SET payload_json=?',(json.dumps(payload),))
    calls=[];before=attempts(flow)
    assert run_image_correction_once(flow,transport=wire_transport(flow,child,calls))=='IMAGE_CORRECTION_HOLD'
    assert calls==[] and attempts(flow)==before


def test_failed_final_db_commit_preserves_candidate_receipt_and_can_retry(repair):
    import sqlite3
    flow,service,_,child,body=repair
    row=service.request(ACTOR,child,body);calls=[]
    run_image_correction_once(flow,transport=wire_transport(flow,child,calls))
    row=service.snapshot(ACTOR,child)['corrections'][0]
    receipt=service.artifact(ACTOR,child,row['correction_id'],'receipt',row['receipt_sha'])[0]
    decision={'expected_revision':row['revision'],'expected_preview_sha':row['preview_sha'],'approve':True,
        'visual_review':{'product_matches':True,'label_matches':True,'cta_policy_matches':True,
                        'no_extra_text':True,'observed_copy':row['approved_copy']}}
    with service.db() as db:
        db.executescript("CREATE TRIGGER reject_final BEFORE UPDATE ON image_corrections WHEN NEW.state='COMPLETED' BEGIN SELECT RAISE(ABORT,'injected DB failure'); END;")
    with pytest.raises(sqlite3.IntegrityError):service.decision(ACTOR,child,row['correction_id'],decision)
    assert service.artifact(ACTOR,child,row['correction_id'],'receipt',row['receipt_sha'])[0]==receipt
    with service.db() as db:db.execute('DROP TRIGGER reject_final')
    assert service.decision(ACTOR,child,row['correction_id'],decision)['state']=='COMPLETED'
    assert len(calls)==1


def test_correction_receipt_must_still_match_cost_ledger_before_review(repair):
    flow,service,_,child,body=repair
    row=service.request(ACTOR,child,body);calls=[]
    run_image_correction_once(flow,transport=wire_transport(flow,child,calls))
    row=service.snapshot(ACTOR,child)['corrections'][0]
    with flow.cost.connect() as db:
        db.execute("UPDATE attempts SET receipt='{}' WHERE id=?",(attempts(flow)[-1]['id'],))
    with pytest.raises(LiveGateError,match='RECEIPT_INTEGRITY'):
        service.artifact(ACTOR,child,row['correction_id'],'preview',row['preview_sha'])
    assert len(calls)==1


@pytest.mark.parametrize('interrupted',['image','composed'])
def test_cross_namespace_interrupted_task_blocks_all_new_paid_claims(repair,monkeypatch,interrupted):
    from demo_staging.live.composed_copy_edit import ComposedCopyEdits
    from demo_staging.live.result_revision_worker import run_result_revision_once
    flow,service,parent,child,body=repair
    monkeypatch.setenv('IT_TEM_COMPOSED_COPY_EDIT_ENABLED','YES')
    monkeypatch.setenv('IT_TEM_COMPOSED_COPY_EDIT_WORKER_PROTOCOL','COMPOSED_COPY_EDIT_V1')
    source=flow.state.get(ACTOR,parent)
    comp=ComposedCopyEdits(flow)
    comp.create(ACTOR,parent,{'expected_image_sha':source['image_sha'],'expected_copy_sha':source['copy_sha'],
        'expected_approval_sha':source['approval_sha'],'request_key':'a'*32,
        'ad_copy':{'headline':'매일의 샴푸 시간','subline':'차분하게 시작해요','cta':'제품 만나기'}})
    service.request(ACTOR,child,body)
    if interrupted=='image':
        with service.db() as db:db.execute("UPDATE image_corrections SET state='RUNNING'")
    else:
        with comp.db() as db:
            record=json.loads(db.execute('SELECT record_json FROM composed_copy_edits').fetchone()[0])
            record['state']='RUNNING';comp._save(db,record);db.commit()
    before=attempts(flow)
    assert 'BILLING_UNKNOWN' in run_result_revision_once(flow)
    assert attempts(flow)==before
    with service.db() as db:assert db.execute('SELECT state FROM image_corrections').fetchone()[0]==('BILLING_UNKNOWN' if interrupted=='image' else 'QUEUED')
    with comp.db() as db:assert db.execute('SELECT state FROM composed_copy_edits').fetchone()[0]==('QUEUED_REVIEW' if interrupted=='image' else 'BILLING_UNKNOWN')


@pytest.mark.parametrize('observed,target,old_range,new_range,old_fragment,new_fragment,initial',[
    ('자분하게 시작해요','차분하게 시작해요',[0,1],[0,1],'자','차',('ㅈ','ㅊ')),
    ('오늘 자분하게','오늘 차분하게',[3,4],[3,4],'자','차',('ㅈ','ㅊ')),
    ('차분게 시작해요','차분하게 시작해요',[2,2],[2,3],'','하',None),
    ('차분하하게 시작해요','차분하게 시작해요',[3,4],[3,3],'하','',None),
    ('가볍게','촉촉하게',[0,2],[0,3],'가볍','촉촉하',None),
])
def test_v3_change_span_is_derived_without_reading_or_inventing_image_text(
        observed,target,old_range,new_range,old_fragment,new_fragment,initial):
    from demo_staging.live.image_correction import _change_span
    span=_change_span(observed,target)
    assert span['observed_range']==old_range and span['target_range']==new_range
    assert span['observed_fragment']==old_fragment and span['target_fragment']==new_fragment
    if initial:
        assert span['initial_consonant_change']['observed_initial']==initial[0]
        assert span['initial_consonant_change']['target_initial']==initial[1]
        assert span['initial_consonant_change']['preserved_medial_index']==0
        assert span['initial_consonant_change']['preserved_final_index']==0
    else:assert span['initial_consonant_change'] is None


def test_stored_v2_payload_replays_exact_old_prompt_and_same_request_is_idempotent(repair):
    from demo_staging.live.image_correction import _prompt_v2, _prompt
    from demo_staging.live.contracts import digest
    flow,service,_,child,body=repair
    admitted=service.request(ACTOR,child,body)
    # Disposable saved v2 request, as it would have been admitted by that source.
    # Its old prompt and request SHA must not be silently upgraded on a replay.
    with service.db() as db:
        row=dict(db.execute('SELECT * FROM image_corrections').fetchone())
        payload=json.loads(row['payload_json'])
        for key in ('change_span','source_size'):payload.pop(key)
        payload['edit_prompt_version']='source-style-preserving-text-edit-v2'
        payload['edit_prompt']=_prompt_v2(payload)
        frozen_prompt=payload['edit_prompt'];frozen_sha=digest(payload)
        db.execute('UPDATE image_corrections SET payload_json=?,request_sha=?',
            (json.dumps(payload,ensure_ascii=False),frozen_sha))
    row_before=None
    with service.db() as db:row_before=dict(db.execute('SELECT * FROM image_corrections').fetchone())
    assert service.request(ACTOR,child,body)['correction_id']==admitted['correction_id']
    with service.db() as db:assert dict(db.execute('SELECT * FROM image_corrections').fetchone())==row_before
    assert _prompt(payload)==frozen_prompt
    calls=[]
    assert run_image_correction_once(flow,transport=wire_transport(flow,child,calls))=='IMAGE_CORRECTION_REVIEW_REQUIRED'
    assert len(calls)==1
    parts=BytesParser(policy=policy.default).parsebytes(
        b'Content-Type: '+calls[0].headers['content-type'].encode()+b'\r\n\r\n'+calls[0].read())
    sent_prompt=next(part.get_payload(decode=True).decode('utf-8') for part in parts.iter_parts()
                     if part.get_param('name',header='content-disposition')=='prompt')
    assert sent_prompt==frozen_prompt
    with service.db() as db:
        saved=dict(db.execute('SELECT * FROM image_corrections').fetchone())
        assert saved['request_sha']==frozen_sha and json.loads(saved['payload_json'])==payload


@pytest.mark.parametrize('mutate', ['span', 'initial_component', 'frozen_prompt'])
def test_v3_span_or_prompt_semantic_tampering_is_held_even_with_recomputed_hash(repair,mutate):
    from demo_staging.live.contracts import digest
    flow,service,_,child,body=repair
    service.request(ACTOR,child,body)
    with service.db() as db:
        payload=json.loads(db.execute('SELECT payload_json FROM image_corrections').fetchone()[0])
        if mutate=='span':payload['change_span']['target_range']=[1,2]
        elif mutate=='initial_component':payload['change_span']['initial_consonant_change']={'observed_initial':'ㅈ','target_initial':'ㄱ'}
        else:payload['edit_prompt']+='문장 전체를 크게 다시 그리세요.'
        db.execute('UPDATE image_corrections SET payload_json=?,request_sha=?',
            (json.dumps(payload,ensure_ascii=False),digest(payload)))
    before=attempts(flow);calls=[]
    assert run_image_correction_once(flow,transport=wire_transport(flow,child,calls))=='IMAGE_CORRECTION_HOLD'
    assert calls==[] and attempts(flow)==before


def test_v3_single_initial_region_keeps_vowel_and_remaining_field_pixels_exact(repair):
    from PIL import ImageChops
    flow,service,_,child,body=repair
    approved=json.loads(flow.state.get(ACTOR,child)['copy_json'])['ad_copy']['subline']
    # Keep the fixture's signed approved copy/F09 untouched. Change only the
    # observed first initial to construct a one-syllable mismatch for this test.
    offset=ord(approved[0])-0xAC00
    assert 0<=offset<11172
    other_initial=(offset//588+1)%19
    observed=chr(0xAC00+other_initial*588+offset%588)+approved[1:]
    box=[294,238,343,305]
    body={**body,'observed_text':observed,'region':[294/1152,238/1440,343/1152,305/1440]}
    admitted=service.request(ACTOR,child,body)
    assert admitted['edit_prompt_version']=='source-style-preserving-glyph-edit-v3'
    assert admitted['change_span']['observed_range']==[0,1]
    assert admitted['change_span']['target_range']==[0,1]
    assert admitted['change_span']['initial_consonant_change'] is not None
    assert admitted['source_size']==[1152,1440] and admitted['style_note']=='HUMAN_STYLE_REVIEW_REQUIRED'
    with service.db() as db:
        payload=json.loads(db.execute('SELECT payload_json FROM image_corrections').fetchone()[0])
    assert '전체 문장을 마스크 안에 다시 쓰거나' in payload['edit_prompt']
    assert '초성만' in payload['edit_prompt']
    source=flow.image_path(child).read_bytes();calls=[]
    assert run_image_correction_once(flow,transport=wire_transport(flow,child,calls))=='IMAGE_CORRECTION_REVIEW_REQUIRED'
    result=service.snapshot(ACTOR,child)['corrections'][0]
    preview,_=service.artifact(ACTOR,child,result['correction_id'],'preview',result['preview_sha'])
    receipt=json.loads(service.artifact(ACTOR,child,result['correction_id'],'receipt',result['receipt_sha'])[0])
    assert receipt['region_pixels']==box and receipt['outside_region_pixel_count']==1655597
    assert receipt['change_span']==admitted['change_span'] and receipt['server_text_overlay'] is False
    assert receipt['style_note']=='HUMAN_STYLE_REVIEW_REQUIRED'
    with Image.open(BytesIO(source)) as original,Image.open(BytesIO(preview)) as corrected:
        diff=ImageChops.difference(original.convert('RGB'),corrected.convert('RGB'))
        assert diff.getbbox()==tuple(box)
        # The original vowel and the rest of the line are to the right of the
        # selected initial; the whole right side must remain pixel-identical.
        assert original.crop((343,0,1152,1440)).tobytes()==corrected.crop((343,0,1152,1440)).tobytes()
    assert len(calls)==1 and flow.state.get(ACTOR,child)['state']=='IMAGE_REJECTED'


def test_stored_v1_unversioned_payload_is_readable_and_not_silently_upgraded(repair):
    from demo_staging.live.image_correction import _prompt_v1, _prompt
    from demo_staging.live.contracts import digest
    flow,service,_,child,body=repair
    service.request(ACTOR,child,body)
    with service.db() as db:
        payload=json.loads(db.execute('SELECT payload_json FROM image_corrections').fetchone()[0])
        for key in ('change_span','source_size','source_ink_rgb','source_background_rgb','edit_prompt_version','edit_prompt'):
            payload.pop(key)
        raw=json.dumps(payload,ensure_ascii=False)
        db.execute('UPDATE image_corrections SET payload_json=?,request_sha=?',(raw,digest(payload)))
    old=service.snapshot(ACTOR,child)['corrections'][0]
    assert old['change_span'] is None and old['edit_prompt_version'] is None
    assert _prompt(payload)==_prompt_v1(payload)
    assert service.request(ACTOR,child,body)==old
    with service.db() as db:assert db.execute('SELECT payload_json FROM image_corrections').fetchone()[0]==raw
    assert len(attempts(flow))==7
