"""Nonbillable, read-only PM Actor alignment preflight. Not a payment approval.

Only a PM-confirmed signed Tailnet SSO session may supply --confirmed-actor.
Never infer a PM's identity from an actor name or a registry key.
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path

ROOT=Path("/home/macstudio/ittem-bp18-product-completion-20261111")
ACTOR_RE=re.compile(r"^bp18_b_[A-Za-z0-9_-]{3,40}$")


def check_actor(root: Path, actor: str) -> dict:
    if not ACTOR_RE.fullmatch(actor):
        raise ValueError("PM_ACTOR_INVALID_OR_NOT_TRACK_B")
    path=Path(root)/"config/bp18_tailnet_roles.json"
    if not path.is_file() or path.is_symlink() or path.stat().st_mode & 0o077:
        raise ValueError("SSO_ACTOR_REGISTRY_MISSING_OR_INSECURE")
    try:
        data=json.loads(path.read_text())
    except (ValueError,UnicodeError) as exc:
        raise ValueError("SSO_ACTOR_REGISTRY_INVALID") from exc
    if not isinstance(data,dict) or len(data)!=5 or data.get(actor) not in ("admin","evaluator"):
        raise ValueError("PM_CONFIRMED_ACTOR_NOT_IN_REGISTERED_SSO_USERS")
    # Deliberately does NOT authorize model usage or set Worker allowlists.
    return {"registered":True,"actor":actor,"role":data[actor],
            "paid_provider_allowed":False,"pm_identity_verified_by_script":False}


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,default=ROOT)
    parser.add_argument("--confirmed-actor",default=None)
    args=parser.parse_args(argv)
    if not args.confirmed_actor:
        print("PENDING_PM_SSO_SESSION_CONFIRMATION; NO_MODEL_CALLS",flush=True)
        return 78
    try:
        outcome=check_actor(args.root,args.confirmed_actor)
    except ValueError as exc:
        print("DENIED:"+str(exc),flush=True)
        return 78
    print(json.dumps(outcome,sort_keys=True),flush=True)
    print("REGISTERED_ACTOR_MATCH_ONLY; PAYMENT_AUTHORIZATION_STILL_PENDING",flush=True)
    return 0

if __name__=="__main__":
    sys.exit(main())
