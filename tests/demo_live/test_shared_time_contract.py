"""#17 shared timestamp contract: read-only extension of canonical SQLite data."""
from datetime import datetime, timezone
from demo_staging.live.reviews import LiveShares

def test_sqlite_timestamp_compatibility_and_boundary(tmp_path):
    shares = LiveShares(tmp_path / "shares.sqlite")
    published = shares.publish("alice", "a" * 32, "b" * 64, "c" * 64)
    original = published["shared_at"]
    expected = datetime.strptime(original, "%Y-%m-%d %H:%M:%S").replace(
        tzinfo=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    assert LiveShares.utc_iso8601(original) == expected
    assert shares.item("a" * 32)["shared_at"] == original
    assert LiveShares.utc_iso8601("2026-11-03 09:16:05") == "2026-11-03T09:16:05Z"
    assert LiveShares.utc_iso8601("2026-11-03 15:30:00") == "2026-11-03T15:30:00Z"

def test_invalid_untrusted_timestamp_fails_closed():
    for timestamp in [None, "", "no timestamp", "2026-02-30 09:16:05",
                      "2026-11-03T09:16:05+09:00", "2026-11-03 25:16:05",
                      "2026-11-03T09:16:05Z", "2026-11-03 09:16:05+00:00"]:
        assert LiveShares.utc_iso8601(timestamp) is None
