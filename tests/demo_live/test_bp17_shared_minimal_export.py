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
                   "receipt_json text,receipt_sha text,envelope_json text,"
                   "envelope_sha text,final_sha text,caption_sha text)")
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
            envelope='{"proof":"fixture-envelope"}'
            db.execute("insert into live_compose_manifests values(?,?,?,?,?,?,?)",
                (jid,receipt.decode(),rsha,envelope,
                 hashlib.sha256(envelope.encode()).hexdigest(),fsha,csha))
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

def test_missing_manifest_fails_closed(tmp_path,monkeypatch):
    root=make_fixture(tmp_path,monkeypatch)
    with sqlite3.connect(root/"runtime/live/live.sqlite") as db:
        db.execute("delete from live_compose_manifests where job_id=?",(ONE,))
    out=tmp_path/"missing_manifest"
    with pytest.raises(ValueError,match="SHARED_RECEIPT_MANIFEST_MISSING"):
        projection.run(root,out)
    assert not out.exists()

def test_receipt_missing_or_tampered_fails_closed(tmp_path,monkeypatch):
    root=make_fixture(tmp_path,monkeypatch)
    receipt=root/"runtime/live/outputs"/ONE/"receipt.json"
    receipt.unlink()
    with pytest.raises(ValueError,match="SHARED_RECEIPT_MANIFEST_MISMATCH"):
        projection.run(root,tmp_path/"missing")
    receipt.write_bytes(b'{"state":"TAMPERED"}')
    with pytest.raises(ValueError,match="SHARED_RECEIPT_MANIFEST_MISMATCH"):
        projection.run(root,tmp_path/"tampered")
    assert not (tmp_path/"missing").exists()
    assert not (tmp_path/"tampered").exists()

def test_job_vs_share_sha_and_incomplete_job_fail_closed(tmp_path,monkeypatch):
    root=make_fixture(tmp_path,monkeypatch)
    dbfile=root/"runtime/live/live.sqlite"
    with sqlite3.connect(dbfile) as db:
        db.execute("update live_jobs set final_sha=? where job_id=?",("f"*64,ONE))
    with pytest.raises(ValueError,match="SHARED_OWNER_OR_ARTIFACT_LEDGER_CONFLICT"):
        projection.run(root,tmp_path/"wrong_sha")
    with sqlite3.connect(dbfile) as db:
        db.execute("update live_jobs set final_sha=(select final_sha from "
                   "live_compose_manifests where job_id=?) where job_id=?",(ONE,ONE))
        db.execute("update live_jobs set state='IMAGE_REJECTED' where job_id=?",(ONE,))
    with pytest.raises(ValueError,match="SHARED_OWNER_OR_ARTIFACT_LEDGER_CONFLICT"):
        projection.run(root,tmp_path/"incomplete")

def test_receipt_manifest_wrong_digest_fails_closed(tmp_path,monkeypatch):
    root=make_fixture(tmp_path,monkeypatch)
    with sqlite3.connect(root/"runtime/live/live.sqlite") as db:
        db.execute("update live_compose_manifests set receipt_sha=? "
                   "where job_id=?",("0"*64,ONE))
    with pytest.raises(ValueError,match="SHARED_RECEIPT_MANIFEST_MISMATCH"):
        projection.run(root,tmp_path/"wrong_receipt_sha")

def test_existing_output_replaced_never_after_concurrent_publication(
    tmp_path,monkeypatch
):
    import multiprocessing
    root=make_fixture(tmp_path,monkeypatch)
    output=tmp_path/"racy_publication"
    ctx=multiprocessing.get_context("fork")
    barrier=ctx.Barrier(2)
    queue=ctx.Queue()
    def worker():
        old=projection._publish_no_replace
        def synchronized(tmp,final):
            barrier.wait(timeout=15)
            return old(tmp,final)
        projection._publish_no_replace=synchronized
        try:
            projection.run(root,output)
            queue.put("PUBLISHED")
        except FileExistsError:
            queue.put("EXISTS")
        except Exception as exc:
            queue.put(f"FAIL:{type(exc).__name__}:{exc}")
    processes=[ctx.Process(target=worker) for _ in range(2)]
    for p in processes:p.start()
    for p in processes:p.join(25)
    assert all(p.exitcode==0 for p in processes)
    assert sorted([queue.get(timeout=5),queue.get(timeout=5)])==["EXISTS","PUBLISHED"]
    assert hashlib.sha256((output/"final_ads"/ONE/"final.png").read_bytes()).hexdigest()==(
        json.loads((output/"projection_manifest.json").read_text())
        ["shared_final_adverts"][0]["final_sha256"])
    assert not list(tmp_path.glob(".bp17_export_incomplete_*"))

