"""Explicit derived migration preserves preexisting records and cold-start state."""
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from demo_staging.live.contracts import LiveGateError
from demo_staging.live import derived_store
from demo_staging.live.derived_store import DerivedStore, migrate_derived_schema


def test_constructor_does_not_create_or_migrate(tmp_path):
    database = tmp_path / "missing.sqlite"
    with pytest.raises(LiveGateError, match="DERIVED_SCHEMA_NOT_MIGRATED"):
        DerivedStore(database)
    assert not database.exists()
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE existing (id TEXT PRIMARY KEY,value TEXT)")
        connection.execute("INSERT INTO existing VALUES ('old','unchanged')")
    before = database.read_bytes()
    with pytest.raises(LiveGateError, match="DERIVED_SCHEMA_NOT_MIGRATED"):
        DerivedStore(database)
    assert database.read_bytes() == before


def test_additive_migration_only_mutates_the_named_clone(tmp_path):
    original = tmp_path / "original.sqlite"
    with sqlite3.connect(original) as connection:
        connection.execute("CREATE TABLE original_jobs (id TEXT PRIMARY KEY,record BLOB)")
        connection.execute("INSERT INTO original_jobs VALUES ('old',?)", (b"protected\x00",))
        connection.execute("PRAGMA user_version=12")
    original_bytes = original.read_bytes()
    clone = tmp_path / "clone.sqlite"
    clone.write_bytes(original_bytes)
    result = migrate_derived_schema(clone)
    assert result["changed"] is True
    assert len(result["added_tables"]) == 3
    assert original.read_bytes() == original_bytes
    with sqlite3.connect(clone) as connection:
        assert connection.execute("SELECT * FROM original_jobs").fetchall() == [("old", b"protected\x00")]
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 12
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    DerivedStore(clone)
    assert migrate_derived_schema(clone)["changed"] is False


def test_incompatible_partial_schema_is_not_silently_repaired(tmp_path):
    database = tmp_path / "partial.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE live_derived_renders (wrong TEXT)")
    before = database.read_bytes()
    with pytest.raises(LiveGateError, match="DERIVED_SCHEMA_PARTIAL"):
        migrate_derived_schema(database)
    assert database.read_bytes() == before
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == [
            ("live_derived_renders",)]


def test_missing_immutability_trigger_is_incompatible(tmp_path):
    database = tmp_path / "derived.sqlite"
    migrate_derived_schema(database)
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TRIGGER live_derived_reviews_delete_denied")
    with pytest.raises(LiveGateError, match="DERIVED_SCHEMA_NOT_MIGRATED"):
        DerivedStore(database)


def test_ddl_failure_rolls_back_all_new_tables(tmp_path, monkeypatch):
    database = tmp_path / "clone.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE old_records (id TEXT)")
        connection.execute("INSERT INTO old_records VALUES ('preserve')")
    monkeypatch.setitem(derived_store._INDEXES, "injected_failure", "CREATE INDEX broken ON missing_table(id)")
    with pytest.raises(sqlite3.OperationalError, match="no such table"):
        migrate_derived_schema(database)
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == [("old_records",)]
        assert connection.execute("SELECT * FROM old_records").fetchall() == [("preserve",)]


def test_snapshot_hash_is_checked_under_the_migration_lock(tmp_path):
    database = tmp_path / "clone.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE previous (id TEXT)")
    before = database.read_bytes()
    with pytest.raises(LiveGateError, match="DERIVED_DATABASE_SNAPSHOT_CHANGED"):
        migrate_derived_schema(database, expected_db_sha256="0"*64)
    assert database.read_bytes() == before
    assert migrate_derived_schema(database, expected_db_sha256=sha256(before).hexdigest())["changed"]


def test_database_symlink_is_rejected(tmp_path):
    target = tmp_path / "real.sqlite"
    migrate_derived_schema(target)
    alias = tmp_path / "alias.sqlite"
    alias.symlink_to(target)
    with pytest.raises(LiveGateError, match="DERIVED_DATABASE_PATH_INVALID"):
        DerivedStore(alias)
    with pytest.raises(LiveGateError, match="DERIVED_DATABASE_PATH_INVALID"):
        migrate_derived_schema(alias)


def test_cli_requires_exact_snapshot_or_absent_explicit_database(tmp_path):
    script = Path(__file__).resolve().parents[2] / "scripts/migrate_derived_schema.py"
    database = tmp_path / "new.sqlite"
    command = [sys.executable, "-B", str(script), "--database", str(database)]
    denied = subprocess.run(command, capture_output=True, text=True)
    assert denied.returncode == 2
    assert not database.exists()
    created = subprocess.run([*command, "--create"], capture_output=True, text=True)
    assert created.returncode == 0, created.stderr
    assert json.loads(created.stdout)["changed"]
    current = database.read_bytes()
    denied = subprocess.run([*command, "--expected-db-sha256", "0"*64], capture_output=True, text=True)
    assert denied.returncode == 2
    assert database.read_bytes() == current
    checked = subprocess.run([*command, "--expected-db-sha256", sha256(current).hexdigest()],
                             capture_output=True, text=True)
    assert checked.returncode == 0, checked.stderr
    assert not json.loads(checked.stdout)["changed"]
