"""A51C signed A-only HARD_CAP binding; all secrets are ephemeral TEST keys.

The tests NEVER start the worker, transmit a photo, or call a real Provider.
A valid test PM cost signature is intentionally NOT Owner/PM product approval.
"""
from __future__ import annotations

from datetime import datetime,timedelta,timezone
from hashlib import sha256
import json
from pathlib import Path
import subprocess

import pytest

from demo_staging.live.contracts import LiveGateError
from demo_staging.live.a51c_signed_cost_authority import (
    CONTRACT,signed_hard_cap_policy,require_preinitialized_candidate_ledgers)
from demo_staging.live.http_api import web_queue_policy
from demo_staging.live.worker import policy_from_env
from demo_staging.live.queue import LiveQueue
from demo_staging.live.pipeline import LivePipeline
from demo_staging.live_safety import LiveNotAuthorized
from src.serving.job_store import JobStore
from src.image_generation.provider_attempts import ProviderAttemptStore


def openssl(*args):
    result=subprocess.run(["openssl",*map(str,args)],capture_output=True,
                          text=True,timeout=10)
    assert result.returncode==0,result.stderr[:300]


@pytest.fixture
def pm_beta(tmp_path,monkeypatch):
    root=tmp_path/"isolated_beta"
    root.mkdir(mode=0o700)
    policy=tmp_path/"separate_pm_authority"
    trust=tmp_path/"separate_pubkey"
    policy.mkdir(mode=0o700)
    trust.mkdir(mode=0o700)
    priv=tmp_path/"pm_TEST_ONLY.private.pem"
    pub=trust/"pm-cost.pub.pem"
    openssl("genpkey","-algorithm","ed25519","-out",priv)
    openssl("pkey","-in",priv,"-pubout","-out",pub)
    priv.chmod(0o600);pub.chmod(0o600)
    start=datetime.now(timezone.utc)-timedelta(minutes=1)
    record={
        "contract":CONTRACT,
        "decision_id":"TEST_ONLY_PM_BUDGET_NOT_ACTUAL_AUTHORITY",
        "deployment_scope":"GCP_A_ISOLATED_BETA_ONLY",
        "execution_scope":"HARD_CAP_SINGLE_IMAGE_BETA",
        "candidate_runtime_root":str(root.resolve()),
        "source_commit":"b"*40,
        "policy_epoch":"TEST_ONLY_epoch_1",
        "approved_actors":["alice"],
        "budget_usd":"1.500000",
        "text_reservation_usd":"0.100000",
        "image_reservation_usd":"0.500000",
        "max_requests":12,
        "valid_from_utc":start.isoformat(),
        "expires_utc":(start+timedelta(days=1)).isoformat(),
    }
    file=policy/"spend_approval.json"
    sig=policy/"pm-cost.sig"
    def resign():
        file.write_text(json.dumps(record,sort_keys=True,
            ensure_ascii=False,separators=(",",":")))
        file.chmod(0o600)
        openssl("pkeyutl","-sign","-inkey",priv,"-rawin",
                "-in",file,"-out",sig)
        sig.chmod(0o600)
    resign()
    flags={
        "IT_TEM_A51C_HARD_CAP_ENABLE":"YES",
        "IT_TEM_LIVE_COST_POLICY":"HARD_CAP",
        "IT_TEM_TAILNET_SSO_ONLY":"YES",
        "IT_TEM_TAILNET_AUTH_ENABLED":"YES",
        "IT_TEM_A51C_COST_POLICY_ROOT":str(policy),
        "IT_TEM_A51C_COST_TRUST_ROOT":str(trust),
        "IT_TEM_A51C_PM_COST_PUB_SHA":sha256(pub.read_bytes()).hexdigest(),
        "IT_TEM_A51C_DEPLOYED_SOURCE_SHA":record["source_commit"],
        "IT_TEM_LIVE_APPROVED_ACTORS":"alice",
        "IT_TEM_LIVE_WEB_QUEUE_ENABLED":"YES",
        "IT_TEM_LIVE_ENABLED":"YES",
        "IT_TEM_LIVE_EXECUTION_APPROVED":"YES",
        "IT_TEM_PROVIDER_READINESS_CONFIRMED":"YES",
        "OPENAI_API_KEY":"FAKE_TEST_ONLY_NEVER_SENT",
    }
    for k,v in flags.items():monkeypatch.setenv(k,v)
    def init():
        # Simulate the operator's explicit isolated candidate migration,
        # never implicit creation during signed policy verification.
        LivePipeline(root/"live",JobStore(root/"jobs"))
        LiveQueue(root/"live"/"queue.sqlite")
        ProviderAttemptStore(root/"live"/"owner_image"/"image_attempts.sqlite")
    return {"root":root,"policy":policy,"trust":trust,"record":record,
            "file":file,"sig":sig,"resign":resign,"init":init}


