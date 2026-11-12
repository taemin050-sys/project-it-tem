"""C-A5-0D P1-01 and P2-02 regression, no real signoffs.

Runs the patched generator against an isolated baseline Git archive. Real Track A
registered decision/contract files, owner sources and GCP are NEVER modified.
"""
from __future__ import annotations
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

import pytest

ROOT=Path(__file__).resolve().parents[2]
HEAD="9ccd8d95aa3d33cde00b166e25ba494e34e75bb6"
DEC="docs/integration/BP18_A50D_OWNER_PM_DECISION_REGISTER_20261110.csv"
CONTRACT="docs/integration/BP18_A50D_PROFILE_V3_REVIEW_ONLY_CONTRACT_20261110.json"
MANIFEST="docs/integration/evidence/A50_20261110/A50_DESIGN_PROPOSALS_MANIFEST.json"
GEN="scripts/a50d_owner_pm_decision_preflight.py"
OLD_ZIP="docs/integration/handoffs/IT_TEM_P03_A50D_OWNER_PM_REVIEW_ONLY_20261110.zip"
OLD_ZIP_SHA="fb8fb89a76a675b994aba9b62d4229a8ff715747b18486c998ea9ab41ef07eff"


def digest(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def archive_tree():
    with tempfile.TemporaryDirectory(prefix="ittem-a50dr1-git-archive-") as t:
        dest=Path(t)/"source"
        dest.mkdir()
        result=subprocess.run(["git","archive","--format=tar",HEAD],cwd=ROOT,
                              stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True)
        # Create minimal baseline from a true immutable git archive, not a copy
        # of the developer's mutable worktree. No untrusted tar path extraction.
        with tarfile.open(fileobj=io.BytesIO(result.stdout),mode="r:") as tar:
            allow={
                DEC, CONTRACT, MANIFEST,
                "docs/integration/evidence/A50_20261110/A41_ORIGINAL_WITHOUT_CTA.png",
                "docs/integration/evidence/A50_20261110/A50_OWNER_PM_4UP_COMPARISON.png",
                "scripts/a50_composed45_design_concepts.py",
            }
            a=json.loads((ROOT/MANIFEST).read_text())
            allow.update(
                "docs/integration/evidence/A50_20261110/"+v["png"]
                for v in a["candidates"].values())
            for member in tar:
                if member.name in allow:
                    assert member.isfile() and not member.issym()
                    f=dest/member.name
                    f.parent.mkdir(parents=True,exist_ok=True)
                    with tar.extractfile(member) as inp, f.open("wb") as out:
                        shutil.copyfileobj(inp,out)
        # Overwrite ONLY the isolated snapshot's generator with new R1 script.
        # All accepted A50 assets & original decision content remain archived.
        (dest/GEN).write_bytes((ROOT/GEN).read_bytes())
        yield dest


def run_generator(root:Path,out:Path)->subprocess.CompletedProcess:
    return subprocess.run([sys.executable,"-B",str(root/GEN),"--out",str(out)],
                          cwd=root,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                          text=True,timeout=20)


def test_r1_old_review_zip_immutable():
    assert digest(ROOT/OLD_ZIP)==OLD_ZIP_SHA


def test_r1_isolated_archive_external_out_does_not_touch_old_decisions(archive_tree):
    original={name:digest(archive_tree/name) for name in (DEC,CONTRACT,MANIFEST)}
    with tempfile.TemporaryDirectory(prefix="ittem-a50dr1-external-out-") as t:
        out=Path(t)/"owner-review"
        assert not out.is_relative_to(archive_tree)
        run=run_generator(archive_tree,out)
        assert run.returncode==0,run.stdout
        assert "A50D_REVIEW_ASSETS_READY_OUTSIDE_SIGNED_LEDGER" in run.stdout
        assert len(list(out.iterdir()))==3
        draft=json.loads((out/Path(CONTRACT).name).read_text("utf-8"))
        assert draft["approval_state"]=="DRAFT_NOT_APPROVED"
        assert draft["a5_1_implementation_authorized"] is False
        assert draft["pm_signoff"] is None
        assert {name:digest(archive_tree/name) for name in original}==original
        first={p.name:digest(p) for p in out.iterdir()}
        again=run_generator(archive_tree,out)
        assert again.returncode!=0
        assert "EXISTING_DESTINATION_HOLD" in again.stdout
        assert {p.name:digest(p) for p in out.iterdir()}==first


def test_r1_synthetic_owner_pm_signatures_in_archived_canonical_preserved(archive_tree):
    # Synthetic signatures are deliberately in the isolated git archive.
    # Never alter the canonical Track A signoff register.
    csvpath=archive_tree/DEC
    with csvpath.open(encoding="utf-8",newline="") as f:
        data=list(csv.DictReader(f));columns=list(data[0])
    row=next(row for row in data if row["decision_id"]=="D50-02")
    row.update({
        "status":"APPROVED","image_owner_signoff_ref":"TEST_OWNER_SIGNATURE_ONLY",
        "pm_signoff_ref":"TEST_PM_SIGNATURE_ONLY",
        "exact_profile_json_sha256":"a"*64,
        "effective_policy_epoch":"TEST_EPOCH_DO_NOT_USE",
        "approval_timestamp":"2026-11-10T00:00:00+09:00",
    })
    with csvpath.open("w",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=columns,lineterminator="\n")
        writer.writeheader();writer.writerows(data)
    conpath=archive_tree/CONTRACT
    contract=json.loads(conpath.read_text())
    contract.update({"owner_pm_signed":True,"approval_state":"APPROVED",
                     "owner_image24_signoff":"TEST_OWNER_SIGNATURE_ONLY",
                     "pm_signoff":"TEST_PM_SIGNATURE_ONLY",
                     "profile_json_sha256":"a"*64,
                     "effective_policy_epoch":"TEST_EPOCH_DO_NOT_USE"})
    conpath.write_text(json.dumps(contract,indent=2,ensure_ascii=False)+"\n")
    locked={name:digest(archive_tree/name) for name in (DEC,CONTRACT)}
    with tempfile.TemporaryDirectory(prefix="ittem-a50dr1-audit-owned-") as t:
        done=run_generator(archive_tree,Path(t)/"new-draft")
        assert done.returncode==0,done.stdout
        assert {name:digest(archive_tree/name) for name in locked}==locked
        # If the explicitly requested dir is the SIGNED canonical directory,
        # fail-closed on pre-existing approval content before opening anything.
        denied=run_generator(archive_tree,archive_tree/"docs/integration")
        assert denied.returncode!=0
        assert "EXISTING_DESTINATION_HOLD" in denied.stdout
        assert {name:digest(archive_tree/name) for name in locked}==locked
        assert "TEST_PM_SIGNATURE_ONLY" in conpath.read_text()
        assert "TEST_OWNER_SIGNATURE_ONLY" in csvpath.read_text()


def test_r1_external_signed_destination_fail_closed_and_bytes_preserved(archive_tree):
    with tempfile.TemporaryDirectory(prefix="ittem-a50dr1-signed-external-") as t:
        out=Path(t)/"review"
        out.mkdir()
        for name,text in (
            (Path(CONTRACT).name,'{"approval_state":"APPROVED","owner_pm_signed":true}'),
            (Path(DEC).name,'D50-02,APPROVED,TEST_PM_SIGNATURE_ONLY\n'),
        ):
            (out/name).write_text(text)
        old={p.name:digest(p) for p in out.iterdir()}
        r=run_generator(archive_tree,out)
        assert r.returncode!=0 and "EXISTING_DESTINATION_HOLD" in r.stdout
        assert {p.name:digest(p) for p in out.iterdir()}==old
        assert not (out/"A50D_GEOMETRY_AND_DECISION_PREFLIGHT.json").exists()


def test_r1_symlinked_output_dir_refused(archive_tree):
    with tempfile.TemporaryDirectory(prefix="ittem-a50dr1-link-") as t:
        tgt=Path(t)/"protected"
        tgt.mkdir()
        marker=tgt/"TEST_OWNER_SIGNED_NEVER_TOUCH.json"
        marker.write_text('{"status":"APPROVED"}')
        link=Path(t)/"audit_alias"
        link.symlink_to(tgt,target_is_directory=True)
        r=run_generator(archive_tree,link)
        assert r.returncode!=0 and "PATH_HOLD" in r.stdout
        assert marker.read_text()=='{"status":"APPROVED"}'
        assert list(tgt.iterdir())==[marker]


def test_r1_canonical_inputs_still_unsigned_in_real_track_a():
    draft=json.loads((ROOT/CONTRACT).read_text())
    assert draft["owner_pm_signed"] is False
    assert draft["approval_state"]=="DRAFT_NOT_APPROVED"
    with (ROOT/DEC).open(encoding="utf-8",newline="") as f:
        rows=list(csv.DictReader(f))
    assert len(rows)==9
    assert all(not x["pm_signoff_ref"] and not x["image_owner_signoff_ref"]
               for x in rows)
