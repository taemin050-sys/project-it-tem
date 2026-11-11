"""A51F dual human-signature source rights before paid dispatch.

Every signature here uses ephemeral *test* Ed25519 identities. This does not
constitute real IP permission or enable any paid calls, GCP or real beta.
"""
from __future__ import annotations

from datetime import datetime,timedelta,timezone
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import subprocess

from PIL import Image
import pytest

from demo_staging.live.contracts import LiveGateError
from demo_staging.live.a51f_product_rights_authority import (
    CONTRACT,_assets_hash,validate_signed_source_rights,
)
from src.serving.job_store import JobStore,ValidatedUpload


def crypto(*args):
    result=subprocess.run(["openssl",*map(str,args)],capture_output=True,
                          text=True,timeout=10,check=False)
    assert result.returncode==0,result.stderr[:200]


def image(color,name):
    out=BytesIO()
    Image.new("RGB",(200,300),color).save(out,format="PNG")
    data=out.getvalue()
    return ValidatedUpload(name,"image/png",data,200,300,sha256(data).hexdigest())


@pytest.fixture
def signed(tmp_path,monkeypatch):
    runtime=tmp_path/"runtime"
    runtime.mkdir(mode=0o700)
    store=JobStore(runtime/"jobs")
    job=store.create_job([
        image((70,90,150),"sku-a1.png"),image((80,100,155),"sku-a2.png")
    ],[image((90,120,170),"background.png")])
    rights=tmp_path/"rights";trust=tmp_path/"public"
    rights.mkdir(mode=0o700);trust.mkdir(mode=0o700)
    jid=job["job_id"]
    roles=("image_owner","pm")
    private={}
    trusted={}
    for role in roles:
        private[role]=tmp_path/(role+".private.pem")
        pub=trust/(role+".pub.pem")
        crypto("genpkey","-algorithm","ed25519","-out",private[role])
        crypto("pkey","-in",private[role],"-pubout","-out",pub)
        private[role].chmod(0o600);pub.chmod(0o600)
        trusted[role]=sha256(pub.read_bytes()).hexdigest()
    license=rights/(jid+".rights_evidence")
    license.write_text("TEST_ONLY_NOT_A_REAL_LICENSE")
    license.chmod(0o600)
    now=datetime.now(timezone.utc)
    record={
        "contract":CONTRACT,
        "decision_id":"TEST_ONLY_OWNER_PM_NOT_COMMERCIAL",
        "deployment_scope":"GCP_A_ISOLATED_BETA_ONLY",
        "deployed_source_commit":"a"*40,
        "actor":"alice",
        "job_id":jid,
        "policy_epoch":"TEST_ONLY_A51F_EPOCH_1",
        "product_sku":"sku_care_A",
        "generation_mode":"composed",
        "image_size":"4:5",
        "assets_sha256":_assets_hash(store,job),
        "rights_evidence_sha256":sha256(license.read_bytes()).hexdigest(),
        "rights_scope":"OWNED_OR_LICENSED_FOR_APPROVED_PROVIDER_AD_GENERATION",
        "provider_id":"openai",
        "grant_basis":"DOCUMENTED_LICENSE",
        "review_decision":"APPROVE_LIMITED_GCP_A_PROVIDER_TRANSFER",
        "valid_from_utc":(now-timedelta(minutes=1)).isoformat(),
        "expires_utc":(now+timedelta(hours=24)).isoformat(),
    }
    target=rights/(jid+".source_rights.json")
    def resign():
        target.write_text(json.dumps(
            record,sort_keys=True,ensure_ascii=False,separators=(",",":")))
        target.chmod(0o600)
        for role in roles:
            sig=rights/(jid+"."+role+".sig")
            crypto("pkeyutl","-sign","-inkey",private[role],"-rawin",
                   "-in",target,"-out",sig)
            sig.chmod(0o600)
    resign()
    flags={
        "IT_TEM_A51C_DEPLOYED_SOURCE_SHA":"a"*40,
        "IT_TEM_A51F_APPROVED_PROVIDER":"openai",
        "IT_TEM_A51F_RIGHTS_ROOT":str(rights),
        "IT_TEM_A51F_RIGHTS_TRUST_ROOT":str(trust),
        "IT_TEM_A51B_IMAGE_OWNER_PUB_SHA":trusted["image_owner"],
        "IT_TEM_A51B_PM_PUB_SHA":trusted["pm"],
    }
    for k,v in flags.items():monkeypatch.setenv(k,v)
    def check(**kw):
        return validate_signed_source_rights(
           store=store,job=job,actor=kw.get("actor","alice"),
           generation_mode=kw.get("mode","composed"),
           image_size=kw.get("ratio","4:5"),
           now=kw.get("now"))
    return locals()


def test_two_real_cryptographic_test_signatures_plus_source_bytes(
        signed):
    x=signed
    result=x["check"]()
    assert result["verified_signers"]==["image_owner","pm"]
    assert result["source_rights_scope_verified"] is True
    assert result["release_authorized"] is False
    assert result["provider_id"]=="openai"
    assert result["assets_sha256"]==_assets_hash(x["store"],x["job"])
    assert "TEST_ONLY_NOT_A_REAL_LICENSE" not in str(result)
    assert "private" not in json.dumps(result)


