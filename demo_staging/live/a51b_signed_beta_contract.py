"""A5-1B: separately versioned, signable beta profile and offline safety gates.

This is NOT authority to deploy or charge. Only signed Owner+PM approvals may
initialize a NEW beta job. Provider calls additionally need rights/ledger
reconciliation and cost authorization (not provided by this module).
Historical v1/v2 and unsigned A5-1 development proposals stay immutable.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .a5_beta_profile_v3 import (
    build_proposal, PROFILE_OPTIONS, PRETENDARD_139_SHA, FONT_LICENSE_SHA,
)
from .contracts import LiveGateError, digest

BETA_PREFIX = "OWNER_COMPOSED_4X5_V3_SIGNED_BETA_"
BETA_VERSION = "owner-composed-4x5-v3-signed-beta1"
CONTRACT = "IT_TEM_P03_A51B_PROFILE_ACTIVATION_V1"
TRUST_CONTRACT = "IT_TEM_P03_A51B_TRUST_ANCHORS_V1"
KEYS = ("image_owner", "pm")
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", re.ASCII)
HEX = re.compile(r"[a-f0-9]{64}",re.ASCII)


def _blocked(code: str):
    raise LiveGateError("A51B_" + code)


def _sealed_dir(path: str) -> Path:
    if not isinstance(path,str) or not path or not os.path.isabs(path):
        _blocked("PRIVATE_ROOT_REQUIRED")
    root = Path(path)
    try:
        # Do not permit aliases/symlinks into mutable Git, world-readable
        # customer data, or third-party asset folders.
        if root.is_symlink() or not root.is_dir():
            _blocked("PRIVATE_ROOT_NOT_DIRECTORY")
        if root.stat().st_mode & 0o077:
            _blocked("PRIVATE_ROOT_PERMISSIONS_UNSAFE")
        if root.resolve().is_relative_to(Path(__file__).resolve().parents[2]):
            _blocked("PRIVATE_ROOT_MUST_BE_OUTSIDE_REPOSITORY")
    except OSError:
        _blocked("PRIVATE_ROOT_UNAVAILABLE")
    return root


def _regular(root: Path, name: str, max_bytes:int=128*1024) -> Path:
    if name != Path(name).name or "/" in name or "\\" in name or not name:
        _blocked("PRIVATE_FILE_NAME_INVALID")
    path=root/name
    try:
        if path.is_symlink() or not path.is_file():
            _blocked("PRIVATE_EVIDENCE_FILE_MISSING")
        if path.stat().st_mode & 0o077:
            _blocked("PRIVATE_FILE_PERMISSIONS_UNSAFE")
        if path.stat().st_size > max_bytes:
            _blocked("PRIVATE_FILE_TOO_LARGE")
    except OSError:
        _blocked("PRIVATE_EVIDENCE_FILE_UNAVAILABLE")
    return path


def _read_json(root:Path,name:str):
    try:
        return json.loads(_regular(root,name).read_text("utf8"))
    except (UnicodeError, ValueError, TypeError):
        _blocked("DECISION_JSON_INVALID")


def _verify_signature(data:bytes, signature:Path, public_key:Path,
                      decision_path:Path):
    """Ed25519 public-key validation with system OpenSSL, no private key."""
    try:
        proc=subprocess.run(
            ["openssl","pkeyutl","-verify","-pubin","-inkey",str(public_key),
             "-rawin","-sigfile",str(signature),"-in",str(decision_path)],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            timeout=10,check=False)
    except (OSError,subprocess.TimeoutExpired):
        _blocked("SIGNATURE_VERIFIER_UNAVAILABLE")
    if proc.returncode!=0:
        _blocked("SIGNATURE_INVALID")
    # An untrusted process cannot swap decision bytes between SHA calculation
    # and signature check without triggering a hard failure.
    if decision_path.read_bytes()!=data:
        _blocked("SIGNED_DECISION_CHANGED_DURING_VERIFICATION")


def _verify_trust_anchor(trust_root:Path, role:str, declared_sha:str):
    if role not in KEYS or not HEX.fullmatch(str(declared_sha)):
        _blocked("TRUST_FINGERPRINT_INVALID")
    root_key = _regular(trust_root,role+".pub.pem")
    if hashlib.sha256(root_key.read_bytes()).hexdigest()!=declared_sha:
        _blocked("TRUST_FINGERPRINT_MISMATCH")
    return root_key


def beta_profile(choice:str, epoch:str, signed_digest:str)->dict:
    if type(choice) is not str or choice not in PROFILE_OPTIONS:
        _blocked("PROFILE_CHOICE_INVALID")
    if (type(epoch) is not str or IDENTIFIER.fullmatch(epoch) is None
            or type(signed_digest) is not str or HEX.fullmatch(signed_digest) is None):
        _blocked("POLICY_EPOCH_OR_DECISION_SHA_INVALID")
    base=build_proposal(choice)
    zone=dict(base["safe_zone"])
    zone.update({
        "policy_epoch":epoch,
        "deployment_authority":"SIGNED_OWNER_PM_BETA_CONTRACT_FROZEN",
        "signed_owner_pm_decision_sha256":signed_digest,
        "profile_provenance_sha256":digest(base),
        "protection_basis":"REAL_CANDIDATE_PRODUCT_AND_LABEL_MASK_REQUIRED",
        # Activation alone does NOT establish product/brand rights, an image
        # mask or an approved USD cap; all remain additional hard gates.
        "real_provider_permitted":False,
        "real_customer_assets_permitted":False,
        "candidate_mask_verified":False,
        "rights_review_verified":False,
    })
    return {
        "profile_id":BETA_PREFIX+choice,
        "profile_version":BETA_VERSION,
        "safe_zone":zone,
        "layout":base["layout"],
    }


def verify_activation(*, choice:str, policy_root:str, trust_root:str,
                      trusted_sha:dict[str,str], now:datetime|None=None)->dict:
    """Require a separately signed canonical decision, not an editable CSV.

    Authenticated public-key fingerprints come from a *trusted operator*
    configuration external to this JSON/ZIP, not from uploaded data.
    """
    policy=_sealed_dir(policy_root)
    trust=_sealed_dir(trust_root)
    if policy==trust:
        _blocked("TRUST_AND_POLICY_CANNOT_SHARE_ROOT")
    if type(trusted_sha) is not dict or set(trusted_sha)!=set(KEYS):
        _blocked("TWO_DISTINCT_TRUST_ANCHORS_REQUIRED")
    pub={role:_verify_trust_anchor(trust,role,trusted_sha[role]) for role in KEYS}
    if trusted_sha[KEYS[0]]==trusted_sha[KEYS[1]]:
        _blocked("DISTINCT_SIGNER_KEYS_REQUIRED")
    decision_path=_regular(policy,"activation.json")
    decision_bytes=decision_path.read_bytes()
    decision=_read_json(policy,"activation.json")
    if type(decision) is not dict or set(decision)!={
        "contract","decision_id","profile_choice","policy_epoch","profile_sha256",
        "font_sha256","font_license_sha256","valid_from_utc","expires_utc",
        "deployment_scope",
    }:
        _blocked("DECISION_SCHEMA_INVALID")
    if (decision["contract"]!=CONTRACT or decision["profile_choice"]!=choice
        or type(decision["decision_id"]) is not str
        or IDENTIFIER.fullmatch(decision["decision_id"]) is None
        or decision["deployment_scope"]!="GCP_A_ISOLATED_BETA_ONLY"
        or decision["font_sha256"]!=PRETENDARD_139_SHA
        or decision["font_license_sha256"]!=FONT_LICENSE_SHA):
        _blocked("DECISION_SCOPE_OR_FONT_MISMATCH")
    epoch=decision["policy_epoch"]
    if type(epoch) is not str or IDENTIFIER.fullmatch(epoch) is None:
        _blocked("DECISION_EPOCH_INVALID")
    signed_hash=hashlib.sha256(decision_bytes).hexdigest()
    profile=beta_profile(choice,epoch,signed_hash)
    if decision["profile_sha256"]!=profile["safe_zone"]["profile_provenance_sha256"]:
        _blocked("PROFILE_DESIGN_SHA_MISMATCH")
    try:
        start=datetime.fromisoformat(decision["valid_from_utc"].replace("Z","+00:00"))
        end=datetime.fromisoformat(decision["expires_utc"].replace("Z","+00:00"))
        instant=now or datetime.now(timezone.utc)
        if (start.tzinfo is None or end.tzinfo is None
            or not start<=instant<=end or (end-start).days>90):
            _blocked("DECISION_EXPIRED_OR_NOT_YET_VALID")
    except (TypeError,ValueError,AttributeError):
        _blocked("DECISION_TIME_INVALID")
    for role,key in pub.items():
        _verify_signature(decision_bytes,_regular(policy,role+".sig"),key,
                          decision_path)
    profile["safe_zone"]["verified_decision_id"]=decision["decision_id"]
    profile["safe_zone"]["verified_owner_pm_public_key_sha256"]=trusted_sha
    profile["safe_zone"]["verified_signer_roles"]=list(KEYS)
    return profile


def validate_beta_snapshot(row,zone,layout)->str:
    """Only immutable snapshot format; no implicit promotion or rehash."""
    name=row["profile_id"]
    if type(name) is not str or not name.startswith(BETA_PREFIX):
        _blocked("NOT_BETA_PROFILE")
    choice=name[len(BETA_PREFIX):]
    try:
        expected=beta_profile(
            choice,zone["policy_epoch"],zone["signed_owner_pm_decision_sha256"])
        for k in ("verified_decision_id","verified_owner_pm_public_key_sha256",
                  "verified_signer_roles"):
            expected["safe_zone"][k]=zone[k]
        if (row["profile_version"]!=BETA_VERSION
            or zone!=expected["safe_zone"] or layout!=expected["layout"]
            or row["layout_sha"]!=digest(layout)
            or row["safe_zone_sha"]!=digest(zone)):
            _blocked("BETA_FROZEN_PROFILE_DRIFT")
    except (KeyError,TypeError,ValueError):
        _blocked("BETA_FROZEN_PROFILE_INVALID")
    return choice


def select_signed_beta(input_snapshot,*,template_profile:str)->dict|None:
    """Called at new Job creation; never toggles historical v2/v3 rows."""
    choice=os.environ.get("IT_TEM_A51B_PROFILE","").strip()
    if not choice:return None
    if choice not in PROFILE_OPTIONS:
        _blocked("PROFILE_CHOICE_INVALID")
    if (template_profile!="A" or input_snapshot.get("image_size")!="4:5"
        or input_snapshot.get("generation_mode")!="composed"):
        return None
    if os.environ.get("IT_TEM_A5_V3_BETA_PROFILE"):
        _blocked("SIGNED_AND_UNSIGNED_SELECTORS_CONFLICT")
    if os.environ.get("IT_TEM_A51B_NEW_JOB_ENABLE")!="YES":
        _blocked("SIGNED_NEW_JOB_ACTIVATION_NOT_AUTHORIZED")
    if (os.environ.get("IT_TEM_LIVE_ENABLED")=="YES"
        or os.environ.get("IT_TEM_LIVE_EXECUTION_APPROVED")=="YES"
        or os.environ.get("IT_TEM_ENABLE_BILLABLE_TEXT_CALLS")=="YES"):
        # This implementation unit has NOT yet integrated paid-worker mask and
        # rights verification. A signed profile alone cannot activate live.
        _blocked("BETA_PAID_RUNTIME_NOT_ACTIVATED")
    try:
        trust_sha={
            role:os.environ["IT_TEM_A51B_"+role.upper()+"_PUB_SHA"]
            for role in KEYS
        }
        return verify_activation(choice=choice,
            policy_root=os.environ["IT_TEM_A51B_POLICY_ROOT"],
            trust_root=os.environ["IT_TEM_A51B_TRUST_ROOT"],
            trusted_sha=trust_sha)
    except KeyError:
        _blocked("TRUST_CONFIGURATION_MISSING")

def verify_frozen_runtime_activation(template:dict)->dict:
    """Revalidate the real signature before returning Image Owner request.

    This reopens the trusted private approval record: a deleted, expired,
    rotated, or changed contract MUST block the Job, not silently restore it.
    """
    if not template or not str(template.get("profile_id","")).startswith(BETA_PREFIX):
        _blocked("ACTIVATION_UNRECOGNIZED_PROFILE")
    selected=template["profile_id"][len(BETA_PREFIX):]
    if os.environ.get("IT_TEM_A51B_NEW_JOB_ENABLE")!="YES":
        _blocked("RUNTIME_PROFILE_NOT_ENABLED")
    try:
        approved=verify_activation(choice=selected,
            policy_root=os.environ["IT_TEM_A51B_POLICY_ROOT"],
            trust_root=os.environ["IT_TEM_A51B_TRUST_ROOT"],
            trusted_sha={
                role:os.environ["IT_TEM_A51B_"+role.upper()+"_PUB_SHA"] for role in KEYS
            })
    except KeyError:
        _blocked("TRUST_CONFIGURATION_MISSING")
    if (template["profile_version"]!=approved["profile_version"]
        or template["layout_sha"]!=digest(approved["layout"])
        or template["safe_zone_sha"]!=digest(approved["safe_zone"])
        or template["safe_zone"]!=approved["safe_zone"]):
        _blocked("APPROVAL_EPOCH_OR_PROFILE_DRIFT")
    return approved

def verify_beta_composition_receipt(receipt:dict, *, plan:dict,
                                    font_sha:str, copy_json:dict)->dict:
    """Preserve proven v3 CTA/text SHA validators for signed beta proposals.

    A signed layout is NOT a rights-cleared product, human quality approval,
    or provider authorization. Those remain separate gates.
    """
    from .a5_beta_profile_v3 import (
        verify_receipt_for_v3, PROFILE_PREFIX, PROFILE_VERSION,
    )
    if not str(plan.get("profile_id","")).startswith(BETA_PREFIX):
        _blocked("INVALID_BETA_RECEIPT_PROFILE")
    choice=plan["profile_id"][len(BETA_PREFIX):]
    expected=build_proposal(choice)
    if (plan["profile_version"]!=BETA_VERSION
        or plan["layout_sha"]!=digest(expected["layout"])
        or font_sha!=PRETENDARD_139_SHA):
        _blocked("BETA_RECEIPT_CONTRACT_MISMATCH")
    checked=verify_receipt_for_v3(receipt,plan={
        "profile_id":PROFILE_PREFIX+choice,
        "profile_version":PROFILE_VERSION,
        "layout_sha":plan["layout_sha"],
    },font_sha=font_sha,copy_json=copy_json)
    verified=verify_frozen_runtime_activation(plan["frozen_profile"])
    return {
        **checked,
        "profile_id":plan["profile_id"],
        "profile_version":plan["profile_version"],
        "profile_layout_sha256":plan["layout_sha"],
        "profile_policy_epoch":verified["safe_zone"]["policy_epoch"],
        "profile_signed_decision_sha256":verified["safe_zone"]["signed_owner_pm_decision_sha256"],
        "signed_profile_authorities":["image_owner","pm"],
        "signatures_verified_for_layout_only":True,
        "verified_profile_authority_scope":"GCP_A_ISOLATED_BETA_ONLY",
        "actual_product_mask_verified":False,
        "actual_brand_label_preservation":"NOT_AUDITED",
        "actual_product_rights_authenticated":False,
        "cost_ledger_verified":False,
        "protected_region_check":False,
        "protection_evidence":"SYNTHETIC_TARGET_ONLY_REAL_PRODUCT_NOT_AUDITED",
        "paid_provider_authorized":False,
        "human_pm_visual_accepted":False,
        "beta_only":True,
        "owner_pm_signed":False,
    }
