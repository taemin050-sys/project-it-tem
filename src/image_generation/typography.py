"""Versioned local display typography for approved copy.

Font bytes and all effective settings remain bound by CompositionInput.
Legacy layouts omit this contract and keep the original renderer.
"""
from dataclasses import dataclass
from io import BytesIO
import math
from typing import Annotated, Literal

from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont
from pydantic import ConfigDict, Field, model_validator
import unicodedata2 as unicode

from .contracts import Contract
from .errors import GatewayError


class TypographyStyle(Contract):
    model_config = ConfigDict(extra="forbid", strict=True)
    version: Literal["display-typography-v1"] = "display-typography-v1"
    weight: Annotated[int, Field(strict=True, ge=100, le=900)] | None = None
    tracking_em: float = Field(default=0, ge=-0.08, le=0.2, allow_inf_nan=False)
    line_height: float = Field(default=1.1, ge=1, le=2, allow_inf_nan=False)
    horizontal_scale: float = Field(default=1, ge=0.75, le=1.25, allow_inf_nan=False)
    break_offsets: list[Annotated[int, Field(strict=True, ge=1)]] = Field(default_factory=list, max_length=19)
    background_radius: int = Field(default=0, strict=True, ge=0, le=128)

    @model_validator(mode="after")
    def ordered_breaks(self):
        if self.break_offsets != sorted(set(self.break_offsets)):
            raise ValueError("Display break offsets must be unique and ordered")
        return self


@dataclass(frozen=True)
class PreparedTypography:
    masks: tuple[Image.Image, ...]
    lines: tuple[str, ...]
    font_size: int
    pitch: int
    weight: float | None
    axes: dict[str, float]


def _reject(code):
    return GatewayError(code, "승인 문구의 글꼴·자간·줄바꿈·표시 영역을 확인해 주세요.")


def _clusters(text):
    """Preserve marks/modifiers for tracked, NFC Korean and Latin display copy."""
    groups = []
    for char in text:
        modifier = unicode.category(char).startswith("M") or 0x1F3FB <= ord(char) <= 0x1F3FF
        regional_pair = (groups and len(groups[-1]) == 1 and
                         0x1F1E6 <= ord(groups[-1]) <= 0x1F1FF and
                         0x1F1E6 <= ord(char) <= 0x1F1FF)
        if groups and (modifier or regional_pair):
            groups[-1] += char
        else:
            groups.append(char)
    return groups


def _requires_contextual_shaping(text):
    # Tracked/manual-break display copy is limited to scripts whose letter
    # boundaries do not require a shaping engine. Whole-line, untracked copy
    # still uses Pillow's normal font shaping and preserves legacy support.
    supported = ("LATIN ", "HANGUL SYLLABLE ", "CJK UNIFIED IDEOGRAPH-",
                 "CJK COMPATIBILITY IDEOGRAPH-", "HIRAGANA ", "KATAKANA ")
    return any(unicode.category(char).startswith("L") and
               not unicode.name(char, "").startswith(supported) for char in text)


def _segments(text, style):
    boundaries = {0}
    offset = 0
    for cluster in _clusters(text):
        offset += len(cluster)
        boundaries.add(offset)
    if any(point >= len(text) or point not in boundaries for point in style.break_offsets):
        raise _reject("COMPOSITION_TYPOGRAPHY_BREAK_INVALID")
    if style.break_offsets and _requires_contextual_shaping(text):
        raise _reject("COMPOSITION_TYPOGRAPHY_SCRIPT_UNSUPPORTED")
    points = [0, *style.break_offsets, len(text)]
    # The exact source slices, including spaces, remain in the receipt.
    return [text[start:end] for start, end in zip(points, points[1:])]


def _font_settings(data, index, style):
    with TTFont(BytesIO(data), fontNumber=index) as face:
        axes = [(axis.axisTag, axis.minValue, axis.defaultValue, axis.maxValue)
                for axis in face["fvar"].axes] if "fvar" in face else []
        static_weight = float(face["OS/2"].usWeightClass) if "OS/2" in face else None
    settings = {name: default for name, _, default, _ in axes}
    if style.weight is not None:
        if "wght" in settings:
            bounds = next(axis for axis in axes if axis[0] == "wght")
            if not bounds[1] <= style.weight <= bounds[3]:
                raise _reject("COMPOSITION_FONT_WEIGHT_UNAVAILABLE")
            settings["wght"] = style.weight
        elif static_weight != style.weight:
            raise _reject("COMPOSITION_FONT_WEIGHT_UNAVAILABLE")
    return settings, static_weight


def _make_font(data, index, size, settings):
    font = ImageFont.truetype(BytesIO(data), size, index=index)
    if settings:
        font.set_variation_by_axes(list(settings.values()))
    return font


def _line_geometry(text, font, tracking):
    if not text:
        return [], (0, 0, 1, 1)
    tracked = bool(tracking)
    clusters = _clusters(text) if tracked else [text]
    runs = []
    prefix = ""
    for index, cluster in enumerate(clusters):
        x = font.getlength(prefix) + index * tracking
        box = font.getbbox(cluster, anchor="ls")
        runs.append((cluster, x, box))
        prefix += cluster
    left = math.floor(min(0, *(x + box[0] for _, x, box in runs)))
    top = min(box[1] for _, _, box in runs)
    right = math.ceil(max(font.getlength(text) + max(0, len(clusters)-1) * tracking,
                          *(x + box[2] for _, x, box in runs)))
    bottom = max(box[3] for _, _, box in runs)
    return runs, (left, top, right, bottom)


