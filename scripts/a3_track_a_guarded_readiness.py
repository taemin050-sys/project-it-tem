"""A3 Track A read-only build/operational readiness evidence.

No deployment, paid API, worker execution, ledger mutation, or credentials.
This tool deliberately NEVER returns a paid-worker activation PASS.
Run against A only. Output contains counts/hashes, not Actor or private Job data.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
BRANCH = "integration/bp18-baseline-e2e-20261111"
LOCKS = (
    "configs/requirements-serving-gcp.lock.txt",
    "demo_staging/requirements-live-extra.txt",
    "app/package-lock.json",
    "tests/browser-harness/package-lock.json",
    "tests/image_generation/requirements.txt",
)
PROTECTED = frozenset(("ittem-bp18-product-completion-20261111",
                       "ittem-bp17-final-qa-20261107",
                       "ittem-bp17-shared-history-qa-20261107"))


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(("git", "-C", str(ROOT), *args),
                                   stderr=subprocess.DEVNULL, text=True).strip()


def source_manifest() -> dict:
    """Git identity and dependency-lock hashes, no changes to any worktree."""
    branch = git("branch", "--show-current")
    head = git("rev-parse", "HEAD")
    tree = git("rev-parse", "HEAD^{tree}")
    dirty = bool(git("status", "--porcelain"))
    locks = {}
    for rel in LOCKS:
        path = ROOT / rel
        locks[rel] = digest_bytes(path.read_bytes()) if path.is_file() else None
    return {
        "contract": "IT_TEM_P03_A3_A_ONLY_GUARDED_MANIFEST_V1",
        "track": "A_OWNER_SOURCE_FIRST",
        "branch": branch, "commit": head, "tree": tree,
        "worktree_clean": not dirty,
        "source_gate": ("PASS" if branch == BRANCH and not dirty else "HOLD"),
        "python": sys.version.split()[0], "locks_sha256": locks,
        "serving_schema_contract": {
            "approval_policy_table": "live_copy_policy_bindings",
            "prompt_cas_table": "live_prompt_context_bindings",
            "immutable_prompt_checkpoint_table": "text_revision_checkpoints",
            "migration_permission": "SEPARATE_APPROVAL_REQUIRED",
            "legacy_live_approval_without_policy": "HOLD_FOR_REVIEW",
        },
        "test_evidence_sha256": {
            rel: digest_bytes((ROOT / rel).read_bytes()) if (ROOT / rel).is_file()
            else None
            for rel in (
                "docs/integration/evidence/A3_20261109/A31_30x_real_process_race.log",
                "docs/integration/evidence/A3_20261109/A31_FULL_PYTHON.log",
                "docs/integration/evidence/A3_20261109/A31_LINUX_SYSCALL_30x.log",
                "docs/integration/evidence/A3_20261109/A34_FULL_PYTHON_FINAL.log",
                "docs/integration/evidence/A3_20261109/A34_C_INDEPENDENT_NEGATIVES_REPLAY.log",
                "docs/integration/evidence/A3_20261109/A34_REACT_TEST.log",
            )
        },
        "live_provider_post_authorized": False,
        "gcp_qa_deployed": False,
        "policy_priority": ["FE_PR26", "TEXT_PR27", "IMAGE_PR24"],
        "image_contract": {
            "modes": ["composed", "freeform"],
            "ratios": ["3:4", "4:5", "9:16"],
            "candidates_per_request": 1,
            "batch_allowed": False
        },
        "acceptance": {
            "A2_C_AUDIT": "C_A2_SAFETY_CODE_ACCEPTED_WITH_KNOWN_TEST_NOTE",
            "GCP_A_SHA_SSO": "NOT_AUDITED",
            "PROVIDER_COST_INVOICE": "NOT_AUDITED",
            "REAL_PROVIDER_E2E": "NOT_AUDITED",
            "PAID_WORKER": "HOLD",
            "RELEASE": "HOLD",
        },
    }


def _read_only_state(db_path: Path, table: str) -> dict:
    """Read only from an EXISTING SQLite file. Never create a DB or sidecars."""
    if not db_path.is_file() or db_path.is_symlink():
        return {"gate": "NOT_AUDITED", "reason": "DB_MISSING_OR_UNSAFE"}
    try:
        uri = "file:" + quote(str(db_path.resolve(strict=True)), safe="/") + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=3)) as connection:
            connection.execute("PRAGMA query_only=ON")
            connection.execute("PRAGMA busy_timeout=3000")
            # Query projection only: no Actor, Job, receipt or private payload.
            if table == "queued_ops":
                sql = "SELECT state,COUNT(*) FROM queued_ops WHERE mode='LIVE' GROUP BY state"
            elif table == "attempts":
                sql = "SELECT status,COUNT(*) FROM attempts GROUP BY status"
            else:
                sql = "SELECT state,COUNT(*) FROM provider_attempts GROUP BY state"
            counts = dict(connection.execute(sql).fetchall())
        return {"gate": "PASS", "counts": counts}
    except (sqlite3.Error, OSError, ValueError):
        return {"gate": "HOLD", "reason": "SQLITE_UNREADABLE_OR_SCHEMA_UNKNOWN"}


def inspect_a_runtime(a_root: Path) -> dict:
    """Observational A-only audit: never connect to B, Live or historic QA."""
    a_root = Path(a_root).expanduser().resolve()
    if a_root.name != "ittem-e2e-baseline-20261107" or any(
        part in PROTECTED for part in a_root.parts
    ):
        raise ValueError("NOT_A_TRACK_RUNTIME_ROOT")
    repo_marker = a_root / "repo" / "SOURCE_SHA.txt"
    try:
        deployed_sha = repo_marker.read_text().strip() if repo_marker.is_file() else None
    except (OSError, UnicodeError):
        deployed_sha = None
    runtime = a_root / "runtime" / "live"
    queue = _read_only_state(runtime / "queue.sqlite", "queued_ops")
    cost = _read_only_state(runtime / "cost.sqlite", "attempts")
    image = _read_only_state(runtime / "owner_image" / "image_attempts.sqlite",
                             "provider_attempts")
    bad = {
        "queue": ("RUNNING", "BILLING_UNKNOWN"),
        "cost": ("RESERVED", "DISPATCHED", "BILLING_UNKNOWN"),
        "image": ("submitting", "failed", "unknown"),
    }
    ledgers = {"queue": queue, "cost": cost, "image": image}
    uncertain = [
        label for label, result in ledgers.items()
        if result["gate"] != "PASS" or
        any(result["counts"].get(state, 0) for state in bad[label])
    ]
    return {
        "contract": "IT_TEM_P03_A3_READONLY_BILLING_INTEGRITY_V1",
        "runtime": "A_ONLY", "observed_source_sha": deployed_sha,
        "expected_source_match": ("PASS" if deployed_sha == git("rev-parse", "HEAD")
                                  else "HOLD"),
        "ledgers": ledgers,
        "uncertainty": uncertain,
        "billing_gate": ("HOLD" if uncertain else "PASS_WITH_NOTE"),
        "authorized_budget_verified": False,
        "external_provider_invoice_reconciled": False,
        # Even a clean local SQLite state does NOT prove external billing or
        # current SSO security. Activation requires independent authorization.
        "paid_worker": "HOLD",
        "release": "HOLD",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path,
                        help="A-only root for optional read-only ledger inspection")
    args = parser.parse_args()
    out = {"manifest": source_manifest()}
    if args.runtime_root is not None:
        out["a_runtime"] = inspect_a_runtime(args.runtime_root)
    print(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
