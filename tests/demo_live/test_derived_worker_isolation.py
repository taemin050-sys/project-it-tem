"""Credential-free renderer startup/claim boundaries, without Provider calls."""
from pathlib import Path
import os
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

import pytest

from demo_staging.live.contracts import LiveGateError
from demo_staging.live.derived_store import DerivedStore,LOCAL_RENDER_PROTOCOL,migrate_derived_schema


CREDENTIALS=("OPENAI_API_KEY","ANTHROPIC_API_KEY","GOOGLE_API_KEY","GEMINI_API_KEY","CREDENTIALS_DIRECTORY")
REQUIRED=("IT_TEM_DERIVED_AUTHORITY_FILE","IT_TEM_DERIVED_ROOT","IT_TEM_DERIVED_FONT",
          "IT_TEM_DERIVED_FONT_LICENSE","IT_TEM_DERIVED_SOURCE_TREE_SHA")


def no_credentials(monkeypatch):
    for key in CREDENTIALS:
        monkeypatch.delenv(key,raising=False)


def test_import_does_not_initialize_provider_sdk_paid_queue_or_paid_worker():
    root=Path(__file__).resolve().parents[2]
    script="""import importlib.abc,sys
forbidden=('openai','src.image_generation.openai_images','src.image_generation.api_image_processor',
           'demo_staging.live.worker','demo_staging.live.queue')
class Deny(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if any(fullname==name or fullname.startswith(name+'.') for name in forbidden):
   raise AssertionError('Provider or paid queue import: '+fullname)
sys.meta_path.insert(0,Deny())
import demo_staging.live.derived_worker
assert not any(name in sys.modules for name in forbidden)
print('LOCAL_IMPORT_ONLY')
"""
    env=dict(os.environ)
    for key in CREDENTIALS:env.pop(key,None)
    completed=subprocess.run([sys.executable,"-B","-c",script],cwd=root,env=env,capture_output=True,text=True)
    assert completed.returncode==0,completed.stderr
    assert completed.stdout.strip()=="LOCAL_IMPORT_ONLY"


def test_configured_runtime_startup_does_not_load_provider_or_paid_dispatch(tmp_path):
    root=Path(__file__).resolve().parents[2]
    runtime=tmp_path/"runtime"
    (runtime/"live").mkdir(parents=True)
    from demo_staging.live.store import LiveStore
    LiveStore(runtime/"live/live.sqlite")
    migrate_derived_schema(runtime/"live/live.sqlite")
    authority=tmp_path/"authority.json"
    authority.write_text('{"schema":"bp18-derived-authority-v1","revision":1,"business_roles":{},"delegations":[]}')
    authority.chmod(0o600)
    script="""import importlib.abc,sys
from pathlib import Path
forbidden=('openai','src.image_generation.openai_images','src.image_generation.api_image_processor',
           'demo_staging.live.worker','demo_staging.live.queue')
class Deny(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if any(fullname==name or fullname.startswith(name+'.') for name in forbidden):
   raise AssertionError('Provider or paid queue import: '+fullname)
sys.meta_path.insert(0,Deny())
from demo_staging.live.derived_worker import service_from_runtime
service=service_from_runtime(Path(sys.argv[1]))
assert not any(name in sys.modules for name in forbidden)
assert not (Path(sys.argv[1])/'live'/'queue.sqlite').exists()
print('LOCAL_STARTUP_ONLY')
"""
    env=dict(os.environ)
    for key in CREDENTIALS:env.pop(key,None)
    env.update(IT_TEM_DERIVED_AUTHORITY_FILE=str(authority),
               IT_TEM_DERIVED_ROOT=str(tmp_path/"derived"),
               IT_TEM_DERIVED_FONT=str(root/"app/node_modules/pretendard/dist/public/variable/PretendardVariable.ttf"),
               IT_TEM_DERIVED_FONT_LICENSE=str(root/"app/node_modules/pretendard/dist/LICENSE.txt"),
               IT_TEM_DERIVED_SOURCE_TREE_SHA="a"*40)
    completed=subprocess.run([sys.executable,"-B","-c",script,str(runtime)],cwd=root,env=env,capture_output=True,text=True)
    assert completed.returncode==0,completed.stderr
    assert completed.stdout.strip()=="LOCAL_STARTUP_ONLY"


