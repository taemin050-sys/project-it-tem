"""Immutable Owner Text stage checkpoints, distinct from attempt receipts.

Input stages are immutable per Job. Copy revisions and image prompts are
immutable per request or approval context. A previously returned result
is reusable without another Provider attempt.
"""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from pydantic import BaseModel
from .contracts import digest, LiveGateError

_STAGES=frozenset({"vision","research","copy","image_prompt","copy_revision"})
_MODES=frozenset({"LIVE","OFFLINE_FIXTURE"})
_CONTEXT_STAGES=frozenset({"copy_revision","image_prompt"})


class LiveCheckpoints:
    def __init__(self,path:Path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        with self.db() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS text_checkpoints (
              job_id TEXT NOT NULL,actor TEXT NOT NULL,stage TEXT NOT NULL,
              context_sha TEXT NOT NULL,mode TEXT NOT NULL,
              payload_sha TEXT NOT NULL,payload_json TEXT NOT NULL,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              PRIMARY KEY(job_id,stage));
            -- Copy revisions and prompts may run repeatedly for one Job,
            -- each bound to a distinct request or approval context.
            -- Historical one-shot checkpoints are not migrated or modified.
            CREATE TABLE IF NOT EXISTS text_revision_checkpoints (
              job_id TEXT NOT NULL,actor TEXT NOT NULL,stage TEXT NOT NULL,
              context_sha TEXT NOT NULL,mode TEXT NOT NULL,
              payload_sha TEXT NOT NULL,payload_json TEXT NOT NULL,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              PRIMARY KEY(job_id,stage,context_sha)
            );
            """)

    def db(self):
        c=sqlite3.connect(self.path,timeout=20)
        c.execute("PRAGMA busy_timeout=20000")
        c.row_factory=sqlite3.Row
        return c

    def _check(self,stage,mode,context_sha):
        if (stage not in _STAGES or mode not in _MODES or
            type(context_sha) is not str or len(context_sha)!=64 or
            any(ch not in "0123456789abcdef" for ch in context_sha)):
            raise LiveGateError("CHECKPOINT_CONTRACT_INVALID")

    @staticmethod
    def _record(db,job_id,stage,context_sha):
        if stage not in _CONTEXT_STAGES:
            return db.execute("SELECT * FROM text_checkpoints WHERE job_id=? AND stage=?",
                              (job_id,stage)).fetchone()
        row=db.execute("""SELECT * FROM text_revision_checkpoints
            WHERE job_id=? AND stage=? AND context_sha=?""",
            (job_id,stage,context_sha)).fetchone()
        if row is None and stage=="image_prompt":
            # Preserve and reuse historical prompt checkpoints for their exact approval.
            row=db.execute("""SELECT * FROM text_checkpoints
                WHERE job_id=? AND stage=? AND context_sha=?""",
                (job_id,stage,context_sha)).fetchone()
        return row

    def load(self,actor,job_id,stage,context_sha,mode,model:type[BaseModel]):
        self._check(stage,mode,context_sha)
        with self.db() as db:
            row=self._record(db,job_id,stage,context_sha)
        if row is None:
            return None
        if (row["actor"]!=actor or row["context_sha"]!=context_sha
            or row["mode"]!=mode):
            raise LiveGateError("CHECKPOINT_CONTEXT_CONFLICT")
        try:
            payload=json.loads(row["payload_json"])
            if digest(payload)!=row["payload_sha"]:
                raise LiveGateError("CHECKPOINT_INTEGRITY_FAILURE")
            return model.model_validate(payload,strict=True)
        except (ValueError,TypeError):
            raise LiveGateError("CHECKPOINT_INTEGRITY_FAILURE") from None

    def commit(self,actor,job_id,stage,context_sha,mode,result:BaseModel,
               model:type[BaseModel]):
        self._check(stage,mode,context_sha)
        try:
            payload=model.model_validate(result.model_dump(mode="json"),strict=True)
            raw=payload.model_dump(mode="json")
            sha=digest(raw)
            encoded=json.dumps(raw,ensure_ascii=False,sort_keys=True,separators=(",",":"))
        except (AttributeError,TypeError,ValueError):
            raise LiveGateError("CHECKPOINT_RESULT_INVALID") from None
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            table=("text_revision_checkpoints" if stage in _CONTEXT_STAGES
                   else "text_checkpoints")
            existing=self._record(db,job_id,stage,context_sha)
            if existing:
                if (existing["actor"]!=actor or existing["context_sha"]!=context_sha
                    or existing["mode"]!=mode or existing["payload_sha"]!=sha
                    or existing["payload_json"]!=encoded):
                    raise LiveGateError("CHECKPOINT_REWRITE_DENIED")
                return payload
            db.execute(f"""INSERT INTO {table}
              (job_id,actor,stage,context_sha,mode,payload_sha,payload_json)
              VALUES (?,?,?,?,?,?,?)""",
              (job_id,actor,stage,context_sha,mode,sha,encoded))
        return payload
