"""Approved-copy display typography and legacy snapshot regressions."""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO

from fontTools.ttLib import TTFont
from PIL import Image, ImageChops, ImageDraw
import pytest
from pydantic import ValidationError

from .helpers import FONT, body, copy_output, layout
from src.image_generation.ad_resize import resize_ad_png
from src.image_generation.composition import compose_ad_png
from src.image_generation.contracts import content_hash
from src.image_generation.errors import GatewayError
from src.image_generation.openai_images import OpenAIImagesAdapter
from src.image_generation.typography import TypographyStyle, _segments


@pytest.fixture(autouse=True)
def forbid_provider_calls(monkeypatch):
    monkeypatch.setattr(
        OpenAIImagesAdapter, "execute",
        lambda *args, **kwargs: pytest.fail("Local typography must not call a provider"),
    )


def styled_body(style=None, *, headline="하루의  샴푸 루틴", **region_changes):
    approved = copy_output()
    approved["ad_copy"]["headline"] = headline
    selected = layout()
    selected["text_regions"]["headline"].update(
        min_font_size=48, max_font_size=48, max_lines=3,
        typography=style if style is not None else {"weight": 400},
    )
    selected["text_regions"]["headline"].update(region_changes)
    return body(copy_output=approved, copy_hash=content_hash(approved), layout=selected)


def decode(raw):
    image = Image.open(BytesIO(raw))
    image.load()
    return image.convert("RGBA")


def test_omitted_and_explicit_null_style_keep_legacy_bytes_and_fingerprint():
    original = body()
    with_null = original.model_dump()
    for region in with_null["layout"]["text_regions"].values():
        region["typography"] = None
    restored = type(original).model_validate(with_null)
    assert restored.model_dump() == original.model_dump()
    assert all("typography" not in region for region in restored.layout.model_dump()["text_regions"].values())
    before = compose_ad_png(original, font_path=FONT)
    after = compose_ad_png(restored, font_path=FONT)
    assert after.image_bytes == before.image_bytes
    assert after.caption_bytes == before.caption_bytes
    assert after.receipt["renderer"] == "korean-composition-v1"
    assert after.receipt["input_sha256"] == before.receipt["input_sha256"]


def test_historical_layout_canonical_hashes_are_unchanged():
    from demo_staging.live.template_contract import (
        bp18_provisional_4x5_policy, digest, owner_a_policy,
    )
    from src.image_generation.size_selection import size_composition_policy

    policies = [
        (owner_a_policy(), "c9fe0d76a35e8171cbfca2b23ae1eafc2bd4d60e9ad7cb8164098b6f420d43e1"),
        (bp18_provisional_4x5_policy(), "8edffb37dc44cbfbcbcded8893cd6c18778581dc11309eabcb25bf921889dca9"),
        (size_composition_policy("4:5"), "5d156b8b673556b2d7b4d059f45f6b25b79c3f42af4dfc02dc4a8383141df623"),
    ]
    for policy, expected in policies:
        assert digest(policy["layout"]) == expected


def test_explicit_visual_breaks_keep_approved_source_and_caption():
    request = styled_body({"weight": 400, "break_offsets": [5]})
    original = deepcopy(request.copy_output)
    result = compose_ad_png(request, font_path=FONT)
    placed = result.receipt["placements"]["headline"]
    assert result.receipt["renderer"] == "korean-composition-v2"
    assert placed["typography"]["lines"] == ["하루의  ", "샴푸 루틴"]
    assert "".join(placed["typography"]["lines"]) == original["ad_copy"]["headline"]
    assert placed["text_sha256"] == sha256(original["ad_copy"]["headline"].encode()).hexdigest()
    assert placed["typography"]["resolved_weight"] == 400
    assert result.copy_hash == request.copy_hash == content_hash(original)
    assert request.copy_output == original
    assert result.caption_bytes.decode() == original["caption"] + "\n\n" + " ".join(original["hashtags"])
    assert result.receipt["provider_calls"] == 0


@pytest.mark.parametrize("change", [
    {"weight": 400}, {"tracking_em": -0.04}, {"tracking_em": 0.08},
    {"line_height": 1.6}, {"horizontal_scale": 0.8},
    {"horizontal_scale": 1.2}, {"break_offsets": [5]}, {"background_radius": 24},
])
def test_every_effective_typography_setting_is_in_the_input_fingerprint(change):
    baseline = compose_ad_png(styled_body({}), font_path=FONT)
    changed = compose_ad_png(styled_body(change), font_path=FONT)
    assert changed.receipt["input_sha256"] != baseline.receipt["input_sha256"]
    assert changed.copy_hash == baseline.copy_hash
    assert changed.caption_bytes == baseline.caption_bytes


