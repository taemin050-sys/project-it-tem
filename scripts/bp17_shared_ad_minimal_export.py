"""BP17-P2: allowlisted, offline, non-serving projection of ALREADY shared final ads.

Never modifies source QA or LIVE. Does NOT produce an auth-capable/serving
database. It is for privacy-minimal visual review and SHA replay only.
Usage: python scripts/bp17_shared_ad_minimal_export.py QA_ROOT FRESH_DEST
"""
from __future__ import annotations
import argparse
import ctypes
import errno
import sys
import hashlib
import json
import os
import sqlite3
import secrets
import stat
from contextlib import ExitStack
from pathlib import Path
from PIL import Image

ALLOWED_ROOTS=frozenset({
    Path("/home/macstudio/ittem-bp17-final-qa-20261107"),
    Path("/home/macstudio/ittem-bp17-shared-history-qa-20261107"),
})
MAX_PIXEL_COUNT=12_000_000

def sha(data:bytes)->str:
    return hashlib.sha256(data).hexdigest()

def read_db(path:Path):
    if not path.is_file() or path.is_symlink():
        raise ValueError("SOURCE_DB_NOT_REGULAR_FILE")
    canonical=path.resolve(strict=True)
    conn=sqlite3.connect(canonical.as_uri()+"?mode=ro",uri=True,timeout=5)
    try:
        conn.execute("PRAGMA query_only=ON")
        dbs=conn.execute("PRAGMA database_list").fetchall()
        if len(dbs)!=1 or Path(dbs[0][2]).resolve()!=canonical:
            raise ValueError("SOURCE_READ_ONLY_DB_PATH_MISMATCH")
    except BaseException:
        conn.close()
        raise
    conn.row_factory=sqlite3.Row
    return conn

def verified_png(data:bytes)->tuple[int,int]:
    from io import BytesIO
    if not data.startswith(bytes.fromhex("89504e470d0a1a0a")):
        raise ValueError("SHARED_IMAGE_NOT_PNG")
    with Image.open(BytesIO(data)) as im:
        width,height=im.size
        if im.format!="PNG" or min(width,height)<=0 or width*height>MAX_PIXEL_COUNT:
            raise ValueError("SHARED_IMAGE_DIMENSIONS_UNSAFE")
        im.verify()
    return (width,height)

DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW

def _inode(st):
    return st.st_dev,st.st_ino

def _same_stage_at(pfd:int,name:str,stage_fd:int)->bool:
    try:st=os.stat(name,dir_fd=pfd,follow_symlinks=False)
    except FileNotFoundError:return False
    return stat.S_ISDIR(st.st_mode) and _inode(st)==_inode(os.fstat(stage_fd))

def _assert_path_bound(parent:Path,pfd:int)->None:
    """Point-in-time check only; cannot prevent later ancestor renames."""
    try:
        path_st=os.stat(parent,follow_symlinks=False)
        if not stat.S_ISDIR(path_st.st_mode) or _inode(path_st)!=_inode(os.fstat(pfd)):
            raise ValueError("DESTINATION_PARENT_PATH_UNSTABLE")
    except OSError as error:
        raise ValueError("DESTINATION_PARENT_PATH_UNSTABLE") from error

def _create_stage(pfd:int)->tuple[str,int]:
    """mkdirat + openat on the ORIGINAL verified directory object."""
    for _ in range(4):
        name=".bp17_export_incomplete_"+secrets.token_hex(16)
        try:
            os.mkdir(name,0o700,dir_fd=pfd)
            break
        except FileExistsError:continue
    else:raise ValueError("STAGE_EXCLUSIVE_CREATION_FAILED")
    try:
        fd=os.open(name,DIR_FLAGS,dir_fd=pfd)
    except BaseException:
        # The stage is still empty: safely remove it through the parent FD.
        try:os.rmdir(name,dir_fd=pfd)
        except BaseException as error:
            raise RuntimeError(
                "STAGING_CREATION_CLEANUP_FAILED_MANUAL_RECONCILIATION"
            ) from error
        raise
    if not _same_stage_at(pfd,name,fd):
        os.close(fd)
        try:os.rmdir(name,dir_fd=pfd)
        except BaseException as error:
            raise RuntimeError(
                "STAGING_CREATION_CLEANUP_FAILED_MANUAL_RECONCILIATION"
            ) from error
        raise ValueError("STAGE_IDENTITY_CONFLICT")
    os.fchmod(fd,0o700)
    return name,fd

