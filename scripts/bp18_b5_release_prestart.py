"""BP18 B5 — fail-closed GCP release/rollback ExecStartPre guard.

No provider IO. Intended for systemd user's ExecStartPre on B ONLY.
The only production root is a fixed operator path. Test helpers operate on
temporary cloned roots via validate() and never touch real B/Live/QA.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import fcntl
import os
import re
import socket
import sqlite3
import stat
import sys
from pathlib import Path

PRODUCTION_ROOT = Path("/home/macstudio/ittem-bp18-product-completion-20261111")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
VALID_MODES = frozenset({"web", "worker"})
EXIT_DENY = 78
AUTH_CONTRACT_FILE = "config/bp18_required_auth_contract.json"
REVIEW_CONTRACT_FILE = "config/bp18_required_review_contract.json"
DUAL_CONTRACT_FILE = "config/bp18_required_dual_contract.json"
DUAL_PROTOCOL = "LIVE_DUAL_V1"
DUAL_SOURCE_MARKERS = {
    "demo_staging/live/store.py": (b"live_paid_dual_groups", b"live_dual_f09_parent"),
    "demo_staging/live/pipeline.py": (b"live_dual_candidate_receipt", b"verify_live_dual_f09"),
    "demo_staging/live/queue.py": (b"LIVE_DUAL_V1", b"dual_billing_unknown"),
    "demo_staging/live/worker.py": (b"live_dual_lease", b"reconcile_live_dual"),
    "demo_staging/live/dual_worker.py": (b"LIVE_DUAL_PROTOCOL", b"LIVE_DUAL_WORKER_RESTART_UNCERTAIN"),
    "demo_staging/live/http_api.py": (b"LIVE_DUAL", b"live_dual_access"),
    "src/image_generation/backend_adapter.py": (b"include_provider_prompt_sha",),
}
DUAL_SOURCE_FILES = tuple(DUAL_SOURCE_MARKERS)
REVIEW_SOURCE_FILES = (
    "demo_staging/live/copy_review.py",
    "demo_staging/live/pipeline.py",
    "demo_staging/live/store.py",
    "demo_staging/live/review_policy.py",
)
REVIEW_SOURCE_MARKERS = {
    "demo_staging/live/copy_review.py": (b"def request_review(", b"def complete_report("),
    "demo_staging/live/pipeline.py": (b"copy_review", b"require_live_actor"),
    "demo_staging/live/store.py": (b"LLM_REVIEW_REQUIRED",),
    "demo_staging/live/review_policy.py": (b"IT_TEM_BP18_F09_REQUIRED", b"llm_model"),
}
SSO_SOURCE_FILES = (
    "demo_staging/app.py",
    "demo_staging/tailnet_assertion.py",
    "scripts/tailnet_sso_gateway.py",
    "app/src/demo/DemoGate.tsx",
)
SSO_SOURCE_MARKERS = {
    "demo_staging/app.py": (b"IT_TEM_TAILNET_SSO_ONLY", b"TAILNET_SSO_ONLY_HOST_NOT_PINNED"),
    "demo_staging/tailnet_assertion.py": (b"TAILNET_ASSERTION_HOST_MISMATCH",),
    "scripts/tailnet_sso_gateway.py": (b"TAILNET_EXPECTED_HOST",),
    "app/src/demo/DemoGate.tsx": (b"VITE_IT_TEM_SSO_ONLY",),
}


class ReleaseUnsafe(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _regular(path: Path, *, trusted: bool = False) -> Path:
    if not path.is_file() or path.is_symlink():
        raise ReleaseUnsafe("RELEASE_METADATA_INVALID")
    if trusted and (path.stat().st_mode & (stat.S_IWGRP | stat.S_IWOTH)):
        raise ReleaseUnsafe("RELEASE_METADATA_PERMISSIONS_INVALID")
    return path


def _epoch(root: Path) -> int:
    db = _regular(root / "runtime/live/live.sqlite")
    try:
        with sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=2) as cx:
            cx.execute("PRAGMA query_only=ON")
            tables = {r[0] for r in cx.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            if "live_policy_activation" not in tables:
                return 0
            rows = cx.execute("SELECT epoch,policy_version,policy_sha "
                              "FROM live_policy_activation WHERE singleton=1").fetchall()
            if len(rows) != 1 or type(rows[0][0]) is not int or rows[0][0] <= 0:
                raise ReleaseUnsafe("POLICY_EPOCH_LEDGER_INVALID")
            if not re.fullmatch(r"[0-9a-f]{64}", rows[0][2]):
                raise ReleaseUnsafe("POLICY_EPOCH_SHA_INVALID")
            return rows[0][0]
    except (sqlite3.DatabaseError, OSError) as exc:
        raise ReleaseUnsafe("POLICY_DB_READ_FAILED") from exc


def _required_sso_auth_contract(root: Path, target: str,
                                *, mode: str, port: int) -> str | None:
    # This is a protected *runtime operator* contract, not a flag in a
    # candidate release. In production its absence is a hard stop.
    path=root/AUTH_CONTRACT_FILE
    required = root == PRODUCTION_ROOT or path.exists()
    if not required:
        return None
    try:
        doc=json.loads(_regular(path, trusted=True).read_text(encoding="utf8"))
    except (OSError, ValueError, UnicodeError, ReleaseUnsafe) as exc:
        raise ReleaseUnsafe("SSO_REQUIRED_AUTH_CONTRACT_INVALID") from exc
    if (not isinstance(doc,dict) or set(doc)!={"version","required_mode",
           "expected_host","verified_sources"} or
        doc["version"]!=1 or doc["required_mode"]!="TAILNET_SSO_ONLY" or
        doc["expected_host"]!="macstudio-macstudio.tail17dfff.ts.net:10500" or
        not isinstance(doc["verified_sources"],dict)):
        raise ReleaseUnsafe("SSO_REQUIRED_AUTH_CONTRACT_INVALID")
    verified=doc["verified_sources"].get(target)
    # Policy Epoch compatibility is NOT enough: this release must also
    # be approved for the mandatory SSO-only identity contract.
    if not isinstance(verified,dict) or set(verified)!=set(SSO_SOURCE_FILES):
        raise ReleaseUnsafe("SSO_INCOMPATIBLE_RELEASE_DENIED")
    source_dir=root/"releases"/target
    for name in SSO_SOURCE_FILES:
        digest=verified[name]
        if not isinstance(digest,str) or not re.fullmatch(r"[0-9a-f]{64}",digest):
            raise ReleaseUnsafe("SSO_AUTH_SOURCE_PROVENANCE_INVALID")
        source=_regular(source_dir/name)
        actual=source.read_bytes()
        if hashlib.sha256(actual).hexdigest()!=digest:
            raise ReleaseUnsafe("SSO_AUTH_SOURCE_PROVENANCE_INVALID")
        if any(marker not in actual for marker in SSO_SOURCE_MARKERS[name]):
            raise ReleaseUnsafe("SSO_REQUIRED_AUTH_CODE_MISSING")
    # ExecStartPre receives the service unit Environment; verify that the
    # verified source is actually started with required SSO enforcement.
    # Control prechecks use port=0 while the current service is running;
    # systemd startup uses the effective listener port 18100.
    if mode=="web" and port==18100:
        if (os.environ.get("IT_TEM_TAILNET_AUTH_ENABLED")!="YES" or
            os.environ.get("IT_TEM_TAILNET_SSO_ONLY")!="YES" or
            os.environ.get("IT_TEM_TAILNET_EXPECTED_HOST")!=doc["expected_host"]):
            raise ReleaseUnsafe("SSO_REQUIRED_RUNTIME_ENV_MISMATCH")
    return doc["required_mode"]


def review_contract_required(root: Path) -> bool:
    if (root / REVIEW_CONTRACT_FILE).exists():
        return True
    db = root / "runtime/live/live.sqlite"
    if not db.exists():
        return False
    try:
        with sqlite3.connect(_regular(db).resolve().as_uri() + "?mode=ro",
                             uri=True, timeout=2) as cx:
            cx.execute("PRAGMA query_only=ON")
            table = cx.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                               "AND name='live_policy_activation'").fetchone()
            if not table:
                return False
            rows = cx.execute("SELECT policy_version FROM live_policy_activation "
                              "WHERE singleton=1").fetchall()
            if len(rows) != 1:
                raise ReleaseUnsafe("POLICY_EPOCH_LEDGER_INVALID")
            return str(rows[0][0]).startswith("bp18-f09-")
    except (sqlite3.DatabaseError, OSError) as exc:
        raise ReleaseUnsafe("POLICY_DB_READ_FAILED") from exc


def required_review_contract(root: Path, target: str) -> dict | None:
    """An activated two-stage policy requires exact reviewed release sources."""
    if not review_contract_required(root):
        return None
    try:
        doc = json.loads(_regular(root / REVIEW_CONTRACT_FILE, trusted=True).read_text())
    except (OSError, ValueError, UnicodeError, ReleaseUnsafe) as exc:
        raise ReleaseUnsafe("LLM_REQUIRED_REVIEW_CONTRACT_INVALID") from exc
    if (not isinstance(doc, dict) or set(doc) !=
            {"version", "required_mode", "model", "verified_sources"} or
            doc["version"] != 1 or doc["required_mode"] != "RULES_AND_LLM" or
            not isinstance(doc["model"], str) or
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", doc["model"]) or
            not isinstance(doc["verified_sources"], dict)):
        raise ReleaseUnsafe("LLM_REQUIRED_REVIEW_CONTRACT_INVALID")
    verified = doc["verified_sources"].get(target)
    if not isinstance(verified, dict) or set(verified) != set(REVIEW_SOURCE_FILES):
        raise ReleaseUnsafe("LLM_INCOMPATIBLE_RELEASE_DENIED")
    for name in REVIEW_SOURCE_FILES:
        expected = verified[name]
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ReleaseUnsafe("LLM_REVIEW_SOURCE_PROVENANCE_INVALID")
        try:
            actual = _regular(root / "releases" / target / name).read_bytes()
        except (OSError, ReleaseUnsafe) as exc:
            raise ReleaseUnsafe("LLM_REVIEW_SOURCE_PROVENANCE_INVALID") from exc
        if hashlib.sha256(actual).hexdigest() != expected:
            raise ReleaseUnsafe("LLM_REVIEW_SOURCE_PROVENANCE_INVALID")
        if any(marker not in actual for marker in REVIEW_SOURCE_MARKERS[name]):
            raise ReleaseUnsafe("LLM_REQUIRED_REVIEW_CODE_MISSING")
    return doc


def _dual_history(root: Path) -> bool:
    """Pending work and historical outputs both require a compatible reader."""
    for filename, table, condition, parameters in (
        ("live.sqlite", "live_paid_dual_groups", "", ()),
        ("queue.sqlite", "queued_ops", " WHERE mode=?", (DUAL_PROTOCOL,)),
    ):
        database = root / "runtime/live" / filename
        if not database.exists():
            continue
        try:
            with sqlite3.connect(_regular(database).resolve().as_uri() + "?mode=ro",
                                 uri=True, timeout=2) as connection:
                connection.execute("PRAGMA query_only=ON")
                if not connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
                ).fetchone():
                    continue
                # Original pre-Dual test/legacy queue schemas may have only state.
                columns = {row[1] for row in connection.execute("PRAGMA table_info(queued_ops)")}
                if table == "queued_ops" and "mode" not in columns:
                    continue
                if connection.execute(
                    "SELECT 1 FROM " + table + condition + " LIMIT 1", parameters
                ).fetchone():
                    return True
        except (sqlite3.DatabaseError, OSError) as error:
            raise ReleaseUnsafe("LIVE_DUAL_HISTORY_UNREADABLE") from error
    return False


def required_dual_contract(root: Path, target: str, *, activating: bool = False) -> dict | None:
    """Pin both the executor and historical-result reader before release swap."""
    path = root / DUAL_CONTRACT_FILE
    if not activating and not path.exists() and not _dual_history(root):
        return None
    try:
        document = json.loads(_regular(path, trusted=True).read_text())
    except (OSError, ValueError, UnicodeError, ReleaseUnsafe) as error:
        raise ReleaseUnsafe("LIVE_DUAL_REQUIRED_CONTRACT_INVALID") from error
    if (not isinstance(document, dict) or set(document) !=
            {"version", "required_mode", "verified_sources"} or
            document["version"] != 1 or document["required_mode"] != DUAL_PROTOCOL or
            not isinstance(document["verified_sources"], dict)):
        raise ReleaseUnsafe("LIVE_DUAL_REQUIRED_CONTRACT_INVALID")
    verified = document["verified_sources"].get(target)
    if not isinstance(verified, dict) or set(verified) != set(DUAL_SOURCE_FILES):
        raise ReleaseUnsafe("LIVE_DUAL_INCOMPATIBLE_RELEASE_DENIED")
    for name in DUAL_SOURCE_FILES:
        expected = verified[name]
        try:
            source = _regular(root / "releases" / target / name).read_bytes()
        except (OSError, ReleaseUnsafe) as error:
            raise ReleaseUnsafe("LIVE_DUAL_SOURCE_PROVENANCE_INVALID") from error
        if (not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected) or
                hashlib.sha256(source).hexdigest() != expected):
            raise ReleaseUnsafe("LIVE_DUAL_SOURCE_PROVENANCE_INVALID")
        if any(marker not in source for marker in DUAL_SOURCE_MARKERS[name]):
            raise ReleaseUnsafe("LIVE_DUAL_REQUIRED_PROTOCOL_CODE_MISSING")
    return document


def _queue_running(root: Path) -> bool:
    db = _regular(root / "runtime/live/queue.sqlite")
    try:
        with sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=2) as cx:
            cx.execute("PRAGMA query_only=ON")
            return cx.execute("SELECT COUNT(*) FROM queued_ops WHERE state='RUNNING'"
                              ).fetchone()[0] != 0
    except (sqlite3.DatabaseError, OSError) as exc:
        raise ReleaseUnsafe("QUEUE_DB_READ_FAILED") from exc


def _worker_lock_busy(root: Path) -> bool:
    lock = root / "runtime/live/worker.lock"
    if not lock.exists():
        return False
    _regular(lock)
    fd = os.open(lock, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, PermissionError):
            return True
        else:
            fcntl.flock(fd, fcntl.LOCK_UN)
            return False
    finally:
        os.close(fd)


def _port_busy(port: int) -> bool:
    if port <= 0:
        return False
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=.25):
            return True
    except (ConnectionRefusedError, TimeoutError, OSError):
        return False


def validate(root: Path, *, mode: str, port: int = 18100,
             target_override: str | None = None) -> dict:
    root = Path(root)
    if mode not in VALID_MODES:
        raise ReleaseUnsafe("INVALID_START_MODE")
    if root.is_symlink() or not root.is_dir():
        raise ReleaseUnsafe("RELEASE_ROOT_INVALID")
    repo = root / "repo"
    if not repo.is_symlink():
        raise ReleaseUnsafe("RELEASE_SYMLINK_MISSING")
    target_name = os.readlink(repo)
    if not re.fullmatch(r"releases/[0-9a-f]{40}", target_name):
        raise ReleaseUnsafe("RELEASE_SYMLINK_OUTSIDE_ROOT")
    current = target_name.split("/")[1]
    if target_override is not None:
        if not SHA_RE.fullmatch(target_override):
            raise ReleaseUnsafe("RELEASE_TARGET_INVALID")
        target = target_override
        target_name = "releases/" + target
    else:
        target = current
    saved = _regular(root / target_name / "SOURCE_SHA.txt")
    if saved.read_text().strip() != target:
        raise ReleaseUnsafe("RELEASE_SHA_MISMATCH")
    _regular(root / target_name / "demo_staging/live/store.py")
    trusted = _regular(root / "config/epoch_capable_shas.txt", trusted=True)
    listed = [x.strip() for x in trusted.read_text().splitlines()
              if x.strip() and not x.startswith("#")]
    if not listed or any(not SHA_RE.fullmatch(x) for x in listed):
        raise ReleaseUnsafe("TRUSTED_RELEASE_ALLOWLIST_INVALID")
    epoch = _epoch(root)
    if epoch > 0 and target not in listed:
        raise ReleaseUnsafe("OLD_RELEASE_CANNOT_START_WITH_EPOCH_DB")
    required_auth=_required_sso_auth_contract(root,target,mode=mode,port=port)
    review_contract=required_review_contract(root,target)
    dual_contract=required_dual_contract(root,target)
    if _worker_lock_busy(root):
        raise ReleaseUnsafe("ACTIVE_PROVIDER_WORKER_BLOCKS_RELEASE")
    if _queue_running(root):
        raise ReleaseUnsafe("QUEUED_RUNNING_ATTEMPT_UNRESOLVED")
    if mode == "web" and _port_busy(port):
        raise ReleaseUnsafe("WEB_PORT_ALREADY_OCCUPIED")
    if mode == "worker" and epoch == 0:
        raise ReleaseUnsafe("WORKER_REQUIRES_INITIALIZED_EPOCH")
    return {"release": target, "policy_epoch": epoch, "mode": mode,
            "required_auth": required_auth,
            "required_review": review_contract["required_mode"] if review_contract else None,
            "required_dual": dual_contract["required_mode"] if dual_contract else None,
            "worker_lock": "FREE", "queue_running": 0}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=sorted(VALID_MODES), required=True)
    parser.add_argument("--port", type=int, default=18100)
    # Operator prechecks the candidate before stopping the running release.
    # ExecStartPre intentionally omits --target and verifies the live symlink.
    parser.add_argument("--target", default=None)
    args = parser.parse_args()
    try:
        result = validate(PRODUCTION_ROOT, mode=args.mode, port=args.port,
                          target_override=args.target)
    except ReleaseUnsafe as exc:
        print("BP18_RELEASE_PRESTART_DENIED:" + exc.code, flush=True)
        return EXIT_DENY
    print("BP18_RELEASE_PRESTART_PASS release=" + result["release"] +
          " epoch=" + str(result["policy_epoch"]) + " mode=" + args.mode, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
