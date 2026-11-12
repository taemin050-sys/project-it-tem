"""A5-0D: prevent turning unsigned design options into product approval.

Pure read-only checks of the proposed contract/decision register and existing
A50 independently accepted mock SHA. No network or Owner source modifications.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
D = ROOT/"docs/integration"
E = D/"evidence/A50D_20261110"
A50 = D/"evidence/A50_20261110"
M = json.loads((E/"A50D_GEOMETRY_AND_DECISION_PREFLIGHT.json").read_text("utf-8"))
C = json.loads((D/"BP18_A50D_PROFILE_V3_REVIEW_ONLY_CONTRACT_20261110.json").read_text("utf-8"))
with (D/"BP18_A50D_OWNER_PM_DECISION_REGISTER_20261110.csv").open(
        encoding="utf-8", newline="") as handle:
    DECISIONS = list(csv.DictReader(handle))
ORIGINAL = json.loads((A50/"A50_DESIGN_PROPOSALS_MANIFEST.json").read_text("utf-8"))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_a50d_source_audit_basis_and_preflight_are_exact():
    assert M["source_audit_head"] == "3842db04123fc8a8c681a2bf50c90dc82464c143"
    assert M["source_audit_tree"] == "03e9d11eaa0d3e02d57f09367fa571f8d0a65580"
    assert M["source_copy_sha256"] == ORIGINAL["copy_sha256"]
    assert M["canvas"] == ORIGINAL["canvas"] == [1080,1350]
    assert M["safe_frame_from_owner_v2"] == [64,64,1016,1286]
    assert M["product_target_unverified"] == [466,418,611,1183]
    assert M["release"] == "NOT_RELEASE_READY"
    assert M["owner_source_v3_implementation"] == "NOT_STARTED"


def test_a50d_candidate_source_sha_and_exact_review_geometry():
    assert set(M["candidates"]) == set(ORIGINAL["candidates"])
    for name, record in M["candidates"].items():
        old = ORIGINAL["candidates"][name]
        assert record["mock_sha256"] == old["sha256"] == sha(A50/old["png"])
        assert record["cta_region_1080"] == old["text"]["cta"]["region"]
        assert record["cta_font_px_1080"] == old["text"]["cta"]["font_px"]
        assert record["approved_for_production"] is False
        assert record["real_brand_label_protection"] == "NOT_AUDITED"
        assert record["platform_crop_safe_zone"] == "NOT_AUDITED"


def test_a50d_proposed_thresholds_never_become_signed_rules():
    goals = M["goals_proposed_not_approved"]
    assert goals["threshold_authority"] == "PROPOSAL_ONLY_NOT_PM_APPROVED"
    assert goals["mobile_reference_width"] == 360
    assert goals["proposed_cta_rendered_font_min_display_px"] == 16
    assert goals["proposed_safe_frame_bottom_inset_min_display_px"] == 12
    assert goals["proposed_cta_foreground_background_contrast_min"] == 4.5
    assert M["candidates"]["A_EDITORIAL_CENTER"]["proposed_min_font_pass"] is False
    assert all(
        not candidate["proposed_min_bottom_inset_pass"]
        for candidate in M["candidates"].values()
    )
    assert all(candidate["proposed_min_contrast_pass"]
               for candidate in M["candidates"].values())


@pytest.mark.parametrize("name,font,inset", (
    ("A_EDITORIAL_CENTER",15.67,2.0),
    ("B_EDITORIAL_LEFT",16.33,2.0),
    ("C_CONTRAST_ACTION",16.67,1.33),
))
def test_a50d_actual_360_values_not_rounded_to_pass(name,font,inset):
    measured = M["candidates"][name]
    assert measured["cta_font_px_on_360"] == font
    assert measured["safe_frame_bottom_inset_360"] == inset
    assert measured["cta_to_unverified_product_target_1080"] in (15,17)


def test_a50d_declared_proposal_cannot_authorize_implementation():
    assert C["document_type"] == "DRAFT_REVIEW_ONLY_NON_EXECUTABLE"
    assert C["approval_state"] == "DRAFT_NOT_APPROVED"
    assert C["a5_1_implementation_authorized"] is False
    assert C["owner_pm_signed"] is False
    assert C["owner_image24_signoff"] is None
    assert C["pm_signoff"] is None
    for key in ("selected_profile","profile_id","profile_version",
                "profile_json_sha256","image_owner_source_commit",
                "effective_policy_epoch"):
        assert C[key] is None
    assert C["binding_target"]["layout_boxes_ltrb"] is None
    assert C["binding_target"]["cta_placement"] == "image"
    assert C["binding_target"]["cta_expected_render_count"] == 1


def test_a50d_font_candidates_are_license_sources_not_bundled_binaries():
    f = C["commercial_font"]
    for key in ("family","weight","file_sha256","license_evidence_sha256"):
        assert f[key] is None
    assert f["server_runtime_distribution_cleared"] is False
    candidates = f["candidates_for_legal_review_not_adopted"]
    assert {x["family"] for x in candidates} == {
        "Pretendard","Noto Sans CJK KR"
    }
    assert all(x["status"] == "UPSTREAM_LICENSE_FOUND_NO_PINNED_FONT_BINARY"
               for x in candidates)
    assert all(x["license"].startswith("SIL-OFL-1.1") for x in candidates)
    assert all(x["publisher_license_url"].startswith("https://github.com/")
               for x in candidates)


def test_a50d_decision_rows_complete_and_have_zero_fake_signoffs():
    assert len(DECISIONS) == 9
    assert {x["decision_id"] for x in DECISIONS} == {
        f"D50-{i:02d}" for i in range(1,10)
    }
    assert DECISIONS[0]["status"] == "ALREADY_DECIDED_POLICY"
    assert DECISIONS[7]["status"] == "DECISION_PENDING_PM_OWNER"
    assert all("APPROVED" not in row["status"]
               for row in DECISIONS[1:])
    for row in DECISIONS:
        for key in ("selected_mock_sha256","exact_profile_json_sha256",
                    "approved_font_sha256","font_license_evidence_sha256",
                    "effective_policy_epoch","owner_commit_sha",
                    "image_owner_signoff_ref","pm_signoff_ref",
                    "approval_timestamp","decision_rationale"):
            assert row[key] == "", (row["decision_id"],key)


def test_a50d_discovered_existing_fe_pretendard_not_approved_for_server():
    proof=json.loads((E/"A50D_EXISTING_FE_PRETENDARD_LICENSE_CANDIDATE.json"
                     ).read_text("utf-8"))
    assert proof["contract"]=="IT_TEM_P03_A50D_FE_INSTALLED_PRETENDARD_FONT_CANDIDATE_DISCOVERY_V1"
    assert proof["installed_package_version"]==proof["locked_version"]=="1.3.9"
    assert proof["license_type"]=="OFL-1.1"
    assert proof["font_sha256"]=="3090ccde0442bb347aa7685d9ba8b17436a60682df6e8f92a9a670de14056e22"
    assert proof["license_sha256"]=="b04538c9abec39a3db75108cf0af0fd9c77032fe8aa2cf38345b4d250e98e38e"
    assert proof["lockfile_sha256"]==sha(ROOT/"app/package-lock.json")
    assert proof["qa_copy_supported_glyphs"]==proof["qa_copy_unique_glyphs"]==19
    assert proof["pillow_freetype_load_success"] is True
    for key in ("server_font_actual_production_selected","weight_policy_approved",
                "production_server_font_distribution_approved",
                "license_notice_redistribution_verified",
                "font_sha_signed_by_image_owner_pm",
                "a5_1_implementation_authorized",
                "font_file_copied_to_evidence"):
        assert proof[key] is False
    assert not any(x.suffix.lower() in (".ttf",".otf",".woff2")
                   for x in E.iterdir())


def test_a50d_legacy_and_gcp_work_protected():
    legacy = C["legacy_preservation"]
    assert legacy["existing_completed_job"] == "IMMUTABLE"
    assert legacy["in_flight_v2_job"] == "PRESERVE_FROZEN_V2"
    assert legacy["other_modes_and_ratios"] == "UNCHANGED"
    assert legacy["freeform_server_overlay"] == "FORBIDDEN"
    assert legacy["9x16_cta_policy"] == "DECISION_PENDING_PM_OWNER"
    assert legacy["automatic_migration"] == "FORBIDDEN"
    assert legacy["automatic_rebill_or_provider_retry"] == "FORBIDDEN"
    assert C["safety"] == {
        "paid_worker_authorization": "HOLD",
        "gcp_qa_deployment":"HOLD",
        "product_release":"NOT_RELEASE_READY",
    }


def test_a50d_pm_handoff_zip_has_only_mock_images_and_pending_decisions():
    from zipfile import ZipFile
    bundle=D/"handoffs/IT_TEM_P03_A50D_OWNER_PM_REVIEW_ONLY_20261110.zip"
    assert sha(bundle)=="fb8fb89a76a675b994aba9b62d4229a8ff715747b18486c998ea9ab41ef07eff"
    with ZipFile(bundle) as z:
        assert z.testzip() is None
        members=z.namelist()
        assert len(members)==18
        assert not any(x.lower().endswith(
            (".ttf",".otf",".woff",".woff2",".db",".sqlite",".env",".key"))
            for x in members)
        policy=json.loads(z.read("BUNDLE_CONDITIONS.json"))
        assert policy["owner_signoff"]==policy["pm_signoff"]=="MISSING"
        assert policy["profile_v3_implementation"]=="NOT_AUTHORIZED"
        assert policy["gcp_deploy"]==policy["paid_worker"]=="HOLD"
        assert policy["file_count"]==16
        manifest=z.read("SHA256_CONTENT_MANIFEST.txt").decode("utf8")
        assert hashlib.sha256(manifest.encode("utf8")).hexdigest() == policy[
            "content_manifest_sha256"]
        for line in manifest.splitlines():
            digest,name=line.split("  ",1)
            assert hashlib.sha256(z.read(name)).hexdigest()==digest
        assert "PROFILE_V3_DRAFT_NOT_APPROVED.json" in members
        assert "VISUALS/00_ORIGINAL_AND_A_B_C_4UP.png" in members


def test_a50d_written_owner_pm_decision_packet_not_human_acceptance():
    text = (D/"BP18_A50D_OWNER_PM_PROFILE_V3_DECISION_PACKET_20261110.md"
            ).read_text("utf-8")
    for marker in ("SIGNATURES_0","A5_1_IMPLEMENTATION_HOLD",
                   "PENDING","DECISION_PENDING_PM_OWNER",
                   "1.33px","15.67px","A41_PRODUCT_CTA_01"):
        assert marker in text
    assert "4:5 Composed" in text
