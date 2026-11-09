"""A3 deployment/billing preflight is A-only, inspect-only, never unlocks paid."""
from __future__ import annotations

import hashlib
from pathlib import Path
import sqlite3

import pytest

from scripts.a3_track_a_guarded_readiness import (
    inspect_a_runtime, source_manifest, git,
)


def fixture_a(tmp_path: Path, *, installed_head=True) -> Path:
    a = tmp_path / "ittem-e2e-baseline-20261107"
    runtime = a / "runtime" / "live"
    runtime.mkdir(parents=True)
    repo = a / "repo"
    repo.mkdir()
    (repo / "SOURCE_SHA.txt").write_text(
        git("rev-parse", "HEAD") if installed_head else "9879eb0" + "0" * 33
    )
    schemas = [
        ("queue.sqlite", "CREATE TABLE queued_ops(mode TEXT,state TEXT)",
         "INSERT INTO queued_ops VALUES ('LIVE','SUCCEEDED')"),
        ("cost.sqlite", "CREATE TABLE attempts(status TEXT)",
         "INSERT INTO attempts VALUES ('SUCCEEDED_USAGE_UNPRICED')"),
        ("owner_image/image_attempts.sqlite",
         "CREATE TABLE provider_attempts(state TEXT)",
         "INSERT INTO provider_attempts VALUES ('succeeded')"),
    ]
    for file, ddl, example in schemas:
        path = runtime / file
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as db:
            db.execute(ddl)
            db.execute(example)
    return a


def snapshot_hashes(root: Path) -> dict:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*") if path.is_file()
    }


def test_readonly_a_preflight_preserves_all_sqlite_and_receipts(tmp_path):
    a = fixture_a(tmp_path)
    before = snapshot_hashes(a)
    result = inspect_a_runtime(a)
    assert result["expected_source_match"] == "PASS"
    assert result["billing_gate"] == "PASS_WITH_NOTE"
    assert result["ledgers"]["cost"]["counts"] == {
        "SUCCEEDED_USAGE_UNPRICED": 1
    }
    assert result["external_provider_invoice_reconciled"] is False
    assert result["authorized_budget_verified"] is False
    assert result["paid_worker"] == "HOLD"
    assert result["release"] == "HOLD"
    assert snapshot_hashes(a) == before


@pytest.mark.parametrize(("ledger","state"), [
    ("queue.sqlite", "BILLING_UNKNOWN"),
    ("queue.sqlite", "RUNNING"),
    ("cost.sqlite", "RESERVED"),
    ("cost.sqlite", "DISPATCHED"),
    ("cost.sqlite", "BILLING_UNKNOWN"),
    ("owner_image/image_attempts.sqlite", "submitting"),
    ("owner_image/image_attempts.sqlite", "failed"),
    ("owner_image/image_attempts.sqlite", "unknown"),
])
def test_any_uncertain_ledger_causes_hold(tmp_path,ledger,state):
    a=fixture_a(tmp_path)
    path=a/"runtime"/"live"/ledger
    with sqlite3.connect(path) as db:
        table=("queued_ops" if ledger=="queue.sqlite"
               else "attempts" if ledger=="cost.sqlite" else "provider_attempts")
        db.execute("UPDATE "+table+" SET state=?" if table!="attempts"
                   else "UPDATE attempts SET status=?", (state,))
    result=inspect_a_runtime(a)
    assert result["billing_gate"]=="HOLD" and result["paid_worker"]=="HOLD"
    assert result["uncertainty"]


def test_missing_and_corrupt_ledger_fail_closed(tmp_path):
    a=fixture_a(tmp_path)
    target=a/"runtime"/"live"/"cost.sqlite"
    target.unlink()
    assert inspect_a_runtime(a)["billing_gate"]=="HOLD"
    target.write_bytes(b"not SQLite")
    assert inspect_a_runtime(a)["billing_gate"]=="HOLD"


def test_legacy_gcp_sha_stale_never_declares_match(tmp_path):
    a=fixture_a(tmp_path,installed_head=False)
    result=inspect_a_runtime(a)
    assert result["expected_source_match"]=="HOLD"
    assert result["paid_worker"]=="HOLD"


def test_protected_b_live_qa_roots_are_rejected(tmp_path):
    for name in ("ittem-bp18-product-completion-20261111",
                 "ittem-bp17-final-qa-20261107",
                 "ittem-bp17-shared-history-qa-20261107"):
        with pytest.raises(ValueError,match="NOT_A_TRACK_RUNTIME_ROOT"):
            inspect_a_runtime(tmp_path / name)


def test_manifest_source_sha_and_owner_policy_no_paid_activation():
    result=source_manifest()
    assert result["contract"]=="IT_TEM_P03_A3_A_ONLY_GUARDED_MANIFEST_V1"
    assert result["commit"]==git("rev-parse","HEAD")
    assert result["tree"]==git("rev-parse","HEAD^{tree}")
    assert result["image_contract"]["candidates_per_request"]==1
    assert result["image_contract"]["batch_allowed"] is False
    assert result["live_provider_post_authorized"] is False
    assert result["acceptance"]["PAID_WORKER"]=="HOLD"
    assert all(len(v)==64 for v in result["locks_sha256"].values() if v)
