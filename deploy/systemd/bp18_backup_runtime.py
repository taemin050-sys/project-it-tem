"""BP18 B-only SQLite online snapshot; never overwrite a backup."""
from pathlib import Path
from datetime import datetime, timezone
import sqlite3, hashlib, os, json, sys

ROOT = Path("/home/macstudio/ittem-bp18-product-completion-20261111")
NAMES = ("demo.sqlite3", "live/live.sqlite", "live/queue.sqlite",
         "live/cost.sqlite", "live/shares.sqlite", "live/text_checkpoints.sqlite")
assert len(sys.argv) == 2
tag = sys.argv[1]
assert tag.isalnum() and len(tag) <= 25, "INVALID_BACKUP_TAG"
out = ROOT / "backups" / ("b5-control-" + tag)
out.mkdir(parents=True, exist_ok=False, mode=0o700)
records = []
for name in NAMES:
    source = ROOT/"runtime"/name
    target = out/name
    if not source.is_file() or source.is_symlink():
        raise SystemExit("DB_MISSING_OR_LINK:" + name)
    target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    with sqlite3.connect(source.resolve().as_uri()+"?mode=ro",uri=True,timeout=10) as origin:
        with sqlite3.connect(target) as saved:
            origin.backup(saved)
            assert saved.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
    target.chmod(0o600)
    records.append({"db":name,"bytes":target.stat().st_size,
                    "sha256":hashlib.sha256(target.read_bytes()).hexdigest()})
manifest = out/"MANIFEST_SHA256.json"
manifest.write_text(json.dumps({"timestamp":datetime.now(timezone.utc).isoformat(),
                                 "dbs":records},indent=2))
manifest.chmod(0o600)
print("BP18_B5_SQLITE_SIX_BACKUPS_VERIFIED",out)
