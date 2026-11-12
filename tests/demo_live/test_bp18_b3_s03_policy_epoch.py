"""BP18 B-only audit follow-up: persistent policy epoch and source-cache fail-closed.

No paid model calls. Versions change via fresh LiveStore construction to
represent process replacement, never illicit hot reload of cached Owner rules.
"""
import json
import sqlite3
from pathlib import Path

import pytest

from demo_staging.live.contracts import LiveGateError
from demo_staging.live.store import LiveStore
from tests.demo_live.test_bp18_r01_f11_policy_binding import start,fail_review
from tests.demo_live.test_pipeline import FakeOwner


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setenv("IT_TEM_BP18_F11_ENABLED","YES")
    monkeypatch.setenv("IT_TEM_BP18_REVIEW_POLICY_ID","bp18-b3-version-one")
    return monkeypatch


def _epoch(store):
    with store.db() as con:
        return con.execute("SELECT epoch FROM live_policy_activation WHERE singleton=1").fetchone()[0]


def test_epoch_rollback_v1_v2_v1_never_revives_old_approval(
    tmp_path,enabled
):
    flow,jid,v1=start(tmp_path)
    a=flow.state.approve_copy("alice",jid,v1["generation"],v1["review_sha"])
    assert a["approval_sha"] and _epoch(flow.state)==1
    enabled.setenv("IT_TEM_BP18_REVIEW_POLICY_ID","bp18-b3-version-two")
    newer=LiveStore(flow.state.filename)
    assert _epoch(newer)==2
    with pytest.raises(LiveGateError,match="REVIEW_POLICY_REVALIDATION_REQUIRED"):
        newer._approved(newer.get("alice",jid))
    changed=newer.revalidate_review_policy("alice",jid,
                                           a["generation"],a["review_sha"])
    assert changed["approval_sha"] is None
    again=newer.approve_copy("alice",jid,changed["generation"],
                             changed["review_sha"],acknowledge_evidence=True)
    assert again["approval_sha"]!=a["approval_sha"]
    enabled.setenv("IT_TEM_BP18_REVIEW_POLICY_ID","bp18-b3-version-one")
    restored=LiveStore(newer.filename)
    assert _epoch(restored)==3
    assert restored.policy_status("alice",jid)["status"]=="REVALIDATION_REQUIRED"
    with pytest.raises(LiveGateError,match="REVIEW_POLICY_REVALIDATION_REQUIRED"):
        restored._approved(restored.get("alice",jid))
    back=restored.revalidate_review_policy("alice",jid,
                                          again["generation"],again["review_sha"])
    assert back["generation"]>again["generation"]
    assert back["copy_sha"]==again["copy_sha"]
    assert back["approval_sha"] is None
    assert back["review_sha"] not in (v1["review_sha"],changed["review_sha"])
    with pytest.raises(LiveGateError,match="STALE_REVIEW_OR_REVISION"):
        restored.approve_copy("alice",jid,a["generation"],a["review_sha"])
    with flow.cost.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]==0


def test_old_worker_instance_after_new_activation_fails_closed(tmp_path,enabled):
    flow,jid,v1=start(tmp_path)
    old_worker=flow.state
    a=old_worker.approve_copy("alice",jid,v1["generation"],v1["review_sha"])
    enabled.setenv("IT_TEM_BP18_REVIEW_POLICY_ID","bp18-b3-version-two")
    next_process=LiveStore(old_worker.filename)
    assert _epoch(next_process)==2
    # Runtime environment also changed in this process, but old review epoch
    # cannot be reconstructed into an approval from the previous process.
    with pytest.raises(LiveGateError,match="REVIEW_POLICY_RUNTIME_VERSION_CHANGED"):
        old_worker._approved(old_worker.get("alice",jid))
    # Old instance cannot reset database epoch after a new deployment.
    assert _epoch(next_process)==2
    assert old_worker.get("alice",jid)["approval_sha"]==a["approval_sha"]
    assert next_process.get("alice",jid)["generation"]==a["generation"]


