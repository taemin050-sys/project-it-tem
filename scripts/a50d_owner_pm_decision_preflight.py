"""A5-0D proposal-only, read-only Owner/PM decision dossier preflight.

Does not install fonts, edit production runtime, change Owner profile,
or infer human approvals. Source inputs are existing A5-0 versioned mockups.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
A50 = BASE / "docs/integration/evidence/A50_20261110"
DOCS = BASE / "docs/integration"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def canonical(data: object) -> bytes:
    return json.dumps(data, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def contrast_ratio(a: str, b: str) -> float:
    def lum(hex_color: str) -> float:
        rgb = [int(hex_color[i:i+2], 16)/255 for i in (1, 3, 5)]
        rgb = [v/12.92 if v <= 0.04045 else ((v+0.055)/1.055)**2.4
               for v in rgb]
        return sum(x*y for x, y in zip((0.2126, 0.7152, 0.0722), rgb))
    left, right = sorted((lum(a), lum(b)), reverse=True)
    return round((left + .05)/(right + .05), 3)


def load_style_defs() -> dict:
    spec = importlib.util.spec_from_file_location(
        "a50_standalone_design", BASE/"scripts/a50_composed45_design_concepts.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.CANDIDATES


def inspect() -> dict:
    m = json.loads((A50/"A50_DESIGN_PROPOSALS_MANIFEST.json").read_text("utf-8"))
    s = load_style_defs()
    safe = (64, 64, 1016, 1286)
    assert m["owner_pm_approval"] == "DECISION_PENDING"
    assert m["runtime_profile_implementation"] == "NOT_PERFORMED"
    assert m["9x16_cta_policy"] == "DECISION_PENDING_PM_OWNER"
    assert len(m["candidates"]) == 3 and set(m["candidates"]) == set(s)
    assert sha(A50/"A50_OWNER_PM_4UP_COMPARISON.png") == m["four_up_comparison_sha256"]
    assert sha(A50/"A41_ORIGINAL_WITHOUT_CTA.png") == m["actual_a41_png_sha256"]
    assert m["copy_sha256"]["cta"] == hashlib.sha256(
        "지금 만나보세요".encode("utf-8")).hexdigest()
    goals = {
        # Review-proposal thresholds ONLY; never treat as a signed PM policy.
        "mobile_reference_width": 360,
        "proposed_cta_rendered_font_min_display_px": 16.0,
        "proposed_safe_frame_bottom_inset_min_display_px": 12.0,
        "proposed_cta_foreground_background_contrast_min": 4.5,
        "threshold_authority": "PROPOSAL_ONLY_NOT_PM_APPROVED",
    }
    cases = {}
    for name, info in sorted(m["candidates"].items()):
        assert sha(A50/info["png"]) == info["sha256"]
        style = s[name]
        box = tuple(info["text"]["cta"]["region"])
        assert box == style["cta"]
        assert box[3] <= safe[3]
        f = info["text"]["cta"]["font_px"]
        displayed = round(f/3, 2)
        inset = round((safe[3]-box[3])/3, 2)
        contrast = contrast_ratio(style["action_ink"], style["action_bg"])
        assert info["text"]["cta"]["render_count"] == 1
        cases[name] = {
            "design_file": info["png"],
            "mock_sha256": info["sha256"],
            "comparison_source_sha256": m["four_up_comparison_sha256"],
            "cta_region_1080": list(box),
            "cta_font_px_1080": f,
            "cta_font_px_on_360": displayed,
            "safe_frame_bottom_inset_1080": safe[3]-box[3],
            "safe_frame_bottom_inset_360": inset,
            "cta_to_unverified_product_target_1080": box[1]-1183,
            "cta_text_vs_button_bg_contrast_ratio": contrast,
            "proposed_min_font_pass": displayed >= goals[
                "proposed_cta_rendered_font_min_display_px"],
            "proposed_min_bottom_inset_pass": inset >= goals[
                "proposed_safe_frame_bottom_inset_min_display_px"],
            "proposed_min_contrast_pass": contrast >= goals[
                "proposed_cta_foreground_background_contrast_min"],
            "real_brand_label_protection": "NOT_AUDITED",
            "platform_crop_safe_zone": "NOT_AUDITED",
            "approved_for_production": False,
        }
    assert all(not x["proposed_min_bottom_inset_pass"] for x in cases.values())
    assert cases["A_EDITORIAL_CENTER"]["proposed_min_font_pass"] is False
    return {
        "contract": "IT_TEM_P03_A5_0D_DECISION_PREFLIGHT_V1",
        "review_status": "OWNER_AND_PM_DECISION_PENDING",
        "source_audit_head": "3842db04123fc8a8c681a2bf50c90dc82464c143",
        "source_audit_tree": "03e9d11eaa0d3e02d57f09367fa571f8d0a65580",
        "canvas": [1080, 1350],
        "source_copy_sha256": m["copy_sha256"],
        "goals_proposed_not_approved": goals,
        "safe_frame_from_owner_v2": list(safe),
        "product_target_unverified": [466, 418, 611, 1183],
        "candidates": cases,
        "recommendation_not_a_decision": {
            "default_first_review": "A_EDITORIAL_CENTER",
            "optional_promotional": "C_CONTRAST_ACTION",
            "editorial_alternative": "B_EDITORIAL_LEFT",
        },
        "findings": [
            "ALL_MOCKS_INSUFFICIENT_BOTTOM_SAFE_INSET_AT_PROPOSED_12PX_360_THRESHOLD",
            "A_MOCK_BELOW_PROPOSED_16PX_360_CTA_FONT_THRESHOLD",
            "V2_PRODUCT_TARGET_NOT_A_DETECTED_PACKAGING_OR_LABEL_MASK",
            "MODEL_FONT_AND_HUMAN_COMMERCIAL_QUALITY_NOT_AUDITED",
        ],
        "owner_source_v3_implementation": "NOT_STARTED",
        "replayable_design_assets": "C_A50_DESIGN_MOCKS_REPRODUCIBLE_PROPOSAL_ACCEPTED",
        "release": "NOT_RELEASE_READY",
    }


def build_contract(m: dict) -> dict:
    return {
        "document_type": "DRAFT_REVIEW_ONLY_NON_EXECUTABLE",
        "contract": "IT_TEM_P03_PROFILE_V3_PROPOSAL_ENVELOPE_V1",
        "approval_state": "DRAFT_NOT_APPROVED",
        "a5_1_implementation_authorized": False,
        "owner_pm_signed": False,
        "owner_image24_signoff": None,
        "pm_signoff": None,
        "selected_profile": None,
        "profile_id": None,
        "profile_version": None,
        "profile_json_sha256": None,
        "image_owner_source_commit": None,
        "effective_policy_epoch": None,
        "commercial_font": {
            "family": None,
            "weight": None,
            "file_sha256": None,
            "license_evidence_sha256": None,
            "server_runtime_distribution_cleared": False,
            "candidates_for_legal_review_not_adopted": [
                {
                    "family": "Pretendard",
                    "license": "SIL-OFL-1.1",
                    "publisher_license_url":
                        "https://github.com/orioncactus/pretendard/blob/main/LICENSE",
                    "status": "UPSTREAM_LICENSE_FOUND_NO_PINNED_FONT_BINARY",
                },
                {
                    "family": "Noto Sans CJK KR",
                    "license": "SIL-OFL-1.1 (verify exact release)",
                    "publisher_license_url":
                        "https://github.com/notofonts/noto-cjk",
                    "status": "UPSTREAM_LICENSE_FOUND_NO_PINNED_FONT_BINARY",
                },
            ],
        },
        "binding_target": {
            "generation_mode": "composed",
            "aspect_ratio": "4:5",
            "final_canvas_px": [1080, 1350],
            "cta_placement": "image",
            "cta_expected_render_count": 1,
            "copy_sha256": m["source_copy_sha256"],
            "bound_fields": [
                "job_id", "actor", "input_sha", "copy_sha", "review_sha",
                "generation", "approval_sha", "policy_epoch", "image_attempt_id",
                "image_attempt_version", "image_sha", "prompt_context_sha",
                "profile_id", "profile_version", "layout_sha",
                "font_sha256", "font_license_evidence_sha256",
                "composition_receipt_sha256", "final_png_sha256",
                "caption_sha256", "source_commit", "runtime_build_sha",
            ],
            "layout_boxes_ltrb": None,
            "approved_typography": None,
            "actual_product_protection_contract": None,
            "mobile_crop_and_safe_zone_contract": None,
            "fail_closed_on_unresolved": True,
        },
        "prioritization_only": m["recommendation_not_a_decision"],
        "mock_sha_candidates": {
            k: v["mock_sha256"] for k, v in m["candidates"].items()
        },
        "design_revision_required_before_approval": True,
        "required_gates_for_a5_1": [
            "D50-02", "D50-03", "D50-04", "D50-05",
            "D50-06", "D50-07", "D50-09",
        ],
        "legacy_preservation": {
            "existing_completed_job": "IMMUTABLE",
            "in_flight_v2_job": "PRESERVE_FROZEN_V2",
            "new_4x5_composed_after_effective_policy_epoch": "NEW_V3_ONLY_IF_SIGNED",
            "other_modes_and_ratios": "UNCHANGED",
            "freeform_server_overlay": "FORBIDDEN",
            "9x16_cta_policy": "DECISION_PENDING_PM_OWNER",
            "automatic_migration": "FORBIDDEN",
            "automatic_rebill_or_provider_retry": "FORBIDDEN",
            "rollback": "REVERT_NEW_JOB_ROUTE_TO_V2_ONLY_AFTER_PM_APPROVAL",
        },
        "safety": {
            "paid_worker_authorization": "HOLD",
            "gcp_qa_deployment": "HOLD",
            "product_release": "NOT_RELEASE_READY",
        },
        "source_audit_head": m["source_audit_head"],
    }


def make_register(m: dict) -> list[dict]:
    catalogue = [
        ("D50-01", "4:5 composed on-image CTA once", "Image Owner+PM",
         "ALREADY_DECIDED_POLICY", "C-A4 CTA P1 and original PM policy"),
        ("D50-02", "A/C priority and B editorial profile selection", "Image Owner+PM",
         "PENDING", "A50 4-up screenshot and 360/390 mobile assets"),
        ("D50-03", "exact regions, profile ID/version, canonical JSON SHA", "Image Owner+PM",
         "PENDING", "A50 proposal geometry, revised safe inset review"),
        ("D50-04", "production font and weight, font SHA and OFL notice", "Image Owner+PM/Legal",
         "HOLD", "upstream font license, exact binary hash and distribution scope"),
        ("D50-05", "actual brand, package, model and label segmentation", "Image Owner+PM",
         "NOT_AUDITED", "representative permitted real product images and protected masks"),
        ("D50-06", "mobile CTA font/spacing/contrast/crop/overflow", "Image Owner+PM",
         "PENDING", "360/390 and mixed long-Korean strings, A50D preflight"),
        ("D50-07", "visual scorecard, weighting and human acceptance rubric", "PM+Image Owner",
         "PENDING", "blinded review with actual brand/product examples"),
        ("D50-08", "9:16 CTA platform versus image policy", "PM+Image Owner",
         "DECISION_PENDING_PM_OWNER", "separate 9:16 product policy"),
        ("D50-09", "new job-only version binding, v2 rollback and no migration", "Serving+PM+Image Owner",
         "A5_1_IMPLEMENTATION_HOLD", "immutable job schema, historical receipt and rollback tests"),
    ]
    return [{
        "decision_id": did,
        "decision_topic": topic,
        "required_approver_roles": who,
        "status": status,
        "review_evidence_required": evid,
        "selected_mock_sha256": "",
        "exact_profile_json_sha256": "",
        "approved_font_sha256": "",
        "font_license_evidence_sha256": "",
        "effective_policy_epoch": "",
        "owner_commit_sha": "",
        "image_owner_signoff_ref": "",
        "pm_signoff_ref": "",
        "approval_timestamp": "",
        "decision_rationale": "",
    } for did, topic, who, status, evid in catalogue]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    # R1: The generator owns ONLY its explicit output directory, never the
    # version-controlled canonical review CSV/JSON, or a future signed ledger.
    # Refuse *every* pre-existing destination, even if its draft bytes match.
    supplied = args.out.expanduser().absolute()
    if supplied.is_symlink() or (supplied.exists() and not supplied.is_dir()):
        raise SystemExit("A50D_SIGNED_OR_EXISTING_OUTPUT_PATH_HOLD")
    # macOS standard /var -> /private/var alias must not appear as a
    # malicious output path; resolve only AFTER rejecting leaf symlinks.
    out = supplied.resolve()
    out.mkdir(parents=True, exist_ok=True)
    measurements = inspect()
    contract = build_contract(measurements)
    register = make_register(measurements)
    paths = {
        "measurements": out/"A50D_GEOMETRY_AND_DECISION_PREFLIGHT.json",
        "contract": out/"BP18_A50D_PROFILE_V3_REVIEW_ONLY_CONTRACT_20261110.json",
        "decisions": out/"BP18_A50D_OWNER_PM_DECISION_REGISTER_20261110.csv",
    }
    # A signed record in any output location must remain untouched.
    # Preflight ALL file paths before creating the first draft.
    for f in paths.values():
        if f.exists() or f.is_symlink():
            raise SystemExit(f"A50D_SIGNED_OR_EXISTING_DESTINATION_HOLD: {f}")
    from io import StringIO
    csvbuf = StringIO(newline="")
    writer = csv.DictWriter(csvbuf, fieldnames=list(register[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(register)
    payloads = {
        "measurements": json.dumps(measurements, ensure_ascii=False, sort_keys=True, indent=2)+"\n",
        "contract": json.dumps(contract, ensure_ascii=False, sort_keys=True, indent=2)+"\n",
        "decisions": csvbuf.getvalue(),
    }
    created = []
    try:
        for key, f in paths.items():
            # O_EXCL / O_NOFOLLOW: prevent race-driven clobber, including
            # previously accepted signoff material. No rewrite capability.
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            fd = os.open(f, flags, 0o600)
            created.append(f)
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
                handle.write(payloads[key])
                handle.flush()
                os.fsync(handle.fileno())
    except BaseException:
        for f in created:
            f.unlink(missing_ok=True)  # only this invocation's drafts
        raise
    print("A50D_REVIEW_ASSETS_READY_OUTSIDE_SIGNED_LEDGER")
    for key, f in paths.items():
        print(key, str(f), sha(f))
    print("A50D_SIGNOFFS=0; PRODUCT_PROFILE_IMPLEMENTATION=HOLD")


if __name__ == "__main__":
    main()
