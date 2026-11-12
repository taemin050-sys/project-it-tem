"""BP10 — prevent Python 3.10 Unicode 13 false negatives without widening C* rules.

No Provider requests, no GCP DB writes. The Owner compositor/approved hashes are
the only evaluated source of truth. All examples use independently computed hashes.
"""
from copy import deepcopy

import pytest
import unicodedata2

from src.image_generation.composition import _copy_fields, compose_ad_png, validate_copy_output
from src.image_generation.contracts import content_hash
from src.image_generation.errors import GatewayError
from .helpers import FONT, body, copy_output


def with_caption(caption: str, *, tags: list[str] | None = None):
    copy = deepcopy(copy_output())
    copy["caption"] = caption
    if tags is not None:
        copy["hashtags"] = tags
    return copy


def test_unicode_data_is_modern_and_has_real_bubbles_emoji():
    assert tuple(map(int, unicodedata2.unidata_version.split("."))) >= (16, 0, 0)
    assert unicodedata2.category("\U0001fae7") == "So"
    assert unicodedata2.category("\u0378") == "Cn"


@pytest.mark.parametrize("caption,tags", [
    ("🫧 매일 피부를 산뜻하게\n가벼운 루틴.", ["#스킨케어🫧", "#매일"]),
    ("한글 English 012345\n일상 루틴", ["#한국어", "#abc123"]),
    ("기존 이모지 ✨💧와 한글\n다음 줄", ["#✨", "#제품"]),
    ("캡션은 렌더링할 폰트 glyph의 대상이 아닙니다 🫧", ["#🫧"]),
])
def test_approved_captions_and_tags_accept_modern_assigned_unicode_without_mutation(caption, tags):
    item = with_caption(caption, tags=tags)
    sha = content_hash(item)
    ad, accepted, hashtags = validate_copy_output(item, sha)
    assert (ad, accepted, hashtags) == (item["ad_copy"], caption, tags)
    assert content_hash(item) == sha
    composed = compose_ad_png(body(copy_output=item, copy_hash=sha), font_path=FONT)
    assert composed.copy_hash == sha
    assert composed.caption == caption
    assert composed.hashtags == tuple(tags)
    assert composed.caption_bytes.decode("utf-8") == caption + "\n\n" + " ".join(tags)
    assert composed.receipt["provider_calls"] == 0


@pytest.mark.parametrize("dangerous", [
    "\u0378",   # genuinely unassigned, including on Unicode 16
    "\x00",     # NUL control
    "\x07",     # BEL control
    "\u200b",   # ZERO WIDTH SPACE, format character
    "\u200d",   # ZERO WIDTH JOINER (current strict policy)
    "\u202e",   # RIGHT-TO-LEFT OVERRIDE
    "\ud800",   # isolated surrogate
])
def test_unassigned_controls_invisible_formats_surrogates_still_rejected(dangerous):
    for destination in ("caption", "hashtags"):
        c = with_caption("정상 캡션" + dangerous,
                         tags=["#안전" + dangerous] if destination == "hashtags" else ["#안전"])
        if destination == "hashtags":
            c["caption"] = "정상 캡션"
        if dangerous == "\ud800":
            # The canonical hash itself is fail-closed on isolated surrogates.
            with pytest.raises(UnicodeError):
                content_hash(c)
            continue
        with pytest.raises(GatewayError) as e:
            validate_copy_output(c, content_hash(c))
        assert e.value.code == "COMPOSITION_COPY_INVALID"


def test_approved_snapshot_copy_hash_not_weakened_with_bubbles_emoji():
    c = with_caption("🫧 정본 캡션", tags=["#원본🫧"])
    h = content_hash(c)
    changed = deepcopy(c)
    changed["caption"] = "🫧 변경된 캡션"
    with pytest.raises(GatewayError) as e:
        validate_copy_output(changed, h)
    assert e.value.code == "COMPOSITION_COPY_HASH_MISMATCH"


def test_image_sha_still_rejected_even_when_caption_contains_latest_emoji():
    c = with_caption("🫧 정상 caption")
    p = body(copy_output=c, copy_hash=content_hash(c))
    p.image_sha256 = "0" * 64
    with pytest.raises(GatewayError) as e:
        _copy_fields(p)
    assert e.value.code == "COMPOSITION_IMAGE_HASH_MISMATCH"


def test_rendered_copy_missing_font_glyph_must_still_fail_closed():
    c = with_caption("🫧 정상 caption")
    c["ad_copy"]["headline"] = "🫧"  # this is rendered on image, unlike caption.
    with pytest.raises(GatewayError) as e:
        compose_ad_png(body(copy_output=c, copy_hash=content_hash(c)), font_path=FONT)
    assert e.value.code == "COMPOSITION_GLYPH_MISSING"


def test_existing_owner_copy_and_layout_contract_still_valid():
    original = copy_output()
    baseline = body()
    composed = compose_ad_png(baseline, font_path=FONT)
    assert composed.copy_hash == content_hash(original)
    assert composed.source_image_sha256 == baseline.image_sha256
    assert composed.caption == original["caption"]
