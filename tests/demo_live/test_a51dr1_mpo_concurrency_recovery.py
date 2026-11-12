"""A51D-R1 C-A differential negatives: durable SQLite token CAS vs ASGI races.

No GCP/Provider, no rights-cleared user assets, no signed SSO or live worker.
The older v2 Owner route is never mutated or approved for production use.
"""
from __future__ import annotations

import asyncio
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

from fastapi.testclient import TestClient
import httpx
import pytest

from demo_staging.app import make_demo_app
from demo_staging.live import a51d_mpo_fixture_bridge as bridge
from demo_staging.live.a51dr1_mpo_selection_journal import (
    MpoSelectionJournal, JournalConflict,
)
from tests.demo_live.test_a51d_mpo_http_fixture_bridge import (
    auth_fixture_app, inspect, choice_of, confirm, create, O,
)
from tests.demo_live.test_a51c_explicit_mpo_ingress import synthetic_mpo
from tests.demo_live.test_http_gateway import photo, login


def multipart(raw,selected):
    return [
        ("product_images",("masked.jpg",raw,"image/jpeg")),
        ("product_images",("same-sku-other-angle.png",
                           photo((52,142,190)),"image/png")),
        ("mpo_choices_json",(None,json.dumps(selected),"application/json")),
    ]


@pytest.mark.parametrize("n", [2, 12])
def test_same_confirmed_token_concurrent_http_post_creates_exactly_one_job(
        auth_fixture_app,monkeypatch,n):
    app,codes=auth_fixture_app
    raw=synthetic_mpo()
    async def scenario():
        transport=httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport,
                                    base_url="http://testserver") as client:
            assert (await client.post("/demo/api/session",
                  json={"invite_code":codes["alice"]},headers=O)).status_code==200
            preview=await client.post("/demo/api/a51d/mpo/preview",
                files={"photo":("masked.jpg",raw,"image/jpeg")},headers=O)
            assert preview.status_code==200
            selected=choice_of(preview.json())
            acknowledged=await client.post("/demo/api/a51d/mpo/confirm",
                json={k:selected[0][k] for k in (
                    "token","selected_frame_index","selected_preview_sha256")},
                headers=O)
            assert acknowledged.status_code==200
            # Force all N asynchronous requests to overlap their reads.
            # The old RLock+await implementation gives N independent HTTP201.
            gates={name:asyncio.Barrier(n) for name in
                   ("masked.jpg","same-sku-other-angle.png")}
            read=bridge._read
            async def collide(upload):
                b=await read(upload)
                if upload.filename in gates:
                    await asyncio.wait_for(
                        gates[upload.filename].wait(),timeout=20)
                return b
            monkeypatch.setattr(bridge,"_read",collide)
            async def submit():
                return await client.post("/demo/api/a51d/mpo/jobs",
                      headers=O,files=multipart(raw,selected),timeout=35)
            results=await asyncio.gather(*(submit() for _ in range(n)))
            status=sorted(x.status_code for x in results)
            assert status==[201]+[409]*(n-1),[(x.status_code,x.text[:120]) for x in results]
            good=[x.json()["job_id"] for x in results if x.status_code==201]
            assert len(good)==1 and app.state.demo_ledger.owns("alice",good[0])
            assert len(list(app.state.job_store.root.iterdir()))==1
            row=app.state.a51dr1_mpo_journal.inspect_state_for_test(
                selected[0]["token"])
            assert row["state"]=="COMMITTED" and row["job_id"]==good[0]
            assert row["upload_request_sha256"]==(
                app.state.job_store.get_job(good[0])["assets"][0]
                ["source_provenance"]["upload_request_sha256"])
            # Rebooted journal independently observes terminal state.
            second=MpoSelectionJournal(app.state.a51dr1_mpo_journal.path)
            assert second.inspect_state_for_test(selected[0]["token"])==row
            return status,good[0]
    status,_=asyncio.run(scenario())
    assert status.count(201)==1


