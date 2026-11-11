"""Credential-free LOCAL_PROTECTED_RENDER_V1 consumer.

This process never imports a Provider adapter or claims paid Queue operations.
An explicit migrated runtime and role policy are required. Crash recovery can
only reproduce the same local recipe and content-addressed output bytes.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import signal
import subprocess
import time
import sys
from threading import Event

from src.image_generation.protected_product import render_protected_product
from src.image_generation.protected_recipe import recipe_content_sha
from .contracts import LiveGateError
from .derived_approval import require_same_context
from .derived_service import renderer_fingerprints


PRODUCTION_ROOT = Path("/home/macstudio/ittem-bp18-product-completion-20261111")


@contextmanager
def protected_release_lease(runtime):
    """Keep a production local render inside its validated, sealed release.

    Sandbox runtimes require no deployment authority. Production shares the
    existing B5 operator lock, so a source switch cannot race an active renderer.
    It never acquires the paid Queue or reads the Provider credential.
    """
    runtime = Path(runtime)
    if runtime.resolve() == PRODUCTION_ROOT / "runtime" and runtime != PRODUCTION_ROOT / "runtime":
        raise LiveGateError("DERIVED_EXPLICIT_RUNTIME_REQUIRED")
    if runtime != PRODUCTION_ROOT / "runtime":
        yield
        return
    from deploy.systemd.bp18_live_launch import worker_release_lease, release_sha, configure, require_web_policy
    with worker_release_lease(PRODUCTION_ROOT):
        source = release_sha(PRODUCTION_ROOT)
        if not Path(__file__).resolve().is_relative_to(PRODUCTION_ROOT / "releases" / source):
            raise LiveGateError("DERIVED_WORKER_RELEASE_MISMATCH")
        guard = PRODUCTION_ROOT / "control/inventory-tools/bp18_b5_derived_contract.py"
        checked = subprocess.run(["/usr/bin/python3", "-I", "-S", "-B", str(guard),
                                  "--target", source], check=False)
        if checked.returncode != 0:
            raise LiveGateError("DERIVED_WORKER_RELEASE_GATE_DENIED")
        fingerprint = configure(PRODUCTION_ROOT, worker=False)
        if not fingerprint or os.environ.get("IT_TEM_DERIVED_ENABLED") != "YES":
            raise LiveGateError("DERIVED_WORKER_DISABLED")
        require_web_policy(PRODUCTION_ROOT, fingerprint)
        os.environ["IT_TEM_DEMO_CODE_SHA"] = source
        yield


def require_no_provider_credentials():
    if any(os.environ.get(name) for name in (
        "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY", "CREDENTIALS_DIRECTORY")):
        raise LiveGateError("DERIVED_WORKER_CREDENTIALS_FORBIDDEN")


def run_once(service, *, worker_id, phase_hook=None):
    require_no_provider_credentials()
    row = service.store.claim_render(worker_id=worker_id, billing_unknown=service.billing_unknown(), lease_seconds=300)
    if row is None:
        return None
    owner, job_id, derived_id = row["actor"], row["job_id"], row["derived_id"]
    try:
        with service.store.transaction() as c:
            grant = service.store.active_admission(owner, job_id, row["grant_id"], expected_revision=row["grant_revision"], c=c)
            reviewer = grant["record"]["payload"]["reviewer"]
            _, job, _, current_sha, _ = service.context(c, reviewer["reviewer_actor"], reviewer["reviewer_role"], job_id, "admit")
            require_same_context(current_sha, row["context_sha"])
            recipe = row["payload"]["recipe"]
            if (recipe_content_sha(recipe) != row["recipe_sha"] or
                    renderer_fingerprints(recipe["render_mode"]) != recipe["code_sha256"]):
                raise LiveGateError("DERIVED_RENDERER_OR_RECIPE_CHANGED")
            service.raw_candidate(job, row["payload"]["context"])
        assets = service.registry.resolve_recipe(owner, job_id, recipe,
            upload_bindings=row["payload"]["upload_bindings"])
        background = service.registry.read_content(owner, job_id, row["payload"]["background_ref"]).data
        result = render_protected_product(recipe, {name: asset.data for name, asset in assets.items()},
            layer_spec=row["payload"]["layer_spec"], roi_spec=row["payload"]["roi_spec"],
            job_id=job_id, copy_revision=job["generation"],
            font_path=service.font_path if recipe["render_mode"] == "composed_protected_product" else None,
            background_bytes=background)
        receipt = {**result.receipt, "job_id": job_id, "derived_id": derived_id,
                   "worker_source_tree_sha": service.source_tree_sha,
                   "recipe_source_tree_sha": recipe["source_tree_sha"],
                   "admission_event_id": row["admission_event_id"], "grant_revision": row["grant_revision"],
                   "admission_context_sha": row["context_sha"], "raw_provider_reference": row["payload"]["context"]}
        artifacts = {
            "preview": service.registry.put_content(owner, job_id, result.image_bytes, "image/png", kind="preview").model_dump(),
            "draft_caption": service.registry.put_content(owner, job_id, result.caption_bytes, "text/plain", kind="caption").model_dump(),
            "local_receipt": service.registry.put_content(owner, job_id,
                json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(),
                "application/json", kind="receipt").model_dump(),
        }
        if phase_hook:
            # Test-only injected crashes deliberately escape normal error
            # handling, leaving the lease recoverable at the same recipe.
            phase_hook("files_published", row)
        with service.store.transaction() as c:
            _, _, _, current_sha, _ = service.context(c, reviewer["reviewer_actor"], reviewer["reviewer_role"], job_id, "admit")
            require_same_context(current_sha, row["context_sha"])
            if service.billing_unknown():
                raise LiveGateError("BILLING_UNKNOWN")
            return service.store.complete_render(actor=owner, job_id=job_id, derived_id=derived_id,
                expected_revision=row["revision"], lease_token=row["lease_token"],
                result_sha=receipt["result_binding_sha"], preview_sha=artifacts["preview"]["sha256"],
                local_receipt_sha=artifacts["local_receipt"]["sha256"], artifacts=artifacts, c=c)
    except (ValueError, OSError, sqlite3.Error) as error:
        code = error.code if isinstance(error, LiveGateError) else "DERIVED_LOCAL_RENDER_FAILED"
        if not isinstance(error, LiveGateError) and str(error).isupper() and " " not in str(error):
            code = str(error)[:100]
        return service.store.fail_render(actor=owner, job_id=job_id, derived_id=derived_id,
            expected_revision=row["revision"], lease_token=row["lease_token"], error_code=code, hold=True)


def service_from_runtime(runtime):
    from src.serving.job_store import JobStore
    from .store import LiveStore
    from .derived_approval import DerivedAuthority
    from .derived_service import DerivedService
    from .derived_store import DerivedStore

    runtime = Path(runtime)
    if not runtime.is_absolute() or runtime.is_symlink():
        raise LiveGateError("DERIVED_EXPLICIT_RUNTIME_REQUIRED")
    database = runtime / "live/live.sqlite"
    DerivedStore(database)  # Verify explicit migration before LiveStore startup.
    def owns(actor, job_id):
        with sqlite3.connect((runtime / "demo.sqlite3").resolve().as_uri()+"?mode=ro", uri=True) as c:
            return c.execute("SELECT 1 FROM jobs WHERE actor=? AND job_id=?", (actor, job_id)).fetchone() is not None
    required = {name: os.environ.get(name) for name in (
        "IT_TEM_DERIVED_AUTHORITY_FILE", "IT_TEM_DERIVED_ROOT", "IT_TEM_DERIVED_FONT",
        "IT_TEM_DERIVED_FONT_LICENSE", "IT_TEM_DERIVED_SOURCE_TREE_SHA")}
    if not all(required.values()):
        raise LiveGateError("DERIVED_WORKER_CONFIGURATION_REQUIRED")
    return DerivedService(LiveStore.open_existing(database), JobStore(runtime/"jobs"), owns,
        root=Path(required["IT_TEM_DERIVED_ROOT"]), authority=DerivedAuthority(Path(required["IT_TEM_DERIVED_AUTHORITY_FILE"])),
        font_path=Path(required["IT_TEM_DERIVED_FONT"]), license_path=Path(required["IT_TEM_DERIVED_FONT_LICENSE"]),
        source_tree_sha=required["IT_TEM_DERIVED_SOURCE_TREE_SHA"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--worker-id", default="protected-local-renderer")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    require_no_provider_credentials()
    stopping = Event()
    signal.signal(signal.SIGTERM, lambda *_: stopping.set())
    signal.signal(signal.SIGINT, lambda *_: stopping.set())
    with protected_release_lease(args.runtime):
        service = service_from_runtime(args.runtime)
        while not stopping.is_set():
            row = run_once(service, worker_id=args.worker_id)
            if row:
                print(json.dumps({"derived_id": row["derived_id"], "state": row["state"]}), flush=True)
            if args.once:
                return
            if row is None:
                stopping.wait(1)


if __name__ == "__main__":
    main()
