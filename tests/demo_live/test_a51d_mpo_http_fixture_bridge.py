"""A51D authenticated candidate HTTP upload→B0 Job provenance. TEST-ONLY.

No actual cosmetics, no real model, no paid API, no live Tailscale listener,
no changes to historical Owner/B0 upload or v2 jobs.
"""
from __future__ import annotations

import base64
from hashlib import sha256
import json

from fastapi.testclient import TestClient
import pytest

from demo_staging.live.a51d_mpo_fixture_bridge import MODE
from tests.demo_live.test_http_gateway import setup,login,photo
from tests.demo_live.test_a51c_explicit_mpo_ingress import synthetic_mpo

O={"Origin":"http://testserver"}


@pytest.fixture
def auth_fixture_app(monkeypatch,tmp_path):
    monkeypatch.setenv("IT_TEM_A51D_MPO_FIXTURE_BRIDGE","YES")
    monkeypatch.setenv("IT_TEM_QA_FIXTURE_ENABLED","YES")
    monkeypatch.setenv("IT_TEM_ENABLE_BILLABLE_TEXT_CALLS","NO")
    monkeypatch.setenv("IT_TEM_A51D_NONDEPLOYABLE_TEST_ONLY","YES")
    for k in ("IT_TEM_A51C_HARD_CAP_ENABLE","IT_TEM_TAILNET_AUTH_ENABLED",
              "IT_TEM_TAILNET_SSO_ONLY","IT_TEM_LIVE_ENABLED",
              "IT_TEM_LIVE_EXECUTION_APPROVED"):
        monkeypatch.setenv(k,"NO")
    return setup(tmp_path)


def inspect(c:TestClient,raw:bytes,filename="masked.jpg"):
    return c.post("/demo/api/a51d/mpo/preview",
        files={"photo":(filename,raw,"image/jpeg")},headers=O)


def create(c,raw,choices,filename="masked.jpg"):
    return c.post("/demo/api/a51d/mpo/jobs",headers=O,
      files=[
        ("product_images",(filename,raw,"image/jpeg")),
        ("product_images",("same-sku-other-angle.png",
                           photo((52,142,190)),"image/png")),
        ("mpo_choices_json",(None,json.dumps(choices),"application/json")),
      ])


def choice_of(preview):
    return [{
        "category":"product",
        "index":0,
        "token":preview["token"],
        "selected_frame_index":1,
        "selected_preview_sha256":preview["frames"][1]["preview_png_sha256"],
    }]


def confirm(c,chosen):
    return c.post("/demo/api/a51d/mpo/confirm",json={
        "token":chosen["token"],
        "selected_frame_index":chosen["selected_frame_index"],
        "selected_preview_sha256":chosen["selected_preview_sha256"],
    },headers=O)


def test_default_off_no_beta_mpo_routes_and_legacy_unchanged(tmp_path,monkeypatch):
    monkeypatch.delenv("IT_TEM_A51D_MPO_FIXTURE_BRIDGE",raising=False)
    app,_=setup(tmp_path)
    with TestClient(app) as client:
        assert client.post("/demo/api/a51d/mpo/preview",files={
            "photo":("a.jpg",synthetic_mpo(),"image/jpeg")
        },headers=O).status_code in (401,404)
    assert "/demo/api/a51d/mpo/preview" not in app.openapi()["paths"]
    assert "/api/v1/jobs" in app.openapi()["paths"]


def test_true_browser_preview_to_authenticated_single_job_provenance(auth_fixture_app):
    app,codes=auth_fixture_app
    raw=synthetic_mpo()
    with TestClient(app) as alice,TestClient(app) as bob:
        assert inspect(alice,raw).status_code==401
        login(alice,codes["alice"]);login(bob,codes["bob"])
        preview=inspect(alice,raw)
        assert preview.status_code==200,preview.text
        body=preview.json()
        assert body["contract"]==MODE
        assert body["source_sha256"]==sha256(raw).hexdigest()
        assert body["source_frame_count"]==2
        assert body["requires_explicit_confirmation"] is True
        assert body["provider_calls"]==0
        assert body["contract_final_owner_approved"] is False
        assert len(body["frames"])==2
        assert body["frames"][0]["preview_png_sha256"]!=body[
            "frames"][1]["preview_png_sha256"]
        for f in body["frames"]:
            b=base64.b64decode(f["preview_data_uri"].split(",",1)[1])
            assert b[:8]==b"\x89PNG\r\n\x1a\n"
            assert sha256(b).hexdigest()==f["preview_png_sha256"]
        chosen=choice_of(body)
        assert confirm(bob,chosen[0]).status_code==409
        assert create(bob,raw,chosen).status_code==409
        assert confirm(alice,chosen[0]).status_code==200
        assert confirm(alice,chosen[0]).status_code==409
        accepted=create(alice,raw,chosen)
        assert accepted.status_code==201,accepted.text
        job=accepted.json()
        assert job["status"]=="INPUTS_VALIDATED"
        assert len(job["assets"])==2
        mpo=job["assets"][0]["source_provenance"]
        assert mpo["original_sha256"]==sha256(raw).hexdigest()
        assert mpo["selected_frame"]==1
        assert mpo["selected_frame_preview_png_sha256"]==chosen[0][
            "selected_preview_sha256"]
        assert mpo["source_frame_count"]==2
        assert mpo["color_normalization_contract"]=="EXIF_UPRIGHT_ICC_TO_SRGB_V2"
        assert mpo["brand_rights_accepted"] is False
        assert mpo["external_provider_transfer_permitted"] is False
        assert job["assets"][0]["content_type"]=="image/jpeg"
        assert app.state.demo_ledger.owns("alice",job["job_id"])
        assert not app.state.demo_ledger.owns("bob",job["job_id"])
        assert alice.get(f"/api/v1/jobs/{job['job_id']}").status_code==200
        assert bob.get(f"/api/v1/jobs/{job['job_id']}").status_code==404
        assert create(alice,raw,chosen).status_code==409
        assert not any(
            sha256(p.read_bytes()).hexdigest()==sha256(raw).hexdigest()
            for p in (app.state.job_store.root / job["job_id"]).iterdir()
            if p.suffix==".jpg"
        )