@pytest.mark.parametrize("where",["create_job","claim","settle"])
def test_creation_ownership_or_settlement_failure_blocks_replay(
        auth_fixture_app,monkeypatch,where):
    app,codes=auth_fixture_app
    raw=synthetic_mpo()
    with TestClient(app) as client:
        login(client,codes["alice"])
        choice=choice_of(inspect(client,raw).json())
        assert confirm(client,choice[0]).status_code==200
        if where=="create_job":
            monkeypatch.setattr(app.state.job_store,"create_job",
              lambda *_: (_ for _ in ()).throw(OSError("injected fixture fault")))
        elif where=="claim":
            monkeypatch.setattr(app.state.demo_ledger,"claim",
              lambda *_: (_ for _ in ()).throw(sqlite3.OperationalError(
                  "injected fixture fault")))
        else:
            journal=app.state.a51dr1_mpo_journal
            original=journal.settle
            attempts=[0]
            def fail_once(**kwargs):
                attempts[0]+=1
                if attempts[0]==1:
                    raise sqlite3.OperationalError("injected fixture settlement")
                return original(**kwargs)
            monkeypatch.setattr(journal,"settle",fail_once)
        failure=create(client,raw,choice)
        assert failure.status_code==503,failure.text
        assert create(client,raw,choice).status_code==409
        row=app.state.a51dr1_mpo_journal.inspect_state_for_test(
            choice[0]["token"])
        assert row["state"] in ("FAILED_RETRY_REQUIRED","COMMITTED","RESERVED")
        assert len(list(app.state.job_store.root.iterdir()))<=1
        if where in ("create_job","claim"):
            assert row["state"]=="FAILED_RETRY_REQUIRED"
            assert not list(app.state.job_store.root.iterdir())
        if where=="settle":
            assert row["state"]=="COMMITTED"
            assert len(list(app.state.job_store.root.iterdir()))==1
            assert app.state.demo_ledger.owns("alice",row["job_id"])


def test_expired_confirmed_token_cannot_be_reserved(auth_fixture_app):
    app,codes=auth_fixture_app
    raw=synthetic_mpo()
    with TestClient(app) as client:
        login(client,codes["alice"])
        chosen=choice_of(inspect(client,raw).json())
        assert confirm(client,chosen[0]).status_code==200
        p=app.state.a51dr1_mpo_journal.path
        with sqlite3.connect(p) as db:
            db.execute("UPDATE selection_tokens SET expires_utc=0 WHERE token_sha256=?",
                       (sha256(chosen[0]["token"].encode()).hexdigest(),))
        assert create(client,raw,chosen).status_code==409
        assert not list(app.state.job_store.root.iterdir())


def test_after_reserved_token_process_crash_restarted_app_never_replays_job(
        auth_fixture_app,tmp_path):
    app,codes=auth_fixture_app
    raw=synthetic_mpo()
    with TestClient(app) as client:
        login(client,codes["alice"])
        chosen=choice_of(inspect(client,raw).json())
        assert confirm(client,chosen[0]).status_code==200

    journal=app.state.a51dr1_mpo_journal
    j=chosen[0]
    claims=[{
      "token_sha256":sha256(j["token"].encode()).hexdigest(),
      "source_sha256":sha256(raw).hexdigest(),
      "frame_count":2,"frame_index":1,
      "preview_sha256":j["selected_preview_sha256"],
    }]
    # Crash in another process IMMEDIATELY AFTER durable RESERVED commit,
    # BEFORE JobStore creation. There must be no automatic token release.
    script=(
      "import os,sys\n"
      "from demo_staging.live.a51dr1_mpo_selection_journal import MpoSelectionJournal\n"
      "import json\n"
      "j=MpoSelectionJournal(sys.argv[1]);"
      "j.reserve(actor='alice',claims=json.loads(sys.argv[2]),"
      "request_sha='f'*64);os._exit(53)\n"
    )
    proc=subprocess.run([sys.executable,"-c",script,str(journal.path),
                         json.dumps(claims)],cwd=Path(__file__).resolve().parents[2],
                         capture_output=True,text=True,timeout=15)
    assert proc.returncode==53,(proc.stderr,proc.stdout)
    assert journal.inspect_state_for_test(j["token"])["state"]=="RESERVED"
    assert not list(app.state.job_store.root.iterdir())
    # Simulated restart creates a NEW FastAPI app/ledger on same fixture root.
    restarted=make_demo_app(tmp_path/"runtime",tmp_path/"invites.json",
                            tmp_path/"dist",secure_cookie=False)
    with TestClient(restarted) as client:
        login(client,codes["alice"])
        denied=create(client,raw,chosen)
        assert denied.status_code==409,denied.text
        assert not list(restarted.state.job_store.root.iterdir())
    assert restarted.state.a51dr1_mpo_journal.inspect_state_for_test(
        j["token"])["state"]=="RESERVED"


