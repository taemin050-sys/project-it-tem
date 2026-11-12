#!/usr/bin/env python3
"""Read-only, standard-library independent verification of A5-1 Chrome evidence.

Checks actual frozen profile SQLite export, exact Owner composition receipt,
final PNG/caption download SHA, real-browser actor/refresh/retry proof, and
absence of paid Provider, cost and queue in two OFFLINE_FIXTURE Jobs.
Does NOT verify a live GCP deployment, signed Owner/PM authority, real masks,
or commercial rights. Run after a trusted clone has checked the Git commit.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CODE_SHA = "3db1c124e0c9e56844d249a480f0cbf60aec5fb1"
TREE_SHA = "55315f45e5876b074ede64d9832eebae764a6487"
FONT_SHA = "3090ccde0442bb347aa7685d9ba8b17436a60682df6e8f92a9a670de14056e22"
POLICY_EPOCH = "a5-v3-beta-unsigned-20261110"
EXACT_LABELS = (
    "QA_USER_LOGIN", "UPLOAD_AND_COPY_FIXTURE",
    "PREAPPROVAL_AND_BATCH_REJECTION",
    "COPY_REVISION_CHANGED_SHA_AND_GENERATION",
    "COPY_RESTORED_BUT_OLD_APPROVAL_NOT_REVIVED",
    "STALE_COPY_APPROVAL_DENIED",
    "ONE_IMAGE_AFTER_COPY_APPROVAL",
    "EXPLICIT_IMAGE_REJECTION",
    "SECOND_CANDIDATE_NEW_ATTEMPT_NEW_SHA",
    "COMPOSED_FINAL_ARTIFACT_READY",
    "ACTUAL_CHROME_DOWNLOAD_SHA_MATCH",
    "GET_ONLY_REFRESH_RESUME",
    "MOBILE_VIEWPORT_390", "MOBILE_VIEWPORT_360",
    "FOREIGN_ACTOR_AND_UNAUTHENTICATED_DENIED",
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_digest(value) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")).hexdigest()


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def verify_profile(name: str) -> dict:
    p = ROOT / name
    assert p.is_dir(), f"PROFILE_DIR_MISSING:{name}"
    manifest = p / "SHA256_MANIFEST.txt"
    assert manifest.is_file()
    manifest_lines = manifest.read_text().splitlines()
    assert len(manifest_lines) == 19
    for line in manifest_lines:
        want, filename = line.split("  ", 1)
        assert re.fullmatch(r"[0-9a-f]{64}", want)
        assert filename == Path(filename).name, "UNSAFE_EVIDENCE_FILENAME"
        assert sha(p / filename) == want, f"MANIFEST_SHA_MISMATCH:{name}:{filename}"
    t, v = load(p / "browser_trace.json"), load(p / "ledger_artifact_verification.json")
    frozen = load(p / "frozen_profile_snapshot.json")
    receipt = load(p / "owner_composition_receipt.json")
    agg = load(ROOT / "A51_BOTH_PROFILES_AGGREGATE.json")
    assert t["source_commit"] == CODE_SHA == v["source_commit"]
    assert t["contract"] == "IT_TEM_A51_V3_OFFICIAL_REACT_CHROME_FIXTURE_V1"
    assert t["actual_react_app"] is True and t["qa_fixture"] is True
    assert t["a51_profile"] == name
    assert t["network_external_post_count"] == 0
    assert t["exfiltration_attempts"] == [] and t["browser_errors"] == []
    assert t["final_state"] == "COMPLETED" and t["image_attempt_version"] == 2
    assert tuple(x["label"] for x in t["steps"]) == EXACT_LABELS
    refresh = next(x for x in t["steps"] if x["label"] == "GET_ONLY_REFRESH_RESUME")
    assert refresh["post_count_after_reload"] == 0
    access = next(x for x in t["steps"]
                  if x["label"] == "FOREIGN_ACTOR_AND_UNAUTHENTICATED_DENIED")
    assert access["http_without_session"] == 401
    assert access["http_foreign_actor"] == 404
    batch = next(x for x in t["steps"] if x["label"] == "PREAPPROVAL_AND_BATCH_REJECTION")
    assert all(batch[f"candidate_count_{i}"] == 422 for i in (2, 3, 4))
    assert batch["mixed_modes_http"] == 422
    assert len(t["screenshots"]) == 12
    assert sorted(x["filename"] for x in t["screenshots"] if "mobile" in x["filename"]) == [
        "11_mobile_360.png", "11_mobile_390.png"]
    for shot in t["screenshots"]:
        assert sha(p / shot["filename"]) == shot["sha256"]
    assert t["http_totals"]["post"] == 18 and t["http_totals"]["get"] >= 1
    assert v["queue_rows"] == v["cost_attempt_rows"] == v["provider_calls"] == 0
    assert v["download_verified"] is True and v["final_png_pixels"] == [1080, 1350]
    assert v["mode"] == "OFFLINE_FIXTURE" and v["provider_e2e"] == "NOT_AUDITED"
    assert v["image_attempt_versions"] == [1, 2]
    assert v["image_attempt_states"] == ["REJECTED", "COMPLETED"]
    assert v["image_attempt_shas"][0] != v["image_attempt_shas"][1]
    assert v["approval_sha"] != "" and v["copy_sha"] != ""
    assert v["human_pm_visual_acceptance"] == "PENDING"
    assert v["real_product_protection"] == "NOT_AUDITED"
    assert v["product_quality"]["4x5_image_cta_present"] is True
    assert v["product_quality"]["gate"] == "ON_IMAGE_CTA_FIXTURE_PASS_REAL_PRODUCT_FIDELITY_HOLD"
    assert sha(p / "ad_1080x1350.png") == v["final_png_sha256"] == t["final_sha"]
    assert sha(p / "caption.txt") == v["caption_sha256"] == t["caption_sha"]
    assert (p / "ad_1080x1350.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert (p / "caption.txt").read_bytes().decode("utf-8")
    assert sha(p / "owner_composition_receipt.json") == v["composition_receipt_sha256"]
    assert receipt["profile_id"] == frozen["profile_id"] == f"OWNER_COMPOSED_4X5_V3_BETA_{name}"
    assert receipt["profile_version"] == frozen["profile_version"]
    assert frozen["source"] == "READ_ONLY_REAL_SQLITE_TEMPLATE_SNAPSHOT"
    assert frozen["source_job_id"] == t["completed_job_id"] == agg["profiles"][name]["job_id"]
    assert frozen["layout_sha"] == canonical_digest(frozen["layout"])
    assert frozen["safe_zone_sha"] == canonical_digest(frozen["safe_zone"])
    assert frozen["bound_font_sha"] == receipt["font_sha256"] == FONT_SHA
    assert receipt["profile_layout_sha256"] == frozen["layout_sha"]
    assert receipt["profile_policy_epoch"] == frozen["safe_zone"]["policy_epoch"] == POLICY_EPOCH
    assert frozen["safe_zone"]["real_provider_permitted"] is False
    assert frozen["safe_zone"]["real_customer_assets_permitted"] is False
    assert frozen["layout"]["cta_placement"] == receipt["cta_placement"] == "image"
    assert set(frozen["layout"]["text_regions"]) == set(receipt["placements"]) == {
        "headline", "subline", "cta"}
    assert receipt["omitted_image_fields"] == []
    assert receipt["beta_style"] == name
    assert receipt["typography_variable_weight"] == {
        "headline": 700, "subline": 500, "cta": 700}
    assert receipt["owner_pm_signed"] is False and receipt["beta_only"] is True
    assert receipt["protected_region_check"] is False
    assert receipt["synthetic_target_region_check"] is True
    assert receipt["protection_evidence"] == "SYNTHETIC_TARGET_ONLY_REAL_PRODUCT_NOT_AUDITED"
    assert receipt["provider_calls"] == 0
    for field in ("headline", "subline", "cta"):
        q = receipt["placements"][field]
        assert re.fullmatch(r"[0-9a-f]{64}", q["text_sha256"])
        assert q["line_count"] == 1
        assert q["ink_boxes"]
    assert receipt["placements"]["cta"]["font_size"] >= 48
    assert agg["code_commit_sha"] == CODE_SHA
    assert agg["code_tree_sha"] == TREE_SHA
    assert agg["profiles"][name]["final_png_sha256"] == t["final_sha"]
    assert agg["profiles"][name]["receipt_sha256"] == v["composition_receipt_sha256"]
    assert agg["full_feature_beta_ready_for_team_uat"] is False
    assert agg["paid_provider_calls"] == 0
    assert agg["gcp_a_deployment_performed"] is False
    return {
        "profile": name, "job": t["completed_job_id"],
        "final_sha": t["final_sha"], "caption_sha": t["caption_sha"],
        "owner_receipt_sha": v["composition_receipt_sha256"],
        "layout_sha": frozen["layout_sha"], "steps": len(t["steps"]),
        "screenshots": len(t["screenshots"]),
    }


def main():
    for filename, needle in {
        "A51_FULL_PYTHON_1161.log": "1161 passed",
        "A51_REACT_57.log": "pass 57",
        "A51_LINT.log": "0 warnings and 0 errors",
        "A51_BUILD.log": "built in",
        "A51_V2_COMPATIBILITY_48.log": "48 passed",
        "A51_OWNER_IMAGE_MOCKTRANSPORT_11.log": "11 passed",
        "A51_CHROME_A_EXIT0.log": "A51_V3_OFFICIAL_REACT_FUNCTIONAL_E2E_PASS",
        "A51_CHROME_C_EXIT0.log": "A51_V3_OFFICIAL_REACT_FUNCTIONAL_E2E_PASS",
    }.items():
        assert needle in (ROOT / filename).read_text(), filename
    results = [verify_profile("A"), verify_profile("C")]
    for p in ROOT.rglob("*"):
        if p.is_file() and p.suffix in (".txt", ".log", ".json"):
            data = p.read_text(errors="replace").lower()
            for secret_marker in ("sk-proj-", "openai_api_key=", "a41-fixture-invite-"):
                assert secret_marker not in data, f"SECRET_MARKER_IN_EVIDENCE:{p.name}"
    print(json.dumps({
        "result": "A51_A_AND_C_OFFLINE_CHROME_EVIDENCE_PASS",
        "code_sha": CODE_SHA,
        "code_tree": TREE_SHA,
        "independent_c_a": "PENDING",
        "gcp": "NOT_DEPLOYED",
        "real_provider": "NOT_AUDITED",
        "commercial_release_ready": False,
        "profiles": results,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
