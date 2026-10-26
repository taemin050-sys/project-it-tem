"""Purely synthetic *proposal* validation; does not claim FastAPI wire exists."""
import json
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parents[1] / "docs" / "contracts" / "examples"


def source(name):
    return json.loads((BASE / name).read_text(encoding="utf-8"))


def test_all_wire_examples_are_unfrozen_but_complete():
    doc = source("wire_proposals.json")
    assert doc["schema_state"] == "BLOCKED_WIRE"
    actions = doc["actions"]
    assert len(actions) == 7
    assert len({a["id"] for a in actions}) == len(actions)
    for item in actions:
        assert item["method"] in {"POST", "GET"}
        assert item["route_proposal"].startswith("/api/v1/jobs")
        for field in ("owner", "reason", "request", "response",
                      "error_proposal", "allowed"):
            assert item[field]
        assert isinstance(item["request"], dict)
        assert isinstance(item["response"], dict)
        assert isinstance(item["error_proposal"], dict)


def test_vlm_failclosed_proposals_do_not_invent_enum_states():
    p = source("vlm_outcomes_proposed.json")
    assert p["status"] == "BLOCKED_WIRE"
    cases = {c["id"]: c for c in p["cases"]}
    assert set(cases) == {"TRUE", "FALSE", "UNKNOWN", "TIMEOUT"}
    assert cases["TRUE"]["product_analysis"]["is_cosmetic"] is True
    assert cases["TRUE"]["next_paid_stage_allowed"] is True
    for key in ("FALSE", "UNKNOWN", "TIMEOUT"):
        assert cases[key]["next_paid_stage_allowed"] is False
        assert cases[key]["job_status"] == "INPUTS_VALIDATED"
    assert cases["FALSE"]["product_analysis"]["is_cosmetic"] is False
    for key in ("UNKNOWN", "TIMEOUT"):
        assert cases[key]["product_analysis"] is None
        assert cases[key]["error_proposal"]


def test_known_legacy_approval_is_valid_json_without_union():
    yes = json.loads('{"approved":true}')
    no = json.loads('{"approved":false}')
    assert yes == {"approved": True} and no == {"approved": False}
    with pytest.raises(json.JSONDecodeError):
        json.loads('{"approved":true|false}')