def test_explicit_static_font_weight_mismatch_fails_without_fallback():
    with pytest.raises(GatewayError) as caught:
        compose_ad_png(styled_body({"weight": 900}), font_path=FONT)
    assert caught.value.code == "COMPOSITION_FONT_WEIGHT_UNAVAILABLE"


@pytest.mark.parametrize("offsets", [[0], [2, 1], [2, 2]])
def test_invalid_break_order_is_rejected(offsets):
    with pytest.raises(ValidationError):
        styled_body({"break_offsets": offsets})


@pytest.mark.parametrize("offset", [11, 40])
def test_break_at_or_after_source_end_is_rejected(offset):
    request = styled_body({"break_offsets": [offset]}, headline="하루의 샴푸 루틴")
    with pytest.raises(GatewayError) as caught:
        compose_ad_png(request, font_path=FONT)
    assert caught.value.code == "COMPOSITION_TYPOGRAPHY_BREAK_INVALID"


def test_break_cannot_split_combining_cluster_or_emoji_modifier():
    for source, offset in [("A\u0301B", 1), ("👍🏻다음", 1)]:
        with pytest.raises(GatewayError) as caught:
            _segments(source, TypographyStyle(break_offsets=[offset]))
        assert caught.value.code == "COMPOSITION_TYPOGRAPHY_BREAK_INVALID"


def test_manual_break_in_indic_conjunct_fails_closed():
    with pytest.raises(GatewayError) as caught:
        _segments("क्ष", TypographyStyle(break_offsets=[2]))
    assert caught.value.code == "COMPOSITION_TYPOGRAPHY_SCRIPT_UNSUPPORTED"


@pytest.mark.parametrize("source", ["e\u0301", "مرحبا", "क्ष"])
def test_tracking_unsupported_scripts_fails_before_rasterization(tmp_path, source):
    # Add cmap coverage to isolate script validation from the separate glyph gate.
    # No actual image is rendered using these synthetic mappings.
    with TTFont(FONT) as face:
        fallback_glyph = face.getBestCmap()[ord("A")]
        for table in face["cmap"].tables:
            if table.isUnicode():
                table.cmap.update({ord(char): fallback_glyph for char in source})
        patched = tmp_path / "covered-font.ttf"
        face.save(patched)
    request = styled_body({"tracking_em": 0.02}, headline=source)
    with pytest.raises(GatewayError) as caught:
        compose_ad_png(request, font_path=patched)
    assert caught.value.code == "COMPOSITION_TRACKING_SCRIPT_UNSUPPORTED"


def test_large_display_size_requires_explicit_typography_contract():
    selected = layout()
    selected["text_regions"]["headline"].update(min_font_size=148, max_font_size=148)
    with pytest.raises(ValidationError):
        body(layout=selected)
    request = styled_body({"weight": 400}, headline="하루", min_font_size=148, max_font_size=148)
    result = compose_ad_png(request, font_path=FONT)
    assert result.receipt["placements"]["headline"]["font_size"] == 148


def test_horizontal_scale_is_applied_to_actual_ink():
    compressed = compose_ad_png(styled_body({"horizontal_scale": 0.75}), font_path=FONT)
    expanded = compose_ad_png(styled_body({"horizontal_scale": 1.25}), font_path=FONT)
    compact = compressed.receipt["placements"]["headline"]["ink_boxes"][0]
    wide = expanded.receipt["placements"]["headline"]["ink_boxes"][0]
    assert wide[2] - wide[0] > (compact[2] - compact[0]) * 1.5
    assert wide[3] - wide[1] == compact[3] - compact[1]


