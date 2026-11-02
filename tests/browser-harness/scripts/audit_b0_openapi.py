"""Read-only S3-B.2 OpenAPI / real response / TypeScript cross-check.

Creates a private, disposable TestClient JobStore. No runtime changes or API calls.
The diagnostic intentionally lists documentation gaps without auto-fixing them.
"""
from __future__ import annotations

import argparse
import json
import tempfile
import sys
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image
# Direct script execution must resolve the canonical repository root.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from src.serving.main import create_app


def png(color: tuple[int, int, int]) -> bytes:
    stream = BytesIO()
    Image.new("RGB", (24, 24), color).save(stream, format="PNG")
    return stream.getvalue()


def audit() -> dict:
    repo = Path(__file__).resolve().parents[3]
    ts_source = (repo / "tests/browser-harness/src/api.ts").read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="ittem_openapi_audit_") as temp:
        with TestClient(create_app(storage_root=Path(temp) / "jobs")) as client:
            spec = client.get("/openapi.json").json()
            ops = {
                (method.upper(), route)
                for route, definitions in spec["paths"].items()
                for method in definitions
                if method in {"get", "post", "put", "patch", "delete"}
            }
            assert len(ops) == 11, ops
            upload = client.post("/api/v1/jobs", files=[
                ("product_images", ("first.png", png((90, 10, 10)), "image/png")),
                ("product_images", ("second.png", png((10, 90, 10)), "image/png")),
            ])
            assert upload.status_code == 201
            job = upload.json()
            job_id = job["job_id"]
            artifact_not_ready = client.get(f"/api/v1/jobs/{job_id}/artifacts/final")
            assert artifact_not_ready.status_code == 404
            wrong_state = client.post(f"/api/v1/jobs/{job_id}/mock/copy")
            assert wrong_state.status_code == 409
            for key in ("job_id", "status", "created_at", "assets"):
                assert key in job and (key + ":") in ts_source
            assert "content_type" in ts_source and "download_url" in ts_source
            # Inspect how the published OpenAPI represents the artifact stream.
            artifact = spec["paths"]["/api/v1/jobs/{job_id}/artifacts/{kind}"]["get"]
            response_200 = artifact["responses"].get("200", {})
            declared_content = list(response_200.get("content", {}))
            declared_json_schema = (
                response_200.get("content", {}).get("application/json", {}).get("schema")
            )
            results = {
                "source": "current FastAPI TestClient app.openapi(), no external API",
                "mode": "MOCK_ONLY",
                "operation_count": len(ops),
                "operations": [{"method": m, "path": p} for m, p in sorted(ops)],
                "observed": {
                    "job_created_status": upload.status_code,
                    "job_keys": sorted(job),
                    "job_asset_keys": sorted(job["assets"][0]),
                    "wrong_workflow_state": wrong_state.status_code,
                    "wrong_workflow_detail": wrong_state.json().get("detail"),
                    "artifact_missing": artifact_not_ready.status_code,
                },
                "documented_artifact_get_200": {
                    "media_types": declared_content,
                    "json_schema": declared_json_schema,
                },
                "diagnostic_gaps": {
                    "file_response": (
                        "OpenAPI currently describes /artifacts/{kind} with JSON, "
                        "but actual FileResponse returns PNG/JSON/text with Content-Disposition"
                        if "application/json" in declared_content else
                        "Artifact FileResponse documentation must be manually reviewed"
                    ),
                    "business_errors": "404/409/413/503 handler outcomes not enumerated on all operations",
                    "client_types": "TS Job is a hand-maintained structural type; not generated from authoritative response_model",
                },
                "typescript_static_keys_checked": ["job_id", "status", "created_at", "assets",
                    "download_url", "content_type"],
                "contract_change": "NONE; diagnostic only; new HTTP Wire still BLOCKED_WIRE=7 FROZEN=0",
            }
            return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", help="Write JSON diagnostic to this optional path")
    args = parser.parse_args()
    result = audit()
    pretty = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        destination = Path(args.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(pretty, encoding="utf-8")
    print("OPENAPI_DIAGNOSTIC_PASS: 11 operations, 201/404/409 and TS structural keys")
    print("OpenAPI gaps: FileResponse documentation, missing business errors and generated TS types")
    if args.output:
        print("DIAGNOSTIC_FILE: " + str(args.output))


if __name__ == "__main__":
    main()
