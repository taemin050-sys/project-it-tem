"""Deterministic original-product rendering. No Provider or serving imports.

Recipes identify bytes, not locations. A caller must establish source rights,
Job ACL, Copy/F09 approval and recipe admission before invoking this renderer.
Visual appearance and literal label truth still require human review.
"""
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import json
import math
from pathlib import Path
import warnings

from PIL import Image, ImageChops, ImageCms, ImageOps, __version__ as pillow_version

from .ad_resize import resize_ad_png
from .composition import CompositionInput, CompositionLayout, compose_ad_png, validate_copy_output
from .contracts import content_hash
from .protected_recipe import checked_recipe, recipe_content_sha, result_binding_sha


@dataclass(frozen=True)
class ProtectedRender:
    image_bytes: bytes
    caption_bytes: bytes
    receipt: dict


def _reject(code):
    raise ValueError(code)


def _decode(raw, *, upright=False):
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(BytesIO(raw)) as image:
            if image.width * image.height > 16_000_000 or getattr(image, "n_frames", 1) != 1:
                _reject("PROTECTED_IMAGE_LIMIT")
            if image.format not in ("PNG", "JPEG", "WEBP"):
                _reject("PROTECTED_IMAGE_FORMAT")
            image.load()
            if image.getexif().get(274, 1) != 1 and not upright:
                _reject("PROTECTED_ORIENTATION_REQUIRES_REGISTERED_SOURCE")
            return ImageOps.exif_transpose(image) if upright else image.copy()


def _png(image, profile):
    output = BytesIO()
    image.save(output, "PNG", compress_level=6, **({"icc_profile": profile} if profile else {}))
    return output.getvalue()


def _rect(box, size):
    if (not isinstance(box, list) or len(box) != 4 or any(type(n) is not int for n in box)
            or not 0 <= box[0] < box[2] <= size[0] or not 0 <= box[1] < box[3] <= size[1]):
        _reject("PROTECTED_REGION_BOUNDS")
    return tuple(box)


def professional_layout(copy, size, *, protected_regions=(), direction="editorial"):
    """Use the accepted variable-font typography primitives at every ratio."""
    from .composition import CompositionTextRegion, CompositionRect
    from .typography import TypographyStyle

    width, height = size
    if size not in ((1080, 1350), (1080, 1440), (1080, 1920)):
        _reject("PROTECTED_OUTPUT_SIZE")
    if direction not in ("editorial", "bold"):
        _reject("PROTECTED_TYPOGRAPHY_PROFILE")
    def region(box, low, high, weight, *, background=None, color="#183448"):
        left, top, right, bottom = box
        return CompositionTextRegion(
            left=left/width, top=top/height, right=right/width, bottom=bottom/height,
            min_font_size=low, max_font_size=high, max_lines=2, padding=10 if background else 0,
            align="center", vertical_align="center", color=color, background=background,
            typography=TypographyStyle(weight=weight, tracking_em=-0.02, line_height=1.08,
                background_radius=42 if background else 0))
    regions = {
        "headline": region((76, round(height*.075), 1004, round(height*.18)), 64, 112, 850 if direction == "bold" else 770),
        "subline": region((92, round(height*.195), 988, round(height*.245)), 32, 48, 510),
        "cta": region((300, round(height*.885), 780, round(height*.945)), 32, 44, 730,
                      background="#163D4F", color="#FFFFFF"),
    }
    return CompositionLayout(canvas_size=size, cta_placement="image", text_regions=regions,
        protected_regions=[CompositionRect.model_validate(value) for value in protected_regions])


def _repair_background(canvas, boxes, exclusions):
    """Local bounded repair from the existing side pixels, with visible review.

    This is not model inpainting or an automatic ghost detector. Human-approved
    source-space envelopes must cover the unwanted model object and reflections.
    The renderer rejects any repair intersecting the model's advertising text.
    """
    canvas = canvas.copy()
    for box in boxes:
        left, top, right, bottom = _rect(box, canvas.size)
        if left < 3 or right > canvas.width-3:
            _reject("HYBRID_REPAIR_CONTEXT_REQUIRED")
        for other in exclusions:
            if max(left, other[0]) < min(right, other[2]) and max(top, other[1]) < min(bottom, other[3]):
                _reject("HYBRID_REPAIR_COPY_OVERLAP")
        # At each scanline interpolate between the intact, existing left/right
        # scene. Feathering never changes the protected original product layer.
        strip = Image.new("RGB", (2, bottom-top))
        for y in range(bottom-top):
            strip.putpixel((0, y), canvas.getpixel((left-2, top+y)))
            strip.putpixel((1, y), canvas.getpixel((right+1, top+y)))
        patch = strip.resize((right-left, bottom-top), Image.Resampling.BILINEAR)
        canvas.paste(patch, (left, top))
    return canvas