def test_runtime_source_change_requires_restart_no_rule_cache_silent_reuse(
    tmp_path,enabled,monkeypatch
):
    import demo_staging.live.store as module
    flow,jid,v1=start(tmp_path)
    original=module.sources_fingerprint
    monkeypatch.setattr(module,"sources_fingerprint",lambda:"f"*64)
    assert flow.state.policy_status("alice",jid)["status"]=="RESTART_REQUIRED"
    with pytest.raises(LiveGateError,match="REVIEW_POLICY_RUNTIME_SOURCE_CHANGED"):
        flow.state.approve_copy("alice",jid,v1["generation"],v1["review_sha"])
    assert flow.state.get("alice",jid)["approval_sha"] is None
    monkeypatch.setattr(module,"sources_fingerprint",original)
    # Only the immutable release booted with the changed sources may record
    # its new hash. No in-place LRU cache invalidation is considered approval.


def test_legacy_review_epoch_migration_is_additive_no_approval_revived(
    tmp_path,monkeypatch
):
    monkeypatch.delenv("IT_TEM_BP18_F11_ENABLED",raising=False)
    flow,jid,legacy=start(tmp_path)
    old=flow.state.approve_copy("alice",jid,legacy["generation"],
                                 legacy["review_sha"])
    with flow.state.db() as con:
        count=con.execute("SELECT COUNT(*) FROM live_review_policy").fetchone()[0]
        assert count==0
    monkeypatch.setenv("IT_TEM_BP18_F11_ENABLED","YES")
    monkeypatch.setenv("IT_TEM_BP18_REVIEW_POLICY_ID","bp18-b3-from-legacy")
    new=LiveStore(flow.state.filename)
    assert new.get("alice",jid)["approval_sha"]==old["approval_sha"]
    assert new.policy_status("alice",jid)["status"]=="LEGACY_UNBOUND"
    with pytest.raises(LiveGateError,match="REVIEW_POLICY_REVALIDATION_REQUIRED"):
        new._approved(new.get("alice",jid))
    re=new.revalidate_review_policy("alice",jid,
                              old["generation"],old["review_sha"])
    assert re["approval_sha"] is None
    with new.db() as con:
        columns={row["name"] for row in con.execute("PRAGMA table_info(live_review_policy)")}
        assert "activation_epoch" in columns
        version=con.execute("SELECT activation_epoch FROM live_review_policy WHERE job_id=?",
                  (jid,)).fetchone()[0]
        assert version==1


def test_completed_historical_artifacts_remain_readonly_after_epoch_upgrade(
    tmp_path,monkeypatch
):
    import hashlib
    from src.image_generation.backend_adapter import BackendGeneratedImage
    from src.image_generation.size_selection import resolve_size_choice
    from tests.demo_live.test_live_contracts import sample_input
    from tests.demo_live.test_pipeline import png,FONT,FakeOwner,prepare_service
    monkeypatch.delenv("IT_TEM_BP18_F11_ENABLED",raising=False)
    flow,jid=prepare_service(tmp_path)
    flow.prepare("alice",jid,{**sample_input(),"image_size":"4:5",
       "generation_mode":"composed"},template_profile="A")
    owner=FakeOwner()
    old=flow.text("alice",jid,owner,offline=True)
    flow.state.approve_copy("alice",jid,old["generation"],old["review_sha"])
    flow.prompt("alice",jid,owner,offline=True)
    req=flow.image_input("alice",jid)
    native=resolve_size_choice("4:5")[1].native
    raw=png((195,197,199),size=native)
    candidate=BackendGeneratedImage(image_bytes=raw,mime_type="image/png",
      width=native[0],height=native[1],sha256=hashlib.sha256(raw).hexdigest(),
      job_id=jid,copy_revision=req.copy_revision,copy_hash=req.copy_hash,
      mock=True,receipt={"mode":"OFFLINE_FIXTURE","provider_calls":0})
    flow.accept_image_result("alice",jid,candidate,offline=True)
    flow.state.approve_image("alice",jid,candidate.sha256)
    completed=flow.compose("alice",jid,font_path=FONT)
    before={x:hashlib.sha256((flow.root/"outputs"/jid/x).read_bytes()).hexdigest()
            for x in ("final.png","caption.txt")}
    assert completed["state"]=="COMPLETED"
    monkeypatch.setenv("IT_TEM_BP18_F11_ENABLED","YES")
    monkeypatch.setenv("IT_TEM_BP18_REVIEW_POLICY_ID","bp18-b3-historical-readonly")
    flow.state=LiveStore(flow.state.filename)
    assert flow.state.get("alice",jid)["state"]=="COMPLETED"
    verified=flow.validate_final_artifacts("alice",jid)
    assert verified["final_sha"]==completed["final_sha"]
    assert verified["caption_sha"]==completed["caption_sha"]
    after={x:hashlib.sha256((flow.root/"outputs"/jid/x).read_bytes()).hexdigest()
            for x in ("final.png","caption.txt")}
    assert after==before
    with flow.cost.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]==0


