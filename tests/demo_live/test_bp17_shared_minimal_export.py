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

def _competing_projection_worker(source_root, destination, barrier, queue):
    """Fresh child interpreter: never fork an initialized pytest/SQLite/PIL.

    This still races two independent real export processes at the atomic
    no-replace syscall, not mocks of file publication.
    """
    # The test fixture's allowlist is intentionally in-memory; spawn does
    # not inherit monkeypatch from pytest. Grant only this temporary fixture.
    source_root=Path(source_root)
    destination=Path(destination)
    projection.ALLOWED_ROOTS=frozenset({source_root.resolve()})
    original=projection._publish_no_replace
    def synchronized(parent_fd,stage_name,target_name):
        barrier.wait(timeout=15)
        return original(parent_fd,stage_name,target_name)
    projection._publish_no_replace=synchronized
    try:
        projection.run(source_root,destination)
        queue.put("PUBLISHED")
    except FileExistsError:
        queue.put("EXISTS")
    except Exception as error:
        queue.put(f"FAIL:{type(error).__name__}:{error}")


@pytest.mark.parametrize("start_method", ("spawn", "forkserver"))
def test_existing_output_replaced_never_after_concurrent_publication(
    tmp_path,monkeypatch,start_method
):
    import multiprocessing
    root=make_fixture(tmp_path,monkeypatch)
    output=tmp_path/"racy_publication"
    # macOS/Python 3.12: fork after pytest/PIL/SQLite/ObjC initialization
    # can crash before reaching the publication barrier. Use an independent
    # interpreter per contender; NEVER weaken the two-winner race assertion.
    # Verify both independent interpreter startup and fresh forkserver.
    # Neither may fork the populated pytest parent.
    ctx=multiprocessing.get_context(start_method)
    barrier=ctx.Barrier(2)
    queue=ctx.Queue()
    processes=[ctx.Process(target=_competing_projection_worker,
                           args=(str(root),str(output),barrier,queue))
               for _ in range(2)]
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
    def fail_pre_publish(pfd,stage_name,target_name):
        import os,stat
        assert stat.S_ISDIR(os.stat(stage_name,dir_fd=pfd).st_mode)
        assert target_name=="unpublished"
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
    def path_swapped(pfd,stage_name,target_name):
        parent.rename(moved)
        parent.symlink_to(outside,target_is_directory=True)
        return old(pfd,stage_name,target_name)
    monkeypatch.setattr(projection,"_publish_no_replace",path_swapped)
    try:
        with pytest.raises(RuntimeError,match="PUBLISHED_BUT_UNVERIFIED_MANUAL_RECONCILIATION"):
            projection.run(root,final)
        assert not (outside/"output").exists()
        assert (moved/"output"/"projection_manifest.json").is_file()
        assert not list(moved.glob(".bp17_export_incomplete_*"))
    finally:
        if parent.is_symlink():parent.unlink()
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

# B″ P2-05 hardened directory-object tests. All attacks below act only
# against ephemeral, fake-photo test fixture directories.
def test_p205_r1_swap_before_mkdirat_has_no_external_stage_or_private_orphan(
    tmp_path,monkeypatch
):
    root=make_fixture(tmp_path,monkeypatch)
    parent=tmp_path/"entry";parent.mkdir()
    detached=tmp_path/"old_parent"
    real_create=projection._create_stage
    def swap_before_stage(parent_fd):
        parent.rename(detached)
        parent.mkdir()
        return real_create(parent_fd)
    monkeypatch.setattr(projection,"_create_stage",swap_before_stage)
    with pytest.raises(ValueError,match="DESTINATION_PARENT_PATH_UNSTABLE"):
        projection.run(root,parent/"output")
    assert not (parent/"output").exists()
    assert not (detached/"output").exists()
    assert not list(parent.glob(".bp17_export_incomplete_*"))
    assert not list(detached.glob(".bp17_export_incomplete_*"))
    assert not list(parent.rglob("final.png"))
    assert not list(parent.rglob("caption.txt"))

def test_p205_r2_and_r4_real_parent_swap_fake_same_stage_name_not_published(
    tmp_path,monkeypatch
):
    root=make_fixture(tmp_path,monkeypatch)
    parent=tmp_path/"entry";parent.mkdir()
    detached=tmp_path/"real_parent"
    original=projection._publish_no_replace
    fake_sha="none"
    def attack(parent_fd,stage_name,dest_name):
        nonlocal fake_sha
        parent.rename(detached)
        parent.mkdir()
        forged=parent/stage_name
        forged.mkdir()
        (forged/"projection_manifest.json").write_text('{"forged":"RACE-A"}')
        fake_sha=projection.sha((forged/"projection_manifest.json").read_bytes())
        return original(parent_fd,stage_name,dest_name)
    monkeypatch.setattr(projection,"_publish_no_replace",attack)
    with pytest.raises(RuntimeError,match="PUBLISHED_BUT_UNVERIFIED_MANUAL_RECONCILIATION"):
        projection.run(root,parent/"published")
    assert not (parent/"published").exists()
    assert len(list(parent.glob(".bp17_export_incomplete_*")))==1  # attacker dummy ONLY
    assert (detached/"published"/"projection_manifest.json").is_file()
    assert not list(detached.glob(".bp17_export_incomplete_*"))
    true_sha=projection.sha((detached/"published"/"projection_manifest.json").read_bytes())
    assert true_sha!=fake_sha
    assert json.loads((detached/"published"/"projection_manifest.json").read_text()
        )["schema_version"]=="bp17-published-final-projection-v1"