def _line_width(text, font, tracking, scale):
    _, (left, _, right, _) = _line_geometry(text, font, tracking)
    return max(1, round(max(1, right-left)*scale))


def _line_mask(text, font, tracking, scale):
    runs, (left, top, right, bottom) = _line_geometry(text, font, tracking)
    mask = Image.new("L", (max(1, right-left), max(1, bottom-top)))
    draw = ImageDraw.Draw(mask)
    for cluster, x, _ in runs:
        draw.text((x-left, -top), cluster, font=font, fill=255, anchor="ls")
    if scale != 1:
        mask = mask.resize((max(1, round(mask.width*scale)), mask.height), Image.Resampling.LANCZOS)
    return mask


def _wrapped_lines(segments, font, tracking, scale, width, explicit):
    lines = []
    for segment in segments:
        for paragraph in segment.split("\n"):
            if explicit:
                lines.append(paragraph)
                continue
            line = ""
            for cluster in _clusters(paragraph):
                candidate = line + cluster
                if _line_width(candidate, font, tracking, scale) > width:
                    if not line:
                        return None
                    boundary = max((index+1 for index, char in enumerate(line)
                                    if char.isspace()), default=0)
                    if boundary:
                        lines.append(line[:boundary])
                        line = line[boundary:] + cluster
                    else:
                        lines.append(line)
                        line = cluster
                else:
                    line = candidate
            lines.append(line)
    return lines


def prepare_typography(text, region, data, index, canvas_size):
    style = region.typography
    if ((style.tracking_em or style.break_offsets) and unicode.normalize("NFC", text) != text or
        style.tracking_em and _requires_contextual_shaping(text)):
        raise _reject("COMPOSITION_TRACKING_SCRIPT_UNSUPPORTED")
    segments = _segments(text, style)
    settings, static_weight = _font_settings(data, index, style)
    left, top, right, bottom = region.pixels(canvas_size)
    width, height = right-left-2*region.padding, bottom-top-2*region.padding
    low, high, best = region.min_font_size, region.max_font_size, None
    while low <= high:
        size = (low+high)//2
        font = _make_font(data, index, size, settings)
        lines = _wrapped_lines(segments, font, style.tracking_em*size,
                               style.horizontal_scale, width, bool(style.break_offsets))
        fitting_lines = (lines is not None and
                         all(_line_width(line, font, style.tracking_em*size,
                                         style.horizontal_scale) <= width for line in lines))
        masks = tuple(_line_mask(line, font, style.tracking_em*size, style.horizontal_scale)
                      for line in lines) if fitting_lines else ()
        pitch = max(math.ceil(size*style.line_height), max((m.height for m in masks), default=0))
        used = (len(masks)-1)*pitch + (masks[-1].height if masks else 0)
        if (masks and max(m.width for m in masks) <= width and used <= height and
            (region.max_lines is None or len(masks) <= region.max_lines)):
            best = PreparedTypography(masks, tuple(lines), size, pitch,
                                      settings.get("wght", static_weight), settings)
            low = size+1
        else:
            high = size-1
    if best is None:
        raise _reject("COMPOSITION_TEXT_OVERFLOW")
    return best


def draw_typography(overlay, region, prepared, canvas_size):
    left, top, right, bottom = region.pixels(canvas_size)
    draw = ImageDraw.Draw(overlay)
    if region.background:
        draw.rounded_rectangle((left, top, right-1, bottom-1),
                               radius=region.typography.background_radius, fill=region.background)
    used = (len(prepared.masks)-1)*prepared.pitch + prepared.masks[-1].height
    offset = (bottom-top-2*region.padding-used)//2 if region.vertical_align == "center" else 0
    boxes = []
    for index, mask in enumerate(prepared.masks):
        x = left+region.padding
        if region.align == "center":
            x = left+(right-left-mask.width)//2
        elif region.align == "right":
            x = right-region.padding-mask.width
        y = top+region.padding+offset+index*prepared.pitch
        if not (left+region.padding <= x and x+mask.width <= right-region.padding and
                top+region.padding <= y and y+mask.height <= bottom-region.padding):
            raise _reject("COMPOSITION_TEXT_OVERFLOW")
        color = Image.new("RGBA", mask.size, region.color)
        color.putalpha(mask)
        overlay.alpha_composite(color, (x, y))
        ink = mask.getbbox()
        if ink:
            boxes.append([x+ink[0], y+ink[1], x+ink[2], y+ink[3]])
    return {"region": [left, top, right, bottom], "font_size": prepared.font_size,
            "line_count": len(prepared.lines), "ink_boxes": boxes,
            "typography": {"style": region.typography.model_dump(mode="json"),
                           "lines": list(prepared.lines), "resolved_weight": prepared.weight,
                           "axes": prepared.axes, "line_pitch": prepared.pitch}}