@pytest.mark.parametrize("key",CREDENTIALS)
def test_credential_presence_rejected_before_claim_or_service_access(monkeypatch,key):
    from demo_staging.live.derived_worker import run_once
    no_credentials(monkeypatch)
    monkeypatch.setenv(key,"sentinel-never-printed")
    # Missing attributes deliberately ensure no queue/DB/service access occurs.
    with pytest.raises(LiveGateError,match="DERIVED_WORKER_CREDENTIALS_FORBIDDEN"):
        run_once(SimpleNamespace(),worker_id="local-one")


def test_runtime_root_must_be_absolute_and_migration_explicit(tmp_path,monkeypatch):
    from demo_staging.live.derived_worker import service_from_runtime
    no_credentials(monkeypatch)
    with pytest.raises(LiveGateError,match="DERIVED_EXPLICIT_RUNTIME_REQUIRED"):
        service_from_runtime(Path("relative-runtime"))
    runtime=tmp_path/"runtime";runtime.mkdir()
    with pytest.raises(LiveGateError,match="DERIVED_DATABASE_PATH_INVALID"):
        service_from_runtime(runtime)
    assert not (runtime/"live").exists()


def test_missing_worker_config_does_not_create_legacy_job_schema(tmp_path,monkeypatch):
    from demo_staging.live.derived_worker import service_from_runtime
    no_credentials(monkeypatch)
    for key in REQUIRED:monkeypatch.delenv(key,raising=False)
    runtime=tmp_path/"runtime";(runtime/"live").mkdir(parents=True)
    database=runtime/"live/live.sqlite"
    migrate_derived_schema(database)
    before=database.read_bytes()
    with pytest.raises(LiveGateError,match="DERIVED_WORKER_CONFIGURATION_REQUIRED"):
        service_from_runtime(runtime)
    assert database.read_bytes()==before
    assert not (runtime/"jobs").exists()
    with sqlite3.connect(database) as c:
        assert c.execute("SELECT 1 FROM sqlite_master WHERE name='live_jobs'").fetchone() is None


def test_billing_unknown_pauses_local_claim_without_provider_or_data_writes(tmp_path,monkeypatch):
    from demo_staging.live.derived_worker import run_once
    no_credentials(monkeypatch)
    database=tmp_path/"local.sqlite";migrate_derived_schema(database)
    store=DerivedStore(database)
    # An unclaimed empty ledger is enough to verify the UNKNOWN gate is before
    # its write transaction and before any service context or asset access.
    before=database.read_bytes()
    service=SimpleNamespace(store=store,billing_unknown=lambda:True)
    assert run_once(service,worker_id="local-one") is None
    assert database.read_bytes()==before


def test_local_claim_rejects_paid_or_unknown_protocol(tmp_path):
    database=tmp_path/"local.sqlite";migrate_derived_schema(database)
    store=DerivedStore(database)
    with pytest.raises(LiveGateError,match="DERIVED_PROTOCOL_UNSUPPORTED"):
        store.claim_render(worker_id="old-paid-worker",billing_unknown=False,protocol="LIVE_DUAL_V1")
    assert LOCAL_RENDER_PROTOCOL=="LOCAL_PROTECTED_RENDER_V1"


def test_production_runtime_alias_cannot_bypass_release_lease(tmp_path,monkeypatch):
    from demo_staging.live import derived_worker as worker
    root=tmp_path/"production-clone";(root/"runtime").mkdir(parents=True)
    monkeypatch.setattr(worker,"PRODUCTION_ROOT",root)
    alias=root/"runtime/../runtime"
    assert alias.resolve()==root/"runtime"
    with pytest.raises(LiveGateError,match="DERIVED_EXPLICIT_RUNTIME_REQUIRED"):
        with worker.protected_release_lease(alias):pytest.fail("Production alias entered sandbox branch")


