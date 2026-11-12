"""R7 regressions. No real Provider calls; immutable source and queue behavior only."""
import json
import pytest

from demo_staging.live.worker import quarantined_uncertain_jobs, _run_locked
from demo_staging.live.queue import LiveQueue
from demo_staging.live.contracts import LiveGateError,digest
from demo_staging.live.checkpoints import LiveCheckpoints
from demo_staging.live.pipeline import LivePipeline
from src.text_generation.schemas import AdCopyOutput,CopyRevisionOutput
from tests.demo_live.test_a2_worker_authority_billing import prepare


def test_live_revised_copy_attested_not_rejected(tmp_path):
    """A trusted owner copy revision may become the current approved copy."""
    from tests.demo_live.test_live_contracts import safe_copy
    a,r,original,_=safe_copy()
    from src.text_generation.schemas import ProductAnalysisResult,ResearchResult
    a=ProductAnalysisResult.model_validate(a).model_dump(mode='json')
    r=ResearchResult.model_validate(r).model_dump(mode='json')
    original=AdCopyOutput.model_validate(original).model_dump(mode='json')
    copy=dict(original)
    copy=json.loads(json.dumps(original))
    copy['ad_copy']['headline']='촉촉한 하루 시작'
    # The validation helper only relies on the immutable checkpoint boundary.
    p=object.__new__(LivePipeline)
    p.checkpoints=LiveCheckpoints(tmp_path/'checkpoint.sqlite')
    actor,jid='alice','1'*32
    ctx=digest({'input_sha':'1'*64,'assets':['a'*64,'b'*64],'model':'vision'})
    research_ctx=digest({'input_sha':'1'*64,'analysis_sha':digest(a),'model':'text'})
    original_ctx=digest({'input_sha':'1'*64,'analysis_sha':digest(a),
                         'research_sha':digest(r),'model':'text'})
    from src.text_generation.schemas import ProductAnalysisResult,ResearchResult
    p.checkpoints.commit(actor,jid,'vision',ctx,'LIVE',
                         ProductAnalysisResult.model_validate(a),ProductAnalysisResult)
    p.checkpoints.commit(actor,jid,'research',research_ctx,'LIVE',
                         ResearchResult.model_validate(r),ResearchResult)
    p.checkpoints.commit(actor,jid,'copy',original_ctx,'LIVE',
                         AdCopyOutput.model_validate(original),AdCopyOutput)
    from src.text_generation.schemas import RevisableField
    revised=CopyRevisionOutput(revised=AdCopyOutput.model_validate(copy),
        changed_fields=['headline'],note=None)
    revision_ctx='b'*64
    p.checkpoints.commit(actor,jid,'copy_revision',revision_ctx,'LIVE',
                         revised,CopyRevisionOutput)
    data={'mode':'LIVE','input_sha':'1'*64,
        'input_json':json.dumps({'ordered_asset_hashes':[{'sha256':'a'*64},
                       {'sha256':'b'*64}]}),
        'analysis_json':json.dumps(a),'research_json':json.dumps(r),
        'copy_json':json.dumps(copy)}
    assert p._assert_live_prompt_sources(actor,jid,data,text_model='text',vision_model='vision') is None
    assert p._assert_live_prompt_sources(actor,jid,{**data,'copy_json':json.dumps(original)},
        text_model='text',vision_model='vision') is None
    tampered=json.loads(json.dumps(copy));tampered['ad_copy']['headline']='위조'
    with pytest.raises(LiveGateError,match='PROMPT_LIVE_SOURCE_PROVENANCE_INVALID'):
        p._assert_live_prompt_sources(actor,jid,{**data,'copy_json':json.dumps(tampered)},
             text_model='text',vision_model='vision')
    with pytest.raises(LiveGateError,match='PROMPT_LIVE_SOURCE_PROVENANCE_INVALID'):
        p._assert_live_prompt_sources(actor,jid,{**data,'mode':'OFFLINE_FIXTURE'},
             text_model='text',vision_model='vision')
    with pytest.raises(LiveGateError,match='PROMPT_LIVE_SOURCE_PROVENANCE_INVALID'):
        p._assert_live_prompt_sources('bob',jid,data,text_model='text',vision_model='vision')


