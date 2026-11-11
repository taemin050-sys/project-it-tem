#!/usr/bin/env python3
"""Disposable, loopback-only Signed HTTP fixture for derived browser QA.

Never use on GCP or a real runtime. Provider constructors are blocked, credentials
are removed in this process, Paid Live is disabled, and the only worker is local.
The synthetic signer is explicitly NOT real Tailscale/Owner/PM authentication.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import secrets
import sys
import threading

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont
from starlette.responses import JSONResponse
import uvicorn

from demo_staging.app import make_demo_app
from demo_staging.live import pipeline, worker
from demo_staging.live.derived_store import migrate_derived_schema
from demo_staging.live.derived_worker import run_once
from demo_staging.tailnet_assertion import build_assertion
from src.image_generation.backend_adapter import BackendGeneratedImage
from tests.demo_live.test_live_contracts import sample_input
from tests.demo_live.test_pipeline import FakeOwner

ACTOR = "a_test_pm"
HOST = "derived-qa.example.ts.net:10500"
FONT = REPO / "app/node_modules/pretendard/dist/public/variable/PretendardVariable.ttf"
LICENSE = REPO / "app/node_modules/pretendard/dist/LICENSE.txt"


def encoded(image):
    output = BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


def photo(color):
    image = Image.new("RGB", (450, 600), "#f1f4f2")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((110, 125, 345, 550), 28, fill=color, outline="#173b4d", width=3)
    draw.rectangle((192, 75, 245, 135), fill="#173b4d")
    draw.rounded_rectangle((165, 55, 300, 82), 8, fill="#173b4d")
    draw.rectangle((135, 280, 320, 430), fill="white")
    draw.text((158, 310), "FIXTURE", font=ImageFont.truetype(str(FONT), 30), fill="#173b4d")
    draw.text((167, 365), "가상 제품", font=ImageFont.truetype(str(FONT), 22), fill="#173b4d")
    return encoded(image)


def background(mode, ad_copy):
    image = Image.new("RGB", (1080, 1350), "#dcece8")
    draw = ImageDraw.Draw(image)
    # Deliberately synthetic geometry; no image Provider is involved.
    draw.ellipse((120, 1080, 980, 1240), fill="#b4d1ca")
    if mode == "freeform":
        draw.rounded_rectangle((390, 425, 700, 960), 35, fill="#a6bfca")
        draw.text((65, 80), ad_copy["headline"], font=ImageFont.truetype(str(FONT), 67), fill="#173b4d")
        draw.text((65, 210), ad_copy["subline"], font=ImageFont.truetype(str(FONT), 42), fill="#173b4d")
        draw.rounded_rectangle((280, 1175, 800, 1270), 40, fill="#173b4d")
        draw.text((340, 1195), ad_copy["cta"], font=ImageFont.truetype(str(FONT), 38), fill="white")
    return encoded(image.resize((1152, 1440), Image.Resampling.LANCZOS))


def protected_snapshot(flow, manifest):
    raw = {}
    for item in manifest["jobs"]:
        job = item["job_id"]
        raw[job] = {"state": flow.state.get(ACTOR, job), "files": {
            p.name: sha256(p.read_bytes()).hexdigest() for p in (flow.root / "outputs" / job).iterdir() if p.is_file()}}
    with flow.cost.connect() as c:
        attempts = [dict(row) for row in c.execute("SELECT * FROM attempts ORDER BY rowid")]
    return {"raw_jobs": raw, "attempts": attempts}


class SyntheticLoopbackSigner:
    def __init__(self, app, key, manifest, ui_origin):
        self.app, self.key, self.manifest, self.ui_origin = app, key, manifest, ui_origin
        self.requests = []

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope["headers"])
        host = headers.get(b"host", b"").decode()
        origin = headers.get(b"origin", b"").decode()
        if (scope.get("client", ("",))[0] not in ("127.0.0.1", "::1", "testclient")
                or host not in ("127.0.0.1:18325", "127.0.0.1:18425", HOST)
                or (scope["method"] not in ("GET", "HEAD") and origin not in (self.ui_origin, f"https://{HOST}"))):
            return await JSONResponse({"detail": "LOOPBACK_FIXTURE_ONLY"}, status_code=403)(scope, receive, send)
        if scope["path"] == "/__derived_qa__/manifest":
            return await JSONResponse(self.manifest, headers={"Cache-Control": "no-store"})(scope, receive, send)
        if scope["path"].startswith(("/demo/api/", "/api/v1/jobs")):
            target = scope["path"] + ("?" + scope["query_string"].decode() if scope["query_string"] else "")
            assertion = build_assertion(self.key, ACTOR, "admin", scope["method"], target, HOST)
            filtered = [(key, value) for key, value in scope["headers"]
                        if key not in (b"host", b"origin") and not key.lower().startswith(b"x-ittem-tailnet-")]
            scope = dict(scope, scheme="https", headers=[*filtered, (b"host", HOST.encode()),
                (b"origin", f"https://{HOST}".encode()), *[(k.lower().encode(), v.encode()) for k, v in assertion.items()]])
            self.requests.append({"method": scope["method"], "target": target, "synthetic_actor": ACTOR})
        return await self.app(scope, receive, send)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    args = parser.parse_args()
    root = args.runtime
    if not root.is_absolute() or root.exists() or not str(root).startswith(("/private/tmp/", "/tmp/")):
        parser.error("Use a new absolute /private/tmp/ runtime, never a real environment")
    root.mkdir(mode=0o700, parents=True)
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY", "CREDENTIALS_DIRECTORY",
                 "IT_TEM_BP18_F11_ENABLED", "IT_TEM_BP18_F09_REQUIRED", "IT_TEM_BP18_REVIEW_POLICY_REQUIRED",
                 "IT_TEM_REVIEW_POLICY_VERSION", "IT_TEM_REVIEW_POLICY_SHA"):
        os.environ.pop(name, None)
    key = secrets.token_bytes(48)
    key_file = root / "synthetic-hmac.key"
    key_file.write_bytes(key)
    key_file.chmod(0o600)
    actors = root / "actors.json"
    actors.write_text(json.dumps({ACTOR: "admin", "a_test_fe": "evaluator", "a_test_text": "evaluator",
                                 "a_test_image": "evaluator", "a_test_ops": "evaluator"}))
    actors.chmod(0o600)
    authority = root / "authority.json"
    authority.write_text(json.dumps({"schema": "bp18-derived-authority-v1", "revision": 1,
        "business_roles": {ACTOR: "owner"}, "delegations": []}))
    authority.chmod(0o600)
    invitations = root / "invitations.json"
    invitations.write_text("{}")
    dist = root / "empty-dist"
    dist.mkdir()
    (dist / "index.html").write_text("OFFLINE_FIXTURE; use the separate Vite QA entry")
    (dist / "assets").mkdir()
    os.environ.update({"IT_TEM_TAILNET_AUTH_ENABLED": "YES", "IT_TEM_TAILNET_SSO_ONLY": "YES",
        "IT_TEM_TAILNET_AUTH_KEY_FILE": str(key_file), "IT_TEM_TAILNET_ACTORS_FILE": str(actors),
        "IT_TEM_TAILNET_EXPECTED_HOST": HOST, "IT_TEM_LIVE_ENABLED": "NO", "IT_TEM_LIVE_EXECUTION_APPROVED": "NO",
        "IT_TEM_LIVE_WEB_QUEUE_ENABLED": "NO", "IT_TEM_DERIVED_ENABLED": "YES",
        "IT_TEM_DERIVED_AUTHORITY_FILE": str(authority), "IT_TEM_DERIVED_ROOT": str(root / "protected"),
        "IT_TEM_DERIVED_FONT": str(FONT), "IT_TEM_DERIVED_FONT_LICENSE": str(LICENSE),
        "IT_TEM_DERIVED_SOURCE_TREE_SHA": "1" * 40})

    def no_provider(*_args, **_kwargs):
        raise RuntimeError("OFFLINE_FIXTURE_PROVIDER_FORBIDDEN")

    pipeline.OfficialTextProvider = no_provider
    worker.live_image_adapter = no_provider
    app = make_demo_app(root, invitations, dist, secure_cookie=True, code_sha="1" * 40)
    flow = app.state.live_pipeline
    manifest = {"provenance": "OFFLINE_FIXTURE", "provider_calls": 0, "authentication": "SYNTHETIC_LOOPBACK_TEST_SIGNER", "jobs": []}
    with TestClient(app, base_url=f"https://{HOST}") as client:
        for mode in ("composed", "freeform"):
            path = "/api/v1/jobs"
            headers = {"Host": HOST, "Origin": f"https://{HOST}", **build_assertion(key, ACTOR, "admin", "POST", path, HOST)}
            uploaded = client.post(path, headers=headers, files=[
                ("product_images", ("fixture-a.png", photo("#9eb9bc"), "image/png")),
                ("product_images", ("fixture-b.png", photo("#c1cfbb"), "image/png"))])
            uploaded.raise_for_status()
            job = uploaded.json()["job_id"]
            flow.prepare(ACTOR, job, {**sample_input(), "generation_mode": mode, "image_size": "4:5"}, template_profile="A")
            owner = FakeOwner()
            reviewed = flow.text(ACTOR, job, owner, offline=True)
            flow.state.approve_copy(ACTOR, job, reviewed["generation"], reviewed["review_sha"])
            prompt = flow.prompt(ACTOR, job, owner, offline=True)
            copy = json.loads(prompt["copy_json"])["ad_copy"]
            raw = background(mode, copy)
            flow.accept_image_result(ACTOR, job, BackendGeneratedImage(image_bytes=raw, mime_type="image/png",
                width=1152, height=1440, sha256=sha256(raw).hexdigest(), job_id=job,
                copy_revision=prompt["generation"], copy_hash=prompt["copy_sha"], mock=True,
                receipt={"mode": "OFFLINE_MOCK_TRANSPORT", "provider_calls": 0,
                         "generation_mode": mode, "state": "succeeded"}), offline=True)
            manifest["jobs"].append({"job_id": job, "mode": mode, "target": {"width": 1080, "height": 1350}, "approved_copy": copy})
    migrate_derived_schema(flow.state.filename)
    before = protected_snapshot(flow, manifest)
    (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    wrapper = SyntheticLoopbackSigner(app, key, manifest, "http://127.0.0.1:18425")
    stop = threading.Event()

    def local_worker():
        while not stop.wait(.25):
            service = getattr(app.state, "derived_service", None)
            if service:
                try:
                    run_once(service, worker_id="offline-browser-local-only")
                except Exception as error:
                    print(json.dumps({"local_worker_error": str(error)}), flush=True)

    thread = threading.Thread(target=local_worker, daemon=True)
    thread.start()
    print(json.dumps({"provenance": "OFFLINE_FIXTURE", "runtime": str(root), "backend": "http://127.0.0.1:18325",
                      "frontend": "http://127.0.0.1:18425/derived-qa.html"}), flush=True)
    try:
        uvicorn.run(wrapper, host="127.0.0.1", port=18325, log_level="warning")
    finally:
        stop.set()
        thread.join(timeout=5)
        after = protected_snapshot(flow, manifest)
        result = {"provenance": "OFFLINE_FIXTURE", "provider_calls": 0, "raw_and_cost_unchanged": before == after,
                  "before": before, "after": after, "http_requests": wrapper.requests}
        (root / "browser-qa-preservation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
