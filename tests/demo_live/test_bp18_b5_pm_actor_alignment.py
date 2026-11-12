"""P1-03 offline registration/approval boundary; no identity inference."""
import json
from pathlib import Path
import pytest
from scripts.bp18_b5_pm_actor_preflight import check_actor,main


@pytest.fixture
def root(tmp_path):
    p=tmp_path/"config"
    p.mkdir()
    j=p/"bp18_tailnet_roles.json"
    j.write_text(json.dumps({
        "bp18_b_admin":"admin",
        "bp18_b_member1":"evaluator",
        "bp18_b_member2":"evaluator",
        "bp18_b_member3":"evaluator",
        "bp18_b_member4":"evaluator",
    }))
    j.chmod(0o600)
    return tmp_path


def test_missing_pm_attestation_does_not_select_an_actor(root,capsys):
    assert main(["--root",str(root)])==78
    assert "PENDING_PM_SSO_SESSION_CONFIRMATION" in capsys.readouterr().out


def test_no_fabricated_pm_actor(root):
    with pytest.raises(ValueError,match="PM_ACTOR_INVALID_OR_NOT_TRACK_B"):
        check_actor(root,"bp18_b_pm")


def test_a_actor_cannot_authenticate_to_b(root):
    with pytest.raises(ValueError,match="NOT_TRACK_B"):
        check_actor(root,"bp18_a_admin")


def test_registered_actor_is_not_a_payment_approval(root):
    out=check_actor(root,"bp18_b_member1")
    assert out["registered"] is True
    assert out["role"]=="evaluator"
    assert out["paid_provider_allowed"] is False
    assert out["pm_identity_verified_by_script"] is False


def test_insecure_registry_denied(root):
    p=root/"config/bp18_tailnet_roles.json"
    p.chmod(0o644)
    with pytest.raises(ValueError,match="INSECURE"):
        check_actor(root,"bp18_b_member1")


def test_actor_registry_corrupt_and_unregistered_denied(root):
    p=root/"config/bp18_tailnet_roles.json"
    p.write_text("{}")
    with pytest.raises(ValueError,match="NOT_IN_REGISTERED_SSO_USERS"):
        check_actor(root,"bp18_b_member1")


def test_confirmed_actor_still_prints_no_payment_authorization(root,capsys):
    assert main(["--root",str(root),"--confirmed-actor","bp18_b_member1"])==0
    text=capsys.readouterr().out
    assert "PAYMENT_AUTHORIZATION_STILL_PENDING" in text
    assert '"paid_provider_allowed": false' in text
