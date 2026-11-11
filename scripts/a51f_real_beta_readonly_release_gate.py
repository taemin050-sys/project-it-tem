"""A51F A-only release gate: evidence inventory and FAIL-CLOSED readiness.

No GCP access, DDL, network, writes to runtime, proxy key reading or model
calls. A C-A generated READ-ONLY probe is an observation, NOT PM authority.
Current prototype is not ready for live beta even if a forged external
"approval" JSON claims otherwise. Operator must provide exact genuine
Owner/PM approvals and a separately audited deployable runtime implementation.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess


REPO=Path(__file__).resolve().parents[1]
CONTRACT="IT_TEM_P03_A51F_REAL_BETA_READ_ONLY_RELEASE_GATE_V1"
PROBE_CONTRACT="IT_TEM_P03_A51B_GCP_A_READ_ONLY_THREE_LEDGER_PROBE_V1"
SHA40=re.compile(r"^[a-f0-9]{40}$")
UNMET=[
    "A51F_SIGNED_BETA_REAL_INGRESS_NOT_YET_AUDITED",
    "OWNER_PM_MPO_POLICY_OR_SAFE_REJECTION_NOT_FORMALLY_DECIDED",
    "ACTUAL_SAME_SKU_PHOTO_RIGHTS_AND_LABEL_MASK_NOT_SIGNED",
    "OWNER_PM_PROFILE_V3_REAL_PAID_EXECUTION_AUTHORITY_NOT_PRESENT",
    "PAID_SIX_COMBINATIONS_NOT_IMPLEMENTED_AS_SIGNED_PROFILES",
    "REAL_TAILSCALE_SERVE_SSO_TEAM_EVIDENCE_NOT_PRESENT",
    "PM_ED25519_COST_HARD_CAP_AND_EXTERNAL_ACCOUNT_LIMIT_NOT_APPROVED",
    "ACTUAL_PROVIDER_SIX_INDEPENDENT_JOBS_NOT_RUN",
    "ACTUAL_GCP_ISOLATED_ROLLBACK_AND_TEAM_UAT_NOT_PERFORMED",
]


def git(*args:str,repo:Path=REPO)->str:
    return subprocess.check_output(
        ["git","-C",str(repo),*args],text=True,
        stderr=subprocess.DEVNULL,timeout=10).strip()


def inspect(*,repo:Path,gcp_probe:Path)->dict:
    root=repo.resolve(strict=True)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("REPO_INVALID")
    source=git("rev-parse","HEAD",repo=root)
    tree=git("rev-parse","HEAD^{tree}",repo=root)
    if not SHA40.fullmatch(source) or not SHA40.fullmatch(tree):
        raise ValueError("SOURCE_SHA_INVALID")
    changed=git("status","--porcelain",repo=root)
    if gcp_probe.is_symlink() or not gcp_probe.is_file():
        raise ValueError("GCP_READONLY_EVIDENCE_MISSING_OR_SYMLINK")
    raw=gcp_probe.read_bytes()
    if len(raw)>256*1024:
        raise ValueError("GCP_PROBE_EVIDENCE_TOO_LARGE")
    try:record=json.loads(raw)
    except (UnicodeError,ValueError,TypeError):
        raise ValueError("GCP_PROBE_EVIDENCE_INVALID") from None
    if type(record) is not dict or record.get("contract")!=PROBE_CONTRACT:
        raise ValueError("GCP_PROBE_CONTRACT_INVALID")
    original=record.get("source_sha_observed")
    if type(original) is not str:
        raise ValueError("GCP_PROBE_SHA_MISSING")
    owner=record.get("ledgers",{}).get("owner_provider",{})
    if type(owner) is not dict:
        raise ValueError("GCP_LEDGER_PROBE_INVALID")
    owner_ready=(owner.get("schema")=="TABLE_PRESENT"
                 and owner.get("exists") is True)
    blocker=list(UNMET)
    if original!=source:
        blocker.insert(0,"DEPLOYED_GCP_A_SOURCE_SHA_MISMATCH")
    if not owner_ready:
        blocker.insert(1 if original!=source else 0,
                       "GCP_A_OWNER_PROVIDER_ATTEMPT_LEDGER_UNAVAILABLE")
    if changed:
        blocker.insert(0,"LOCAL_SOURCE_NOT_CLEAN")
    if not (root/"demo_staging"/"live"/"a51f_product_rights_authority.py").is_file():
        blocker.append("A51F_SOURCE_RIGHTS_CONTRACT_NOT_IN_SOURCE")
    # Real authorization requires separate signed decisions, actual GCP
    # execution + C-A validation. This diagnostic never promotes itself
    # to deployment authority on a matching HEAD/Tree alone.
    return {
        "contract":CONTRACT,
        "source_commit":source,
        "source_tree":tree,
        "local_worktree_clean":not bool(changed),
        "remote_evidence_kind":"PRIOR_C_A_READ_ONLY_SNAPSHOT_NOT_LIVE_PROOF",
        "gcp_readonly_evidence_sha256":sha256(raw).hexdigest(),
        "gcp_source_commit_observed":original,
        "source_matches_observed_gcp":original==source,
        "gcp_owner_provider_ledger_schema_present":owner_ready,
        "source_rights_verifier_implemented":
            (root/"demo_staging"/"live"/
             "a51f_product_rights_authority.py").is_file(),
        "actual_owner_pm_approval_validated":False,
        "actual_tailscale_serve_sso_validated":False,
        "actual_pm_hard_cap_approved":False,
        "actual_rights_cleared_photos_used":False,
        "real_provider_e2e_completed":0,
        "real_provider_e2e_required":6,
        "existing_a51e_local_fixture_may_be_promoted":False,
        "human_approval_gates_unmet":blocker,
        "deployment_writes_performed":False,
        "billing_calls_performed":0,
        "gcp_deployment_gate":"HOLD",
        "paid_worker_gate":"HOLD",
        "full_feature_beta_gate":"HOLD",
        "commercial_release_ready":False,
        "disposition":"RELEASE_CANDIDATE_NOT_YET_AUTHORIZED",
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--gcp-readonly-evidence",type=Path,required=True)
    parser.add_argument("--out",type=Path)
    p=parser.parse_args()
    try:
        result=inspect(repo=REPO,gcp_probe=p.gcp_readonly_evidence)
    except (OSError,ValueError,subprocess.CalledProcessError,subprocess.TimeoutExpired):
        raise SystemExit("A51F_READ_ONLY_EVIDENCE_UNAVAILABLE_OR_INVALID") from None
    report=json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+"\n"
    if p.out is None:
        print(report,end="")
    else:
        out=p.out
        if out.exists() or out.is_symlink():
            raise SystemExit("A51F_REPORT_EXISTS_REFUSE_OVERWRITE")
        if out.resolve().is_relative_to(p.gcp_readonly_evidence.parent.resolve()):
            # Audit evidence directory is C-A-owned and immutable to Track A.
            raise SystemExit("A51F_REPORT_MUST_NOT_MODIFY_C_A_SOURCE")
        out.parent.mkdir(parents=True,exist_ok=True)
        out.write_text(report)
        print("A51F_REAL_BETA_FAIL_CLOSED_READ_ONLY_GATES_CAPTURED")
        print("RELEASE_HOLD_NOT_DEPLOYED_NO_BILLING")


if __name__=="__main__":
    main()
