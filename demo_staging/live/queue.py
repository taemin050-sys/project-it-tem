"""SQLite single-worker queue; never automatically replay a dispatched provider stage.

The HTTP request only commits a job request. A separately launched worker
claims it. Recovery marks lost ownership as unknown; never claims a new
provider attempt on network or process uncertainty.
"""
from __future__ import annotations

import sqlite3
import uuid
import json
from pathlib import Path

from .contracts import LiveGateError


LIVE_DUAL_PROTOCOL = "LIVE_DUAL_V1"
LIVE_DUAL_STAGES = frozenset({"analysis", "copy_revision", "copy_review", "image_prompt", "image"})


class LiveQueue:
    def __init__(self, file:Path):
        self.file=Path(file)
        self.file.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        with self.db() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS queued_ops (
              id TEXT PRIMARY KEY, actor TEXT NOT NULL, job_id TEXT NOT NULL,
              stage TEXT NOT NULL, context_sha TEXT NOT NULL,
              state TEXT NOT NULL, mode TEXT NOT NULL,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              started_at TEXT, ended_at TEXT, result_sha TEXT, error_code TEXT,
              UNIQUE(job_id,stage,context_sha)
            );
            CREATE INDEX IF NOT EXISTS queue_state ON queued_ops(state,created_at);
            -- Durable private text task payloads for the isolated worker.
            -- Never put them in URL, task-status or event logs.
            CREATE TABLE IF NOT EXISTS queued_revision_payloads (
              task_id TEXT PRIMARY KEY REFERENCES queued_ops(id),
              payload_json TEXT NOT NULL
            );
            """)

    def db(self):
        db=sqlite3.connect(self.file,timeout=20)
        db.execute("PRAGMA busy_timeout=20000")
        db.row_factory=sqlite3.Row
        return db

    def enqueue(self,*,actor,job_id,stage,context_sha,mode="LIVE",revision_payload=None,
                review_payload=None):
        if (stage not in {"analysis","research","copy","image_prompt","image",
                          "copy_revision","copy_review"} or
                mode not in {"LIVE","OFFLINE_FIXTURE",LIVE_DUAL_PROTOCOL} or
                (mode == LIVE_DUAL_PROTOCOL and stage not in LIVE_DUAL_STAGES) or
                type(context_sha) is not str or len(context_sha)!=64 or
                any(ch not in "0123456789abcdef" for ch in context_sha)):
            raise LiveGateError("QUEUE_INVALID_REQUEST")
        if (stage=="copy_revision") != (revision_payload is not None):
            raise LiveGateError("QUEUE_REVISION_PAYLOAD_REQUIRED")
        if (stage=="copy_review") != (review_payload is not None):
            raise LiveGateError("QUEUE_REVIEW_PAYLOAD_REQUIRED")
        raw=None
        if stage=="copy_revision":
            if (type(revision_payload) is not dict or
                set(revision_payload)!={"instruction","expected_generation","expected_review_sha"} or
                type(revision_payload["instruction"]) is not str or
                not 1<=len(revision_payload["instruction"].strip())<=300 or
                type(revision_payload["expected_generation"]) is not int or
                type(revision_payload["expected_review_sha"]) is not str):
                raise LiveGateError("QUEUE_REVISION_PAYLOAD_INVALID")
            raw=json.dumps(revision_payload,ensure_ascii=False,sort_keys=True,
                           separators=(",",":"))
        if stage=="copy_review":
            if (type(review_payload) is not dict or
                set(review_payload)!={"expected_generation","expected_review_sha"} or
                type(review_payload["expected_generation"]) is not int or
                review_payload["expected_generation"]<1 or
                type(review_payload["expected_review_sha"]) is not str or
                len(review_payload["expected_review_sha"])!=64 or
                any(ch not in "0123456789abcdef" for ch in review_payload["expected_review_sha"])):
                raise LiveGateError("QUEUE_REVIEW_PAYLOAD_INVALID")
            raw=json.dumps(review_payload,ensure_ascii=False,sort_keys=True,separators=(",",":"))
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            existing=db.execute("""SELECT * FROM queued_ops WHERE job_id=?
                AND stage=? AND context_sha=?""",(job_id,stage,context_sha)).fetchone()
            if existing:
                if existing["actor"]!=actor or existing["mode"]!=mode:
                    raise LiveGateError("QUEUE_IDENTITY_MISMATCH")
                if stage in {"copy_revision","copy_review"}:
                    previous=db.execute("""SELECT payload_json FROM queued_revision_payloads
                        WHERE task_id=?""",(existing["id"],)).fetchone()
                    if not previous or previous["payload_json"]!=raw:
                        raise LiveGateError("QUEUE_REVISION_CONTEXT_CONFLICT")
                return dict(existing),False
            if stage in {"copy_revision","copy_review"}:
                active=db.execute("""SELECT id FROM queued_ops
                    WHERE job_id=? AND stage IN ('analysis','copy_revision','copy_review') AND state IN
                    ('QUEUED','RUNNING','BILLING_UNKNOWN') LIMIT 1""",
                    (job_id,)).fetchone()
                if active:
                    raise LiveGateError("REVISION_IN_PROGRESS")
            task=uuid.uuid4().hex
            db.execute("""INSERT INTO queued_ops(id,actor,job_id,stage,context_sha,state,mode)
                VALUES (?,?,?,?,?,'QUEUED',?)""",
                (task,actor,job_id,stage,context_sha,mode))
            if stage in {"copy_revision","copy_review"}:
                db.execute("""INSERT INTO queued_revision_payloads(task_id,payload_json)
                    VALUES (?,?)""",(task,raw))
            item=db.execute("SELECT * FROM queued_ops WHERE id=?",(task,)).fetchone()
            db.commit()
            return dict(item),True

    def assert_image_retry_safe(self,actor,job_id):
        """No paid replay while any old image attempt is queued/uncertain."""
        with self.db() as c:
            rows=c.execute("""SELECT actor,state FROM queued_ops
                WHERE job_id=? AND stage='image' AND state IN
                ('QUEUED','RUNNING','BILLING_UNKNOWN')""",(job_id,)).fetchall()
        if any(row["actor"]!=actor for row in rows):
            raise LiveGateError("IMAGE_RETRY_ACTOR_CONFLICT")
        if rows:
            raise LiveGateError("IMAGE_RETRY_OUTSTANDING_OR_UNKNOWN")

    def revision_payload(self,task_id):
        return self._text_payload(task_id,"copy_revision")

    def review_payload(self,task_id):
        return self._text_payload(task_id,"copy_review")

    def _text_payload(self,task_id,stage):
        with self.db() as db:
            row=db.execute("""SELECT p.payload_json FROM queued_revision_payloads p
                JOIN queued_ops q ON q.id=p.task_id
                WHERE p.task_id=? AND q.stage=?""",
                (task_id,stage)).fetchone()
        if row is None:
            raise LiveGateError("REVISION_PAYLOAD_NOT_FOUND")
        try:
            return json.loads(row["payload_json"])
        except (ValueError,TypeError):
            raise LiveGateError("REVISION_PAYLOAD_CORRUPTED") from None

    def claim(self,worker_mode="LIVE",*,include_dual=False):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            in_progress=db.execute("""SELECT 1 FROM queued_ops
                WHERE state='RUNNING' LIMIT 1""").fetchone()
            if in_progress:
                return None  # one attempt at a time across stages
            # An unresolved Dual send survives process restart and blocks new
            # sends, including its sibling. Legacy uncertainty semantics remain.
            if self._dual_unknown(db):
                return None
            item=db.execute("""SELECT * FROM queued_ops
                WHERE state='QUEUED' AND (mode=? OR (? AND mode=?))
                ORDER BY created_at,id LIMIT 1""",
                (worker_mode,include_dual,LIVE_DUAL_PROTOCOL)).fetchone()
            if not item:
                return None
            db.execute("""UPDATE queued_ops SET state='RUNNING',
                 started_at=CURRENT_TIMESTAMP WHERE id=?""",(item["id"],))
            result=db.execute("SELECT * FROM queued_ops WHERE id=?",(item["id"],)).fetchone()
            db.commit()
            return dict(result)

    def complete(self,task_id,result_sha):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            r=db.execute("SELECT state FROM queued_ops WHERE id=?",(task_id,)).fetchone()
            if not r or r["state"]!="RUNNING":
                raise LiveGateError("QUEUE_ATTEMPT_NOT_RUNNING")
            db.execute("""UPDATE queued_ops SET state='SUCCEEDED',
                result_sha=?,ended_at=CURRENT_TIMESTAMP WHERE id=?""",
                (result_sha,task_id))

    def interrupt(self,task_id,error_code):
        # Even an apparently recoverable failure is not implicitly retried.
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            r=db.execute("SELECT state FROM queued_ops WHERE id=?",(task_id,)).fetchone()
            if not r or r["state"]!="RUNNING":
                raise LiveGateError("QUEUE_ATTEMPT_NOT_RUNNING")
            db.execute("""UPDATE queued_ops SET state='BILLING_UNKNOWN',error_code=?,
                ended_at=CURRENT_TIMESTAMP WHERE id=?""",(error_code,task_id))

    def reconcile_restart(self):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            return db.execute("""UPDATE queued_ops SET state='BILLING_UNKNOWN',
                error_code='WORKER_RESTART_UNCERTAIN',ended_at=CURRENT_TIMESTAMP
                WHERE state='RUNNING'""").rowcount

    @staticmethod
    def _dual_unknown(db):
        return db.execute("""SELECT 1 FROM queued_ops
            WHERE mode=? AND state='BILLING_UNKNOWN' LIMIT 1""",
            (LIVE_DUAL_PROTOCOL,)).fetchone() is not None

    def dual_billing_unknown(self):
        with self.db() as db:
            return self._dual_unknown(db)

    def running_dual(self):
        with self.db() as db:
            return [dict(row) for row in db.execute("""SELECT * FROM queued_ops
                WHERE mode=? AND state='RUNNING'""", (LIVE_DUAL_PROTOCOL,))]

    def fail_dual(self,task_id,error_code):
        """Terminal failure with dispatch and billing certainty; never a retry."""
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            changed=db.execute("""UPDATE queued_ops SET state='FAILED',error_code=?,
                ended_at=CURRENT_TIMESTAMP WHERE id=? AND mode=? AND state='RUNNING'""",
                (error_code,task_id,LIVE_DUAL_PROTOCOL)).rowcount
            if changed != 1:
                raise LiveGateError("QUEUE_ATTEMPT_NOT_RUNNING")

    def read(self,task_id):
        with self.db() as db:
            r=db.execute("SELECT * FROM queued_ops WHERE id=?",(task_id,)).fetchone()
            return dict(r) if r else None
