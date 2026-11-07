"""Data minimization is a new offline projection, never an in-place DB scrub."""
import hashlib
import json
import sqlite3
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image
from scripts import bp17_shared_ad_minimal_export as projection

ONE="a"*32
UNSHARED="b"*32
ACTOR="private_actor"
SECRET="DO_NOT_EXPORT_SENSITIVE_PRIVATE_PRODUCT_RESEARCH"

def make_fixture(tmp_path,monkeypatch):
    root=tmp_path/"ittem-bp17-final-qa-20261107"
    live=root/"runtime/live"
    live.mkdir(parents=True)
    (root/"repo").mkdir()
    (root/"repo/SOURCE_SHA.txt").write_text("c"*40)
    with sqlite3.connect(root/"runtime/demo.sqlite3") as db:
        db.execute("create table jobs(job_id text,actor text)")
        db.executemany("insert into jobs values (?,?)",[(ONE,ACTOR),(UNSHARED,ACTOR)])
    with sqlite3.connect(live/"live.sqlite") as db:
        db.execute("""create table live_jobs(job_id text,actor text,state text,
            mode text,final_sha text,caption_sha text,copy_sha text,
            review_sha text,approval_sha text,input_json text,
            analysis_json text,research_json text)""")
        db.execute("create table live_compose_manifests(job_id text,"
                   "receipt_sha text,final_sha text,caption_sha text)")
        image=BytesIO();Image.new("RGB",(180,240),"pink").save(image,"PNG")
        photo=image.getvalue();caption=b"Published approved final caption"
        fsha=hashlib.sha256(photo).hexdigest()
        csha=hashlib.sha256(caption).hexdigest()
        receipt=b'{"state":"succeeded"}';rsha=hashlib.sha256(receipt).hexdigest()
        for jid in (ONE,UNSHARED):
            db.execute("insert into live_jobs values (?,?,?,?,?,?,?,?,?,?,?,?)",
                (jid,ACTOR,"COMPLETED","LIVE",fsha,csha,"e"*64,"f"*64,
                 "d"*64,SECRET,SECRET,SECRET))
            folder=live/"outputs"/jid;folder.mkdir(parents=True)
            (folder/"final.png").write_bytes(photo)
            (folder/"caption.txt").write_bytes(caption)
            (folder/"receipt.json").write_bytes(receipt)
            db.execute("insert into live_compose_manifests values(?,?,?,?)",
                (jid,rsha,fsha,csha))
    with sqlite3.connect(live/"shares.sqlite") as db:
        db.execute("create table shared_live_results(job_id text,actor text,"
                   "final_sha text,caption_sha text,shared_at text)")
        db.execute("insert into shared_live_results values (?,?,?,?,?)",
            (ONE,ACTOR,fsha,csha,"2026-11-07 12:00:00"))
    monkeypatch.setattr(projection,"ALLOWED_ROOTS",frozenset({root.resolve()}))
    return root

def test_minimal_projection_excludes_private_payload_and_unshared(tmp_path,monkeypatch):
    root=make_fixture(tmp_path,monkeypatch)
    out=tmp_path/"published_only"
    result=projection.run(root,out)
    assert result["published_count"]==1
    manifest=json.loads((out/"projection_manifest.json").read_text())
    assert manifest["usable_as_operational_job_database"] is False
    assert manifest["contains_private_job_payload"] is False
    assert len(manifest["shared_final_adverts"])==1
    assert manifest["shared_final_adverts"][0]["job_id"]==ONE
    assert manifest["shared_final_adverts"][0]["pixels"]=={"width":180,"height":240}
    assert manifest["shared_final_adverts"][0]["final_sha256"]==hashlib.sha256(
        (out/"final_ads"/ONE/"final.png").read_bytes()).hexdigest()
    assert not (out/"final_ads"/UNSHARED).exists()
    assert not list(out.rglob("*.sqlite*"))
    assert SECRET not in (out/"projection_manifest.json").read_text()
    assert ACTOR not in (out/"projection_manifest.json").read_text()
    assert len(list(out.rglob("*.png")))==1
    # Original QA never modified.
    with sqlite3.connect(root/"runtime/live/live.sqlite") as db:
        assert db.execute("select count(*) from live_jobs").fetchone()[0]==2
        assert db.execute("select input_json from live_jobs where job_id=?",
                          (ONE,)).fetchone()[0]==SECRET

def test_corrupt_published_png_blocks_projection_without_orphan(tmp_path,monkeypatch):
    root=make_fixture(tmp_path,monkeypatch)
    (root/"runtime/live/outputs"/ONE/"final.png").write_bytes(b"tampered")
    out=tmp_path/"bad_projection"
    with pytest.raises(ValueError,match="SHARED_ARTIFACT_SHA_MISMATCH"):
        projection.run(root,out)
    assert not out.exists()

def test_published_actor_conflict_fails_closed(tmp_path,monkeypatch):
    root=make_fixture(tmp_path,monkeypatch)
    with sqlite3.connect(root/"runtime/live/shares.sqlite") as db:
        db.execute("update shared_live_results set actor='spoofed'")
    out=tmp_path/"spoofed_projection"
    with pytest.raises(ValueError,match="SHARED_OWNER_OR_ARTIFACT_LEDGER_CONFLICT"):
        projection.run(root,out)
    assert not out.exists()

def test_allowlist_destination_and_existing_export_guards(tmp_path,monkeypatch):
    root=make_fixture(tmp_path,monkeypatch)
    out=tmp_path/"result"
    projection.run(root,out)
    with pytest.raises(FileExistsError,match="DESTINATION_MUST_BE_NEW"):
        projection.run(root,out)
    with pytest.raises(ValueError,match="QA_SOURCE_NOT_ON_EXPLICIT_ALLOWLIST"):
        projection.run(tmp_path,tmp_path/"different")
    # A QA root symlink is rejected despite resolving to the allowed path.
    link=tmp_path/"unsafe_alias";link.symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError,match="QA_SOURCE_NOT_ON_EXPLICIT_ALLOWLIST"):
        projection.run(link,tmp_path/"via_alias")
