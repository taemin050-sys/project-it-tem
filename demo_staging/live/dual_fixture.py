"""Synthetic Freeform response for the loopback QA route."""

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def _png(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


def _bottle(draw: ImageDraw.ImageDraw, bounds: tuple[int, int, int, int]) -> None:
    left, top, right, bottom = bounds
    width = min(right - left, (bottom - top) * 2 // 3)
    height = width * 3 // 2
    left, top = (left + right - width) // 2, (top + bottom - height) // 2

    def box(x1: float, y1: float, x2: float, y2: float):
        return (round(left + width * x1), round(top + height * y1),
                round(left + width * x2), round(top + height * y2))

    draw.rounded_rectangle(box(0, 0.20, 1, 1), width // 7, fill="#E4F2EC")
    draw.rectangle(box(0.34, 0.06, 0.68, 0.20), fill="#92B4BC")
    draw.rounded_rectangle(box(0.25, 0, 0.86, 0.06), width // 16, fill="#92B4BC")
    draw.rectangle(box(0, 0.50, 1, 0.78), fill="#AEDBD4")
    draw.line(box(0.23, 0.64, 0.77, 0.64), fill="#236477", width=max(1, width // 36))


def render_composed_fixture(native: tuple[int, int], protected: dict[str, float]) -> bytes:
    """Place the synthetic product inside the server's protected target."""
    width, height = native
    image = Image.new("RGB", native, "#D2E5E4")
    left, top, right, bottom = (
        round(protected[key] * axis)
        for key, axis in zip(("left", "top", "right", "bottom"), (width, height, width, height))
    )
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((left, top, right, bottom), (right - left) // 2, fill="#BED8D6")
    inset = (right - left) // 8
    _bottle(draw, (left + inset, top + inset, right - inset, bottom - inset))
    return _png(image)


def render_freeform_fixture(
    native: tuple[int, int], ad_copy: dict[str, str | None], font_path: Path,
) -> bytes:
    """Render approved text inside the fake response, before any export step."""
    width, height = native
    image = Image.new("RGB", native, "#123447")
    draw = ImageDraw.Draw(image)

    def box(left: float, top: float, right: float, bottom: float):
        return (round(width * left), round(height * top),
                round(width * right), round(height * bottom))

    def text(value: str | None, y: float, scale: float, fill: str):
        if not value:
            return
        size = max(1, round(width * scale))
        font = ImageFont.truetype(str(font_path), size)
        while draw.textlength(value, font=font) > width * 0.84 and size > 1:
            size -= 1
            font = ImageFont.truetype(str(font_path), size)
        draw.text((width // 2, round(height * y)), value, font=font,
                  fill=fill, anchor="mt")

    draw.ellipse(box(0.17, 0.27, 0.83, 0.77), fill="#236477")
    draw.ellipse(box(0.27, 0.70, 0.73, 0.76), fill="#0E384A")
    _bottle(draw, box(0.39, 0.38, 0.61, 0.73))

    text("QA FIXTURE", 0.04, 0.022, "#AEDBD4")
    text(ad_copy["headline"], 0.10, 0.095, "#FFFFFF")
    text(ad_copy.get("subline"), 0.20, 0.042, "#E4F2EC")
    text(ad_copy.get("cta"), 0.85, 0.046, "#AEDBD4")

    return _png(image)