def test_signed_hard_cap_verifies_scope_and_live_config(pm_beta):
    x=pm_beta
    with pytest.raises(LiveGateError,match="A51C_HARD_CAP_REQUIRED_LEDGER_NOT_INITIALIZED"):
        require_preinitialized_candidate_ledgers(x["root"])
    with pytest.raises(LiveGateError,match="A51C_HARD_CAP_REQUIRED_LEDGER_NOT_INITIALIZED"):
        # Signature alone must not initialize a single DB.
        policy_from_env(x["root"])
    assert list(x["root"].iterdir())==[]
    signed=signed_hard_cap_policy(x["root"])
    assert signed["budget_usd"]=="1.500000"
    assert signed["image_reservation_usd"]=="0.500000"
    assert signed["monitoring_only"] is False
    assert web_queue_policy(x["root"])["enabled"] is False
    x["init"]()
    assert require_preinitialized_candidate_ledgers(x["root"]) is None
    web=web_queue_policy(x["root"])
    assert web["enabled"] is True
    assert web["monitoring_only"] is False
    assert web["budget"]==signed["budget_usd"]
    assert web["limit"]==signed["max_requests"]
    worker=policy_from_env(x["root"])
    assert worker.monitoring_only is False
    assert worker.cost.monitoring_only is False
    assert worker.cost.max_requests==12
    assert worker.cost.budget_usd==1_500_000
    assert worker.text_reservation==.1
    assert worker.image_reservation==.5
    assert worker.approved_actors==frozenset(["alice"])


@pytest.mark.parametrize("attack",[
    "deleted_signature","tampered_signed_record","source_drift","actor_drift",
    "trust_sha","sso_off","feature_disabled","monitored_policy","expired",
    "90days","invalid_cap","zero_reservation","strange_path","bad_scope",
])
def test_signed_hard_cap_rejects_each_invalid_authorization(
        pm_beta,monkeypatch,attack):
    x=pm_beta
    x["init"]()
    if attack=="deleted_signature":x["sig"].unlink()
    elif attack=="tampered_signed_record":
        x["file"].write_text(x["file"].read_text().replace("1.500000","9.500000"))
    elif attack=="source_drift":
        monkeypatch.setenv("IT_TEM_A51C_DEPLOYED_SOURCE_SHA","a"*40)
    elif attack=="actor_drift":
        monkeypatch.setenv("IT_TEM_LIVE_APPROVED_ACTORS","bob")
    elif attack=="trust_sha":
        monkeypatch.setenv("IT_TEM_A51C_PM_COST_PUB_SHA","f"*64)
    elif attack=="sso_off":
        monkeypatch.setenv("IT_TEM_TAILNET_SSO_ONLY","NO")
    elif attack=="feature_disabled":
        monkeypatch.setenv("IT_TEM_A51C_HARD_CAP_ENABLE","NO")
    elif attack=="monitored_policy":
        monkeypatch.setenv("IT_TEM_LIVE_COST_POLICY","MONITOR_ONLY")
    elif attack=="expired":
        x["record"]["expires_utc"]=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()
        x["resign"]()
    elif attack=="90days":
        x["record"]["expires_utc"]=(datetime.now(timezone.utc)+timedelta(days=90)).isoformat()
        x["resign"]()
    elif attack=="invalid_cap":
        x["record"]["budget_usd"]="NaN";x["resign"]()
    elif attack=="zero_reservation":
        x["record"]["image_reservation_usd"]="0.000000";x["resign"]()
    elif attack=="strange_path":
        x["record"]["candidate_runtime_root"]="/tmp/not-this-root";x["resign"]()
    elif attack=="bad_scope":
        x["record"]["deployment_scope"]="GCP_B";x["resign"]()
    with pytest.raises((LiveGateError,LiveNotAuthorized)):
        policy_from_env(x["root"])
    assert web_queue_policy(x["root"])["enabled"] is False


def test_missing_owner_provider_ledger_rejected_without_reinitialization(pm_beta):
    x=pm_beta;x["init"]()
    owner=x["root"]/"live"/"owner_image"/"image_attempts.sqlite"
    owner.unlink()
    with pytest.raises(LiveGateError,match="A51C_HARD_CAP_REQUIRED_LEDGER_NOT_INITIALIZED"):
        require_preinitialized_candidate_ledgers(x["root"])
    assert web_queue_policy(x["root"])["enabled"] is False
    assert not owner.exists()


def test_owner_unknown_attempt_blocks_hard_cap_start(pm_beta):
    from uuid import uuid4
    x=pm_beta;x["init"]()
    owner=ProviderAttemptStore(x["root"]/"live"/"owner_image"/"image_attempts.sqlite")
    job,project=uuid4(),uuid4()
    attempt=owner.begin(job,project,"c"*64,budget_limit_usd="1.500000",
                        reservation_usd="0.500000")
    owner.finish(job,project,attempt,state="unknown",
                 error_code="PROVIDER_SUBMISSION_UNKNOWN")
    with pytest.raises(LiveGateError,match="A51C_HARD_CAP_OWNER_PROVIDER_ATTEMPT_UNRECONCILED"):
        require_preinitialized_candidate_ledgers(x["root"])
    assert web_queue_policy(x["root"])["enabled"] is False


