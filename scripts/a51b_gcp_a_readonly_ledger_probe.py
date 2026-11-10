"""A5-1B GCP A immutable-source and three-ledger READ-ONLY preflight.

Run via an ALREADY authorized SSH operator directly on the GCP A host.
No GCP credentials, no network calls, no DDL, no DB creation, no worker
startup, no migrations. This is a diagnostic ONLY, not deploy permission.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path

SCHEMA={
 "app":{"filename":"live.sqlite","table":"live_image_attempts","states":"state"},
 "queue":{"filename":"queue.sqlite","table":"queued_ops","states":"state"},
 "cost":{"filename":"cost.sqlite","table":"attempts","states":"status"},
 "owner_provider":{"filename":"owner_image/image_attempts.sqlite",
                   "table":"provider_attempts","states":"state"},
}
IDENT=re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
SHA40=re.compile(r"[0-9a-f]{40}")


def _db_status(path:Path, table:str, state:str) ->dict:
    if not path.is_file():
        return {"exists":False,"schema":"MISSING_NOT_MIGRATED",
                "row_count":None,"states":{}}
    result={"exists":True,"schema":"UNVERIFIED",
            "row_count":None,"states":{}}
    if not IDENT.fullmatch(table) or not IDENT.fullmatch(state):
        raise ValueError("SQL_FIELD_NAME_INVALID")
    try:
        # Mode=ro refuses to create a missing file.  No INSERT, UPDATE,
        # PRAGMA writable_schema or migration is issued.
        with sqlite3.connect(f"{path.absolute().as_uri()}?mode=ro",uri=True,
                             timeout=5) as db:
            db.execute("PRAGMA query_only=ON")
            tables={name for (name,) in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            if table not in tables:
                result["schema"]="TABLE_MISSING"
                return result
            columns={row[1] for row in db.execute(
                f'PRAGMA table_info("{table}")')}
            if state not in columns:
                result["schema"]="STATE_COLUMN_MISSING"
                return result
            result["schema"]="TABLE_PRESENT"
            result["row_count"]=db.execute(
                f'SELECT count(*) FROM "{table}"').fetchone()[0]
            result["states"]={str(status):count for status,count in db.execute(
                f'SELECT "{state}",count(*) FROM "{table}" GROUP BY "{state}"')}
    except (sqlite3.DatabaseError,OSError):
        result["schema"]="READ_ONLY_QUERY_FAILED"
    return result


def inspect(root:Path)->dict:
    root=root.expanduser().resolve(strict=True)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("GCP_A_RUNTIME_ROOT_INVALID")
    source=root/"repo"/"SOURCE_SHA.txt"
    if source.is_file():
        observed=source.read_text().strip()
        if not SHA40.fullmatch(observed):
            observed="SOURCE_SHA_FILE_INVALID"
    else:
        observed="SOURCE_SHA_NOT_FOUND"
    basedir=root/"runtime"/"live"
    data={kind:_db_status(basedir/spec["filename"],
                          spec["table"],spec["states"])
          for kind,spec in SCHEMA.items()}
    app=data["app"];owner=data["owner_provider"];queue=data["queue"];cost=data["cost"]
    # C-A: existing live_image_attempts are APP image approvals, not Owner
    # provider billing attempts. 0 queue+cost cannot prove provider readiness.
    owner_ready=owner["schema"]=="TABLE_PRESENT"
    conditions={
       "app_image_attempts_mapped":app["schema"]=="TABLE_PRESENT",
       "queue_table_mapped":queue["schema"]=="TABLE_PRESENT",
       "cost_table_mapped":cost["schema"]=="TABLE_PRESENT",
       "owner_provider_attempt_table_mapped":owner_ready,
       "no_cost_or_provider_auth_without_private_key_trust":True,
    }
    return {
      "contract":"IT_TEM_P03_A51B_GCP_A_READ_ONLY_THREE_LEDGER_PROBE_V1",
      "source_sha_observed":observed,
      "source_is_latest_a51b":False, # probe cannot elevate latest artifact
      "app_image_attempts_kind":"APPLICATION_IMAGE_REVIEW_LEDGER",
      "owner_provider_attempts_kind":"PAID_PROVIDER_ATTEMPT_LEDGER",
      "ledgers":data,
      "conditions":conditions,
      "provider_attempt_store_creation_or_migration_performed":False,
      "gcp_file_modified":False,
      "actual_provider_cost_and_receipt":"NOT_AUDITED",
      "signed_sso_and_actor":"NOT_AUDITED",
      "deployment_approved":False,
      "paid_worker_authorized":False,
      "beta_ready":False,
      "gate":"GCP_A_READ_ONLY_DIAGNOSIS_NOT_DEPLOY_AUTHORIZATION",
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",required=True,type=Path)
    args=parser.parse_args()
    try:
        print(json.dumps(inspect(args.root),ensure_ascii=False,
                         sort_keys=True,indent=2))
    except (OSError,ValueError):
        raise SystemExit("GCP_A_READ_ONLY_ROOT_UNAVAILABLE") from None


if __name__=="__main__":
    main()
