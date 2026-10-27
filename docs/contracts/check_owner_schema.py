#!/usr/bin/env python3
"""Inspect trusted Text-owner schemas.py at an explicitly supplied commit/file.

Does NOT infer an 'official' owner source from meeting text or synthetic fixture.
Run with the actual owner's repository checkout at an agreed immutable SHA.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import sys


MAPPING = {
    "product_input.json": "ProductInput",
    "product_analysis.json": "ProductAnalysis",
    "research_result_no_search.json": "ResearchResult",
    "ad_copy_output.json": "AdCopyOutput",
    "copy_for_block.json": "AdCopyOutput",
    "image_prompt_output.json": "ImagePromptOutput",
    "compliance_report_pass.json": "ComplianceReport",
    "compliance_report_block.json": "ComplianceReport",
}


def run() -> int:
    parser = argparse.ArgumentParser(description="Pydantic v0.5 Owner schema contract checker")
    parser.add_argument("--source", required=True, type=Path, help="REAL owner schemas.py from pinned git checkout")
    parser.add_argument("--expected-sha256", required=True, help="SHA-256 of actual trusted owner file")
    parser.add_argument("--out", type=Path, help="Optional directory for generated owner JSON Schema")
    args = parser.parse_args()
    if not args.source.is_file():
        print("BLOCKED_BY_SOURCE: owner schemas.py does not exist", file=sys.stderr)
        return 2
    digest = sha256(args.source.read_bytes()).hexdigest()
    if len(args.expected_sha256) != 64 or digest != args.expected_sha256.lower():
        print("BLOCKED_BY_SOURCE: exact schema source SHA-256 mismatch", file=sys.stderr)
        return 2

    spec = importlib.util.spec_from_file_location("ittem_verified_owner_schemas", args.source)
    if spec is None or spec.loader is None:
        raise RuntimeError("Invalid schema module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fix = Path(__file__).resolve().parent / "fixtures"
    for file, model_name in MAPPING.items():
        model = getattr(module, model_name)
        payload = json.loads((fix / file).read_text(encoding="utf-8"))
        model.model_validate(payload)
        if args.out:
            args.out.mkdir(parents=True, exist_ok=True)
            schema_path = args.out / (model_name + ".schema.json")
            schema_path.write_text(json.dumps(model.model_json_schema(), ensure_ascii=False,
                                              indent=2) + "\n", encoding="utf-8")
        print(f"VALID: {file} -> {model_name}")
    print("OWNER SCHEMA MODEL_VALIDATE: PASS, source SHA256=" + digest)
    print("WARNING: this tests v0.5 model structure, not legacy mapper round-trip or HTTP OpenAPI.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