def render_protected_product(recipe, contents, *, layer_spec, roi_spec,
                             job_id, copy_revision, font_path=None, background_bytes=None):
    recipe = checked_recipe(recipe)
    recipe_sha = recipe_content_sha(recipe)
    if content_hash(layer_spec) != recipe["layer_spec_sha256"] or content_hash(roi_spec) != recipe["roi_spec_sha256"]:
        _reject("PROTECTED_RENDER_SPEC_CHANGED")
    if set(contents) != set(recipe["assets"]):
        _reject("PROTECTED_RENDER_ASSETS_CHANGED")
    for role, ref in recipe["assets"].items():
        raw = contents[role]
        if sha256(raw).hexdigest() != ref["sha256"] or len(raw) != ref["byte_length"]:
            _reject("PROTECTED_RENDER_CONTENT_CHANGED")
    copy = json.loads(contents["copy_snapshot"])
    _, caption, tags = validate_copy_output(copy, recipe["copy_sha256"])
    with Image.open(BytesIO(contents["source_photo"])) as source_metadata:
        source_orientation = source_metadata.getexif().get(274, 1)
    if source_orientation != layer_spec.get("source_orientation", 1):
        _reject("PROTECTED_SOURCE_ORIENTATION_CHANGED")
    source = _decode(contents["source_photo"], upright=True)
    mask = _decode(contents["product_mask"])
    geometry = recipe["geometry"]
    if list(source.size) != geometry["source_size"] or mask.size != source.size or mask.mode != "L":
        _reject("PROTECTED_SOURCE_MASK_DIMENSIONS")
    profile = source.info.get("icc_profile")
    if (sha256(profile).hexdigest() if profile else None) != recipe["source_icc_sha256"]:
        _reject("PROTECTED_SOURCE_ICC_CHANGED")
    crop, size, offset = geometry["source_crop"], tuple(geometry["registered_size"]), tuple(geometry["output_offset"])
    canvas_size = tuple(geometry["output_size"])
    if source.mode == "RGBA" and source.crop(crop).getchannel("A").getextrema() != (255, 255):
        _reject("PROTECTED_SOURCE_ALPHA")
    original = source.crop(crop).convert("RGB")
    alpha = mask.crop(crop)
    if original.size != size:
        original = original.resize(size, Image.Resampling.LANCZOS)
        alpha = alpha.resize(size, Image.Resampling.LANCZOS)
    if alpha.getbbox() is None:
        _reject("PROTECTED_EMPTY_PRODUCT")
    raw_background = contents.get("raw_candidate", background_bytes)
    if raw_background is None or sha256(raw_background).hexdigest() != layer_spec["raw_candidate_sha"]:
        _reject("PROTECTED_BACKGROUND_CHANGED")
    resized = resize_ad_png(raw_background, final_size=canvas_size)
    canvas = _decode(resized.image_bytes).convert("RGB")
    background_profile = _decode(resized.image_bytes).info.get("icc_profile")
    if profile:
        canvas = ImageCms.profileToProfile(canvas,
            ImageCms.ImageCmsProfile(BytesIO(background_profile)) if background_profile else ImageCms.createProfile("sRGB"),
            ImageCms.ImageCmsProfile(BytesIO(profile)), outputMode="RGB")
    elif background_profile:
        canvas = ImageCms.profileToProfile(canvas, ImageCms.ImageCmsProfile(BytesIO(background_profile)),
            ImageCms.createProfile("sRGB"), outputMode="RGB")

    exclusions = [_rect(rect, canvas_size) for rect in layer_spec.get("copy_exclusions", [])]
    repair_regions = layer_spec.get("model_regions", [])
    if recipe["render_mode"] == "freeform_protected_product_hybrid":
        spec = json.loads(contents["scene_review_spec"])
        if content_hash(spec) != layer_spec.get("scene_review_sha") or spec.get("candidate_sha256") != layer_spec["raw_candidate_sha"]:
            _reject("HYBRID_SCENE_REVIEW_CHANGED")
        if not exclusions or not repair_regions:
            _reject("HYBRID_SCENE_REVIEW_REQUIRED")
        if spec.get("reviewed") is not True:
            _reject("HYBRID_SCENE_REVIEW_REQUIRED")
    canvas = _repair_background(canvas, repair_regions, exclusions)
    alpha_canvas = Image.new("L", canvas_size)
    alpha_canvas.paste(alpha, offset)
    for rectangle in exclusions:
        if alpha_canvas.crop(rectangle).getbbox():
            _reject("HYBRID_COPY_PRODUCT_OVERLAP")
    before_product = canvas.copy()
    canvas.paste(original, offset, alpha)
    for rectangle in exclusions:
        if canvas.crop(rectangle).tobytes() != before_product.crop(rectangle).tobytes():
            _reject("HYBRID_COPY_CHANGED")
    placements = {}
    if recipe["render_mode"] == "composed_protected_product":
        if font_path is None or sha256(Path(font_path).read_bytes()).hexdigest() != recipe["assets"]["font"]["sha256"]:
            _reject("PROTECTED_FONT_CHANGED")
        value = json.loads(contents["layout"])
        value["canvas_size"] = tuple(value["canvas_size"])
        layout = CompositionLayout.model_validate(value)
        for region in layout.text_regions.values():
            if alpha_canvas.crop(region.pixels(canvas_size)).getbbox():
                _reject("PROTECTED_COPY_PRODUCT_OVERLAP")
        baseline = _png(canvas, profile)
        result = compose_ad_png(CompositionInput(job_id=job_id, image_bytes=baseline,
            image_sha256=sha256(baseline).hexdigest(), copy_revision=copy_revision,
            copy_hash=recipe["copy_sha256"], copy_output=copy, layout=layout), font_path=font_path)
        final_bytes = result.image_bytes
        placements = result.receipt["placements"]
    else:
        final_bytes = _png(canvas, profile)
    final = _decode(final_bytes).convert("RGB")
    actual = final.crop((offset[0], offset[1], offset[0]+size[0], offset[1]+size[1]))
    opaque = alpha.point([0]*255+[255])
    difference = Image.new("RGB", size)
    difference.paste(ImageChops.difference(actual, original), mask=opaque)
    if difference.getbbox():
        _reject("PROTECTED_PRODUCT_PIXELS_CHANGED")
    roi_results = {}
    for name, rect in roi_spec.items():
        left, top, right, bottom = _rect(rect, source.size)
        if not crop[0] <= left < right <= crop[2] or not crop[1] <= top < bottom <= crop[3]:
            _reject("PROTECTED_ROI_OUTSIDE_CROP")
        local = (math.floor((left-crop[0])*size[0]/(crop[2]-crop[0])),
                 math.floor((top-crop[1])*size[1]/(crop[3]-crop[1])),
                 math.ceil((right-crop[0])*size[0]/(crop[2]-crop[0])),
                 math.ceil((bottom-crop[1])*size[1]/(crop[3]-crop[1])))
        expected = original.crop(local).tobytes()
        if alpha.crop(local).getextrema() != (255, 255) or expected != actual.crop(local).tobytes():
            _reject("PROTECTED_ROI_CHANGED")
        roi_results[name] = {"registered_roi": list(local), "rgb_sha256": sha256(expected).hexdigest(),
                             "pixel_count": len(expected)//3}
    if not roi_results:
        _reject("PROTECTED_REVIEW_ROI_REQUIRED")
    text = caption + ("\n\n" if caption and tags else "") + " ".join(tags)
    receipt = {"schema": "bp18-local-protected-render-receipt-v1", "recipe_content_sha": recipe_sha,
               "result_binding_sha": result_binding_sha(recipe_sha, final_bytes),
               "render_mode": recipe["render_mode"], "raw_candidate_sha": layer_spec["raw_candidate_sha"],
               "source_photo_sha": recipe["assets"]["source_photo"]["sha256"],
               "mask_sha": recipe["assets"]["product_mask"]["sha256"],
               "source_icc_sha": recipe["source_icc_sha256"], "copy_sha": recipe["copy_sha256"],
               "geometry": geometry, "protected_rois": roi_results, "opaque_rgb_mismatches": 0,
               "opaque_pixel_count": opaque.histogram()[255], "placements": placements,
               "provider_calls": 0, "provider_billing_events": 0, "pillow_version": pillow_version,
               "checks": {"source_pixels_preserved": True, "no_copy_occlusion": True},
               "needs_manual_check": True, "literal_label_ground_truth": "PENDING",
               "scene_repair": "existing_side_pixel_interpolation" if repair_regions else "none",
               "visual_quality": "HUMAN_REVIEW_REQUIRED"}
    return ProtectedRender(final_bytes, text.encode("utf-8"), receipt)
