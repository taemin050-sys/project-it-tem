"""A3 deployment/billing preflight is A-only, inspect-only, never unlocks paid."""
from __future__ import annotations

import hashlib
from pathlib import Path
import sqlite3
from unittest.mock import patch

import pytest

from scripts.a3_track_a_guarded_readiness import (
    inspect_a_runtime, source_manifest, git, LEDGERS, A_RUNTIME_ROOT,
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
    # A3R: fixture schemas are derived from the real required Owner ledger
    # columns; a minimal mock missing context or ownership MUST now HOLD.
    for ledger, spec in LEDGERS.items():
        path = a.joinpath(*spec["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        cols=", ".join(name+" "+sqltype for name,sqltype in spec["fields"].items())
        data = {"queue": {"id":"task1","actor":"alice","job_id":"job1",
                 "stage":"analysis","context_sha":"a"*64,"state":"SUCCEEDED",
                 "mode":"LIVE"},
                "cost": {"id":"attempt1","actor":"alice","job_id":"job1",
                 "stage":"image_prompt","payload_hash":"c"*64,
                 "status":"SUCCEEDED_USAGE_UNPRICED",
                 "billing_unknown":0,"reserved_microusd":0,
                 "receipt":'{"billing_status":"UNPRICED_RESERVATION_HELD","provider_response_id":"fake-provider-test-id","usage":{"total_tokens":7}}'},
                "image": {"job_id":"image1","project_id":"project1",
                 "request_hash":"b"*64,"attempt_id":"attempt-image1",
                 "state":"succeeded","reservation_units":0,
                 "result_json":'{"attempt_id":"fake","fixture_only":true}',
                 "usage_json":None,"provider_request_id":"fake-provider-test-id"}}[ledger]
        with sqlite3.connect(path) as db:
            db.execute(f"CREATE TABLE {spec['table']} ({cols})")
            names=list(data)
            db.execute(f"INSERT INTO {spec['table']} ({','.join(names)}) "
                       f"VALUES ({','.join('?' for _ in names)})",
                       tuple(data[k] for k in names))
    receipt = runtime / "outputs" / "demo" / "receipt.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_bytes(b'{"state":"immutable-receipt"}')
    return a


def snapshot_hashes(root: Path) -> dict:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*") if path.is_file()
    }


def test_readonly_a_preflight_preserves_all_sqlite_and_receipts(tmp_path):
    a = fixture_a(tmp_path)
    before = snapshot_hashes(a)
    result = inspect_a_runtime(a,fixture_mode=True)
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
    result=inspect_a_runtime(a,fixture_mode=True)
    assert result["billing_gate"]=="HOLD" and result["paid_worker"]=="HOLD"
    assert result["uncertainty"]


def test_missing_and_corrupt_ledger_fail_closed(tmp_path):
    a=fixture_a(tmp_path)
    target=a/"runtime"/"live"/"cost.sqlite"
    target.unlink()
    assert inspect_a_runtime(a,fixture_mode=True)["billing_gate"]=="HOLD"
    target.write_bytes(b"not SQLite")
    assert inspect_a_runtime(a,fixture_mode=True)["billing_gate"]=="HOLD"


def test_legacy_gcp_sha_stale_never_declares_match(tmp_path):
    a=fixture_a(tmp_path,installed_head=False)
    result=inspect_a_runtime(a,fixture_mode=True)
    assert result["expected_source_match"]=="HOLD"
    assert result["paid_worker"]=="HOLD"


def test_protected_b_live_qa_roots_are_rejected(tmp_path):
    for name in ("ittem-bp18-product-completion-20261111",
                 "ittem-bp17-final-qa-20261107",
                 "ittem-bp17-shared-history-qa-20261107"):
        with pytest.raises(ValueError,match="NOT_A_TRACK_RUNTIME_ROOT"):
            inspect_a_runtime(tmp_path / name,fixture_mode=True)


def test_manifest_source_sha_and_owner_policy_no_paid_activation():
    result=source_manifest()
    assert result["contract"]=="IT_TEM_P03_A3R1_ALL_TRACKED_HEAD_ATTESTATION_V3"
    assert result["commit"]==git("rev-parse","HEAD")
    assert result["tree"]==git("rev-parse","HEAD^{tree}")
    assert result["image_contract"]["candidates_per_request"]==1
    assert result["image_contract"]["batch_allowed"] is False
    assert result["live_provider_post_authorized"] is False
    assert result["acceptance"]["PAID_WORKER"]=="HOLD"
    assert all(len(v)==64 for v in result["locks_sha256"].values() if v)


# A3R -- C-A3 independently discovered unsafe preflight cases.
# All A/B runtime and SQLite fixtures below are TEMPORARY; never point to
# actual GCP, Track B, Protected Live or historic QA.

@pytest.mark.parametrize("kind", ("runtime", "live", "owner_image", "queue_file"))
def test_c_a3_p101_intermediate_or_final_symlink_into_fake_b_denied(
    tmp_path, kind,
):
    a=fixture_a(tmp_path)
    protected=tmp_path/"ittem-bp18-product-completion-20261111"/"runtime"/"live"
    protected.mkdir(parents=True)
    # B fixture contains fake canary data; real B is never opened.
    bfile=protected/"queue.sqlite"
    with sqlite3.connect(bfile) as db:
        db.execute("CREATE TABLE only_fake_b(canary TEXT)")
        db.execute("INSERT INTO only_fake_b VALUES('FAKE_B_PRIVATE_SENTINEL')")
    b_initial=snapshot_hashes(protected)
    if kind=="runtime":
        target=a/"runtime"
        target.rename(a/"isolated_runtime_old")
        target.symlink_to(protected.parent,target_is_directory=True)
    elif kind=="live":
        target=a/"runtime"/"live"
        target.rename(a/"runtime"/"isolated_live_old")
        target.symlink_to(protected,target_is_directory=True)
    elif kind=="owner_image":
        target=a/"runtime"/"live"/"owner_image"
        target.rename(a/"runtime"/"live"/"isolated_image_old")
        target.symlink_to(protected,target_is_directory=True)
    else:
        target=a/"runtime"/"live"/"queue.sqlite"
        target.rename(a/"runtime"/"live"/"original_queue.sqlite")
        target.symlink_to(bfile)
    result=inspect_a_runtime(a,fixture_mode=True)
    assert result["ledger_integrity_gate"]=="HOLD"
    assert result["deployment_preflight_gate"]=="HOLD"
    assert result["paid_worker"]=="HOLD"
    assert result["uncertainty"]
    if kind in ("live","runtime","queue_file"):
        assert result["ledgers"]["queue"]["gate"]!="PASS"
        assert result["ledgers"]["queue"]["counts"]=={}
    assert snapshot_hashes(protected)==b_initial


def test_c_a3_p101_operational_path_exact_and_fixture_explicit(tmp_path):
    a=fixture_a(tmp_path)
    with pytest.raises(ValueError,match="NOT_A_TRACK_RUNTIME_ROOT"):
        inspect_a_runtime(a)
    assert inspect_a_runtime(a,fixture_mode=True)["runtime"]=="A_ONLY_TEST_FIXTURE"
    with pytest.raises(ValueError,match="NOT_A_TRACK_RUNTIME_ROOT"):
        inspect_a_runtime(A_RUNTIME_ROOT.parent/"DIFFERENT")
    b=tmp_path/"ittem-bp18-product-completion-20261111"
    b.mkdir()
    alias=tmp_path/"ittem-e2e-baseline-20261107-alias"
    alias.symlink_to(b,target_is_directory=True)
    with pytest.raises(ValueError,match="NOT_A_TRACK_RUNTIME_ROOT"):
        inspect_a_runtime(alias,fixture_mode=True)


@pytest.mark.parametrize("ledger,value", [
    ("queue","UNRECOGNIZED_STATE"),
    ("cost","UNRECOGNIZED_STATE"),
    ("image","UNRECOGNIZED_STATE"),
    ("queue",None),("cost",None),("image",None),
    ("queue",17),("cost",17),("image",17),
])
def test_c_a3_p102_unknown_null_invalid_type_never_pass(
    tmp_path,ledger,value,
):
    a=fixture_a(tmp_path)
    spec=LEDGERS[ledger]
    with sqlite3.connect(a.joinpath(*spec["path"])) as db:
        db.execute(f"UPDATE {spec['table']} SET {spec['state']}=?",(value,))
    r=inspect_a_runtime(a,fixture_mode=True)
    assert r["ledger_integrity_gate"]=="HOLD"
    assert r["ledgers"][ledger]["reason"]=="LEDGER_UNKNOWN_STATE"
    assert ledger in r["uncertainty"] and r["paid_worker"]=="HOLD"


@pytest.mark.parametrize(("col","value"), [
    ("mode","UNRECOGNIZED_MODE"),
    ("mode",None),
    ("stage","UNRECOGNIZED_STAGE"),
    ("stage",None),
])
def test_p102_queue_other_critical_enum_invalid(tmp_path,col,value):
    a=fixture_a(tmp_path)
    with sqlite3.connect(a/"runtime"/"live"/"queue.sqlite") as db:
        db.execute(f"UPDATE queued_ops SET {col}=?",(value,))
    r=inspect_a_runtime(a,fixture_mode=True)
    assert r["ledger_integrity_gate"]=="HOLD"
    assert r["ledgers"]["queue"]["gate"]=="HOLD"


@pytest.mark.parametrize("value", (None,"INVALID",2))
def test_p102_billing_unknown_flag_malformed_fails_closed(tmp_path,value):
    a=fixture_a(tmp_path)
    with sqlite3.connect(a/"runtime"/"live"/"cost.sqlite") as db:
        db.execute("UPDATE attempts SET billing_unknown=?",(value,))
    result=inspect_a_runtime(a,fixture_mode=True)
    assert result["ledgers"]["cost"]["gate"]=="HOLD"


@pytest.mark.parametrize("name",("queue","cost","image"))
def test_p102_incompatible_schema_fails_closed(tmp_path,name):
    a=fixture_a(tmp_path)
    spec=LEDGERS[name]
    target=a.joinpath(*spec["path"])
    target.unlink()
    with sqlite3.connect(target) as db:
        db.execute(f"CREATE TABLE {spec['table']} (state TEXT)")
    r=inspect_a_runtime(a,fixture_mode=True)
    assert r["ledgers"][name]["gate"]=="HOLD"
    assert r["ledgers"][name]["reason"]=="LEDGER_SCHEMA_MISMATCH"


def test_p102_unpriced_usage_is_not_a_confirmed_zero_dollar_invoice(tmp_path):
    a=fixture_a(tmp_path)
    r=inspect_a_runtime(a,fixture_mode=True)
    assert r["ledgers"]["cost"]["counts"]=={"SUCCEEDED_USAGE_UNPRICED":1}
    assert r["authorized_budget_verified"] is False
    assert r["external_provider_invoice_reconciled"] is False
    assert r["qa_deployment_readiness_gate"]=="HOLD"
    assert r["paid_worker_authorization_gate"]=="HOLD"


def test_p2_missing_lock_and_evidence_hash_or_git_blob_holds(monkeypatch):
    import scripts.a3_track_a_guarded_readiness as module
    extra="configs/REQUIRED_LOCK_MISSING_A3R_test.txt"
    monkeypatch.setattr(module,"LOCKS",module.LOCKS+(extra,))
    lock=module.source_manifest()
    assert lock["locks_sha256"][extra] is None
    assert lock["lock_integrity_gate"]=="HOLD"
    assert lock["source_gate"]=="HOLD"
    monkeypatch.undo()
    original_is_file=Path.is_file
    def simulate_missing(self):
        if str(self).endswith("/A34_FULL_PYTHON_FINAL.log"):
            return False
        return original_is_file(self)
    with patch.object(Path,"is_file",simulate_missing):
        missing=source_manifest()
    assert missing["evidence_integrity_gate"]=="HOLD"
    assert missing["source_integrity_gate"]=="HOLD"
    with patch.object(module,"_committed_bytes",return_value=b"wrong-git-blob"):
        forged=module.source_manifest()
    assert forged["source_gate"]=="HOLD"


def test_p2_wal_shm_and_receipt_remain_byte_immutable(tmp_path):
    a=fixture_a(tmp_path)
    target=a/"runtime"/"live"/"queue.sqlite"
    conn=sqlite3.connect(target)
    try:
        assert conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]=="wal"
        conn.execute("INSERT INTO queued_ops (id,actor,job_id,stage,context_sha,"
                     "state,mode) VALUES (?,?,?,?,?,?,?)",
                     ("t2","alice","j2","analysis","a"*64,"QUEUED","LIVE"))
        conn.commit()
        assert (target.parent/"queue.sqlite-wal").is_file()
        before=snapshot_hashes(a)
        r=inspect_a_runtime(a,fixture_mode=True)
        after=snapshot_hashes(a)
        assert before==after, "Preflight may NOT write DB/WAL/SHM/receipt"
        assert r["ledger_integrity_gate"]=="HOLD"
        assert r["ledgers"]["queue"]["reason"]==(
            "ACTIVE_WAL_SHM_REQUIRES_QUIESCED_SNAPSHOT")
        assert r["ledgers"]["queue"]["sidecars_sha256_unchanged"] is True
    finally:
        conn.close()


def test_p2_source_mismatch_and_missing_image_cannot_be_deployment_pass(tmp_path):
    a=fixture_a(tmp_path,installed_head=False)
    missing=a/"runtime"/"live"/"owner_image"/"image_attempts.sqlite"
    missing.unlink()
    r=inspect_a_runtime(a,fixture_mode=True)
    assert r["expected_source_match"]=="HOLD"
    assert r["ledgers"]["image"]["gate"]=="HOLD"
    assert r["qa_deployment_readiness_gate"]=="HOLD"
    assert r["deployment_preflight_gate"]=="HOLD"
    assert r["signed_sso_gate"]=="NOT_AUDITED"
    assert r["paid_worker"]=="HOLD"


@pytest.mark.parametrize(("ledger","field"), (
    ("cost","receipt"),("image","result_json")
))
def test_unpriced_without_receipt_or_success_without_image_result_holds(
    tmp_path,ledger,field,
):
    a=fixture_a(tmp_path)
    spec=LEDGERS[ledger]
    with sqlite3.connect(a.joinpath(*spec["path"])) as db:
        db.execute(f"UPDATE {spec['table']} SET {field}=NULL")
    result=inspect_a_runtime(a,fixture_mode=True)
    assert result["ledgers"][ledger]["gate"]=="HOLD"
    assert result["ledgers"][ledger]["reason"]=="LEDGER_INVALID_COLUMN_VALUE"


def test_exact_fixture_root_symlink_to_fake_protected_b_rejected(tmp_path):
    a=fixture_a(tmp_path)
    fake_b=tmp_path/"ittem-bp18-product-completion-20261111"
    fake_b.mkdir()
    a.rename(tmp_path/"quarantined_original_fixture_A")
    a.symlink_to(fake_b,target_is_directory=True)
    with pytest.raises(ValueError,match="NOT_A_TRACK_RUNTIME_ROOT"):
        inspect_a_runtime(a,fixture_mode=True)


# A3R.1 SOURCE_ATTESTATION_FALSE_PASS negative regression suite.
# Git archive -> fresh Git repository. Never manipulate real Track A/B index.

@pytest.fixture()
def _isolated_head_archive(tmp_path, monkeypatch):
    import io
    import subprocess
    import tarfile
    import scripts.a3_track_a_guarded_readiness as module

    archive = subprocess.check_output(
        ("git", "-C", str(module.ROOT), "archive", "--format=tar", "HEAD")
    )
    dest = tmp_path / "isolated-archive"
    dest.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tf:
        tf.extractall(dest, filter="data")
    def run(*args):
        return subprocess.check_output(
            ("git", "-C", str(dest), *args),
            stderr=subprocess.PIPE, text=True,
        ).strip()
    run("init", "-q", "-b", module.BRANCH)
    run("add", "-A")
    run("-c", "user.name=Isolated Test",
        "-c", "user.email=isolated@example.invalid",
        "-c", "core.hooksPath=/dev/null",
        "commit", "-q", "-m", "isolated-archive-candidate")
    monkeypatch.setattr(module, "ROOT", dest)
    assert run("status","--porcelain")==""
    return dest, run, module


def test_a3r1_clean_all_370_head_blobs_and_archive_hash_pass(
    _isolated_head_archive,
):
    root, git_run, module = _isolated_head_archive
    manifest = module.source_manifest()
    proof = manifest["tracked_source_attestation"]
    assert proof["gate"]=="PASS", proof
    assert proof["index_flags_gate"]=="PASS"
    assert proof["checked_files"]==proof["head_files"]>=370
    assert manifest["source_integrity_gate"]=="PASS"
    assert manifest["source_gate"]=="PASS"
    assert manifest["git_status_clean"] is True
    assert manifest["worktree_clean"] is True
    assert manifest["lock_integrity_gate"]=="PASS"
    assert manifest["a3_evidence_integrity_gate"]=="PASS"
    assert manifest["a3r_evidence_integrity_gate"]=="PASS"
    assert len(manifest["locks_sha256"])==5
    assert len(manifest["test_evidence_sha256"])==6
    assert len(manifest["a3r_test_evidence_sha256"])==7
    build=manifest["build_provenance"]
    assert build["source_commit"]==git_run("rev-parse","HEAD")
    assert build["source_tree"]==git_run("rev-parse","HEAD^{tree}")
    assert len(build["expected_git_archive_sha256"])==64
    assert build["verified_head_files"]==proof["checked_files"]
    assert build["built_artifact_sha256"] is None
    assert build["running_build_sha256"] is None
    assert build["build_runtime_match_gate"]=="NOT_AUDITED"
    assert manifest["qa_deployment_readiness_gate"]=="HOLD"
    assert manifest["paid_worker_authorization_gate"]=="HOLD"


@pytest.mark.parametrize(("flag","undo"), (
    ("--assume-unchanged","--no-assume-unchanged"),
    ("--skip-worktree","--no-skip-worktree"),
))
def test_a3r1_hidden_serving_worker_change_fails_closed(
    _isolated_head_archive, flag, undo,
):
    root, run, module = _isolated_head_archive
    worker=root/"demo_staging"/"live"/"worker.py"
    original=worker.read_bytes()
    try:
        run("update-index",flag,"demo_staging/live/worker.py")
        worker.write_bytes(original+b"\n# ISOLATED_A3R1_HIDDEN_WORKER_MUTATION\n")
        # Demonstrates the precise C-A3R bypass: Git status is false-clean.
        assert run("status","--porcelain")==""
        result=module.source_manifest()
        assert result["git_status_clean"] is True
        assert result["worktree_clean"] is False
        assert result["source_integrity_gate"]=="HOLD"
        assert result["tracked_source_attestation"]["gate"]=="HOLD"
        assert result["tracked_source_attestation"]["index_flags_gate"]=="HOLD"
        assert result["paid_worker_authorization_gate"]=="HOLD"
    finally:
        worker.write_bytes(original)
        run("update-index",undo,"demo_staging/live/worker.py")
    assert run("status","--porcelain")==""


@pytest.mark.parametrize("source", (
    "demo_staging/live/http_api.py",
    "src/text_generation/compliance/rule_checker.py",
    "src/image_generation/provider_attempts.py",
    "app/src/main.tsx",
))
def test_a3r1_attests_full_serving_text_image_and_frontend(
    _isolated_head_archive, source,
):
    root, run, module = _isolated_head_archive
    target=root/source
    assert target.is_file(), "Required Owner or Serving source missing in HEAD"
    old=target.read_bytes()
    target.write_bytes(old+b"\nISOLATED_A3R1_TAMPER")
    try:
        assert module.source_manifest()["source_integrity_gate"]=="HOLD"
    finally:
        target.write_bytes(old)


def test_a3r1_deleted_source_and_symbolic_link_not_pass(
    _isolated_head_archive,
):
    root, run, module = _isolated_head_archive
    rel="demo_staging/live/worker.py"
    f=root/rel
    original=f.read_bytes()
    f.unlink()
    try:
        assert module.source_manifest()["source_integrity_gate"]=="HOLD"
        f.symlink_to(root/"README.md")
        assert module.source_manifest()["source_integrity_gate"]=="HOLD"
    finally:
        f.unlink()
        f.write_bytes(original)
    assert run("status","--porcelain")==""


def test_a3r1_special_index_flag_alone_is_not_a_clean_source(
    _isolated_head_archive,
):
    root, run, module=_isolated_head_archive
    rel="demo_staging/live/worker.py"
    run("update-index","--assume-unchanged",rel)
    try:
        manifest=module.source_manifest()
        assert manifest["git_status_clean"] is True
        assert manifest["source_integrity_gate"]=="HOLD"
    finally:
        run("update-index","--no-assume-unchanged",rel)


def test_a3r1_missing_A3R_evidence_is_hold(_isolated_head_archive):
    root, run, module=_isolated_head_archive
    f=root/module.A3R_EVIDENCE[0]
    data=f.read_bytes()
    f.unlink()
    try:
        m=module.source_manifest()
        assert m["a3r_evidence_integrity_gate"]=="HOLD"
        assert m["source_integrity_gate"]=="HOLD"
    finally:
        f.write_bytes(data)


def test_a3r1_ignored_git_status_can_not_mask_attestation(
    _isolated_head_archive,
    monkeypatch,
):
    root, run, module=_isolated_head_archive
    worker=root/"demo_staging"/"live"/"worker.py"
    orig=worker.read_bytes()
    worker.write_bytes(orig+b"\n# MUTATION\n")
    monkeypatch.setattr(module,"git",
                        lambda *a: ("" if a==("status","--porcelain")
                                    else run(*a)))
    try:
        m=module.source_manifest()
        assert m["git_status_clean"] is True
        assert m["source_integrity_gate"]=="HOLD"
        assert m["tracked_source_attestation"]["gate"]=="HOLD"
    finally:
        worker.write_bytes(orig)
