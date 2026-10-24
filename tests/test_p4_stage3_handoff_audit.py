"""Stage3 deterministic non-network contract audit tests."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.audit_p4_handoff import (
    REQUIRED_WIRE, STABLE_STATUSES, assemble_report, compare_routes,
    extract_ts_statuses, validate_fixtures, verify_manifest, wire_inventory,
)


def _manifest(folder: Path) -> None:
    schemas = folder / "schemas"
    schemas.mkdir(parents=True)
    artifacts = {"openapi.json": b"{}"}
    for name in ("product_facts", "evidence", "plan_result", "copy_result", "visual_brief",
                 "image_result", "generation_receipt"):
        artifacts[f"schemas/{name}.schema.json"] = b"{}"
    for name, payload in artifacts.items():
        path = folder / name
        path.write_bytes(payload)
    (folder / "manifest.json").write_text(json.dumps({
        "contract_status": "PROVISIONAL_NOT_APPROVED",
        "artifacts": {name: hashlib.sha256(payload).hexdigest() for name, payload in artifacts.items()},
    }), encoding="utf-8")


def test_route_inventory_filters_openapi_metadata():
    result = wire_inventory({"paths": {"/api/v1/jobs": {"post": {}, "parameters": []}}})
    assert result == {"POST /api/v1/jobs"}


def test_critical_missing_route_detected():
    actual = set(REQUIRED_WIRE) - {"GET /api/v1/capabilities"}
    assert compare_routes(actual)["errors"]


def test_required_routes_can_be_present():
    assert compare_routes(set(REQUIRED_WIRE))["errors"] == []


def test_unapproved_new_routes_are_review_only():
    actual = set(REQUIRED_WIRE) | {"POST /api/v1/jobs/{job_id}/ai/image"}
    check = compare_routes(actual)
    assert check["errors"] == []
    assert len(check["review_notes"]) == 1


def test_ts_multiline_parser():
    source = 'export type JobStatus =\n' + " | ".join('"' + x + '"' for x in STABLE_STATUSES) + ';'
    assert extract_ts_statuses(source) == STABLE_STATUSES


def test_ts_parser_detects_no_statuses_when_missing():
    assert extract_ts_statuses("export type Other = 'foo';") == set()


def test_missing_fixtures_fail_closed(tmp_path: Path):
    assert len(validate_fixtures(tmp_path, {})) == 7


def test_export_manifest_integrity(tmp_path: Path):
    _manifest(tmp_path)
    assert verify_manifest(tmp_path) == []
    (tmp_path / "openapi.json").write_text('tampered', encoding='utf-8')
    assert any('Hash mismatch' in msg for msg in verify_manifest(tmp_path))


def test_manifest_cannot_silently_claim_approval(tmp_path: Path):
    _manifest(tmp_path)
    path = tmp_path / "manifest.json"
    doc = json.loads(path.read_text())
    doc["contract_status"] = "APPROVED"
    path.write_text(json.dumps(doc))
    assert any("PROVISIONAL_NOT_APPROVED" in msg for msg in verify_manifest(tmp_path))


def test_assembled_report_surfaces_failure_without_rewriting_contract(tmp_path: Path):
    _manifest(tmp_path)
    report = assemble_report(
        inventory=set(REQUIRED_WIRE), ts_source="type JobStatus = nonsense;",
        models={}, fixtures_dir=tmp_path / "not-existing", export_dir=tmp_path,
    )
    assert report["verdict"] == "FAIL_PREFLIGHT"
    assert report["integration_gaps_not_tested"]
    assert report["contract_status"] == "PROVISIONAL_NOT_APPROVED"


def test_production_wire_not_conflated_with_internal_dto():
    assert "POST /api/v1/jobs/{job_id}/ai/image" not in REQUIRED_WIRE
    assert len(STABLE_STATUSES) == 9
