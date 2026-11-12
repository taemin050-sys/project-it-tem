"""Actual B Copy approval reuse plus explicit business-role/delegation policy."""
from hashlib import sha256
import json

import pytest

from demo_staging.live.contracts import LiveGateError
from demo_staging.live.contracts import digest
from demo_staging.live.derived_approval import (
    DerivedAuthority, current_derived_context, require_same_context,
)
from src.image_generation.backend_adapter import BackendGeneratedImage
from tests.demo_live.test_live_contracts import sample_input
from tests.demo_live.test_pipeline import FakeOwner, prepare_service, png


@pytest.fixture(autouse=True)
def offline_environment(monkeypatch):
    for variable in ("IT_TEM_BP18_F11_ENABLED", "IT_TEM_BP18_F09_REQUIRED"):
        monkeypatch.delenv(variable, raising=False)


def policy_file(tmp_path, *, delegated=False, business_roles=None):
    value = {"schema": "bp18-derived-authority-v1", "revision": 1,
             "business_roles": business_roles if business_roles is not None else {"alice": "owner", "pm": "pm"},
             "delegations": [{"actor": "pm", "owner_actor": "alice", "job_id": "a"*32,
                              "scopes": ["read", "admit", "render", "review", "finalize", "select"]}]
                             if delegated else []}
    filename = tmp_path / "derived-policy.json"
    filename.write_text(json.dumps(value))
    filename.chmod(0o600)
    return filename


def candidate(flow, job_id, owner):
    flow.prompt("alice", job_id, owner, offline=True)
    row = flow.state.get("alice", job_id)
    raw = png((224, 233, 239), size=(1152, 1440))
    generated = BackendGeneratedImage(image_bytes=raw, mime_type="image/png", width=1152, height=1440,
        sha256=sha256(raw).hexdigest(), job_id=job_id, copy_revision=row["generation"],
        copy_hash=row["copy_sha"], mock=True,
        receipt={"mode": "OFFLINE_MOCK_TRANSPORT", "provider_calls": 0})
    flow.accept_image_result("alice", job_id, generated, offline=True)


@pytest.fixture
def approved_fixture(tmp_path, monkeypatch):
    # These are explicit offline state fixtures. No real PM or LLM signoff is asserted.
    for variable in ("IT_TEM_BP18_REVIEW_POLICY_REQUIRED", "IT_TEM_BP18_F09_REQUIRED",
                     "IT_TEM_REVIEW_POLICY_VERSION", "IT_TEM_REVIEW_POLICY_SHA"):
        monkeypatch.delenv(variable, raising=False)
    flow, job_id = prepare_service(tmp_path)
    flow.prepare("alice", job_id, sample_input())
    owner = FakeOwner()
    text = flow.text("alice", job_id, owner, offline=True)
    flow.state.approve_copy("alice", job_id, text["generation"], text["review_sha"])
    candidate(flow, job_id, owner)
    return flow, job_id, owner


def context(flow, job_id, actor="alice"):
    with flow.state.db() as connection:
        connection.execute("BEGIN IMMEDIATE")
        return current_derived_context(flow.state, connection, actor, job_id)


def test_business_owner_requires_actual_allowed_auth_role(tmp_path):
    authority = DerivedAuthority(policy_file(tmp_path))
    allowed = authority.authorize("alice", "admin", "alice", "a"*32, "admit")
    assert allowed["business_role"] == "owner"
    assert allowed["reviewer_actor"] == "alice"
    for role in ("owner", "pm", "guest", None):
        with pytest.raises(LiveGateError, match="DERIVED_REVIEWER_FORBIDDEN"):
            authority.authorize("alice", role, "alice", "a"*32, "admit")


def test_admin_alone_does_not_imply_owner_or_pm(tmp_path):
    authority = DerivedAuthority(policy_file(tmp_path, business_roles={}))
    assert authority.authorize("alice", "admin", "alice", "a"*32, "read")["business_role"] is None
    for scope in ("admit", "review", "finalize", "select"):
        with pytest.raises(LiveGateError, match="DERIVED_BUSINESS_ROLE_REQUIRED"):
            authority.authorize("alice", "admin", "alice", "a"*32, scope)


def test_other_business_pm_requires_explicit_job_and_scope_delegation(tmp_path):
    filename = policy_file(tmp_path)
    authority = DerivedAuthority(filename)
    with pytest.raises(LiveGateError, match="DERIVED_JOB_NOT_FOUND"):
        authority.authorize("pm", "admin", "alice", "a"*32, "admit")
    value = json.loads(filename.read_text())
    value["delegations"] = [{"actor": "pm", "owner_actor": "alice", "job_id": "a"*32,
                             "scopes": ["read"]}]
    filename.write_text(json.dumps(value))
    assert authority.authorize("pm", "evaluator", "alice", "a"*32, "read")["business_role"] == "pm"
    with pytest.raises(LiveGateError, match="DERIVED_JOB_NOT_FOUND"):
        authority.authorize("pm", "evaluator", "alice", "a"*32, "admit")
    with pytest.raises(LiveGateError, match="DERIVED_JOB_NOT_FOUND"):
        authority.authorize("pm", "evaluator", "alice", "b"*32, "read")


def test_policy_revision_and_delegation_revoke_are_effective_each_request(tmp_path):
    filename = policy_file(tmp_path, delegated=True)
    authority = DerivedAuthority(filename)
    before = authority.authorize("pm", "admin", "alice", "a"*32, "review")
    value = json.loads(filename.read_text())
    value["revision"] += 1
    filename.write_text(json.dumps(value))
    after = authority.authorize("pm", "admin", "alice", "a"*32, "review")
    assert before["authority_policy_sha"] != after["authority_policy_sha"]
    assert after["authority_revision"] == 2
    value["delegations"] = []
    value["revision"] += 1
    filename.write_text(json.dumps(value))
    with pytest.raises(LiveGateError, match="DERIVED_JOB_NOT_FOUND"):
        authority.authorize("pm", "admin", "alice", "a"*32, "review")


