"""GCP isolated staging entrypoint (never autostart tunnel)."""
import os
from pathlib import Path
from .app import make_demo_app
BASE=Path(os.environ["IT_TEM_DEMO_ROOT"]).resolve()
if os.getenv("IT_TEM_DEMO_ENABLE_LIVE_CONFIG")=="YES":
    from .live.env_loader import load_from_fixed_path
    load_from_fixed_path(worker=False)
app=make_demo_app(
    BASE/"runtime",
    BASE/"config/invites.sha256.json",
    BASE/"repo/app/dist",
    secure_cookie=os.getenv("IT_TEM_DEMO_SECURE_COOKIE","YES")=="YES",
    code_sha=os.getenv("IT_TEM_DEMO_CODE_SHA","UNPINNED")
)
