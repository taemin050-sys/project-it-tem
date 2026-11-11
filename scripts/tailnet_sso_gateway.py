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
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

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

    def transport_diagnostic(self, request_id, phase, error, started):
        # Fixed fields only: no URL/query, identity, headers, or exception text.
        print("IT_TEM_TAILNET_TRANSPORT "+json.dumps({
            "request_id":request_id,"phase":phase,"error_class":type(error).__name__,
            "elapsed_ms":round((time.monotonic()-started)*1000)},
            separators=(",",":")),flush=True)

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
        request_id=uuid4().hex
        started=time.monotonic()
        upstream=None
        phase="upstream_connect"
        try:
            upstream=http.client.HTTPConnection(
                "127.0.0.1",self.server.target_port,timeout=330)
            phase="upstream_request"
            upstream.request(self.command,self.path,body=body,headers=headers)
            phase="upstream_response_headers"
            result=upstream.getresponse()
            phase="upstream_response_body"
            payload=result.read()
            status=result.status
            response_headers=result.getheaders()
        except (OSError,TimeoutError,http.client.HTTPException) as error:
            self.transport_diagnostic(request_id,phase,error,started)
            # Upstream I/O is fully buffered before any client response starts.
            # A disconnect while sending this single failure is a client abort.
            try:
                self.fail(502,"IT-TEM QA upstream unavailable")
            except (OSError,TimeoutError) as downstream_error:
                self.transport_diagnostic(request_id,"downstream_error_response",downstream_error,started)
            return
        finally:
            if upstream is not None:
                try:
                    upstream.close()
                except (OSError,TimeoutError,http.client.HTTPException) as error:
                    self.transport_diagnostic(request_id,"upstream_close",error,started)
        try:
            self.send_response(status)
            for k,v in response_headers:
                if k.lower() not in HOP and k.lower() not in ("content-length","server","date"):
                    self.send_header(k,v)
            self.send_header("Content-Length",str(len(payload)))
            self.send_header("Cache-Control","private, no-store")
            self.send_header("X-IT-TEM-Auth-Path","tailscale-sso")
            self.end_headers()
            if self.command!="HEAD":self.wfile.write(payload)
        except (OSError,TimeoutError) as error:
            # Headers may already be on the wire. Never append a second 502
            # response or misclassify a browser cancellation as upstream failure.
            self.transport_diagnostic(request_id,"downstream_response",error,started)

    def log_message(self,format,*args):
        # No secret, cookie, email, or query parameters in gateway logs.
        print("IT_TEM_TAILNET_GATEWAY",self.command,self.path.split("?")[0],
              str(args[1]) if len(args)>1 else "",flush=True)


# Isolated A/B gateways reuse 8443 verified security implementation.
# Existing 8443 default remains untouched; separate instances get dedicated
# signing keys, ports and user-to-actor maps.
SERVICES = {
    "8443": (18987, 18988),
    "10443": (19097, 19096),
    "10500": (19101, 19100),
}

def run():
    key=key_from_file(os.environ["IT_TEM_TAILNET_GATEWAY_KEY_FILE"])
    users=load_users(os.environ["IT_TEM_TAILNET_GATEWAY_USERS_FILE"])
    expected=os.environ["IT_TEM_TAILNET_EXPECTED_HOST"].lower()
    service_port=expected.rsplit(":",1)[-1]
    if (service_port not in SERVICES or
        not re.fullmatch(r"[a-z0-9.-]+\.ts\.net:"+service_port,expected)):
        raise RuntimeError("UNAPPROVED_TAILSCALE_HOST")
    listen_port,target_port=SERVICES[service_port]
    server=ThreadingHTTPServer(("127.0.0.1",listen_port),Gateway)
    server.secret=key
    server.allowed_users=users
    server.expected_host=expected
    server.target_port=target_port
    print("IT_TEM_TAILNET_SSO_MAC_GATEWAY_STARTED",listen_port,len(users),
          "identities","UPSTREAM_PORT",target_port,flush=True)
    server.serve_forever(poll_interval=.25)


if __name__=="__main__":run()
