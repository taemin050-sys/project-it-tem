#!/usr/bin/env python3
"""No-provider smoke checks for the distributed meeting contract package.
Not a replacement for text team's real Pydantic schemas.py v0.5 or FastAPI contract tests.
"""
import json
from pathlib import Path
from validation import ContractViolation, validate_compliance

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
# Validate exact issue offsets against the FULL source copy field, not issue.text.
# The 'blocked' report belongs to a distinct deliberately risky Copy Fixture.
for report_name, copy_name, expected in [
    ("compliance_report_pass", "ad_copy_output", True),
    ("compliance_report_block", "copy_for_block", False),
]:
    report = read(report_name, ["passed", "issues", "revised_fields",
                                "checklist", "notice"])
    source = read(copy_name, ["plan", "ad_copy", "caption", "hashtags"])
    outcome = validate_compliance(source, report, product_name=p["product_name"])
    if outcome is not expected:
        raise ContractViolation(f"unexpected compliance result: {report_name}")
# One invalid offset must FAIL. This smoke guard prevents reintroducing the
# formerly incorrect self-slicing issue.text[start:end] validation.
invalid = json.loads(json.dumps(read("compliance_report_block", ["issues", "passed"])))
invalid["issues"][0]["start"] = 0
invalid["issues"][0]["end"] = len(invalid["issues"][0]["text"])
try:
    validate_compliance(read("copy_for_block", ["ad_copy", "caption", "hashtags"]),
                        invalid, product_name=p["product_name"])
except ContractViolation:
    pass
else:
    raise ContractViolation("bad offset was accepted")
print("STATIC TEAM PACK SMOKE: PASS (10 docs+entrypoints, 7 synthetic fixtures)")


# DOC_MARKDOWN_STRUCTURE: all relative links and fenced Mermaid/code blocks.
import re
all_docs = [ROOT.parent / "interface_spec.md", *sorted(ROOT.rglob("*.md"))]
for doc in all_docs:
    body = doc.read_text(encoding="utf-8")
    assert body.count(chr(96) * 3) % 2 == 0, f"unclosed markdown fence: {doc}"
    assert body.startswith("# "), f"missing H1: {doc}"
    for target in re.findall(r"\]\(([^)]+)\)", body):
        if target.startswith(("https://", "http://", "mailto:", "#")):
            continue
        path = doc.parent / target.split("#", 1)[0]
        assert path.exists(), f"broken link: {doc} -> {target}"
contract = (ROOT.parent / "interface_spec.md").read_text(encoding="utf-8")
for section in ("## 1.", "## 2.", "## 3.", "## 4.", "## 5.", "## 6.", "## 7.", "## 8.", "## 9."):
    assert section in contract, f"missing interface section {section}"
for token in ("13개", "ProductInput", "ProductAnalysis", "ResearchResult",
              "AdCopyOutput", "ComplianceReport", "ImagePromptOutput",
              "GenerationReceipt", "409", "1080", "1350"):
    assert token in contract, f"missing required reference: {token}"
print(f"DOC MARKDOWN STRUCTURE: PASS ({len(all_docs)} docs, relative links, fences, v0.1 coverage)")
