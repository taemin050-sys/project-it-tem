"""Read-only revision attribution; no app, providers, credentials or network."""
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

from demo_staging.live.contracts import LiveGateError, digest
from demo_staging.live.revision_costs import revision_cost_summary

ACTOR, OTHER = "bp18_b_owner", "bp18_b_other"
JOB, CHILD = "1"*32, "2"*32


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def flow_at(tmp_path):
    root = tmp_path/"live";root.mkdir()
    cost = root/"cost.sqlite"
    with sqlite3.connect(cost) as c:
        c.execute("CREATE TABLE attempts(id TEXT PRIMARY KEY,actor TEXT,job_id TEXT,stage TEXT,payload_hash TEXT,status TEXT,billing_unknown INTEGER,receipt TEXT,created_at TEXT)")
    return SimpleNamespace(root=root,cost=SimpleNamespace(filename=cost))


def receipt(model="fixture-model"):
    return {"provider":"openai","model":model,"provider_response_id":"resp_fixture",
        "usage":{"input_tokens":7,"output_tokens":3,"total_tokens":10},"billing_status":"UNPRICED_RESERVATION_HELD"}


def attempt(flow, *, id, actor=ACTOR, job=JOB, stage="image", payload=None, state="SUCCEEDED_USAGE_UNPRICED", usage=None):
    with sqlite3.connect(flow.cost.filename) as c:
        c.execute("INSERT INTO attempts VALUES(?,?,?,?,?,?,?,?,?)",(id,actor,job,stage,digest(payload or {"initial":id}),state,
            int(state=="BILLING_UNKNOWN"),canonical(usage if usage is not None else receipt()) if state=="SUCCEEDED_USAGE_UNPRICED" else None,"2026-11-12"))


def image_revision(flow, *, id="a"*32, actor=ACTOR, job=CHILD, state="REVIEW_REQUIRED"):
    source={"protocol":"FREEFORM_TEXT_EDIT_V1","actor":actor,"job_id":job,"source_image_sha":"a"*64,
            "copy_sha":"b"*64,"approval_sha":"c"*64,"review_sha":"d"*64}
    payload={"source_context":source,"expected_image_sha":source["source_image_sha"],"expected_copy_sha":source["copy_sha"],
             "expected_approval_sha":source["approval_sha"],"request_key":"f"*32,"field":"subline","observed_text":"자분하게"}
    request_sha=digest(payload)
    with sqlite3.connect(flow.root/"image_corrections.sqlite") as c:
        c.execute("CREATE TABLE IF NOT EXISTS image_corrections(correction_id TEXT,actor TEXT,job_id TEXT,request_key TEXT,request_sha TEXT,context_sha TEXT,payload_json TEXT,state TEXT)")
        c.execute("INSERT INTO image_corrections VALUES(?,?,?,?,?,?,?,?)",(id,actor,job,payload["request_key"],request_sha,digest(source),canonical(payload),state))
    return {"protocol":"FREEFORM_TEXT_EDIT_V1","correction_id":id,"request_sha":request_sha}


