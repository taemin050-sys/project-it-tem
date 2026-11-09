"""R4 offline, fail-closed CostGuard prototype. No provider/worker integration.

This is NOT approval to enable LIVE. No public routes or model calls.
Explicit policy and real attempt logging must be integrated after PM wire approval.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def utc():
    return datetime.now(timezone.utc).isoformat()


class LiveNotAuthorized(Exception):
    pass


class AttemptLedger:
    def __init__(self, filename: Path, *, live_enabled=False,
                 max_requests=0, budget_usd=0, monitoring_only=False):
        self.filename=Path(filename)
        self.filename.parent.mkdir(parents=True,exist_ok=True)
        self.live_enabled=bool(live_enabled)
        self.max_requests=int(max_requests)
        self.monitoring_only=bool(monitoring_only)
        self.budget_usd=int(round(float(budget_usd)*1_000_000))
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS attempts(
                id TEXT PRIMARY KEY, actor TEXT NOT NULL, job_id TEXT NOT NULL,
                stage TEXT NOT NULL, payload_hash TEXT NOT NULL,
                created_at TEXT NOT NULL, status TEXT NOT NULL,
                reserved_microusd INTEGER NOT NULL, cost_microusd INTEGER,
                receipt TEXT, billing_unknown INTEGER NOT NULL DEFAULT 0,
                UNIQUE(job_id,stage,payload_hash)
            );
            """)

    def connect(self):
        db=sqlite3.connect(str(self.filename),timeout=15)
        db.execute("PRAGMA busy_timeout=15000")
        db.row_factory=sqlite3.Row
        return db

    @staticmethod
    def digest(payload):
        data=json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":"),
                        allow_nan=False)
        return hashlib.sha256(data.encode()).hexdigest()

    def reserve(self,*,actor,role,job_id,stage,payload,estimated_usd,
                pm_authorized=False):
        if not (self.live_enabled and pm_authorized and role=="live_operator"):
            raise LiveNotAuthorized("LIVE_DISABLED_OR_ROLE_NOT_AUTHORIZED")
        if stage not in {"text","vision","research","copy","image_prompt","image",
                         "copy_revision","copy_review"} or not actor or not job_id:
            raise LiveNotAuthorized("INVALID_STAGE_OR_PRINCIPAL")
        cost=int(round(float(estimated_usd)*1_000_000))
        if self.monitoring_only:
            # Monitoring only must not require a speculative per-call USD
            # reservation. No monetary quota or user call-count quota applies.
            cost=0
        elif cost<=0 or cost>self.budget_usd:
            raise LiveNotAuthorized("INVALID_COST_OR_BUDGET")
        digest=self.digest(payload)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing=db.execute("SELECT * FROM attempts WHERE job_id=? AND stage=? AND payload_hash=?",
                                (job_id,stage,digest)).fetchone()
            if existing:
                # No auto retry even if previous state is FAILED, DISPATCHED or BILLING_UNKNOWN.
                return {"id":existing["id"],"status":existing["status"],"new":False}
            count=db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
            reserved=db.execute("SELECT COALESCE(SUM(reserved_microusd),0) FROM attempts").fetchone()[0]
            if not self.monitoring_only and (
                count>=self.max_requests or reserved+cost>self.budget_usd
            ):
                raise LiveNotAuthorized("QUOTA_OR_BUDGET_EXHAUSTED")
            attempt=uuid4().hex
            db.execute("INSERT INTO attempts VALUES(?,?,?,?,?,?,?,?,?,?,?)",(
                attempt,actor,job_id,stage,digest,utc(),"RESERVED",
                cost,None,None,0
            ))
            return {"id":attempt,"status":"RESERVED","new":True}

    def dispatch_intent(self,attempt_id):
        """Persist intent *before* I/O. A crash after this is uncertain billing."""
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old=db.execute("SELECT status FROM attempts WHERE id=?",(attempt_id,)).fetchone()
            if not old or old["status"]!="RESERVED":
                raise LiveNotAuthorized("NO_SAFE_DISPATCH_RIGHT")
            db.execute("UPDATE attempts SET status='DISPATCHED' WHERE id=?",(attempt_id,))

    def confirm(self,attempt_id,*,cost_usd,receipt):
        if not receipt or len(receipt)>200:
            raise LiveNotAuthorized("PROVIDER_RECEIPT_REQUIRED")
        cost=int(round(float(cost_usd)*1_000_000))
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old=db.execute("SELECT status,reserved_microusd FROM attempts WHERE id=?",
                           (attempt_id,)).fetchone()
            if not old or old["status"]!="DISPATCHED" or cost<0 or cost>old["reserved_microusd"]:
                raise LiveNotAuthorized("UNSAFE_CONFIRMATION")
            db.execute("UPDATE attempts SET status='SUCCEEDED',cost_microusd=?,receipt=? WHERE id=?",
                       (cost,receipt,attempt_id))

    def confirm_usage_unpriced(self,attempt_id,receipt:dict):
        """Verified provider response, but no actual dollar invoice available.

        Keep the full pre-call reservation held. Never record an estimated
        amount as actual cost or permit a duplicate POST.
        """
        if not isinstance(receipt,dict) or receipt.get("billing_status")!="UNPRICED_RESERVATION_HELD":
            raise LiveNotAuthorized("RECEIPT_MISSING_OR_INCOMPLETE")
        if not isinstance(receipt.get("provider_response_id"),str):
            raise LiveNotAuthorized("PROVIDER_RECEIPT_ID_MISSING")
        raw=json.dumps(receipt,sort_keys=True,ensure_ascii=False)
        if len(raw)>3000:
            raise LiveNotAuthorized("PROVIDER_RECEIPT_TOO_LARGE")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old=db.execute("SELECT status FROM attempts WHERE id=?",(attempt_id,)).fetchone()
            if not old or old["status"]!="DISPATCHED":
                raise LiveNotAuthorized("UNSAFE_RECEIPT_STATE")
            db.execute("""UPDATE attempts SET status='SUCCEEDED_USAGE_UNPRICED',
                 receipt=?,cost_microusd=NULL,billing_unknown=0 WHERE id=?""",
                 (raw,attempt_id))

    def mark_billing_unknown(self,attempt_id):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old=db.execute("SELECT status FROM attempts WHERE id=?",(attempt_id,)).fetchone()
            if not old or old["status"]!="DISPATCHED":
                raise LiveNotAuthorized("UNKNOWN_ONLY_AFTER_DISPATCH")
            db.execute("UPDATE attempts SET status='BILLING_UNKNOWN',billing_unknown=1 WHERE id=?",
                       (attempt_id,))

    def reconcile_crashed_dispatches(self):
        """Mark ambiguous intents for human review. NO automatic provider retries."""
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            return db.execute("""UPDATE attempts SET status='BILLING_UNKNOWN',billing_unknown=1
                 WHERE status='DISPATCHED'""").rowcount

    def inspect(self,attempt_id):
        with self.connect() as db:
            r=db.execute("SELECT * FROM attempts WHERE id=?",(attempt_id,)).fetchone()
            return dict(r) if r else None
