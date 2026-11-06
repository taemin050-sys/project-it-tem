"""IT-TEM QA Tailscale Serve authenticated-identity gateway (Mac localhost).

Tailscale Serve strips caller-supplied identity headers and injects verified
Tailscale-User-Login. This gateway maps *five explicitly approved users* to
distinct job/evaluation identities and signs per-request assertions for the
GCP FastAPI listener, which remains private behind an SSH tunnel.

NEVER bind the gateway to 0.0.0.0, expose with Funnel, or trust generic IP
membership. Secrets / email mappings belong in chmod-0600 runtime files.
"""
from __future__ import annotations

import http.client
import json
import os
import re
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from demo_staging.tailnet_assertion import build_assertion, key_from_file

LOGIN_RE = re.compile(r"^[A-Za-z0-9._+%-]+@[A-Za-z0-9.-]+$")
HOP = {"connection","keep-alive","proxy-authenticate","proxy-authorization",
       "te","trailer","transfer-encoding","upgrade","proxy-connection"}
MAX_BODY = 80 * 1024 * 1024


def load_users(path: str) -> dict[str, dict[str,str]]:
    p=Path(path)
    if not p.is_file() or p.stat().st_mode & 0o077:
        raise RuntimeError("TAILNET_USER_REGISTRY_MISSING_OR_INSECURE")
    doc=json.loads(p.read_text(encoding="utf8"))
    if not isinstance(doc,dict) or len(doc)!=5:
        raise RuntimeError("TAILNET_EXACT_FIVE_USERS_REQUIRED")
    actors=set()
    for login, entry in doc.items():
        if (not LOGIN_RE.fullmatch(login) or login!=login.lower() or
            not isinstance(entry,dict) or set(entry)!={"actor","role"} or
            entry["role"] not in ("evaluator","admin") or
            not re.fullmatch(r"[A-Za-z0-9_-]{3,40}",entry["actor"])):
            raise RuntimeError("TAILNET_USER_REGISTRY_INVALID")
        actors.add(entry["actor"])
    if len(actors)!=5:
        raise RuntimeError("TAILNET_USER_ACTOR_COLLISION")
    return doc


class Gateway(BaseHTTPRequestHandler):
    server_version = "IT-TEM-Tailnet-SSO/1.0"
    sys_version = ""

    def do_GET(self):self.forward()
    def do_HEAD(self):self.forward()
    def do_POST(self):self.forward()
    def do_PUT(self):self.forward()
    def do_PATCH(self):self.forward()
    def do_DELETE(self):self.forward()
    def do_OPTIONS(self):self.forward()

    def fail(self, status: int, reason: str):
        body=json.dumps({"detail":reason},ensure_ascii=False).encode("utf8")
        self.send_response(status)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Cache-Control","private, no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Content-Length",str(len(body)))
        self.end_headers()
        if self.command!="HEAD":self.wfile.write(body)

    def forward(self):
        # HTTP server MUST only be reached from Tailscale Serve on Mac.
        if self.client_address[0] not in ("127.0.0.1","::1"):
            return self.fail(403,"Gateway loopback only")
        logins=self.headers.get_all("Tailscale-User-Login", [])
        if len(logins)!=1:
            return self.fail(403,"Authenticated Tailscale Serve identity required")
        login=logins[0].strip().lower()
        if not LOGIN_RE.fullmatch(login):
            return self.fail(403,"Tailscale user identity invalid")
        record=self.server.allowed_users.get(login)
        if not record:
            return self.fail(403,"User not on IT-TEM team allowlist")
        host=self.headers.get("Host","")
        # User-facing endpoint must be the pinned HTTPS Tailscale Serve host.
        if host.lower()!=self.server.expected_host:
            return self.fail(403,"Non-Tailscale host denied")
        rawlen=self.headers.get("Content-Length","0")
        if not rawlen.isascii() or not rawlen.isdecimal():
            return self.fail(411,"Content-Length required")
        length=int(rawlen)
        if length>MAX_BODY:
            return self.fail(413,"Upload too large")
        if self.headers.get("Transfer-Encoding"):
            return self.fail(400,"Transfer-Encoding not supported")
        body=self.rfile.read(length) if length else b""
        if len(body)!=length:
            return self.fail(400,"Incomplete request body")
        headers={}
        for k,v in self.headers.items():
            lk=k.lower()
            if (lk in HOP or lk=="content-length"
                or lk.startswith("tailscale-") or
                lk.startswith("x-ittem-tailnet-") or
                lk.startswith("x-forwarded-")):
                continue
            headers[k]=v
        headers.update(build_assertion(
            self.server.secret,record["actor"],record["role"],
            self.command,self.path,host))
        headers["X-Forwarded-Proto"]="https"
        headers["Content-Length"]=str(len(body))
        headers["Connection"]="close"
        try:
            upstream=http.client.HTTPConnection(
                "127.0.0.1",self.server.target_port,timeout=330)
            upstream.request(self.command,self.path,body=body,headers=headers)
            result=upstream.getresponse()
            payload=result.read()
            self.send_response(result.status)
            for k,v in result.getheaders():
                if k.lower() not in HOP and k.lower() not in ("content-length","server","date"):
                    self.send_header(k,v)
            self.send_header("Content-Length",str(len(payload)))
            self.send_header("Cache-Control","private, no-store")
            self.send_header("X-IT-TEM-Auth-Path","tailscale-sso")
            self.end_headers()
            if self.command!="HEAD":self.wfile.write(payload)
            upstream.close()
        except (OSError,TimeoutError,http.client.HTTPException):
            self.fail(502,"IT-TEM QA upstream unavailable")

    def log_message(self,format,*args):
        # No secret, cookie, email, or query parameters in gateway logs.
        print("IT_TEM_TAILNET_GATEWAY",self.command,self.path.split("?")[0],
              str(args[1]) if len(args)>1 else "",flush=True)


def run():
    key=key_from_file(os.environ["IT_TEM_TAILNET_GATEWAY_KEY_FILE"])
    users=load_users(os.environ["IT_TEM_TAILNET_GATEWAY_USERS_FILE"])
    expected=os.environ["IT_TEM_TAILNET_EXPECTED_HOST"].lower()
    if not re.fullmatch(r"[a-z0-9.-]+\.ts\.net:8443",expected):
        raise RuntimeError("UNAPPROVED_TAILSCALE_HOST")
    server=ThreadingHTTPServer(("127.0.0.1",18987),Gateway)
    server.secret=key
    server.allowed_users=users
    server.expected_host=expected
    server.target_port=18988
    print("IT_TEM_TAILNET_SSO_MAC_GATEWAY_18987_STARTED",len(users),"identities",
          "UPSTREAM_127.0.0.1:18988",flush=True)
    server.serve_forever(poll_interval=.25)


if __name__=="__main__":run()
