"""Inspect or record a reviewed Live Dual incident disposition without Provider I/O."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys

from demo_staging.live.contracts import LiveGateError
from demo_staging.live.dual_billing import apply_disposition, inspect_incident
from deploy.systemd.bp18_live_launch import LaunchDenied
from scripts.bp18_b5_release_prestart import PRODUCTION_ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=PRODUCTION_ROOT)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("inspect").add_argument("task_id")
    apply = commands.add_parser("apply")
    apply.add_argument("task_id")
    apply.add_argument("--approval", type=Path, required=True)
    apply.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = (inspect_incident(args.root, args.task_id) if args.command == "inspect"
                  else apply_disposition(args.root, args.task_id, args.approval, args.evidence))
    except (LiveGateError, LaunchDenied) as error:
        print(str(error), file=sys.stderr)
        return 78
    except (OSError, sqlite3.Error, ValueError, TypeError, KeyError):
        print("LIVE_DUAL_RECONCILE_EVIDENCE_UNAVAILABLE", file=sys.stderr)
        return 78
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
