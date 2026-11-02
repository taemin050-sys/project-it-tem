"""S5-I0 trusted *offline-only* image/Serving rehearsal.

No public HTTP endpoints, no Text Owner model, no Compliance attestation,
no real provider: use the existing owner's Python image package when merged
(or in a throwaway integration checkout), never vendor/copy it here.

The copy approval in this module is an explicit local fixture confirmation,
NOT B1-R Compliance or real-user authentication. It cannot run without the
store's opt-in trusted mutation observer and a provider explicitly configured
for in-process MockTransport and live_calls=False.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from PIL import Image

from .job_store import JobStore, get_mock_artifact, transition_job

_REVIEW_INPUTS = ("plan", "assets", "copy_candidate", "offline_copy")
_APPROVED_INPUTS = _REVIEW_INPUTS + ("offline_copy_approval", "image_candidate", "offline_image_approval")


def _fail(reason: str) -> None:
    raise HTTPException(409, detail={"error": "OFFLINE_IMAGE_GATE_BLOCKED", "reason": reason})


def _hash(value: dict) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")).hexdigest()


def _owner():
    # Owner sources intentionally do NOT exist in current official dev. This
    # import becomes available only in an isolated joint checkout or after
    # the image team PR is independently approved and merged.
    try:
        from src import image_generation as owner
        from src.image_generation.contracts import content_hash
    except ImportError as exc:
        raise RuntimeError("IMAGE_OWNER_SOURCE_NOT_INSTALLED") from exc
    return owner, content_hash


def _assets(store: JobStore, job: dict) -> tuple[list[bytes], list[bytes]]:
    products, references = [], []
    for asset in job["assets"]:
        path, stored = store.get_asset(job["job_id"], asset["asset_id"])
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != stored["sha256"]:
            _fail("INPUT_ASSET_HASH_CHANGED")
        (products if stored["role"] == "product" else references).append(data)
    if not 2 <= len(products) <= 5 or len(references) > 5:
        _fail("INPUT_ASSET_COUNT_INVALID")
    return products, references


def _assert_full_snapshot(snapshot: dict, approved_hash: str) -> None:
    if type(snapshot) is not dict or set(snapshot) != {
        "plan", "ad_copy", "caption", "hashtags"
    }:
        _fail("INVALID_FULL_COPY_SNAPSHOT")
    ad = snapshot.get("ad_copy")
    if not isinstance(snapshot["plan"], dict) or not isinstance(ad, dict) or set(ad) != {
        "headline", "subline", "cta"
    } or any(type(ad[k]) is not str for k in ad):
        _fail("INVALID_FULL_COPY_SNAPSHOT")
    if type(snapshot["caption"]) is not str or type(snapshot["hashtags"]) is not list or any(
        type(x) is not str for x in snapshot["hashtags"]
    ):
        _fail("INVALID_FULL_COPY_SNAPSHOT")
    try:
        if _hash(snapshot) != approved_hash:
            _fail("FULL_COPY_HASH_MISMATCH")
    except (TypeError, ValueError, OverflowError, UnicodeError, RecursionError):
        _fail("INVALID_FULL_COPY_SNAPSHOT")


class OfflineImageFlow:
    """Trusted, single-process, non-HTTP, deterministic integration harness."""

    def __init__(self, store: JobStore, *, adapter: Any, project_id: UUID, font_path: Path):
        if not isinstance(project_id, UUID) or not isinstance(font_path, Path):
            raise ValueError("A stable project UUID and trusted font path are required")
        provider = getattr(getattr(adapter, "processor", None), "adapter", None)
        config = getattr(provider, "config", None)
        if (type(getattr(provider, "offline", None)) is not bool
                or provider.offline is not True
                or type(getattr(config, "live_calls", None)) is not bool
                or config.live_calls is not False):
            raise ValueError("OFFLINE_MOCK_TRANSPORT_REQUIRED: real provider disabled")
        self.store, self.adapter, self.project_id, self.font_path = (
            store, adapter, project_id, font_path,
        )
        if getattr(store, "_s5_mutation_observer", None) is not None:
            raise RuntimeError("Only one S5-I0 offline flow may own a JobStore")
        store._s5_mutation_observer = self._observe

    @staticmethod
    def _observe(old: dict, new: dict) -> None:
        if "offline_copy" not in old and "offline_copy" not in new:
            return
        review_changed = any(old.get(k) != new.get(k) for k in _REVIEW_INPUTS)
        image_candidate_changed = old.get("image_candidate") != new.get("image_candidate")
        image_approval_changed = old.get("offline_image_approval") != new.get("offline_image_approval")
        if old["status"] not in {"COPY_REVIEW_REQUIRED", "COPY_APPROVED",
                                  "IMAGE_REVIEW_REQUIRED", "IMAGE_APPROVED"}:
            if review_changed or image_candidate_changed or image_approval_changed:
                _fail("OFFLINE_INPUT_CHANGE_OUT_OF_SCOPE")
        if old["status"] in {"COPY_APPROVED", "IMAGE_REVIEW_REQUIRED", "IMAGE_APPROVED"}:
            if review_changed or (
                old.get("offline_copy_approval") != new.get("offline_copy_approval")
            ):
                _fail("APPROVED_COPY_IMMUTABLE")
        if ("image_candidate" in old and image_candidate_changed
                or "offline_image_approval" in old and image_approval_changed):
            _fail("IMAGE_CANDIDATE_IMMUTABLE")
        if review_changed and old["status"] == "COPY_REVIEW_REQUIRED":
            new["offline_input_generation"] = old.get("offline_input_generation", 0) + 1

    def stage_copy(
        self, job_id: str, *, copy_output: dict, copy_revision: str | int,
        product_analysis: dict, image_prompt: dict | str,
    ) -> dict:
        """Stage a full Text-like fixture, *before* its local confirmation."""
        owner, hash_copy = _owner()
        with self.store._lock:
            job = self.store.get_job(job_id)
            if job["status"] != "COPY_REVIEW_REQUIRED":
                _fail("COPY_NOT_AWAITING_REVIEW")
            # Owner DTO enforces opaque revision type; '1' and 1 must differ.
            products, references = _assets(self.store, job)
            if not (type(copy_revision) is str or type(copy_revision) is int):
                _fail("INVALID_COPY_REVISION")
            try:
                candidate = owner.BackendImageInput(
                    job_id=job_id, copy_revision=copy_revision,
                    copy_hash=hash_copy(copy_output),
                    product_analysis=product_analysis, image_prompt=image_prompt,
                    ad_copy=copy_output["ad_copy"], caption=copy_output["caption"],
                    hashtags=copy_output["hashtags"], product_images=products,
                    reference_images=references,
                )
            except (KeyError, ValueError, TypeError) as exc:
                _fail("INVALID_OWNER_INPUT_FIXTURE")
            digest = hash_copy(copy_output)
            _assert_full_snapshot(copy_output, digest)
            staged = {
                "copy_output": deepcopy(copy_output),
                "copy_revision": copy_revision,
                "copy_hash": digest,
                "stage_generation": job.get("offline_input_generation", 0) + 1,
                "product_analysis": deepcopy(product_analysis),
                "image_prompt": deepcopy(image_prompt),
                "plan_at_stage": deepcopy(job.get("plan")),
                "copy_candidate_at_stage": deepcopy(job.get("copy_candidate")),
                "assets_at_stage": deepcopy(job["assets"]),
                "review_scope": "OFFLINE_FIXTURE_NO_COMPLIANCE",
            }
            return transition_job(
                self.store, job_id, expected_status="COPY_REVIEW_REQUIRED",
                next_status="COPY_REVIEW_REQUIRED",
                updates={"offline_copy": staged},
            )

    def approve_fixture_copy(self, job_id: str) -> dict:
        """Explicit trusted offline fixture approval, never a public HTTP route."""
        with self.store._lock:
            job = self.store.get_job(job_id)
            if job["status"] != "COPY_REVIEW_REQUIRED":
                _fail("COPY_NOT_AWAITING_REVIEW")
            stage = job.get("offline_copy")
            if not isinstance(stage, dict) or stage.get("review_scope") != "OFFLINE_FIXTURE_NO_COMPLIANCE":
                _fail("OFFLINE_COPY_NOT_STAGED")
            _assert_full_snapshot(stage["copy_output"], stage["copy_hash"])
            if stage.get("stage_generation") != job.get("offline_input_generation"):
                _fail("STALE_STAGED_COPY_GENERATION")
            if (job.get("plan") != stage["plan_at_stage"] or
                job.get("copy_candidate") != stage["copy_candidate_at_stage"] or
                job["assets"] != stage["assets_at_stage"]):
                _fail("STAGED_COPY_CONTEXT_CHANGED")
            # Both original bytes and their order must remain identical.
            _assets(self.store, job)
            binding = {
                "copy_hash": stage["copy_hash"],
                "copy_revision": stage["copy_revision"],
                "generation": job.get("offline_input_generation", 0),
                "scope": "OFFLINE_FIXTURE_APPROVAL_NOT_COMPLIANCE",
            }
            return transition_job(
                self.store, job_id, expected_status="COPY_REVIEW_REQUIRED",
                next_status="COPY_APPROVED",
                updates={"copy_approved": True, "offline_copy_approval": binding},
            )

    def _approved_copy(self, job: dict) -> dict:
        stage = job.get("offline_copy")
        binding = job.get("offline_copy_approval")
        if not isinstance(stage, dict) or not isinstance(binding, dict):
            _fail("MISSING_APPROVED_FULL_COPY")
        _assert_full_snapshot(stage["copy_output"], stage["copy_hash"])
        if (binding.get("scope") != "OFFLINE_FIXTURE_APPROVAL_NOT_COMPLIANCE"
            or stage.get("stage_generation") != job.get("offline_input_generation")
            or binding.get("generation") != job.get("offline_input_generation")
            or (type(binding.get("copy_revision")) is not type(stage["copy_revision"]))
            or binding.get("copy_revision") != stage["copy_revision"]
            or binding.get("copy_hash") != stage["copy_hash"]):
            _fail("COPY_APPROVAL_BINDING_CHANGED")
        if (job.get("plan") != stage["plan_at_stage"] or
            job.get("copy_candidate") != stage["copy_candidate_at_stage"] or
            job["assets"] != stage["assets_at_stage"]):
            _fail("APPROVED_COPY_CONTEXT_CHANGED")
        return stage

    def generate(self, job_id: str) -> dict:
        owner, content_hash = _owner()
        with self.store._lock:
            job = self.store.get_job(job_id)
            if job["status"] != "COPY_APPROVED":
                _fail("COPY_NOT_APPROVED")
            stage = self._approved_copy(job)
            products, references = _assets(self.store, job)
            args = owner.BackendImageInput(
                job_id=job_id, copy_revision=stage["copy_revision"],
                copy_hash=stage["copy_hash"],
                product_analysis=stage["product_analysis"],
                image_prompt=stage["image_prompt"],
                ad_copy=stage["copy_output"]["ad_copy"],
                caption=stage["copy_output"]["caption"],
                hashtags=stage["copy_output"]["hashtags"],
                product_images=products, reference_images=references,
            )
            # Validate offline transport every time before this code can
            # enter the owner's attempt ledger; automatic retries disabled.
            provider = self.adapter.processor.adapter
            if provider.offline is not True or provider.config.live_calls is not False:
                _fail("OFFLINE_PROVIDER_NOT_AVAILABLE")
            # Same project UUID/job ID after an interrupted write; owner reuses
            # its persisted attempt/asset rather than issuing a second request.
            output = self.adapter.generate(args, project_id=self.project_id)
            if output.mock is not True or hashlib.sha256(output.image_bytes).hexdigest() != output.sha256:
                _fail("OFFLINE_IMAGE_OUTPUT_INVALID")
            if (output.copy_revision != stage["copy_revision"]
                or type(output.copy_revision) is not type(stage["copy_revision"])
                or output.copy_hash != stage["copy_hash"]
                or output.job_id != job_id):
                _fail("IMAGE_COPY_IDENTITY_MISMATCH")
            return transition_job(
                self.store, job_id, expected_status="COPY_APPROVED",
                next_status="IMAGE_REVIEW_REQUIRED",
                updates={"image_candidate": {
                    "mock": True, "source": "OWNER_OFFLINE_MOCKTRANSPORT",
                    "sha256": output.sha256, "width": output.width,
                    "height": output.height, "copy_hash": output.copy_hash,
                    "copy_revision": output.copy_revision,
                    "receipt": output.receipt,
                }},
                artifact_kind="image", artifact_bytes=output.image_bytes,
            )

    def approve_image(self, job_id: str) -> dict:
        with self.store._lock:
            job = self.store.get_job(job_id)
            if job["status"] != "IMAGE_REVIEW_REQUIRED":
                _fail("IMAGE_NOT_AWAITING_REVIEW")
            stage = self._approved_copy(job)
            image = job.get("image_candidate")
            path, _ = get_mock_artifact(self.store, job_id, "image")
            data = path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            if (not isinstance(image, dict) or digest != image.get("sha256") or
                image.get("copy_hash") != stage["copy_hash"] or
                type(image.get("copy_revision")) is not type(stage["copy_revision"]) or
                image.get("copy_revision") != stage["copy_revision"]):
                _fail("IMAGE_APPROVAL_HASH_MISMATCH")
            return transition_job(
                self.store, job_id, expected_status="IMAGE_REVIEW_REQUIRED",
                next_status="IMAGE_APPROVED",
                updates={"image_approved": True, "offline_image_approval": {
                    "sha256": digest, "copy_hash": stage["copy_hash"],
                    "copy_revision": stage["copy_revision"],
                    "scope": "OFFLINE_FIXTURE_APPROVAL_NOT_REAL_USER",
                }},
            )

    def compose(self, job_id: str, *, layout: dict) -> dict:
        owner, _ = _owner()
        with self.store._lock:
            job = self.store.get_job(job_id)
            if job["status"] != "IMAGE_APPROVED":
                _fail("IMAGE_NOT_APPROVED")
            stage = self._approved_copy(job)
            image = job.get("offline_image_approval")
            if not isinstance(image, dict) or image.get("scope") != "OFFLINE_FIXTURE_APPROVAL_NOT_REAL_USER":
                _fail("IMAGE_APPROVAL_MISSING")
            original, _ = get_mock_artifact(self.store, job_id, "image")
            data = original.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            if (digest != image.get("sha256") or
                image.get("copy_hash") != stage["copy_hash"] or
                type(image.get("copy_revision")) is not type(stage["copy_revision"]) or
                image.get("copy_revision") != stage["copy_revision"]):
                _fail("APPROVED_IMAGE_CHANGED")
            result = owner.compose_ad_png(
                owner.CompositionInput(
                    job_id=job_id, image_bytes=data, image_sha256=digest,
                    copy_revision=stage["copy_revision"],
                    copy_hash=stage["copy_hash"],
                    copy_output=stage["copy_output"], layout=layout,
                ),
                font_path=self.font_path,
            )
            if (result.copy_hash != stage["copy_hash"]
                or result.copy_revision != stage["copy_revision"]
                or type(result.copy_revision) is not type(stage["copy_revision"])
                or result.source_image_sha256 != digest
                or hashlib.sha256(result.image_bytes).hexdigest() != result.sha256
                or result.width != 1080 or result.height != 1350):
                _fail("COMPOSED_ARTIFACT_BINDING_INVALID")
            return transition_job(
                self.store, job_id, expected_status="IMAGE_APPROVED",
                next_status="COMPLETED",
                updates={"final_output": {
                    "mock": True, "width": result.width,
                    "height": result.height, "sha256": result.sha256,
                    "source_image_sha256": digest,
                    "copy_hash": stage["copy_hash"],
                    "copy_revision": stage["copy_revision"],
                    "receipt": result.receipt,
                    "scope": "OFFLINE_FIXTURE_NOT_LIVE",
                }},
                artifact_kind="final", artifact_bytes=result.image_bytes,
                additional_artifacts={"caption": result.caption_bytes},
            )
