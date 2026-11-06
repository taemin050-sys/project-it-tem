"""SQLite single-worker queue; never automatically replay a dispatched provider stage.

The HTTP request only commits a job request. A separately launched worker
claims it. Recovery marks lost ownership as unknown; never claims a new
provider attempt on network or process uncertainty.
"""
from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

from .contracts import LiveGateError


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
            """)

    def db(self):
        db=sqlite3.connect(self.file,timeout=20)
        db.execute("PRAGMA busy_timeout=20000")
        db.row_factory=sqlite3.Row
        return db

    def enqueue(self,*,actor,job_id,stage,context_sha,mode="LIVE"):
        if (stage not in {"analysis","research","copy","image_prompt","image"}
                or mode not in {"LIVE","OFFLINE_FIXTURE"} or
                len(context_sha)!=64):
            raise LiveGateError("QUEUE_INVALID_REQUEST")
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            existing=db.execute("""SELECT * FROM queued_ops WHERE job_id=?
                AND stage=? AND context_sha=?""",(job_id,stage,context_sha)).fetchone()
            if existing:
                if existing["actor"]!=actor or existing["mode"]!=mode:
                    raise LiveGateError("QUEUE_IDENTITY_MISMATCH")
                return dict(existing),False
            task=uuid.uuid4().hex
            db.execute("""INSERT INTO queued_ops(id,actor,job_id,stage,context_sha,state,mode)
                VALUES (?,?,?,?,?,'QUEUED',?)""",
                (task,actor,job_id,stage,context_sha,mode))
            item=db.execute("SELECT * FROM queued_ops WHERE id=?",(task,)).fetchone()
            db.commit()
            return dict(item),True

    def claim(self,worker_mode="LIVE"):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            in_progress=db.execute("""SELECT 1 FROM queued_ops
                WHERE state='RUNNING' LIMIT 1""").fetchone()
            if in_progress:
                return None  # one attempt at a time across stages
            item=db.execute("""SELECT * FROM queued_ops
                WHERE state='QUEUED' AND mode=? ORDER BY created_at,id LIMIT 1""",
                (worker_mode,)).fetchone()
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

    def read(self,task_id):
        with self.db() as db:
            r=db.execute("SELECT * FROM queued_ops WHERE id=?",(task_id,)).fetchone()
            return dict(r) if r else None
