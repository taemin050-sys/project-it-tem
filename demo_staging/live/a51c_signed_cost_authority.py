"""A51C: separately signed PM-only hard-cap authority for an *isolated* Beta.

This is a guarded implementation, NOT an approval/entitlement:
- no supplied real PM signature, real product rights or billing authorization;
- never auto-create a missing historical Owner Provider Attempt ledger;
- signed cost approval alone NEVER grants signed Image/Profile authority;
- signed A-only cost policy must be independently audited before deployment.
"""
from __future__ import annotations

from datetime import datetime,timedelta,timezone
from pathlib import Path
from hashlib import sha256
import json
import os
import re
import sqlite3

from src.image_generation.provider_attempts import money_units
from .contracts import LiveGateError
from .a51b_signed_beta_contract import _sealed_dir,_regular,_verify_signature

CONTRACT="IT_TEM_P03_A51C_SIGNED_PM_HARD_CAP_AUTHORITY_V1"
IDENT=re.compile(r"[a-zA-Z][a-zA-Z0-9_-]{2,39}\Z")
HEX=re.compile(r"[a-f0-9]{64}\Z")
GIT_HEAD=re.compile(r"[a-f0-9]{40}\Z")
REQUIRED_FIELDS={
    "contract","decision_id","deployment_scope","candidate_runtime_root",
    "source_commit","policy_epoch","approved_actors","budget_usd",
    "text_reservation_usd","image_reservation_usd","max_requests",
    "valid_from_utc","expires_utc","execution_scope",
}


def _block(msg:str):
    raise LiveGateError("A51C_HARD_CAP_"+msg)


def _date(value):
    try:
        if type(value) is not str or "T" not in value:
            _block("UTC_TIME_INVALID")
        result=datetime.fromisoformat(value.replace("Z","+00:00"))
        if result.tzinfo is None or result.utcoffset()!=timedelta(0):
            _block("UTC_TIME_INVALID")
        return result
    except (TypeError,ValueError,OverflowError) as exc:
        if isinstance(exc,LiveGateError):
            raise
        _block("UTC_TIME_INVALID")


def signed_hard_cap_policy(root:Path,*,now:datetime|None=None)->dict:
    """Check the PM's signed exact budget/actor/source, no DB or provider I/O.

    All private trust-anchor fingerprints are pinned by an A-only operator,
    not accepted from uploaded/remote job data.
    """
    if (os.environ.get("IT_TEM_A51C_HARD_CAP_ENABLE")!="YES"
        or os.environ.get("IT_TEM_LIVE_COST_POLICY")!="HARD_CAP"
        or os.environ.get("IT_TEM_TAILNET_SSO_ONLY")!="YES"
        or os.environ.get("IT_TEM_TAILNET_AUTH_ENABLED")!="YES"):
        _block("DISABLED_OR_SSO_NOT_SIGNED")
    root=Path(root)
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        _block("CANDIDATE_ROOT_INVALID")
    try:
        if root.stat().st_mode & 0o077:
            _block("CANDIDATE_ROOT_PERMISSIONS_UNSAFE")
    except OSError:
        _block("CANDIDATE_ROOT_UNAVAILABLE")
    if root.resolve()==Path(__file__).resolve().parents[2] or root.resolve().is_relative_to(
        Path(__file__).resolve().parents[2]):
        _block("RUNTIME_MUST_BE_OUTSIDE_REPO")
    try:
        policy=_sealed_dir(os.environ["IT_TEM_A51C_COST_POLICY_ROOT"])
        trust=_sealed_dir(os.environ["IT_TEM_A51C_COST_TRUST_ROOT"])
        expected=os.environ["IT_TEM_A51C_PM_COST_PUB_SHA"]
        deployed=os.environ["IT_TEM_A51C_DEPLOYED_SOURCE_SHA"]
    except KeyError:
        _block("TRUST_CONFIG_MISSING")
    if policy==trust or not HEX.fullmatch(expected) or not GIT_HEAD.fullmatch(deployed):
        _block("TRUST_OR_DEPLOYMENT_SHA_INVALID")
    pub=_regular(trust,"pm-cost.pub.pem")
    if sha256(pub.read_bytes()).hexdigest()!=expected:
        _block("TRUST_KEY_FINGERPRINT_CHANGED")
    file=_regular(policy,"spend_approval.json")
    raw=file.read_bytes()
    try:record=json.loads(raw)
    except (TypeError,ValueError,UnicodeError):
        _block("APPROVAL_JSON_INVALID")
    if type(record) is not dict or set(record)!=REQUIRED_FIELDS:
        _block("APPROVAL_SCHEMA_INVALID")
    if (record["contract"]!=CONTRACT
        or record["deployment_scope"]!="GCP_A_ISOLATED_BETA_ONLY"
        or record["execution_scope"]!="HARD_CAP_SINGLE_IMAGE_BETA"
        or record["source_commit"]!=deployed
        or record["candidate_runtime_root"]!=str(root.resolve())
        or type(record["decision_id"]) is not str
        or not IDENT.fullmatch(record["decision_id"])
        or type(record["policy_epoch"]) is not str
        or not IDENT.fullmatch(record["policy_epoch"])):
        _block("APPROVAL_SCOPE_OR_SOURCE_MISMATCH")
    actors=record["approved_actors"]
    if (type(actors) is not list or not 1<=len(actors)<=5
        or not all(type(a) is str and IDENT.fullmatch(a) for a in actors)
        or len(set(actors))!=len(actors)):
        _block("APPROVED_ACTORS_INVALID")
    actual=frozenset(x.strip() for x in
        os.environ.get("IT_TEM_LIVE_APPROVED_ACTORS","").split(",") if x.strip())
    if actual!=frozenset(actors):
        _block("ACTOR_SCOPE_CHANGED")
    if type(record["max_requests"]) is not int or not 1<=record["max_requests"]<=200:
        _block("REQUEST_LIMIT_INVALID")
    try:
        cap=money_units(record["budget_usd"],positive=True)
        text=money_units(record["text_reservation_usd"],positive=True)
        image=money_units(record["image_reservation_usd"],positive=True)
    except ValueError:
        _block("CURRENCY_INVALID")
    if (not all(type(record[k]) is str for k in
            ("budget_usd","text_reservation_usd","image_reservation_usd"))
        or cap>1000*1_000_000 or max(text,image)>cap):
        _block("UNSAFE_CAP_OR_RESERVATION")
    start=_date(record["valid_from_utc"])
    stop=_date(record["expires_utc"])
    instant=now if now is not None else datetime.now(timezone.utc)
    if (instant.tzinfo is None or instant.utcoffset()!=timedelta(0)
        or stop<start or stop-start>timedelta(days=30)
        or not start<=instant<=stop):
        _block("COST_APPROVAL_EXPIRED_OR_NOT_YET_VALID")
    _verify_signature(raw,_regular(policy,"pm-cost.sig"),pub,file)
    return {
        "approval_sha256":sha256(raw).hexdigest(),
        "policy_epoch":record["policy_epoch"],
        "source_commit":deployed,
        "approved_actors":frozenset(actors),
        "budget_usd":record["budget_usd"],
        "image_reservation_usd":record["image_reservation_usd"],
        "text_reservation_usd":record["text_reservation_usd"],
        "max_requests":record["max_requests"],
        "monitoring_only":False,
    }


