"""A51C disposable provider/cost/queue reservation test only, no paid calls."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from scripts.a51c_synthetic_three_ledger_hard_cap_rehearsal import (
    rehearse,SCENARIOS,FAKE_CAP_USD,
)


def test_six_independent_single_candidate_ledger_reservations_not_provider_calls():
    with TemporaryDirectory(prefix="ittem-a51c-unit-",dir="/private/tmp") as temp:
        root=Path(temp)
        root.chmod(0o700)
        report=rehearse(root)
        assert report["independent_job_count"]==6
        assert len(report["scenarios"])==6
        assert [tuple(x[k] for k in ("generation_mode","ratio"))
                for x in report["scenarios"]]==[
                    (mode.lower(),ratio) for mode,ratio in SCENARIOS]
        assert all(x["candidate_count"]==1 for x in report["scenarios"])
        assert report["queue_attempts"]==0
        assert report["cost_reservation_rows"]==6
        assert report["provider_attempt_rows"]==6
        assert report["fake_only_cap_usd"]==FAKE_CAP_USD
        assert report["seventh_cost_reservation_blocked"] is True
        assert report["seventh_owner_attempt_blocked"] is True
        assert report["owner_duplicate_job_rejected"] is True
        assert report["uncertain_provider_attempt_remains_held"] is True
        assert report["actual_paid_provider_requests"]==0
        assert report["actual_provider_receipts"]==0
        assert report["real_pm_budget_approval"] is False
        assert report["real_provider_attempt_store_created_on_gcp"] is False
        assert report["gcp_modified"] is False


def test_protected_non_disposable_directory_always_rejected(tmp_path):
    with pytest.raises(RuntimeError,match="NOT_A_PRIVATE_TMP_REHEARSAL"):
        rehearse(tmp_path)


def test_no_implicit_reuse_of_existing_ledger_in_disposable_root():
    with TemporaryDirectory(prefix="ittem-a51c-unit-",dir="/private/tmp") as temp:
        root=Path(temp)
        root.chmod(0o700)
        (root/"existing.sqlite").write_bytes(b"some previous data")
        with pytest.raises(RuntimeError,match="REHEARSAL_ROOT_MUST_BE_EMPTY"):
            rehearse(root)
        assert (root/"existing.sqlite").read_bytes()==b"some previous data"


def test_unsafe_private_root_permissions_fail_closed():
    with TemporaryDirectory(prefix="ittem-a51c-unit-",dir="/private/tmp") as temp:
        root=Path(temp)
        root.chmod(0o755)
        with pytest.raises(RuntimeError,match="ISOLATED_0700_DISPOSABLE_ROOT_REQUIRED"):
            rehearse(root)


def test_cli_only_returns_sanitized_synthetic_report(tmp_path):
    import sys
    source=Path(__file__).resolve().parents[2]
    code=subprocess.run(
        [sys.executable,"-B","-m",
         "scripts.a51c_synthetic_three_ledger_hard_cap_rehearsal"],
         cwd=source,capture_output=True,text=True,timeout=25)
    assert code.returncode==0,code.stderr
    data=json.loads(code.stdout)
    assert data["independent_job_count"]==6
    assert data["actual_paid_provider_requests"]==0
    for sensitive in ("api_key","/private/tmp/ittem-a51c-ledger-",
                      "Bearer ","sk-proj-","test_actor","openai_response"):
        assert sensitive not in code.stdout.lower()
