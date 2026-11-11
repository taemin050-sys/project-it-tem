"""Revocation retires the local grant, including its finalized download authority."""
import pytest

from demo_staging.live.contracts import LiveGateError
from demo_staging.live.derived_worker import run_once
from tests.demo_live.test_derived_worker import service, approved_fixture, enqueue, completed_review


def body(value,jid,row):
    current=value.snapshot('alice','admin',jid)
    public=next(r for r in current['renders'] if r['derived_id']==row['derived_id'])
    return {'expected_revision':public['revision'],'expected_context_sha':current['context_sha'],
            'expected_admission_sha':public['admission_sha']}


def test_revoke_completed_grant_invalidates_approval_selection_and_execution(service):
    value,jid=service
    row=completed_review(value,jid)
    final=value.finalize('alice','admin',jid,row['derived_id'],{
        'expected_revision':row['revision'],'expected_approval_sha':row['approval_sha'],'expected_preview_sha':row['preview_sha']})
    value.select('alice','admin',jid,{'derived_id':row['derived_id'],
        'expected_final_sha':final['final_sha'],'expected_approval_sha':final['approval_sha']})
    request=body(value,jid,row)
    revoked=value.revoke('alice','admin',jid,row['derived_id'],request)
    assert revoked['state']=='STALE'
    assert value.snapshot('alice','admin',jid)['selected_derived_id'] is None
    with pytest.raises(LiveGateError):value.store.require_approval('alice',jid,row['derived_id'])
    with pytest.raises(LiveGateError):value.revoke('alice','admin',jid,row['derived_id'],request)
    assert run_once(value,worker_id='no-automatic-replay') is None


def test_stale_revision_or_other_actor_cannot_revoke(service):
    value,jid=service
    row,_=enqueue(value,jid);request=body(value,jid,row)
    with pytest.raises(LiveGateError,match='DERIVED_REVOCATION_STALE'):
        value.revoke('alice','admin',jid,row['derived_id'],{**request,'expected_revision':request['expected_revision']+1})
    with pytest.raises(LiveGateError,match='DERIVED_JOB_NOT_FOUND'):
        value.revoke('mallory','admin',jid,row['derived_id'],request)
    assert value.store.get_render('alice',jid,row['derived_id'])['state']=='QUEUED'