@pytest.mark.parametrize("violation",[
    "missing_manifest","unsigned","tampered_manifest","changed_source_sha",
    "changed_actor","changed_job","wrong_provider","wrong_scope",
    "wrong_grant","wrong_decision","wrong_policy_epoch",
    "unlicensed_document","wrong_asset_hash","wrong_image_mode",
    "wrong_ratio","changed_sku","expired","future","too_long",
    "future_created","source_file_tamper","trust_key_change",
    "swapped_signer_key","rights_document_symlink","untrusted_policy_root",
    "wrong_source_commit","wrong_job_asset_role","extra_field",
])
def test_no_owner_pm_signature_rights_bypass(
        signed,monkeypatch,violation):
    x=signed
    j=x["record"]
    path=x["target"]
    root=x["rights"]
    job=x["job"]
    when=datetime.now(timezone.utc)
    updated=True
    if violation=="missing_manifest":
        path.unlink();updated=False
    elif violation=="unsigned":
        (root/(job["job_id"]+".pm.sig")).unlink();updated=False
    elif violation=="tampered_manifest":
        path.write_text(path.read_text()+"\n ");updated=False
    elif violation=="changed_source_sha":
        j["assets_sha256"]="b"*64
    elif violation=="changed_actor":
        j["actor"]="bob"
    elif violation=="changed_job":
        j["job_id"]="0"*32
    elif violation=="wrong_provider":
        j["provider_id"]="other"
    elif violation=="wrong_scope":
        j["rights_scope"]="LOCAL_QA_ONLY"
    elif violation=="wrong_grant":
        j["grant_basis"]="SELF_DECLARED"
    elif violation=="wrong_decision":
        j["review_decision"]="PROVISIONAL"
    elif violation=="wrong_policy_epoch":
        j["policy_epoch"]="!invalid!"
    elif violation=="unlicensed_document":
        j["rights_evidence_sha256"]="c"*64
    elif violation=="wrong_asset_hash":
        j["assets_sha256"]="d"*64
    elif violation=="wrong_image_mode":
        j["generation_mode"]="freeform"
    elif violation=="wrong_ratio":
        j["image_size"]="9:16"
    elif violation=="changed_sku":
        j["product_sku"]="!invalid"
    elif violation=="expired":
        j["expires_utc"]=(when-timedelta(hours=2)).isoformat()
    elif violation=="future":
        j["valid_from_utc"]=(when+timedelta(days=1)).isoformat()
    elif violation=="too_long":
        j["expires_utc"]=(when+timedelta(days=31)).isoformat()
    elif violation=="future_created":
        j["valid_from_utc"]=(when+timedelta(minutes=1)).isoformat()
    elif violation=="source_file_tamper":
        file,_=x["store"].get_asset(job["job_id"],job["assets"][0]["asset_id"])
        file.write_bytes(b"TAMPER")
        updated=False
    elif violation=="trust_key_change":
        monkeypatch.setenv("IT_TEM_A51B_PM_PUB_SHA","f"*64);updated=False
    elif violation=="swapped_signer_key":
        sig=root/(job["job_id"]+".pm.sig")
        sig.write_bytes((root/(job["job_id"]+".image_owner.sig")).read_bytes())
        updated=False
    elif violation=="rights_document_symlink":
        original=x["license"]
        content=original.read_bytes()
        original.unlink()
        target=root/"real_license"
        target.write_bytes(content)
        target.chmod(0o600)
        original.symlink_to(target)
        updated=False
    elif violation=="untrusted_policy_root":
        monkeypatch.setenv("IT_TEM_A51F_RIGHTS_ROOT",str(x["trust"]))
        updated=False
    elif violation=="wrong_source_commit":
        monkeypatch.setenv("IT_TEM_A51C_DEPLOYED_SOURCE_SHA","b"*40)
        updated=False
    elif violation=="wrong_job_asset_role":
        job["assets"][0]["role"]="reference"
        updated=False
    elif violation=="extra_field":
        j["unknown"]="NOPE"
    if updated:x["resign"]()
    with pytest.raises((LiveGateError,RuntimeError)):
        x["check"]()


def test_rights_decision_bound_to_job_real_mode_and_ratio(signed):
    x=signed
    with pytest.raises(LiveGateError,match="A51F_RIGHTS_OWNER_PM_CONTEXT_MISMATCH"):
        x["check"](mode="freeform")
    with pytest.raises(LiveGateError,match="A51F_RIGHTS_OWNER_PM_CONTEXT_MISMATCH"):
        x["check"](ratio="9:16")
    with pytest.raises(LiveGateError,match="A51F_RIGHTS_OWNER_PM_CONTEXT_MISMATCH"):
        x["check"](actor="bob")


def test_missing_pm_or_owner_operator_configuration_denied(signed,monkeypatch):
    monkeypatch.delenv("IT_TEM_A51F_RIGHTS_ROOT")
    with pytest.raises(LiveGateError,match="A51F_RIGHTS_OPERATOR_TRUST_CONFIGURATION_MISSING"):
        signed["check"]()
