"""A51E locally simulated signed Tailscale Serve admission — NONBILLABLE ONLY.

Real HMAC signed actor headers (ephemeral test key), persistent isolated SQLite,
B0 generated Job, policy-pending MPO denial, browser/SSO/Actor bypass negatives.
Does NOT connect to actual Tailscale, GCP A, real Provider or actual brand data.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import asyncio
import json
from pathlib import Path
import secrets
import sqlite3

from fastapi.testclient import TestClient
import httpx
from PIL import Image
import pytest

from demo_staging.app import make_demo_app
from demo_staging.tailnet_assertion import build_assertion
from demo_staging.live.a51e_signed_beta_ingress_ledger import (
    BetaUploadLedger, BetaIngressConflict,
)
from tests.demo_live.test_a51c_explicit_mpo_ingress import synthetic_mpo
from tests.demo_live.test_http_gateway import photo

HOST="macstudio-integration.ts.net:10443"
BASE="https://"+HOST
ROOT="/demo/api/a51e/beta/jobs"
O={"Origin":BASE}


def picture(color,format="PNG"):
    b=BytesIO();Image.new("RGB",(155,185),color).save(b,format)
    return b.getvalue()


def signed(key,actor,path=ROOT,method="POST"):
    return {**O,**build_assertion(key,actor,"evaluator",method,path,HOST)}


def form(raw1=None,raw2=None,source_name="first.png",second_name="second.png"):
    raw1=photo((65,95,150)) if raw1 is None else raw1
    raw2=photo((80,125,165)) if raw2 is None else raw2
    return [
       ("product_images",(source_name,raw1,
           "image/jpeg" if source_name.lower().endswith((".jpg",".jpeg")) else "image/png")),
       ("product_images",(second_name,raw2,
           "image/jpeg" if second_name.lower().endswith((".jpg",".jpeg")) else "image/png")),
       ("product_input_json",(None,'{"generation_mode":"composed","image_size":"4:5"}')),
    ]


@pytest.fixture
def candidate(tmp_path,monkeypatch):
    # This is an isolated TEST-only host with ephemeral HMAC assertion secret,
    # NOT a real signed Tailscale SSO or PM/Owner approval.
    runtime=tmp_path/"runtime"
    runtime.mkdir(mode=0o700)
    secret=tmp_path/"proxy_key"
    # tailnet_assertion.key_from_file strips surrounding whitespace from
    # operator-provided text secrets. Use ASCII-hex fixture key to avoid
    # intermittent auth drift when a random binary key starts/ends in ASCII
    # whitespace. This is an ephemeral *test-only* HMAC key.
    secret.write_bytes(secrets.token_hex(32).encode("ascii"));secret.chmod(0o600)
    actors=tmp_path/"actors.json"
    actors.write_text(json.dumps({
        "alice":"evaluator","bob":"evaluator","charlie":"admin",
        "delta":"evaluator","echo":"admin",
    }))
    invites=tmp_path/"invites.json"
    invites.write_text(json.dumps({
        "alice":{"role":"evaluator","digest":"a"*64},
    }))
    dist=tmp_path/"dist"
    (dist/"assets").mkdir(parents=True)
    (dist/"index.html").write_text("<html>signed test</html>")
    keys={
        "IT_TEM_A51E_SIGNED_BETA_INTAKE":"YES",
        "IT_TEM_A51E_NONBILLABLE_CANDIDATE":"YES",
        "IT_TEM_A51E_MPO_POLICY_STATE":"PENDING_REJECT",
        "IT_TEM_A51D_SIGNED_BETA_RUNTIME":"YES",
        "IT_TEM_TAILNET_SSO_ONLY":"YES",
        "IT_TEM_TAILNET_AUTH_ENABLED":"YES",
        "IT_TEM_TAILNET_AUTH_KEY_FILE":str(secret),
        "IT_TEM_TAILNET_ACTORS_FILE":str(actors),
        "IT_TEM_TAILNET_EXPECTED_HOST":HOST,
        "IT_TEM_LIVE_COST_POLICY":"HARD_CAP",
        "IT_TEM_A51C_HARD_CAP_ENABLE":"YES",
        "IT_TEM_QA_FIXTURE_ENABLED":"YES",
        "IT_TEM_LIVE_ENABLED":"NO",
        "IT_TEM_LIVE_EXECUTION_APPROVED":"NO",
        "IT_TEM_LIVE_WEB_QUEUE_ENABLED":"NO",
        "IT_TEM_ENABLE_BILLABLE_TEXT_CALLS":"NO",
        "IT_TEM_A51D_MPO_FIXTURE_BRIDGE":"NO",
    }
    for k,v in keys.items():monkeypatch.setenv(k,v)
    def make(preinit=True):
        # Separate *explicit* operator-style setup, never app auto-init.
        if preinit:
            BetaUploadLedger(runtime/"a51e_beta_upload_request.sqlite",
                             initialize=True)
        return make_demo_app(runtime,invites,dist,secure_cookie=True)
    return {"root":runtime,"make":make,"key":secret.read_bytes(),"env":keys}


def test_signed_sso_beta_no_ledger_never_initializes_automatically(candidate):
    x=candidate
    with pytest.raises(RuntimeError,match="A51E_PREINITIALIZED_PRIVATE_LEDGER_REQUIRED"):
        x["make"](preinit=False)
    assert not (x["root"]/"a51e_beta_upload_request.sqlite").exists()


def test_real_signed_hmac_actor_to_new_b0_job_and_idempotent_replay(candidate):
    x=candidate;app=x["make"]()
    key=x["key"];request_id=secrets.token_hex(16)
    with TestClient(app,base_url=BASE) as alice:
        # The legacy frame-zero B0 upload route cannot be called in candidate.
        legacy=alice.post("/api/v1/jobs",headers=signed(
            key,"alice","/api/v1/jobs"),files=form())
        assert legacy.status_code==423
        invalid=alice.post(ROOT,headers=O,files=form())
        assert invalid.status_code==401
        legacy_cookie=alice.post("/demo/api/session",
                      headers=signed(key,"alice","/demo/api/session"),
                      json={"invite_code":"legacy-invite-is-never-allowed-in-signed-SSO"})
        assert legacy_cookie.status_code==403
        signed_login=alice.get("/demo/api/session",
                 headers=signed(key,"alice","/demo/api/session",method="GET"))
        assert signed_login.status_code==200
        assert signed_login.json()["auth_provider"]=="TAILSCALE_SERVE"

        h={**signed(key,"alice"),"X-IT-TEM-Upload-Request-ID":request_id}
        good=alice.post(ROOT,headers=h,files=form())
        assert good.status_code==201,good.text
        job=good.json();assert job["status"]=="INPUTS_VALIDATED"
        jid=job["job_id"]
        assert app.state.demo_ledger.owns("alice",jid)
        assert len(job["assets"])==2
        assert len(list(app.state.job_store.root.iterdir()))==1
        assert app.state.a51e_beta_upload_ledger.inspect_for_test(
             request_id)["state"]=="COMMITTED"
        assert app.state.a51e_beta_upload_ledger.inspect_for_test(
             request_id)["job_id"]==jid

        # Same request actor/content/id may return exact SAME Job, not 2 Jobs.
        replay=alice.post(ROOT,headers=h,files=form())
        assert replay.status_code==200,replay.text
        assert replay.headers["x-it-tem-upload-idempotent"]=="REPLAY_SAME_JOB"
        assert replay.json()["job_id"]==jid
        assert len(list(app.state.job_store.root.iterdir()))==1
        # Same id but altered source bytes is never idempotent.
        different=alice.post(ROOT,headers=h,
           files=form(raw1=photo((210,15,55))))
        assert different.status_code==409
        # Different Actor cannot adopt a committed request_id.
        another=alice.post(ROOT,headers={
            **signed(key,"bob"),"X-IT-TEM-Upload-Request-ID":request_id,
        },files=form())
        assert another.status_code==409
        own=alice.get(f"/api/v1/jobs/{jid}",headers=signed(
            key,"alice",f"/api/v1/jobs/{jid}",method="GET"))
        assert own.status_code==200
        cross=alice.get(f"/api/v1/jobs/{jid}",headers=signed(
            key,"bob",f"/api/v1/jobs/{jid}",method="GET"))
        assert cross.status_code==404
        assert app.state.a51e_beta_upload_ledger.inspect_for_test(request_id)[
            "actor"]=="alice"


@pytest.mark.parametrize("filename,mime",[
    ("hidden.jpg","image/jpeg"),("actually.mpo","image/jpeg"),
])
def test_signed_mpo_detected_from_container_never_selects_frame0(
        candidate,filename,mime):
    x=candidate;app=x["make"]();key=x["key"]
    with TestClient(app,base_url=BASE) as c:
        req=secrets.token_hex(16)
        got=c.post(ROOT,headers={**signed(key,"alice"),
                       "X-IT-TEM-Upload-Request-ID":req},
          files=form(raw1=synthetic_mpo(),source_name=filename))
        assert got.status_code==422
        assert got.json()["detail"]=="A51E_MPO_OWNER_POLICY_PENDING"
        assert app.state.a51e_beta_upload_ledger.inspect_for_test(req) is None
        assert len(list(app.state.job_store.root.iterdir()))==0


def test_signed_beta_rejects_invalid_headers_and_cross_origin(candidate):
    x=candidate;app=x["make"]();key=x["key"]
    with TestClient(app,base_url=BASE) as c:
        ident=secrets.token_hex(16)
        valid={**signed(key,"alice"),"X-IT-TEM-Upload-Request-ID":ident}
        unsigned=dict(valid)
        unsigned.pop("x-ittem-tailnet-signature")
        assert c.post(ROOT,headers=unsigned,files=form()).status_code==401
        forged={**valid,"x-ittem-tailnet-actor":"bob"}
        assert c.post(ROOT,headers=forged,files=form()).status_code==401
        wrong_origin={**valid,"Origin":"https://evil.example"}
        assert c.post(ROOT,headers=wrong_origin,files=form()).status_code==403
        missing_id=signed(key,"alice")
        assert c.post(ROOT,headers=missing_id,files=form()).status_code==422
        assert not list(app.state.job_store.root.iterdir())


@pytest.mark.parametrize("flag,value",[
   ("IT_TEM_A51E_MPO_POLICY_STATE","ALLOW_UNAPPROVED"),
   ("IT_TEM_A51E_NONBILLABLE_CANDIDATE","NO"),
   ("IT_TEM_A51D_SIGNED_BETA_RUNTIME","NO"),
   ("IT_TEM_TAILNET_SSO_ONLY","NO"),
   ("IT_TEM_LIVE_ENABLED","YES"),
   ("IT_TEM_LIVE_EXECUTION_APPROVED","YES"),
   ("IT_TEM_LIVE_WEB_QUEUE_ENABLED","YES"),
   ("IT_TEM_ENABLE_BILLABLE_TEXT_CALLS","YES"),
   ("IT_TEM_LIVE_COST_POLICY","MONITOR_ONLY"),
   ("IT_TEM_A51C_HARD_CAP_ENABLE","NO"),
   ("IT_TEM_A51D_MPO_FIXTURE_BRIDGE","YES"),
])
def test_nonbillable_signed_candidate_does_not_start_with_unsafe_flags(
        candidate,monkeypatch,flag,value):
    x=candidate
    monkeypatch.setenv(flag,value)
    with pytest.raises(RuntimeError,match="A51E_SIGNED_SSO_CANDIDATE_HARD_GATES_NOT_MET"):
        x["make"]()


@pytest.mark.parametrize("reason",["job_create","owner_claim"])
def test_signed_job_creation_failure_retains_id_tombstone(
        candidate,monkeypatch,reason):
    x=candidate;app=x["make"]();key=x["key"]
    req=secrets.token_hex(16)
    with TestClient(app,base_url=BASE) as c:
        if reason=="job_create":
            monkeypatch.setattr(app.state.job_store,"create_job",
               lambda *_: (_ for _ in ()).throw(OSError("test-only")))
        else:
            monkeypatch.setattr(app.state.demo_ledger,"claim",
               lambda *_: (_ for _ in ()).throw(
                   sqlite3.OperationalError("test-only")))
        h={**signed(key,"alice"),"X-IT-TEM-Upload-Request-ID":req}
        failed=c.post(ROOT,headers=h,files=form())
        assert failed.status_code==503,failed.text
        row=app.state.a51e_beta_upload_ledger.inspect_for_test(req)
        assert row["state"]=="FAILED_REQUIRES_REVIEW"
        assert not list(app.state.job_store.root.iterdir())
        again=c.post(ROOT,headers=h,files=form())
        assert again.status_code==409


def test_signed_request_id_survives_restart_and_replay_same_b0_job(candidate):
    x=candidate;app=x["make"]();key=x["key"]
    req=secrets.token_hex(16)
    h={**signed(key,"alice"),"X-IT-TEM-Upload-Request-ID":req}
    with TestClient(app,base_url=BASE) as c:
        job=c.post(ROOT,headers=h,files=form())
        assert job.status_code==201
        job_id=job.json()["job_id"]
    new_app=x["make"](preinit=False)
    with TestClient(new_app,base_url=BASE) as c:
        retried=c.post(ROOT,headers=h,files=form())
        assert retried.status_code==200,retried.text
        assert retried.json()["job_id"]==job_id
        assert len(list(new_app.state.job_store.root.iterdir()))==1


def test_same_request_id_concurrent_uploads_publish_only_one_b0_job(
        candidate):
    x=candidate;app=x["make"]();key=x["key"]
    req=secrets.token_hex(16)
    async def go():
        transport=httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport,base_url=BASE) as c:
            async def one():
                return await c.post(ROOT,headers={
                    **signed(key,"alice"),
                    "X-IT-TEM-Upload-Request-ID":req},files=form())
            results=await asyncio.gather(*(one() for _ in range(8)))
        assert sum(y.status_code==201 for y in results)==1
        assert all(y.status_code in (200,201,409) for y in results)
        ids=[y.json()["job_id"] for y in results if y.status_code in (200,201)]
        assert len(set(ids))==1
        assert app.state.demo_ledger.owns("alice",ids[0])
        assert len(list(app.state.job_store.root.iterdir()))==1
    asyncio.run(go())


def test_preinitialized_private_ledger_never_follows_symlink(tmp_path):
    private=tmp_path/"private"
    private.mkdir(mode=0o700)
    fake=tmp_path/"x.sqlite"
    with sqlite3.connect(fake) as db:
        db.execute("CREATE TABLE t(x)")
    bad=private/"a51e_beta_upload_request.sqlite"
    bad.symlink_to(fake)
    with pytest.raises(RuntimeError,match="A51E_LEDGER_SYMLINK_DENIED"):
        BetaUploadLedger(bad)


@pytest.mark.parametrize("mode,ratio",[
    ("composed","4:5"),("composed","3:4"),("composed","9:16"),
    ("freeform","4:5"),("freeform","3:4"),("freeform","9:16"),
])
def test_signed_actor_new_b0_job_to_full_copy_image_caption_offline_e2e(
        candidate,monkeypatch,mode,ratio):
    """Six INDEPENDENT, synthetic, nonbillable signed-assertion API Jobs.

    Not six paid Provider jobs. Not proof of actual Tailscale Serve, licensed
    product photos or owner-approved v3 signature. Keep review gates intact.
    """
    monkeypatch.setenv("IT_TEM_QA_ALLOWED_ACTORS","alice")
    monkeypatch.setenv("IT_TEM_LIVE_KOREAN_FONT",
                       "/System/Library/Fonts/Supplemental/AppleGothic.ttf")
    from tests.demo_live.test_live_contracts import sample_input
    app=candidate["make"]();key=candidate["key"]
    origin=ROOT
    with TestClient(app,base_url=BASE,client=("127.0.0.1",21337)) as c:
        req=secrets.token_hex(16)
        created=c.post(origin,headers={
            **signed(key,"alice",origin),
            "X-IT-TEM-Upload-Request-ID":req,
        },files=form())
        assert created.status_code==201,created.text
        jid=created.json()["job_id"]
        root=f"/demo/api/live/jobs/{jid}"
        inp=sample_input()
        inp.update({"generation_mode":mode,"image_size":ratio})
        input_result=c.post(root+"/input",headers=signed(
            key,"alice",root+"/input"),json=inp)
        assert input_result.status_code==200,input_result.text
        assert input_result.json()["state"]=="INPUT_STORED"

        # Paid path is impossible with live disabled and no PM signoff.
        no_billing=c.post(root+"/queue-text",headers=signed(
            key,"alice",root+"/queue-text"))
        assert no_billing.status_code==423
        txtpath=f"/demo/api/qa/jobs/{jid}/text"
        output=c.post(txtpath,headers=signed(key,"alice",txtpath))
        assert output.status_code==200,output.text
        reviewed=output.json()
        assert reviewed["state"]=="COPY_REVIEW_REQUIRED"
        assert reviewed["mode"]=="OFFLINE_FIXTURE"

        path=root+"/approve-copy"
        copy_approved=c.post(path,headers=signed(key,"alice",path),
           json={"expected_generation":reviewed["generation"],
                 "expected_review_sha":reviewed["review_sha"],
                 "acknowledge_evidence":True})
        assert copy_approved.status_code==200,copy_approved.text
        assert copy_approved.json()["state"]=="COPY_APPROVED"

        path=f"/demo/api/qa/jobs/{jid}/prompt-image"
        draft=c.post(path,headers=signed(key,"alice",path))
        assert draft.status_code==200,draft.text
        image=draft.json()
        assert image["state"]=="IMAGE_REVIEW_REQUIRED"
        assert image["image_attempt_version"]==1
        assert image["image_size"]==ratio
        assert image["generation_mode"]==mode

        path=root+"/approve-image"
        approved=c.post(path,headers=signed(key,"alice",path),
             json={"image_sha":image["image_sha"]})
        assert approved.status_code==200,approved.text
        assert approved.json()["state"]=="IMAGE_APPROVED"

        path=f"/demo/api/qa/jobs/{jid}/compose"
        final=c.post(path,headers=signed(key,"alice",path),json={})
        assert final.status_code==200,final.text
        completed=final.json()
        assert completed["state"]=="COMPLETED"
        assert completed["image_attempt_version"]==1
        assert completed["image_size"]==ratio
        for kind,field in (("final","final_sha"),("caption","caption_sha")):
            url=f"/demo/api/qa/jobs/{jid}/artifacts/{kind}"
            got=c.get(url,headers=signed(key,"alice",url,method="GET"))
            assert got.status_code==200,got.text[:100]
            assert sha256(got.content).hexdigest()==completed[field]
            assert got.headers["x-it-tem-provenance"]=="OFFLINE_FIXTURE"
            other=c.get(url,headers=signed(key,"bob",url,method="GET"))
            assert other.status_code==404
        # No Queue/Cost reservations or Provider attempt records were created.
        with app.state.live_queue.db() as db:
            assert db.execute("SELECT COUNT(*) FROM queued_ops").fetchone()[0]==0
        with app.state.live_pipeline.cost.connect() as db:
            assert db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]==0
        assert app.state.a51e_beta_upload_ledger.inspect_for_test(req)[
               "job_id"]==jid
