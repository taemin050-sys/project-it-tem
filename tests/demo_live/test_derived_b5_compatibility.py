"""Local cloned release/schema rehearsals. No GCP, Provider, or real runtime IO."""
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess

import pytest

from demo_staging.live.derived_store import DerivedStore, migrate_derived_schema
from scripts import bp18_b5_derived_contract as derived
from scripts import bp18_b5_release_prestart as guard


SOURCE=Path(__file__).resolve().parents[2]
D2="d2e82bc7871d14223d9ace9c13a906cbe3bc2703"


def git(repo,*args):
    return subprocess.check_output(["git","-C",str(repo),*args],text=True).strip()


def dump_legacy(database):
    with sqlite3.connect(database) as c:
        return {name:c.execute('SELECT * FROM "'+name+'" ORDER BY rowid').fetchall()
                for name, in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'live_derived_%' AND name NOT LIKE 'sqlite_%'")}


@pytest.fixture
def pair(tmp_path):
    repo=tmp_path/"source";repo.mkdir()
    git(repo,"init","-q")
    for name in set(guard.DUAL_SOURCE_FILES)|set(derived.SOURCE_MARKERS):
        path=repo/name;path.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(SOURCE/name,path)
    (repo/"README.md").write_text("Synthetic compatible rollback\n")
    git(repo,"add",".")
    identity=("-c","user.name=Local B5 fixture","-c","user.email=fixture@example.invalid")
    git(repo,*identity,"commit","-qm","Synthetic compatible rollback")
    rollback=git(repo,"rev-parse","HEAD")
    (repo/"README.md").write_text("Synthetic compatible forward\n")
    git(repo,"add","README.md");git(repo,*identity,"commit","-qm","Synthetic compatible forward")
    forward=git(repo,"rev-parse","HEAD")
    root=tmp_path/"b-clone";(root/"config").mkdir(parents=True)
    for commit in (rollback,forward):
        release=root/"releases"/commit;release.mkdir(parents=True)
        for name in git(repo,"ls-tree","-r","--name-only",commit).splitlines():
            path=release/name;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(subprocess.check_output(["git","-C",str(repo),"show",f"{commit}:{name}"]))
        (release/"SOURCE_SHA.txt").write_text(commit+"\n")
    database=root/"runtime/live/live.sqlite";database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as c:
        c.executescript("CREATE TABLE live_jobs(job_id TEXT,actor TEXT); INSERT INTO live_jobs VALUES('protected-job','owner');"
                       "CREATE TABLE live_image_attempts(attempt_id TEXT,receipt TEXT); INSERT INTO live_image_attempts VALUES('historical-provider','original-receipt');")
    artifacts=root/"runtime/live/outputs/protected-job";artifacts.mkdir(parents=True)
    (artifacts/"image.png").write_bytes(b"historical-original-provider-image")
    (artifacts/"owner_candidate_receipt.json").write_bytes(b'{"scope":"historical"}')
    before=dump_legacy(database)
    artifact_hashes={path.name:sha256(path.read_bytes()).hexdigest() for path in artifacts.iterdir()}
    migrate_derived_schema(database,expected_db_sha256=sha256(database.read_bytes()).hexdigest())
    records={role:derived.inspect_source(repo,root,commit)[0] for role,commit in (("forward",forward),("rollback",rollback))}
    approval={"version":1,"required_mode":derived.DERIVED_PROTOCOL,"approval_reference":"SYNTHETIC_LOCAL_ONLY",**records}
    contract=derived.prepare_contract(repo,root,approval)
    installed=root/derived.DERIVED_CONTRACT_FILE;installed.write_text(json.dumps(contract));installed.chmod(0o600)
    return {"root":root,"repo":repo,"forward":forward,"rollback":rollback,"approval":approval,
            "contract":contract,"database":database,"legacy":before,"artifacts":artifact_hashes}


def test_migration_and_both_compatible_releases_preserve_legacy_and_artifacts(pair):
    database=pair["database"];root=pair["root"]
    assert dump_legacy(database)==pair["legacy"]
    before=database.read_bytes()
    for role in ("forward","rollback"):
        assert derived.required_derived_contract(root,pair[role])["required_mode"]==derived.DERIVED_PROTOCOL
        DerivedStore(database)
    assert database.read_bytes()==before
    assert {path.name:sha256(path.read_bytes()).hexdigest() for path in (root/"runtime/live/outputs/protected-job").iterdir()}==pair["artifacts"]


def test_historical_d2_rollback_is_rejected_after_even_empty_schema_migration(pair):
    with pytest.raises(guard.ReleaseUnsafe,match="DERIVED_INCOMPATIBLE_RELEASE_DENIED"):
        derived.required_derived_contract(pair["root"],D2)
    with sqlite3.connect(pair["database"]) as c:
        for table in derived.TABLES:assert c.execute("SELECT COUNT(*) FROM "+table).fetchone()[0]==0


def test_migrated_schema_cannot_start_without_operator_contract(pair):
    (pair["root"]/derived.DERIVED_CONTRACT_FILE).unlink()
    with pytest.raises(guard.ReleaseUnsafe,match="DERIVED_REQUIRED_CONTRACT_INVALID"):
        derived.required_derived_contract(pair["root"],pair["forward"])


def test_legacy_before_migration_keeps_existing_b5_gate(tmp_path):
    (tmp_path/"runtime/live").mkdir(parents=True)
    with sqlite3.connect(tmp_path/"runtime/live/live.sqlite") as c:c.execute("CREATE TABLE live_jobs(id TEXT)")
    assert derived.required_derived_contract(tmp_path,D2) is None


@pytest.mark.parametrize("mutation",["drop_trigger","replace_trigger","drop_index","extra_index","alter_table","partial_table","extra_table"])
def test_schema_trigger_index_or_table_tampering_fails_closed(pair,mutation):
    with sqlite3.connect(pair["database"]) as c:
        if mutation=="drop_trigger":c.execute("DROP TRIGGER live_derived_reviews_delete_denied")
        elif mutation=="replace_trigger":
            c.execute("DROP TRIGGER live_derived_reviews_delete_denied")
            c.execute("CREATE TRIGGER live_derived_reviews_delete_denied BEFORE DELETE ON live_derived_reviews BEGIN SELECT 1; END")
        elif mutation=="drop_index":c.execute("DROP INDEX live_derived_claim")
        elif mutation=="extra_index":c.execute("CREATE INDEX live_derived_unapproved ON live_derived_renders(job_id)")
        elif mutation=="alter_table":c.execute("ALTER TABLE live_derived_renders ADD COLUMN injected TEXT")
        elif mutation=="partial_table":c.execute("DROP TABLE live_derived_reviews")
        else:c.execute("CREATE TABLE live_derived_unapproved(value TEXT)")
    with pytest.raises(guard.ReleaseUnsafe,match="DERIVED_RUNTIME_SCHEMA_(INCOMPATIBLE|PARTIAL)"):
        derived.required_derived_contract(pair["root"],pair["forward"])


@pytest.mark.parametrize("target",["renderer","worker","untracked","symlink","extra_directory"])
def test_code_inventory_and_protocol_tampering_fails_closed(pair,target):
    release=pair["root"]/"releases"/pair["forward"]
    if target in ("renderer","worker"):
        path=release/("src/image_generation/protected_product.py" if target=="renderer" else "demo_staging/live/derived_worker.py")
        path.write_bytes(path.read_bytes()+b"\n# Unapproved change\n")
    elif target=="untracked":(release/"unapproved.pth").write_text("unapproved startup hook")
    elif target=="extra_directory":(release/"unapproved-empty-directory").mkdir()
    else:(release/"unapproved-link").symlink_to(release/"README.md")
    with pytest.raises(guard.ReleaseUnsafe):derived.required_derived_contract(pair["root"],pair["forward"])


def test_all_semantic_source_and_inventory_hashes_are_location_independent(pair,tmp_path):
    relocated=tmp_path/"relocated-control-root";shutil.copytree(pair["root"],relocated)
    for role in ("forward","rollback"):
        a=derived.inspect_source(pair["repo"],pair["root"],pair[role])
        b=derived.inspect_source(pair["repo"],relocated,pair[role])
        assert a==b
    assert derived.required_derived_contract(relocated,pair["forward"])==pair["contract"]


def test_prepare_rejects_stale_operator_fingerprint(pair):
    approval=json.loads(json.dumps(pair["approval"]))
    approval["forward"]["schema_sha256"]="0"*64
    with pytest.raises(guard.ReleaseUnsafe,match="DERIVED_APPROVED_SOURCE_EVIDENCE_MISMATCH"):
        derived.prepare_contract(pair["repo"],pair["root"],approval)


def test_prepare_requires_explicit_distinct_pair_and_fails_for_legacy_source(pair):
    same={**pair["approval"],"rollback":pair["approval"]["forward"]}
    with pytest.raises(guard.ReleaseUnsafe,match="DERIVED_DISTINCT_SOURCE_PAIR_REQUIRED"):
        derived.prepare_contract(pair["repo"],pair["root"],same)
    release=pair["root"]/"releases"/pair["rollback"]
    (release/"demo_staging/live/derived_worker.py").unlink()
    with pytest.raises((guard.ReleaseUnsafe,OSError)):
        derived.prepare_contract(pair["repo"],pair["root"],pair["approval"])


def test_schema_parser_never_evaluates_candidate_python(tmp_path):
    canary=tmp_path/"candidate-executed"
    raw=(SOURCE/"demo_staging/live/derived_store.py").read_bytes()
    schema=derived.schema_from_source(raw+b"\nopen("+repr(str(canary)).encode()+b",'w').write('unsafe')\n")
    assert len(schema["objects"])==11
    assert not canary.exists()


def test_runtime_contract_verification_cli_is_read_only(pair,capsys):
    before=pair["database"].read_bytes()
    args=["--git-repo",str(pair["repo"]),"--staging-root",str(pair["root"]),"verify"]
    assert derived.main([*args,"--target",pair["forward"]])==0
    assert "BP18_DERIVED_CONTRACT_VERIFIED" in capsys.readouterr().out
    assert derived.main([*args,"--target",D2])==78
    assert "DERIVED_INCOMPATIBLE_RELEASE_DENIED" in capsys.readouterr().err
    assert pair["database"].read_bytes()==before


def test_fixed_production_cli_cannot_override_runtime_root(pair,monkeypatch,capsys):
    # This monkeypatch affects only a disposable local fixture. The actual CLI
    # has no root override option and is intended for systemd ExecStartPre.
    monkeypatch.setattr(derived._guard,"PRODUCTION_ROOT",pair["root"])
    assert derived.main(["--target",pair["forward"],"--activating"])==0
    assert "BP18_DERIVED_PRESTART_PASS" in capsys.readouterr().out
    assert derived.main(["--target",D2,"--activating"])==78
    assert "DERIVED_INCOMPATIBLE_RELEASE_DENIED" in capsys.readouterr().err
    assert derived.main(["--target",pair["forward"],"--staging-root",str(pair["root"])])==78
    assert "DERIVED_FIXED_RUNTIME_ROOT_REQUIRED" in capsys.readouterr().err


def test_standalone_control_copy_runs_with_isolated_stdlib_only(pair,tmp_path):
    control=tmp_path/"trusted-control";control.mkdir()
    # A cloned guard root is embedded only in this test copy. No production
    # source, actual runtime, credential, or Provider is accessed.
    raw=(SOURCE/"scripts/bp18_b5_release_prestart.py").read_text()
    (control/"bp18_release_prestart.py").write_text(raw.replace(str(guard.PRODUCTION_ROOT),str(pair["root"])))
    shutil.copyfile(SOURCE/"scripts/bp18_b5_derived_contract.py",control/"bp18_b5_derived_contract.py")
    import sys
    result=subprocess.run([sys.executable,"-I","-S",str(control/"bp18_b5_derived_contract.py"),"--target",pair["forward"],"--activating"],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert result.stdout.startswith("BP18_DERIVED_PRESTART_PASS")
