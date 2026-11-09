"""A4-1 ephemeral 127.0.0.1 QA fixture server with real Track A React build.

NOT a deployment entrypoint. Requires explicitly disabled paid API settings.
Creates only disposable simulated assets, invite credentials and SQLite.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from PIL import Image
from demo_staging.app import make_demo_app

def prepare() -> object:
    root=Path(os.environ["A41_TEST_ROOT"]).resolve(strict=True)
    if not root.is_dir() or not str(root).startswith("/private/tmp/ittem-a41-"):
        raise RuntimeError("A41_DISPOSABLE_MAC_TEMP_ROOT_REQUIRED")
    frontend=root/"frontend"
    if not (frontend/"index.html").is_file():
        raise RuntimeError("A41_BUNDLED_OFFLINE_REACT_REQUIRED")
    if not (frontend/"assets").is_dir():
        raise RuntimeError("A41_JS_ASSET_DIR_REQUIRED")
    sha=os.environ.get("A41_SOURCE_SHA","")
    if not re.fullmatch(r"[0-9a-f]{40}",sha):
        raise RuntimeError("A41_PINNED_SOURCE_SHA_REQUIRED")
    required={
        "IT_TEM_QA_FIXTURE_ENABLED":"YES",
        "IT_TEM_LIVE_ENABLED":"NO",
        "IT_TEM_LIVE_EXECUTION_APPROVED":"NO",
        "IT_TEM_LIVE_WEB_QUEUE_ENABLED":"NO",
        "IT_TEM_DEMO_SECURE_COOKIE":"NO",
        "IT_TEM_QA_ALLOWED_ACTORS":"alice",
        "IT_TEM_ENABLE_BILLABLE_TEXT_CALLS":"NO",
    }
    for key,value in required.items():
        if os.getenv(key)!=value:raise RuntimeError("A41_UNSAFE_ENV:"+key)
    if any(os.getenv(k) for k in (
        "OPENAI_API_KEY","GOOGLE_API_KEY","GEMINI_API_KEY","ANTHROPIC_API_KEY")):
        raise RuntimeError("A41_PAID_PROVIDER_CREDENTIAL_PRESENT")
    if not Path(os.environ.get("IT_TEM_LIVE_KOREAN_FONT","")).is_file():
        raise RuntimeError("A41_KOREAN_FONT_REQUIRED")
    runtime=root/"isolated"
    runtime.mkdir(exist_ok=True,mode=0o700)
    # No real product images. Not used or copied from Owner/GCP/Track B.
    for index,color in enumerate(((120,130,140),(140,150,160)),1):
        image=root/f"product{index}.png"
        if not image.exists():
            Image.new("RGB",(480,640),color).save(image)
    tokenfile=root/"invite_token.private"
    if tokenfile.exists():
        invite=tokenfile.read_text()
    else:
        import secrets
        invite="a41-fixture-invite-"+secrets.token_hex(24)
        tokenfile.write_text(invite)
        tokenfile.chmod(0o600)
    registry={
      "alice":{"role":"evaluator","digest":hashlib.sha256(invite.encode()).hexdigest()},
      "bob":{"role":"evaluator","digest":hashlib.sha256(("not"+invite).encode()).hexdigest()},
    }
    invitations=root/"invites.json"
    invitations.write_text(json.dumps(registry))
    invitations.chmod(0o600)
    return make_demo_app(runtime,invitations,frontend,
                         secure_cookie=False,code_sha=sha)

app=prepare()
