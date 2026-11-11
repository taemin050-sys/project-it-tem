"""Authenticated Tailscale Serve identity assertion, signed by isolated Mac proxy.

Never trust an unsigned Tailscale-User-Login header inside the GCP app.
The shared HMAC key is runtime-only and must not be committed or shipped.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
import sqlite3
from pathlib import Path

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from fastapi import Request

ACTOR = re.compile(r"^[a-zA-Z0-9_-]{3,40}$")
HEX32 = re.compile(r"^[a-f0-9]{32}$")
HEX64 = re.compile(r"^[a-f0-9]{64}$")
PREFIX = "x-ittem-tailnet-"
MAX_CLOCK_SKEW = 45


class TailnetAssertionError(ValueError):
    pass



class TailnetNonceJournal:
    """GCP A5-1I only: durable, atomic anti-replay for valid signed assertions.

    Application-side nonce replay protection is not a substitute for a
    trusted Tailscale Serve -> gateway origin on the Mac host.
    Existing A/B/v2 signers and validators are unaffected.
    """
    def __init__(self, path: Path, *, initialize: bool = False):
        self.path = Path(path)
        if not self.path.is_absolute() or self.path.is_symlink():
            raise RuntimeError("TAILNET_NONCE_LEDGER_PATH_UNTRUSTED")
        if not initialize and not self.path.is_file():
            raise RuntimeError("TAILNET_NONCE_LEDGER_NOT_PREINITIALIZED")
        if self.path.parent.is_symlink() or not self.path.parent.is_dir():
            raise RuntimeError("TAILNET_NONCE_LEDGER_ROOT_UNTRUSTED")
        if initialize:
            if self.path.exists():
                raise RuntimeError("TAILNET_NONCE_LEDGER_ALREADY_EXISTS")
            with sqlite3.connect(self.path, timeout=5, isolation_level=None) as db:
                db.execute("CREATE TABLE assertion_nonces ("
                           "nonce TEXT PRIMARY KEY NOT NULL,"
                           "seen_utc INTEGER NOT NULL)")
            self.path.chmod(0o600)
        if self.path.stat().st_mode & 0o077:
            raise RuntimeError("TAILNET_NONCE_LEDGER_PERMISSIONS_UNSAFE")
        with sqlite3.connect(self.path, timeout=5) as db:
            rows=db.execute("PRAGMA table_info(assertion_nonces)").fetchall()
            if [(r[1],r[2]) for r in rows] != [
                    ("nonce","TEXT"),("seen_utc","INTEGER")]:
                raise RuntimeError("TAILNET_NONCE_LEDGER_SCHEMA_INVALID")

    def consume(self, nonce: str, *, instant: int | None = None) -> None:
        if not isinstance(nonce,str) or not HEX32.fullmatch(nonce):
            raise TailnetAssertionError("TAILNET_NONCE_INVALID")
        now=int(time.time()) if instant is None else int(instant)
        try:
            # A lock contention is a DENY, not a replay allowance.
            with sqlite3.connect(self.path, timeout=5, isolation_level=None) as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("DELETE FROM assertion_nonces WHERE seen_utc < ?",
                           (now-4*MAX_CLOCK_SKEW,))
                db.execute("INSERT INTO assertion_nonces(nonce,seen_utc) VALUES (?,?)",
                           (nonce,now))
                db.execute("COMMIT")
        except sqlite3.IntegrityError:
            raise TailnetAssertionError("TAILNET_ASSERTION_NONCE_REPLAY") from None
        except sqlite3.Error:
            raise TailnetAssertionError("TAILNET_NONCE_LEDGER_UNAVAILABLE") from None

def key_from_file(path: str) -> bytes:
    file = Path(path)
    if not file.is_file():
        raise RuntimeError("TAILNET_AUTH_KEY_FILE_UNAVAILABLE")
    if file.stat().st_mode & 0o077:
        raise RuntimeError("TAILNET_AUTH_KEY_FILE_PERMISSIONS")
    key = file.read_bytes().strip()
    if len(key) < 32 or len(key) > 256:
        raise RuntimeError("TAILNET_AUTH_KEY_INVALID")
    return key


def signature(key: bytes, actor: str, role: str, method: str,
              target: str, host: str, timestamp: str, nonce: str) -> str:
    message = "\n".join(("it-tem-tailnet-v1", actor, role, method.upper(),
                          target, host.lower(), timestamp, nonce)).encode("utf8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def build_assertion(key: bytes, actor: str, role: str, method: str,
                    target: str, host: str, now: int | None = None) -> dict[str,str]:
    if not ACTOR.fullmatch(actor) or role not in ("admin", "evaluator"):
        raise TailnetAssertionError("INVALID_ACTOR")
    timestamp = str(int(time.time()) if now is None else now)
    nonce = secrets.token_hex(16)
    return {
        PREFIX + "actor": actor, PREFIX + "role": role,
        PREFIX + "timestamp": timestamp, PREFIX + "nonce": nonce,
        PREFIX + "signature": signature(key, actor, role, method, target,
                                        host, timestamp, nonce),
    }


def verify_request(request: Request, key: bytes | None,
                   allowed_roles: dict[str,str],
                   expected_host: str | None = None) -> tuple[str,str] | None:
    headers = request.headers
    keys = [PREFIX + x for x in ("actor","role","timestamp","nonce","signature")]
    present = [x in headers for x in keys]
    if not any(present):
        return None
    if key is None or not all(present):
        raise TailnetAssertionError("TAILNET_ASSERTION_INCOMPLETE")
    # Header duplication is ambiguous. Reject instead of trusting a
    # first/last value selected by an upstream HTTP implementation.
    if any(len(headers.getlist(k)) != 1 for k in keys):
        raise TailnetAssertionError("TAILNET_ASSERTION_DUPLICATE")
    actor, role, ts, nonce, digest = [headers.get(x,"") for x in keys]
    if (not ACTOR.fullmatch(actor) or allowed_roles.get(actor) != role or
        not HEX32.fullmatch(nonce) or not HEX64.fullmatch(digest) or
        not ts.isascii() or not ts.isdecimal() or len(ts) > 12):
        raise TailnetAssertionError("TAILNET_ASSERTION_INVALID")
    if abs(int(time.time()) - int(ts)) > MAX_CLOCK_SKEW:
        raise TailnetAssertionError("TAILNET_ASSERTION_EXPIRED")
    target = request.scope.get("raw_path", b"").decode("latin1")
    query = request.scope.get("query_string", b"").decode("latin1")
    if query:
        target += "?" + query
    host = headers.get("host", "")
    if not host or len(host)>255:
        raise TailnetAssertionError("TAILNET_ASSERTION_HOST_INVALID")
    if expected_host is not None and host.lower() != expected_host.lower():
        raise TailnetAssertionError("TAILNET_ASSERTION_HOST_MISMATCH")
    expected = signature(key,actor,role,request.method,target,host,ts,nonce)
    if not hmac.compare_digest(expected,digest):
        raise TailnetAssertionError("TAILNET_ASSERTION_BAD_SIGNATURE")
    return actor,role
