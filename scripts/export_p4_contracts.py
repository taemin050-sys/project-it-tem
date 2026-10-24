"""Export machine-readable PROVISIONAL schemas without network or paid API calls.

Run from repo root: python -m scripts.export_p4_contracts --output .runtime/contracts
Output is a derived build artifact, never a replacement for docs/interface_spec.md.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from src.serving.main import create_app
from src.serving.provisional_contracts import PROVISIONAL_MODELS


def serialize(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def export(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    schema_dir = output_dir / "schemas"
    schema_dir.mkdir(parents=True, exist_ok=True)
    files = {"openapi.json": create_app(storage_root=output_dir / "unused-job-storage").openapi()}
    for name, model in sorted(PROVISIONAL_MODELS.items()):
        files[f"schemas/{name}.schema.json"] = model.model_json_schema()
    hashes = {}
    for relative, payload in sorted(files.items()):
        destination = output_dir / relative
        destination.write_bytes(serialize(payload))
        hashes[relative] = hashlib.sha256(destination.read_bytes()).hexdigest()
    manifest = {
        "contract_status": "PROVISIONAL_NOT_APPROVED",
        "canonical_document": "docs/interface_spec.md",
        "source": "FastAPI /openapi.json and src/serving/provisional_contracts.py",
        "artifacts": hashes,
        "warnings": [
            "Do not interpret provisional DTO schemas as existing HTTP response formats.",
            "No paid models, web research, product-claim verification, or compliance check are performed.",
        ],
    }
    (output_dir / "manifest.json").write_bytes(serialize(manifest))
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path(".runtime/contracts"))
    args = parser.parse_args()
    result = export(args.output)
    print(f"P4-Preflight provisional export PASS: {len(result['artifacts'])} schema files")
