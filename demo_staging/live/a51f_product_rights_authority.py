"""A51F versioned source photo and brand/license review before Provider I/O.

Proposed cryptographic contract: no approvals are issued here. Only private
operator-owned signed files may assert rights. No metadata, filenames or
unsigned user upload may substitute for actual human Owner+PM authorization.
This gate is deliberately *additive* and cannot lift existing hard stops
against paid A5-1B/v2/legacy Job paths.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
import re
from pathlib import Path

from .a51b_signed_beta_contract import (
    KEYS, IDENTIFIER, HEX, _sealed_dir, _regular,
    _verify_signature, _verify_trust_anchor,
)
from .contracts import LiveGateError

CONTRACT="IT_TEM_P03_A51F_DUAL_SIGNED_SOURCE_RIGHTS_V1"
_SHA40=re.compile(r"^[0-9a-f]{40}$")
_SHA32=re.compile(r"^[0-9a-f]{32}$")
_ALLOWED_MODES=frozenset(("composed","freeform"))
_ALLOWED_RATIOS=frozenset(("3:4","4:5","9:16"))
_RIGHTS_SCOPE="OWNED_OR_LICENSED_FOR_APPROVED_PROVIDER_AD_GENERATION"
_DECISION="APPROVE_LIMITED_GCP_A_PROVIDER_TRANSFER"
_REQUIRED=frozenset((
    "contract","decision_id","deployment_scope","deployed_source_commit",
    "actor","job_id","policy_epoch","product_sku",
    "generation_mode","image_size","assets_sha256","rights_evidence_sha256",
    "rights_scope","provider_id","grant_basis","review_decision",
    "valid_from_utc","expires_utc",
))


def _deny(reason:str):
    raise LiveGateError("A51F_RIGHTS_"+reason)


def _utc(value):
    if type(value) is not str or "T" not in value:
        _deny("TIMESTAMP_INVALID")
    try:
        d=datetime.fromisoformat(value.replace("Z","+00:00"))
    except (ValueError,OverflowError,TypeError):
        _deny("TIMESTAMP_INVALID")
    if d.tzinfo is None or d.utcoffset()!=timedelta(0):
        _deny("TIMESTAMP_NOT_UTC")
    return d


def _assets_hash(store,job):
    """Hash actual authoritative B0 assets in order, not filenames or hints."""
    assets=job.get("assets")
    if type(assets) is not list or not 2<=len(assets)<=10:
        _deny("JOB_ASSET_COUNT_INVALID")
    sequence=[]
    product=0
    reference=0
    seen=set()
    for a in assets:
        if type(a) is not dict or type(a.get("asset_id")) is not str:
            _deny("ASSET_METADATA_INVALID")
        role=a.get("role")
        if role not in ("product","reference"):
            _deny("ASSET_ROLE_INVALID")
        product+=role=="product"
        reference+=role=="reference"
        identifier=a["asset_id"]
        if identifier in seen:
            _deny("ASSET_ID_DUPLICATE")
        seen.add(identifier)
        value=a.get("sha256")
        if type(value) is not str or not HEX.fullmatch(value):
            _deny("ASSET_METADATA_SHA_INVALID")
        try:
            file,record=store.get_asset(job["job_id"],identifier)
            if (record.get("role")!=role or
                record.get("sha256")!=value or file.is_symlink() or
                sha256(file.read_bytes()).hexdigest()!=value):
                _deny("ASSET_SHA_CHANGED")
        except (OSError,ValueError,KeyError,TypeError) as exc:
            if isinstance(exc,LiveGateError):raise
            _deny("ASSET_UNAVAILABLE")
        sequence.append({"role":role,"asset_id":identifier,"sha256":value})
    if not 2<=product<=5 or reference>5:
        _deny("PHOTO_COUNT_INVALID")
    return sha256(json.dumps(
        sequence,sort_keys=True,separators=(",",":")).encode()).hexdigest()


def validate_signed_source_rights(*,store,job:dict,actor:str,
                                   generation_mode:str,image_size:str,
                                   now:datetime|None=None)->dict:
    """Return audited scope only after real dual signature and source proof.

    All private roots, trust hashes, provider ID and source SHA come from
    protected operator configuration, never browser-controlled content.
    Does NOT authorize any live call by itself: worker cost/identity/state,
    queue and separate Owner profile gates remain mandatory.
    """
    jid=job.get("job_id")
    if type(jid) is not str or not _SHA32.fullmatch(jid):
        _deny("JOB_ID_INVALID")
    if type(actor) is not str or not IDENTIFIER.fullmatch(actor):
        _deny("ACTOR_INVALID")
    if generation_mode not in _ALLOWED_MODES or image_size not in _ALLOWED_RATIOS:
        _deny("OUTPUT_SCOPE_INVALID")
    try:
        source=os.environ["IT_TEM_A51C_DEPLOYED_SOURCE_SHA"]
        provider=os.environ["IT_TEM_A51F_APPROVED_PROVIDER"]
        rights=_sealed_dir(os.environ["IT_TEM_A51F_RIGHTS_ROOT"])
        trust=_sealed_dir(os.environ["IT_TEM_A51F_RIGHTS_TRUST_ROOT"])
        trusted={
            role:os.environ["IT_TEM_A51B_"+role.upper()+"_PUB_SHA"]
            for role in KEYS
        }
    except KeyError:
        _deny("OPERATOR_TRUST_CONFIGURATION_MISSING")
    if (source=="" or not _SHA40.fullmatch(source)
        or type(provider) is not str or not IDENTIFIER.fullmatch(provider)
        or rights==trust or trusted["image_owner"]==trusted["pm"]):
        _deny("OPERATOR_SCOPE_INVALID")
    public={k:_verify_trust_anchor(trust,k,trusted[k]) for k in KEYS}
    manifest=_regular(rights,jid+".source_rights.json")
    original=manifest.read_bytes()
    try:
        record=json.loads(original)
    except (UnicodeError,ValueError,TypeError):
        _deny("MANIFEST_INVALID")
    if type(record) is not dict or set(record)!=_REQUIRED:
        _deny("MANIFEST_SCHEMA_INVALID")
    if (record["contract"]!=CONTRACT or
        record["deployment_scope"]!="GCP_A_ISOLATED_BETA_ONLY" or
        record["deployed_source_commit"]!=source or
        record["actor"]!=actor or record["job_id"]!=jid or
        type(record["decision_id"]) is not str or
        not IDENTIFIER.fullmatch(record["decision_id"]) or
        type(record["policy_epoch"]) is not str or
        not IDENTIFIER.fullmatch(record["policy_epoch"]) or
        type(record["product_sku"]) is not str or
        not IDENTIFIER.fullmatch(record["product_sku"]) or
        record["generation_mode"]!=generation_mode or
        record["image_size"]!=image_size or
        record["provider_id"]!=provider or
        record["rights_scope"]!=_RIGHTS_SCOPE or
        record["review_decision"]!=_DECISION or
        record["grant_basis"] not in ("OWNED_SOURCE","DOCUMENTED_LICENSE") or
        type(record["assets_sha256"]) is not str or
        not HEX.fullmatch(record["assets_sha256"]) or
        type(record["rights_evidence_sha256"]) is not str or
        not HEX.fullmatch(record["rights_evidence_sha256"])):
        _deny("OWNER_PM_CONTEXT_MISMATCH")
    instant=now if now is not None else datetime.now(timezone.utc)
    if instant.tzinfo is None or instant.utcoffset()!=timedelta(0):
        _deny("CLOCK_INVALID")
    start=_utc(record["valid_from_utc"])
    end=_utc(record["expires_utc"])
    if not start<=instant<=end or end<start or end-start>timedelta(days=30):
        _deny("DECISION_EXPIRED_OR_FUTURE")
    actual_assets_sha=_assets_hash(store,job)
    if actual_assets_sha!=record["assets_sha256"]:
        _deny("SOURCE_ASSET_SET_CHANGED")
    evidence=_regular(rights,jid+".rights_evidence",max_bytes=2*1024*1024)
    if sha256(evidence.read_bytes()).hexdigest()!=record["rights_evidence_sha256"]:
        _deny("RIGHTS_DOCUMENT_SHA_CHANGED")
    for role,public_key in public.items():
        _verify_signature(original,
                          _regular(rights,jid+"."+role+".sig"),
                          public_key,manifest)
    return {
        "contract":CONTRACT,
        "job_id":jid,"actor":actor,"provider_id":provider,
        "decision_id":record["decision_id"],
        "decision_sha256":sha256(original).hexdigest(),
        "rights_evidence_sha256":record["rights_evidence_sha256"],
        "assets_sha256":actual_assets_sha,
        "generation_mode":generation_mode,"image_size":image_size,
        "source_commit":source,
        "verified_signers":["image_owner","pm"],
        "cryptographic_authority":"TWO_SIGNATURES_VERIFIED",
        "actual_license_merits":"HUMAN_REVIEW_NOT_INDEPENDENT_LEGAL_OPINION",
        "source_rights_scope_verified":True,
        "does_not_supersede_cost_profile_or_deployment_gates":True,
        "release_authorized":False,
    }
