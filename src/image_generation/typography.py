"""Bundled headline faces for the three A-composition variants."""

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Literal, Mapping


FontPreset = Literal["gothic", "round", "myeongjo"]


@dataclass(frozen=True)
class HeadlineFont:
    path: Path
    variation_weight: int | None = None


_FONT_DIR = Path(__file__).resolve().parent / "fonts"
FONT_PRESETS: Mapping[FontPreset, HeadlineFont] = MappingProxyType({
    "gothic": HeadlineFont(_FONT_DIR / "PretendardVariable.ttf", variation_weight=500),
    "round": HeadlineFont(_FONT_DIR / "NanumSquareRoundB.ttf"),
    "myeongjo": HeadlineFont(_FONT_DIR / "NanumMyeongjo-Bold.ttf"),
})
