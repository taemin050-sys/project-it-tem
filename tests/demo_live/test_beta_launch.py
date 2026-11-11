"""Per-release beta configuration never inherits a stale source's flags."""
import json
import os
from pathlib import Path

import pytest

from tests.demo_live.test_bp18_live_launch import root, launch, SHA, private_file, write_policy


def beta_policy(root, **changes):
    values = {"IT_TEM_DERIVED_ENABLED": "YES", "IT_TEM_DERIVED_AUTHORITY_FILE": str(root/"config/derived-authority.json"),
        "IT_TEM_DERIVED_ROOT": str(root/"runtime/protected"), "IT_TEM_DERIVED_FONT": str(root/"fonts/Pretendard.ttf"),
        "IT_TEM_DERIVED_FONT_LICENSE": str(root/"fonts/LICENSE.txt"), "IT_TEM_DERIVED_SOURCE_TREE_SHA": "b"*40,
        "IT_TEM_BP18_LIVE_DUAL_MULTI_RATIO_ENABLED": "YES", "IT_TEM_BP18_9_16_CTA_POLICY": str(root/"config/cta.json"),
        "IT_TEM_BP18_BETA_TYPOGRAPHY_ENABLED": "YES"}
    values.update(changes)
    path=private_file(root/"config/bp18_beta_policies"/(SHA+".env"), "\n".join(f"{k}={v}" for k,v in values.items()))
    return path, values


def test_missing_beta_policy_clears_inherited_flags_without_legacy_digest_drift(root):
    write_policy(root)
    original=launch.configure(root,worker=False)
    os.environ.update({key:"stale" for key in launch.BETA_KEYS})
    assert launch.configure(root,worker=False)==original
    assert not (launch.BETA_KEYS & os.environ.keys())


def test_beta_web_worker_fingerprint_matches_and_new_schema_gate_is_required(root,monkeypatch):
    write_policy(root)
    _, values=beta_policy(root)
    from scripts import bp18_b5_derived_contract as guard
    calls=[]
    def check(given,target,*,activating):
        calls.append((given,target,activating)); return {"required_mode":"LOCAL_PROTECTED_RENDER_V1",
            "release_inventories": {target: {"tree_sha": "b"*40}}}
    monkeypatch.setattr(guard,"required_derived_contract",check)
    web=launch.configure(root,worker=False)
    assert all(os.environ[key]==value for key,value in values.items())
    assert "OPENAI_API_KEY" not in os.environ
    assert launch.configure(root,worker=True)==web
    assert calls==[(root,SHA,True),(root,SHA,True)]
    beta_policy(root,IT_TEM_BP18_BETA_TYPOGRAPHY_ENABLED="NO")
    assert launch.configure(root,worker=False)!=web


def test_beta_tree_must_match_the_approved_source_inventory(root,monkeypatch):
    write_policy(root)
    beta_policy(root)
    from scripts import bp18_b5_derived_contract as guard
    monkeypatch.setattr(guard,"required_derived_contract",lambda *a,**kw:
        {"release_inventories":{SHA:{"tree_sha":"c"*40}}})
    with pytest.raises(launch.LaunchDenied,match="BETA_POLICY_TREE_MISMATCH"):
        launch.configure(root,worker=False)
    assert os.environ["IT_TEM_LIVE_ENABLED"]=="NO"


@pytest.mark.parametrize("changes,code",[
    ({"OPENAI_API_KEY":"never-permitted"},"BETA_POLICY_INVALID"),
    ({"IT_TEM_DERIVED_SOURCE_TREE_SHA":"invalid"},"BETA_POLICY_TREE_INVALID"),
    ({"IT_TEM_DERIVED_ENABLED":"true"},"BETA_POLICY_FLAG_INVALID"),
    ({"IT_TEM_DERIVED_ROOT":"relative"},"BETA_POLICY_PATH_INVALID"),
    ({"IT_TEM_DERIVED_ROOT":"/tmp/../elsewhere"},"BETA_POLICY_PATH_INVALID"),
])
def test_malformed_beta_policy_fails_closed(root,changes,code):
    beta_policy(root,**changes)
    with pytest.raises(launch.LaunchDenied,match=code):launch.read_beta_policy(root,SHA)


def test_beta_duplicate_or_incomplete_policy_never_activates(root):
    path,_=beta_policy(root)
    original=path.read_text()
    path.write_text(original+"\nIT_TEM_DERIVED_ENABLED=NO")
    with pytest.raises(launch.LaunchDenied,match="BETA_POLICY_INVALID"):launch.read_beta_policy(root,SHA)
    path.write_text("IT_TEM_DERIVED_ENABLED=YES")
    with pytest.raises(launch.LaunchDenied,match="BETA_POLICY_INCOMPLETE"):launch.read_beta_policy(root,SHA)