@pytest.mark.parametrize("web_matches",[True,False])
def test_production_renderer_reuses_web_f09_policy_without_key_or_paid_dispatch(tmp_path,monkeypatch,web_matches):
    import fcntl
    from demo_staging.live import derived_worker as worker
    from deploy.systemd import bp18_live_launch as launch
    from tests.demo_live.test_bp18_live_launch import private_file,write_policy,SHA

    monkeypatch.setattr(os,"environ",dict(os.environ))

    root=tmp_path/"production-clone";root.mkdir(mode=0o700)
    runtime=root/"runtime";runtime.mkdir()
    release=root/"releases"/SHA;release.mkdir(parents=True)
    (release/"SOURCE_SHA.txt").write_text(SHA)
    (root/"repo").symlink_to("releases/"+SHA)
    private_file(root/"config/bp18_tailnet_roles.json",'{"bp18_b_exobiz7":"admin","bp18_b_taemin":"evaluator"}')
    write_policy(root)
    monkeypatch.setattr(worker,"PRODUCTION_ROOT",root)
    monkeypatch.setattr(worker,"__file__",str(release/"demo_staging/live/derived_worker.py"))
    no_credentials(monkeypatch)
    for key in ("IT_TEM_BP18_F09_REQUIRED","IT_TEM_BP18_F11_ENABLED","IT_TEM_TEXT_MODEL"):
        monkeypatch.delenv(key,raising=False)
    monkeypatch.setenv("IT_TEM_TAILNET_AUTH_ENABLED","YES")
    monkeypatch.setenv("IT_TEM_TAILNET_SSO_ONLY","YES")
    monkeypatch.setenv("IT_TEM_TAILNET_EXPECTED_HOST",launch.HOST)
    # Full source/schema contract validation has separate clone tests. Here
    # isolate the process boundary: actual configure() must pin the same F09
    # model/policy as web, never load a credential or use worker=True.
    monkeypatch.setattr(launch,"read_beta_policy",lambda root,sha:{"IT_TEM_DERIVED_ENABLED":"YES"})
    monkeypatch.setattr(launch,"validate_beta_source",lambda *args:None)
    guard_calls=[]
    def guard(command,**kwargs):
        guard_calls.append(command)
        assert command[:4]==["/usr/bin/python3","-I","-S","-B"]
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(worker.subprocess,"run",guard)
    original_configure=launch.configure
    configured=[]
    def configure(root,*,worker):
        assert worker is False
        fingerprint=original_configure(root,worker=worker)
        configured.append(fingerprint)
        return fingerprint
    monkeypatch.setattr(launch,"configure",configure)
    web_checks=[]
    def web_policy(root,fingerprint):
        assert fingerprint==configured[-1]
        assert os.environ["IT_TEM_BP18_F11_ENABLED"]=="YES"
        assert os.environ["IT_TEM_BP18_F09_REQUIRED"]=="YES"
        assert os.environ["IT_TEM_BP18_REVIEW_POLICY_ID"]=="bp18-f09-two-stage-policy-v2"
        assert os.environ["IT_TEM_TEXT_MODEL"]=="gpt-6-luna"
        assert os.environ["IT_TEM_ENABLE_BILLABLE_TEXT_CALLS"]=="NO"
        assert not any(os.environ.get(key) for key in CREDENTIALS)
        web_checks.append(fingerprint)
        if not web_matches:raise launch.LaunchDenied("B_WEB_WORKER_POLICY_MISMATCH")
    monkeypatch.setattr(launch,"require_web_policy",web_policy)
    if not web_matches:
        with pytest.raises(launch.LaunchDenied,match="B_WEB_WORKER_POLICY_MISMATCH"):
            with worker.protected_release_lease(runtime):pytest.fail("Mismatched web policy was admitted")
    else:
        with worker.protected_release_lease(runtime):
            assert os.environ["IT_TEM_DEMO_CODE_SHA"]==SHA
            # The real shared B5 operator lock remains held across rendering.
            with (root/"config/.b5_operator_control.lock").open("rb") as descriptor:
                with pytest.raises(BlockingIOError):
                    fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB)
    assert len(guard_calls)==len(configured)==len(web_checks)==1