def copy_revision(flow, *, id="e"*32, actor=ACTOR, job=JOB, state="COPY_REVIEW_REQUIRED", publish=True, model="fixture-model"):
    source={"protocol":"COMPOSED_COPY_EDIT_V1","actor":actor,"job_id":job,"image_sha":"a"*64,
            "copy_sha":"b"*64,"approval_sha":"c"*64,"review_sha":"d"*64}
    copy={"ad_copy":{"headline":"수정 헤드","subline":"차분하게","cta":"만나기"},"caption":"본문","hashtags":[]}
    request={"expected_image_sha":source["image_sha"],"expected_copy_sha":source["copy_sha"],"expected_approval_sha":source["approval_sha"],
             "ad_copy":copy["ad_copy"],"request_key":"f"*32}
    evidence={"attempt_id":"6"*32,"receipt_sha":digest(receipt(model)),"response_model":model} if publish else None
    row={"protocol":"COMPOSED_COPY_EDIT_V1","edit_id":id,"actor":actor,"job_id":job,"state":state,
         "request_key":request["request_key"],"request_sha":digest(request),"source_context":source,"source_context_sha":digest(source),
         "copy":copy,"copy_sha":digest(copy),"report":{"llm_review":{"model":model}} if publish else {},"cost_receipt":evidence,
         "review_model":model}
    with sqlite3.connect(flow.root/"composed_copy_edits.sqlite") as c:
        c.execute("CREATE TABLE IF NOT EXISTS composed_copy_edits(edit_id TEXT,actor TEXT,job_id TEXT,request_key TEXT,request_sha TEXT,state TEXT,record_json TEXT)")
        c.execute("INSERT INTO composed_copy_edits VALUES(?,?,?,?,?,?,?)",(id,actor,job,request["request_key"],row["request_sha"],state,canonical(row)))
    return {"protocol":"COMPOSED_COPY_EDIT_V1","edit_id":id,"source_context_sha":digest(source),"copy_sha":digest(copy),"model":model}


def bytes_under(root):
    return {str(p.relative_to(root)):sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}


def test_missing_optional_stores_are_not_created_and_zero_is_not_usd(tmp_path):
    flow=flow_at(tmp_path);before=bytes_under(flow.root)
    summary=revision_cost_summary(flow,ACTOR,JOB)
    assert summary["provider_attempt_count"]==0 and summary["actual_usd"] is None
    assert summary["revisions"]==[] and summary["excluded_attempt_ids"]==[]
    assert bytes_under(flow.root)==before


def test_original_5_text_1_image_each_and_revision_2_images_1_review_do_not_double_count(tmp_path):
    flow=flow_at(tmp_path)
    for index,stage in enumerate(("vision","research","copy","copy_review","image_prompt")):
        attempt(flow,id=str(index)*32,stage=stage)
    attempt(flow,id="7"*32)
    attempt(flow,id="8"*32,job=CHILD)
    one=image_revision(flow,id="a"*32);two=image_revision(flow,id="b"*32)
    attempt(flow,id="9"*32,job=CHILD,payload=one)
    attempt(flow,id="a"*32,job=CHILD,payload=two)
    manual=copy_revision(flow)
    attempt(flow,id="6"*32,stage="copy_review",payload=manual)
    before=bytes_under(flow.root)
    parent=revision_cost_summary(flow,ACTOR,JOB);child=revision_cost_summary(flow,ACTOR,CHILD)
    assert parent["excluded_attempt_ids"]==["6"*32] and parent["provider_attempt_count"]==1
    assert set(child["excluded_attempt_ids"])=={"9"*32,"a"*32} and child["provider_attempt_count"]==2
    assert parent["revisions"][0]["kind"]=="composed_copy_edit"
    assert {item["kind"] for item in child["revisions"]}=={"image_correction"}
    with sqlite3.connect(flow.cost.filename) as c:
        rows=c.execute("SELECT id,job_id,stage FROM attempts").fetchall()
    excluded=set(parent["excluded_attempt_ids"]+child["excluded_attempt_ids"])
    base=[row for row in rows if row[0] not in excluded]
    assert sum(row[2]!="image" for row in base)==5
    assert sum(row[2]=="image" for row in base)==2
    assert len(base)+parent["provider_attempt_count"]+child["provider_attempt_count"]==len(rows)==10
    assert all(row["actual_usd"] is None for row in parent["attempts"]+child["attempts"])
    assert bytes_under(flow.root)==before


