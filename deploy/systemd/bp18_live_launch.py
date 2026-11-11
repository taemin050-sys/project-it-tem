"""Launch the pinned B web/worker policy and consume systemd credentials.

The operator policy contains model IDs and approved actors. The provider key
is read in the worker process from systemd's ephemeral credential directory.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
from io import StringIO
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
from threading import Event

# Release folders are sealed inventories. Keep interpreter-generated caches out
# of both this process and the exec'd web process; mutable data lives in runtime.
sys.dont_write_bytecode = True


ROOT = Path("/home/macstudio/ittem-bp18-product-completion-20261111")
HOST = "macstudio-macstudio.tail17dfff.ts.net:10500"
POLICY_KEYS = frozenset({
    "IT_TEM_BP18_LIVE_RELEASE_SHA", "IT_TEM_LIVE_APPROVED_ACTORS",
    "IT_TEM_TEXT_MODEL", "IT_TEM_VISION_MODEL", "IT_TEM_IMAGE_MODEL",
    "IT_TEM_IMAGE_QUALITY", "IT_TEM_IMAGE_COMPLEXITY",
})
DUAL_FLAG = "IT_TEM_BP18_LIVE_DUAL_ENABLED"
OPTIONAL_POLICY_KEYS = frozenset({DUAL_FLAG})
BETA_KEYS = frozenset({
    "IT_TEM_DERIVED_ENABLED", "IT_TEM_DERIVED_AUTHORITY_FILE", "IT_TEM_DERIVED_ROOT",
    "IT_TEM_DERIVED_FONT", "IT_TEM_DERIVED_FONT_LICENSE", "IT_TEM_DERIVED_SOURCE_TREE_SHA",
    "IT_TEM_BP18_LIVE_DUAL_MULTI_RATIO_ENABLED", "IT_TEM_BP18_9_16_CTA_POLICY",
    "IT_TEM_BP18_BETA_TYPOGRAPHY_ENABLED",
})
RELEASE_POLICY_DIRECTORY = "bp18_live_policies"
LIVE_FLAGS = (
    "IT_TEM_LIVE_ENABLED", "IT_TEM_LIVE_EXECUTION_APPROVED",
    "IT_TEM_LIVE_WEB_QUEUE_ENABLED", "IT_TEM_PROVIDER_READINESS_CONFIRMED",
)


class LaunchDenied(ValueError):
    pass


def _private_directory(path: Path) -> None:
    info = path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
            or info.st_mode & 0o077):
        raise LaunchDenied("PRIVATE_DIRECTORY_REQUIRED")


def private_text(path: Path, *, credential: bool = False) -> str:
    """Read bounded owner-only regular files without following a final symlink."""
    _private_directory(path.parent)
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as source:
        info = os.fstat(source.fileno())
        allowed_modes = (0o400, 0o600) if credential else (0o600,)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) not in allowed_modes
                or not 0 < info.st_size <= 16384):
            raise LaunchDenied("PRIVATE_FILE_REQUIRED")
        raw = source.read(16385)
    if len(raw) > 16384:
        raise LaunchDenied("PRIVATE_FILE_TOO_LARGE")
    return raw.decode("utf-8")


def release_sha(root: Path) -> str:
    target = os.readlink(root / "repo")
    if not re.fullmatch(r"releases/[a-f0-9]{40}", target):
        raise LaunchDenied("RELEASE_SYMLINK_INVALID")
    sha = target.split("/")[1]
    if (root / "releases").is_symlink() or (root / target).is_symlink():
        raise LaunchDenied("RELEASE_DIRECTORY_INVALID")
    if (root / target / "SOURCE_SHA.txt").read_text().strip() != sha:
        raise LaunchDenied("RELEASE_SHA_MISMATCH")
    return sha


def read_policy(root: Path, sha: str) -> dict[str, str] | None:
    if not re.fullmatch(r"[a-f0-9]{40}", sha):
        raise LaunchDenied("LIVE_POLICY_RELEASE_INVALID")
    config = root / "config"
    policy_directory = config / RELEASE_POLICY_DIRECTORY
    try:
        _private_directory(policy_directory)
    except FileNotFoundError:
        per_release = False
        try:
            policy_text = private_text(config / "bp18_b_live.env")
        except FileNotFoundError:
            return None
    else:
        per_release = True
        _private_directory(config)
        try:
            policy_text = private_text(policy_directory / f"{sha}.env")
        except FileNotFoundError:
            raise LaunchDenied("LIVE_RELEASE_POLICY_FILE_REQUIRED") from None
        except OSError:
            raise LaunchDenied("LIVE_RELEASE_POLICY_FILE_INVALID") from None
    policy = {}
    for line in policy_text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or key not in POLICY_KEYS | OPTIONAL_POLICY_KEYS or key in policy:
            raise LaunchDenied("LIVE_POLICY_KEYS_INVALID")
        policy[key] = value
    if not POLICY_KEYS.issubset(policy):
        raise LaunchDenied("LIVE_POLICY_FIELDS_REQUIRED")
    if DUAL_FLAG in policy and policy[DUAL_FLAG] not in ("YES", "NO"):
        raise LaunchDenied("LIVE_DUAL_POLICY_FLAG_INVALID")
    if not re.fullmatch(r"[a-f0-9]{40}", policy["IT_TEM_BP18_LIVE_RELEASE_SHA"]):
        raise LaunchDenied("LIVE_POLICY_RELEASE_INVALID")
    if per_release and policy["IT_TEM_BP18_LIVE_RELEASE_SHA"] != sha:
        raise LaunchDenied("LIVE_RELEASE_POLICY_SHA_MISMATCH")
    actors = policy["IT_TEM_LIVE_APPROVED_ACTORS"].split(",")
    if (len(actors) != len(set(actors)) or
            any(not re.fullmatch(r"bp18_b_[a-zA-Z0-9_-]{1,33}", actor) for actor in actors)):
        raise LaunchDenied("LIVE_POLICY_ACTORS_INVALID")
    registry = json.loads(private_text(root / "config/bp18_tailnet_roles.json"))
    if any(registry.get(actor) not in ("admin", "evaluator") for actor in actors):
        raise LaunchDenied("LIVE_POLICY_ACTOR_NOT_REGISTERED")
    for name in ("IT_TEM_TEXT_MODEL", "IT_TEM_VISION_MODEL", "IT_TEM_IMAGE_MODEL"):
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,99}", policy[name]):
            raise LaunchDenied("LIVE_POLICY_MODEL_REQUIRED")
    if policy["IT_TEM_IMAGE_QUALITY"] not in ("low", "medium", "high"):
        raise LaunchDenied("LIVE_POLICY_IMAGE_QUALITY_INVALID")
    if policy["IT_TEM_IMAGE_COMPLEXITY"] not in ("", "low", "medium", "high"):
        raise LaunchDenied("LIVE_POLICY_IMAGE_COMPLEXITY_INVALID")
    return policy


def read_beta_policy(root: Path, sha: str) -> dict[str, str] | None:
    """An optional per-release, nonsecret beta policy; historical boots stay off."""
    path = root / "config/bp18_beta_policies" / f"{sha}.env"
    if not path.exists():
        return None
    values = {}
    for line in private_text(path).splitlines():
        if not line or line.startswith("#"):
            continue
        name, separator, value = line.partition("=")
        if (not separator or name not in BETA_KEYS or name in values or not value
                or not re.fullmatch(r"[A-Za-z0-9_./:-]+", value)):
            raise LaunchDenied("BETA_POLICY_INVALID")
        values[name] = value
    if set(values) != BETA_KEYS:
        raise LaunchDenied("BETA_POLICY_INCOMPLETE")
    if any(values[key] not in ("YES", "NO") for key in
           ("IT_TEM_DERIVED_ENABLED", "IT_TEM_BP18_LIVE_DUAL_MULTI_RATIO_ENABLED", "IT_TEM_BP18_BETA_TYPOGRAPHY_ENABLED")):
        raise LaunchDenied("BETA_POLICY_FLAG_INVALID")
    if not re.fullmatch(r"[0-9a-f]{40}", values["IT_TEM_DERIVED_SOURCE_TREE_SHA"]):
        raise LaunchDenied("BETA_POLICY_TREE_INVALID")
    for key in BETA_KEYS - {"IT_TEM_DERIVED_ENABLED", "IT_TEM_BP18_LIVE_DUAL_MULTI_RATIO_ENABLED", "IT_TEM_BP18_BETA_TYPOGRAPHY_ENABLED", "IT_TEM_DERIVED_SOURCE_TREE_SHA"}:
        if not Path(values[key]).is_absolute() or ".." in Path(values[key]).parts:
            raise LaunchDenied("BETA_POLICY_PATH_INVALID")
    return values


def validate_beta_source(root: Path, sha: str, beta: dict[str, str]) -> None:
    from scripts.bp18_b5_derived_contract import required_derived_contract
    evidence = required_derived_contract(root, sha, activating=True)
    if beta["IT_TEM_DERIVED_SOURCE_TREE_SHA"] != evidence["release_inventories"][sha]["tree_sha"]:
        raise LaunchDenied("BETA_POLICY_TREE_MISMATCH")


def configure(root: Path, *, worker: bool) -> str | None:
    for name in list(os.environ):
        if name.startswith("OPENAI_") or name in POLICY_KEYS | OPTIONAL_POLICY_KEYS | BETA_KEYS:
            os.environ.pop(name)
    os.environ.update({name: "NO" for name in LIVE_FLAGS})
    os.environ.update({
        "IT_TEM_LIVE_COST_POLICY": "MONITOR_ONLY",
        "IT_TEM_DEMO_ENABLE_LIVE_CONFIG": "NO",
        "IT_TEM_QA_FIXTURE_ENABLED": "NO",
        "IT_TEM_LIVE_APPROVED_ACTORS": "",
        "IT_TEM_BP18_LIVE_POLICY_SHA": "",
        "PYTHON_DOTENV_DISABLED": "1",
        "IT_TEM_ENABLE_BILLABLE_TEXT_CALLS": "NO",
        "IT_TEM_BP18_F09_REQUIRED": "NO",
        DUAL_FLAG: "NO",
        "IT_TEM_BP18_REVIEW_POLICY_ID": "bp18-f11-compliance-policy-v1",
    })
    sha = release_sha(root)
    beta = read_beta_policy(root, sha)
    from scripts.bp18_b5_release_prestart import required_review_contract
    required_review = required_review_contract(root, sha)
    policy = read_policy(root, sha)
    if policy is None or policy["IT_TEM_BP18_LIVE_RELEASE_SHA"] != sha:
        if worker or required_review:
            raise LaunchDenied("LIVE_POLICY_FOR_CURRENT_RELEASE_REQUIRED")
        return None
    if not required_review:
        raise LaunchDenied("LIVE_POLICY_REVIEW_CONTRACT_REQUIRED")
    if policy["IT_TEM_TEXT_MODEL"] != required_review["model"]:
        raise LaunchDenied("LIVE_POLICY_REVIEW_MODEL_MISMATCH")
    if policy.get(DUAL_FLAG) == "YES":
        from scripts.bp18_b5_release_prestart import required_dual_contract
        required_dual_contract(root, sha, activating=True)
    if (os.environ.get("IT_TEM_TAILNET_AUTH_ENABLED") != "YES"
            or os.environ.get("IT_TEM_TAILNET_SSO_ONLY") != "YES"
            or os.environ.get("IT_TEM_TAILNET_EXPECTED_HOST") != HOST):
        raise LaunchDenied("SIGNED_B_SSO_REQUIRED")
    os.environ.update(policy)
    if beta:
        validate_beta_source(root, sha, beta)
        os.environ.update(beta)
    from demo_staging.live.image_runtime_profile import effective_image_profile
    profile = effective_image_profile()
    if profile["complexity"] != (policy["IT_TEM_IMAGE_COMPLEXITY"] or None):
        raise LaunchDenied("LIVE_POLICY_EXPLICIT_COMPLEXITY_REQUIRED")
    fingerprint = hashlib.sha256(json.dumps({"live": policy, "beta": beta} if beta else policy,
                                           sort_keys=True).encode()).hexdigest()
    os.environ.update({name: "YES" for name in LIVE_FLAGS})
    os.environ.update({
        "IT_TEM_BP18_LIVE_POLICY_SHA": fingerprint,
        "IT_TEM_BP18_F11_ENABLED": "YES",
        "IT_TEM_BP18_F09_REQUIRED": "YES",
        "IT_TEM_BP18_REVIEW_POLICY_ID": "bp18-f09-two-stage-policy-v2",
        "IT_TEM_ENABLE_BILLABLE_TEXT_CALLS": "YES" if worker else "NO",
        "OPENAI_MODEL_TEXT": policy["IT_TEM_TEXT_MODEL"],
        "OPENAI_MODEL_VISION": policy["IT_TEM_VISION_MODEL"],
    })
    return fingerprint


def require_web_policy(root: Path, fingerprint: str, *, proc: Path = Path("/proc")) -> None:
    pid = private_text(root / "web.pid").strip()
    if not re.fullmatch(r"[1-9][0-9]{0,9}", pid):
        raise LaunchDenied("B_WEB_PID_INVALID")
    fields = (proc / pid / "environ").read_bytes().split(b"\0")
    environment = dict(item.split(b"=", 1) for item in fields if b"=" in item)
    if (environment.get(b"IT_TEM_BP18_LIVE_POLICY_SHA") != fingerprint.encode()
            or environment.get(b"IT_TEM_DEMO_CODE_SHA") != release_sha(root).encode()
            or environment.get(b"OPENAI_API_KEY")):
        raise LaunchDenied("B_WEB_WORKER_POLICY_MISMATCH")


def load_credential() -> None:
    directory = Path(os.environ.get("CREDENTIALS_DIRECTORY", ""))
    if not directory.is_absolute():
        raise LaunchDenied("SYSTEMD_CREDENTIAL_REQUIRED")
    from dotenv import dotenv_values
    values = dotenv_values(stream=StringIO(private_text(
        directory / "bp18-openai.env", credential=True)), interpolate=False)
    key = values.get("OPENAI_API_KEY")
    if not isinstance(key, str) or not re.fullmatch(r"[!-~]{20,512}", key):
        raise LaunchDenied("SYSTEMD_CREDENTIAL_KEY_INVALID")
    os.environ["OPENAI_API_KEY"] = key
    os.environ["OPENAI_BASE_URL"] = "https://api.openai.com/v1"


@contextmanager
def worker_release_lease(root: Path):
    _private_directory(root / "config")
    fd = os.open(root / "config/.b5_operator_control.lock",
                 os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600):
            raise LaunchDenied("PRIVATE_FILE_REQUIRED")
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            raise LaunchDenied("B_RELEASE_OPERATION_ACTIVE") from None
        yield
    finally:
        os.close(fd)


def launch_worker(root: Path) -> int:
    with worker_release_lease(root):
        fingerprint = configure(root, worker=True)
        require_web_policy(root, fingerprint)
        checked = subprocess.run([
            "/usr/bin/python3", "-I", "-S", str(root / "control/bp18_release_prestart.py"),
            "--mode", "worker", "--port", "0",
        ], check=False)
        if checked.returncode:
            raise LaunchDenied("B5_WORKER_PRESTART_DENIED")
        stop_requested = Event()
        signal.signal(signal.SIGTERM, lambda *_: stop_requested.set())
        signal.signal(signal.SIGINT, lambda *_: stop_requested.set())
        load_credential()
        try:
            from demo_staging.live.worker import serve_loop
            result = serve_loop(root / "runtime", stop_requested=stop_requested)
            print(result, flush=True)
            return 78 if result == "LIVE_STAGE_HELD_FOR_RECONCILIATION" else 0
        finally:
            os.environ.pop("OPENAI_API_KEY", None)


def main() -> int:
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        mode = sys.argv[1] if len(sys.argv) > 1 else ""
        if mode == "worker" and len(sys.argv) == 2:
            return launch_worker(ROOT)
        if mode != "web" or sys.argv[2:] != [
            "-m", "uvicorn", "demo_staging.serve:app", "--app-dir", str(ROOT / "repo"),
            "--host", "127.0.0.1", "--port", "18100", "--workers", "1", "--no-use-colors",
        ]:
            raise LaunchDenied("B_LAUNCH_MODE_INVALID")
        try:
            configure(ROOT, worker=False)
        except Exception:
            from scripts.bp18_b5_release_prestart import review_contract_required
            if review_contract_required(ROOT):
                raise LaunchDenied("REQUIRED_LLM_WEB_POLICY_UNAVAILABLE") from None
            # A stale/invalid optional policy must keep signed web access usable.
            os.environ.update({name: "NO" for name in LIVE_FLAGS})
            os.environ["IT_TEM_LIVE_APPROVED_ACTORS"] = ""
            os.environ["IT_TEM_BP18_LIVE_POLICY_SHA"] = ""
            os.environ["IT_TEM_BP18_F09_REQUIRED"] = "NO"
            os.environ[DUAL_FLAG] = "NO"
            os.environ["IT_TEM_BP18_REVIEW_POLICY_ID"] = "bp18-f11-compliance-policy-v1"
            os.environ["IT_TEM_ENABLE_BILLABLE_TEXT_CALLS"] = "NO"
            print("BP18_WEB_LIVE_POLICY_DISABLED", flush=True)
        os.environ.pop("CREDENTIALS_DIRECTORY", None)
        os.execv(sys.executable, [sys.executable, *sys.argv[2:]])
    except LaunchDenied as exc:
        print("BP18_LAUNCH_DENIED " + str(exc), flush=True)
    except Exception:
        print("BP18_LAUNCH_FAILED", flush=True)
    return 78


if __name__ == "__main__":
    raise SystemExit(main())
