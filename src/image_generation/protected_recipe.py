"""Portable protected-product render identities independent of storage locations.

Content identity grants no authority. Serving binds the resulting digests to its
Signed Actor, Job, Copy/F09, epoch and monotonic approval records separately.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .contracts import content_hash

Digest = Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{64}$")]
SafeInt = Annotated[int, Field(strict=True, ge=0, le=9_007_199_254_740_991)]
MediaType = Literal["image/png", "image/jpeg", "image/webp", "font/ttf",
                    "text/plain", "application/json"]
RenderMode = Literal["composed_protected_product", "freeform_protected_product_hybrid"]
ASSET_ROLES = {
    "composed_protected_product": frozenset({"source_photo", "product_mask", "font",
                                             "font_license", "copy_snapshot", "layout"}),
    "freeform_protected_product_hybrid": frozenset({"source_photo", "product_mask",
                                                    "raw_candidate", "copy_snapshot", "scene_review_spec"}),
}
CODE_ROLES = {
    "composed_protected_product": frozenset({"study_adapter", "base_adapter", "composition", "typography", "resize"}),
    "freeform_protected_product_hybrid": frozenset({"study_adapter", "resize", "color_management"}),
}


class ProtectedContract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ContentRef(ProtectedContract):
    """Content-addressed identity. Upload IDs and paths belong in a resolver."""
    asset_id: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    sha256: Digest
    byte_length: Annotated[SafeInt, Field(gt=0, le=64 * 1024 * 1024)]
    media_type: MediaType

    @model_validator(mode="after")
    def matching_identity(self):
        if self.asset_id != "sha256:" + self.sha256:
            raise ValueError("ASSET_ID_CONTENT_MISMATCH")
        return self


class Geometry(ProtectedContract):
    """One upright source crop, uniformly downsampled and integer-translated."""
    source_size: Annotated[list[SafeInt], Field(min_length=2, max_length=2)]
    source_crop: Annotated[list[SafeInt], Field(min_length=4, max_length=4)]
    registered_size: Annotated[list[SafeInt], Field(min_length=2, max_length=2)]
    output_offset: Annotated[list[SafeInt], Field(min_length=2, max_length=2)]
    output_size: Annotated[list[SafeInt], Field(min_length=2, max_length=2)]
    resampler: Literal["NONE", "LANCZOS_RGB_AND_ALPHA"]

    @model_validator(mode="after")
    def valid_registration(self):
        left, top, right, bottom = self.source_crop
        source_width, source_height = self.source_size
        width, height = self.registered_size
        x, y = self.output_offset
        output_width, output_height = self.output_size
        if (not 0 < source_width <= 16384 or not 0 < source_height <= 16384
                or source_width * source_height > 16_000_000
                or not 0 <= left < right <= source_width
                or not 0 <= top < bottom <= source_height
                or width <= 0 or height <= 0
                or width * (bottom-top) != height * (right-left)
                or width > right-left or height > bottom-top
                or x+width > output_width or y+height > output_height
                or (output_width, output_height) not in {(1080,1350), (1080,1440), (1080,1920)}):
            raise ValueError("PROTECTED_GEOMETRY_INVALID")
        if (self.resampler == "NONE") != (width == right-left and height == bottom-top):
            raise ValueError("PROTECTED_RESAMPLER_INVALID")
        return self


class PortableRecipe(ProtectedContract):
    schema_id: Literal["bp18-portable-render-recipe-v1"] = Field(alias="schema")
    render_mode: RenderMode
    assets: Annotated[dict[str, ContentRef], Field(max_length=8)]
    code_sha256: Annotated[dict[str, Digest], Field(max_length=8)]
    source_tree_sha: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    source_icc_sha256: Digest | None
    roi_spec_sha256: Digest
    copy_sha256: Digest
    geometry: Geometry
    design_id: Annotated[str, Field(pattern=r"^[a-z0-9-]{1,80}$")]
    layer_spec_sha256: Digest
    alpha_rule: Literal["combined_single_pass_photo_v1"]

    @model_validator(mode="after")
    def expected_roles(self):
        if set(self.assets) != ASSET_ROLES[self.render_mode] or set(self.code_sha256) != CODE_ROLES[self.render_mode]:
            raise ValueError("PROTECTED_RECIPE_ROLES_INVALID")
        if self.assets["source_photo"].media_type not in {"image/png", "image/jpeg", "image/webp"}:
            raise ValueError("PROTECTED_SOURCE_MEDIA_INVALID")
        if self.assets["product_mask"].media_type != "image/png":
            raise ValueError("PROTECTED_MASK_MEDIA_INVALID")
        expected_media = {"copy_snapshot":"application/json", "layout":"application/json",
                          "scene_review_spec":"application/json", "font":"font/ttf", "font_license":"text/plain",
                          "raw_candidate":"image/png"}
        if any(ref.media_type != expected_media[role] for role, ref in self.assets.items()
               if role in expected_media):
            raise ValueError("PROTECTED_ROLE_MEDIA_INVALID")
        return self


class ResultBinding(ProtectedContract):
    schema_id: Literal["bp18-derived-result-binding-v1"] = Field(default="bp18-derived-result-binding-v1", alias="schema")
    recipe_content_sha: Digest
    preview: ContentRef

    @model_validator(mode="after")
    def preview_is_png(self):
        if self.preview.media_type != "image/png":
            raise ValueError("PROTECTED_PREVIEW_MEDIA_INVALID")
        return self


def _semantic(value: Any, depth: int = 0) -> None:
    """Keep Python and JavaScript canonical bytes equal for supported JSON."""
    if depth > 32:
        raise ValueError("PROTECTED_JSON_DEPTH")
    if value is None or type(value) is bool:
        return
    if type(value) is int:
        if abs(value) > 9_007_199_254_740_991:
            raise ValueError("PROTECTED_JSON_UNSAFE_INTEGER")
        return
    if type(value) is str:
        value.encode("utf-8")
        return
    if type(value) is list:
        for item in value:
            _semantic(item, depth+1)
        return
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise ValueError("PROTECTED_JSON_KEY")
        for item in value.values():
            _semantic(item, depth+1)
        return
    raise ValueError("PROTECTED_JSON_TYPE")


def canonical_bytes(value: BaseModel | dict | list) -> bytes:
    payload = value.model_dump(mode="json", by_alias=True) if isinstance(value, BaseModel) else value
    _semantic(payload)
    return json.dumps(payload, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def canonical_sha(value: BaseModel | dict | list) -> str:
    # The validated payload uses the repository's existing hash representation.
    canonical_bytes(value)
    payload = value.model_dump(mode="json", by_alias=True) if isinstance(value, BaseModel) else value
    return content_hash(payload)


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("PROTECTED_JSON_DUPLICATE_KEY")
        result[key] = value
    return result


def load_recipe_json(data: bytes | str) -> dict:
    if not isinstance(data, (bytes, str)) or len(data) > 128 * 1024:
        raise ValueError("PROTECTED_JSON_LIMIT")
    def invalid_constant(_):
        raise ValueError("PROTECTED_JSON_NONFINITE")
    try:
        payload = json.loads(data, object_pairs_hook=_unique_pairs, parse_constant=invalid_constant)
        if type(payload) is not dict:
            raise ValueError("PROTECTED_JSON_OBJECT_REQUIRED")
        return checked_recipe(payload)
    except (RecursionError, UnicodeError) as exc:
        raise ValueError("PROTECTED_JSON_INVALID") from exc


def checked_recipe(payload: dict | PortableRecipe) -> dict:
    recipe = payload if isinstance(payload, PortableRecipe) else PortableRecipe.model_validate(payload)
    # Revalidate model instances too: Pydantic models can be copied with unvalidated updates.
    data = recipe.model_dump(mode="json", by_alias=True)
    return PortableRecipe.model_validate(data).model_dump(mode="json", by_alias=True)


def recipe_content_sha(payload: dict | PortableRecipe) -> str:
    return canonical_sha(checked_recipe(payload))


def content_ref(data: bytes, media_type: MediaType) -> ContentRef:
    if not isinstance(data, bytes) or not data:
        raise ValueError("PROTECTED_CONTENT_BYTES_REQUIRED")
    digest = sha256(data).hexdigest()
    return ContentRef(asset_id="sha256:"+digest, sha256=digest,
                      byte_length=len(data), media_type=media_type)


def result_binding(recipe_sha: str, output: bytes) -> dict:
    return ResultBinding(recipe_content_sha=recipe_sha, preview=content_ref(output,"image/png")).model_dump(mode="json", by_alias=True)


def result_binding_sha(recipe_sha: str, output: bytes) -> str:
    return canonical_sha(result_binding(recipe_sha, output))