def test_existing_monitored_policy_unchanged_when_beta_switch_off(
        tmp_path,monkeypatch):
    monkeypatch.setenv("IT_TEM_A51C_HARD_CAP_ENABLE","NO")
    monkeypatch.setenv("IT_TEM_LIVE_COST_POLICY","MONITOR_ONLY")
    monkeypatch.setenv("IT_TEM_LIVE_ENABLED","YES")
    monkeypatch.setenv("IT_TEM_LIVE_EXECUTION_APPROVED","YES")
    monkeypatch.setenv("IT_TEM_PROVIDER_READINESS_CONFIRMED","YES")
    monkeypatch.setenv("IT_TEM_LIVE_APPROVED_ACTORS","alice")
    monkeypatch.setenv("OPENAI_API_KEY","FAKE_TEST_ONLY")
    legacy=policy_from_env(tmp_path)
    assert legacy.monitoring_only is True
    assert legacy.cost.monitoring_only is True


def test_real_worker_authorizer_hard_cap_blocks_legacy_job_before_billing(
        pm_beta,monkeypatch):
    import sqlite3
    from io import BytesIO
    from PIL import Image
    from src.serving.job_store import ValidatedUpload
    from demo_staging.app import DemoLedger
    from demo_staging.live.worker import authorize_worker_item
    from tests.demo_live.test_live_contracts import sample_input
    from hashlib import sha256

    x=pm_beta
    x["init"]()
    root=x["root"]
    flow=policy_from_env(root)
    photos=[]
    for i in range(2):
        buf=BytesIO()
        Image.new("RGB",(320,240),(120+i*20,140,150)).save(buf,"PNG")
        raw=buf.getvalue()
        photos.append(ValidatedUpload(
            f"product{i}.png","image/png",raw,320,240,
            sha256(raw).hexdigest(),None))
    original=JobStore(root/"jobs").create_job(photos,[])
    jid=original["job_id"]
    DemoLedger(root/"demo.sqlite3").claim("alice",jid)
    state=flow.prepare("alice",jid,sample_input())
    assert state["state"]=="INPUT_STORED"
    item={"actor":"alice","job_id":jid,"stage":"analysis",
          "mode":"LIVE","context_sha":state["input_sha"]}
    with pytest.raises(LiveGateError,match="A51C_HARD_CAP_SIGNED_BETA_JOB_REQUIRED"):
        authorize_worker_item(flow,item)
    from demo_staging.live.a51b_signed_beta_contract import BETA_PREFIX
    gates=("real_provider_permitted","real_customer_assets_permitted",
           "candidate_mask_verified","rights_review_verified")
    # Fake profile ID alone is insufficient: an A5-1B profile legitimately
    # signed for typography has the rights/Mask/paid flags all False.
    monkeypatch.setattr(flow.state,"template",
        lambda *_:{"profile_id":BETA_PREFIX+"A",
                   "safe_zone":{k:False for k in gates}})
    with pytest.raises(LiveGateError,match="A51C_HARD_CAP_PRODUCT_RIGHTS_NOT_AUTHORIZED"):
        authorize_worker_item(flow,item)
    # Even forging the gate flags cannot bypass the separately verified
    # real Owner+PM signed profile (no such keys exist for this test job).
    monkeypatch.setattr(flow.state,"template",
        lambda *_:{"profile_id":BETA_PREFIX+"A",
                   "safe_zone":{k:True for k in gates}})
    with pytest.raises(LiveGateError,match="A51B_RUNTIME_PROFILE_NOT_ENABLED"):
        authorize_worker_item(flow,item)
    with sqlite3.connect(flow.cost.filename) as db:
        assert db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]==0
    with sqlite3.connect(root/"live"/"owner_image"/"image_attempts.sqlite") as db:
        assert db.execute("SELECT COUNT(*) FROM provider_attempts").fetchone()[0]==0
    # Same previously-created flow must not survive PM-signature revocation.
    x["sig"].unlink()
    with pytest.raises(LiveGateError,match="A51B_PRIVATE_EVIDENCE_FILE_MISSING"):
        authorize_worker_item(flow,item)


def test_signed_cap_does_not_imply_image_owner_profile_or_product_rights(
        pm_beta):
    x=pm_beta
    x["init"]()
    data=signed_hard_cap_policy(x["root"])
    assert data["monitoring_only"] is False
    assert "owner_pm_profile_approved" not in data
    assert "rights_verified" not in data
    assert "provider_calls_authorized" not in data
