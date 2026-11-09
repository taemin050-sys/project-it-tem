"""A3R Track A strict *read-only* source and three-ledger preflight.

NEVER deploys, initializes a SQLite DB, touches B/Live/QA or authorizes paid
workers. CLI accepts ONLY the exact operational A path. Explicit fixture_mode
exists for isolated in-process tests and is NOT exposed via the CLI.
"""
from __future__ import annotations

from contextlib import closing, contextmanager
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BRANCH = "integration/bp18-baseline-e2e-20261111"
A_RUNTIME_ROOT = Path("/home/macstudio/ittem-e2e-baseline-20261107")
LOCKS = (
    "configs/requirements-serving-gcp.lock.txt",
    "demo_staging/requirements-live-extra.txt",
    "app/package-lock.json",
    "tests/browser-harness/package-lock.json",
    "tests/image_generation/requirements.txt",
)
EVIDENCE = (
    "docs/integration/evidence/A3_20261109/A31_30x_real_process_race.log",
    "docs/integration/evidence/A3_20261109/A31_FULL_PYTHON.log",
    "docs/integration/evidence/A3_20261109/A31_LINUX_SYSCALL_30x.log",
    "docs/integration/evidence/A3_20261109/A34_FULL_PYTHON_FINAL.log",
    "docs/integration/evidence/A3_20261109/A34_C_INDEPENDENT_NEGATIVES_REPLAY.log",
    "docs/integration/evidence/A3_20261109/A34_REACT_TEST.log",
)
PROTECTED = frozenset((
    "ittem-bp18-product-completion-20261111",
    "ittem-bp17-final-qa-20261107",
    "ittem-bp17-shared-history-qa-20261107",
))
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_GIT_SHA = re.compile(r"[0-9a-f]{40}\Z")

# Canonical states from live/queue.py, live_safety.py and
# src/image_generation/provider_attempts.py. Unknown states NEVER imply green.
LEDGERS = {
    "queue": {
        "path": ("runtime", "live", "queue.sqlite"),
        "table": "queued_ops", "state": "state",
        "fields": {"id": "TEXT", "actor": "TEXT", "job_id": "TEXT",
                   "stage": "TEXT", "context_sha": "TEXT", "state": "TEXT",
                   "mode": "TEXT"},
        "states": frozenset(("QUEUED", "RUNNING", "SUCCEEDED", "BILLING_UNKNOWN")),
        "unsafe": frozenset(("RUNNING", "BILLING_UNKNOWN")),
    },
    "cost": {
        "path": ("runtime", "live", "cost.sqlite"),
        "table": "attempts", "state": "status",
        "fields": {"id": "TEXT", "actor": "TEXT", "job_id": "TEXT",
                   "stage": "TEXT", "payload_hash": "TEXT",
                   "status": "TEXT", "billing_unknown": "INTEGER",
                   "reserved_microusd": "INTEGER", "receipt": "TEXT"},
        "states": frozenset(("RESERVED", "DISPATCHED", "BILLING_UNKNOWN",
                             "SUCCEEDED_USAGE_UNPRICED", "SUCCEEDED")),
        "unsafe": frozenset(("RESERVED", "DISPATCHED", "BILLING_UNKNOWN")),
    },
    "image": {
        "path": ("runtime", "live", "owner_image", "image_attempts.sqlite"),
        "table": "provider_attempts", "state": "state",
        "fields": {"job_id": "TEXT", "project_id": "TEXT", "request_hash": "TEXT",
                   "attempt_id": "TEXT", "state": "TEXT",
                   "reservation_units": "INTEGER", "result_json": "TEXT",
                   "usage_json": "TEXT", "provider_request_id": "TEXT"},
        "states": frozenset(("submitting", "succeeded", "failed", "unknown")),
        "unsafe": frozenset(("submitting", "failed", "unknown")),
    },
}
_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | getattr(os, "O_NONBLOCK", 0)


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(("git", "-C", str(ROOT), *args),
                                   stderr=subprocess.DEVNULL, text=True).strip()


def _committed_bytes(rel: str) -> bytes:
    """Git blob is source authority, not just matching 64-character hashes."""
    return subprocess.check_output(
        ("git", "-C", str(ROOT), "cat-file", "blob", "HEAD:" + rel),
        stderr=subprocess.DEVNULL,
    )


