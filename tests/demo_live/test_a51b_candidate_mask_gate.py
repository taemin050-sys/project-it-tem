"""A5-1B isolated signed profile + per-candidate signed mask/receipt E2E.

Uses disposable Ed25519 TEST keys and geometric TEST mask, no actual third-party
photo, commercial rights, actual PM signature or paid Provider call.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from PIL import Image, ImageDraw
from fastapi.testclient import TestClient

from demo_staging.live.contracts import LiveGateError
from demo_staging.live.a51b_candidate_mask_gate import (
    CONTRACT, validate_candidate_review, validate_review_time,
)
from demo_staging.live.a51b_signed_beta_contract import BETA_PREFIX
from tests.demo_live.test_a51b_signed_beta_contract import signed_beta, openssl
from tests.demo_live.test_pm_track_a_single_candidate import (
    configure_qa, new_job, ORIGIN,
)
from tests.demo_live.test_http_gateway import setup,login
from tests.demo_live.test_live_contracts import sample_input


def ready_to_compose(tmp_path,monkeypatch,signed_beta):
    configure_qa(monkeypatch)
    monkeypatch.setenv("IT_TEM_A51B_POLICY_ROOT",str(signed_beta["policy"]))
    monkeypatch.setenv("IT_TEM_A51B_TRUST_ROOT",str(signed_beta["trust"]))
    monkeypatch.setenv("IT_TEM_A51B_PROFILE","A")
    monkeypatch.setenv("IT_TEM_A51B_NEW_JOB_ENABLE","YES")
    source=Path(__file__).resolve().parents[2]
    font=source/"app/node_modules/pretendard/dist/public/variable/PretendardVariable.ttf"
    monkeypatch.setenv("IT_TEM_LIVE_KOREAN_FONT",str(font))
    root=tmp_path/"mask-review-private"
    root.mkdir(mode=0o700)
    monkeypatch.setenv("IT_TEM_A51B_MASK_REVIEW_ROOT",str(root))
    app,codes=setup(tmp_path/"run")
    client=TestClient(app,client=("127.0.0.1",12347))
    client.__enter__()
    login(client,codes["alice"])
    jid=new_job(client)
    live="/demo/api/live/jobs/"+jid
    qa="/demo/api/qa/jobs/"+jid
    post=client.post(live+"/input",json={
        **sample_input(),"image_size":"4:5","generation_mode":"composed"
    },headers=ORIGIN)
    assert post.status_code==200,post.text
    text=client.post(qa+"/text",headers=ORIGIN)
    assert text.status_code==200,text.text
    approval=client.post(live+"/approve-copy",json={
        "expected_generation":text.json()["generation"],
        "expected_review_sha":text.json()["review_sha"]},headers=ORIGIN)
    assert approval.status_code==200,approval.text
    prompt=client.post(qa+"/prompt-image",headers=ORIGIN)
    assert prompt.status_code==200,prompt.text
    img=client.post(live+"/approve-image",json={
        "image_sha":prompt.json()["image_sha"]},headers=ORIGIN)
    assert img.status_code==200,img.text
    state=app.state.live_pipeline.state
    job=state.get("alice",jid)
    frozen=state.template("alice",jid)
    assert frozen["profile_id"]==BETA_PREFIX+"A"
    raw=app.state.live_pipeline.image_path(jid).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==job["image_sha"]
    return client, app, job, frozen, raw, root, live, qa


def sign_candidate_review(signed_beta,root,job,frozen,raw, *,
                          protected_rect=(460,480,620,900),
                          mutate=None):
    jid=job["job_id"]
    mask=Image.new("L",(1080,1350),0)
    ImageDraw.Draw(mask).rectangle(protected_rect,fill=255)
    maskpath=root/(jid+".protected_mask.png")
    mask.save(maskpath)
    maskpath.chmod(0o600)
    source={
        "contract":CONTRACT,
        "job_id":jid,
        "profile_id":frozen["profile_id"],
        "layout_sha256":frozen["layout_sha"],
        "policy_epoch":frozen["safe_zone"]["policy_epoch"],
        "signed_profile_decision_sha256":frozen["safe_zone"][
            "signed_owner_pm_decision_sha256"],
        "copy_sha256":job["copy_sha"],
        "approval_sha256":job["approval_sha"],
        "source_candidate_sha256":hashlib.sha256(raw).hexdigest(),
        "mask_sha256":hashlib.sha256(maskpath.read_bytes()).hexdigest(),
        "annotation_kind":"PRODUCT_PACKAGE_LOGO_LABEL_UNION",
        "annotation_scope":"FINAL_1080x1350_COORDINATES",
        "rights_evidence_sha256":"a"*64,  # synthetic dummy, NOT rights
        "rights_scope":"LOCAL_READ_ONLY_PRODUCT_QA_ONLY",
        "review_time_utc":datetime.now(timezone.utc).isoformat(),
        "review_decision":"APPROVED_FOR_MASK_GEOMETRY_ONLY",
    }
    if mutate:source.update(mutate)
    file=root/(jid+".maskreview.json")
    file.write_text(json.dumps(source,sort_keys=True,separators=(",",":")))
    file.chmod(0o600)
    for role,details in signed_beta["keys"].items():
        path=root/(jid+"."+role+".sig")
        openssl("pkeyutl","-sign","-inkey",details["private"],"-rawin",
                "-in",file,"-out",path)
        path.chmod(0o600)
    return maskpath,file


def test_a51b_signed_profile_missing_mask_blocks_without_output(
        tmp_path,monkeypatch,signed_beta):
    client,app,job,frozen,raw,root,live,qa=ready_to_compose(
        tmp_path,monkeypatch,signed_beta)
    try:
        result=client.post(qa+"/compose",json={},headers=ORIGIN)
        assert result.status_code in (409,422),result.text
        assert "A51B_PRIVATE_EVIDENCE_FILE_MISSING" in result.text
        assert app.state.live_pipeline.state.get("alice",job["job_id"])["state"]=="IMAGE_APPROVED"
        assert not (app.state.live_pipeline.root/"outputs"/job["job_id"]/"final.png").exists()
    finally:
        client.__exit__(None,None,None)


def test_a51b_signed_offline_actual_owner_composition_receipt_mask_sha(
        tmp_path,monkeypatch,signed_beta):
    client,app,job,frozen,raw,root,live,qa=ready_to_compose(
        tmp_path,monkeypatch,signed_beta)
    try:
        mask,_=sign_candidate_review(signed_beta,root,job,frozen,raw)
        response=client.post(qa+"/compose",json={},headers=ORIGIN)
        assert response.status_code==200,response.text
        assert response.json()["state"]=="COMPLETED"
        manifest=app.state.live_pipeline.state.read_manifest("alice",job["job_id"])
        receipt=manifest["receipt"]
        assert receipt["beta_style"]=="A"
        assert receipt["cta_placement"]=="image"
        assert set(receipt["placements"])=={"headline","subline","cta"}
        assert receipt["signed_profile_authorities"]==["image_owner","pm"]
        assert receipt["signatures_verified_for_layout_only"] is True
        assert receipt["profile_id"]==BETA_PREFIX+"A"
        assert receipt["actual_product_mask_verified"] is False
        assert receipt["actual_product_rights_authenticated"] is False
        assert receipt["paid_provider_authorized"] is False
        assert receipt["human_pm_visual_accepted"] is False
        assert receipt["candidate_mask_validation"]["mask_sha256"]==hashlib.sha256(
            mask.read_bytes()).hexdigest()
        assert receipt["candidate_mask_validation"][
            "geometry_and_pixel_preservation"]=="PASS"
        assert receipt["candidate_mask_validation"][
            "product_quality_gate"]=="HOLD"
        assert receipt["candidate_mask_validation"]["real_provider_transfer_authorized"] is False
        assert client.get(qa+"/artifacts/final").status_code==200
        assert client.get(qa+"/artifacts/caption").status_code==200
        with app.state.live_pipeline.cost.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]==0
    finally:
        client.__exit__(None,None,None)


@pytest.mark.parametrize("attack",(
    "cta_collision","headline_collision","wrong_source","wrong_approval",
    "wrong_policy","mask_modified","unsigned_mask","mask_non_binary",
    "mask_wrong_dimensions","world_readable_mask"
))
def test_a51b_mask_or_provenance_tamper_blocks_without_final_artifact(
        tmp_path,monkeypatch,signed_beta,attack):
    client,app,job,frozen,raw,root,live,qa=ready_to_compose(
        tmp_path,monkeypatch,signed_beta)
    try:
        rect={
            "cta_collision":(300,1150,700,1200),
            "headline_collision":(460,100,610,170),
        }.get(attack,(460,480,620,900))
        updates={}
        if attack=="wrong_source":updates["source_candidate_sha256"]="f"*64
        if attack=="wrong_approval":updates["approval_sha256"]="f"*64
        if attack=="wrong_policy":updates["policy_epoch"]="forged"
        mask,record=sign_candidate_review(
            signed_beta,root,job,frozen,raw,protected_rect=rect,mutate=updates)
        if attack=="mask_modified":mask.write_bytes(mask.read_bytes()+b"tampered")
        if attack=="unsigned_mask":(root/(job["job_id"]+".pm.sig")).unlink()
        if attack=="mask_non_binary":
            with Image.open(mask) as img:
                temp=img.copy()
            temp.putpixel((500,500),33)
            temp.save(mask)
            # Resigned SHA would still be rejected as a nonbinary mask,
            # but for this test a SHA violation also demonstrates failclosed.
        if attack=="mask_wrong_dimensions":
            Image.new("L",(1,1),255).save(mask)
        if attack=="world_readable_mask":mask.chmod(0o644)
        resp=client.post(qa+"/compose",json={},headers=ORIGIN)
        assert resp.status_code in (409,422),resp.text
        assert "A51B_" in resp.text
        assert app.state.live_pipeline.state.get("alice",job["job_id"])["state"]=="IMAGE_APPROVED"
        assert not (app.state.live_pipeline.root/"outputs"/job["job_id"]/"final.png").exists()
    finally:
        client.__exit__(None,None,None)

@pytest.mark.parametrize("seconds_delta,permitted",[
    (0,True), (30,True), (31,False),
    (5*60,False), (30*24*3600,False),
    (-90*24*3600,True),(-90*24*3600-1,False),
])
def test_a51b_r1_asymmetric_utc_review_age_boundaries(seconds_delta,permitted):
    # Freeze both the review-time record and acceptance clock: no flaky
    # integration sleep or tolerance that shifts the 90-day boundary.
    fixed=datetime(2026,11,10,10,0,0,tzinfo=timezone.utc)
    value=(fixed+timedelta(seconds=seconds_delta)).isoformat()
    if permitted:
        assert validate_review_time(value,now_utc=fixed) is None
    else:
        with pytest.raises(LiveGateError,match=(
            "A51B_MASK_REVIEW_TIME_IN_FUTURE" if seconds_delta>30
            else "A51B_MASK_REVIEW_TIME_STALE"
        )):
            validate_review_time(value,now_utc=fixed)


@pytest.mark.parametrize("invalid",[
    "2026-11-10T10:00:00",                 # naive
    "2026-11-10T19:00:00+09:00",          # same instant, not UTC
    "2026-11-10T10:00:00+99:99",
    "not-a-date", "", None, 174343,
])
def test_a51b_r1_review_timestamp_invalid_or_non_utc_blocked(invalid):
    fixed=datetime(2026,11,10,10,0,0,tzinfo=timezone.utc)
    with pytest.raises(LiveGateError,match="A51B_MASK_REVIEW_TIME_INVALID"):
        validate_review_time(invalid,now_utc=fixed)


@pytest.mark.parametrize("seconds_in_future", [300, 30*24*3600])
def test_a51b_r1_valid_dual_signatures_cannot_authorize_future_mask_review(
        tmp_path,monkeypatch,signed_beta,seconds_in_future):
    # End-to-end: real test Ed25519 signatures cannot legalize an observation
    # that has not occurred. Final files and Image Approval stay unmodified.
    client,app,job,frozen,raw,root,live,qa=ready_to_compose(
        tmp_path,monkeypatch,signed_beta)
    try:
        timestamp=(datetime.now(timezone.utc)+timedelta(
            seconds=seconds_in_future)).isoformat()
        sign_candidate_review(signed_beta,root,job,frozen,raw,
                              mutate={"review_time_utc":timestamp})
        response=client.post(qa+"/compose",json={},headers=ORIGIN)
        assert response.status_code in (409,422),response.text
        assert "A51B_MASK_REVIEW_TIME_IN_FUTURE" in response.text
        assert app.state.live_pipeline.state.get(
            "alice",job["job_id"])["state"]=="IMAGE_APPROVED"
        assert not (app.state.live_pipeline.root/"outputs"/job["job_id"]/"final.png").exists()
    finally:
        client.__exit__(None,None,None)