@pytest.mark.parametrize("case",["no_choice","wrong_index","wrong_sha",
                                  "wrong_token","wrong_preview","wrong_category",
                                  "duplicate","unspecified_second"])
def test_invalid_or_missing_choice_fails_closed_before_b0_job(
    auth_fixture_app,case):
    app,codes=auth_fixture_app
    raw=synthetic_mpo()
    with TestClient(app) as alice:
        login(alice,codes["alice"])
        body=inspect(alice,raw).json()
        choices=choice_of(body)
        assert confirm(alice,choices[0]).status_code==200
        if case=="no_choice":choices=[]
        elif case=="wrong_index":choices[0]["index"]=1
        elif case=="wrong_sha":raw=synthetic_mpo(colors=((1,2,3),(4,5,6)))
        elif case=="wrong_token":choices[0]["token"]="X"*43
        elif case=="wrong_preview":choices[0]["selected_preview_sha256"]="0"*64
        elif case=="wrong_category":choices[0]["category"]="other"
        elif case=="duplicate":choices=choices*2
        elif case=="unspecified_second":
            choices[0]["selected_frame_index"]=0  # SHA still frame 1
        before=set(p.name for p in app.state.job_store.root.iterdir())
        resp=create(alice,raw,choices)
        assert resp.status_code in (409,422),resp.text
        assert set(p.name for p in app.state.job_store.root.iterdir())==before
        assert "sk-" not in resp.text


def test_plain_png_two_photos_use_beta_fixture_route_without_mpo_tokens(
        auth_fixture_app):
    app,codes=auth_fixture_app
    with TestClient(app) as alice:
        login(alice,codes["alice"])
        files=[
            ("product_images",("a.png",photo((100,110,120)),"image/png")),
            ("product_images",("b.png",photo((60,70,80)),"image/png")),
            ("mpo_choices_json",(None,"[]","application/json")),
        ]
        resp=alice.post("/demo/api/a51d/mpo/jobs",headers=O,files=files)
        assert resp.status_code==201,resp.text
        assert len(resp.json()["assets"])==2
        assert all(a.get("source_provenance") is None
                   for a in resp.json()["assets"])


@pytest.mark.parametrize("flag",[
    "IT_TEM_LIVE_ENABLED","IT_TEM_LIVE_EXECUTION_APPROVED",
    "IT_TEM_TAILNET_AUTH_ENABLED","IT_TEM_TAILNET_SSO_ONLY",
    "IT_TEM_A51C_HARD_CAP_ENABLE",
])
def test_never_install_test_route_with_live_sso_or_billing_enabled(tmp_path,monkeypatch,flag):
    monkeypatch.setenv("IT_TEM_A51D_MPO_FIXTURE_BRIDGE","YES")
    monkeypatch.setenv("IT_TEM_QA_FIXTURE_ENABLED","YES")
    monkeypatch.setenv("IT_TEM_ENABLE_BILLABLE_TEXT_CALLS","NO")
    monkeypatch.setenv("IT_TEM_A51D_NONDEPLOYABLE_TEST_ONLY","YES")
    for k in ("IT_TEM_A51C_HARD_CAP_ENABLE","IT_TEM_TAILNET_AUTH_ENABLED",
              "IT_TEM_TAILNET_SSO_ONLY","IT_TEM_LIVE_ENABLED",
              "IT_TEM_LIVE_EXECUTION_APPROVED"):
        monkeypatch.setenv(k,"NO")
    monkeypatch.setenv(flag,"YES")
    with pytest.raises(RuntimeError,match="(A51D_MPO_FIXTURE_BRIDGE_NEVER_ACTIVATES|TAILNET_AUTH_CONFIG_MISSING|TAILNET_SSO_ONLY_REQUIRES_SIGNED_AUTH)"):
        setup(tmp_path)

def test_authenticated_actor_must_confirm_action_before_any_mpo_job(
        auth_fixture_app):
    app,codes=auth_fixture_app
    raw=synthetic_mpo()
    with TestClient(app) as client:
        login(client,codes["alice"])
        preview=inspect(client,raw).json()
        selected=choice_of(preview)
        assert create(client,raw,selected).status_code==409
        assert not list(app.state.job_store.root.iterdir())
        assert confirm(client,selected[0]).status_code==200
        assert create(client,raw,selected).status_code==201