def _verified_tracked_files(paths: tuple[str, ...]) -> tuple[dict, bool]:
    values = {}
    good = True
    for rel in paths:
        f = ROOT / rel
        try:
            if f.is_symlink() or not f.is_file():
                raise ValueError("REQUIRED_FILE_MISSING_OR_SYMLINK")
            data = f.read_bytes()
            found = digest_bytes(data)
            # Missing, forged or unstaged evidence cannot become an accepted
            # source manifest even if Git happens to report CLEAN.
            if not _SHA.fullmatch(found) or _committed_bytes(rel) != data:
                raise ValueError("SOURCE_GIT_BLOB_MISMATCH")
            values[rel] = found
        except (OSError, ValueError, subprocess.CalledProcessError):
            values[rel] = None
            good = False
    return values, good


def source_manifest() -> dict:
    """Read-only, commit-bound; clean tree is necessary but not sufficient."""
    branch = git("branch", "--show-current")
    head = git("rev-parse", "HEAD")
    tree = git("rev-parse", "HEAD^{tree}")
    dirty = bool(git("status", "--porcelain"))
    locks, locks_ok = _verified_tracked_files(LOCKS)
    evidence, evidence_ok = _verified_tracked_files(EVIDENCE)
    valid = (branch == BRANCH and not dirty and locks_ok and evidence_ok
             and bool(_GIT_SHA.fullmatch(head)) and bool(_GIT_SHA.fullmatch(tree))
             and git("rev-parse", "HEAD^{tree}") == tree)
    return {
        "contract": "IT_TEM_P03_A3R_A_ONLY_GUARDED_MANIFEST_V2",
        "track": "A_OWNER_SOURCE_FIRST", "branch": branch,
        "commit": head, "tree": tree,
        "worktree_clean": not dirty,
        "source_integrity_gate": "PASS" if valid else "HOLD",
        "source_gate": "PASS" if valid else "HOLD",
        "lock_integrity_gate": "PASS" if locks_ok else "HOLD",
        "evidence_integrity_gate": "PASS" if evidence_ok else "HOLD",
        "locks_sha256": locks, "test_evidence_sha256": evidence,
        "python": sys.version.split()[0],
        "serving_schema_contract": {
            "approval_policy_table": "live_copy_policy_bindings",
            "prompt_cas_table": "live_prompt_context_bindings",
            "immutable_prompt_checkpoint_table": "text_revision_checkpoints",
            "migration_permission": "SEPARATE_APPROVAL_REQUIRED",
            "legacy_live_approval_without_policy": "HOLD_FOR_REVIEW",
        },
        "policy_priority": ["FE_PR26", "TEXT_PR27", "IMAGE_PR24"],
        "image_contract": {"modes": ["composed", "freeform"],
                           "ratios": ["3:4", "4:5", "9:16"],
                           "candidates_per_request": 1,
                           "batch_allowed": False},
        "qa_deployment_readiness_gate": "HOLD",
        "paid_worker_authorization_gate": "HOLD",
        "live_provider_post_authorized": False,
        "gcp_qa_deployed": False,
        "acceptance": {
            "A2_C_AUDIT": "C_A2_SAFETY_CODE_ACCEPTED_WITH_KNOWN_TEST_NOTE",
            "GCP_A_SHA_SSO": "NOT_AUDITED",
            "PROVIDER_COST_INVOICE": "NOT_AUDITED",
            "REAL_PROVIDER_E2E": "NOT_AUDITED",
            "PAID_WORKER": "HOLD", "RELEASE": "HOLD",
        },
    }


def _fd_identity(fd: int) -> tuple[int, int]:
    info = os.fstat(fd)
    return info.st_dev, info.st_ino


@contextmanager
def _root_directory(path: Path):
    """Open each exact ancestor through dir_fd/O_NOFOLLOW, no resolved escapes.

    The root descriptor is pinned against ancestor changes. A race during a
    path swap can at worst turn an otherwise read-only result into HOLD; the
    subsequent ledger traversal never follows the changed pathname.
    """
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("NOT_A_TRACK_RUNTIME_ROOT")
    chain = []
    try:
        current = os.open("/", _DIR_FLAGS)
        chain.append(("/", current))
        for component in path.parts[1:]:
            if component in ("", ".", "..") or component in PROTECTED:
                raise ValueError("NOT_A_TRACK_RUNTIME_ROOT")
            current = os.open(component, _DIR_FLAGS, dir_fd=current)
            chain.append((component, current))
        yield current
    finally:
        for _, fd in reversed(chain):
            os.close(fd)