def _create_child_dir(parent_fd:int,name:str)->int:
    os.mkdir(name,0o700,dir_fd=parent_fd)
    fd=os.open(name,DIR_FLAGS,dir_fd=parent_fd)
    if not _same_stage_at(parent_fd,name,fd):
        os.close(fd)
        raise ValueError("STAGE_CHILD_IDENTITY_CONFLICT")
    os.fchmod(fd,0o700)
    return fd

def _write_at(dirfd:int,name:str,data:bytes)->None:
    fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,
               0o600,dir_fd=dirfd)
    try:
        with os.fdopen(fd,"wb",closefd=False) as handle:
            handle.write(data);handle.flush();os.fsync(fd)
        os.fchmod(fd,0o400)
        os.fsync(fd)
    finally:os.close(fd)

def _read_at(dirfd:int,name:str)->bytes:
    fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=dirfd)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("PUBLISHED_MANIFEST_NOT_REGULAR")
        with os.fdopen(fd,"rb",closefd=False) as handle:return handle.read()
    finally:os.close(fd)

def _publish_no_replace(pfd:int,stage_name:str,dest_name:str)->None:
    """Both rename arguments pinned by SAME Parent FD, never reopen pathname."""
    if (not isinstance(pfd,int) or pfd<0 or
        any(x in ("",".","..") or "/" in x for x in (stage_name,dest_name)) or
        stage_name==dest_name):
        raise ValueError("PUBLISH_PARENT_OR_SOURCE_INVALID")
    libc=ctypes.CDLL(None,use_errno=True)
    if sys.platform.startswith("linux"):
        fn=getattr(libc,"renameat2",None);bit=1
    elif sys.platform=="darwin":
        fn=getattr(libc,"renameatx_np",None);bit=0x00000004
    else:raise OSError(errno.ENOTSUP,"PLATFORM_NO_ATOMIC_NOREPLACE")
    if fn is None:raise OSError(errno.ENOTSUP,"ATOMIC_NOREPLACE_UNAVAILABLE")
    fn.argtypes=[ctypes.c_int,ctypes.c_char_p,
                 ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]
    fn.restype=ctypes.c_int
    if fn(pfd,os.fsencode(stage_name),pfd,os.fsencode(dest_name),bit):
        err=ctypes.get_errno()
        if err in (errno.EEXIST,errno.ENOTEMPTY):
            raise FileExistsError("DESTINATION_MUST_BE_NEW")
        raise OSError(err,os.strerror(err))
    os.fsync(pfd)

def _published_matches(pfd:int,dest_name:str,stage_fd:int)->bool:
    return _same_stage_at(pfd,dest_name,stage_fd)

def _remove_contents_fd(directory_fd:int)->None:
    """Portable openat/scandirat/unlinkat/rmdirat, never path-following cleanup.

    shutil.rmtree(dir_fd=...) is unavailable on the pinned GCP Python.
    Every recursive step opens and validates the child inode via O_NOFOLLOW.
    """
    with os.scandir(directory_fd) as entries:
        names=[entry.name for entry in entries]
    for name in names:
        st=os.stat(name,dir_fd=directory_fd,follow_symlinks=False)
        if stat.S_ISDIR(st.st_mode):
            child_fd=os.open(name,DIR_FLAGS,dir_fd=directory_fd)
            try:
                if _inode(os.fstat(child_fd))!=_inode(st):
                    raise RuntimeError("STAGING_CLEANUP_CHILD_IDENTITY_CHANGED")
                _remove_contents_fd(child_fd)
                if not _same_stage_at(directory_fd,name,child_fd):
                    raise RuntimeError("STAGING_CLEANUP_CHILD_IDENTITY_CHANGED")
                os.rmdir(name,dir_fd=directory_fd)
            finally:os.close(child_fd)
        else:
            os.unlink(name,dir_fd=directory_fd)
    os.fsync(directory_fd)


def _cleanup_original_stage(pfd:int,stage_name:str,stage_fd:int)->None:
    if not _same_stage_at(pfd,stage_name,stage_fd):
        raise RuntimeError("STAGING_OBJECT_MISSING_MANUAL_RECONCILIATION")
    _remove_contents_fd(stage_fd)
    if not _same_stage_at(pfd,stage_name,stage_fd):
        raise RuntimeError("STAGING_OBJECT_MISSING_MANUAL_RECONCILIATION")
    os.rmdir(stage_name,dir_fd=pfd)
    os.fsync(pfd)

