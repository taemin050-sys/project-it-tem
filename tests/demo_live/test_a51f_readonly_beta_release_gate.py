"""A51F real beta release inspection cannot manufacture permission or GCP PASS."""
from __future__ import annotations

import json
from pathlib import Path
import pytest
from scripts import a51f_real_beta_readonly_release_gate as gate


@pytest.fixture
def sample(tmp_path,monkeypatch):
    root=tmp_path/"source"
    root.mkdir()
    (root/"demo_staging"/"live").mkdir(parents=True)
    (root/"demo_staging"/"live"/
     "a51f_product_rights_authority.py").write_text("sealed source")
    observed={
        "contract":gate.PROBE_CONTRACT,
        "source_sha_observed":"a"*40,
        "ledgers":{
            "owner_provider":{"schema":"MISSING_NOT_MIGRATED","exists":False},
        },
        "beta_ready":False,"deployment_approved":False,
    }
    remote=tmp_path/"external_c_a_readonly.json"
    def save():
        remote.write_text(json.dumps(observed))
    save()
    def fakegit(*args,repo):
        if args==("rev-parse","HEAD"):return "b"*40
        if args==("rev-parse","HEAD^{tree}"):return "c"*40
        if args==("status","--porcelain"):return ""
        raise AssertionError(args)
    monkeypatch.setattr(gate,"git",fakegit)
    return locals()


def test_real_gcp_old_sha_and_missing_owner_ledger_hold(sample):
    x=sample
    d=gate.inspect(repo=x["root"],gcp_probe=x["remote"])
    assert d["local_worktree_clean"] is True
    assert d["source_matches_observed_gcp"] is False
    assert d["gcp_owner_provider_ledger_schema_present"] is False
    assert "DEPLOYED_GCP_A_SOURCE_SHA_MISMATCH" in d["human_approval_gates_unmet"]
    assert "GCP_A_OWNER_PROVIDER_ATTEMPT_LEDGER_UNAVAILABLE" in d["human_approval_gates_unmet"]
    assert d["gcp_deployment_gate"]=="HOLD"
    assert d["paid_worker_gate"]=="HOLD"
    assert d["real_provider_e2e_completed"]==0
    assert d["billing_calls_performed"]==0


def test_same_sha_and_pretend_owner_ledger_pass_still_not_authority(sample):
    x=sample
    x["observed"]["source_sha_observed"]="b"*40
    x["observed"]["ledgers"]["owner_provider"]={
        "schema":"TABLE_PRESENT","exists":True,
    }
    x["observed"]["deployment_approved"]=True
    x["observed"]["beta_ready"]=True
    x["save"]()
    d=gate.inspect(repo=x["root"],gcp_probe=x["remote"])
    assert d["source_matches_observed_gcp"] is True
    assert d["gcp_owner_provider_ledger_schema_present"] is True
    assert d["gcp_deployment_gate"]=="HOLD"
    assert d["commercial_release_ready"] is False
    assert d["existing_a51e_local_fixture_may_be_promoted"] is False
    assert d["actual_pm_hard_cap_approved"] is False


@pytest.mark.parametrize("broken",[
    "wrong_contract","removed_contract","invalid_json","missing_file",
    "symlink","non_object","invalid_owner_schema",
])
def test_invalid_or_untrusted_readonly_source_rejected(sample,broken):
    x=sample
    rec=x["observed"]
    if broken=="wrong_contract":rec["contract"]="UNTRUSTED"
    elif broken=="removed_contract":rec.pop("contract")
    elif broken=="non_object":rec.clear()
    elif broken=="invalid_owner_schema":
        rec["ledgers"]["owner_provider"]=[]
    elif broken=="invalid_json":
        x["remote"].write_text("{invalid")
    elif broken=="missing_file":
        x["remote"].unlink()
    elif broken=="symlink":
        temp=x["remote"].with_name("real.json")
        temp.write_text(json.dumps(rec))
        x["remote"].unlink()
        x["remote"].symlink_to(temp)
    if broken in ("wrong_contract","removed_contract","non_object",
                  "invalid_owner_schema"):x["save"]()
    if broken=="invalid_owner_schema":
        # The probe's owner state must be a dict; shape errors fail closed.
        with pytest.raises(ValueError,match="GCP_LEDGER_PROBE_INVALID"):
            gate.inspect(repo=x["root"],gcp_probe=x["remote"])
    else:
        with pytest.raises((ValueError,OSError)):
            gate.inspect(repo=x["root"],gcp_probe=x["remote"])


def test_dirty_local_source_always_hold(sample,monkeypatch):
    x=sample
    prior=gate.git
    monkeypatch.setattr(gate,"git",lambda *args,repo: " M sample.py"
        if args==("status","--porcelain") else prior(*args,repo=repo))
    d=gate.inspect(repo=x["root"],gcp_probe=x["remote"])
    assert d["local_worktree_clean"] is False
    assert "LOCAL_SOURCE_NOT_CLEAN" in d["human_approval_gates_unmet"]
    assert d["disposition"]=="RELEASE_CANDIDATE_NOT_YET_AUTHORIZED"
