"""BP11 failed compliance must allow revision/restore but never approval.

Offline-only; no model, paid API, or external socket. Reuse Text Owner #25
deterministic FakeRevision and real Serving SQLite state/review/approval CAS.
"""
import json
import sqlite3
from copy import deepcopy

import pytest

from demo_staging.live.contracts import LiveGateError
from tests.demo_live.test_owner_text25_revision_integration import create_ready


def test_failed_compliance_revision_recheck_restore_and_no_approval_revival(tmp_path):
    flow, jid, original, fake = create_ready(tmp_path)
    blocked = deepcopy(json.loads(original["copy_json"]))
    blocked["ad_copy"]["headline"] = "여드름을 100% 치료합니다"
    invalid = flow.state.edit_copy("alice", jid, blocked)
    invalid_report = json.loads(invalid["compliance_json"])
    assert invalid["state"] == "COPY_REVIEW_REQUIRED"
    assert invalid_report["passed"] is False
    assert invalid["approval_sha"] is None
    with pytest.raises(LiveGateError, match="REAL_COMPLIANCE_BLOCKED"):
        flow.state.approve_copy(
            "alice", jid, invalid["generation"], invalid["review_sha"],
            acknowledge_evidence=True
        )
    # Failed compliance is NOT a precondition of the remediation action.
    context = flow.revision_context("alice", jid, "치료 표현 삭제",
        invalid["generation"], invalid["review_sha"])
    assert context["copy_sha"] == invalid["copy_sha"]
    fixed = flow.revise_copy("alice", jid, "치료 표현 삭제",
        invalid["generation"], invalid["review_sha"], provider=fake, offline=True)
    assert fixed["generation"] == invalid["generation"] + 1
    assert fixed["review_sha"] != invalid["review_sha"]
    assert fixed["copy_sha"] != invalid["copy_sha"]
    assert json.loads(fixed["compliance_json"])["passed"] is True
    assert fixed["approval_sha"] is None
    assert flow.state.previous_copy_available("alice", jid)
    with pytest.raises(LiveGateError, match="STALE_REVIEW_OR_REVISION"):
        flow.state.approve_copy("alice", jid, invalid["generation"], invalid["review_sha"])
    with pytest.raises(LiveGateError, match="STALE_REVIEW_OR_REVISION"):
        flow.state.restore_previous_copy("alice", jid, invalid["generation"], invalid["review_sha"])
    # Restore a prohibited previous copy: it remains prohibited and is never approved.
    restored = flow.state.restore_previous_copy(
        "alice", jid, fixed["generation"], fixed["review_sha"])
    assert restored["copy_sha"] == invalid["copy_sha"]
    assert restored["review_sha"] not in (fixed["review_sha"], invalid["review_sha"])
    assert restored["generation"] == fixed["generation"] + 1
    assert json.loads(restored["compliance_json"])["passed"] is False
    assert restored["approval_sha"] is None
    with pytest.raises(LiveGateError, match="REAL_COMPLIANCE_BLOCKED"):
        flow.state.approve_copy("alice", jid, restored["generation"], restored["review_sha"],
            acknowledge_evidence=True)
    # A safe restored revision can still be approved only after fresh review+ack.
    safe_again = flow.state.restore_previous_copy(
        "alice", jid, restored["generation"], restored["review_sha"])
    assert safe_again["copy_sha"] == fixed["copy_sha"]
    assert safe_again["review_sha"] not in (fixed["review_sha"], restored["review_sha"])
    assert safe_again["approval_sha"] is None
    assert json.loads(safe_again["compliance_json"])["passed"] is True
    approved = flow.state.approve_copy("alice", jid,
        safe_again["generation"], safe_again["review_sha"], acknowledge_evidence=True)
    assert approved["state"] == "COPY_APPROVED"
    assert approved["approval_sha"]
    assert approved["approved_generation"] == safe_again["generation"]
    with sqlite3.connect(tmp_path / "live" / "cost.sqlite") as c:
        assert c.execute("select count(*) from attempts").fetchone()[0] == 0
    # The offline-only LivePipeline test has no dispatch queue at all.
    assert not (tmp_path / "live" / "queue.sqlite").exists()
