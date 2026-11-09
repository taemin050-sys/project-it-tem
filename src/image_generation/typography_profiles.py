"""B display studies for a caller-reviewed 4:5 product photograph."""
from .composition import CompositionLayout, CompositionRect, CompositionTextRegion
from .typography import TypographyStyle

PROFILES = ("bold_type_hero", "editorial_botanical", "graphic_layout")
PROFILE_VERSION = "bp18-ad-typography-4x5-v1"


def study_layout(direction, copy_output, *, protected_regions):
    """Explicit study geometry, never inferred product detection or live policy."""
    if direction not in PROFILES:
        raise ValueError("Unknown advertising typography direction")
    headline = copy_output["ad_copy"]["headline"]
    spaces = [i+1 for i, char in enumerate(headline[:-1]) if char == " "]
    # Pick a word boundary near the middle, retaining the original space.
    breaks = [min(spaces, key=lambda point: abs(point-len(headline)/2))] if spaces else []

    def region(box, size, weight, *, color="#152941", background=None,
               align="left", tracking=0, scale=1, line_breaks=None, radius=0, lines=1):
        left, top, right, bottom = box
        return CompositionTextRegion(
            left=left/1080, top=top/1350, right=right/1080, bottom=bottom/1350,
            min_font_size=size[0], max_font_size=size[1], padding=0,
            max_lines=lines, vertical_align="center", align=align,
            color=color, background=background,
            typography=TypographyStyle(weight=weight, tracking_em=tracking,
                horizontal_scale=scale, line_height=1.04,
                break_offsets=line_breaks or [], background_radius=radius))

    if direction == "bold_type_hero":
        regions = {
            "headline": region((76, 80, 1004, 356), (128, 146), 900,
                               tracking=-0.025, line_breaks=breaks, lines=2),
            "subline": region((82, 374, 1004, 416), (40, 44), 500, tracking=-0.01),
            "cta": region((310, 1202, 770, 1278), (44, 48), 700,
                          color="#FFFDF5", background="#152941", align="center", radius=38),
        }
    elif direction == "editorial_botanical":
        regions = {
            "headline": region((80, 110, 1000, 240), (90, 112), 700,
                               color="#1D3A32", align="center", tracking=-0.015),
            "subline": region((96, 274, 984, 330), (44, 48), 500,
                              color="#1D3A32", align="center", tracking=0.01),
            "cta": region((340, 1202, 740, 1278), (40, 44), 650,
                          color="#FFFDF5", background="#28483E", align="center", radius=38),
        }
    else:
        regions = {
            "headline": region((76, 102, 1004, 244), (110, 126), 900,
                               tracking=-0.025, scale=0.92),
            "subline": region((342, 278, 1004, 354), (44, 48), 650,
                              background="#DEE8C8", align="center", tracking=-0.01),
            "cta": region((650, 1202, 1004, 1278), (40, 44), 750,
                          color="#FFFDF5", background="#152941", align="center", radius=8),
        }
    return CompositionLayout(canvas_size=(1080, 1350), cta_placement="image",
                             text_regions=regions,
                             protected_regions=[CompositionRect.model_validate(rect)
                                                for rect in protected_regions])
