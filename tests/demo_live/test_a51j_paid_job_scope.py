"""A51J candidate tests. All signatures use *ephemeral test-only keys*.

No actual Owner/PM keys, no GCP deployment, no financial approval.
"""
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess

import pytest

from demo_staging.live.a51j_paid_job_scope import (
    BASE, CONTRACT, owner_visual_contract, verify_paid_job_permit)
from demo_staging.live.a51b_signed_beta_contract import BETA_PREFIX
from demo_staging.live.contracts import LiveGateError


@pytest.mark.parametrize("mode,ratio,profile,rendering,overlay",[
    ("freeform","3:4","OWNER_IMAGE_SIZE_3_4","provider_text_single_image",False),
    ("freeform","4:5","OWNER_IMAGE_SIZE_4_5","provider_text_single_image",False),
    ("freeform","9:16","OWNER_IMAGE_SIZE_9_16","provider_text_single_image",False),
    ("composed","3:4","OWNER_IMAGE_SIZE_3_4","owner_ratio_composition",True),
    ("composed","4:5",BETA_PREFIX+"A","owner_v3_a_c_reflow",True),
    ("composed","9:16","OWNER_IMAGE_SIZE_9_16","owner_ratio_composition",True),
])
def test_six_owner_render_contracts(mode,ratio,profile,rendering,overlay):
    selection=owner_visual_contract(mode,ratio,profile)
    assert selection["rendering"]==rendering
    assert selection["text_overlay"] is overlay
    assert selection["one_candidate"] is True


@pytest.mark.parametrize("mode,ratio,profile",[
    ("freeform","4:5",BETA_PREFIX+"A"),
    ("freeform","9:16","OWNER_IMAGE_SIZE_4_5"),
    ("composed","4:5","OWNER_IMAGE_SIZE_4_5"),
    ("composed","3:4",BETA_PREFIX+"C"),
    ("composed","9:16","OWNER_IMAGE_SIZE_4_5"),
    ("composed","1:1","OWNER_IMAGE_SIZE_1_1"),
    ("unknown","3:4","OWNER_IMAGE_SIZE_3_4"),
])
def test_wrong_layout_or_accidental_v3_sharing_denied(mode,ratio,profile):
    with pytest.raises(LiveGateError,match="A51J_"):
        owner_visual_contract(mode,ratio,profile)


def run(*args):
    subprocess.run(["openssl",*map(str,args)],check=True,
                   capture_output=True,timeout=10)


def private_file(path:Path,data:bytes):
    path.write_bytes(data)
    path.chmod(0o600)


def test_only_authentic_dual_signed_exact_job_permit_accepted(tmp_path):
    root=tmp_path/"policy";root.mkdir(mode=0o700)
    trust=tmp_path/"trust";trust.mkdir(mode=0o700)
    private=tmp_path/"local-only-signing-fixture";private.mkdir(mode=0o700)
    hashes={}
    for role in ("image_owner","pm"):
        secret=private/(role+".testonly.priv.pem")
        public=trust/(role+".pub.pem")
        run("genpkey","-algorithm","Ed25519","-out",secret)
        run("pkey","-in",secret,"-pubout","-out",public)
        secret.chmod(0o600);public.chmod(0o600)
        hashes[role]=hashlib.sha256(public.read_bytes()).hexdigest()
    d={key:"f"*64 for key in BASE}
    d.update({
      "job_id":"a"*32,"actor":"tester","product_sku":"synthetic.demo01",
      "source_commit":"c"*40,
      "mode":"composed","ratio":"4:5","provider":"openai",
      "model":"gpt-image-2.6-sunburst","policy_epoch":"test.20261111",
      "owner_design_profile":BETA_PREFIX+"C",
    })
    assert set(d)==BASE
    present=datetime.now(timezone.utc)
    full={**d,"contract":CONTRACT,
         "valid_from_utc":(present-timedelta(minutes=1)).isoformat(),
         "expires_utc":(present+timedelta(minutes=30)).isoformat()}
    path=root/(d["job_id"]+".paid_job.json")
    private_file(path,json.dumps(full,sort_keys=True).encode())
    for role in hashes:
        signed=root/(d["job_id"]+"."+role+".sig")
        run("pkeyutl","-sign","-inkey",
            private/(role+".testonly.priv.pem"),
            "-rawin","-in",path,"-out",signed)
        signed.chmod(0o600)
    kw={"policy_root":str(root),"trust_root":str(trust),
         "trusted_sha":hashes,"expected":d}
    got=verify_paid_job_permit(**kw,now=present)
    assert got["paid_scope_signature_verified"] is True
    assert got["actual_paid_worker_activation"] is False
    assert got["rendering"]=="owner_v3_a_c_reflow"
    assert got["rights_mask_cost_verification_still_required"] is True
    for change in ({"actor":"another"},
                   {"ratio":"9:16"},
                   {"source_commit":"1"*40},
                   {"source_rights_decision_sha256":"2"*64},
                   {"pm_cost_policy_sha256":"3"*64},
                   {"source_protection_plan_sha256":"4"*64}):
        with pytest.raises(LiveGateError):
            verify_paid_job_permit(**{**kw,"expected":{**d,**change}},now=present)
    with pytest.raises(LiveGateError,match="A51J_PAID_DECISION_EXPIRED_OR_INVALID"):
        verify_paid_job_permit(**kw,now=present+timedelta(days=1))
    old=path.read_bytes()
    private_file(path,old+b" ")
    with pytest.raises(LiveGateError):
        verify_paid_job_permit(**kw,now=present)
    private_file(path,old)
    target=root/(d["job_id"]+".pm.sig")
    target.unlink()
    with pytest.raises(LiveGateError):
        verify_paid_job_permit(**kw,now=present)
    assert not (root/"actual_signed_worker_approved").exists()