def test_queued_image_attempt_stale_review_cannot_call_owner_or_commit_artifacts(
    tmp_path,enabled
):
    import hashlib
    from src.image_generation.backend_adapter import BackendGeneratedImage
    from src.image_generation.size_selection import resolve_size_choice
    from tests.demo_live.test_live_contracts import sample_input
    from tests.demo_live.test_pipeline import png,FakeOwner,prepare_service
    flow,jid=prepare_service(tmp_path)
    flow.prepare("alice",jid,{**sample_input(),"image_size":"4:5",
        "generation_mode":"composed"},template_profile="A")
    fake=FakeOwner()
    text=flow.text("alice",jid,fake,offline=True)
    approved=flow.state.approve_copy("alice",jid,text["generation"],text["review_sha"])
    prompt=flow.prompt("alice",jid,fake,offline=True)
    req=flow.image_input("alice",jid)
    assert flow.state.get("alice",jid)["state"]=="PROMPT_READY"
    assert [a for a in fake.calls if a in ("analyze","research","copy","prompt")]==[
        "analyze","research","copy","prompt"]
    raw=png((202,204,206),size=resolve_size_choice("4:5")[1].native)
    output=BackendGeneratedImage(image_bytes=raw,mime_type="image/png",
      width=1152,height=1440,sha256=hashlib.sha256(raw).hexdigest(),
      job_id=jid,copy_revision=req.copy_revision,copy_hash=req.copy_hash,
      mock=True,receipt={"mode":"OFFLINE_FIXTURE","provider_calls":0})
    enabled.setenv("IT_TEM_BP18_REVIEW_POLICY_ID","bp18-b3-version-two")
    flow.state=LiveStore(flow.state.filename)
    with pytest.raises(LiveGateError,match="REVIEW_POLICY_REVALIDATION_REQUIRED"):
        flow.image_input("alice",jid)
    with pytest.raises(LiveGateError,match="REVIEW_POLICY_REVALIDATION_REQUIRED"):
        flow.accept_image_result("alice",jid,output,offline=True)
    assert not flow.image_path(jid).exists()
    assert flow.state.get("alice",jid)["state"]=="PROMPT_READY"
    assert flow.state.get("alice",jid)["approval_sha"]==approved["approval_sha"]
    newer=flow.state.revalidate_review_policy("alice",jid,prompt["generation"],
                                                   prompt["review_sha"])
    assert newer["state"]=="COPY_REVIEW_REQUIRED"
    assert newer["approval_sha"] is None
    assert newer["prompt_json"] is None
    with pytest.raises(LiveGateError,match="IMAGE_NOT_READY"):
        flow.accept_image_result("alice",jid,output,offline=True)
    with flow.cost.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]==0
