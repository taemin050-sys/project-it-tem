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
    ns=parser.parse_args()
    root=ns.runtime_root.resolve(strict=True)
    ev=ns.evidence_dir.resolve(strict=True)
    trace=json.loads((ev/"browser_trace.json").read_text())
    assert trace["contract"]=="IT_TEM_A42_OFFICIAL_REACT_CHROME_FIXTURE_V1"
    mode,ratio=trace["generation_mode"],trace["image_size"]
    cases={("composed","3:4"):"A4-S02",("composed","9:16"):"A4-S03",
           ("freeform","4:5"):"A4-S04",("freeform","3:4"):"A4-S05",
           ("freeform","9:16"):"A4-S06"}
    assert cases.get((mode,ratio))==trace["scenario_id"]
    dimensions={"3:4":(1080,1440),"4:5":(1080,1350),"9:16":(1080,1920)}
    assert trace["qa_fixture"] is True and trace["actual_react_app"] is True
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
        assert snapshot["image_size"]==ratio and snapshot["generation_mode"]==mode
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
    with open_ro(root/"live"/"queue.sqlite") as db:
        queue_count=db.execute("SELECT COUNT(*) FROM queued_ops").fetchone()[0]
    with open_ro(root/"live"/"cost.sqlite") as db:
        cost_count=db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
    assert queue_count==cost_count==0

    outputs=root/"live"/"outputs"/jid
    final_png=ev/f"ad_{dimensions[ratio][0]}x{dimensions[ratio][1]}.png"
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
        assert img.format=="PNG" and img.size==dimensions[ratio]
    assert sha(outputs/"image.png")==j["image_sha"]
    archived=outputs/"attempts"/f"v1-{attempts[0]['candidate_sha']}.png"
    assert sha(archived)==attempts[0]["candidate_sha"]
    receipt_p=outputs/"receipt.json"
    receipt=json.loads(receipt_p.read_text())
    assert receipt["provider_calls"] == 0
    # Composition v2 legacy receipts omit the explicit generation_mode, which
    # canonically denotes composed; Freeform export binds it explicitly.
    assert receipt.get("generation_mode","composed") == mode
    if mode=="freeform":
        assert receipt["rendering"]=="provider_drawn_text"
        assert receipt["source_image_sha256"]==j["image_sha"]
        assert receipt["image_sha256"]==j["final_sha"]
        assert "font_sha256" not in receipt
        assert "placements" not in receipt
        assert receipt["needs_manual_check"] is True
        assert "GENERATED_COPY_REQUIRES_REVIEW" in receipt["warnings"]
        quality_issue="FREEFORM_FIXTURE_CANNOT_CERTIFY_GENERATED_KOREAN_COPY"
    else:
        assert isinstance(receipt.get("font_sha256"),str)
        assert receipt.get("placements",{}).get("headline")
        assert receipt.get("placements",{}).get("subline")
        for field in ("headline", "subline"):
            assert (receipt["placements"][field]["text_sha256"] ==
                    hashlib.sha256(cp["ad_copy"][field].encode("utf-8")).hexdigest())
        if ratio=="3:4":
            assert receipt["cta_placement"]=="image"
            assert receipt.get("omitted_image_fields")==[]
            assert receipt.get("placements",{}).get("cta")
            assert receipt["placements"]["cta"]["text_sha256"] == hashlib.sha256(
                cp["ad_copy"]["cta"].encode("utf-8")).hexdigest()
            quality_issue="OWNER_PM_3X4_VISUAL_DESIGN_REVIEW_PENDING"
        else:
            assert ratio=="9:16"
            # Owner/PM policy unresolved, NOT a pass or a defect workaround.
            assert receipt["cta_placement"]=="platform"
            assert receipt["omitted_image_fields"]==["cta"]
            quality_issue="DECISION_PENDING_PM_OWNER_9X16_CTA"
    screens=trace["screenshots"]
    assert len(screens) >= 10
    for s in screens:
        f=ev/s["filename"]
        assert f.is_file()
        assert sha(f)==s["sha256"],s["filename"]
    assert all(s["state"] in (None,"COPY_REVIEW_REQUIRED","IMAGE_REVIEW_REQUIRED",
        "IMAGE_REJECTED","COMPLETED") for s in trace["steps"])
    summary={
      "contract":"IT_TEM_A42_OFFLINE_FIXTURE_EVIDENCE_VERIFICATION_V1",
      "scenario_id":trace["scenario_id"],
      "source_commit":trace["source_commit"],
      "browser_flow_gate":"PASS",
      "browser_actual_application":"OFFICIAL_REACT_FE",
      "provider_calls":0,
      "provider_e2e":"NOT_AUDITED",
      "human_pm_visual_acceptance":"PENDING",
      "scenario":trace["scenario_id"],
      "generation_mode":mode,"image_size":ratio,
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
      "final_png_pixels":list(dimensions[ratio]),
      "browser_screenshot_count":len(screens),
      "browser_trace_sha256":sha(ev/"browser_trace.json"),
      "queue_rows":queue_count,"cost_attempt_rows":cost_count,
      "copy_policy_bindings":approve_bindings,
      "prompt_context_bindings":prompt_bindings,
      "product_quality": {
        "gate":"HOLD",
        "finding":quality_issue,
        "receipt_omitted_image_fields":receipt.get("omitted_image_fields",[]),
        "reason":"Browser fixture verifies functionality only. Freeform cannot prove model-drawn typography; 9:16 CTA owner/PM undecided; Composed 3:4 still needs visual/human assessment."
      },
      "gcp_qa_gate":"HOLD","paid_worker":"HOLD",
      "release":"NOT_RELEASE_READY"
    }
    ns.output.write_text(json.dumps(summary,ensure_ascii=False,indent=2,sort_keys=True)+"\n")
    print("A42_OFFICIAL_BROWSER_FLOW_PASS",trace["scenario_id"])
    print("A42_DOWNLOAD_SHA_AND_PIXELS_PASS",dimensions[ratio])
    print("A42_ATTEMPT_VERSION_1_REJECTED_2_COMPLETED")
    print("A42_QUEUE_COST_PROVIDER_0")
    print("A42_PRODUCT_QUALITY_HOLD",quality_issue)
    print("A42_SUMMARY_SHA256",sha(ns.output))

if __name__=="__main__":
    main()
