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
import shutil
import sqlite3
import tempfile
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
    conn=sqlite3.connect(path.resolve().as_uri()+"?mode=ro",uri=True,timeout=5)
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

def _publish_no_replace(staged:Path,target:Path)->None:
    """Atomic no-replace DIRECTORY publication. Never use plain os.rename.

    Linux renameat2(RENAME_NOREPLACE) / macOS renameatx_np(RENAME_EXCL).
    Fail closed on unknown OS/filesystems rather than expose a partial folder.
    dirfd anchors both paths against parent symlink/path replacement races.
    """
    if staged.parent != target.parent or staged.name==target.name:
        raise ValueError("PUBLISH_PARENT_OR_SOURCE_INVALID")
    name=target.name
    if name in ("", ".", "..") or "/" in name:
        raise ValueError("PUBLISH_TARGET_INVALID")
    flags=os.O_RDONLY | getattr(os,"O_DIRECTORY",0) | getattr(os,"O_NOFOLLOW",0)
    fd=os.open(staged.parent,flags)
    try:
        libc=ctypes.CDLL(None,use_errno=True)
        if sys.platform.startswith("linux"):
            fn=getattr(libc,"renameat2",None)
            bit=1 # RENAME_NOREPLACE from linux/fs.h
        elif sys.platform=="darwin":
            fn=getattr(libc,"renameatx_np",None)
            bit=0x00000004 # RENAME_EXCL from sys/stdio.h
        else:
            raise OSError(errno.ENOTSUP,"PLATFORM_NO_ATOMIC_NOREPLACE")
        if fn is None:
            raise OSError(errno.ENOTSUP,"ATOMIC_NOREPLACE_UNAVAILABLE")
        fn.argtypes=[ctypes.c_int,ctypes.c_char_p,
                     ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]
        fn.restype=ctypes.c_int
        result=fn(fd,os.fsencode(staged.name),fd,os.fsencode(name),bit)
        if result:
            err=ctypes.get_errno()
            if err in (errno.EEXIST,errno.ENOTEMPTY):
                raise FileExistsError("DESTINATION_MUST_BE_NEW")
            raise OSError(err,os.strerror(err))
        os.fsync(fd)
    finally:
        os.close(fd)


def run(source:Path,destination:Path)->dict:
    src=source.resolve(strict=True)
    if src not in ALLOWED_ROOTS or source.is_symlink():
        raise ValueError("QA_SOURCE_NOT_ON_EXPLICIT_ALLOWLIST")
    dest=destination.absolute()
    if dest.exists() or dest.is_symlink():
        raise FileExistsError("DESTINATION_MUST_BE_NEW")
    parent=dest.parent.resolve(strict=True)
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
    # No private input/research/copy/compliance JSON, actor, auth, DB, raw photos,
    # or receipt body is included in the derived folder.
    # Hold the original directory inode for fd-anchored cleanup even if
    # another local process changes the path while building the projection.
    pfd=os.open(parent,os.O_RDONLY | getattr(os,"O_DIRECTORY",0) |
                getattr(os,"O_NOFOLLOW",0))
    staged=None
    try:
        original_parent=os.fstat(pfd)
        tmp=Path(tempfile.mkdtemp(prefix=".bp17_export_incomplete_",dir=parent))
        staged=tmp.name
        os.chmod(tmp,0o700)
        manifest={"schema_version":"bp17-published-final-projection-v1",
          "source_committed_code_sha":source_code_sha,
          "audited_explicit_share_count":len(job_records),
          "contains_private_job_payload":False,
          "contains_actor_or_auth_tokens":False,
          "usable_as_operational_job_database":False,
          "new_provider_calls":0,
          "shared_final_adverts":[row[0] for row in job_records]}
        files=tmp/"final_ads";files.mkdir(mode=0o700)
        for record,photo,caption in job_records:
            folder=files/record["job_id"];folder.mkdir(mode=0o700)
            for name,data in (("final.png",photo),("caption.txt",caption)):
                target=folder/name
                with target.open("xb") as handle:
                    handle.write(data);handle.flush();os.fsync(handle.fileno())
                target.chmod(0o400)
        j=tmp/"projection_manifest.json"
        with j.open("x",encoding="utf-8") as handle:
            handle.write(json.dumps(manifest,ensure_ascii=False,
                indent=2,sort_keys=True)+"\n")
            handle.flush()
            os.fsync(handle.fileno())
        j.chmod(0o400)
        parent_now=os.stat(parent,follow_symlinks=False)
        if ((parent_now.st_dev,parent_now.st_ino)!=
            (original_parent.st_dev,original_parent.st_ino)):
            raise ValueError("DESTINATION_PARENT_CHANGED_BEFORE_PUBLISH")
        _publish_no_replace(tmp,dest)  # true atomic no-replace (Linux/macOS)
        return {"destination":str(dest),"published_count":len(job_records),
                "manifest_sha256":sha((dest/"projection_manifest.json").read_bytes()),
                "new_provider_calls":0}
    except BaseException:
        # The staging directory is under the inode originally opened by pfd,
        # not necessarily under the current path (which may now be a symlink).
        if staged is not None:
            try:
                shutil.rmtree(staged,dir_fd=pfd)
            except FileNotFoundError:
                pass  # successful atomic rename already moved this directory
        raise
    finally:
        os.close(pfd)

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_qa_root",type=Path)
    parser.add_argument("new_destination",type=Path)
    args=parser.parse_args()
    print(json.dumps(run(args.source_qa_root,args.new_destination),
                     indent=2,ensure_ascii=False))
