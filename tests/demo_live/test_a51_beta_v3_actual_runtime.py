"""A5-1 real Owner Composition PNG via LIVE pipeline (offline synthetic only).

Not a model-provider test, NOT a signed design, NOT real object/brand mask QA.
Exercises official image approval, frozen Profile v3 at new Job ingress,
real Korean text composition, receipt, Job ledger and download bytes.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from demo_staging.live.a5_beta_profile_v3 import (
    build_proposal, GEOMETRY, PROFILE_VERSION, PROFILE_PREFIX,
    PROPOSAL_EPOCH, PRETENDARD_139_SHA, verify_receipt_for_v3,
)
from demo_staging.live.contracts import LiveGateError, digest
from tests.demo_live.test_http_gateway import setup, login
from tests.demo_live.test_pm_track_a_single_candidate import (
    configure_qa, new_job, ORIGIN,
)
from tests.demo_live.test_live_contracts import sample_input

ROOT=Path(__file__).resolve().parents[2]
FONT=ROOT/"app/node_modules/pretendard/dist/public/variable/PretendardVariable.ttf"


@pytest.mark.parametrize("choice", ("A","C"))
def test_a51_new_job_frozen_v3_real_owner_composed_png_download(tmp_path,monkeypatch,choice):
    configure_qa(monkeypatch)
    monkeypatch.setenv("IT_TEM_A5_V3_BETA_PROFILE",choice)
    monkeypatch.setenv("IT_TEM_A5_V3_OFFLINE_DEV_ALLOWED","YES")
    monkeypatch.setenv("IT_TEM_LIVE_KOREAN_FONT",str(FONT))
    app,codes=setup(tmp_path)
    with TestClient(app, client=("127.0.0.1",12121)) as client:
        login(client,codes["alice"])
        jid=new_job(client)
        live="/demo/api/live/jobs/"+jid
        qa="/demo/api/qa/jobs/"+jid
        inp=client.post(live+"/input",json={
            **sample_input(),"image_size":"4:5","generation_mode":"composed",
        },headers=ORIGIN)
        assert inp.status_code==200,inp.text
        state=app.state.live_pipeline.state
        template=state.template("alice",jid)
        assert template["profile_id"]==PROFILE_PREFIX+choice
        assert template["profile_version"]==PROFILE_VERSION
        assert template["safe_zone"]["policy_epoch"]==PROPOSAL_EPOCH
        assert template["safe_zone"]["real_provider_permitted"] is False
        assert template["layout_sha"]==digest(build_proposal(choice)["layout"])
        assert template["layout"]["cta_placement"]=="image"
        assert set(template["layout"]["text_regions"])=={"headline","subline","cta"}
        # Actual Owner Image DTO carries the new versioned prompt contract,
        # not the incompatible legacy 4:5 CTA=platform instruction.
        # This DTO is still OFFLINE_FIXTURE and cannot authorize paid calls.
        review=client.post(qa+"/text",headers=ORIGIN)
        assert review.status_code==200,review.text
        text=review.json()
        approval=client.post(live+"/approve-copy",json={
            "expected_generation":text["generation"],
            "expected_review_sha":text["review_sha"]},headers=ORIGIN)
        assert approval.status_code==200,approval.text
        from tests.demo_live.test_pipeline import FakeOwner
        app.state.live_pipeline.prompt("alice",jid,FakeOwner(),offline=True)
        owner_request=app.state.live_pipeline.image_input("alice",jid)
        assert owner_request.composed_layout_profile=="a5-v3-beta-"+choice
        assert owner_request.generation_mode=="composed"
        assert owner_request.layout_selection.aspect_ratio=="4:5"
        gen=client.post(qa+"/prompt-image",headers=ORIGIN)
        assert gen.status_code==200,gen.text
        candidate=gen.json()
        assert candidate["state"]=="IMAGE_REVIEW_REQUIRED"
        assert candidate["image_attempt_version"]==1
        sha=candidate["image_sha"]
        source_candidate=client.get(qa+"/artifacts/candidate")
        assert source_candidate.status_code==200
        assert hashlib.sha256(source_candidate.content).hexdigest()==sha
        assert client.post(live+"/approve-image",json={"image_sha":sha},
                           headers=ORIGIN).status_code==200
        done=client.post(qa+"/compose",json={},headers=ORIGIN)
        assert done.status_code==200,done.text
        final=done.json()
        assert final["state"]=="COMPLETED"
        png=client.get(qa+"/artifacts/final")
        caption=client.get(qa+"/artifacts/caption")
        assert png.status_code==200 and caption.status_code==200
        assert hashlib.sha256(png.content).hexdigest()==final["final_sha"]
        assert hashlib.sha256(caption.content).hexdigest()==final["caption_sha"]
        with __import__("io").BytesIO(png.content) as fp, Image.open(fp) as im:
            assert im.format=="PNG" and im.size==(1080,1350)
            # A round CTA corner shows source pixels, unlike a full
            # rectangle's solid color. Center CTA uses the style fill.
            corners=GEOMETRY[choice]["cta"]
            source_color=(216,226,234)
            assert im.convert("RGB").getpixel((corners[0]+1,corners[1]+1))==source_color
            center=(corners[0]+15,(corners[1]+corners[3])//2)
            assert im.convert("RGB").getpixel(center)!=source_color
        manifest=state.read_manifest("alice",jid)
        receipt=manifest["receipt"]
        assert receipt["renderer"]=="korean-composition-v1"
        assert receipt["beta_style"]==choice
        assert receipt["cta_corner_radius"]==GEOMETRY[choice]["cta_corner_radius"]
        assert receipt["typography_variable_weight"]=={
            "headline":700,"subline":500,"cta":700}
        assert receipt["cta_placement"]=="image"
        assert receipt["omitted_image_fields"]==[]
        assert set(receipt["placements"])=={"headline","subline","cta"}
        assert receipt["profile_id"]==PROFILE_PREFIX+choice
        assert receipt["profile_version"]==PROFILE_VERSION
        assert receipt["profile_layout_sha256"]==template["layout_sha"]
        assert receipt["profile_policy_epoch"]==PROPOSAL_EPOCH
        assert receipt["font_sha256"]==PRETENDARD_139_SHA
        assert receipt["beta_only"] is True and receipt["owner_pm_signed"] is False
        assert receipt["protection_evidence"]=="SYNTHETIC_TARGET_ONLY_REAL_PRODUCT_NOT_AUDITED"
        assert receipt["protected_region_check"] is False
        assert receipt["synthetic_target_region_check"] is True
        copy=json.loads(state.get("alice",jid)["copy_json"])
        for field in ("headline","subline","cta"):
            assert receipt["placements"][field]["region"]==list(GEOMETRY[choice][field])
            assert receipt["placements"][field]["text_sha256"]==hashlib.sha256(
                copy["ad_copy"][field].encode()).hexdigest()
            assert receipt["placements"][field]["line_count"]==1
        assert receipt["placements"]["cta"]["font_size"]>=48
        # Real image has copy pixels, unlike solid-background source fixture.
        with Image.open(__import__("io").BytesIO(png.content)) as rendered:
            with Image.open(__import__("io").BytesIO(source_candidate.content)) as source:
                cta=GEOMETRY[choice]["cta"]
                spot=((cta[0]+cta[2])//2,cta[1]+10)
                source_color=source.convert("RGB").getpixel((50,50))
                assert rendered.convert("RGB").getpixel(spot)!=source_color
        with app.state.live_pipeline.cost.connect() as conn:
            assert conn.execute("select count(*) from attempts").fetchone()[0]==0
        with app.state.live_queue.db() as conn:
            assert conn.execute("select count(*) from queued_ops").fetchone()[0]==0
        with state.db() as conn:
            rows=conn.execute("select state,candidate_sha from live_image_attempts where job_id=?",
                              (jid,)).fetchall()
            assert len(rows)==1 and rows[0]["state"]=="COMPLETED"
            assert rows[0]["candidate_sha"]==sha
        # GET-only re-entry, byte-for-byte stable. Actor isolation as existing.
        assert client.get(live).status_code==200
        assert client.get(qa+"/artifacts/final").content==png.content
        assert client.post(qa+"/compose",json={},headers=ORIGIN).status_code in (409,422)


@pytest.mark.parametrize("profile",("A","C"))
def test_a51_profile_v3_geometry_and_exact_text_region(profile):
    from src.image_generation.composition import CompositionLayout
    layout=CompositionLayout.model_validate_json(json.dumps(
        build_proposal(profile)["layout"]))
    assert layout.cta_placement=="image"
    assert layout.canvas_size==(1080,1350)
    assert len(layout.protected_regions)==1
    for field in ("headline","subline","cta"):
        assert layout.text_regions[field].pixels((1080,1350))==GEOMETRY[profile][field]


@pytest.mark.parametrize("mode,ratio",(
    ("freeform","4:5"),("composed","3:4"),("composed","9:16"),
    ("freeform","3:4"),("freeform","9:16"),
))
def test_a51_does_not_substitute_v3_for_other_approved_modes(tmp_path,monkeypatch,mode,ratio):
    configure_qa(monkeypatch)
    monkeypatch.setenv("IT_TEM_A5_V3_BETA_PROFILE","A")
    monkeypatch.setenv("IT_TEM_A5_V3_OFFLINE_DEV_ALLOWED","YES")
    app,codes=setup(tmp_path)
    with TestClient(app, client=("127.0.0.1",12121)) as client:
        login(client,codes["alice"])
        jid=new_job(client)
        r=client.post("/demo/api/live/jobs/"+jid+"/input",json={
            **sample_input(),"image_size":ratio,"generation_mode":mode,
        },headers=ORIGIN)
        assert r.status_code==200,r.text
        t=app.state.live_pipeline.state.template("alice",jid)
        assert t["profile_id"].startswith("OWNER_IMAGE_SIZE_")
        assert not t["profile_id"].startswith(PROFILE_PREFIX)


def test_a51_unsigned_v3_cannot_activate_when_live_enabled(tmp_path,monkeypatch):
    configure_qa(monkeypatch)
    monkeypatch.setenv("IT_TEM_A5_V3_BETA_PROFILE","A")
    monkeypatch.setenv("IT_TEM_A5_V3_OFFLINE_DEV_ALLOWED","YES")
    monkeypatch.setenv("IT_TEM_LIVE_ENABLED","YES")
    app,codes=setup(tmp_path)
    with TestClient(app,client=("127.0.0.1",12121)) as client:
        login(client,codes["alice"])
        jid=new_job(client)
        response=client.post("/demo/api/live/jobs/"+jid+"/input",json={
            **sample_input(),"image_size":"4:5","generation_mode":"composed",
        },headers=ORIGIN)
        assert response.status_code in (409,422)
        assert "A5_V3_PROPOSAL_UNAUTHORIZED" in response.text
        with pytest.raises(LiveGateError,match="LIVE_JOB_NOT_FOUND"):
            app.state.live_pipeline.state.get("alice",jid)


def test_a51_beta_v3_requires_explicit_opt_in(tmp_path,monkeypatch):
    configure_qa(monkeypatch)
    monkeypatch.delenv("IT_TEM_A5_V3_BETA_PROFILE",raising=False)
    monkeypatch.delenv("IT_TEM_A5_V3_OFFLINE_DEV_ALLOWED",raising=False)
    app,codes=setup(tmp_path)
    with TestClient(app,client=("127.0.0.1",12121)) as client:
        login(client,codes["alice"])
        jid=new_job(client)
        response=client.post("/demo/api/live/jobs/"+jid+"/input",json={
            **sample_input(),"image_size":"4:5","generation_mode":"composed",
        },headers=ORIGIN)
        assert response.status_code==200
        t=app.state.live_pipeline.state.template("alice",jid)
        assert t["profile_id"]=="OWNER_IMAGE_SIZE_4_5"
        assert t["profile_version"]=="instagram-copy-hierarchy-v2"


def test_a51_v3_receipt_rejects_missing_cta_and_modified_hash():
    base=build_proposal("A")
    layout=base["layout"]
    plan={"profile_id":base["profile_id"],
          "profile_version":base["profile_version"],
          "layout_sha":digest(layout)}
    copy={"ad_copy":{"headline":"데일리 크림","subline":"매일 촉촉한 사용감",
                     "cta":"지금 만나보세요"}}
    bad={"cta_placement":"platform","omitted_image_fields":["cta"],
         "placements":{"headline":{"text_sha256":"0"*64},
                       "subline":{"text_sha256":"0"*64}}}
    with pytest.raises(LiveGateError,match="A5_V3_CTA_MISSING_OR_DUPLICATED"):
        verify_receipt_for_v3(bad,plan=plan,font_sha=PRETENDARD_139_SHA,copy_json=copy)
    with pytest.raises(LiveGateError,match="A5_V3_FROZEN_PROFILE_FONT_MISMATCH"):
        verify_receipt_for_v3({},plan=plan,font_sha="f"*64,copy_json=copy)

def test_a51_v3_image_request_cannot_activate_provider_after_flag_flip(
        tmp_path,monkeypatch):
    configure_qa(monkeypatch)
    monkeypatch.setenv("IT_TEM_A5_V3_BETA_PROFILE","A")
    monkeypatch.setenv("IT_TEM_A5_V3_OFFLINE_DEV_ALLOWED","YES")
    app,codes=setup(tmp_path)
    with TestClient(app,client=("127.0.0.1",12121)) as client:
        login(client,codes["alice"])
        jid=new_job(client)
        base="/demo/api/live/jobs/"+jid
        assert client.post(base+"/input",json={
            **sample_input(),"image_size":"4:5","generation_mode":"composed"
        },headers=ORIGIN).status_code==200
        st=app.state.live_pipeline.state
        from tests.demo_live.test_pipeline import FakeOwner
        flow=app.state.live_pipeline
        text=flow.text("alice",jid,FakeOwner(),offline=True)
        st.approve_copy("alice",jid,text["generation"],text["review_sha"])
        flow.prompt("alice",jid,FakeOwner(),offline=True)
        # Even after an offline Job was created, later host LIVE enablement
        # cannot hand its unsigned v3 proposal to the paid Image provider.
        monkeypatch.setenv("IT_TEM_LIVE_ENABLED","YES")
        with pytest.raises(LiveGateError,match="A5_V3_PROVIDER_NOT_AUTHORIZED"):
            flow.image_input("alice",jid)
        monkeypatch.setenv("IT_TEM_LIVE_ENABLED","NO")
        monkeypatch.setenv("IT_TEM_LIVE_EXECUTION_APPROVED","YES")
        with pytest.raises(LiveGateError,match="A5_V3_PROVIDER_NOT_AUTHORIZED"):
            flow.image_input("alice",jid)
        assert st.get("alice",jid)["state"]=="PROMPT_READY"


def test_a51_old_v2_job_snapshot_not_migrated_when_optin_changes(
        tmp_path,monkeypatch):
    configure_qa(monkeypatch)
    monkeypatch.delenv("IT_TEM_A5_V3_BETA_PROFILE",raising=False)
    app,codes=setup(tmp_path)
    with TestClient(app,client=("127.0.0.1",12121)) as client:
        login(client,codes["alice"])
        jid=new_job(client)
        assert client.post("/demo/api/live/jobs/"+jid+"/input",json={
            **sample_input(),"image_size":"4:5","generation_mode":"composed"
        },headers=ORIGIN).status_code==200
        state=app.state.live_pipeline.state
        old=state.template("alice",jid)
        monkeypatch.setenv("IT_TEM_A5_V3_BETA_PROFILE","C")
        monkeypatch.setenv("IT_TEM_A5_V3_OFFLINE_DEV_ALLOWED","YES")
        assert state.template("alice",jid)==old
        assert old["profile_version"]=="instagram-copy-hierarchy-v2"
        assert old["layout"]["cta_placement"]=="platform"

def test_a51_profile_geometry_links_to_accepted_a50e_proposal_bytes():
    from demo_staging.live.a5_beta_profile_v3 import REFERENCE_MANIFEST_SHA
    m=ROOT/"docs/integration/evidence/A50E_20261110/A50E_REFLOW_DESIGN_MANIFEST.json"
    assert hashlib.sha256(m.read_bytes()).hexdigest()==REFERENCE_MANIFEST_SHA
    data=json.loads(m.read_text())
    for key,choice in (
      ("A_REFLOW_EDITORIAL_CENTER","A"),
      ("C_REFLOW_CONTRAST_ACTION","C"),
    ):
        reference=data["variants"][key]
        proposed=build_proposal(choice)
        assert reference["sha256"]==proposed["safe_zone"]["proposal_sha256"]
        assert reference["copy"]["cta"]["rect"]==list(GEOMETRY[choice]["cta"])
        assert reference["fake_protected_target"]==list(GEOMETRY[choice]["product"])
    assert data["owner_pm_approved"] is False