def test_preflight_failure_not_billing_unknown(tmp_path,monkeypatch):
    import demo_staging.live.worker as worker
    app,jid,flow,queue=prepare(tmp_path,monkeypatch)
    item,_=queue.enqueue(actor='alice',job_id=jid,stage='image_prompt',
                         context_sha='a'*64)
    monkeypatch.setattr(worker,'authorize_worker_item',lambda *args: None)
    def fails_pre_provider(*args,**kwargs):
        raise LiveGateError('PROMPT_LIVE_SOURCE_PROVENANCE_INVALID')
    monkeypatch.setattr(flow,'prompt',fails_pre_provider)
    assert _run_locked(tmp_path/'runtime',flow)=='LIVE_STAGE_FAILED_PRE_DISPATCH'
    assert queue.read(item['id'])['state']=='FAILED_PRE_DISPATCH'
    with flow.cost.connect() as db:
        assert db.execute("SELECT count(*) FROM attempts").fetchone()[0]==0
    assert _run_locked(tmp_path/'runtime',flow)=='NO_LIVE_TASK'


def test_live_preflight_unknown_from_old_r6_isolated_without_settlement(
    tmp_path,monkeypatch
):
    app,jid,flow,queue=prepare(tmp_path,monkeypatch)
    monkeypatch.setenv('IT_TEM_R6_ISOLATE_UNCERTAIN_JOBS','YES')
    a,_=queue.enqueue(actor='alice',job_id=jid,stage='image_prompt',context_sha='b'*64)
    queue.claim('LIVE');queue.interrupt(a['id'],'PROMPT_LIVE_SOURCE_PROVENANCE_INVALID')
    assert quarantined_uncertain_jobs(queue,flow)=={jid}
    assert _run_locked(tmp_path/'runtime',flow)=='NO_LIVE_TASK'
    assert queue.read(a['id'])['state']=='BILLING_UNKNOWN'


def test_untrusted_unknown_still_blocks_all(tmp_path,monkeypatch):
    app,jid,flow,queue=prepare(tmp_path,monkeypatch)
    monkeypatch.setenv('IT_TEM_R6_ISOLATE_UNCERTAIN_JOBS','YES')
    a,_=queue.enqueue(actor='alice',job_id=jid,stage='image_prompt',context_sha='b'*64)
    queue.claim('LIVE');queue.interrupt(a['id'],'SOME_UNVERIFIED_PROVIDER_ERROR')
    assert quarantined_uncertain_jobs(queue,flow) is None
    assert _run_locked(tmp_path/'runtime',flow)=='LIVE_WORKER_BILLING_HOLD'


def test_preflight_cannot_be_misused_for_other_failures(tmp_path):
    q=LiveQueue(tmp_path/'queue.sqlite')
    a,_=q.enqueue(actor='alice',job_id='a'*32,stage='analysis',context_sha='a'*64)
    q.claim('LIVE')
    with pytest.raises(LiveGateError,match='PRE_DISPATCH_FAILURE_CLASSIFICATION_DENIED'):
        q.fail_pre_dispatch(a['id'],'PROMPT_LIVE_SOURCE_PROVENANCE_INVALID')
    assert q.read(a['id'])['state']=='RUNNING'



def test_r7_worker_loop_continues_safe_recheck_after_hold(tmp_path,monkeypatch):
    """A new ambiguous Job does not permanently kill other users' worker."""
    import demo_staging.live.worker as worker
    import time
    monkeypatch.setenv("IT_TEM_R6_ISOLATE_UNCERTAIN_JOBS","YES")
    statuses=iter([
        "LIVE_STAGE_HELD_FOR_RECONCILIATION",
        "LIVE_WORKER_BILLING_HOLD",
        "LIVE_STAGE_COMMITTED",
    ])
    calls=[]
    def fake_once(root):
        calls.append(root)
        try:return next(statuses)
        except StopIteration:raise RuntimeError("STOP_AFTER_RECHECK") from None
    monkeypatch.setattr(worker,"run_once",fake_once)
    monkeypatch.setattr(time,"sleep",lambda _:None)
    with pytest.raises(RuntimeError,match="STOP_AFTER_RECHECK"):
        worker.serve_loop(tmp_path/"runtime",interval=0)
    assert len(calls)==4


def test_r7_worker_default_policy_still_stops_on_hold(tmp_path,monkeypatch):
    import demo_staging.live.worker as worker
    monkeypatch.delenv("IT_TEM_R6_ISOLATE_UNCERTAIN_JOBS",raising=False)
    calls=[]
    monkeypatch.setattr(worker,"run_once",lambda _: calls.append(1) or "LIVE_STAGE_HELD_FOR_RECONCILIATION")
    assert worker.serve_loop(tmp_path/"runtime")=="LIVE_STAGE_HELD_FOR_RECONCILIATION"
    assert len(calls)==1
