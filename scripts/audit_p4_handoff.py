"""Read-only audit of provisional IT-TEM P4 handoffs and schema drift.

Does not enable providers, invoke external APIs, modify JobStore, or approve a contract.
Run: python -m scripts.audit_p4_handoff --output .runtime/handoff/stage3_audit.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from typing import Any

BASE = "/api/v1/jobs"
REQUIRED_WIRE: dict[str, str] = {
    "POST /api/v1/jobs": "P2-upload",
    f"GET {BASE}/{{job_id}}": "P2-job",
    f"GET {BASE}/{{job_id}}/assets/{{asset_id}}": "P2-asset",
    f"POST {BASE}/{{job_id}}/mock/plan": "P3-mock-plan",
    f"POST {BASE}/{{job_id}}/mock/copy": "P3-mock-copy",
    f"POST {BASE}/{{job_id}}/approvals/copy": "P3-copy-approval",
    f"POST {BASE}/{{job_id}}/mock/image": "P3-mock-image",
    f"POST {BASE}/{{job_id}}/approvals/image": "P3-image-approval",
    f"POST {BASE}/{{job_id}}/mock/compose": "P3-compose",
    f"GET {BASE}/{{job_id}}/artifacts/{{kind}}": "P3-artifact",
    "GET /api/v1/capabilities": "P4A-capabilities",
    f"POST {BASE}/{{job_id}}/ai/plan": "P4A-ai-plan",
    f"POST {BASE}/{{job_id}}/ai/copy": "P4A-ai-copy",
}
PROPOSED_ONLY = {
    f"POST {BASE}/{{job_id}}/ai/image": "P4-image-route-not-approved",
    f"POST {BASE}/{{job_id}}/compose": "P4-live-compose-not-approved",
}
STABLE_STATUSES = {
    "INPUTS_VALIDATED", "PLAN_READY", "COPY_REVIEW_REQUIRED", "COPY_APPROVED",
    "IMAGE_REVIEW_REQUIRED", "IMAGE_APPROVED", "COMPLETED", "COPY_REJECTED",
    "IMAGE_REJECTED",
}
CONTRACT_MODELS = {
    "product_facts", "evidence", "plan_result", "copy_result",
    "visual_brief", "image_result", "generation_receipt",
}


def wire_inventory(openapi: dict[str, Any]) -> set[str]:
    return {
        f"{verb.upper()} {path}"
        for path, methods in openapi.get("paths", {}).items()
        for verb in methods
        if verb.lower() in {"get", "post", "put", "patch", "delete"}
    }


def compare_routes(inventory: set[str]) -> dict[str, Any]:
    missing = sorted(set(REQUIRED_WIRE) - inventory)
    proposed_implemented = sorted(set(PROPOSED_ONLY) & inventory)
    return {
        "required_total": len(REQUIRED_WIRE),
        "required_present": sorted(set(REQUIRED_WIRE) & inventory),
        "required_missing": missing,
        "proposed_only_not_yet_routes": sorted(set(PROPOSED_ONLY) - inventory),
        "proposed_only_currently_exposed": proposed_implemented,
        "errors": [f"Missing regression route: {x}" for x in missing],
        # A proposed route becoming available merits contract review, not an automatic failure.
        "review_notes": [f"New route requires owner/PM decision: {x}" for x in proposed_implemented],
    }


def extract_ts_statuses(source: str) -> set[str]:
    m = re.search(r"export\s+type\s+JobStatus\s*=\s*(.*?);", source, re.S)
    return set(re.findall(r'"([A-Z_]+)"', m.group(1))) if m else set()


def validate_fixtures(fixtures_dir: Path, models: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    for name in sorted(CONTRACT_MODELS):
        target = fixtures_dir / f"{name}.json"
        if not target.is_file():
            problems.append(f"Missing fixture: {target.name}")
            continue
        model = models.get(name)
        if model is None:
            problems.append(f"Missing Pydantic model: {name}")
            continue
        try:
            model.model_validate_json(target.read_bytes())
        except (ValueError, TypeError) as exc:
            problems.append(f"Invalid fixture {target.name}: {type(exc).__name__}")
    return problems


def verify_manifest(folder: Path) -> list[str]:
    """Verify content-addressed outputs; read only. Does not trust arbitrary paths."""
    manifest_file = folder / "manifest.json"
    if not manifest_file.is_file():
        return ["Missing export manifest; run scripts.export_p4_contracts first"]
    try:
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return ["Manifest is not readable JSON"]
    issues = []
    if manifest.get("contract_status") != "PROVISIONAL_NOT_APPROVED":
        issues.append("Manifest contract_status must remain PROVISIONAL_NOT_APPROVED")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != {
        "openapi.json", *(f"schemas/{name}.schema.json" for name in CONTRACT_MODELS)
    }:
        issues.append("Export artifact names differ from expected 8 files")
        return issues
    for rel, expected in sorted(artifacts.items()):
        # Only known relative paths from the set equality above can be read.
        path = folder / rel
        if not path.is_file():
            issues.append(f"Missing contract artifact: {rel}")
        elif not isinstance(expected, str) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            issues.append(f"Hash mismatch in derived contract artifact: {rel}")
    return issues


def assemble_report(*, inventory: set[str], ts_source: str, models: dict[str, Any],
                    fixtures_dir: Path, export_dir: Path, branch: str = "unchecked") -> dict[str, Any]:
    routes = compare_routes(inventory)
    ts_statuses = extract_ts_statuses(ts_source)
    ts_issues = []
    if ts_statuses != STABLE_STATUSES:
        ts_issues.append("TS JobStatus enum drift: missing=" + ",".join(sorted(STABLE_STATUSES-ts_statuses))
                         + "; extra=" + ",".join(sorted(ts_statuses-STABLE_STATUSES)))
    fixture_issues = validate_fixtures(fixtures_dir, models)
    manifest_issues = verify_manifest(export_dir)
    errors = routes["errors"] + ts_issues + fixture_issues + manifest_issues
    return {
        "audit_version": "p4-stage3-review-1",
        "contract_status": "PROVISIONAL_NOT_APPROVED",
        "git_branch_observed": branch,
        "verdict": "PASS_FOR_TEAM_REVIEW" if not errors else "FAIL_PREFLIGHT",
        "errors": errors,
        "routes": routes,
        "frontend": {"stable_status_count": len(STABLE_STATUSES), "ts_statuses": sorted(ts_statuses),
                     "missing": sorted(STABLE_STATUSES-ts_statuses), "extra": sorted(ts_statuses-STABLE_STATUSES)},
        "fixtures": {"expected": sorted(CONTRACT_MODELS), "issues": fixture_issues},
        "derived_artifacts": {"expected": 9, "issues": manifest_issues},
        "integration_gaps_not_tested": [
            "P4A ai/plan does not invoke live ResearchAdapter",
            "P4A ai/plan and ai/copy do not use Stage2 persistent cost ledger",
            "Stage2 image adapter is not bound to approved JobStore state/persistence or public route",
            "No real model/web search/quality/citation/legality E2E evidence",
            "No approved contract or team integration acceptance",
        ],
        "notes": [
            "Review PASS proves local shapes/route presence only, not contract approval or live behavior.",
            "Never infer approval from the fixture or the status of the derived manifest.",
        ],
    }


def run_audit(repo: Path, exports: Path, *, output: Path | None = None) -> dict[str, Any]:
    from src.serving.main import create_app
    from src.serving.provisional_contracts import PROVISIONAL_MODELS

    with TemporaryDirectory(prefix="ittem-p4-audit-") as scratch:
        app = create_app(storage_root=Path(scratch) / "jobs")
        openapi = app.openapi()
        inventory = wire_inventory(openapi)
    ts_source = (repo / "docs/drafts/react_client_provisional.ts").read_text(encoding="utf-8")
    report = assemble_report(
        inventory=inventory, ts_source=ts_source,
        models=PROVISIONAL_MODELS, fixtures_dir=repo / "tests/contracts/fixtures",
        export_dir=exports,
    )
    # Hash-only comparison verifies that exported artifacts match *current* source,
    # not merely that files are internally consistent with their own manifest.
    from scripts.export_p4_contracts import serialize
    manifest_file = exports / "manifest.json"
    if manifest_file.is_file():
        expected_files = {"openapi.json": openapi}
        for name, model in PROVISIONAL_MODELS.items():
            expected_files[f"schemas/{name}.schema.json"] = model.model_json_schema()
        for name, value in sorted(expected_files.items()):
            disk = exports / name
            if disk.is_file() and disk.read_bytes() != serialize(value):
                report["errors"].append(f"Stale derived artifact vs current source: {name}")
    if report["errors"]:
        report["verdict"] = "FAIL_PREFLIGHT"
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                          encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Non-billable P4 contract review readiness audit")
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--exports", type=Path, default=Path(".runtime/contracts"))
    parser.add_argument("--output", type=Path, default=Path(".runtime/handoff/p4_stage3_audit.json"))
    args = parser.parse_args()
    repo = args.repo.resolve()
    exports = args.exports if args.exports.is_absolute() else repo / args.exports
    output = args.output if args.output.is_absolute() else repo / args.output
    report = run_audit(repo, exports, output=output)
    print(f"P4 Stage3 {report['verdict']}: {len(report['routes']['required_present'])}/"
          f"{report['routes']['required_total']} existing routes; "
          f"{len(report['fixtures']['issues'])} fixture issues; "
          f"{len(report['derived_artifacts']['issues'])} artifact issues")
    for issue in report["errors"]:
        print("ERROR:", issue)
    return 0 if not report["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
