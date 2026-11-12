"""A51E isolated, PREINITIALIZED signed-SSO beta upload-idempotency journal.

No production initialization. No secrets. Not the Queue, Cost, Owner Provider
Attempt or historical application image-attempt ledger. Operates only on an
authorized *nonbillable integration candidate* until real Owner/PM signoff.
"""
from __future__ import annotations

from contextlib import closing, contextmanager
from hashlib import sha256
from pathlib import Path
import os
import re
import sqlite3
import time

_HEX32=re.compile(r"^[0-9a-f]{32}$")
_HEX64=re.compile(r"^[0-9a-f]{64}$")


class BetaIngressConflict(Exception):
    pass


class BetaUploadLedger:
    TABLE="beta_upload_request_v1"
    def __init__(self, path:Path, *, initialize:bool=False):
        source=Path(path)
        if source.is_symlink() or source.parent.is_symlink():
            raise RuntimeError("A51E_LEDGER_SYMLINK_DENIED")
        self.path=source.resolve()
        if initialize:
            if not self.path.parent.is_dir():
                raise RuntimeError("A51E_LEDGER_PARENT_NOT_PREPARED")
            if self.path.parent.stat().st_mode & 0o077:
                raise RuntimeError("A51E_LEDGER_PARENT_PERMISSIONS_UNSAFE")
            with closing(sqlite3.connect(self.path)) as db:
                db.execute("PRAGMA journal_mode=WAL")
                db.execute("""CREATE TABLE IF NOT EXISTS beta_upload_request_v1(
                    request_id TEXT PRIMARY KEY,
                    actor TEXT NOT NULL,
                    request_sha256 TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN
                        ('RESERVED','COMMITTED','FAILED_REQUIRES_REVIEW')),
                    job_id TEXT,
                    created_utc INTEGER NOT NULL
                )""")
                db.commit()
            os.chmod(self.path,0o600)
        self.verify_existing()

    def verify_existing(self):
        if (not self.path.is_file() or self.path.is_symlink() or
                self.path.stat().st_mode & 0o077):
            raise RuntimeError("A51E_PREINITIALIZED_PRIVATE_LEDGER_REQUIRED")
        with closing(self._connect()) as db:
            row=db.execute("""SELECT name FROM sqlite_master
                   WHERE type='table' AND name=?""",(self.TABLE,)).fetchone()
            if row is None:
                raise RuntimeError("A51E_UPLOAD_LEDGER_SCHEMA_MISSING")
            cols={x["name"] for x in db.execute(
                f"PRAGMA table_info({self.TABLE})")}
            if cols!={"request_id","actor","request_sha256",
                     "state","job_id","created_utc"}:
                raise RuntimeError("A51E_UPLOAD_LEDGER_SCHEMA_DRIFT")

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

    def reserve(self,*,request_id:str,actor:str,request_sha256:str):
        if (not _HEX32.fullmatch(request_id) or not
                _HEX64.fullmatch(request_sha256)):
            raise BetaIngressConflict("UPLOAD_ID_OR_SHA_INVALID")
        with self._write() as db:
            old=db.execute("""SELECT actor,request_sha256,state,job_id
                FROM beta_upload_request_v1 WHERE request_id=?""",
                (request_id,)).fetchone()
            if old:
                if old["actor"]!=actor or old["request_sha256"]!=request_sha256:
                    raise BetaIngressConflict("REQUEST_ID_ACTOR_OR_CONTENT_CHANGED")
                if old["state"]=="COMMITTED" and old["job_id"]:
                    return old["job_id"]
                raise BetaIngressConflict("REQUEST_UNCERTAIN_NO_AUTO_RETRY")
            db.execute("""INSERT INTO beta_upload_request_v1
                (request_id,actor,request_sha256,state,job_id,created_utc)
                VALUES(?,?,?,'RESERVED',NULL,?)""",
                (request_id,actor,request_sha256,int(time.time())))
            return None

    def settle(self,*,request_id:str,actor:str,request_sha256:str,
               job_id:str|None):
        state="COMMITTED" if job_id else "FAILED_REQUIRES_REVIEW"
        if job_id and not _HEX32.fullmatch(job_id):
            raise BetaIngressConflict("JOB_ID_INVALID")
        with self._write() as db:
            changed=db.execute("""UPDATE beta_upload_request_v1 SET
                state=?,job_id=?
                WHERE request_id=? AND actor=? AND request_sha256=?
                  AND state='RESERVED'""",
                (state,job_id,request_id,actor,request_sha256))
            if changed.rowcount!=1:
                raise BetaIngressConflict("RESERVATION_SETTLEMENT_CAS_DENIED")

    def inspect_for_test(self,request_id):
        with closing(self._connect()) as db:
            row=db.execute("""SELECT state,job_id,request_sha256,actor
              FROM beta_upload_request_v1 WHERE request_id=?""",
              (request_id,)).fetchone()
        return dict(row) if row else None