def test_atomic_exclusive_publish_disallows_existing_nonempty_directory(
    tmp_path,monkeypatch
):
    root=make_fixture(tmp_path,monkeypatch)
    output=tmp_path/"protected";output.mkdir()
    sentinel=output/"DO_NOT_TOUCH";sentinel.write_text("immutable")
    before=hashlib.sha256(sentinel.read_bytes()).hexdigest()
    # Force a "pre-check passed" scenario to prove the atomic syscall is the guard.
    monkeypatch.setattr(Path,"exists",lambda p:False if p==output else
                        p.is_file() or p.is_dir())
    with pytest.raises(FileExistsError,match="DESTINATION_MUST_BE_NEW"):
        projection.run(root,output)
    assert hashlib.sha256(sentinel.read_bytes()).hexdigest()==before
    assert not list(tmp_path.glob(".bp17_export_incomplete_*"))

def test_destination_symlink_must_never_be_followed(tmp_path,monkeypatch):
    root=make_fixture(tmp_path,monkeypatch)
    outside=tmp_path/"outside";outside.mkdir()
    (outside/"existing").write_text("preserve")
    destination=tmp_path/"linkdest";destination.symlink_to(outside,target_is_directory=True)
    with pytest.raises(FileExistsError,match="DESTINATION_MUST_BE_NEW"):
        projection.run(root,destination)
    assert (outside/"existing").read_text()=="preserve"
    assert not list(tmp_path.glob(".bp17_export_incomplete_*"))

def test_fault_injection_pre_publish_keeps_target_absent_and_cleans_temp(
    tmp_path,monkeypatch
):
    root=make_fixture(tmp_path,monkeypatch)
    original=projection._publish_no_replace
    def fail_pre_publish(staged,target):
        assert staged.is_dir() and not target.exists()
        raise OSError("TEST_PROCESS_FAILED_BEFORE_ATOMIC_PUBLISH")
    monkeypatch.setattr(projection,"_publish_no_replace",fail_pre_publish)
    final=tmp_path/"unpublished"
    with pytest.raises(OSError,match="TEST_PROCESS_FAILED_BEFORE_ATOMIC_PUBLISH"):
        projection.run(root,final)
    assert not final.exists()
    assert not list(tmp_path.glob(".bp17_export_incomplete_*"))
    monkeypatch.setattr(projection,"_publish_no_replace",original)
    projection.run(root,final)
    assert (final/"projection_manifest.json").is_file()

def test_parent_path_symlink_swap_fails_and_cleans_old_inode_stage(
    tmp_path,monkeypatch
):
    """A racing path swap cannot publish into an attacker-controlled directory.
    Temporary private files are deleted via original parent dirfd, not symlink.
    """
    root=make_fixture(tmp_path,monkeypatch)
    parent=tmp_path/"review_parent";parent.mkdir()
    moved=tmp_path/"moved_original_parent"
    outside=tmp_path/"outside_destination";outside.mkdir()
    final=parent/"output"
    old=projection._publish_no_replace
    def path_swapped(staged,target):
        parent.rename(moved)
        parent.symlink_to(outside,target_is_directory=True)
        return old(staged,target)
    monkeypatch.setattr(projection,"_publish_no_replace",path_swapped)
    try:
        with pytest.raises(OSError):
            projection.run(root,final)
        assert not (outside/"output").exists()
        assert not list(moved.glob(".bp17_export_incomplete_*"))
    finally:
        parent.unlink()
        moved.rename(parent)

def test_manifest_db_receipt_and_envelope_metadata_mutations_rejected(
    tmp_path,monkeypatch
):
    root=make_fixture(tmp_path,monkeypatch)
    db=root/"runtime/live/live.sqlite"
    with sqlite3.connect(db) as c:
        c.execute("update live_compose_manifests set receipt_json=? "
                  "where job_id=?",('{"state":"tampered_db"}',ONE))
    with pytest.raises(ValueError,match="SHARED_RECEIPT_MANIFEST_MISMATCH"):
        projection.run(root,tmp_path/"tampered_db_receipt")
    with sqlite3.connect(db) as c:
        c.execute("update live_compose_manifests set receipt_json=? "
                  "where job_id=?",('{"state":"succeeded"}',ONE))
        c.execute("update live_compose_manifests set envelope_sha=? "
                  "where job_id=?",("0"*64,ONE))
    with pytest.raises(ValueError,match="SHARED_RECEIPT_MANIFEST_MISMATCH"):
        projection.run(root,tmp_path/"tampered_envelope")
    assert not list(tmp_path.glob(".bp17_export_incomplete_*"))
