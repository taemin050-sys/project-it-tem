import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from src.text_generation.product_analyzer import analyze_product

logging.basicConfig(level=logging.INFO)

OUT_DIR = Path("outputs/product_analysis")
MODELS = ["gpt-5.4-mini", "gpt-6-luna"]

pattern = sys.argv[1]
paths = sorted(Path("data/test_products").glob(pattern))
images = [p.read_bytes() for p in paths]
product = paths[0].stem.rsplit("-", 1)[0] if paths else "unknown"
print("사진:", [p.name for p in paths])

results = {"product": product, "photos": [p.name for p in paths]}
for model in MODELS:
    print(f"\n===== {model} =====")
    r = analyze_product(images, model=model)
    print(r.model_dump_json(indent=2))
    results[model] = r.model_dump()

OUT_DIR.mkdir(parents=True, exist_ok=True)
out = OUT_DIR / f"{product}_{datetime.now():%Y%m%d_%H%M%S}.json"
out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n저장: {out}")
