"""A51D-R1 TEST-ONLY durable MPO token CAS journal.

Independent SQLite WAL file in the isolated fixture runtime; NOT the Live,
Owner Provider Attempt, Cost, Queue or historical B0/PM approval ledger.
PREVIEWED -> CONFIRMED -> RESERVED -> COMMITTED is fail-closed. Any crash
after RESERVED must remain blocked until an operator reconciles an orphan;
it can never automatically replay a model or create a second Job.
This is not a production signed SSO/multi-worker deployment authorization.
"""
from __future__ import annotations

from contextlib import contextmanager, closing
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import time


class JournalConflict(Exception):
    """Invalid, stale, used or actor-mismatched token; never disclose identity."""


class MpoSelectionJournal:
    def __init__(self, filename: Path):
        original=Path(filename)
        if original.is_symlink():
            raise RuntimeError("MPO_JOURNAL_SYMLINK_DENIED")
        self.path=original.resolve()
        self.path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        with closing(self._connect()) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS selection_tokens(
                    token_sha256 TEXT PRIMARY KEY,
                    actor TEXT NOT NULL,
                    original_sha256 TEXT NOT NULL,
                    frame_count INTEGER NOT NULL CHECK(frame_count BETWEEN 2 AND 16),
                    previews_json TEXT NOT NULL,
                    expires_utc REAL NOT NULL,
                    state TEXT NOT NULL CHECK(state IN (
                        'PREVIEWED','CONFIRMED','RESERVED','COMMITTED','FAILED_RETRY_REQUIRED')),
                    frame_index INTEGER,
                    preview_sha256 TEXT,
                    upload_request_sha256 TEXT,
                    job_id TEXT,
                    created_utc REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS selection_token_actor_state
                  ON selection_tokens(actor,state);
            """)
        os.chmod(self.path,0o600)

    def _connect(self):
        db=sqlite3.connect(str(self.path),timeout=10)
        db.row_factory=sqlite3.Row
        db.execute("PRAGMA busy_timeout=10000")
        return db

    @contextmanager
    def _write(self):
        db=self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def digest(token:str)->str:
        return sha256(token.encode("utf-8")).hexdigest()

    def preview(self,*,token:str,actor:str,source_sha:str,frame_count:int,
                previews:dict[int,str],ttl_seconds:int,capacity:int):
        now=time.time()
        with self._write() as db:
            active=db.execute("""SELECT count(*) FROM selection_tokens
                WHERE expires_utc>? AND state IN ('PREVIEWED','CONFIRMED','RESERVED')""",
                (now,)).fetchone()[0]
            if active>=capacity:
                raise JournalConflict("PREVIEW_CAPACITY_EXHAUSTED")
            db.execute("""INSERT INTO selection_tokens(
                token_sha256,actor,original_sha256,frame_count,previews_json,
                expires_utc,state,created_utc
                ) VALUES(?,?,?,?,?,?,'PREVIEWED',?)""",
                (self.digest(token),actor,source_sha,frame_count,
                 json.dumps(previews,sort_keys=True,separators=(",",":")),
                 now+ttl_seconds,now))

    def confirm(self,*,token:str,actor:str,frame_index:int,preview_sha:str):
        digest=self.digest(token)
        now=time.time()
        with self._write() as db:
            row=db.execute("SELECT * FROM selection_tokens WHERE token_sha256=?",
                           (digest,)).fetchone()
            if (row is None or row["actor"]!=actor or
                    row["state"]!="PREVIEWED" or row["expires_utc"]<=now or
                    json.loads(row["previews_json"]).get(str(frame_index))!=preview_sha):
                raise JournalConflict("CONFIRM_CAS_DENIED")
            changed=db.execute("""UPDATE selection_tokens SET
                state='CONFIRMED',frame_index=?,preview_sha256=?
                WHERE token_sha256=? AND state='PREVIEWED'""",
                (frame_index,preview_sha,digest))
            if changed.rowcount!=1:
                raise JournalConflict("CONFIRM_CAS_DENIED")

    def inspect_confirmed(self,*,token:str,actor:str,source_sha:str,
                          frame_index:int,preview_sha:str):
        """Untrusted pre-normalization peek; NOT an allocation or CAS result."""
        with closing(self._connect()) as db:
            row=db.execute("SELECT * FROM selection_tokens WHERE token_sha256=?",
                           (self.digest(token),)).fetchone()
        if (row is None or row["state"]!="CONFIRMED" or row["actor"]!=actor or
                row["original_sha256"]!=source_sha or row["expires_utc"]<=time.time() or
                row["frame_index"]!=frame_index or row["preview_sha256"]!=preview_sha or
                json.loads(row["previews_json"]).get(str(frame_index))!=preview_sha):
            raise JournalConflict("PREVIEW_TOKEN_ACTOR_SHA_OR_FRAME_MISMATCH")
        return {"source_sha256":row["original_sha256"],
                "source_frame_count":row["frame_count"]}

    def reserve(self,*,actor:str,claims:list[dict],request_sha:str):
        """One durable CAS across ALL MPO tokens for a single upload request.

        Runs AFTER all file reads and normalization; no awaits in transaction.
        SQLite BEGIN IMMEDIATE serializes across threads and processes.
        """
        if not claims or len(set(x["token_sha256"] for x in claims))!=len(claims):
            raise JournalConflict("RESERVATION_CLAIMS_INVALID")
        now=time.time()
        with self._write() as db:
            for c in claims:
                row=db.execute("""SELECT state,actor,original_sha256,frame_count,
                    expires_utc,frame_index,preview_sha256,previews_json
                    FROM selection_tokens WHERE token_sha256=?""",
                    (c["token_sha256"],)).fetchone()
                if (row is None or row["state"]!="CONFIRMED" or
                        row["actor"]!=actor or row["expires_utc"]<=now or
                        row["original_sha256"]!=c["source_sha256"] or
                        row["frame_count"]!=c["frame_count"] or
                        row["frame_index"]!=c["frame_index"] or
                        row["preview_sha256"]!=c["preview_sha256"] or
                        json.loads(row["previews_json"]).get(str(c["frame_index"]))!=
                            c["preview_sha256"]):
                    raise JournalConflict("RESERVATION_CAS_DENIED")
            for c in claims:
                changed=db.execute("""UPDATE selection_tokens SET
                    state='RESERVED',upload_request_sha256=?
                    WHERE token_sha256=? AND state='CONFIRMED'""",
                    (request_sha,c["token_sha256"]))
                if changed.rowcount!=1:
                    raise JournalConflict("RESERVATION_CAS_DENIED")

    def settle(self,*,actor:str,claims:list[dict],request_sha:str,
               status:str,job_id:str|None=None):
        if status not in ("COMMITTED","FAILED_RETRY_REQUIRED"):
            raise ValueError("INVALID_TERMINAL_MPO_TOKEN_STATE")
        if status=="COMMITTED" and not job_id:
            raise ValueError("COMMITTED_MPO_TOKEN_REQUIRES_JOB")
        with self._write() as db:
            for c in claims:
                row=db.execute("""SELECT state,actor,upload_request_sha256
                    FROM selection_tokens WHERE token_sha256=?""",
                    (c["token_sha256"],)).fetchone()
                if (row is None or row["state"]!="RESERVED" or
                        row["actor"]!=actor or
                        row["upload_request_sha256"]!=request_sha):
                    raise JournalConflict("RESERVATION_SETTLEMENT_CAS_DENIED")
            for c in claims:
                changed=db.execute("""UPDATE selection_tokens SET state=?,job_id=?
                    WHERE token_sha256=? AND state='RESERVED'""",
                    (status,job_id,c["token_sha256"]))
                if changed.rowcount!=1:
                    raise JournalConflict("RESERVATION_SETTLEMENT_CAS_DENIED")

    def inspect_state_for_test(self,token:str)->dict|None:
        """No HTTP route; isolated test-only diagnostic, never token plaintext."""
        with closing(self._connect()) as db:
            row=db.execute("""SELECT state,job_id,upload_request_sha256,actor
                FROM selection_tokens WHERE token_sha256=?""",
                (self.digest(token),)).fetchone()
        return dict(row) if row else None
