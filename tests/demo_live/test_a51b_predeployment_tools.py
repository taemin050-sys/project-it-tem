"""A5-1B private-media inventory and GCP three-ledger READ ONLY tests."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT=Path(__file__).resolve().parents[2]


def module(path,name):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    obj=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def test_a51b_gcp_a_probe_does_not_create_missing_provider_db(tmp_path):
    m=module("scripts/a51b_gcp_a_readonly_ledger_probe.py","readonly_probe")
    runtime=tmp_path/"gcp-a"
    repo=runtime/"repo"
    base=runtime/"runtime"/"live"
    repo.mkdir(parents=True);base.mkdir(parents=True)
    (repo/"SOURCE_SHA.txt").write_text("9879eb0f85747312a224ecd898aaff84d834590b\n")
    for f,table,col,items in [
        ("live.sqlite","live_image_attempts","state",
         ["COMPLETED"]*8),
        ("queue.sqlite","queued_ops","state",[]),
        ("cost.sqlite","attempts","status",[]),
    ]:
        with sqlite3.connect(str(base/f)) as db:
            db.execute(f'CREATE TABLE {table} ({col} TEXT)')
            db.executemany(f'INSERT INTO {table} VALUES (?)',[(x,) for x in items])
    before={x.relative_to(runtime):hashlib.sha256(x.read_bytes()).hexdigest()
            for x in runtime.rglob("*") if x.is_file()}
    result=m.inspect(runtime)
    assert result["source_sha_observed"]=="9879eb0f85747312a224ecd898aaff84d834590b"
    assert result["ledgers"]["app"]["row_count"]==8
    assert result["ledgers"]["app"]["states"]=={"COMPLETED":8}
    assert result["ledgers"]["queue"]["row_count"]==0
    assert result["ledgers"]["cost"]["row_count"]==0
    assert result["ledgers"]["owner_provider"]["exists"] is False
    assert result["ledgers"]["owner_provider"]["schema"]=="MISSING_NOT_MIGRATED"
    assert result["conditions"]["owner_provider_attempt_table_mapped"] is False
    assert result["beta_ready"] is False and result["paid_worker_authorized"] is False
    assert result["provider_attempt_store_creation_or_migration_performed"] is False
    after={x.relative_to(runtime):hashlib.sha256(x.read_bytes()).hexdigest()
           for x in runtime.rglob("*") if x.is_file()}
    assert before==after
    assert not (base/"owner_image").exists()


def test_a51b_gcp_readonly_missing_schema_never_initializes_files(tmp_path):
    m=module("scripts/a51b_gcp_a_readonly_ledger_probe.py","readonly_probe_missing")
    root=tmp_path/"gcp-a"
    root.mkdir()
    report=m.inspect(root)
    assert all(x["exists"] is False for x in report["ledgers"].values())
    assert list(root.iterdir())==[]


def test_a51b_metadata_only_grouping_and_duplicate_gates(tmp_path):
    m=module("scripts/a51b_local_product_cohort_audit.py","photo_inventory")
    source=tmp_path/"source"
    source.mkdir()
    for name,shade in (
        ("ProductA-1.jpg",80),("ProductA-2.jpg",130),
        ("ProductB-1.jpg",200)):
        Image.new("RGB",(640,640),(shade,shade,shade)).save(source/name,"JPEG")
    (source/"ProductA-3.jpg").write_bytes((source/"ProductA-2.jpg").read_bytes())
    before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()}
    inventory=m.analyze(source)
    assert inventory["file_count"]==4
    assert inventory["groups_total"]==2
    assert inventory["duplicate_bytes_pairs"]==1
    assert inventory["file_container_counts"]=={"JPEG":4,"MPO":0}
    assert inventory["multi_frame_mpo_files"]==0
    a,b=inventory["groups"]
    assert a["group"]=="ProductA" and b["group"]=="ProductB"
    assert a["unique_images"]==2
    assert len(a["suggested_2_to_5_photo_filenames"])==2
    assert b["gate"]=="INSUFFICIENT_DISTINCT_PHOTOS"
    assert inventory["external_provider_allowed"] is False
    assert inventory["source_image_copies_exported"] is False
    assert before=={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in source.iterdir()}


def test_a51b_inventory_cli_refuses_source_overwrite(tmp_path):
    src=tmp_path/"photos";src.mkdir()
    Image.new("RGB",(640,640)).save(src/"Sample-1.jpg","JPEG")
    command=[sys.executable,"-B",str(ROOT/"scripts/a51b_local_product_cohort_audit.py"),
             "--source",str(src),"--out",str(src/"report.json")]
    proc=subprocess.run(command,text=True,capture_output=True,timeout=10)
    assert proc.returncode!=0
    assert "A51B_OUTPUT_INSIDE_SOURCE_FORBIDDEN" in proc.stderr
    assert not (src/"report.json").exists()


def test_a51b_actual_local_report_never_contains_original_private_root():
    report=ROOT/"docs/integration/evidence/A51B_20261110/LOCAL_PRODUCT_METADATA_ONLY.json"
    if not report.is_file():
        # Fixed independent archive contains metadata after evidence commit.
        return
    record=json.loads(report.read_text(encoding="utf8"))
    assert record["external_provider_allowed"] is False
    assert record["mpo_first_frame_automatically_selected"] is False
    assert record["mpo_canonicalized_or_exported"] is False
    assert "/Volumes/SSD 4T" not in report.read_text()
    assert record["source_image_copies_exported"] is False
