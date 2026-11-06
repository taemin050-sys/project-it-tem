import os
import pytest
from demo_staging.live.env_loader import load_server_environment,SecretConfigError

def test_explicit_loader_separates_web_from_worker(tmp_path,monkeypatch):
    parent=tmp_path/"config";parent.mkdir(mode=0o700)
    os.chmod(parent,0o700)
    f=parent/"openai.env"
    f.write_text("OPENAI_API_KEY=sk-test-not-real-and-no-network-123456789\\n"
                 "OPENAI_MODEL_TEXT=gpt-6-luna\\n"
                 "OPENAI_MODEL_VISION=gpt-6-luna\\n"
                 "OPENAI_REASONING_EFFORT=low\\n")
    f.chmod(0o600)
    monkeypatch.delenv("OPENAI_API_KEY",raising=False)
    web=load_server_environment(f,with_provider_key=False)
    assert web["key_present"] and not web["key_loaded"]
    assert "OPENAI_API_KEY" not in os.environ
    worker=load_server_environment(f,with_provider_key=True)
    assert worker["key_loaded"] and os.environ["OPENAI_API_KEY"].startswith("sk-test")
    f.chmod(0o644)
    with pytest.raises(SecretConfigError,match="ENV_PERMISSIONS_INVALID"):
        load_server_environment(f,with_provider_key=True)

def test_secret_file_symlink_and_relative_path_fail(tmp_path):
    with pytest.raises(SecretConfigError):
        load_server_environment(tmp_path/"missing",with_provider_key=True)
    with pytest.raises(SecretConfigError,match="ENV_PATH_INVALID"):
        load_server_environment("fake.env",with_provider_key=True)
