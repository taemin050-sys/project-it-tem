"""A51D deployment-sentinel hard cap: NO MONITOR_ONLY paid beta fallback."""
from __future__ import annotations

from pathlib import Path

import pytest

from demo_staging.live.worker import policy_from_env
from demo_staging.live.http_api import web_queue_policy
from demo_staging.live_safety import LiveNotAuthorized
from demo_staging.live.contracts import LiveGateError
from tests.demo_live.test_http_gateway import setup


@pytest.fixture
def beta(monkeypatch):
    env={
      "IT_TEM_A51D_SIGNED_BETA_RUNTIME":"YES",
      "IT_TEM_LIVE_ENABLED":"YES",
      "IT_TEM_LIVE_EXECUTION_APPROVED":"YES",
      "IT_TEM_PROVIDER_READINESS_CONFIRMED":"YES",
      "IT_TEM_LIVE_WEB_QUEUE_ENABLED":"YES",
      "IT_TEM_LIVE_APPROVED_ACTORS":"alice",
      "IT_TEM_TAILNET_AUTH_ENABLED":"YES",
      "IT_TEM_TAILNET_SSO_ONLY":"YES",
      "IT_TEM_A51C_HARD_CAP_ENABLE":"NO",
      "IT_TEM_LIVE_COST_POLICY":"MONITOR_ONLY",
      "OPENAI_API_KEY":"FAKE_NEVER_SENT",
    }
    for k,v in env.items():monkeypatch.setenv(k,v)
    return env


@pytest.mark.parametrize("policy,cap",[
    ("MONITOR_ONLY","NO"),("MONITOR_ONLY","YES"),("HARD_CAP","NO"),
    ("","NO"),("","YES"),
])
def test_signed_beta_worker_queue_and_startup_never_enter_monitor_only(
        beta,monkeypatch,tmp_path,policy,cap):
    monkeypatch.setenv("IT_TEM_LIVE_COST_POLICY",policy)
    monkeypatch.setenv("IT_TEM_A51C_HARD_CAP_ENABLE",cap)
    with pytest.raises(LiveNotAuthorized,match="A51D_BETA_HARD_CAP_MANDATORY"):
        policy_from_env(tmp_path)
    assert web_queue_policy(tmp_path)["enabled"] is False
    # The app refuses to start with changed beta financial policies.
    with pytest.raises(RuntimeError,match="A51D_SIGNED_BETA_STARTUP_MONITOR_ONLY_OR_SSO_BYPASS"):
        setup(tmp_path)


@pytest.mark.parametrize("flag",["IT_TEM_TAILNET_AUTH_ENABLED","IT_TEM_TAILNET_SSO_ONLY"])
def test_signed_beta_startup_never_falls_back_to_unverified_sso(beta,monkeypatch,tmp_path,flag):
    monkeypatch.setenv("IT_TEM_LIVE_COST_POLICY","HARD_CAP")
    monkeypatch.setenv("IT_TEM_A51C_HARD_CAP_ENABLE","YES")
    monkeypatch.setenv(flag,"NO")
    with pytest.raises(RuntimeError,match="A51D_SIGNED_BETA_STARTUP_MONITOR_ONLY_OR_SSO_BYPASS"):
        setup(tmp_path)


def test_signed_beta_hard_cap_config_without_actual_pm_record_still_denied(
        beta,monkeypatch,tmp_path):
    monkeypatch.setenv("IT_TEM_LIVE_COST_POLICY","HARD_CAP")
    monkeypatch.setenv("IT_TEM_A51C_HARD_CAP_ENABLE","YES")
    assert web_queue_policy(tmp_path)["enabled"] is False
    with pytest.raises((LiveGateError,LiveNotAuthorized),
                       match="(A51C_HARD_CAP_|TRUST_CONFIG)"):
        policy_from_env(tmp_path)


def test_b0_legacy_monitor_only_unchanged_when_beta_marker_unset(beta,monkeypatch,tmp_path):
    monkeypatch.setenv("IT_TEM_A51D_SIGNED_BETA_RUNTIME","NO")
    # Existing monitor-only A2-A4 code is not modified by this marker; this
    # does not authorize real model calls without further PM approval.
    p=policy_from_env(tmp_path)
    assert p.monitoring_only is True
    assert p.cost.monitoring_only is True
