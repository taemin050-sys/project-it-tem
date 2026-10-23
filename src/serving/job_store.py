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
