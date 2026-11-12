"""Explicit human responsibility over warnings; no real providers or suppressed F09 findings."""
import json
import pytest
from fastapi.testclient import TestClient
from demo_staging.live.contracts import LiveGateError,digest
from demo_staging.live.copy_review import CopyReviewIssue,CopyReviewResult
from demo_staging.live import worker
from tests.demo_live.test_live_dual_mock_transport import (dual_runtime,ACTOR,OTHER_ACTOR,
    upload,reviewed,signed_request,install_images,run_stage,attempts,signed_env)


def warned(dual_runtime,monkeypatch):
    root,host,key,app,flow,text=dual_runtime
    original=text.review_copy
    def finding(copy,product,report):
        original(copy,product,report)
        return CopyReviewResult(issues=[CopyReviewIssue(field='headline',text=copy.ad_copy.headline,
            category='효능 과장',risk_level='위반 의심',reason='Test advisory finding',suggestion='문구 검토')])
    monkeypatch.setattr(text,'review_copy',finding)
    return root,host,key,app,flow,text


def test_signed_warning_consent_reaches_both_mock_images_without_changing_report(dual_runtime,monkeypatch):
    from demo_staging.live.dual_worker import live_dual_lease
    root,host,key,app,flow,text=warned(dual_runtime,monkeypatch);calls=[]
    install_images(monkeypatch,flow,calls)
    with TestClient(app,base_url=f'https://{host}') as client:
        job=upload(client,host,key);s=reviewed(flow,job)
        original=s['compliance_json'];assert not json.loads(original)['passed']
        path=f'/demo/api/live/jobs/{job}/dual/start'
        body={'expected_generation':s['generation'],'expected_review_sha':s['review_sha'],
              'acknowledge_two_images':True,'acknowledge_evidence':True}
        def request(body,actor=ACTOR):return signed_request(client,host,key,'POST',path,actor=actor,json=body)
        with worker.exclusive_live_worker(root),live_dual_lease(root):
            assert request(body).status_code in (409,422)
            assert request({**body,'acknowledge_responsibility':'true'}).status_code==422
            assert request({**body,'acknowledge_responsibility':True},OTHER_ACTOR).status_code in (403,404)
            response=request({**body,'acknowledge_responsibility':True});assert response.status_code==202,response.text
            assert request({**body,'acknowledge_responsibility':True}).status_code==202
        group=flow.state.live_dual_group(ACTOR,job);child=group['child_job_id']
        assert flow.state.get(ACTOR,job)['compliance_json']==original
        assert not json.loads(flow.state.get(ACTOR,child)['compliance_json'])['passed']
        assert flow.state.responsibility_authorized(ACTOR,job)
        assert flow.state.responsibility_authorized(ACTOR,child)
        assert len(attempts(flow))==4
        for _ in range(3):assert run_stage(root)=='LIVE_STAGE_COMMITTED'
        assert len(calls)==2 and len(attempts(flow))==7
        # Removing either child's own consent invalidates the derived approval.
        with flow.state.db() as c:
            c.execute("DELETE FROM live_events WHERE job_id=? AND event='user_copy_responsibility_acknowledged'",(child,));c.commit()
        with pytest.raises(LiveGateError):
            flow.state._approved(flow.state.get(ACTOR,child))


def test_failed_report_never_allows_missing_review_or_stale_consent(dual_runtime,monkeypatch):
    root,host,key,app,flow,text=warned(dual_runtime,monkeypatch)
    with TestClient(app,base_url=f'https://{host}') as client:
        job=upload(client,host,key);s=reviewed(flow,job)
    from demo_staging.live.dual_worker import live_dual_profile
    profile=live_dual_profile('4:5')
    with pytest.raises(LiveGateError,match='STALE_REVIEW'):
        flow.state.start_live_dual(ACTOR,job,expected_generation=s['generation']+1,
            expected_review_sha=s['review_sha'],execution_profile=profile,
            acknowledge_two_images=True,acknowledge_responsibility=True)
    with flow.state.db() as c:
        report=json.loads(s['compliance_json']);del report['llm_review']
        c.execute('UPDATE live_jobs SET compliance_json=? WHERE job_id=?',(json.dumps(report),job));c.commit()
    with pytest.raises(LiveGateError):
        flow.state.start_live_dual(ACTOR,job,expected_generation=s['generation'],
            expected_review_sha=s['review_sha'],execution_profile=profile,
            acknowledge_two_images=True,acknowledge_responsibility=True)
    assert not flow.state.responsibility_authorized(ACTOR,job)