def run(source:Path,destination:Path)->dict:
    src=source.resolve(strict=True)
    if src not in ALLOWED_ROOTS or source.is_symlink():
        raise ValueError("QA_SOURCE_NOT_ON_EXPLICIT_ALLOWLIST")
    if destination.name in ("",".",".."):
        raise ValueError("DESTINATION_UNSAFE")
    dest_requested=destination.absolute()
    if dest_requested.exists() or dest_requested.is_symlink():
        raise FileExistsError("DESTINATION_MUST_BE_NEW")
    parent=dest_requested.parent.resolve(strict=True)
    dest=parent/dest_requested.name
    if parent==src or src in parent.parents or parent==Path("/"):
        raise ValueError("DESTINATION_UNSAFE")
    if os.path.samefile(src,parent):
        raise ValueError("DESTINATION_UNSAFE")
    root=src/"runtime/live"
    with read_db(root/"shares.sqlite") as shares:
        rows=[dict(row) for row in shares.execute(
            "select job_id,actor,final_sha,caption_sha,shared_at "
            "from shared_live_results order by job_id")]
    if not rows:
        raise ValueError("SHARED_LEDGER_EMPTY")
    source_code_sha=(src/"repo/SOURCE_SHA.txt").read_text().strip()
    job_records=[]
    with read_db(root/"live.sqlite") as live, read_db(src/"runtime/demo.sqlite3") as owners:
        for entry in rows:
            jid=entry["job_id"]
            if len(jid)!=32 or any(ch not in "0123456789abcdef" for ch in jid):
                raise ValueError("INVALID_SHARED_JOB_ID")
            owner=owners.execute("select actor from jobs where job_id=?",(jid,)).fetchone()
            job=live.execute("select job_id,actor,state,mode,final_sha,caption_sha,"
                "copy_sha,review_sha,approval_sha from live_jobs where job_id=?",
                (jid,)).fetchone()
            manifest=live.execute("select receipt_json,receipt_sha,"
                "envelope_json,envelope_sha,final_sha,caption_sha "
                "from live_compose_manifests where job_id=?",(jid,)).fetchone()
            if (owner is None or job is None or job["actor"]!=entry["actor"] or
                owner["actor"]!=entry["actor"] or job["state"]!="COMPLETED" or
                job["mode"]!="LIVE" or job["final_sha"]!=entry["final_sha"] or
                job["caption_sha"]!=entry["caption_sha"]):
                raise ValueError("SHARED_OWNER_OR_ARTIFACT_LEDGER_CONFLICT")
            base=root/"outputs"/jid
            fin=base/"final.png";cap=base/"caption.txt"
            if fin.is_symlink() or cap.is_symlink():
                raise ValueError("SHARED_FILE_SYMLINK_DENIED")
            try:photo=fin.read_bytes();caption=cap.read_bytes()
            except OSError as e:raise ValueError("SHARED_ARTIFACT_UNAVAILABLE") from e
            if sha(photo)!=entry["final_sha"] or sha(caption)!=entry["caption_sha"]:
                raise ValueError("SHARED_ARTIFACT_SHA_MISMATCH")
            width,height=verified_png(photo)
            # All currently accepted historic share records are completed
            # composed jobs requiring a bound composition manifest. A future
            # freeform evidence contract must be versioned/approved first.
            if manifest is None:
                raise ValueError("SHARED_RECEIPT_MANIFEST_MISSING")
            if manifest:
                rec=base/"receipt.json"
                if (rec.is_symlink() or not rec.is_file() or
                    sha(rec.read_bytes())!=manifest["receipt_sha"] or
                    not isinstance(manifest["receipt_json"],str) or
                    sha(manifest["receipt_json"].encode("utf-8"))!=manifest["receipt_sha"] or
                    not isinstance(manifest["envelope_json"],str) or
                    sha(manifest["envelope_json"].encode("utf-8"))!=manifest["envelope_sha"] or
                    manifest["final_sha"]!=entry["final_sha"] or
                    manifest["caption_sha"]!=entry["caption_sha"]):
                    raise ValueError("SHARED_RECEIPT_MANIFEST_MISMATCH")
            job_records.append(({
                "job_id":jid,
                "shared_at":entry["shared_at"],
                "final_sha256":entry["final_sha"],
                "caption_sha256":entry["caption_sha"],
                "pixels":{"width":width,"height":height},
                "copy_sha256":job["copy_sha"],
                "review_sha256":job["review_sha"],
                "approval_sha256":job["approval_sha"],
                "receipt_sha256":manifest["receipt_sha"] if manifest else None,
            },photo,caption))
    # No internal input/research/Actor/auth DB content in the derived output.
    manifest={"schema_version":"bp17-published-final-projection-v1",
      "source_committed_code_sha":source_code_sha,
      "audited_explicit_share_count":len(job_records),
      "contains_private_job_payload":False,
      "contains_actor_or_auth_tokens":False,
      "usable_as_operational_job_database":False,
      "new_provider_calls":0,
      "shared_final_adverts":[row[0] for row in job_records]}
    manifest_bytes=(json.dumps(manifest,ensure_ascii=False,indent=2,
        sort_keys=True)+"\n").encode("utf-8")
    manifest_sha=sha(manifest_bytes)
    with ExitStack() as stack:
        pfd=os.open(parent,DIR_FLAGS)
        stack.callback(os.close,pfd)
        st=os.fstat(pfd)
        if (not stat.S_ISDIR(st.st_mode) or st.st_uid!=os.geteuid()
            or bool(st.st_mode & 0o022)):
            raise ValueError("DESTINATION_PARENT_WRITABLE_BY_OTHER_PRINCIPALS")
        _assert_path_bound(parent,pfd)
        name=None
        stage_fd=None
        try:
            _assert_path_bound(parent,pfd)
            name,stage_fd=_create_stage(pfd)
            stack.callback(os.close,stage_fd)
            _assert_path_bound(parent,pfd)
            with ExitStack() as parts:
                ads_fd=_create_child_dir(stage_fd,"final_ads")
                parts.callback(os.close,ads_fd)
                for record,photo,caption in job_records:
                    folder_fd=_create_child_dir(ads_fd,record["job_id"])
                    try:
                        _write_at(folder_fd,"final.png",photo)
                        _write_at(folder_fd,"caption.txt",caption)
                        os.fsync(folder_fd)
                    finally:os.close(folder_fd)
                os.fsync(ads_fd)
            _write_at(stage_fd,"projection_manifest.json",manifest_bytes)
            os.fsync(stage_fd)
            if not _same_stage_at(pfd,name,stage_fd):
                raise ValueError("STAGE_IDENTITY_CONFLICT")
            _assert_path_bound(parent,pfd)
            _publish_no_replace(pfd,name,dest.name)
            if not _published_matches(pfd,dest.name,stage_fd):
                raise ValueError("PUBLISHED_STAGE_IDENTITY_MISMATCH")
            published_fd=os.open(dest.name,DIR_FLAGS,dir_fd=pfd)
            try:
                if _inode(os.fstat(published_fd))!=_inode(os.fstat(stage_fd)):
                    raise ValueError("PUBLISHED_STAGE_IDENTITY_MISMATCH")
                actual_sha=sha(_read_at(published_fd,"projection_manifest.json"))
                if actual_sha!=manifest_sha:
                    raise ValueError("PUBLISHED_MANIFEST_SHA_MISMATCH")
            finally:os.close(published_fd)
            _assert_path_bound(parent,pfd)
            if (_inode(os.stat(dest,follow_symlinks=False))!=
                    _inode(os.fstat(stage_fd))):
                raise ValueError("PUBLISHED_PATH_IDENTITY_MISMATCH")
            _assert_path_bound(parent,pfd)
            return {"destination":str(dest),"published_count":len(job_records),
                    "manifest_sha256":manifest_sha,"new_provider_calls":0}
        except BaseException as exc:
            if name is not None and stage_fd is not None:
                if _published_matches(pfd,dest.name,stage_fd):
                    # Late error: actual product exists, NEVER delete silently.
                    raise RuntimeError(
                        "PUBLISHED_BUT_UNVERIFIED_MANUAL_RECONCILIATION"
                    ) from exc
                try:
                    _cleanup_original_stage(pfd,name,stage_fd)
                except BaseException as cleanup_error:
                    raise RuntimeError(
                        "STAGING_CLEANUP_FAILED_MANUAL_RECONCILIATION"
                    ) from cleanup_error
            raise


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_qa_root",type=Path)
    parser.add_argument("new_destination",type=Path)
    args=parser.parse_args()
    print(json.dumps(run(args.source_qa_root,args.new_destination),
                     indent=2,ensure_ascii=False))