def test_rounded_background_keeps_corner_pixels_and_fills_center_edge():
    request = styled_body({"background_radius": 30})
    result = compose_ad_png(request, font_path=FONT)
    before = decode(resize_ad_png(request.image_bytes).image_bytes)
    after = decode(result.image_bytes)
    left, top, right, _ = result.receipt["placements"]["headline"]["region"]
    assert after.getpixel((left, top)) == before.getpixel((left, top))
    assert after.getpixel(((left + right) // 2, top))[:3] == (255, 255, 255)


def test_typography_keeps_product_and_all_pixels_outside_regions_unchanged():
    request = styled_body({"weight": 400, "tracking_em": -0.04,
                           "horizontal_scale": 0.9, "background_radius": 24})
    result = compose_ad_png(request, font_path=FONT)
    before = decode(resize_ad_png(request.image_bytes).image_bytes)
    after = decode(result.image_bytes)
    for protected in request.layout.protected_regions:
        rectangle = protected.pixels(request.layout.canvas_size)
        assert before.crop(rectangle).tobytes() == after.crop(rectangle).tobytes()
    outside = Image.new("L", after.size, 255)
    draw = ImageDraw.Draw(outside)
    for placed in result.receipt["placements"].values():
        left, top, right, bottom = placed["region"]
        draw.rectangle((left, top, right - 1, bottom - 1), fill=0)
        assert all(left <= x <= r <= right and top <= y <= b <= bottom
                   for x, y, r, b in placed["ink_boxes"])
    for channel in ImageChops.difference(before, after).split():
        assert ImageChops.multiply(channel, outside).getbbox() is None


def test_styled_text_cannot_overlap_a_declared_product_region():
    selected = layout()
    selected["text_regions"]["headline"] = dict(
        selected["text_regions"]["headline"], left=0.60, top=0.40,
        right=0.80, bottom=0.50, typography={"weight": 400},
    )
    with pytest.raises(ValidationError):
        body(layout=selected)


def test_unfittable_approved_text_is_rejected_without_truncation():
    request = styled_body({"weight": 400}, headline="아" * 600, max_lines=1)
    with pytest.raises(GatewayError) as caught:
        compose_ad_png(request, font_path=FONT)
    assert caught.value.code == "COMPOSITION_TEXT_OVERFLOW"
    assert request.copy_output["ad_copy"]["headline"] == "아" * 600


def test_long_explicit_line_is_rejected_before_oversized_mask_allocation(monkeypatch):
    from src.image_generation import typography

    request = styled_body(
        {"weight": 400, "break_offsets": [1]}, headline="아" * 600,
        min_font_size=320, max_font_size=320,
    )
    original_new = typography.Image.new
    allocations = []

    def bounded_new(mode, size, *args, **kwargs):
        allocations.append((mode, size))
        assert size[0] <= 2000, "An unfittable line allocated an oversized raster mask"
        return original_new(mode, size, *args, **kwargs)

    monkeypatch.setattr(typography.Image, "new", bounded_new)
    with pytest.raises(GatewayError) as caught:
        compose_ad_png(request, font_path=FONT)
    assert caught.value.code == "COMPOSITION_TEXT_OVERFLOW"
    assert request.copy_output["ad_copy"]["headline"] == "아" * 600
    assert all(size[0] <= 2000 for _, size in allocations)


def test_explicit_empty_line_preserves_text_without_painting_extra_ink():
    original = "하루의\n\n샴푸 루틴"
    request = styled_body({"weight": 400}, headline=original)
    result = compose_ad_png(request, font_path=FONT)
    placed = result.receipt["placements"]["headline"]
    assert placed["typography"]["lines"] == ["하루의", "", "샴푸 루틴"]
    assert "\n".join(placed["typography"]["lines"]) == original
    assert placed["line_count"] == 3
    assert len(placed["ink_boxes"]) == 2
    assert placed["text_sha256"] == sha256(original.encode()).hexdigest()
    assert result.copy_hash == request.copy_hash


def test_missing_glyph_stays_fail_closed_with_typography():
    request = styled_body({"weight": 400}, headline="글리프 없음 🧴")
    with pytest.raises(GatewayError) as caught:
        compose_ad_png(request, font_path=FONT)
    assert caught.value.code == "COMPOSITION_GLYPH_MISSING"


def test_styled_rendering_is_repeatable_within_the_same_environment():
    request = styled_body({"weight": 400, "tracking_em": 0.03,
                           "horizontal_scale": 0.95, "break_offsets": [5]})
    first = compose_ad_png(request, font_path=FONT)
    second = compose_ad_png(request, font_path=FONT)
    assert first.image_bytes == second.image_bytes
    assert first.caption_bytes == second.caption_bytes
    assert first.receipt["input_sha256"] == second.receipt["input_sha256"]
    assert first.receipt["placements"] == second.receipt["placements"]


@pytest.mark.parametrize("style", [
    {"tracking_em": float("nan")}, {"tracking_em": -0.09},
    {"horizontal_scale": 0.7}, {"line_height": 0.9},
    {"weight": True}, {"background_radius": 129},
])
def test_invalid_typographic_ranges_are_rejected(style):
    with pytest.raises(ValidationError):
        TypographyStyle(**style)