def test_p205_r3_post_publish_replaced_path_cannot_return_forged_manifest(
    tmp_path,monkeypatch
):
    root=make_fixture(tmp_path,monkeypatch)
    parent=tmp_path/"entry";parent.mkdir()
    detached=tmp_path/"real_parent"
    original=projection._publish_no_replace
    def move_after_publish(parent_fd,stage_name,dest_name):
        original(parent_fd,stage_name,dest_name)
        parent.rename(detached)
        parent.mkdir()
        fake=(parent/dest_name);fake.mkdir()
        (fake/"projection_manifest.json").write_text('{"fake":"post-publish"}')
    monkeypatch.setattr(projection,"_publish_no_replace",move_after_publish)
    with pytest.raises(RuntimeError,match="PUBLISHED_BUT_UNVERIFIED_MANUAL_RECONCILIATION"):
        projection.run(root,parent/"published")
    assert json.loads((parent/"published"/"projection_manifest.json").read_text())=={
        "fake":"post-publish"}
    assert json.loads((detached/"published"/"projection_manifest.json").read_text()
        )["schema_version"]=="bp17-published-final-projection-v1"
    assert not list(detached.glob(".bp17_export_incomplete_*"))

def test_p205_r6_parent_object_swap_without_symlink_rejected(
    tmp_path,monkeypatch
):
    root=make_fixture(tmp_path,monkeypatch)
    parent=tmp_path/"entry";parent.mkdir()
    detached=tmp_path/"real_parent"
    real_create=projection._create_stage
    def change_parent_object(parent_fd):
        name,fd=real_create(parent_fd)
        parent.rename(detached)
        parent.mkdir()
        return name,fd
    monkeypatch.setattr(projection,"_create_stage",change_parent_object)
    with pytest.raises(ValueError,match="DESTINATION_PARENT_PATH_UNSTABLE"):
        projection.run(root,parent/"published")
    assert not list(detached.glob(".bp17_export_incomplete_*"))
    assert not list(parent.glob(".bp17_export_incomplete_*"))
    assert not (parent/"published").exists()

def test_p205_late_post_publish_error_keeps_genuine_published_inode(
    tmp_path,monkeypatch
):
    root=make_fixture(tmp_path,monkeypatch)
    parent=tmp_path/"entry";parent.mkdir()
    original=projection._publish_no_replace
    def publish_then_fail(parent_fd,stage_name,dest_name):
        original(parent_fd,stage_name,dest_name)
        raise OSError("TEST_LATE_FSYNC_ERROR")
    monkeypatch.setattr(projection,"_publish_no_replace",publish_then_fail)
    final=parent/"published"
    with pytest.raises(RuntimeError,match="PUBLISHED_BUT_UNVERIFIED_MANUAL_RECONCILIATION"):
        projection.run(root,final)
    assert (final/"projection_manifest.json").is_file()
    assert not list(parent.glob(".bp17_export_incomplete_*"))
    assert len(list(final.rglob("final.png")))==1

def test_p205_insecure_group_world_writable_parent_fails_before_stage(
    tmp_path,monkeypatch
):
    root=make_fixture(tmp_path,monkeypatch)
    parent=tmp_path/"insecure";parent.mkdir()
    parent.chmod(0o777)
    try:
        with pytest.raises(ValueError,match="DESTINATION_PARENT_WRITABLE_BY_OTHER_PRINCIPALS"):
            projection.run(root,parent/"published")
        assert not list(parent.iterdir())
    finally:
        parent.chmod(0o700)

def test_p205_openat_failure_after_mkdirat_removes_empty_stage(
    tmp_path,monkeypatch
):
    import os
    root=make_fixture(tmp_path,monkeypatch)
    parent=tmp_path/"secure_parent";parent.mkdir()
    original_open=os.open
    def fail_first_stage_open(path,flags,*args,**kwargs):
        if isinstance(path,str) and path.startswith(".bp17_export_incomplete_"):
            raise OSError("TEST_STAGE_FD_OPEN_FAILED")
        return original_open(path,flags,*args,**kwargs)
    monkeypatch.setattr(os,"open",fail_first_stage_open)
    with pytest.raises(OSError,match="TEST_STAGE_FD_OPEN_FAILED"):
        projection.run(root,parent/"out")
    assert not list(parent.glob(".bp17_export_incomplete_*"))
    assert not (parent/"out").exists()

def test_p205_stage_fchmod_failure_before_return_does_not_orphan(
    tmp_path,monkeypatch
):
    import os
    root=make_fixture(tmp_path,monkeypatch)
    parent=tmp_path/"secure_parent";parent.mkdir()
    def fail_fchmod(fd,mode):
        raise OSError("INJECT_STAGE_FCHMOD_FAILURE")
    monkeypatch.setattr(os,"fchmod",fail_fchmod)
    with pytest.raises(OSError,match="INJECT_STAGE_FCHMOD_FAILURE"):
        projection.run(root,parent/"out")
    assert not list(parent.glob(".bp17_export_incomplete_*"))
    assert not (parent/"out").exists()

def test_p205_nested_directory_fchmod_failure_cleans_complete_stage(
    tmp_path,monkeypatch
):
    import os
    root=make_fixture(tmp_path,monkeypatch)
    parent=tmp_path/"secure_parent";parent.mkdir()
    original=os.fchmod
    calls=[0]
    def fail_second(fd,mode):
        calls[0]+=1
        if calls[0]==2:
            raise OSError("INJECT_CHILD_DIR_FCHMOD_FAILURE")
        return original(fd,mode)
    monkeypatch.setattr(os,"fchmod",fail_second)
    with pytest.raises(OSError,match="INJECT_CHILD_DIR_FCHMOD_FAILURE"):
        projection.run(root,parent/"out")
    assert calls[0]>=2
    assert not list(parent.glob(".bp17_export_incomplete_*"))
    assert not (parent/"out").exists()
