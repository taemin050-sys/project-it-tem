"""Explicitly migrated local render state, separate from Provider attempts.

The caller authenticates users and validates current Copy/F09 policy in the
same transaction. This module supplies persistence, CAS and local lease fences.
Construction never creates a database or changes the schema.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
import sqlite3
import time
from uuid import uuid4

from .contracts import LiveGateError, digest


LOCAL_RENDER_PROTOCOL = "LOCAL_PROTECTED_RENDER_V1"
DERIVED_SCHEMA_VERSION = "bp18-derived-store-v1"
ADMISSIONS = "live_derived_recipe_admissions"
RENDERS = "live_derived_renders"
REVIEWS = "live_derived_reviews"

_TABLES = {
    ADMISSIONS: """CREATE TABLE live_derived_recipe_admissions (
        event_id TEXT PRIMARY KEY, grant_id TEXT NOT NULL,
        actor TEXT NOT NULL, job_id TEXT NOT NULL,
        revision INTEGER NOT NULL CHECK(revision >= 1),
        event_kind TEXT NOT NULL CHECK(event_kind IN ('GRANT','REVOKE')),
        recipe_sha TEXT NOT NULL, context_sha TEXT NOT NULL,
        reviewer_actor TEXT NOT NULL, reviewer_role TEXT NOT NULL,
        scope TEXT NOT NULL, idempotency_key TEXT NOT NULL,
        request_sha TEXT NOT NULL, record_json TEXT NOT NULL,
        record_sha TEXT NOT NULL, created_utc TEXT NOT NULL,
        UNIQUE(grant_id, revision), UNIQUE(actor,job_id,idempotency_key)
    )""",
    RENDERS: """CREATE TABLE live_derived_renders (
        derived_id TEXT PRIMARY KEY, actor TEXT NOT NULL, job_id TEXT NOT NULL,
        grant_id TEXT NOT NULL, grant_revision INTEGER NOT NULL CHECK(grant_revision >= 1),
        admission_event_id TEXT NOT NULL REFERENCES live_derived_recipe_admissions(event_id),
        recipe_sha TEXT NOT NULL, context_sha TEXT NOT NULL,
        protocol TEXT NOT NULL CHECK(protocol = 'LOCAL_PROTECTED_RENDER_V1'),
        state TEXT NOT NULL CHECK(state IN
            ('QUEUED','RENDERING','REVIEW_REQUIRED','APPROVED','COMPLETED',
             'REJECTED','REVOKED','STALE','HOLD','FAILED')),
        revision INTEGER NOT NULL DEFAULT 0 CHECK(revision >= 0),
        idempotency_key TEXT NOT NULL, request_sha TEXT NOT NULL,
        payload_json TEXT NOT NULL, worker_id TEXT, lease_token TEXT,
        lease_expires_at REAL, result_sha TEXT, preview_sha TEXT,
        local_receipt_sha TEXT, review_sha TEXT, approval_sha TEXT,
        final_sha TEXT, caption_sha TEXT, receipt_sha TEXT,
        artifacts_json TEXT NOT NULL DEFAULT '{}', error_code TEXT,
        selected INTEGER NOT NULL DEFAULT 0 CHECK(selected IN (0,1)),
        created_utc TEXT NOT NULL, updated_utc TEXT NOT NULL,
        UNIQUE(actor,job_id,idempotency_key),
        UNIQUE(actor,job_id,grant_id,grant_revision,recipe_sha,context_sha)
    )""",
    REVIEWS: """CREATE TABLE live_derived_reviews (
        review_id TEXT PRIMARY KEY,
        derived_id TEXT NOT NULL REFERENCES live_derived_renders(derived_id),
        actor TEXT NOT NULL, job_id TEXT NOT NULL,
        revision INTEGER NOT NULL CHECK(revision >= 1),
        event_kind TEXT NOT NULL CHECK(event_kind IN ('APPROVE','REJECT','REVOKE')),
        preview_sha TEXT NOT NULL, recipe_sha TEXT NOT NULL, context_sha TEXT NOT NULL,
        reviewer_actor TEXT NOT NULL, reviewer_role TEXT NOT NULL,
        idempotency_key TEXT NOT NULL, request_sha TEXT NOT NULL,
        record_json TEXT NOT NULL, record_sha TEXT NOT NULL,
        created_utc TEXT NOT NULL,
        UNIQUE(derived_id,revision), UNIQUE(derived_id,idempotency_key)
    )""",
}

_INDEXES = {
    "live_derived_grant_latest": "CREATE INDEX live_derived_grant_latest ON live_derived_recipe_admissions(grant_id,revision DESC)",
    "live_derived_job_grants": "CREATE INDEX live_derived_job_grants ON live_derived_recipe_admissions(actor,job_id)",
    "live_derived_claim": "CREATE INDEX live_derived_claim ON live_derived_renders(protocol,state,lease_expires_at,created_utc)",
    "live_derived_job_results": "CREATE INDEX live_derived_job_results ON live_derived_renders(actor,job_id,created_utc)",
}
_TRIGGERS = {
    f"{table}_{operation.lower()}_denied": (
        f"CREATE TRIGGER {table}_{operation.lower()}_denied BEFORE {operation} ON {table} "
        "BEGIN SELECT RAISE(ABORT,'DERIVED_EVENT_IMMUTABLE'); END"
    )
    for table in (ADMISSIONS, REVIEWS) for operation in ("UPDATE", "DELETE")
}


def _reject(code):
    raise LiveGateError(code)


def _canonical(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError):
        _reject("DERIVED_RECORD_INVALID")


def _sha(value):
    if (type(value) is not str or len(value) != 64
            or any(char not in "0123456789abcdef" for char in value)):
        _reject("DERIVED_SHA_INVALID")
    return value


def _identity(value):
    if (type(value) is not str or not value.strip() or len(value) > 200
            or any(ord(char) < 32 for char in value)):
        _reject("DERIVED_IDENTITY_INVALID")
    return value


def _revision(value):
    if type(value) is not int or not 0 <= value <= 9007199254740991:
        _reject("DERIVED_REVISION_INVALID")
    return value


def _instant(value=None):
    value = time.time() if value is None else value
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        _reject("DERIVED_TIME_INVALID")
    return float(value)


def _utc():
    return datetime.now(timezone.utc).isoformat()


def _path(filename, *, must_exist):
    path = Path(filename).absolute()
    if any(item.is_symlink() for item in (path, *path.parents)):
        _reject("DERIVED_DATABASE_PATH_INVALID")
    if not path.parent.is_dir() or (path.exists() and not path.is_file()):
        _reject("DERIVED_DATABASE_PATH_INVALID")
    if must_exist and not path.is_file():
        _reject("DERIVED_SCHEMA_NOT_MIGRATED")
    return path


def _connect(filename, *, readonly=False):
    mode = "ro" if readonly else "rw"
    connection = sqlite3.connect(filename.as_uri() + f"?mode={mode}", uri=True, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=15000")
    connection.execute("PRAGMA foreign_keys=ON")
    if not readonly:
        connection.execute("PRAGMA synchronous=FULL")
    return connection


def _normalized_sql(value):
    return " ".join(value.strip().split()).lower()


def _verify_schema(connection):
    expected = {**_TABLES, **_INDEXES, **_TRIGGERS}
    for name, sql in expected.items():
        row = connection.execute("SELECT sql FROM sqlite_master WHERE name=?", (name,)).fetchone()
        if row is None:
            _reject("DERIVED_SCHEMA_NOT_MIGRATED")
        if _normalized_sql(row["sql"]) != _normalized_sql(sql):
            _reject("DERIVED_SCHEMA_INCOMPATIBLE")


def migrate_derived_schema(filename, *, expected_db_sha256=None):
    """Explicit additive migration. Existing application rows are never edited.

    The operator chooses a copied/snapshotted database before invoking this.
    Callers must not use construction or application cold start as migration.
    """
    path = _path(filename, must_exist=False)
    existing = path.exists()
    connection = sqlite3.connect(path, timeout=15)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("BEGIN IMMEDIATE")
        if expected_db_sha256 is not None:
            _sha(expected_db_sha256)
            wal = Path(str(path) + "-wal")
            if wal.is_symlink() or (wal.is_file() and wal.stat().st_size):
                _reject("DERIVED_DATABASE_SNAPSHOT_HAS_WAL")
            if sha256(path.read_bytes()).hexdigest() != expected_db_sha256:
                _reject("DERIVED_DATABASE_SNAPSHOT_CHANGED")
        previous = {row["name"] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        present = previous & _TABLES.keys()
        if present and present != _TABLES.keys():
            _reject("DERIVED_SCHEMA_PARTIAL")
        if present:
            _verify_schema(connection)
            changed = False
        else:
            for statement in (*_TABLES.values(), *_INDEXES.values(), *_TRIGGERS.values()):
                connection.execute(statement)
            _verify_schema(connection)
            changed = True
        connection.commit()
        return {"schema": DERIVED_SCHEMA_VERSION, "database": str(path),
                "changed": changed, "existing_database": existing,
                "added_tables": sorted(_TABLES) if changed else []}
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def _decoded(row):
    if row is None:
        _reject("DERIVED_NOT_FOUND")
    result = dict(row)
    for field in ("record_json", "payload_json", "artifacts_json"):
        if field in result:
            try:
                result[field.removesuffix("_json")] = json.loads(result[field])
            except (ValueError, TypeError):
                _reject("DERIVED_RECORD_CORRUPT")
    if "record_json" in result and digest(result["record"]) != result["record_sha"]:
        _reject("DERIVED_RECORD_CORRUPT")
    if "payload_json" in result:
        expected = digest({"grant_id": result["grant_id"], "grant_revision": result["grant_revision"],
                           "recipe_sha": result["recipe_sha"], "context_sha": result["context_sha"],
                           "protocol": result["protocol"], "payload": result["payload"]})
        if expected != result["request_sha"]:
            _reject("DERIVED_RECORD_CORRUPT")
    return result


class DerivedStore:
    def __init__(self, filename):
        self.filename = _path(filename, must_exist=True)
        with self.connection(readonly=True) as connection:
            _verify_schema(connection)

    @contextmanager
    def connection(self, *, readonly=False):
        _path(self.filename, must_exist=True)
        connection = _connect(self.filename, readonly=readonly)
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self):
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    @contextmanager
    def _using(self, connection=None, *, write=False):
        if connection is not None:
            main = next((row for row in connection.execute("PRAGMA database_list") if row[1] == "main"), None)
            if (main is None or Path(main[2]).resolve() != self.filename.resolve()
                    or (write and not connection.in_transaction)):
                _reject("DERIVED_TRANSACTION_REQUIRED")
            yield connection
        elif write:
            with self.transaction() as owned:
                yield owned
        else:
            with self.connection(readonly=True) as owned:
                yield owned

    def get_admission(self, actor, job_id, grant_id, *, c=None):
        with self._using(c) as connection:
            return _decoded(connection.execute(f"""SELECT * FROM {ADMISSIONS}
                WHERE grant_id=? AND actor=? AND job_id=? ORDER BY revision DESC LIMIT 1""",
                (grant_id, actor, job_id)).fetchone())

    def list_admissions(self, actor, job_id, *, c=None):
        with self._using(c) as connection:
            rows = connection.execute(f"""SELECT a.* FROM {ADMISSIONS} a
                WHERE a.actor=? AND a.job_id=? AND a.revision=(SELECT MAX(b.revision)
                    FROM {ADMISSIONS} b WHERE b.grant_id=a.grant_id)
                ORDER BY a.created_utc,a.event_id""", (actor, job_id)).fetchall()
            return [_decoded(row) for row in rows]

    def active_admission(self, actor, job_id, grant_id, *, expected_revision=None, c=None):
        admission = self.get_admission(actor, job_id, grant_id, c=c)
        if admission["event_kind"] != "GRANT":
            _reject("DERIVED_ADMISSION_REVOKED")
        if expected_revision is not None and admission["revision"] != _revision(expected_revision):
            _reject("DERIVED_ADMISSION_STALE")
        return admission

    def append_admission(self, *, actor, job_id, recipe_sha, context_sha, record,
                         reviewer_actor, reviewer_role, scope, idempotency_key,
                         grant_id=None, expected_revision=0, c=None):
        actor, job_id = _identity(actor), _identity(job_id)
        recipe_sha, context_sha = _sha(recipe_sha), _sha(context_sha)
        reviewer_actor, reviewer_role = _identity(reviewer_actor), _identity(reviewer_role)
        scope, key = _identity(scope), _identity(idempotency_key)
        expected_revision = _revision(expected_revision)
        if type(record) is not dict:
            _reject("DERIVED_RECORD_INVALID")
        request = {"kind": "GRANT", "actor": actor, "job_id": job_id,
                   "grant_id": grant_id, "expected_revision": expected_revision,
                   "recipe_sha": recipe_sha, "context_sha": context_sha,
                   "reviewer_actor": reviewer_actor, "reviewer_role": reviewer_role,
                   "scope": scope, "record": record}
        request_sha = digest(request)
        with self._using(c, write=True) as connection:
            prior = connection.execute(f"SELECT * FROM {ADMISSIONS} WHERE actor=? AND job_id=? AND idempotency_key=?",
                                       (actor, job_id, key)).fetchone()
            if prior:
                if prior["request_sha"] != request_sha:
                    _reject("DERIVED_IDEMPOTENCY_CONFLICT")
                return _decoded(prior)
            if grant_id is None:
                if expected_revision != 0:
                    _reject("DERIVED_ADMISSION_STALE")
                grant_id = uuid4().hex
            else:
                _identity(grant_id)
                previous = self.get_admission(actor, job_id, grant_id, c=connection)
                if previous["revision"] != expected_revision:
                    _reject("DERIVED_ADMISSION_STALE")
                if previous["event_kind"] != "REVOKE":
                    _reject("DERIVED_ADMISSION_ALREADY_ACTIVE")
            envelope = {"schema": "bp18-derived-admission-event-v1", "event_id": uuid4().hex,
                        "grant_id": grant_id, "revision": expected_revision + 1,
                        "event_kind": "GRANT", "actor": actor, "job_id": job_id,
                        "recipe_sha": recipe_sha, "context_sha": context_sha,
                        "reviewer_actor": reviewer_actor, "reviewer_role": reviewer_role,
                        "scope": scope, "created_utc": _utc(), "payload": record}
            self._insert_admission(connection, envelope, key, request_sha)
            return self.get_admission(actor, job_id, grant_id, c=connection)

    @staticmethod
    def _insert_admission(connection, envelope, key, request_sha):
        fields = ("event_id", "grant_id", "actor", "job_id", "revision", "event_kind",
                  "recipe_sha", "context_sha", "reviewer_actor", "reviewer_role", "scope")
        connection.execute(f"""INSERT INTO {ADMISSIONS}
            ({','.join(fields)},idempotency_key,request_sha,record_json,record_sha,created_utc)
            VALUES ({','.join('?' for _ in range(len(fields)+5))})""",
            (*[envelope[field] for field in fields], key, request_sha, _canonical(envelope),
             digest(envelope), envelope["created_utc"]))

    def revoke_admission(self, *, actor, job_id, grant_id, expected_revision,
                         reviewer_actor, reviewer_role, record, idempotency_key, c=None):
        if type(record) is not dict:
            _reject("DERIVED_RECORD_INVALID")
        expected_revision = _revision(expected_revision)
        key = _identity(idempotency_key)
        request_sha = digest({"kind": "REVOKE", "grant_id": grant_id,
            "expected_revision": expected_revision, "reviewer_actor": _identity(reviewer_actor),
            "reviewer_role": _identity(reviewer_role), "record": record})
        with self._using(c, write=True) as connection:
            prior = connection.execute(f"SELECT * FROM {ADMISSIONS} WHERE actor=? AND job_id=? AND idempotency_key=?",
                                       (actor, job_id, key)).fetchone()
            if prior:
                if prior["request_sha"] != request_sha:
                    _reject("DERIVED_IDEMPOTENCY_CONFLICT")
                return _decoded(prior)
            previous = self.active_admission(actor, job_id, grant_id,
                                            expected_revision=expected_revision, c=connection)
            envelope = {name: previous[name] for name in
                        ("grant_id", "actor", "job_id", "recipe_sha", "context_sha", "scope")}
            envelope.update(schema="bp18-derived-admission-event-v1", event_id=uuid4().hex,
                            revision=expected_revision+1, event_kind="REVOKE",
                            reviewer_actor=reviewer_actor, reviewer_role=reviewer_role,
                            created_utc=_utc(), payload=record)
            self._insert_admission(connection, envelope, key, request_sha)
            connection.execute(f"""UPDATE {RENDERS} SET state='STALE',revision=revision+1,
                lease_token=NULL,lease_expires_at=NULL,selected=0,updated_utc=?
                WHERE actor=? AND job_id=? AND grant_id=? AND grant_revision=?""",
                (_utc(), actor, job_id, grant_id, expected_revision))
            return self.get_admission(actor, job_id, grant_id, c=connection)

    def get_render(self, actor, job_id, derived_id, *, c=None):
        with self._using(c) as connection:
            return _decoded(connection.execute(f"SELECT * FROM {RENDERS} WHERE actor=? AND job_id=? AND derived_id=?",
                                               (actor, job_id, derived_id)).fetchone())

    def list_renders(self, actor, job_id, *, c=None):
        with self._using(c) as connection:
            return [_decoded(row) for row in connection.execute(
                f"SELECT * FROM {RENDERS} WHERE actor=? AND job_id=? ORDER BY created_utc,derived_id",
                (actor, job_id)).fetchall()]

    def enqueue_render(self, *, actor, job_id, grant_id, expected_grant_revision,
                       recipe_sha, context_sha, payload, idempotency_key,
                       protocol=LOCAL_RENDER_PROTOCOL, c=None):
        if protocol != LOCAL_RENDER_PROTOCOL or type(payload) is not dict:
            _reject("DERIVED_RENDER_REQUEST_INVALID")
        key = _identity(idempotency_key)
        _sha(recipe_sha)
        _sha(context_sha)
        raw_payload = _canonical(payload)
        request_sha = digest({"grant_id": grant_id, "grant_revision": expected_grant_revision,
                              "recipe_sha": recipe_sha, "context_sha": context_sha,
                              "protocol": protocol, "payload": payload})
        with self._using(c, write=True) as connection:
            admission = self.active_admission(actor, job_id, grant_id,
                expected_revision=expected_grant_revision, c=connection)
            if (admission["recipe_sha"] != recipe_sha or admission["context_sha"] != context_sha):
                _reject("DERIVED_ADMISSION_CONTEXT_MISMATCH")
            prior = connection.execute(f"SELECT * FROM {RENDERS} WHERE actor=? AND job_id=? AND idempotency_key=?",
                                       (actor, job_id, key)).fetchone()
            if prior:
                if prior["request_sha"] != request_sha:
                    _reject("DERIVED_IDEMPOTENCY_CONFLICT")
                return _decoded(prior), False
            same = connection.execute(f"""SELECT * FROM {RENDERS} WHERE actor=? AND job_id=?
                AND grant_id=? AND grant_revision=? AND recipe_sha=? AND context_sha=?""",
                (actor, job_id, grant_id, expected_grant_revision, recipe_sha, context_sha)).fetchone()
            if same:
                if same["request_sha"] != request_sha:
                    _reject("DERIVED_RENDER_CONTEXT_CONFLICT")
                return _decoded(same), False
            derived_id, now = uuid4().hex, _utc()
            connection.execute(f"""INSERT INTO {RENDERS}
                (derived_id,actor,job_id,grant_id,grant_revision,admission_event_id,recipe_sha,
                 context_sha,protocol,state,idempotency_key,request_sha,payload_json,created_utc,updated_utc)
                VALUES (?,?,?,?,?,?,?,?,?,'QUEUED',?,?,?,?,?)""",
                (derived_id, actor, job_id, grant_id, expected_grant_revision,
                 admission["event_id"], recipe_sha, context_sha, protocol, key,
                 request_sha, raw_payload, now, now))
            return self.get_render(actor, job_id, derived_id, c=connection), True

    def _bound_admission(self, connection, render):
        grant = self.active_admission(render["actor"], render["job_id"], render["grant_id"],
                                      expected_revision=render["grant_revision"], c=connection)
        if (grant["event_id"] != render["admission_event_id"]
                or grant["recipe_sha"] != render["recipe_sha"]
                or grant["context_sha"] != render["context_sha"]):
            _reject("DERIVED_ADMISSION_CONTEXT_MISMATCH")
        return grant

    def claim_render(self, *, worker_id, billing_unknown, lease_seconds=60, now=None,
                     protocol=LOCAL_RENDER_PROTOCOL, c=None):
        if protocol != LOCAL_RENDER_PROTOCOL:
            _reject("DERIVED_PROTOCOL_UNSUPPORTED")
        _identity(worker_id)
        if type(billing_unknown) is not bool:
            _reject("DERIVED_BILLING_STATE_REQUIRED")
        if billing_unknown:
            return None
        if type(lease_seconds) is not int or not 1 <= lease_seconds <= 3600:
            _reject("DERIVED_LEASE_INVALID")
        now = _instant(now)
        with self._using(c, write=True) as connection:
            candidates = connection.execute(f"""SELECT * FROM {RENDERS} WHERE protocol=?
                AND (state='QUEUED' OR (state='RENDERING' AND lease_expires_at<=?))
                ORDER BY created_utc,derived_id""", (protocol, now)).fetchall()
            for row in candidates:
                render = _decoded(row)
                try:
                    self._bound_admission(connection, render)
                except LiveGateError as error:
                    if error.code not in {"DERIVED_ADMISSION_REVOKED", "DERIVED_ADMISSION_STALE"}:
                        raise
                    connection.execute(f"""UPDATE {RENDERS} SET state='STALE',revision=revision+1,
                        lease_token=NULL,lease_expires_at=NULL,updated_utc=? WHERE derived_id=?""",
                        (_utc(), render["derived_id"]))
                    continue
                token = uuid4().hex
                connection.execute(f"""UPDATE {RENDERS} SET state='RENDERING',revision=revision+1,
                    worker_id=?,lease_token=?,lease_expires_at=?,error_code=NULL,updated_utc=?
                    WHERE derived_id=? AND revision=?""",
                    (worker_id, token, now+lease_seconds, _utc(), render["derived_id"], render["revision"]))
                return self.get_render(render["actor"], render["job_id"], render["derived_id"], c=connection)
            return None

    def _leased(self, connection, actor, job_id, derived_id, expected_revision, lease_token, now):
        render = self.get_render(actor, job_id, derived_id, c=connection)
        if (render["state"] != "RENDERING" or render["revision"] != _revision(expected_revision)
                or not lease_token or render["lease_token"] != lease_token
                or render["lease_expires_at"] is None or render["lease_expires_at"] <= now):
            _reject("DERIVED_LEASE_STALE")
        self._bound_admission(connection, render)
        return render

    def renew_lease(self, *, actor, job_id, derived_id, expected_revision, lease_token,
                    lease_seconds=60, now=None, c=None):
        if type(lease_seconds) is not int or not 1 <= lease_seconds <= 3600:
            _reject("DERIVED_LEASE_INVALID")
        now = _instant(now)
        with self._using(c, write=True) as connection:
            self._leased(connection, actor, job_id, derived_id, expected_revision, lease_token, now)
            connection.execute(f"""UPDATE {RENDERS} SET lease_expires_at=?,updated_utc=?
                WHERE derived_id=?""", (now+lease_seconds, _utc(), derived_id))
            return self.get_render(actor, job_id, derived_id, c=connection)

    def complete_render(self, *, actor, job_id, derived_id, expected_revision, lease_token,
                        result_sha, preview_sha, local_receipt_sha, artifacts, now=None, c=None):
        for value in (result_sha, preview_sha, local_receipt_sha):
            _sha(value)
        if type(artifacts) is not dict:
            _reject("DERIVED_ARTIFACTS_INVALID")
        with self._using(c, write=True) as connection:
            self._leased(connection, actor, job_id, derived_id, expected_revision,
                         lease_token, _instant(now))
            connection.execute(f"""UPDATE {RENDERS} SET state='REVIEW_REQUIRED',revision=revision+1,
                result_sha=?,preview_sha=?,local_receipt_sha=?,artifacts_json=?,lease_token=NULL,
                lease_expires_at=NULL,error_code=NULL,updated_utc=? WHERE derived_id=?""",
                (result_sha, preview_sha, local_receipt_sha, _canonical(artifacts), _utc(), derived_id))
            return self.get_render(actor, job_id, derived_id, c=connection)

    def fail_render(self, *, actor, job_id, derived_id, expected_revision, lease_token,
                    error_code, hold=False, now=None, c=None):
        if type(hold) is not bool:
            _reject("DERIVED_RENDER_REQUEST_INVALID")
        with self._using(c, write=True) as connection:
            self._leased(connection, actor, job_id, derived_id, expected_revision,
                         lease_token, _instant(now))
            connection.execute(f"""UPDATE {RENDERS} SET state=?,revision=revision+1,error_code=?,
                lease_token=NULL,lease_expires_at=NULL,updated_utc=? WHERE derived_id=?""",
                ("HOLD" if hold else "FAILED", _identity(error_code), _utc(), derived_id))
            return self.get_render(actor, job_id, derived_id, c=connection)

    def retry_render(self, *, actor, job_id, derived_id, expected_revision, c=None):
        """Explicit retry of a failed local render, never a Provider dispatch."""
        with self._using(c, write=True) as connection:
            render = self.get_render(actor, job_id, derived_id, c=connection)
            self._bound_admission(connection, render)
            if (render["state"] not in {"FAILED", "HOLD"}
                    or render["revision"] != _revision(expected_revision)):
                _reject("DERIVED_RETRY_STALE")
            connection.execute(f"""UPDATE {RENDERS} SET state='QUEUED',revision=revision+1,
                error_code=NULL,worker_id=NULL,lease_token=NULL,lease_expires_at=NULL,
                updated_utc=? WHERE derived_id=?""", (_utc(), derived_id))
            return self.get_render(actor, job_id, derived_id, c=connection)

    def append_review(self, *, actor, job_id, derived_id, expected_revision,
                      preview_sha, recipe_sha, context_sha, decision, record,
                      reviewer_actor, reviewer_role, idempotency_key, c=None):
        if decision not in {"APPROVE", "REJECT", "REVOKE"} or type(record) is not dict:
            _reject("DERIVED_REVIEW_INVALID")
        key = _identity(idempotency_key)
        reviewer_actor, reviewer_role = _identity(reviewer_actor), _identity(reviewer_role)
        for value in (preview_sha, recipe_sha, context_sha):
            _sha(value)
        expected_revision = _revision(expected_revision)
        request_sha = digest({"expected_revision": expected_revision, "preview_sha": preview_sha,
            "recipe_sha": recipe_sha, "context_sha": context_sha, "decision": decision,
            "record": record, "reviewer_actor": reviewer_actor, "reviewer_role": reviewer_role})
        with self._using(c, write=True) as connection:
            render = self.get_render(actor, job_id, derived_id, c=connection)
            prior = connection.execute(f"SELECT * FROM {REVIEWS} WHERE derived_id=? AND idempotency_key=?",
                                       (derived_id, key)).fetchone()
            if prior:
                if prior["request_sha"] != request_sha:
                    _reject("DERIVED_IDEMPOTENCY_CONFLICT")
                return {**render, "latest_review": self.latest_review(actor, job_id, derived_id, c=connection)}
            self._bound_admission(connection, render)
            if (render["revision"] != expected_revision or render["preview_sha"] != preview_sha
                    or render["recipe_sha"] != recipe_sha or render["context_sha"] != context_sha):
                _reject("DERIVED_REVIEW_STALE")
            allowed = {"REVIEW_REQUIRED", "APPROVED", "COMPLETED"}
            if render["state"] not in allowed or (decision == "APPROVE" and render["state"] != "REVIEW_REQUIRED"):
                _reject("DERIVED_REVIEW_STATE_INVALID")
            previous = connection.execute(f"SELECT COALESCE(MAX(revision),0) FROM {REVIEWS} WHERE derived_id=?",
                                          (derived_id,)).fetchone()[0]
            envelope = {"schema": "bp18-derived-review-event-v1", "review_id": uuid4().hex,
                "derived_id": derived_id, "actor": actor, "job_id": job_id,
                "revision": previous+1, "event_kind": decision, "preview_sha": preview_sha,
                "recipe_sha": recipe_sha, "context_sha": context_sha,
                "reviewer_actor": reviewer_actor, "reviewer_role": reviewer_role,
                "created_utc": _utc(), "payload": record}
            fields = ("review_id", "derived_id", "actor", "job_id", "revision", "event_kind",
                      "preview_sha", "recipe_sha", "context_sha", "reviewer_actor", "reviewer_role")
            review_sha = digest(envelope)
            connection.execute(f"""INSERT INTO {REVIEWS}
                ({','.join(fields)},idempotency_key,request_sha,record_json,record_sha,created_utc)
                VALUES ({','.join('?' for _ in range(len(fields)+5))})""",
                (*[envelope[field] for field in fields], key, request_sha,
                 _canonical(envelope), review_sha, envelope["created_utc"]))
            state = {"APPROVE": "APPROVED", "REJECT": "REJECTED", "REVOKE": "REVOKED"}[decision]
            connection.execute(f"""UPDATE {RENDERS} SET state=?,revision=revision+1,
                review_sha=?,approval_sha=?,selected=0,updated_utc=? WHERE derived_id=?""",
                (state, review_sha, review_sha if decision == "APPROVE" else None, _utc(), derived_id))
            updated = self.get_render(actor, job_id, derived_id, c=connection)
            return {**updated, "latest_review": self.latest_review(actor, job_id, derived_id, c=connection)}

    def latest_review(self, actor, job_id, derived_id, *, c=None):
        with self._using(c) as connection:
            self.get_render(actor, job_id, derived_id, c=connection)
            row = connection.execute(f"SELECT * FROM {REVIEWS} WHERE derived_id=? ORDER BY revision DESC LIMIT 1",
                                     (derived_id,)).fetchone()
            return _decoded(row) if row else None

    def require_approval(self, actor, job_id, derived_id, *, c=None):
        with self._using(c) as connection:
            render = self.get_render(actor, job_id, derived_id, c=connection)
            self._bound_admission(connection, render)
            review = self.latest_review(actor, job_id, derived_id, c=connection)
            if (render["state"] not in {"APPROVED", "COMPLETED"} or not review
                    or review["event_kind"] != "APPROVE" or review["record_sha"] != render["approval_sha"]
                    or any(review[name] != render[name] for name in ("recipe_sha", "preview_sha", "context_sha"))):
                _reject("DERIVED_APPROVAL_REQUIRED")
            return render

    def finalize_render(self, *, actor, job_id, derived_id, expected_revision,
                        approval_sha, preview_sha, final_sha, caption_sha, receipt_sha,
                        artifacts, c=None):
        for value in (approval_sha, preview_sha, final_sha, caption_sha, receipt_sha):
            _sha(value)
        if type(artifacts) is not dict:
            _reject("DERIVED_ARTIFACTS_INVALID")
        with self._using(c, write=True) as connection:
            render = self.require_approval(actor, job_id, derived_id, c=connection)
            _revision(expected_revision)
            if (render["approval_sha"] != approval_sha or render["preview_sha"] != preview_sha
                    or final_sha != preview_sha):
                _reject("DERIVED_FINALIZE_STALE")
            if render["state"] == "COMPLETED":
                if (render["final_sha"], render["caption_sha"], render["receipt_sha"], render["artifacts"]) != (
                        final_sha, caption_sha, receipt_sha, artifacts):
                    _reject("DERIVED_FINALIZE_CONFLICT")
                return render
            if render["revision"] != expected_revision:
                _reject("DERIVED_FINALIZE_STALE")
            connection.execute(f"""UPDATE {RENDERS} SET state='COMPLETED',revision=revision+1,
                final_sha=?,caption_sha=?,receipt_sha=?,artifacts_json=?,updated_utc=? WHERE derived_id=?""",
                (final_sha, caption_sha, receipt_sha, _canonical(artifacts), _utc(), derived_id))
            return self.get_render(actor, job_id, derived_id, c=connection)

    def select_render(self, *, actor, job_id, derived_id, expected_revision, expected_final_sha, c=None):
        with self._using(c, write=True) as connection:
            render = self.require_approval(actor, job_id, derived_id, c=connection)
            if (render["state"] != "COMPLETED" or render["revision"] != _revision(expected_revision)
                    or render["final_sha"] != _sha(expected_final_sha)):
                _reject("DERIVED_SELECTION_STALE")
            connection.execute(f"""UPDATE {RENDERS} SET selected=0,revision=revision+1,updated_utc=?
                WHERE actor=? AND job_id=? AND selected=1 AND derived_id<>?""",
                (_utc(), actor, job_id, derived_id))
            if not render["selected"]:
                connection.execute(f"UPDATE {RENDERS} SET selected=1,revision=revision+1,updated_utc=? WHERE derived_id=?",
                                   (_utc(), derived_id))
            return self.get_render(actor, job_id, derived_id, c=connection)