@contextmanager
def _relative_directory(root_fd: int, names: tuple[str, ...]):
    """Every step must be a real directory; no intermediate symbolic links."""
    fds = []
    current = root_fd
    try:
        for name in names:
            if name in ("", ".", "..") or "/" in name or name in PROTECTED:
                raise ValueError("UNSAFE_DIRECTORY_COMPONENT")
            current = os.open(name, _DIR_FLAGS, dir_fd=current)
            fds.append(current)
        yield current
    finally:
        for fd in reversed(fds):
            os.close(fd)


def _open_regular(dir_fd: int, name: str) -> int:
    """Open a pinned, regular inode; never follow a final symlink."""
    if not name or "/" in name or name in (".", ".."):
        raise ValueError("UNSAFE_FILENAME")
    fd = os.open(name, _FILE_FLAGS, dir_fd=dir_fd)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise ValueError("NOT_REGULAR_FILE")
    return fd


def _sha_fd(fd: int) -> str:
    os.lseek(fd, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    while True:
        buf = os.read(fd, 1024 * 256)
        if not buf:
            return digest.hexdigest()
        digest.update(buf)


def _sidecars(dir_fd: int, database_name: str) -> dict:
    """Observe both SQLite sidecars without opening in write-capable mode."""
    checks = {}
    for suffix in ("-wal", "-shm"):
        name = database_name + suffix
        try:
            fd = _open_regular(dir_fd, name)
        except FileNotFoundError:
            checks[suffix] = None
        else:
            try:
                checks[suffix] = _sha_fd(fd)
            finally:
                os.close(fd)
    return checks


def _schema_contract(db: sqlite3.Connection, spec: dict) -> bool:
    """Required canonical columns/types, fail closed on drift."""
    table = spec["table"]
    rows = db.execute("PRAGMA table_info(" + table + ")").fetchall()
    actual = {row[1]: row[2].upper() for row in rows}
    return all(actual.get(key) == value for key, value in spec["fields"].items())


def _read_only_state(root_fd: int, name: str) -> dict:
    """FD-bound snapshot: never open B symlinks or create a SQLite sidecar.

    No WAL read in operational preflight: SQLite immutable mode would silently
    ignore WAL, while ordinary ro SQLite may update an existing -shm. HOLD
    active WAL/SHM and require an explicit, safely quiesced A-only snapshot.
    """
    spec = LEDGERS[name]
    result = {"gate": "HOLD", "counts": {}}
    try:
        with _relative_directory(root_fd, spec["path"][:-1]) as directory:
            basename = spec["path"][-1]
            sidecars_before = _sidecars(directory, basename)
            result["sidecars_present"] = {
                suffix: sha is not None for suffix, sha in sidecars_before.items()
            }
            parent_identity = _fd_identity(directory)
            fd = _open_regular(directory, basename)
            file_identity = _fd_identity(fd)
            try:
                before = _sha_fd(fd)
                # Never infer a PASS from an immutable read which could be
                # stale relative to WAL. No database opened in this case.
                if any(value is not None for value in sidecars_before.values()):
                    result["reason"] = "ACTIVE_WAL_SHM_REQUIRES_QUIESCED_SNAPSHOT"
                else:
                    # sqlite3 uses the pinned inode via inherited /dev/fd/N.
                    # sqlite URI mode=ro, query_only and immutable=1 disallow
                    # any SQLite-created WAL/SHM files or implicit DB writes.
                    uri = "file:/dev/fd/" + str(fd) + "?mode=ro&immutable=1"
                    with closing(sqlite3.connect(uri, uri=True, timeout=3)) as db:
                        db.execute("PRAGMA query_only=ON")
                        if not _schema_contract(db, spec):
                            result["reason"] = "LEDGER_SCHEMA_MISMATCH"
                        else:
                            rows = db.execute(
                                "SELECT " + spec["state"] + ", COUNT(*) FROM "
                                + spec["table"] + " GROUP BY " + spec["state"]
                            ).fetchall()
                            states = {state: count for state, count in rows
                                      if isinstance(state, str)
                                      and state in spec["states"]
                                      and isinstance(count, int) and count >= 0}
                            if (len(states) != len(rows) or
                                    any(type(s) is not str or s not in spec["states"]
                                        for s, _ in rows)):
                                result["reason"] = "LEDGER_UNKNOWN_STATE"
                            else:
                                extra_bad = False
                                if name == "queue":
                                    other = db.execute(
                                        "SELECT COUNT(*) FROM queued_ops WHERE "
                                        "mode IS NULL OR typeof(mode)!='text' OR "
                                        "mode NOT IN ('LIVE','OFFLINE_FIXTURE') "
                                        "OR stage IS NULL OR typeof(stage)!='text' OR "
                                        "stage NOT IN ('analysis','research','copy',"
                                        "'image_prompt','image','copy_revision')"
                                    ).fetchone()[0]
                                    extra_bad = bool(other)
                                    # All states, including fixture rows, are
                                    # validated before grouping LIVE only.
                                    if not extra_bad:
                                        rows_live = db.execute(
                                            "SELECT state,COUNT(*) FROM queued_ops "
                                            "WHERE mode='LIVE' GROUP BY state"
                                        ).fetchall()
                                        states = dict(rows_live)
                                elif name == "cost":
                                    extra_bad = bool(db.execute(
                                        "SELECT COUNT(*) FROM attempts WHERE "
                                        "billing_unknown IS NULL OR "
                                        "typeof(billing_unknown)!='integer' OR "
                                        "billing_unknown NOT IN (0,1)"
                                    ).fetchone()[0])
                                if name == "cost" and not extra_bad:
                                    # A returned-but-unpriced provider call is
                                    # not a blank/zero-cost receipt. The actual
                                    # charge still requires invoice evidence.
                                    receipts = db.execute(
                                        "SELECT receipt FROM attempts "
                                        "WHERE status='SUCCEEDED_USAGE_UNPRICED'"
                                    ).fetchall()
                                    for (raw,) in receipts:
                                        try:
                                            if type(raw) is not str:
                                                raise ValueError
                                            item=json.loads(raw)
                                            if (not isinstance(item,dict) or
                                                item.get("billing_status") !=
                                                    "UNPRICED_RESERVATION_HELD" or
                                                not isinstance(item.get("provider_response_id"),str)
                                                or not item["provider_response_id"] or
                                                not isinstance(item.get("usage"),dict)):
                                                raise ValueError
                                        except (TypeError, ValueError, KeyError):
                                            extra_bad=True
                                            break
                                if name == "image" and not extra_bad:
                                    # ProviderAttemptStore.finish(succeeded)
                                    # requires the saved result; never report
                                    # a bare 'succeeded' status as reconciled.
                                    missing=db.execute(
                                        "SELECT COUNT(*) FROM provider_attempts "
                                        "WHERE state='succeeded' AND "
                                        "(result_json IS NULL OR "
                                        "typeof(result_json)!='text' OR "
                                        "length(result_json)=0)"
                                    ).fetchone()[0]
                                    extra_bad=bool(missing)
                                if extra_bad:
                                    result["reason"] = "LEDGER_INVALID_COLUMN_VALUE"
                                else:
                                    result["counts"] = states
                                    if (any(states.get(k, 0) for k in spec["unsafe"])
                                        or name == "cost" and bool(db.execute(
                                            "SELECT COUNT(*) FROM attempts "
                                            "WHERE billing_unknown!=0").fetchone()[0])):
                                        result["reason"] = "LEDGER_BILLING_UNCERTAIN"
                                    else:
                                        result["gate"] = "PASS"
                after = _sha_fd(fd)
            finally:
                os.close(fd)
            sidecars_after = _sidecars(directory, basename)
            # Detect a renamed parent, replacement DB pathname or inserted
            # symlink during inspection. Reopening ancestors uses O_NOFOLLOW,
            # so the postflight does not follow the new destination.
            try:
                with _relative_directory(root_fd, spec["path"][:-1]) as again:
                    pathname_st = os.stat(basename, dir_fd=again,
                                          follow_symlinks=False)
                    stable = (_fd_identity(again) == parent_identity and
                              (pathname_st.st_dev,pathname_st.st_ino) ==
                              file_identity and stat.S_ISREG(pathname_st.st_mode))
            except (OSError, ValueError):
                stable = False
            result["db_sha256_unchanged"] = before == after
            result["sidecars_sha256_unchanged"] = sidecars_before == sidecars_after
            result["fd_path_identity_unchanged"] = stable
            if before != after or sidecars_before != sidecars_after or not stable:
                result.update(gate="HOLD", reason="LEDGER_OR_SIDECAR_CHANGED_DURING_READ")
            return result
    except (OSError, ValueError, sqlite3.Error, UnicodeError) as error:
        result["reason"] = ("LEDGER_ACCESS_OR_SCHEMA_UNSAFE"
                            if not isinstance(error, sqlite3.Error)
                            else "LEDGER_SQLITE_UNREADABLE")
        return result


def _source_marker(root_fd: int) -> str | None:
    try:
        with _relative_directory(root_fd, ("repo",)) as directory:
            fd = _open_regular(directory, "SOURCE_SHA.txt")
            try:
                if os.fstat(fd).st_size > 128:
                    return None
                data = os.read(fd, 128).decode("ascii").strip()
                return data if _GIT_SHA.fullmatch(data) else None
            finally:
                os.close(fd)
    except (OSError, ValueError, UnicodeError):
        return None


def inspect_a_runtime(a_root: Path, *, fixture_mode: bool = False) -> dict:
    """Default: exact deployed A-only root; fixture_mode cannot be set by CLI."""
    path = Path(a_root).expanduser()
    if not fixture_mode:
        if str(path) != str(A_RUNTIME_ROOT):
            raise ValueError("NOT_A_TRACK_RUNTIME_ROOT")
    else:
        # This switch is direct Python test injection only (not a CLI option).
        # Resolve only the TEST ROOT's ordinary OS temporary parent aliases
        # (e.g. macOS /var -> /private/var), never its runtime children.
        if path.name != A_RUNTIME_ROOT.name or any(
            part in PROTECTED for part in path.parts
        ) or path.is_symlink():
            raise ValueError("NOT_A_TRACK_RUNTIME_ROOT")
        # Canonicalize ONLY the fixture parent (macOS /var alias), not the
        # A-named child directory: a root symlink can never be promoted.
        path = path.parent.resolve(strict=True) / path.name
        if (not path.is_dir() or path.is_symlink() or
                any(part in PROTECTED for part in path.parts)):
            raise ValueError("NOT_A_TRACK_RUNTIME_ROOT")
    ledgers = {name: {"gate": "HOLD", "counts": {}, "reason": "NOT_INSPECTED"}
               for name in LEDGERS}
    deployed_sha = None
    root_safety = "HOLD"
    try:
        with _root_directory(path) as fd:
            before = _fd_identity(fd)
            deployed_sha = _source_marker(fd)
            ledgers = {name: _read_only_state(fd, name) for name in LEDGERS}
            with _root_directory(path) as after_fd:
                root_safety = ("PASS" if _fd_identity(after_fd) == before
                               else "HOLD")
    except (OSError, ValueError):
        root_safety = "HOLD"
    if root_safety != "PASS":
        ledgers = {name: {"gate": "HOLD", "counts": {},
                          "reason": "A_ROOT_UNSAFE_OR_CHANGED"}
                   for name in LEDGERS}
    uncertain = [name for name, data in ledgers.items() if data["gate"] != "PASS"]
    deployed_match = ("PASS" if root_safety == "PASS" and
                      deployed_sha == git("rev-parse", "HEAD") else "HOLD")
    billing = "HOLD" if uncertain or root_safety != "PASS" else "PASS_WITH_NOTE"
    return {
        "contract": "IT_TEM_P03_A3R_READONLY_BILLING_INTEGRITY_V2",
        "runtime": "A_ONLY_TEST_FIXTURE" if fixture_mode else "A_ONLY",
        "operational_runtime_verified": bool(not fixture_mode and root_safety == "PASS"),
        "root_integrity_gate": root_safety,
        "observed_source_sha": deployed_sha,
        "expected_source_match": deployed_match,
        "ledgers": ledgers,
        "uncertainty": uncertain,
        "ledger_integrity_gate": "HOLD" if uncertain else "PASS_WITH_NOTE",
        "billing_gate": billing,
        "source_integrity_gate": source_manifest()["source_integrity_gate"],
        "signed_sso_gate": "NOT_AUDITED",
        "authorized_budget_verified": False,
        "external_provider_invoice_reconciled": False,
        "qa_deployment_readiness_gate": "HOLD",
        "deployment_preflight_gate": "HOLD",
        "paid_worker_authorization_gate": "HOLD",
        "paid_worker": "HOLD", "release": "HOLD",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path,
                        help="read-only EXACT A root: /home/macstudio/ittem-e2e-baseline-20261107")
    args = parser.parse_args()
    out = {"manifest": source_manifest()}
    if args.runtime_root is not None:
        out["a_runtime"] = inspect_a_runtime(args.runtime_root)
    print(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
