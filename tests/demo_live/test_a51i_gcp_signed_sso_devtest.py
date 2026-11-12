"""A51I GCP-scoped WORKER-OFF signed Tailnet dev/test; not paid beta."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import json
import secrets

from fastapi.testclient import TestClient
import pytest

from demo_staging.app import make_demo_app
from demo_staging.tailnet_assertion import TailnetNonceJournal
from demo_staging.tailnet_assertion import build_assertion
from demo_staging.live.a51e_signed_beta_ingress_ledger import BetaUploadLedger
from tests.demo_live.test_a51e_signed_sso_beta_ingress import form
from tests.demo_live.test_a51c_explicit_mpo_ingress import synthetic_mpo

HOST="macstudio-macstudio.tail17dfff.ts.net:10444"
BASE="https://"+HOST
UPLOAD="/demo/api/a51e/beta/jobs"


@pytest.fixture
def candidate(tmp_path,monkeypatch):
    root=tmp_path/"runtime"
    root.mkdir(mode=0o700)
    assert not (tmp_path.stat().st_mode & 0o077)
    sha="c"*40
    (tmp_path/"SOURCE_SHA.txt").write_text(sha+"\n")
    key=tmp_path/"hmac.key"
    key.write_text(secrets.token_hex(48));key.chmod(0o600)
    roles=tmp_path/"actor_registry.json"
    roles.write_text(json.dumps({
        "alice":"admin","bob":"evaluator","charlie":"evaluator",
        "delta":"evaluator","echo":"admin",
    }))
    roles.chmod(0o600)
    invited=tmp_path/"invites.json"
    invited.write_text(json.dumps({
        "legacy":{"role":"admin","digest":sha256(b"legacy").hexdigest()},
    }))
    ui=tmp_path/"app";ui.mkdir()
    (ui/"assets").mkdir()
    (ui/"index.html").write_text("<html>WORKER OFF beta</html>")
    BetaUploadLedger(root/"a51e_beta_upload_request.sqlite",initialize=True)
    TailnetNonceJournal(root/"tailnet_nonce.sqlite",initialize=True)
    environment={
        "IT_TEM_A51I_GCP_SIGNED_SSO_DEVTEST":"YES",
        "IT_TEM_A51I_DEPLOYED_SOURCE_SHA":sha,
        "IT_TEM_A51I_MPO_POLICY":"REJECT_MULTIFRAME_V1",
        "IT_TEM_A51E_SIGNED_BETA_INTAKE":"NO",
        "IT_TEM_A51D_SIGNED_BETA_RUNTIME":"YES",
        "IT_TEM_TAILNET_SSO_ONLY":"YES",
        "IT_TEM_TAILNET_AUTH_ENABLED":"YES",
        "IT_TEM_TAILNET_AUTH_KEY_FILE":str(key),
        "IT_TEM_TAILNET_ACTORS_FILE":str(roles),
        "IT_TEM_TAILNET_EXPECTED_HOST":HOST,
        "IT_TEM_LIVE_COST_POLICY":"HARD_CAP",
        "IT_TEM_A51C_HARD_CAP_ENABLE":"YES",
        "IT_TEM_LIVE_ENABLED":"NO",
        "IT_TEM_LIVE_EXECUTION_APPROVED":"NO",
        "IT_TEM_LIVE_WEB_QUEUE_ENABLED":"NO",
        "IT_TEM_ENABLE_BILLABLE_TEXT_CALLS":"NO",
        "IT_TEM_QA_FIXTURE_ENABLED":"NO",
        "IT_TEM_A51D_MPO_FIXTURE_BRIDGE":"NO",
    }
    for k,v in environment.items():monkeypatch.setenv(k,v)
    for k in ("OPENAI_API_KEY","GOOGLE_API_KEY","GEMINI_API_KEY",
              "ANTHROPIC_API_KEY"):monkeypatch.delenv(k,raising=False)

    def create():
        return make_demo_app(root,invited,ui,secure_cookie=True,code_sha=sha)

    def sign(actor,path,method="GET"):
        return {"Origin":BASE,**build_assertion(
            key.read_bytes().strip(),actor,
            "admin" if actor=="alice" else "evaluator",
            method,path,HOST)}
    return {"root":root,"sha":sha,"create":create,"sign":sign,
            "key":key,"invited":invited}


def test_gcp_scoped_sso_signed_real_b0_job_cas_and_actor_acl(candidate):
    x=candidate;app=x["create"]()
    with TestClient(app,base_url=BASE) as client:
        assert client.get("/health").status_code==200
        assert client.get("/demo/api/session").status_code==401
        good=client.get("/demo/api/session",headers=x["sign"](
            "alice","/demo/api/session"))
        assert good.status_code==200
        assert good.json()["auth_provider"]=="TAILSCALE_SERVE"
        assert good.json()["evaluator_id"]=="alice"
        assert client.post("/api/v1/jobs",headers=x["sign"](
            "alice","/api/v1/jobs","POST"),files=form()).status_code==423
        reqid=secrets.token_hex(16)
        h={**x["sign"]("alice",UPLOAD,"POST"),
           "X-IT-TEM-Upload-Request-ID":reqid}
        job=client.post(UPLOAD,headers=h,files=form())
        assert job.status_code==201,job.text
        jid=job.json()["job_id"]
        assert app.state.demo_ledger.owns("alice",jid)
        replay=client.post(UPLOAD,headers={
            **x["sign"]("alice",UPLOAD,"POST"),
            "X-IT-TEM-Upload-Request-ID":reqid},files=form())
        assert replay.status_code==200
        assert replay.json()["job_id"]==jid
        assert client.get("/api/v1/jobs/"+jid,headers=x["sign"](
            "bob","/api/v1/jobs/"+jid)).status_code==404
        assert client.get("/api/v1/jobs/"+jid,headers=x["sign"](
            "alice","/api/v1/jobs/"+jid)).status_code==200
        assert len(list(app.state.job_store.root.iterdir()))==1
        assert app.state.a51e_beta_upload_ledger.inspect_for_test(reqid)[
            "state"]=="COMMITTED"
        assert client.get("/demo/api/session",headers={
            "Tailscale-User-Login":"alice@example.com"}).status_code==401


def test_pm_adopted_reject_multiframe_including_jpg_spoof_and_no_job(candidate):
    x=candidate;app=x["create"]()
    with TestClient(app,base_url=BASE) as c:
        h={**x["sign"]("alice",UPLOAD,"POST"),
           "X-IT-TEM-Upload-Request-ID":secrets.token_hex(16)}
        got=c.post(UPLOAD,headers=h,files=form(
            raw1=synthetic_mpo(),source_name="normal_looking.jpg"))
        assert got.status_code==422,got.text
        assert not list(app.state.job_store.root.iterdir())


@pytest.mark.parametrize("flag,value",[
    ("IT_TEM_A51I_MPO_POLICY","ALLOW_AUTO_FRAME0"),
    ("IT_TEM_A51I_DEPLOYED_SOURCE_SHA","e"*40),
    ("IT_TEM_TAILNET_EXPECTED_HOST",
     "macstudio-macstudio.tail17dfff.ts.net:10443"),
    ("IT_TEM_TAILNET_SSO_ONLY","NO"),
    ("IT_TEM_TAILNET_AUTH_ENABLED","NO"),
    ("IT_TEM_A51D_SIGNED_BETA_RUNTIME","NO"),
    ("IT_TEM_LIVE_COST_POLICY","MONITOR_ONLY"),
    ("IT_TEM_A51C_HARD_CAP_ENABLE","NO"),
    ("IT_TEM_LIVE_ENABLED","YES"),
    ("IT_TEM_LIVE_EXECUTION_APPROVED","YES"),
    ("IT_TEM_LIVE_WEB_QUEUE_ENABLED","YES"),
    ("IT_TEM_ENABLE_BILLABLE_TEXT_CALLS","YES"),
    ("IT_TEM_QA_FIXTURE_ENABLED","YES"),
    ("IT_TEM_A51D_MPO_FIXTURE_BRIDGE","YES"),
    ("IT_TEM_A51E_SIGNED_BETA_INTAKE","YES"),
    ("OPENAI_API_KEY","test-fake-provider-key-not-used"),
])
def test_devtest_startup_must_fail_closed(candidate,monkeypatch,flag,value):
    x=candidate
    monkeypatch.setenv(flag,value)
    with pytest.raises(RuntimeError,match="A51I_GCP_SIGNED_SSO_WORKER_OFF_GATES_NOT_MET"):
        x["create"]()


def test_current_a51e_test_only_not_promoted(candidate,monkeypatch):
    x=candidate
    monkeypatch.setenv("IT_TEM_A51I_GCP_SIGNED_SSO_DEVTEST","NO")
    monkeypatch.setenv("IT_TEM_A51E_SIGNED_BETA_INTAKE","YES")
    with pytest.raises(RuntimeError,match="A51E_SIGNED_SSO_CANDIDATE_HARD_GATES_NOT_MET"):
        x["create"]()


def test_unpinned_actual_source_and_dir_mismatch_fail_closed(candidate):
    x=candidate
    (x["root"].parent/"SOURCE_SHA.txt").write_text("d"*40)
    with pytest.raises(RuntimeError,match="A51I_GCP_SIGNED_SSO_WORKER_OFF_GATES_NOT_MET"):
        x["create"]()


def test_signed_assertion_replay_and_restart_fail_closed(candidate):
    x=candidate
    app=x["create"]()
    signed=x["sign"]("alice","/demo/api/session")
    with TestClient(app,base_url=BASE) as c:
        assert c.get("/demo/api/session",headers=signed).status_code==200
        # A new HTTP request cannot replay a previously consumed signature.
        assert c.get("/demo/api/session",headers=signed).status_code==401
        assert c.get("/demo/api/session",headers=x["sign"](
            "alice","/demo/api/session")).status_code==200
    # State is persistent across a new app process; no in-memory cache bypass.
    new_app=x["create"]()
    with TestClient(new_app,base_url=BASE) as c:
        assert c.get("/demo/api/session",headers=signed).status_code==401


def test_invalid_or_expired_assertions_never_consume_nonce(candidate):
    from demo_staging.tailnet_assertion import build_assertion
    import time
    x=candidate
    path="/demo/api/session"
    with TestClient(x["create"](),base_url=BASE) as c:
        old={"Origin":BASE,**build_assertion(
            x["key"].read_bytes().strip(),"alice","admin","GET",path,HOST,
            now=int(time.time())-80)}
        assert c.get(path,headers=old).status_code==401
        valid=x["sign"]("alice",path)
        tampered=dict(valid)
        tampered["x-ittem-tailnet-signature"]="0"*64
        assert c.get(path,headers=tampered).status_code==401
        assert c.get(path,headers=valid).status_code==200

def test_same_nonce_concurrent_threads_only_one_wins(candidate):
    from concurrent.futures import ThreadPoolExecutor
    from demo_staging.tailnet_assertion import TailnetAssertionError
    import secrets
    x=candidate
    journal=TailnetNonceJournal(x["root"]/"tailnet_nonce.sqlite")
    nonce=secrets.token_hex(16)
    def consume(i):
        try:
            journal.consume(nonce)
            return "accepted"
        except TailnetAssertionError as exc:
            assert "NONCE_REPLAY" in str(exc)
            return "rejected"
    with ThreadPoolExecutor(max_workers=12) as pool:
        results=list(pool.map(consume,range(12)))
    assert results.count("accepted")==1
    assert results.count("rejected")==11