def test_new_journal_denies_symlink_database(tmp_path):
    real=tmp_path/"real.db"
    with sqlite3.connect(real) as db:
        db.execute("CREATE TABLE a(value INTEGER)")
    symlink=tmp_path/"symlink.db"
    symlink.symlink_to(real)
    with pytest.raises(RuntimeError,match="MPO_JOURNAL_SYMLINK_DENIED"):
        MpoSelectionJournal(symlink)


def test_missing_and_invalid_token_never_publishes_job(auth_fixture_app):
    app,codes=auth_fixture_app
    raw=synthetic_mpo()
    with TestClient(app) as alice:
        login(alice,codes["alice"])
        selected=choice_of(inspect(alice,raw).json())
        assert create(alice,raw,selected).status_code==409
        assert confirm(alice,selected[0]).status_code==200
        invalid=[{**selected[0],"selected_frame_index":0}]
        assert create(alice,raw,invalid).status_code==409
        assert not list(app.state.job_store.root.iterdir())
        assert create(alice,raw,selected).status_code==201
        assert create(alice,raw,selected).status_code==409


def test_two_independent_processes_cannot_reserve_same_durable_token(tmp_path):
    j=MpoSelectionJournal(tmp_path/"separate_test_selection.sqlite")
    token="TEST_ONLY_MULTI_PROCESS_TOKEN_NOT_A_REAL_AUTHORITY"
    preview_sha="a"*64
    original_sha="b"*64
    j.preview(token=token,actor="alice",source_sha=original_sha,frame_count=2,
              previews={0:"c"*64,1:preview_sha},ttl_seconds=300,capacity=24)
    j.confirm(token=token,actor="alice",frame_index=1,preview_sha=preview_sha)
    claim=[{
        "token_sha256":j.digest(token),
        "source_sha256":original_sha,
        "frame_count":2,"frame_index":1,"preview_sha256":preview_sha,
    }]
    child=(
      "import sys,json\n"
      "from demo_staging.live.a51dr1_mpo_selection_journal import "
      "MpoSelectionJournal,JournalConflict\n"
      "j=MpoSelectionJournal(sys.argv[1])\n"
      "try:\n"
      " j.reserve(actor='alice',claims=json.loads(sys.argv[2]),"
      "request_sha='d'*64)\n"
      " print('RESERVED',flush=True)\n"
      "except JournalConflict:\n"
      " print('CONFLICT',flush=True)\n"
    )
    args=[sys.executable,"-c",child,str(j.path),json.dumps(claim)]
    a=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                       text=True,cwd=Path(__file__).resolve().parents[2])
    b=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                       text=True,cwd=Path(__file__).resolve().parents[2])
    aa,ae=a.communicate(timeout=15)
    bb,be=b.communicate(timeout=15)
    assert a.returncode==b.returncode==0,(ae,be)
    assert sorted([aa.strip(),bb.strip()])==["CONFLICT","RESERVED"],(aa,bb)
    assert j.inspect_state_for_test(token)["state"]=="RESERVED"
