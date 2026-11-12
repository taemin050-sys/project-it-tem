"""A51E signed-assertion FAKE PROXY for localhost official React Chrome QA.

TEST ONLY: not a real Tailscale Serve, not real owner/PM SSO authority, no
customer data, GCP or paid Provider. This wrapper impersonates the authorized
macOS signing proxy ONLY in a private loopback synthetic test. It can never
bind a non-loopback address or run under a paid worker config.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import secrets

from demo_staging.app import make_demo_app
from demo_staging.tailnet_assertion import build_assertion
from demo_staging.live.a51e_signed_beta_ingress_ledger import BetaUploadLedger

HOST="macstudio-integration.ts.net:10443"
_ACTOR="alice"
_ROLE="evaluator"


def prepare():
    root=Path(os.environ["A51E_TEST_ROOT"]).resolve(strict=True)
    if not root.is_dir() or not str(root).startswith(
            "/private/tmp/ittem-a51e-"):
        raise RuntimeError("A51E_LOCAL_DISPOSABLE_TEST_ROOT_REQUIRED")
    frontend=root/"frontend"
    if not (frontend/"assets").is_dir() or not (
            frontend/"index.html").is_file():
        raise RuntimeError("A51E_PINNED_REACT_BUNDLE_REQUIRED")
    sha=os.environ.get("A51E_SOURCE_SHA","")
    if len(sha)!=40 or any(c not in "0123456789abcdef" for c in sha):
        raise RuntimeError("A51E_PINNED_GIT_SHA_REQUIRED")
    required={
      "IT_TEM_A51E_SIGNED_BETA_INTAKE":"YES",
      "IT_TEM_A51E_NONBILLABLE_CANDIDATE":"YES",
      "IT_TEM_A51E_MPO_POLICY_STATE":"PENDING_REJECT",
      "IT_TEM_A51D_SIGNED_BETA_RUNTIME":"YES",
      "IT_TEM_A51C_HARD_CAP_ENABLE":"YES",
      "IT_TEM_LIVE_COST_POLICY":"HARD_CAP",
      "IT_TEM_TAILNET_SSO_ONLY":"YES",
      "IT_TEM_TAILNET_AUTH_ENABLED":"YES",
      "IT_TEM_QA_FIXTURE_ENABLED":"YES",
      "IT_TEM_QA_ALLOWED_ACTORS":"alice",
      "IT_TEM_DEMO_SECURE_COOKIE":"YES",
      "IT_TEM_ENABLE_BILLABLE_TEXT_CALLS":"NO",
      "IT_TEM_LIVE_ENABLED":"NO",
      "IT_TEM_LIVE_EXECUTION_APPROVED":"NO",
      "IT_TEM_LIVE_WEB_QUEUE_ENABLED":"NO",
      "IT_TEM_A51D_MPO_FIXTURE_BRIDGE":"NO",
      "IT_TEM_TAILNET_EXPECTED_HOST":HOST,
    }
    for key,value in required.items():
        if os.getenv(key)!=value:
            raise RuntimeError("A51E_UNSAFE_ENV_"+key)
    if any(os.getenv(k) for k in (
        "OPENAI_API_KEY","GOOGLE_API_KEY","GEMINI_API_KEY",
        "ANTHROPIC_API_KEY")):
        raise RuntimeError("A51E_PAID_PROVIDER_CREDENTIAL_REFUSED")
    if not Path(os.environ.get("IT_TEM_LIVE_KOREAN_FONT","")).is_file():
        raise RuntimeError("A51E_LOCAL_KOREAN_FONT_REQUIRED")
    runtime=root/"runtime"
    runtime.mkdir(mode=0o700,exist_ok=True)
    # Test owner-scoped idempotency journal must be EXPLICITLY initialized.
    BetaUploadLedger(runtime/"a51e_beta_upload_request.sqlite",
                     initialize=True)
    # Ephemeral HMAC test secret never included in evidence ZIP/manifest.
    key=secrets.token_hex(32).encode("ascii")
    keyfile=root/"synthetic_private_signing_key_DO_NOT_SHARE"
    keyfile.write_bytes(key);keyfile.chmod(0o600)
    actorsfile=root/"synthetic_roles.json"
    actorsfile.write_text(json.dumps({
        "alice":"evaluator","bob":"evaluator","charlie":"admin",
        "delta":"evaluator","echo":"admin"}))
    actorsfile.chmod(0o600)
    invitation=root/"synthetic_invites.json"
    invitation.write_text(json.dumps({"alice":{
        "role":"evaluator","digest":sha256(b"never-valid-invite").hexdigest()}}))
    invitation.chmod(0o600)
    os.environ["IT_TEM_TAILNET_AUTH_KEY_FILE"]=str(keyfile)
    os.environ["IT_TEM_TAILNET_ACTORS_FILE"]=str(actorsfile)
    underlying=make_demo_app(runtime,invitation,frontend,secure_cookie=True,
                             code_sha=sha)
    return underlying,key


def wrap(app,secret):
    async def signed_proxy(scope,receive,send):
        if scope["type"]!="http":
            return await app(scope,receive,send)
        if not scope.get("client") or scope["client"][0] not in (
                "127.0.0.1","::1"):
            raise RuntimeError("A51E_FAKE_PROXY_REQUIRES_LOOPBACK")
        original={k.lower():v for k,v in scope["headers"]}
        path=scope["raw_path"].decode("latin1")
        query=scope.get("query_string",b"").decode("latin1")
        target=path+("?"+query if query else "")
        method=scope["method"].upper()
        assertions=build_assertion(secret,_ACTOR,_ROLE,method,target,HOST)
        rewritten=[(k,v) for k,v in scope["headers"]
                   if k.lower() not in (b"host",b"origin")
                   and not k.lower().startswith(b"x-ittem-tailnet-")]
        rewritten.append((b"host",HOST.encode("ascii")))
        if method not in ("GET","HEAD","OPTIONS"):
            rewritten.append((b"origin",("https://"+HOST).encode("ascii")))
        rewritten.extend((k.encode("ascii"),v.encode("ascii"))
                         for k,v in assertions.items())
        forwarded=dict(scope)
        forwarded["headers"]=rewritten
        forwarded["scheme"]="https"
        return await app(forwarded,receive,send)
    return signed_proxy


app,secret=prepare()
app=wrap(app,secret)