def test_missing_world_readable_or_symlink_policy_fails_closed(tmp_path):
    filename = tmp_path / "policy.json"
    authority = DerivedAuthority(filename)
    with pytest.raises(LiveGateError, match="DERIVED_AUTHORITY_POLICY_UNAVAILABLE"):
        authority.policy()
    filename = policy_file(tmp_path)
    filename.chmod(0o644)
    with pytest.raises(LiveGateError, match="DERIVED_AUTHORITY_POLICY_UNAVAILABLE"):
        DerivedAuthority(filename).policy()
    filename.chmod(0o600)
    alias = tmp_path / "alias.json"
    alias.symlink_to(filename)
    with pytest.raises(LiveGateError, match="DERIVED_AUTHORITY_POLICY_UNAVAILABLE"):
        DerivedAuthority(alias).policy()


@pytest.mark.parametrize("change", [
    lambda value: value.update(revision=True),
    lambda value: value.update(untrusted="extra"),
    lambda value: value["business_roles"].update(alice="admin"),
    lambda value: value["delegations"].append({"actor": "pm", "owner_actor": "alice",
                                             "job_id": "a"*32, "scopes": ["read", "read"]}),
])
def test_malformed_authority_policy_is_rejected(tmp_path, change):
    filename = policy_file(tmp_path)
    value = json.loads(filename.read_text())
    change(value)
    filename.write_text(json.dumps(value))
    with pytest.raises(LiveGateError, match="DERIVED_AUTHORITY_POLICY_UNAVAILABLE"):
        DerivedAuthority(filename).policy()


def test_duplicate_authority_json_keys_are_rejected(tmp_path):
    filename = policy_file(tmp_path)
    filename.write_text('{"schema":"bp18-derived-authority-v1","revision":1,"revision":2}')
    with pytest.raises(LiveGateError, match="DERIVED_AUTHORITY_POLICY_UNAVAILABLE"):
        DerivedAuthority(filename).policy()


def test_current_context_uses_real_b_approval_and_keeps_fixture_label(approved_fixture):
    flow, job_id, _ = approved_fixture
    job, value, context_sha = context(flow, job_id)
    assert value["copy_approval_sha"] == job["approval_sha"]
    assert value["f09_review_sha"] == job["review_sha"]
    assert value["f09"]["scope"] == "OFFLINE_FIXTURE"
    assert value["owner_candidate_receipt_sha"] is None
    assert value["raw_candidate_sha"] == job["image_sha"]
    assert context_sha and len(context_sha) == 64
    with pytest.raises(LiveGateError, match="LIVE_JOB_NOT_FOUND"):
        context(flow, job_id, "other")


def test_current_context_rejects_tampered_review_or_copy_approval(approved_fixture):
    flow, job_id, _ = approved_fixture
    before, _, _ = context(flow, job_id)
    for field in ("review_sha", "approval_sha"):
        with flow.state.db() as connection:
            connection.execute(f"UPDATE live_jobs SET {field}=? WHERE job_id=?", ("9"*64, job_id))
        with pytest.raises(LiveGateError, match="APPROVAL_CONTEXT_NOT_CURRENT"):
            context(flow, job_id)
        with flow.state.db() as connection:
            connection.execute(f"UPDATE live_jobs SET {field}=? WHERE job_id=?", (before[field], job_id))


def test_copy_is_immutable_after_raw_candidate_context(approved_fixture):
    flow, job_id, _ = approved_fixture
    original, _, before_sha = context(flow, job_id)
    replacement = json.loads(original["copy_json"])
    replacement["caption"] = "가볍게 시작하는 새로운 하루"
    with pytest.raises(LiveGateError, match="COPY_EDIT_STATE_CONFLICT"):
        flow.state.edit_copy("alice", job_id, replacement)
    assert context(flow, job_id)[2] == before_sha


def test_copy_edit_and_manual_restore_has_new_generation_and_approval_before_image(tmp_path):
    flow, job_id = prepare_service(tmp_path)
    flow.prepare("alice", job_id, sample_input())
    owner = FakeOwner()
    text = flow.text("alice", job_id, owner, offline=True)
    original = flow.state.approve_copy("alice", job_id, text["generation"], text["review_sha"])
    replacement = json.loads(original["copy_json"])
    replacement["caption"] = "가볍게 시작하는 새로운 하루"
    edited = flow.state.edit_copy("alice", job_id, replacement)
    with pytest.raises(LiveGateError, match="APPROVAL_CONTEXT_NOT_CURRENT"):
        context(flow, job_id)
    restored = flow.state.edit_copy("alice", job_id, json.loads(original["copy_json"]))
    assert restored["copy_sha"] == original["copy_sha"]
    assert restored["generation"] > original["generation"]
    flow.state.approve_copy("alice", job_id, restored["generation"], restored["review_sha"])
    candidate(flow, job_id, owner)
    _, after, after_sha = context(flow, job_id)
    assert after["copy_sha"] == original["copy_sha"]
    assert after["copy_approval_sha"] != original["approval_sha"]
    assert after["generation"] != original["generation"]
    stale = {**after, "generation": original["generation"],
             "copy_approval_sha": original["approval_sha"], "f09_review_sha": original["review_sha"]}
    with pytest.raises(LiveGateError, match="DERIVED_CONTEXT_STALE"):
        require_same_context(after_sha, digest(stale))
