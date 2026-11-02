"""Single-process, filesystem-backed job ledger for the IT-TEM prototype.

Contract is provisional pending the team's interface sign-off.
Do not share the storage directory with multiple writers/processes.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")
ASSET_ID_RE = re.compile(r"^[0-9a-f]{32}$")
EXTENSIONS = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}


@dataclass(frozen=True)
class ValidatedUpload:
    original_filename: str
    content_type: str
    data: bytes
    width: int
    height: int
    sha256: str


class JobStore:
    """One-process storage only. Paths are UUID-derived; clients never choose paths."""

    def __init__(self, root: Path):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._lock = threading.RLock()

    @staticmethod
    def _valid_job_id(job_id: str) -> bool:
        return bool(JOB_ID_RE.fullmatch(job_id))

    @staticmethod
    def _valid_asset_id(asset_id: str) -> bool:
        return bool(ASSET_ID_RE.fullmatch(asset_id))

    def _job_dir(self, job_id: str) -> Path:
        if not self._valid_job_id(job_id):
            raise HTTPException(status_code=404, detail="Job not found")
        return self.root / job_id

    def get_job(self, job_id: str) -> dict[str, Any]:
        job_file = self._job_dir(job_id) / "job.json"
        try:
            with job_file.open("r", encoding="utf-8") as stream:
                result = json.load(stream)
        except (FileNotFoundError, NotADirectoryError):
            raise HTTPException(status_code=404, detail="Job not found") from None
        if result.get("job_id") != job_id:
            raise HTTPException(status_code=500, detail="Job record is invalid")
        return result

    def create_job(
        self, product_images: list[ValidatedUpload], reference_images: list[ValidatedUpload]
    ) -> dict[str, Any]:
        if not 2 <= len(product_images) <= 5:
            raise HTTPException(status_code=422, detail="product_images must contain 2–5 images")
        if len(reference_images) > 5:
            raise HTTPException(status_code=422, detail="reference_images must contain 0–5 images")
        uploads = product_images + reference_images
        if len({item.sha256 for item in uploads}) != len(uploads):
            raise HTTPException(status_code=422, detail="Duplicate image content is not allowed")

        job_id = uuid4().hex
        job_dir = self._job_dir(job_id)
        created_at = datetime.now(timezone.utc).isoformat()
        metadata: dict[str, Any] = {
            "job_id": job_id,
            "status": "INPUTS_VALIDATED",
            "created_at": created_at,
            "assets": [],
        }
        with self._lock:
            job_dir.mkdir(mode=0o700)
            try:
                for role, items in (("product", product_images), ("reference", reference_images)):
                    for upload in items:
                        asset_id = uuid4().hex
                        extension = EXTENSIONS[upload.content_type]
                        filename = asset_id + extension
                        destination = job_dir / filename
                        with destination.open("xb") as file:
                            file.write(upload.data)
                            file.flush()
                            os.fsync(file.fileno())
                        metadata["assets"].append({
                            "asset_id": asset_id,
                            "role": role,
                            "original_filename": upload.original_filename,
                            "content_type": upload.content_type,
                            "size_bytes": len(upload.data),
                            "width": upload.width,
                            "height": upload.height,
                            "sha256": upload.sha256,
                        })
                temp = job_dir / "job.json.tmp"
                with temp.open("x", encoding="utf-8") as file:
                    json.dump(metadata, file, ensure_ascii=False, indent=2)
                    file.flush()
                    os.fsync(file.fileno())
                os.replace(temp, job_dir / "job.json")
            except BaseException:
                shutil.rmtree(job_dir)
                raise
        return metadata

    def get_asset(self, job_id: str, asset_id: str) -> tuple[Path, dict[str, Any]]:
        if not self._valid_asset_id(asset_id):
            raise HTTPException(status_code=404, detail="Asset not found")
        job = self.get_job(job_id)
        asset = next((asset for asset in job["assets"] if asset["asset_id"] == asset_id), None)
        if not asset:
            raise HTTPException(status_code=404, detail="Asset not found")
        path = self._job_dir(job_id) / (asset_id + EXTENSIONS[asset["content_type"]])
        if not path.is_file() or path.is_symlink():
            raise HTTPException(status_code=404, detail="Asset not found")
        return path, asset


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

# Internal mock-only artifact names; no client-controlled filenames or paths.
MOCK_ARTIFACTS = {
    "plan": ("plan.json", "application/json"),
    "copy": ("copy.json", "application/json"),
    "image": ("image_candidate.png", "image/png"),
    "final": ("final_mock.png", "image/png"),
    "caption": ("caption.txt", "text/plain; charset=utf-8"),
}


def transition_job(
    store: JobStore,
    job_id: str,
    *,
    expected_status: str,
    next_status: str,
    updates: dict[str, Any] | None = None,
    artifact_kind: str | None = None,
    artifact_bytes: bytes | None = None,
    additional_artifacts: dict[str, bytes] | None = None,
) -> dict[str, Any]:
    """Single-worker state change; artifacts and ledger are published together.

    State preconditions reject duplicate/out-of-order requests (409). Artifact
    files are only visible in the ledger after their bytes are fsynced. On
    ledger failure, newly created artifact files are removed.
    """
    if (artifact_kind is None) != (artifact_bytes is None):
        raise ValueError("Artifact name and data must be supplied together")
    contents = dict(additional_artifacts or {})
    if artifact_kind is not None:
        if artifact_kind in contents:
            raise ValueError("Duplicate artifact kind")
        contents[artifact_kind] = artifact_bytes
    if any(kind not in MOCK_ARTIFACTS for kind in contents):
        raise ValueError("Unsupported mock artifact")

    with store._lock:
        current = store.get_job(job_id)
        if current["status"] != expected_status:
            raise HTTPException(
                status_code=409,
                detail={"error": "INVALID_WORKFLOW_STATE", "current_status": current["status"],
                        "expected_status": expected_status},
            )

        next_job = dict(current)
        next_job["status"] = next_status
        next_job.update(updates or {})
        # B1 Fake opt-in only. Invalidate persisted reviews BEFORE publishing a
        # trusted Job mutation. A failed publication may invalidate a review
        # unnecessarily, but can never leave a modified Job with a valid stale
        # review. The default B0 store has no observer and is unchanged.
        observer = getattr(store, "_b1_observe_mutation", None)
        if observer is not None:
            observer(current, next_job)
        job_dir = store._job_dir(job_id)
        registered = dict(current.get("artifacts", {}))
        for kind, data in contents.items():
            filename, media_type = MOCK_ARTIFACTS[kind]
            target = job_dir / filename
            if kind in registered or target.exists() or target.is_symlink():
                raise HTTPException(status_code=409, detail="Artifact already exists")
            registered[kind] = {
                "kind": kind,
                "content_type": media_type,
                "size_bytes": len(data),
                "download_url": f"/api/v1/jobs/{job_id}/artifacts/{kind}",
            }
        if contents:
            next_job["artifacts"] = registered

        # Opt-in S5-I0 trusted mutation observer. The earlier B1-R hook
        # (from its separate unmerged PR) can coexist without conflict.
        # This runs before any artifact or Job ledger publication.
        s5_observer = getattr(store, "_s5_mutation_observer", None)
        if s5_observer is not None:
            s5_observer(current, next_job)

        pending: list[Path] = []
        published: list[Path] = []
        temp_ledger = job_dir / f"job.{uuid4().hex}.tmp"
        try:
            for kind, data in contents.items():
                filename, _ = MOCK_ARTIFACTS[kind]
                target = job_dir / filename
                temp = job_dir / f"artifact.{uuid4().hex}.tmp"
                pending.append(temp)
                with temp.open("xb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temp, target)
                pending.remove(temp)
                published.append(target)
            with temp_ledger.open("x", encoding="utf-8") as stream:
                json.dump(next_job, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_ledger, job_dir / "job.json")
        except BaseException:
            temp_ledger.unlink(missing_ok=True)
            for path in pending + published:
                path.unlink(missing_ok=True)
            raise
        return next_job


def get_mock_artifact(store: JobStore, job_id: str, kind: str) -> tuple[Path, str]:
    if kind not in MOCK_ARTIFACTS:
        raise HTTPException(status_code=404, detail="Artifact not found")
    job = store.get_job(job_id)
    if kind not in job.get("artifacts", {}):
        raise HTTPException(status_code=404, detail="Artifact not found")
    filename, media_type = MOCK_ARTIFACTS[kind]
    path = store._job_dir(job_id) / filename
    if not path.is_file() or path.is_symlink():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return path, media_type
