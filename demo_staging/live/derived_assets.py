"""Job-scoped original and derived content for protected-product rendering.

Original uploads are resolved through JobStore and checked against their saved
byte SHA. They are never replaced by LocalAssetStore's color-normalized PNGs.
The caller supplies an authenticated ownership/delegation predicate.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import re
import stat
from uuid import uuid4
from typing import Callable
import warnings

from PIL import Image, ImageCms, UnidentifiedImageError
from fontTools.ttLib import TTFont, TTLibError
from pydantic import ValidationError

from src.image_generation.contracts import content_hash
from src.image_generation.protected_recipe import (
    ContentRef, PortableRecipe, MediaType, canonical_bytes, checked_recipe, content_ref,
)
from src.serving.job_store import JobStore
from .contracts import LiveGateError

ID = re.compile(r"^[0-9a-f]{32}$")
KINDS = frozenset({"source_photo", "product_mask", "raw_candidate", "font", "font_license",
                   "copy_snapshot", "layout", "scene_review_spec", "preview", "caption", "receipt"})
IMAGE_MEDIA = {"PNG":"image/png", "JPEG":"image/jpeg", "WEBP":"image/webp"}
MAX_BYTES = 32 * 1024 * 1024
MAX_PIXELS = 16_000_000


@dataclass(frozen=True)
class ImageMetadata:
    width: int
    height: int
    upright_width: int
    upright_height: int
    mode: str
    orientation: int
    icc_sha256: str | None

    @property
    def upright_size(self):
        return self.upright_width, self.upright_height


@dataclass(frozen=True)
class ResolvedAsset:
    data: bytes
    ref: ContentRef
    image: ImageMetadata | None
    upload_asset_id: str | None = None
    role: str | None = None


def inspect_image(data: bytes, media_type: str, *, max_bytes=MAX_BYTES,
                  max_pixels=MAX_PIXELS, mask=False) -> ImageMetadata:
    if not isinstance(data, bytes) or not 0 < len(data) <= max_bytes:
        raise LiveGateError("DERIVED_ASSET_BYTE_LIMIT")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as source:
                width, height = source.size
                if (IMAGE_MEDIA.get(source.format) != media_type or
                        getattr(source, "n_frames", 1) != 1):
                    raise LiveGateError("DERIVED_ASSET_IMAGE_FORMAT")
                if not 0 < width <= 16384 or not 0 < height <= 16384 or width * height > max_pixels:
                    raise LiveGateError("DERIVED_ASSET_PIXEL_LIMIT")
                source.load()
                orientation = source.getexif().get(274, 1)
                if type(orientation) is not int or orientation not in range(1, 9):
                    raise LiveGateError("DERIVED_ASSET_ORIENTATION")
                if mask and (source.mode != "L" or orientation != 1):
                    raise LiveGateError("DERIVED_MASK_FORMAT")
                profile = source.info.get("icc_profile")
                if profile is not None:
                    if not isinstance(profile, bytes) or not 0 < len(profile) <= 4 * 1024 * 1024:
                        raise LiveGateError("DERIVED_ASSET_ICC")
                    ImageCms.ImageCmsProfile(BytesIO(profile))
                upright = (height, width) if orientation in {5, 6, 7, 8} else (width, height)
                return ImageMetadata(width, height, *upright, source.mode, orientation,
                                     sha256(profile).hexdigest() if profile else None)
    except LiveGateError:
        raise
    except (OSError, ValueError, TypeError, UnidentifiedImageError, Image.DecompressionBombWarning,
            Image.DecompressionBombError, ImageCms.PyCMSError) as exc:
        raise LiveGateError("DERIVED_ASSET_IMAGE_INVALID") from exc


def _check_document(data, media_type):
    if media_type == "font/ttf":
        try:
            with TTFont(BytesIO(data), lazy=True) as font:
                if not font.getBestCmap():
                    raise ValueError
        except (OSError, ValueError, TTLibError) as exc:
            raise LiveGateError("DERIVED_ASSET_FONT_INVALID") from exc
    elif media_type in {"text/plain", "application/json"}:
        try:
            text = data.decode("utf-8")
            if media_type == "application/json":
                def unique(pairs):
                    result = {}
                    for key, value in pairs:
                        if key in result:
                            raise ValueError
                        result[key] = value
                    return result
                def reject_constant(_):
                    raise ValueError
                json.loads(text, object_pairs_hook=unique, parse_constant=reject_constant)
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise LiveGateError("DERIVED_ASSET_DOCUMENT_INVALID") from exc


class DerivedAssetRegistry:
    """Private per-Job immutable content; content SHA never grants access."""
    def __init__(self, root: Path, jobs: JobStore,
                 owns: Callable[[str, str], bool], *, max_bytes=MAX_BYTES, max_pixels=MAX_PIXELS):
        if not callable(owns) or type(max_bytes) is not int or not 0 < max_bytes <= 64 * 1024 * 1024:
            raise ValueError("Explicit ownership resolver and bounded asset limit required")
        if type(max_pixels) is not int or not 0 < max_pixels <= MAX_PIXELS:
            raise ValueError("Image pixel limit must be positive and bounded")
        path = Path(root).expanduser().absolute()
        if path.is_symlink() or ".." in path.parts:
            raise LiveGateError("DERIVED_ASSET_ROOT_INVALID")
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root = path.resolve()
        self.jobs = jobs
        self.owns = owns
        self.max_bytes = max_bytes
        self.max_pixels = max_pixels

    def _authorize(self, actor, job_id):
        if not isinstance(actor, str) or not actor or not isinstance(job_id, str) or not ID.fullmatch(job_id):
            raise LiveGateError("DERIVED_ASSET_NOT_FOUND")
        if not self.owns(actor, job_id):
            raise LiveGateError("DERIVED_ASSET_NOT_FOUND")

    def _read_regular(self, root: Path, path: Path, *, limit=None):
        """Walk beneath a trusted root with directory fds, refusing symlink hops."""
        try:
            relative = path.relative_to(root)
            if not relative.parts or any(part in {"..", "."} for part in relative.parts):
                raise OSError
            directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                for part in relative.parts[:-1]:
                    child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                    os.close(directory)
                    directory = child
                fd = os.open(relative.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
                try:
                    info = os.fstat(fd)
                    bound = self.max_bytes if limit is None else limit
                    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= bound:
                        raise OSError
                    chunks=[]
                    total=0
                    while True:
                        chunk=os.read(fd, min(1024 * 1024, bound+1-total))
                        if not chunk:
                            break
                        chunks.append(chunk)
                        total += len(chunk)
                        if total > bound:
                            raise OSError
                    return b"".join(chunks)
                finally:
                    os.close(fd)
            finally:
                os.close(directory)
        except (OSError, ValueError) as exc:
            raise LiveGateError("DERIVED_ASSET_INTEGRITY") from exc

    def resolve_upload(self, actor: str, job_id: str, upload_asset_id: str,
                       *, expected_sha256: str | None = None) -> ResolvedAsset:
        self._authorize(actor, job_id)
        if not isinstance(upload_asset_id, str) or not ID.fullmatch(upload_asset_id):
            raise LiveGateError("DERIVED_ASSET_NOT_FOUND")
        path, record = self.jobs.get_asset(job_id, upload_asset_id)
        raw = self._read_regular(self.jobs.root, path)
        actual = sha256(raw).hexdigest()
        if (actual != record.get("sha256") or len(raw) != record.get("size_bytes")
                or expected_sha256 is not None and actual != expected_sha256):
            raise LiveGateError("DERIVED_ORIGINAL_ASSET_CHANGED")
        metadata = inspect_image(raw, record["content_type"], max_bytes=self.max_bytes,
                                 max_pixels=self.max_pixels)
        if (metadata.width, metadata.height) != (record.get("width"), record.get("height")):
            raise LiveGateError("DERIVED_ORIGINAL_DIMENSIONS_CHANGED")
        return ResolvedAsset(raw, content_ref(raw, record["content_type"]), metadata,
                             upload_asset_id, record["role"])

    def register_upload(self, actor, job_id, upload_asset_id, *, expected_sha256=None):
        original = self.resolve_upload(actor, job_id, upload_asset_id, expected_sha256=expected_sha256)
        self.put_content(actor, job_id, original.data, original.ref.media_type, kind="source_photo")
        return original

    def _inspect(self, data, media_type, kind):
        if kind not in KINDS:
            raise LiveGateError("DERIVED_ASSET_KIND_INVALID")
        expected_media = {
            "product_mask": {"image/png"}, "raw_candidate": {"image/png"}, "preview": {"image/png"},
            "font": {"font/ttf"}, "font_license": {"text/plain"}, "caption": {"text/plain"},
            "copy_snapshot": {"application/json"}, "layout": {"application/json"},
            "scene_review_spec": {"application/json"}, "receipt": {"application/json"},
            "source_photo": set(IMAGE_MEDIA.values()),
        }
        if media_type not in expected_media[kind]:
            raise LiveGateError("DERIVED_ASSET_KIND_MEDIA_MISMATCH")
        if media_type in IMAGE_MEDIA.values():
            metadata = inspect_image(data, media_type, max_bytes=self.max_bytes,
                                     max_pixels=self.max_pixels, mask=kind == "product_mask")
            if kind == "product_mask" and media_type != "image/png":
                raise LiveGateError("DERIVED_MASK_FORMAT")
            return metadata
        if kind in {"source_photo", "product_mask", "raw_candidate", "preview"}:
            raise LiveGateError("DERIVED_ASSET_IMAGE_FORMAT")
        _check_document(data, media_type)
        return None

    def put_content(self, actor, job_id, data: bytes, media_type: MediaType, *, kind: str) -> ContentRef:
        self._authorize(actor, job_id)
        if not isinstance(data, bytes) or not 0 < len(data) <= self.max_bytes:
            raise LiveGateError("DERIVED_ASSET_BYTE_LIMIT")
        ref = content_ref(data, media_type)
        self._inspect(data, media_type, kind)
        directory = self.root / job_id
        if directory.is_symlink():
            raise LiveGateError("DERIVED_ASSET_INTEGRITY")
        directory.mkdir(mode=0o700, exist_ok=True)
        metadata = canonical_bytes(ref)
        self._publish(directory, ref.sha256 + ".blob", data)
        self._publish(directory, ref.sha256 + ".json", metadata)
        return ref

    def _publish(self, directory, name, data):
        # Publish relative to open no-follow directory fds, so an inserted
        # symlink cannot redirect a concurrent write out of the Job root.
        temporary = ".pending-" + uuid4().hex
        try:
            root_fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                folder_fd = os.open(directory.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                    dir_fd=root_fd)
            finally:
                os.close(root_fd)
        except OSError as exc:
            raise LiveGateError("DERIVED_ASSET_INTEGRITY") from exc
        try:
            try:
                fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=folder_fd)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                try:
                    os.link(temporary, name, src_dir_fd=folder_fd, dst_dir_fd=folder_fd,
                            follow_symlinks=False)
                except FileExistsError:
                    if self._read_regular(self.root, directory/name,
                                          limit=max(self.max_bytes, 128*1024)) != data:
                        raise LiveGateError("DERIVED_ASSET_INTEGRITY") from None
                os.fsync(folder_fd)
            finally:
                os.unlink(temporary, dir_fd=folder_fd)
        except OSError as exc:
            raise LiveGateError("DERIVED_ASSET_INTEGRITY") from exc
        finally:
            os.close(folder_fd)

    def read_content(self, actor, job_id, ref: ContentRef | dict) -> ResolvedAsset:
        self._authorize(actor, job_id)
        try:
            ref=ContentRef.model_validate(ref.model_dump() if isinstance(ref,ContentRef) else ref)
        except (ValidationError, TypeError) as exc:
            raise LiveGateError("DERIVED_ASSET_REFERENCE_INVALID") from exc
        directory=self.root/job_id
        metadata=self._read_regular(self.root,directory/(ref.sha256+".json"),limit=128*1024)
        if metadata != canonical_bytes(ref):
            raise LiveGateError("DERIVED_ASSET_INTEGRITY")
        raw=self._read_regular(self.root,directory/(ref.sha256+".blob"))
        if len(raw)!=ref.byte_length or sha256(raw).hexdigest()!=ref.sha256:
            raise LiveGateError("DERIVED_ASSET_INTEGRITY")
        image=inspect_image(raw,ref.media_type,max_bytes=self.max_bytes,max_pixels=self.max_pixels) \
            if ref.media_type in IMAGE_MEDIA.values() else None
        return ResolvedAsset(raw,ref,image)

    def resolve_recipe(self, actor, job_id, recipe: PortableRecipe | dict,
                       *, upload_bindings: dict[str,str] | None = None) -> dict[str, ResolvedAsset]:
        self._authorize(actor, job_id)
        body=PortableRecipe.model_validate(checked_recipe(recipe))
        bindings=upload_bindings or {}
        if set(bindings) != {"source_photo"}:
            raise LiveGateError("DERIVED_ORIGINAL_BINDING_REQUIRED")
        assets={}
        for role,ref in body.assets.items():
            if role in bindings:
                asset=self.resolve_upload(actor,job_id,bindings[role],expected_sha256=ref.sha256)
                if asset.ref != ref or asset.role != "product":
                    raise LiveGateError("DERIVED_ORIGINAL_BINDING_INVALID")
            else:
                asset=self.read_content(actor,job_id,ref)
            self._inspect(asset.data,ref.media_type,role)
            assets[role]=asset
        copy_payload=json.loads(assets["copy_snapshot"].data)
        if not isinstance(copy_payload,dict) or content_hash(copy_payload) != body.copy_sha256:
            raise LiveGateError("DERIVED_RECIPE_COPY_MISMATCH")
        if body.render_mode == "freeform_protected_product_hybrid":
            scene=json.loads(assets["scene_review_spec"].data)
            if (not isinstance(scene,dict) or
                    scene.get("candidate_sha256") != assets["raw_candidate"].ref.sha256):
                raise LiveGateError("DERIVED_RECIPE_SCENE_CONTEXT_MISMATCH")
        source=assets["source_photo"]
        mask=assets["product_mask"]
        if (source.image.upright_size != tuple(body.geometry.source_size)
                or source.image.icc_sha256 != body.source_icc_sha256
                or mask.image.upright_size != source.image.upright_size):
            raise LiveGateError("DERIVED_RECIPE_SOURCE_CONTEXT_MISMATCH")
        return assets


OriginalAssetRegistry = DerivedAssetRegistry
