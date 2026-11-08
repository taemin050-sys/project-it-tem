"""BP18 B5 — fail-closed GCP release/rollback ExecStartPre guard.

No provider IO. Intended for systemd user's ExecStartPre on B ONLY.
The only production root is a fixed operator path. Test helpers operate on
temporary cloned roots via validate() and never touch real B/Live/QA.
"""
from __future__ import annotations

import argparse
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
    if _worker_lock_busy(root):
        raise ReleaseUnsafe("ACTIVE_PROVIDER_WORKER_BLOCKS_RELEASE")
    if _queue_running(root):
        raise ReleaseUnsafe("QUEUED_RUNNING_ATTEMPT_UNRESOLVED")
    if mode == "web" and _port_busy(port):
        raise ReleaseUnsafe("WEB_PORT_ALREADY_OCCUPIED")
    if mode == "worker" and epoch == 0:
        raise ReleaseUnsafe("WORKER_REQUIRES_INITIALIZED_EPOCH")
    return {"release": target, "policy_epoch": epoch, "mode": mode,
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
