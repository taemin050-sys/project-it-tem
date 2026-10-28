"""S3-A B0 human API list must reflect executable dev HTTP OpenAPI only.

This is a docs-only consistency guard; response runtime fidelity remains in
test_job_api.py and test_mock_workflow.py.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from src.serving.main import app

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "API_LIST.md"


def _doc() -> str:
    return DOC.read_text(encoding="utf-8")


def test_current_dev_endpoint_overview_exact_openapi_set():
    text = _doc()
    overview = text.split("## 1. API Overview", 1)[1].split("## 2. System", 1)[0]
    documented = {
        (method, path)
        for method, path in re.findall(
            r"^\| .*? \| (GET|POST) \| \[\x60([^\x60]+)\x60\]\(#[^\)]+\) \|",
            overview,
            flags=re.MULTILINE,
        )
    }
    actual = {
        (method.upper(), path)
        for path, methods in app.openapi()["paths"].items()
        for method in methods
        if method in {"get", "post", "put", "patch", "delete"}
    }
    assert len(actual) == 11, actual
    assert documented == actual, {
        "missing": sorted(actual - documented),
        "unexpected": sorted(documented - actual),
    }
    assert "FROZEN 0" in text and "BLOCKED_WIRE" in text


def test_all_json_code_examples_parse():
    snippets = re.findall(r"^\x60{3}json\n(.*?)^\x60{3}", _doc(), re.M | re.S)
    assert len(snippets) >= 6
    for snippet in snippets:
        json.loads(snippet)


def test_bash_code_blocks_are_parseable():
    scripts = re.findall(r"^\x60{3}bash\n(.*?)^\x60{3}", _doc(), re.M | re.S)
    assert len(scripts) >= 6
    for script in scripts:
        check = subprocess.run(
            ["/bin/bash", "-n"], input=script, text=True,
            capture_output=True, check=False,
        )
        assert check.returncode == 0, check.stderr


def test_link_targets_exist_and_fences_balanced():
    text = _doc()
    assert len(re.findall(r"^\x60{3}", text, re.M)) % 2 == 0
    for dest in re.findall(r"\]\(([^)]+)\)", text):
        if dest.startswith(("http:", "https:", "#")):
            continue
        rel = dest.split("#")[0]
        assert (DOC.parent / rel).exists(), dest
    index = (ROOT / "docs/contracts/README.md").read_text()
    assert index.count("../API_LIST.md") == 1


def test_no_new_wire_misrepresented_as_implemented():
    text = _doc()
    section = text.split("## 8. Pending / Proposed Wire", 1)[1].split("## 9.", 1)[0]
    for route in (
        "/api/v1/jobs/{job_id}/ai/analyze",
        "/api/v1/jobs/{job_id}/ai/research",
        "/api/v1/jobs/{job_id}/ai/copy-review",
        "/api/v1/jobs/{job_id}/ai/image",
        "/api/v1/jobs/{job_id}/compose",
    ):
        assert route in section
        assert route not in app.openapi()["paths"]
    assert "BLOCKED_WIRE" in section
    assert "FROZEN 0" in text
