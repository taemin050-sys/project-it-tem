"""GCP isolated staging entrypoint (never autostart tunnel)."""
import os
from pathlib import Path
from .app import make_demo_app
BASE=Path(os.environ["IT_TEM_DEMO_ROOT"]).resolve()
app=make_demo_app(
    BASE/"runtime",
    BASE/"config/invites.sha256.json",
    BASE/"repo/app/dist",
    secure_cookie=os.getenv("IT_TEM_DEMO_SECURE_COOKIE","YES")=="YES",
    code_sha=os.getenv("IT_TEM_DEMO_CODE_SHA","UNPINNED")
)
