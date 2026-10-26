#!/usr/bin/env python3
"""No-provider smoke checks for the distributed meeting contract package.
Not a replacement for text team's real Pydantic schemas.py v0.5 or FastAPI contract tests.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOCROOT = ROOT.parent
needed = [
    DOCROOT / "interface_spec.md",
    ROOT / "README.md",
    ROOT / "DECISION_REGISTER.md",
    ROOT / "SCHEMA_MAPPING.md",
    ROOT / "IMPLEMENTATION_PLAN.md",
    *[ROOT / "partners" / (p + ".md") for p in (
        "FRONTEND", "TEXT_AI", "IMAGE_COMPOSER", "SERVING", "PM_QA")],
    ROOT / "fixtures" / "README.md",
    ROOT / "examples" / "frontend_legacy_upload.ts",
]
for path in needed:
    assert path.is_file() and path.stat().st_size > 100, f"missing / empty: {path}"
fix = ROOT / "fixtures"
def read(name, fields):
    data = json.loads((fix / (name + ".json")).read_text(encoding="utf-8"))
    assert set(fields).issubset(data), f"missing fields in {name}"
    return data

p = read("product_input", ["brand_name", "product_name", "product_category", "features",
                            "ad_purpose", "is_functional", "photo_verified",
                            "product_image_count", "reference_image_count"])
assert 2 <= p["product_image_count"] <= 5
assert 0 <= p["reference_image_count"] <= 5
a = read("product_analysis", ["is_cosmetic", "product_type", "container_type",
                              "colors", "label_text", "mood", "is_transparent"])
r = read("research_result_no_search", ["research", "citations", "research_performed"])
assert r["research_performed"] is False and r["citations"] == []
assert "display_summary" in r["research"]
assert all(v["source"] in {"사용자 입력", "검색 결과", "AI 추론"}
           for v in r["research"]["display_summary"] + r["research"]["market_insights"])
c = read("ad_copy_output", ["plan", "ad_copy", "caption", "hashtags"])
assert {"headline", "subline", "cta"} <= c["ad_copy"].keys()
im = read("image_prompt_output", ["concept", "prompt", "mood"])
assert im["concept"] == c["plan"]["concept"] and im["mood"] == c["plan"]["mood"]
assert "negative_prompt" not in im
for name, expected in [("compliance_report_pass", True), ("compliance_report_block", False)]:
    item = read(name, ["passed", "issues", "revised_fields", "checklist", "notice"])
    assert item["passed"] is expected
    assert item["passed"] == (not any(v["risk_level"] == "위반 의심" for v in item["issues"]))
    for issue in item["issues"]:
        assert issue["start"] >= 0 and issue["end"] > issue["start"]
        assert issue["start"] <= len(issue["text"]) and issue["end"] <= len(issue["text"])
        assert issue["text"][issue["start"]:issue["end"]] == issue["text"]
print("STATIC TEAM PACK SMOKE: PASS (10 docs+entrypoints, 7 synthetic fixtures)")
