"""Nonbillable isolated B-only service prestart gate tests."""
import fcntl
import os
import socket
import sqlite3
from pathlib import Path
import pytest

from scripts.bp18_b5_release_prestart import validate, ReleaseUnsafe

OLD = "564e3731f949773836d0619e872a31d00ef355c3"
NEW = "2fd4b111e4ac64b178f81b9d0ccd8b06df1f8924"


def clone(tmp_path, *, epoch=1, target=NEW):
    root = tmp_path / "ittem-bp18-b-clone"
    for name in ("releases", "config", "runtime/live"):
        (root / name).mkdir(parents=True, exist_ok=True)
    for sha in (OLD,NEW):
        release = root/"releases"/sha
        (release/"demo_staging/live").mkdir(parents=True)
        (release/"demo_staging/live/store.py").write_text("# disabled tests only")
        (release/"SOURCE_SHA.txt").write_text(sha)
    (root/"repo").symlink_to("releases/"+target)
    (root/"config/epoch_capable_shas.txt").write_text(NEW+"\n")
    live = root/"runtime/live/live.sqlite"
    with sqlite3.connect(live) as db:
        if epoch:
            db.execute("CREATE TABLE live_policy_activation("
                       "singleton INT PRIMARY KEY, epoch INT,"
                       "policy_version TEXT, policy_sha TEXT)")
            db.execute("INSERT INTO live_policy_activation VALUES(1,?,'p','" +
                       "e"*64 + "')",(epoch,))
    with sqlite3.connect(root/"runtime/live/queue.sqlite") as db:
        db.execute("CREATE TABLE queued_ops(state TEXT)")
    return root


def test_latest_epoch_release_allowed_readonly(tmp_path):
    root=clone(tmp_path)
    before=(root/"runtime/live/live.sqlite").read_bytes()
    info=validate(root,mode="web",port=0)
    assert info["release"]==NEW and info["policy_epoch"]==1
    assert (root/"runtime/live/live.sqlite").read_bytes()==before


def test_old_binary_current_epoch_db_denied_before_start(tmp_path):
    root=clone(tmp_path,target=OLD)
    with pytest.raises(ReleaseUnsafe,match="OLD_RELEASE_CANNOT_START_WITH_EPOCH_DB"):
        validate(root,mode="web",port=0)


def test_old_binary_pre_epoch_backup_allowed_isolated_only(tmp_path):
    root=clone(tmp_path,epoch=0,target=OLD)
    assert validate(root,mode="web",port=0)["policy_epoch"]==0
    with pytest.raises(ReleaseUnsafe,match="WORKER_REQUIRES_INITIALIZED_EPOCH"):
        validate(root,mode="worker",port=0)


def test_queue_running_attempt_denied(tmp_path):
    root=clone(tmp_path)
    with sqlite3.connect(root/"runtime/live/queue.sqlite") as cx:
        cx.execute("INSERT INTO queued_ops VALUES('RUNNING')")
    with pytest.raises(ReleaseUnsafe,match="QUEUED_RUNNING_ATTEMPT_UNRESOLVED"):
        validate(root,mode="web",port=0)


def test_existing_provider_worker_lock_denies(tmp_path):
    root=clone(tmp_path)
    lock=root/"runtime/live/worker.lock"
    fd=os.open(lock,os.O_CREAT|os.O_RDWR,0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(ReleaseUnsafe,match="ACTIVE_PROVIDER_WORKER_BLOCKS_RELEASE"):
            validate(root,mode="web",port=0)
    finally:
        fcntl.flock(fd,fcntl.LOCK_UN)
        os.close(fd)


def test_wrong_release_metadata_denied(tmp_path):
    root=clone(tmp_path)
    (root/"releases"/NEW/"SOURCE_SHA.txt").write_text(OLD)
    with pytest.raises(ReleaseUnsafe,match="RELEASE_SHA_MISMATCH"):
        validate(root,mode="web",port=0)


def test_wrong_allowlist_not_whitelisted(tmp_path):
    root=clone(tmp_path)
    (root/"config/epoch_capable_shas.txt").write_text(OLD+"\n")
    with pytest.raises(ReleaseUnsafe,match="OLD_RELEASE_CANNOT_START_WITH_EPOCH_DB"):
        validate(root,mode="web",port=0)


def test_malformed_epoch_db_fail_closed(tmp_path):
    root=clone(tmp_path)
    db=root/"runtime/live/live.sqlite"
    db.write_bytes(b"not a sqlite database")
    with pytest.raises(ReleaseUnsafe,match="POLICY_DB_READ_FAILED"):
        validate(root,mode="web",port=0)


def test_external_release_path_denied(tmp_path):
    root=clone(tmp_path)
    (root/"repo").unlink()
    (root/"repo").symlink_to("../untrusted-code")
    with pytest.raises(ReleaseUnsafe,match="RELEASE_SYMLINK_OUTSIDE_ROOT"):
        validate(root,mode="web",port=0)


def test_reserved_web_port_must_be_free(tmp_path):
    root=clone(tmp_path)
    with socket.socket() as s:
        s.bind(("127.0.0.1",0))
        s.listen(1)
        with pytest.raises(ReleaseUnsafe,match="WEB_PORT_ALREADY_OCCUPIED"):
            validate(root,mode="web",port=s.getsockname()[1])


def test_untrusted_file_permissions_denied(tmp_path):
    root=clone(tmp_path)
    f=root/"config/epoch_capable_shas.txt"
    f.chmod(0o666)
    with pytest.raises(ReleaseUnsafe,match="RELEASE_METADATA_PERMISSIONS_INVALID"):
        validate(root,mode="web",port=0)


def test_worker_epoch_release_allowed_when_not_running(tmp_path):
    root=clone(tmp_path)
    assert validate(root,mode="worker",port=0)["mode"]=="worker"


def test_precheck_rejects_bad_target_without_mutating_live_symlink(tmp_path):
    root=clone(tmp_path,epoch=1,target=NEW)
    with pytest.raises(ReleaseUnsafe,match="OLD_RELEASE_CANNOT_START_WITH_EPOCH_DB"):
        validate(root,mode="web",port=0,target_override=OLD)
    assert os.readlink(root/"repo")=="releases/"+NEW


def test_precheck_valid_epoch_compatible_target_no_symlink_change(tmp_path):
    root=clone(tmp_path,epoch=1,target=OLD)
    result=validate(root,mode="web",port=0,target_override=NEW)
    assert result["release"]==NEW
    assert os.readlink(root/"repo")=="releases/"+OLD
