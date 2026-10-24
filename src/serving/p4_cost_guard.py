"""P4 Stage 2: provisional persistent, fail-closed reservation guard.

Internal prototype helper only. Does not authorize billable calls, invoke APIs,
price tokens/images, or reconcile provider invoices. SQLite is single-host only.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
from typing import Callable, Generic, TypeVar
from uuid import uuid4

from fastapi import HTTPException

T = TypeVar("T")
_ALLOWED_PHASES = {"research", "planning", "copy", "image"}
_JOB_ID = re.compile(r"^[a-f0-9]{32}$")
_KEY = re.compile(r"^[A-Za-z0-9_-]{8,100}$")


class ProviderTimeout(Exception):
    pass


class ProviderRateLimited(Exception):
    pass


class ProviderUnavailable(Exception):
    pass


class ProviderInvalidResponse(Exception):
    pass


@dataclass(frozen=True)
class OperationResult(Generic[T]):
    value: T
    attempt_id: str
    billing_state: str  # not_called for fake; unknown for any dispatched billable call


def fingerprint(data: dict) -> str:
    """Stable hash, never persist the prompt, product facts, or input images."""
    return sha256(json.dumps(data, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode("utf-8")).hexdigest()


class P4CostGuard:
    def __init__(self, db_path: Path, *, max_budget_micro_usd: int,
                 enable_billable: bool = False):
        if max_budget_micro_usd <= 0:
            raise ValueError("Budget must be positive")
        self.db_path = Path(db_path)
        self.max_budget_micro_usd = max_budget_micro_usd
        self.enable_billable = enable_billable
        self.db_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS attempts (
                attempt_id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                phase TEXT NOT NULL,
                operation_key TEXT NOT NULL,
                request_hash TEXT NOT NULL,
                reserved_micro_usd INTEGER NOT NULL,
                status TEXT NOT NULL,
                billing_state TEXT NOT NULL,
                error_code TEXT,
                UNIQUE(job_id, phase)
            )""")
        self.db_path.chmod(0o600)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path, isolation_level=None, timeout=5)
        try:
            conn.execute("PRAGMA busy_timeout=5000")
            yield conn
        finally:
            conn.close()

    def snapshot(self) -> list[dict]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            return [dict(row) for row in conn.execute(
                "SELECT attempt_id,job_id,phase,reserved_micro_usd,status,billing_state,error_code "
                "FROM attempts ORDER BY rowid")]

    def _reserve(self, *, job_id: str, phase: str, operation_key: str,
                 request_hash: str, max_cost_micro_usd: int) -> str:
        if not _JOB_ID.fullmatch(job_id) or phase not in _ALLOWED_PHASES:
            raise ValueError("Invalid job or phase")
        if not _KEY.fullmatch(operation_key) or not re.fullmatch(r"[a-f0-9]{64}", request_hash):
            raise ValueError("Invalid operation key or fingerprint")
        if max_cost_micro_usd > 0 and not self.enable_billable:
            raise HTTPException(status_code=503, detail="P4_BILLABLE_CALLS_DISABLED")
        if max_cost_micro_usd < 0 or max_cost_micro_usd > self.max_budget_micro_usd:
            raise HTTPException(status_code=429, detail="P4_BUDGET_LIMIT")
        attempt_id = uuid4().hex
        with self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                previous = conn.execute(
                    "SELECT operation_key, request_hash FROM attempts WHERE job_id=? AND phase=?",
                    (job_id, phase)).fetchone()
                if previous:
                    error = ("OPERATION_ALREADY_RECORDED" if previous == (operation_key, request_hash)
                             else "OPERATION_CONFLICT")
                    raise HTTPException(status_code=409, detail=error)
                committed = conn.execute(
                    "SELECT COALESCE(SUM(reserved_micro_usd),0) FROM attempts").fetchone()[0]
                if committed + max_cost_micro_usd > self.max_budget_micro_usd:
                    raise HTTPException(status_code=429, detail="P4_BUDGET_LIMIT")
                conn.execute("""INSERT INTO attempts
                    (attempt_id,job_id,phase,operation_key,request_hash,
                     reserved_micro_usd,status,billing_state)
                    VALUES (?,?,?,?,?,?,?,?)""",
                    (attempt_id, job_id, phase, operation_key, request_hash,
                     max_cost_micro_usd, "reserved", "unknown" if max_cost_micro_usd else "not_called"))
                conn.execute("COMMIT")
            except BaseException:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
        return attempt_id

    def _finalize(self, attempt_id: str, *, status: str, billing_state: str,
                  error_code: str | None = None) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE attempts SET status=?, billing_state=?, error_code=? WHERE attempt_id=?",
                         (status, billing_state, error_code, attempt_id))

    def execute(self, *, job_id: str, phase: str, operation_key: str,
                request_hash: str, max_cost_micro_usd: int,
                call: Callable[[], T]) -> OperationResult[T]:
        """No automatic retry. A crash leaves 'reserved' blocking re-dispatch.

        A billable error is 'unknown', not 'no_charge'. Reconciliation is manual.
        Call only after the job status and provider feature gate are checked.
        """
        attempt_id = self._reserve(job_id=job_id, phase=phase, operation_key=operation_key,
                                   request_hash=request_hash, max_cost_micro_usd=max_cost_micro_usd)
        billing = "unknown" if max_cost_micro_usd else "not_called"
        try:
            result = call()
        except Exception as exc:
            if isinstance(exc, ProviderTimeout) or isinstance(exc, TimeoutError):
                code, http = "PROVIDER_TIMEOUT_BILLING_UNCERTAIN", 504
            elif isinstance(exc, ProviderRateLimited):
                code, http = "PROVIDER_RATE_LIMITED", 429
            elif isinstance(exc, ProviderUnavailable):
                code, http = "PROVIDER_UNAVAILABLE", 503
            else:
                code, http = "PROVIDER_FAILED_BILLING_UNCERTAIN", 502
            self._finalize(attempt_id, status="unknown" if max_cost_micro_usd else "failed_fake",
                           billing_state=billing, error_code=code)
            raise HTTPException(status_code=http, detail=code) from None
        self._finalize(attempt_id, status="succeeded", billing_state=billing)
        return OperationResult(value=result, attempt_id=attempt_id, billing_state=billing)
