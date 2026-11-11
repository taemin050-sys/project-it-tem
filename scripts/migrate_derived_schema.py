"""Explicitly migrate a selected backed-up B database for local derived renders."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from demo_staging.live.derived_store import migrate_derived_schema


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--expected-db-sha256", help="SHA of the explicit disposable or backed-up database")
    choice.add_argument("--create", action="store_true", help="Create a new empty local database")
    args = parser.parse_args()
    if not args.database.is_absolute():
        parser.error("--database must be an explicit absolute path")
    if args.create:
        if args.database.exists():
            parser.error("--create requires an absent database")
    else:
        if not args.database.is_file() or args.database.is_symlink():
            parser.error("Expected a regular existing database")
        if sha256(args.database.read_bytes()).hexdigest() != args.expected_db_sha256:
            parser.error("Database SHA differs from the approved snapshot")
    print(json.dumps(migrate_derived_schema(
        args.database, expected_db_sha256=args.expected_db_sha256), sort_keys=True))


if __name__ == "__main__":
    main()
