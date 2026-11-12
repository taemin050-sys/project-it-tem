"""Fresh demo startup with external storage must leave sealed source untouched."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap

import pytest


SOURCE_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_OPERATIONS = sorted([
    ["get", "/health"],
    ["post", "/api/v1/jobs"],
    ["get", "/api/v1/jobs/{job_id}"],
    ["get", "/api/v1/jobs/{job_id}/assets/{asset_id}"],
    ["post", "/api/v1/jobs/{job_id}/mock/plan"],
    ["post", "/api/v1/jobs/{job_id}/mock/copy"],
    ["post", "/api/v1/jobs/{job_id}/approvals/copy"],
    ["post", "/api/v1/jobs/{job_id}/mock/image"],
    ["post", "/api/v1/jobs/{job_id}/approvals/image"],
    ["post", "/api/v1/jobs/{job_id}/mock/compose"],
    ["get", "/api/v1/jobs/{job_id}/artifacts/{kind}"],
])
HEALTH = {"status": "ok", "service": "it-tem-backend", "version": "0.1.0"}


@pytest.fixture
def copied_source(tmp_path):
    source = tmp_path / "sealed-source"
    source.mkdir()
    for package in ("src", "demo_staging"):
        shutil.copytree(SOURCE_ROOT / package, source / package,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return source


def _source_snapshot(source):
    return {path.relative_to(source).as_posix():
            ("directory" if path.is_dir() else hashlib.sha256(path.read_bytes()).hexdigest())
            for path in source.rglob("*")}


def _run_fresh(source, runtime, body):
    env = {name: value for name, value in os.environ.items()
           if not name.startswith(("OPENAI_", "IT_TEM_"))}
    env["PYTHONPATH"] = str(source)
    script = textwrap.dedent("""\
        import json
        from pathlib import Path
        import sys

        def offline_only(event, arguments):
            if event in {"socket.connect", "socket.connect_ex", "socket.getaddrinfo",
                         "subprocess.Popen", "os.system"}:
                raise AssertionError("Startup attempted external IO: " + event)
            if event == "import" and arguments[0].split(".")[0] in {"openai", "anthropic"}:
                raise AssertionError("Startup imported a provider SDK")

        sys.addaudithook(offline_only)
        from fastapi.testclient import TestClient
        source = Path(sys.argv[1])
        runtime = Path(sys.argv[2])

        def operations(application):
            return sorted([[method, path] for path, methods in application.openapi()["paths"].items()
                           if path == "/health" or path.startswith("/api/v1/jobs")
                           for method in methods if method in {"get", "post", "put", "patch", "delete"}])
    """) + textwrap.dedent(body)
    result = subprocess.run([sys.executable, "-B", "-c", script, str(source), str(runtime)],
                            cwd=source, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def test_demo_import_and_external_storage_startup_preserve_complete_source(copied_source, tmp_path):
    before = _source_snapshot(copied_source)
    report = _run_fresh(copied_source, tmp_path / "external-runtime", """\
        from demo_staging.app import make_demo_app
        assert "src.serving.main" not in sys.modules
        assert not (source / ".runtime").exists()
        from src.serving.app_factory import create_app
        normal = create_app(runtime / "normal-jobs")
        assert normal.state.job_store.root == (runtime / "normal-jobs").resolve()
        frontend = runtime / "frontend"
        (frontend / "assets").mkdir(parents=True)
        (frontend / "index.html").write_text("<html>offline</html>")
        invites = runtime / "invites.json"
        invites.write_text(json.dumps({"alice": {"role": "evaluator", "digest": "a" * 64}}))
        demo = make_demo_app(runtime / "demo", invites, frontend, secure_cookie=False)
        assert demo.state.job_store.root == (runtime / "demo/jobs").resolve()
        assert "src.serving.main" not in sys.modules
        assert not (source / ".runtime").exists()
        with TestClient(normal) as client:
            normal_health = client.get("/health").json()
        with TestClient(demo) as client:
            demo_health = client.get("/health").json()
            assert client.get("/demo/api/live/capabilities").status_code == 401
        print(json.dumps({"normal_operations": operations(normal), "demo_operations": operations(demo),
                          "normal_health": normal_health, "demo_health": demo_health}))
    """)
    assert report["normal_operations"] == report["demo_operations"] == EXPECTED_OPERATIONS
    assert report["normal_health"] == report["demo_health"] == HEALTH
    assert _source_snapshot(copied_source) == before
    assert not (copied_source / ".runtime").exists()


def test_legacy_main_keeps_global_app_and_factory_reexport(copied_source, tmp_path):
    report = _run_fresh(copied_source, tmp_path / "external-runtime", """\
        from src.serving.main import app, create_app
        from src.serving.app_factory import create_app as pure_factory
        assert create_app is pure_factory
        assert app.state.job_store.root == (source / ".runtime/jobs").resolve()
        assert (source / ".runtime/jobs").is_dir()
        explicit = create_app(runtime / "explicit-jobs")
        assert explicit.state.job_store.root == (runtime / "explicit-jobs").resolve()
        with TestClient(app) as client:
            health = client.get("/health").json()
        print(json.dumps({"operations": operations(app), "health": health,
                          "explicit_operations": operations(explicit)}))
    """)
    assert report["operations"] == report["explicit_operations"] == EXPECTED_OPERATIONS
    assert report["health"] == HEALTH
