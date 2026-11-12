"""B5-P1-02: Epoch-allowed pre-SSO release must FAIL CLOSED before rollback.

All tests are synthetic cloned files/SQLite. No paid provider or real release.
"""
import hashlib
import json
import sqlite3
from pathlib import Path
import pytest

from scripts import bp18_b5_release_prestart as guard

CURRENT="6977cd80e29fb2d3702fccd50c520837196b5f40"
PRE_SSO="4ae7bf3817ab253dbbb5275b9585149e34544471"
NEXT="f"*40
SOURCE_CONTENTS={
  "demo_staging/app.py":b"# IT_TEM_TAILNET_SSO_ONLY TAILNET_SSO_ONLY_HOST_NOT_PINNED\n",
  "demo_staging/tailnet_assertion.py":b"# TAILNET_ASSERTION_HOST_MISMATCH\n",
  "scripts/tailnet_sso_gateway.py":b"# TAILNET_EXPECTED_HOST\n",
  "app/src/demo/DemoGate.tsx":b"// VITE_IT_TEM_SSO_ONLY\n",
}
EXPECTED="macstudio-macstudio.tail17dfff.ts.net:10500"


def fixture(tmp_path, *, selected=CURRENT):
    root=tmp_path/"clone"
    (root/"config").mkdir(parents=True)
    (root/"releases").mkdir()
    (root/"runtime/live").mkdir(parents=True)
    for sha in (CURRENT,PRE_SSO,NEXT):
        base=root/"releases"/sha
        (base/"demo_staging/live").mkdir(parents=True)
        (base/"demo_staging/live/store.py").write_text("# fixture only")
        (base/"SOURCE_SHA.txt").write_text(sha)
        for name, data in SOURCE_CONTENTS.items():
            if sha==PRE_SSO and name=="demo_staging/app.py":
                data=b"# OLD_SOURCE_WITHOUT_SIGNED_SSO_REQUIREMENT"
            p=base/name
            p.parent.mkdir(parents=True,exist_ok=True)
            p.write_bytes(data)
    (root/"repo").symlink_to("releases/"+selected)
    (root/"config/epoch_capable_shas.txt").write_text(
       CURRENT+"\n"+PRE_SSO+"\n"+NEXT+"\n")
    with sqlite3.connect(root/"runtime/live/live.sqlite") as c:
        c.execute("CREATE TABLE live_policy_activation(singleton INT PRIMARY KEY,epoch INT,policy_version TEXT,policy_sha TEXT)")
        c.execute("INSERT INTO live_policy_activation VALUES(1,1,'v1',?)",("a"*64,))
    with sqlite3.connect(root/"runtime/live/queue.sqlite") as c:
        c.execute("CREATE TABLE queued_ops(state TEXT)")
    return root


def contract(root,*,allowed=(CURRENT,NEXT)):
    verified={}
    for sha in allowed:
        verified[sha]={
          name:hashlib.sha256((root/"releases"/sha/name).read_bytes()).hexdigest()
          for name in guard.SSO_SOURCE_FILES
        }
    p=root/guard.AUTH_CONTRACT_FILE
    p.write_text(json.dumps({"version":1,"required_mode":"TAILNET_SSO_ONLY",
        "expected_host":EXPECTED,"verified_sources":verified}))
    p.chmod(0o600)
    return p


def test_p1_02_epoch_allowed_old_pre_sso_is_denied_before_web_start(tmp_path):
    root=fixture(tmp_path,selected=CURRENT)
    contract(root)
    assert guard.validate(root,mode="web",port=0)["required_auth"]=="TAILNET_SSO_ONLY"
    before=(root/"runtime/live/live.sqlite").read_bytes()
    with pytest.raises(guard.ReleaseUnsafe,match="SSO_INCOMPATIBLE_RELEASE_DENIED"):
        guard.validate(root,mode="web",port=0,target_override=PRE_SSO)
    assert (root/"runtime/live/live.sqlite").read_bytes()==before
    assert (root/"repo").readlink()==Path("releases/"+CURRENT)


def test_p1_02_targeted_success_retains_epoch_and_sso(tmp_path):
    root=fixture(tmp_path)
    contract(root)
    item=guard.validate(root,mode="web",port=0,target_override=NEXT)
    assert item["release"]==NEXT and item["policy_epoch"]==1
    assert item["required_auth"]=="TAILNET_SSO_ONLY"


def test_p1_02_manifest_tampering_and_stale_code_denied(tmp_path):
    root=fixture(tmp_path)
    contract(root)
    p=root/"releases"/CURRENT/"demo_staging/app.py"
    p.write_text("IT_TEM_TAILNET_SSO_ONLY but changed semantics")
    with pytest.raises(guard.ReleaseUnsafe,match="SSO_AUTH_SOURCE_PROVENANCE_INVALID"):
        guard.validate(root,mode="web",port=0)


def test_p1_02_old_pre_sso_cannot_be_allowed_by_operator_manifest_alone(tmp_path):
    root=fixture(tmp_path)
    contract(root,allowed=(CURRENT,PRE_SSO))
    with pytest.raises(guard.ReleaseUnsafe,match="SSO_REQUIRED_AUTH_CODE_MISSING"):
        guard.validate(root,mode="web",port=0,target_override=PRE_SSO)


@pytest.mark.parametrize("kind",["missing","invalid","perms","host"])
def test_p1_02_protected_contract_fail_closed(tmp_path,monkeypatch,kind):
    root=fixture(tmp_path)
    p=contract(root)
    if kind=="missing":
        p.unlink()
        monkeypatch.setattr(guard,"PRODUCTION_ROOT",root)
    elif kind=="invalid":p.write_text("not json")
    elif kind=="perms":p.chmod(0o666)
    else:
        data=json.loads(p.read_text())
        data["expected_host"]="evil.invalid:10500"
        p.write_text(json.dumps(data))
    with pytest.raises(guard.ReleaseUnsafe,match="SSO_REQUIRED_AUTH_CONTRACT_INVALID"):
        guard.validate(root,mode="web",port=0)


@pytest.mark.parametrize("a,b,c",[("YES","YES",EXPECTED),("NO","YES",EXPECTED),
                                   ("YES","NO",EXPECTED),("YES","YES","host.invalid:10500")])
def test_p1_02_service_environment_must_match(tmp_path,monkeypatch,a,b,c):
    root=fixture(tmp_path)
    contract(root)
    monkeypatch.setenv("IT_TEM_TAILNET_AUTH_ENABLED",a)
    monkeypatch.setenv("IT_TEM_TAILNET_SSO_ONLY",b)
    monkeypatch.setenv("IT_TEM_TAILNET_EXPECTED_HOST",c)
    if a==b=="YES" and c==EXPECTED:
        assert guard.validate(root,mode="web",port=18100)["required_auth"]=="TAILNET_SSO_ONLY"
    else:
        with pytest.raises(guard.ReleaseUnsafe,match="SSO_REQUIRED_RUNTIME_ENV_MISMATCH"):
            guard.validate(root,mode="web",port=18100)
