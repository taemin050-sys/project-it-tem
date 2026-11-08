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
