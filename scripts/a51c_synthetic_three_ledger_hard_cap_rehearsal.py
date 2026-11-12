"""A51C isolated synthetic three-ledger hard cap rehearsal.

Test actual Owner ProviderAttemptStore / Live AttemptLedger / Queue classes
without OpenAI credentials, provider I/O, LIVE worker activation or GCP writes.
A fake $0.60 test limit is NOT an approved real spending limit.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from demo_staging.live_safety import AttemptLedger, LiveNotAuthorized
from demo_staging.live.queue import LiveQueue
from src.image_generation.provider_attempts import ProviderAttemptStore
from src.image_generation.errors import GatewayError


SCENARIOS=(
    ("COMPOSED","4:5"),("COMPOSED","3:4"),("COMPOSED","9:16"),
    ("FREEFORM","4:5"),("FREEFORM","3:4"),("FREEFORM","9:16"),
)
# Every amount here is a clearly fake *in-memory experiment* number,
# not an estimate of a real API rate or permission to spend money.
FAKE_CAP_USD="0.600000"
FAKE_RESERVE_USD="0.100000"


def _count(path:Path,table:str):
    with sqlite3.connect(path) as db:
        return db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def rehearse(root:Path)->dict:
    """Root MUST be preexisting disposable private directory outside Git/GCP."""
    if (not root.is_dir() or root.is_symlink()
        or root.stat().st_mode & 0o077):
        raise RuntimeError("ISOLATED_0700_DISPOSABLE_ROOT_REQUIRED")
    if not root.resolve().is_relative_to(Path("/private/tmp").resolve()):
        # Guard against accidentally pointing the rehearsal at GCP, a source
        # checkout, a home directory or an active local Runtime.
        raise RuntimeError("NOT_A_PRIVATE_TMP_REHEARSAL")
    if list(root.iterdir()):
        raise RuntimeError("REHEARSAL_ROOT_MUST_BE_EMPTY")
    live=root/"runtime"/"live"
    live.mkdir(parents=True,mode=0o700)
    queue=LiveQueue(live/"queue.sqlite")
    cost=AttemptLedger(live/"cost.sqlite",live_enabled=True,
                       max_requests=6,budget_usd=FAKE_CAP_USD,
                       monitoring_only=False)
    owner_dir=live/"owner_image"
    owner=ProviderAttemptStore(owner_dir/"image_attempts.sqlite")
    project=uuid4()
    jobs=[]
    for i,(mode,ratio) in enumerate(SCENARIOS):
        job=uuid4()
        fake_context={"experiment":"OFFLINE_ONLY","mode":mode,
                      "ratio":ratio,"candidate_count":1,
                      "test_ordinal":i+1}
        h=hashlib.sha256(json.dumps(fake_context,sort_keys=True).encode()).hexdigest()
        reserved=cost.reserve(actor="test_actor",role="live_operator",
             job_id=str(job),stage="image",payload=fake_context,
             estimated_usd=FAKE_RESERVE_USD,pm_authorized=True)
        assert reserved["new"] is True
        owner_attempt=owner.begin(job,project,h,
                budget_limit_usd=FAKE_CAP_USD,
                reservation_usd=FAKE_RESERVE_USD,
                monitoring_only=False)
        assert owner.get(job,project)["attempt_id"]==str(owner_attempt)
        jobs.append((job,h,owner_attempt,reserved["id"]))
    assert len(jobs)==6
    assert _count(cost.filename,"attempts")==6
    assert _count(owner.path,"provider_attempts")==6
    assert _count(queue.file,"queued_ops")==0
    seventh_blocked=False
    try:
        cost.reserve(actor="test_actor",role="live_operator",
          job_id=str(uuid4()),stage="image",
          payload={"experiment":"SEVENTH_UNAPPROVED"},
          estimated_usd=FAKE_RESERVE_USD,pm_authorized=True)
    except LiveNotAuthorized:
        seventh_blocked=True
    assert seventh_blocked
    provider_seventh_blocked=False
    try:
        owner.begin(uuid4(),project,"b"*64,
                    budget_limit_usd=FAKE_CAP_USD,
                    reservation_usd=FAKE_RESERVE_USD,
                    monitoring_only=False)
    except GatewayError as error:
        assert error.code=="PROVIDER_BUDGET_EXCEEDED"
        provider_seventh_blocked=True
    assert provider_seventh_blocked
    retry_denied=False
    try:
        owner.begin(jobs[0][0],project,jobs[0][1],
                    budget_limit_usd=FAKE_CAP_USD,
                    reservation_usd=FAKE_RESERVE_USD,
                    monitoring_only=False)
    except GatewayError as error:
        assert error.code=="PROVIDER_ATTEMPT_CONFLICT"
        retry_denied=True
    assert retry_denied
    # A provider submission with unknown outcome is never replaced by
    # another "free" attempt. No HTTP request is actually made.
    owner.finish(jobs[0][0],project,jobs[0][2],
                 state="unknown",error_code="PROVIDER_SUBMISSION_UNKNOWN")
    assert owner.get(jobs[0][0],project)["state"]=="unknown"
    with sqlite3.connect(owner.path) as conn:
        owner_schema="".join(row[0] or "" for row in conn.execute(
          "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY name"))
    report={
      "contract":"IT_TEM_P03_A51C_OFFLINE_SYNTHETIC_THREE_LEDGER_REHEARSAL_V1",
      "scenarios":[{"generation_mode":mode.lower(),"ratio":ratio,
                    "candidate_count":1} for mode,ratio in SCENARIOS],
      "independent_job_count":6,
      "app_image_attempt_table":"NOT_CREATED_IN_THIS_SIMULATION",
      "queue_attempts":_count(queue.file,"queued_ops"),
      "cost_reservation_rows":_count(cost.filename,"attempts"),
      "provider_attempt_rows":_count(owner.path,"provider_attempts"),
      "owner_provider_attempt_schema_sha256":hashlib.sha256(
          owner_schema.encode()).hexdigest(),
      "fake_only_reservation_usd":FAKE_RESERVE_USD,
      "fake_only_cap_usd":FAKE_CAP_USD,
      "seventh_cost_reservation_blocked":seventh_blocked,
      "seventh_owner_attempt_blocked":provider_seventh_blocked,
      "owner_duplicate_job_rejected":retry_denied,
      "uncertain_provider_attempt_remains_held":True,
      "actual_cost_known":False,
      "actual_paid_provider_requests":0,
      "actual_provider_receipts":0,
      "real_pm_budget_approval":False,
      "real_provider_attempt_store_created_on_gcp":False,
      "gcp_modified":False,
      "team_beta_readiness":"HOLD",
    }
    return report


def main():
    with TemporaryDirectory(prefix="ittem-a51c-ledger-",dir="/private/tmp") as d:
        root=Path(d)
        root.chmod(0o700)
        proof=rehearse(root)
    print(json.dumps(proof,ensure_ascii=False,sort_keys=True,indent=2))


if __name__=="__main__":
    main()