def require_preinitialized_candidate_ledgers(root:Path)->None:
    """Read-only state gate before LivePipeline/Worker may write.

    At the approved new A-only path, a privileged operator must initialize
    the four stores, take snapshots, and verify SQLite schema explicitly.
    Never infer that the old app's live_image_attempts is a provider ledger.
    """
    root=Path(root)
    schemas={
        "live/live.sqlite":{"live_image_attempts"},
        "live/queue.sqlite":{"queued_ops"},
        "live/cost.sqlite":{"attempts"},
        "live/owner_image/image_attempts.sqlite":{"provider_attempts"},
    }
    for suffix,needed in schemas.items():
        file=root/suffix
        if file.is_symlink() or not file.is_file():
            _block("REQUIRED_LEDGER_NOT_INITIALIZED")
        try:
            conn=sqlite3.connect(file.as_uri()+"?mode=ro",uri=True,timeout=5)
            try:
                names={r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")}
                if not needed.issubset(names):
                    _block("REQUIRED_LEDGER_SCHEMA_MISSING")
                if suffix.endswith("image_attempts.sqlite"):
                    # A prior UNKNOWN or still SUBMITTING Provider request
                    # cannot be treated as available budget.
                    pending=conn.execute(
                      "SELECT COUNT(*) FROM provider_attempts "
                      "WHERE state IN ('submitting','unknown','failed')").fetchone()[0]
                    if pending:
                        _block("OWNER_PROVIDER_ATTEMPT_UNRECONCILED")
                if suffix.endswith("cost.sqlite"):
                    pending=conn.execute(
                      "SELECT COUNT(*) FROM attempts "
                      "WHERE status IN ('RESERVED','DISPATCHED','BILLING_UNKNOWN') "
                      "OR billing_unknown!=0").fetchone()[0]
                    if pending:
                        _block("COST_ATTEMPT_UNRECONCILED")
                if suffix.endswith("queue.sqlite"):
                    pending=conn.execute(
                      "SELECT COUNT(*) FROM queued_ops "
                      "WHERE mode='LIVE' AND state IN ('RUNNING','BILLING_UNKNOWN')"
                    ).fetchone()[0]
                    if pending:
                        _block("QUEUE_ATTEMPT_UNRECONCILED")
            finally:conn.close()
        except (OSError,sqlite3.Error):
            _block("LEDGER_READ_ONLY_PROBE_FAILED")
