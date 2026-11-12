"""Human-review-only image Attempt crash inspection: NEVER writes, queues or calls providers.
Usage: python scripts/bp13_image_recovery_audit_readonly.py /path/to/runtime/live JOB_ID
No production recovery is authorized by running this script.
"""
import argparse,hashlib,json,sqlite3,re
from pathlib import Path

def _sha(path):
    if not path.is_file():return None
    return hashlib.sha256(path.read_bytes()).hexdigest()

def _db(path):
    if not path.is_file():return None
    return sqlite3.connect("file:"+str(path.absolute())+"?mode=ro",uri=True)

def inspect(root:Path,jid:str)->dict:
    if not re.fullmatch("[0-9a-f]{32}",jid):raise ValueError("INVALID_JOB_ID")
    db=_db(root/"live.sqlite")
    if db is None:raise ValueError("LIVE_DB_MISSING")
    db.row_factory=sqlite3.Row
    job=db.execute("select * from live_jobs where job_id=?",(jid,)).fetchone()
    if job is None:raise ValueError("JOB_NOT_FOUND")
    has_attempt=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='live_image_attempts'").fetchone()
    attempts=[]
    if has_attempt:
        attempts=[dict(row) for row in db.execute(
            "select * from live_image_attempts where job_id=? order by attempt_version",(jid,))]
    last=attempts[-1] if attempts else None
    image=root/"outputs"/jid/"image.png"
    file_sha=_sha(image)
    receipt=root/"outputs"/jid/"owner_candidate_receipt.json"
    receipt_sha=_sha(receipt)
    queue=_db(root/"queue.sqlite")
    ops=[]
    if queue:
        queue.row_factory=sqlite3.Row
        ops=[dict(row) for row in queue.execute(
            "select id,stage,state,context_sha,error_code from queued_ops where job_id=? and stage='image' order by created_at,id",(jid,))]
        queue.close()
    archived=[]
    archive_dir=root/"outputs"/jid/"attempts"
    if archive_dir.exists():
        for p in sorted(archive_dir.glob("*")):
            if p.is_file():archived.append({"name":p.name,"sha256":_sha(p)})
    previous=attempts[-2] if len(attempts)>1 else None
    # A just-created retry retains the OLD rejected image in image.png;
    # distinguish that from a NEW provider result saved before DB commit.
    old_image_sha=previous.get("candidate_sha") if previous else None
    old_receipt_sha=previous.get("candidate_receipt_sha") if previous else None
    current_unsafe=bool(last and last["state"]=="REQUESTED" and
        job["state"]=="PROMPT_READY" and (
          (file_sha is not None and file_sha!=old_image_sha) or
          (receipt_sha is not None and receipt_sha!=old_receipt_sha)))
    unknown=any(x["state"]=="BILLING_UNKNOWN" for x in ops)
    running=any(x["state"] in ("QUEUED","RUNNING") for x in ops)
    if unknown or current_unsafe:verdict="HOLD_MANUAL_PROVIDER_AND_ARTIFACT_RECONCILIATION"
    elif running:verdict="HOLD_INFLIGHT_NO_REQUEUE"
    elif last and last["state"]=="REQUESTED":verdict="ORPHAN_ATTEMPT_REQUIRES_MANUAL_TASK_RECONCILIATION"
    elif job["state"]=="COMPLETED":verdict="COMPLETED_READONLY"
    else:verdict="INSPECT_CURRENT_STATE_MANUALLY"
    report={"read_only":True,"automatic_replay_permitted":False,
        "job_id":jid,"job_state":job["state"],"image_sha_on_ledger":job["image_sha"],
        "image_sha_on_disk":file_sha,"image_sha_matches_ledger":file_sha==job["image_sha"],
        "receipt_sha_on_disk":receipt_sha,
        "receipt_sha_on_attempt":last.get("candidate_receipt_sha") if last else None,
        "current_attempt":last,"attempt_versions":len(attempts),"queue_image_tasks":ops,
        "archive_sha":archived,"verdict":verdict,
        "required_action":"Review provider request/receipt, usage and exact bytes out-of-band. Never enqueue or replay automatically."}
    db.close()
    return report

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("runtime_live_root",type=Path)
    ap.add_argument("job_id")
    args=ap.parse_args()
    print(json.dumps(inspect(args.runtime_live_root,args.job_id),
                     ensure_ascii=False,indent=2))