@pytest.mark.parametrize("state",["DISPATCHED","BILLING_UNKNOWN"])
def test_prepublication_uncertain_calls_are_attributed_without_hidden_retry(tmp_path,state):
    flow=flow_at(tmp_path)
    image=image_revision(flow,state="RUNNING")
    manual=copy_revision(flow,state="RUNNING",publish=False)
    attempt(flow,id="a"*32,job=CHILD,payload=image,state=state)
    attempt(flow,id="6"*32,stage="copy_review",payload=manual,state=state)
    for job in (JOB,CHILD):
        summary=revision_cost_summary(flow,ACTOR,job)
        assert summary["provider_attempt_count"]==1
        assert summary["status"]==("BILLING_UNKNOWN" if state=="BILLING_UNKNOWN" else "AWAITING_RECEIPT")
        assert summary["attempts"][0]["usage"] is None and summary["actual_usd"] is None
        assert len(summary["excluded_attempt_ids"])==1


def test_cross_actor_or_cross_job_is_never_classified_or_leaked(tmp_path):
    flow=flow_at(tmp_path)
    fingerprint=image_revision(flow)
    attempt(flow,id="a"*32,job=CHILD,payload=fingerprint)
    attempt(flow,id="b"*32,actor=OTHER,job=CHILD,payload=fingerprint,state="BILLING_UNKNOWN")
    other=revision_cost_summary(flow,OTHER,CHILD)
    assert other["revisions"]==[] and other["excluded_attempt_ids"]==[]
    assert other["unclassified_uncertain_attempt_count"]==1
    assert revision_cost_summary(flow,ACTOR,JOB)["excluded_attempt_ids"]==[]
    own=revision_cost_summary(flow,ACTOR,CHILD)
    assert own["excluded_attempt_ids"]==["a"*32] and own["unclassified_uncertain_attempt_count"]==0


def test_receipt_fingerprint_or_context_tampering_fails_closed(tmp_path):
    flow=flow_at(tmp_path);fingerprint=copy_revision(flow)
    attempt(flow,id="6"*32,stage="copy_review",payload=fingerprint)
    with sqlite3.connect(flow.cost.filename) as c:
        c.execute("UPDATE attempts SET payload_hash=? WHERE id=?",("0"*64,"6"*32))
    with pytest.raises(LiveGateError,match="CLASSIFICATION_INTEGRITY"):
        revision_cost_summary(flow,ACTOR,JOB)
    with sqlite3.connect(flow.root/"composed_copy_edits.sqlite") as c:
        record=json.loads(c.execute("SELECT record_json FROM composed_copy_edits").fetchone()[0]);record["actor"]=OTHER
        c.execute("UPDATE composed_copy_edits SET record_json=?",(canonical(record),))
    with pytest.raises(LiveGateError,match="CLASSIFICATION_INTEGRITY"):
        revision_cost_summary(flow,ACTOR,JOB)


def test_sanitized_usage_does_not_expose_raw_payload_secrets_or_fake_actual_usd(tmp_path):
    flow=flow_at(tmp_path);fingerprint=image_revision(flow)
    usage=receipt();usage["usage"].update({"injected<key>":999,"negative":-1,"bool":True});usage["raw_secret"]="must-not-leave"
    attempt(flow,id="a"*32,job=CHILD,payload=fingerprint,usage=usage)
    result=revision_cost_summary(flow,ACTOR,CHILD)
    assert "must-not-leave" not in canonical(result)
    assert result["attempts"][0]["usage"]=={"input_tokens":7,"output_tokens":3,"total_tokens":10}
    assert result["actual_usd"] is None and result["status"]=="UNPRICED"


def test_unpublished_unknown_without_a_joinable_cost_row_stays_unknown(tmp_path):
    flow=flow_at(tmp_path)
    copy_revision(flow,state="BILLING_UNKNOWN",publish=False)
    result=revision_cost_summary(flow,ACTOR,JOB)
    assert result["status"]=="BILLING_UNKNOWN"
    assert result["classification_status"]=="PENDING_LEDGER_BINDING"
    assert result["revisions"][0]["status"]=="BILLING_UNKNOWN"
    assert result["actual_usd"] is None and result["excluded_attempt_ids"]==[]
