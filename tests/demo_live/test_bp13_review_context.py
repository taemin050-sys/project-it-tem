"""BP13 review SHA -> issue context preflight, partial unsafe text fail-closed."""
import json
from copy import deepcopy

import pytest

from demo_staging.live.contracts import LiveGateError,digest
from tests.demo_live.test_owner_text25_revision_integration import create_ready


def test_compliance_context_binds_current_review_and_original_issue_text(tmp_path):
    flow,jid,st,_=create_ready(tmp_path)
    blocked=deepcopy(json.loads(st["copy_json"]))
    blocked["ad_copy"]["headline"]="여드름을 치료하는 크림"
    edited=flow.state.edit_copy("alice",jid,blocked)
    issues=json.loads(edited["compliance_json"])["issues"]
    assert issues and any(x["risk_level"]=="위반 의심" for x in issues)
    context=flow.revision_context("alice",jid,"검수 지적 표현 삭제",
                                edited["generation"],edited["review_sha"])
    assert context["copy_sha"]==edited["copy_sha"]
    assert context["review_sha"]==edited["review_sha"]
    assert context["compliance_report_sha"]==digest(json.loads(edited["compliance_json"]))
    assert {x["text"] for x in context["compliance_issues"]}=={x["text"] for x in issues}
    assert all(set(x)=={"field","text","risk_level","reason","suggestion","basis"}
               for x in context["compliance_issues"])
    assert context["basis_verification"].startswith("UNVERIFIED")
    with pytest.raises(LiveGateError,match="REAL_COMPLIANCE_BLOCKED"):
        flow.state.approve_copy("alice",jid,edited["generation"],edited["review_sha"])
    # Removing one dangerous expression while retaining another cannot pass.
    partial=deepcopy(blocked)
    partial["ad_copy"]["headline"]="여드름 치료 크림"
    updated=flow.state.edit_copy("alice",jid,partial)
    assert json.loads(updated["compliance_json"])["passed"] is False
    with pytest.raises(LiveGateError,match="REAL_COMPLIANCE_BLOCKED"):
        flow.state.approve_copy("alice",jid,updated["generation"],updated["review_sha"])


def test_stale_review_body_is_rejected_before_model_transport(tmp_path):
    flow,jid,st,_=create_ready(tmp_path)
    with flow.state.db() as c:
        data=json.loads(st["compliance_json"])
        data["issues"].append({"field":"headline","text":"fake","risk_level":"위반 의심",
                               "reason":"tampered","suggestion":None,"basis":None})
        c.execute("update live_jobs set compliance_json=? where job_id=?",
                 (json.dumps(data,ensure_ascii=False),jid))
    with pytest.raises(LiveGateError,match="REVISION_REVIEW_CONTEXT_INTEGRITY_FAILED"):
        flow.revision_context("alice",jid,"헤드 수정",st["generation"],st["review_sha"])
    with flow.cost.connect() as c:
        assert c.execute("select count(*) from attempts").fetchone()[0]==0
