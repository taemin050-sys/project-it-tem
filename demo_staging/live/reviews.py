"""Opt-in shared LIVE result evaluation; no raw inputs or owner job rights."""
from pathlib import Path
from datetime import datetime,timezone
import sqlite3,re
from .contracts import LiveGateError

class LiveShares:
    def __init__(self,path:Path):
        self.path=Path(path)
        self.path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        with self.db() as c:
            c.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS shared_live_results (
                job_id TEXT PRIMARY KEY, actor TEXT NOT NULL,
                final_sha TEXT NOT NULL, caption_sha TEXT NOT NULL,
                shared_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """)
    @staticmethod
    def utc_iso8601(value: str | None) -> str | None:
        """Convert only the known SQLite CURRENT_TIMESTAMP wire format.

        The table's canonical producer is LiveShares.publish. No inference is
        made for arbitrary timestamps, invalid calendar dates, or offsets.
        Return None so consumers fail closed rather than guessing a timezone.
        """
        if not isinstance(value, str) or not re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}", value
        ):
            return None
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
        return parsed.replace(tzinfo=timezone.utc).isoformat(
            timespec="seconds"
        ).replace("+00:00", "Z")

    def db(self):
        db=sqlite3.connect(self.path,timeout=15)
        db.execute("PRAGMA busy_timeout=15000")
        db.row_factory=sqlite3.Row
        return db
    def publish(self,actor,job_id,final_sha,caption_sha):
        if not all(isinstance(x,str) and re.fullmatch(r"[0-9a-f]{64}",x)
                   for x in (final_sha,caption_sha)):
            raise LiveGateError("INVALID_ARTIFACT_IDENTITY")
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            prev=db.execute("SELECT * FROM shared_live_results WHERE job_id=?",
                            (job_id,)).fetchone()
            if prev:
                if prev["actor"]!=actor or prev["final_sha"]!=final_sha or prev["caption_sha"]!=caption_sha:
                    raise LiveGateError("SHARE_STATE_CONFLICT")
                return dict(prev)
            db.execute("INSERT INTO shared_live_results(job_id,actor,final_sha,caption_sha) VALUES (?,?,?,?)",
                       (job_id,actor,final_sha,caption_sha))
            return dict(db.execute("SELECT * FROM shared_live_results WHERE job_id=?",
                                   (job_id,)).fetchone())
    def item(self,job_id):
        with self.db() as db:
            row=db.execute("SELECT * FROM shared_live_results WHERE job_id=?",(job_id,)).fetchone()
            return dict(row) if row else None
    def all(self):
        with self.db() as db:
            return [dict(x) for x in db.execute("SELECT * FROM shared_live_results ORDER BY shared_at DESC")]
