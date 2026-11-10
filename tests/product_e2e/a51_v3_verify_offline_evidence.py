"""A4-1 read-only validation of an isolated Chrome QA Fixture run.

NO provider clients, GCP, migrations or modifications to SQLite/WAL/SHM.
Reads temporary local TestClient equivalent state; no customer assets.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

from PIL import Image

def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()

def open_ro(p: Path) -> sqlite3.Connection:
    assert p.is_file(), f"MISSING_DB:{p.name}"
    c = sqlite3.connect(f"{p.resolve().as_uri()}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA query_only=ON")
    return c

def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--runtime-root",type=Path,required=True)
    parser.add_argument("--evidence-dir",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--profile",choices=("A","C"),required=True)
    ns=parser.parse_args()
    root=ns.runtime_root.resolve(strict=True)
    ev=ns.evidence_dir.resolve(strict=True)
    trace=json.loads((ev/"browser_trace.json").read_text())
    assert trace["contract"]=="IT_TEM_A51_V3_OFFICIAL_REACT_CHROME_FIXTURE_V1"
    assert trace["qa_fixture"] is True and trace["actual_react_app"] is True
    assert trace["a51_profile"]==ns.profile
    assert trace["browser_errors"] == [] and trace["exfiltration_attempts"] == []
    assert trace["network_external_post_count"] == 0
    assert trace["final_state"]=="COMPLETED"
    assert len(trace["steps"]) >= 15
    assert trace["image_attempt_version"] == 2
    jid=trace["completed_job_id"]
    assert len(jid)==32 and all(x in "0123456789abcdef" for x in jid)
    dbpath=root/"live"/"live.sqlite"
    with open_ro(dbpath) as db:
        rows=db.execute("SELECT * FROM live_jobs WHERE job_id=?",(jid,)).fetchall()
        assert len(rows)==1
        j=dict(rows[0])
        assert j["mode"]=="OFFLINE_FIXTURE" and j["state"]=="COMPLETED"
        assert j["generation"]==3
        snapshot=json.loads(j["input_json"])
        assert snapshot["image_size"]=="4:5" and snapshot["generation_mode"]=="composed"
        assets=snapshot["ordered_asset_hashes"]
        assert len([a for a in assets if a["role"]=="product"])==2
        assert not [a for a in assets if a["role"]=="reference"]
        attempts=[dict(row) for row in db.execute(
            "SELECT * FROM live_image_attempts WHERE job_id=? ORDER BY attempt_version",(jid,))]
        assert len(attempts)==2
        assert [r["attempt_version"] for r in attempts]==[1,2]
        assert [r["state"] for r in attempts]==["REJECTED","COMPLETED"]
        assert attempts[0]["candidate_sha"]!=attempts[1]["candidate_sha"]
        assert attempts[0]["approval_sha"]==attempts[1]["approval_sha"]==j["approval_sha"]
        assert attempts[0]["prompt_sha"]==attempts[1]["prompt_sha"]
        assert attempts[1]["candidate_sha"]==j["image_sha"]
        assert attempts[0]["attempt_id"]!=attempts[1]["attempt_id"]
        assert attempts[1]["request_key"] not in ("baseline","historical-v1")
        approve_bindings=db.execute(
            "SELECT COUNT(*) FROM live_copy_policy_bindings WHERE job_id=?",(jid,)).fetchone()[0]
        prompt_bindings=db.execute(
            "SELECT COUNT(*) FROM live_prompt_context_bindings WHERE job_id=?",(jid,)).fetchone()[0]
        assert approve_bindings==prompt_bindings==1
        cp=json.loads(j["copy_json"])
        template=db.execute(
            "SELECT * FROM live_job_templates WHERE job_id=?",(jid,)
        ).fetchone()
        assert template is not None
        from demo_staging.live.a5_beta_profile_v3 import (
            PROFILE_PREFIX,PROFILE_VERSION,PROPOSAL_EPOCH,build_proposal,
            PRETENDARD_139_SHA,GEOMETRY
        )
        expected=build_proposal(ns.profile)
        assert template["profile_id"]==PROFILE_PREFIX+ns.profile
        assert template["profile_version"]==PROFILE_VERSION
        assert template["layout_sha"]==hashlib.sha256(
            json.dumps(expected["layout"],sort_keys=True,ensure_ascii=False,
                       separators=(",",":")).encode("utf-8")).hexdigest()
        zone=json.loads(template["safe_zone_json"])
        assert zone["policy_epoch"]==PROPOSAL_EPOCH
        assert zone["real_provider_permitted"] is False
    with open_ro(root/"live"/"queue.sqlite") as db:
        queue_count=db.execute("SELECT COUNT(*) FROM queued_ops").fetchone()[0]
    with open_ro(root/"live"/"cost.sqlite") as db:
        cost_count=db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
    assert queue_count==cost_count==0

    outputs=root/"live"/"outputs"/jid
    final_png=ev/"ad_1080x1350.png"
    final_caption=ev/"caption.txt"
    assert sha(final_png)==sha(outputs/"final.png")==j["final_sha"]==trace["final_sha"]
    assert sha(final_caption)==sha(outputs/"caption.txt")==j["caption_sha"]==trace["caption_sha"]
    assert final_caption.read_text(encoding="utf-8")
    # Caption exports approved long-form caption + hashtags, not headline/CTA.
    # On-image copy glyph fidelity is separately checked against receipt text hashes.
    caption_text=final_caption.read_text(encoding="utf-8")
    assert cp["caption"] in caption_text
    assert all(tag in caption_text for tag in cp["hashtags"])
    with Image.open(final_png) as img:
        assert img.format=="PNG" and img.size==(1080,1350)
    assert sha(outputs/"image.png")==j["image_sha"]
    archived=outputs/"attempts"/f"v1-{attempts[0]['candidate_sha']}.png"
    assert sha(archived)==attempts[0]["candidate_sha"]
    receipt_p=outputs/"receipt.json"
    receipt=json.loads(receipt_p.read_text())
    assert receipt["provider_calls"] == 0
    assert isinstance(receipt.get("font_sha256"),str)
    assert receipt.get("placements",{}).get("headline")
    assert receipt.get("placements",{}).get("subline")
    assert receipt.get("profile_id")==PROFILE_PREFIX+ns.profile
    assert receipt.get("profile_version")==PROFILE_VERSION
    assert receipt.get("profile_policy_epoch")==PROPOSAL_EPOCH
    assert receipt.get("profile_layout_sha256")==template["layout_sha"]
    assert receipt.get("font_sha256")==PRETENDARD_139_SHA
    assert receipt.get("beta_only") is True
    assert receipt.get("owner_pm_signed") is False
    assert receipt.get("protection_evidence")=="SYNTHETIC_TARGET_ONLY_REAL_PRODUCT_NOT_AUDITED"
    assert set(receipt.get("placements",{}))=={"headline","subline","cta"}
    for field in ("headline","subline","cta"):
        placement=receipt["placements"][field]
        assert placement["text_sha256"]==hashlib.sha256(
            cp["ad_copy"][field].encode("utf-8")).hexdigest()
        assert placement["region"]==list(GEOMETRY[ns.profile][field])
        assert placement["line_count"]==1
        assert placement["ink_boxes"]
    image_cta_on_png=("cta" not in receipt.get("omitted_image_fields",[]) and
        "cta" in receipt.get("placements",{}))
    assert receipt.get("cta_placement")=="image"
    assert image_cta_on_png
    assert receipt.get("omitted_image_fields")==[]
    screens=trace["screenshots"]
    assert len(screens) >= 10
    for s in screens:
        f=ev/s["filename"]
        assert f.is_file()
        assert sha(f)==s["sha256"],s["filename"]
    assert all(s["state"] in (None,"COPY_REVIEW_REQUIRED","IMAGE_REVIEW_REQUIRED",
        "IMAGE_REJECTED","COMPLETED") for s in trace["steps"])
    summary={
      "contract":"IT_TEM_A51_V3_OFFLINE_FIXTURE_EVIDENCE_VERIFICATION_V1",
      "source_commit":trace["source_commit"],
      "browser_flow_gate":"PASS",
      "browser_actual_application":"OFFICIAL_REACT_FE",
      "provider_calls":0,
      "provider_e2e":"NOT_AUDITED",
      "human_pm_visual_acceptance":"PENDING",
      "scenario":"A5-S01_COMPOSED_4_5_PROFILE_"+ns.profile,
      "profile_id":PROFILE_PREFIX+ns.profile,
      "policy_epoch":PROPOSAL_EPOCH,
      "real_product_protection":"NOT_AUDITED",
      "job_id":jid,
      "actor":"alice",
      "job_state":"COMPLETED",
      "mode":"OFFLINE_FIXTURE",
      "generation":j["generation"],
      "input_sha":j["input_sha"],
      "copy_sha":j["copy_sha"],
      "review_sha":j["review_sha"],
      "approval_sha":j["approval_sha"],
      "prompt_sha":attempts[1]["prompt_sha"],
      "image_attempt_ids":[row["attempt_id"] for row in attempts],
      "image_attempt_states":[row["state"] for row in attempts],
      "image_attempt_versions":[row["attempt_version"] for row in attempts],
      "image_attempt_shas":[row["candidate_sha"] for row in attempts],
      "final_png_sha256":j["final_sha"],
      "caption_sha256":j["caption_sha"],
      "composition_receipt_sha256":sha(receipt_p),
      "download_verified":True,
      "final_png_pixels":[1080,1350],
      "browser_screenshot_count":len(screens),
      "browser_trace_sha256":sha(ev/"browser_trace.json"),
      "queue_rows":queue_count,"cost_attempt_rows":cost_count,
      "copy_policy_bindings":approve_bindings,
      "prompt_context_bindings":prompt_bindings,
      "product_quality": {
        "4x5_composed_image_cta_required":True,
        "4x5_image_cta_present":image_cta_on_png,
        "gate":"ON_IMAGE_CTA_FIXTURE_PASS_REAL_PRODUCT_FIDELITY_HOLD",
        "finding":"A51_V3_ACTUAL_COMPOSITION_RUNTIMECOPY_SHA_PASS",
        "actual_owner_layout":"cta_placement=image",
        "receipt_omitted_image_fields":receipt["omitted_image_fields"],
        "reason":"On-image CTA actually rendered in approved offline fixture. No real product mask or signed owner/PM commercial visual acceptance."
      },
      "gcp_qa_gate":"HOLD","paid_worker":"HOLD",
      "release":"NOT_RELEASE_READY"
    }
    ns.output.write_text(json.dumps(summary,ensure_ascii=False,indent=2,sort_keys=True)+"\n")
    print("A51_OFFICIAL_BROWSER_FLOW_PASS")
    print("A51_V3_DOWNLOAD_SHA_AND_PIXELS_PASS")
    print("A51_ATTEMPT_VERSION_1_REJECTED_2_COMPLETED")
    print("A51_QUEUE_COST_PROVIDER_0")
    print("A51_ON_IMAGE_CTA_FIXTURE_PASS",summary["product_quality"]["finding"])
    print("A51_REAL_PRODUCT_BRAND_AND_FINAL_PROFILE_ACCEPTANCE_HOLD")
    print("A51_SUMMARY_SHA256",sha(ns.output))

if __name__=="__main__":
    main()
