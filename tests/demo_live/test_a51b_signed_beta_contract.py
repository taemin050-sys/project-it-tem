"""A5-1B: real Ed25519 signature verifier with only throwaway TEST keys.

No actual Owner/PM signoff is created or stored in the canonical repository.
Never enables paid Provider, even if BOTH test roles cryptographically sign.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from demo_staging.live.contracts import LiveGateError, digest
from demo_staging.live.a51b_signed_beta_contract import (
    CONTRACT, BETA_PREFIX, BETA_VERSION, beta_profile,
    verify_activation, validate_beta_snapshot,
    select_signed_beta, verify_frozen_runtime_activation,
)
from demo_staging.live.a5_beta_profile_v3 import (
    PRETENDARD_139_SHA, FONT_LICENSE_SHA, build_proposal,
)
from tests.demo_live.test_http_gateway import setup, login
from tests.demo_live.test_pm_track_a_single_candidate import (
    configure_qa,new_job,ORIGIN,
)
from tests.demo_live.test_live_contracts import sample_input


def openssl(*args):
    result=subprocess.run(["openssl",*map(str,args)],capture_output=True,
                          text=True,timeout=10)
    assert result.returncode==0,(args,result.stderr[:500])
    return result


@pytest.fixture
def signed_beta(tmp_path,monkeypatch):
    policy=tmp_path/"authority"
    trust=tmp_path/"trusted-public-keys"
    policy.mkdir(mode=0o700)
    trust.mkdir(mode=0o700)
    keys={}
    for role in ("image_owner","pm"):
        private=tmp_path/(role+".private.TEST_ONLY.pem")
        pub=trust/(role+".pub.pem")
        openssl("genpkey","-algorithm","ed25519","-out",private)
        openssl("pkey","-in",private,"-pubout","-out",pub)
        private.chmod(0o600)
        pub.chmod(0o600)
        keys[role]={"private":private,"public":pub,
                    "sha":hashlib.sha256(pub.read_bytes()).hexdigest()}
    now=datetime.now(timezone.utc)
    evidence={
        "contract":CONTRACT,
        "decision_id":"TEST_ONLY_NOT_REAL_OWNER_PM_APPROVAL",
        "profile_choice":"A",
        "policy_epoch":"a51b-test-epoch-20261110",
        "profile_sha256":digest(build_proposal("A")),
        "font_sha256":PRETENDARD_139_SHA,
        "font_license_sha256":FONT_LICENSE_SHA,
        "valid_from_utc":(now-timedelta(minutes=1)).isoformat(),
        "expires_utc":(now+timedelta(days=2)).isoformat(),
        "deployment_scope":"GCP_A_ISOLATED_BETA_ONLY",
    }
    record=policy/"activation.json"
    record.write_text(json.dumps(evidence,sort_keys=True,ensure_ascii=False,
                                 separators=(",",":")))
    record.chmod(0o600)
    for role in keys:
        sig=policy/(role+".sig")
        openssl("pkeyutl","-sign","-inkey",keys[role]["private"],"-rawin",
                "-in",record,"-out",sig)
        sig.chmod(0o600)
    monkeypatch.setenv("IT_TEM_A51B_POLICY_ROOT",str(policy))
    monkeypatch.setenv("IT_TEM_A51B_TRUST_ROOT",str(trust))
    monkeypatch.setenv("IT_TEM_A51B_IMAGE_OWNER_PUB_SHA",keys["image_owner"]["sha"])
    monkeypatch.setenv("IT_TEM_A51B_PM_PUB_SHA",keys["pm"]["sha"])
    monkeypatch.setenv("IT_TEM_A51B_NEW_JOB_ENABLE","YES")
    monkeypatch.setenv("IT_TEM_A51B_PROFILE","A")
    monkeypatch.delenv("IT_TEM_A5_V3_BETA_PROFILE",raising=False)
    monkeypatch.setenv("IT_TEM_LIVE_ENABLED","NO")
    monkeypatch.setenv("IT_TEM_LIVE_EXECUTION_APPROVED","NO")
    monkeypatch.setenv("IT_TEM_ENABLE_BILLABLE_TEXT_CALLS","NO")
    return {"policy":policy,"trust":trust,"keys":keys,
            "record":record,"evidence":evidence}


def test_a51b_real_crypto_verifies_both_distinct_test_keys(signed_beta):
    approved=verify_activation(
        choice="A",policy_root=str(signed_beta["policy"]),
        trust_root=str(signed_beta["trust"]),
        trusted_sha={role:record["sha"] for role,record in signed_beta["keys"].items()})
    assert approved["profile_id"]==BETA_PREFIX+"A"
    assert approved["profile_version"]==BETA_VERSION
    assert approved["safe_zone"]["verified_signer_roles"]==["image_owner","pm"]
    assert approved["safe_zone"]["real_provider_permitted"] is False
    assert approved["safe_zone"]["real_customer_assets_permitted"] is False
    assert approved["safe_zone"]["candidate_mask_verified"] is False
    assert approved["safe_zone"]["signed_owner_pm_decision_sha256"]==hashlib.sha256(
        signed_beta["record"].read_bytes()).hexdigest()
    assert verify_frozen_runtime_activation({
      "profile_id":approved["profile_id"],
      "profile_version":approved["profile_version"],
      "safe_zone":approved["safe_zone"],
      "safe_zone_sha":digest(approved["safe_zone"]),
      "layout_sha":digest(approved["layout"])}) == approved


@pytest.mark.parametrize("tamper",("decision","owner_signature","pm_signature",
                                     "trust_fingerprint","world_readable",
                                     "expired","wrong_profile","missing_role"))
def test_a51b_tampered_or_missing_approval_fails_closed(signed_beta,monkeypatch,tamper):
    root=signed_beta["policy"];trust=signed_beta["trust"]
    if tamper=="decision":
        p=signed_beta["record"];p.write_text(p.read_text().replace(
            "GCP_A_ISOLATED_BETA_ONLY","GCP_A_PRODUCTION"))
    elif tamper in ("owner_signature","pm_signature"):
        p=root/(("image_owner" if tamper=="owner_signature" else "pm")+".sig")
        p.write_bytes(b"\\0"*64)
    elif tamper=="trust_fingerprint":
        monkeypatch.setenv("IT_TEM_A51B_PM_PUB_SHA","0"*64)
    elif tamper=="world_readable":
        root.chmod(0o755)
    elif tamper=="expired":
        p=signed_beta["record"];p.write_text(p.read_text().replace(
            signed_beta["evidence"]["expires_utc"],"2020-01-01T00:00:00+00:00"))
    elif tamper=="wrong_profile":
        monkeypatch.setenv("IT_TEM_A51B_PROFILE","C")
    elif tamper=="missing_role":
        (root/"pm.sig").unlink()
    with pytest.raises(LiveGateError,match="A51B_"):
        select_signed_beta(sample_input()|{
           "image_size":"4:5","generation_mode":"composed"},template_profile="A")


def test_a51b_profile_activation_never_authorizes_live(signed_beta,monkeypatch):
    monkeypatch.setenv("IT_TEM_LIVE_ENABLED","YES")
    with pytest.raises(LiveGateError,match="A51B_BETA_PAID_RUNTIME_NOT_ACTIVATED"):
        select_signed_beta({"image_size":"4:5","generation_mode":"composed"},
                           template_profile="A")


def test_a51b_cannot_self_approve_with_one_key(signed_beta,monkeypatch):
    same=signed_beta["keys"]["image_owner"]["sha"]
    monkeypatch.setenv("IT_TEM_A51B_PM_PUB_SHA",same)
    with pytest.raises(LiveGateError,match="A51B_(DISTINCT_SIGNER_KEYS_REQUIRED|TRUST_FINGERPRINT_MISMATCH)"):
        select_signed_beta({"image_size":"4:5","generation_mode":"composed"},
                           template_profile="A")


def test_a51b_unsigned_selector_conflicts_with_signed(signed_beta,monkeypatch):
    monkeypatch.setenv("IT_TEM_A5_V3_BETA_PROFILE","A")
    with pytest.raises(LiveGateError,match="A51B_SIGNED_AND_UNSIGNED_SELECTORS_CONFLICT"):
        select_signed_beta({"image_size":"4:5","generation_mode":"composed"},
                           template_profile="A")


def test_a51b_stale_signature_revocation_blocks_after_job_created(
        tmp_path,monkeypatch,signed_beta):
    configure_qa(monkeypatch)
    monkeypatch.setenv("IT_TEM_A51B_PROFILE","A")
    monkeypatch.setenv("IT_TEM_A51B_NEW_JOB_ENABLE","YES")
    monkeypatch.setenv("IT_TEM_A51B_POLICY_ROOT",str(signed_beta["policy"]))
    monkeypatch.setenv("IT_TEM_A51B_TRUST_ROOT",str(signed_beta["trust"]))
    app,codes=setup(tmp_path/"app")
    with TestClient(app,client=("127.0.0.1",12345)) as client:
        login(client,codes["alice"])
        jid=new_job(client)
        resp=client.post("/demo/api/live/jobs/"+jid+"/input",json={
            **sample_input(),"image_size":"4:5","generation_mode":"composed",
        },headers=ORIGIN)
        assert resp.status_code==200,resp.text
        state=app.state.live_pipeline.state
        frozen=state.template("alice",jid)
        assert frozen["profile_id"]==BETA_PREFIX+"A"
        assert frozen["profile_version"]==BETA_VERSION
        assert frozen["safe_zone"]["real_provider_permitted"] is False
        assert frozen["safe_zone"]["verified_decision_id"].startswith("TEST_ONLY")
        # The signed Job does not change the default v2 or A5-1 proposal.
        assert state.template("alice",jid)==frozen
        (signed_beta["policy"]/"pm.sig").unlink()
        with pytest.raises(LiveGateError,match="A51B_"):
            verify_frozen_runtime_activation(frozen)
        assert state.template("alice",jid)==frozen


@pytest.mark.parametrize("mode,ratio",(
   ("freeform","4:5"),("composed","3:4"),("composed","9:16"),
))
def test_a51b_signed_profile_does_not_replace_other_product_modes(
        tmp_path,monkeypatch,signed_beta,mode,ratio):
    configure_qa(monkeypatch)
    monkeypatch.setenv("IT_TEM_A51B_PROFILE","A")
    app,codes=setup(tmp_path/"app")
    with TestClient(app,client=("127.0.0.1",12345)) as client:
        login(client,codes["alice"])
        jid=new_job(client)
        resp=client.post("/demo/api/live/jobs/"+jid+"/input",json={
            **sample_input(),"image_size":ratio,"generation_mode":mode,
        },headers=ORIGIN)
        assert resp.status_code==200,resp.text
        assert app.state.live_pipeline.state.template("alice",jid)[
            "profile_id"].startswith("OWNER_IMAGE_SIZE_")


def test_a51b_public_key_or_policy_in_repo_not_allowed(signed_beta,monkeypatch):
    monkeypatch.setenv("IT_TEM_A51B_POLICY_ROOT",str(
        Path(__file__).resolve().parents[2]))
    with pytest.raises(LiveGateError,match="A51B_PRIVATE_ROOT"):
        select_signed_beta({"image_size":"4:5","generation_mode":"composed"},
                           template_profile="A")


def test_a51b_do_not_consider_signed_profile_real_product_or_cost_approval(
        signed_beta):
    p=select_signed_beta({"image_size":"4:5","generation_mode":"composed"},
                         template_profile="A")
    z=p["safe_zone"]
    assert z["real_provider_permitted"] is False
    assert z["real_customer_assets_permitted"] is False
    assert z["candidate_mask_verified"] is False
    assert z["rights_review_verified"] is False
    assert z["protection_basis"]=="REAL_CANDIDATE_PRODUCT_AND_LABEL_MASK_REQUIRED"

@pytest.mark.parametrize("flag",(
    "IT_TEM_LIVE_ENABLED",
    "IT_TEM_LIVE_EXECUTION_APPROVED",
    "IT_TEM_ENABLE_BILLABLE_TEXT_CALLS",
))
def test_a51b_beta_signed_job_initiation_refuses_any_billable_flag(
        signed_beta,monkeypatch,flag):
    monkeypatch.setenv(flag,"YES")
    with pytest.raises(LiveGateError,match="A51B_BETA_PAID_RUNTIME_NOT_ACTIVATED"):
        select_signed_beta({"image_size":"4:5","generation_mode":"composed"},
                           template_profile="A")

@pytest.mark.parametrize("extra_seconds,permitted",[
    (0, True), (1, False), (23*3600, False),
])
def test_a51b_r1_profile_exact_90d_max_authentic_double_signature(
        signed_beta,extra_seconds,permitted):
    # A true detached Ed25519 signature over exact mutated bytes is
    # necessary, but never sufficient to bypass the signed policy duration.
    fixed=datetime(2026,11,10,10,0,0,tzinfo=timezone.utc)
    start=fixed-timedelta(days=45)
    end=start+timedelta(days=90,seconds=extra_seconds)
    record=signed_beta["record"]
    blob=json.loads(record.read_text())
    blob["valid_from_utc"]=start.isoformat()
    blob["expires_utc"]=end.isoformat()
    record.write_text(json.dumps(blob,sort_keys=True,ensure_ascii=False,
                                 separators=(",",":")))
    for role, key in signed_beta["keys"].items():
        signature=signed_beta["policy"]/(role+".sig")
        openssl("pkeyutl","-sign","-inkey",key["private"],"-rawin",
                "-in",record,"-out",signature)
    arguments={
        "choice":"A","policy_root":str(signed_beta["policy"]),
        "trust_root":str(signed_beta["trust"]),
        "trusted_sha":{
            role:k["sha"] for role,k in signed_beta["keys"].items()
        },
        "now":fixed,
    }
    if permitted:
        verified=verify_activation(**arguments)
        assert verified["profile_id"]==BETA_PREFIX+"A"
    else:
        with pytest.raises(LiveGateError,match="A51B_DECISION_EXPIRED_OR_NOT_YET_VALID"):
            verify_activation(**arguments)
