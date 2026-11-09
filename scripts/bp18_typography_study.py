"""Render B advertising studies through the normal composer, with no provider.

All inputs are explicit files. This command never reads credentials or Job DBs.
Existing output directories are refused, preserving prior study evidence.
"""
import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFont, features, __version__ as pillow_version

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.image_generation.ad_resize import resize_ad_png
from src.image_generation.composition import CompositionInput, compose_ad_png
from src.image_generation.contracts import content_hash
from src.image_generation.typography_profiles import PROFILES, PROFILE_VERSION, study_layout


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--copy", required=True, type=Path)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--original", required=True, type=Path)
    parser.add_argument("--font", required=True, type=Path)
    parser.add_argument("--license", required=True, type=Path)
    parser.add_argument("--references", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--product-rect", nargs=4, type=int, required=True,
                        metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"))
    args = parser.parse_args()
    approved = json.loads(args.copy.read_text())
    copy = approved["copy"]
    raw = args.image.read_bytes()
    image_sha = sha256(raw).hexdigest()
    if content_hash(copy) != approved["copy_sha"] or image_sha != approved["image_sha"]:
        raise ValueError("Approved copy/image SHA mismatch")
    baseline = resize_ad_png(raw).image_bytes
    base_image = Image.open(BytesIO(baseline)).convert("RGBA")
    left, top, right, bottom = args.product_rect
    if not 0 <= left < right <= 1080 or not 0 <= top < bottom <= 1350:
        raise ValueError("Invalid reviewed product rectangle")
    protected = [{"left": left/1080, "top": top/1350,
                  "right": right/1080, "bottom": bottom/1350}]
    references = json.loads(args.references.read_text())
    for ref in references["references"]:
        if sha256(Path(ref["destination"]).read_bytes()).hexdigest() != ref["sha256"]:
            raise ValueError("Reference SHA mismatch")
    # Validate all input files before creating a new, private study directory.
    font_sha = sha256(args.font.read_bytes()).hexdigest()
    license_bytes = args.license.read_bytes()
    original = Image.open(args.original)
    original.load()
    args.output.mkdir(mode=0o700)
    manifest = {"profile_version": PROFILE_VERSION, "status": "B_DESIGN_REVIEW_C_PENDING",
        "source_image_sha": image_sha, "copy_sha": approved["copy_sha"],
        "copy_approval_sha": approved["approval_sha"],
        "source_image_approval_sha": approved["image_approval_sha"],
        "font_sha": font_sha, "font_license_sha": sha256(license_bytes).hexdigest(),
        "references": references["references"], "provider_calls": 0,
        "baseline_sha": sha256(baseline).hexdigest(), "reviewed_product_rect": args.product_rect,
        "selection": "bold_type_hero", "variants": {}}
    source_root = Path(__file__).resolve().parents[1]
    manifest["renderer_sources"] = {name: sha256((source_root/name).read_bytes()).hexdigest()
        for name in ("src/image_generation/composition.py", "src/image_generation/typography.py",
                     "src/image_generation/typography_profiles.py", "scripts/bp18_typography_study.py")}
    manifest["environment"] = {"python": sys.version.split()[0], "pillow": pillow_version,
        "freetype": features.version("freetype2"), "raqm": features.check("raqm")}
    manifest["original_export_sha"] = sha256(args.original.read_bytes()).hexdigest()
    board = Image.new("RGB", (1440, 502), "#EEECE4")
    draw = ImageDraw.Draw(board)
    label_font = ImageFont.truetype(str(args.font), 17)
    board.paste(original.convert("RGB").resize((360, 450), Image.Resampling.LANCZOS), (0, 52))
    draw.text((12, 10), "current approved export", font=label_font, fill="#152941")
    for index, direction in enumerate(PROFILES, start=1):
        layout = study_layout(direction, copy, protected_regions=protected)
        body = CompositionInput(job_id="bp18-offline-typography-study", image_bytes=raw,
            image_sha256=image_sha, copy_revision=approved["generation"],
            copy_hash=approved["copy_sha"], copy_output=copy, layout=layout)
        result = compose_ad_png(body, font_path=args.font)
        repeated = compose_ad_png(body, font_path=args.font)
        if result.image_bytes != repeated.image_bytes or result.caption_bytes != repeated.caption_bytes:
            raise ValueError("Non-deterministic rendering")
        image = Image.open(BytesIO(result.image_bytes)).convert("RGBA")
        if image.crop(args.product_rect).tobytes() != base_image.crop(args.product_rect).tobytes():
            raise ValueError("Reviewed product pixels changed")
        (args.output/(direction+".png")).write_bytes(result.image_bytes)
        for width in (360, 390):
            thumb = image.convert("RGB").resize((width, round(width*1350/1080)), Image.Resampling.LANCZOS)
            thumb.save(args.output/(direction+f"_{width}.png"))
            if width == 360:
                board.paste(thumb, (index*360, 52))
        draw.text((index*360+12, 10), direction.replace("_", " "), font=label_font, fill="#152941")
        write_json(args.output/(direction+"_receipt.json"), result.receipt)
        write_json(args.output/(direction+"_layout.json"), layout.model_dump(mode="json"))
        manifest["variants"][direction] = {"sha256": result.sha256, "layout_sha": content_hash(layout),
            "caption_sha": sha256(result.caption_bytes).hexdigest(),
            "receipt_sha": content_hash(result.receipt), "dimensions": [result.width, result.height],
            "protected_pixels_unchanged": True, "same_environment_repeat_match": True}
        (args.output/"caption.txt").write_bytes(result.caption_bytes)
    (args.output/"FONT_LICENSE.txt").write_bytes(license_bytes)
    board.save(args.output/"comparison.png")
    manifest["files"] = {path.name: sha256(path.read_bytes()).hexdigest()
                         for path in sorted(args.output.iterdir())}
    write_json(args.output/"manifest.json", manifest)
    for path in args.output.iterdir():
        path.chmod(0o600)
    print(json.dumps({"output": str(args.output), "manifest_sha": content_hash(manifest),
                      "provider_calls": 0, "variants": manifest["variants"]}))


if __name__ == "__main__":
    main()
