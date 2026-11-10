"""Prepare a B5 Dual source contract from separately reviewed release evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from .bp18_b5_release_prestart import (
    DUAL_CONTRACT_FILE, DUAL_PROTOCOL, DUAL_SOURCE_MARKERS, EXIT_DENY,
    SHA_RE, ReleaseUnsafe, _regular,
)


ROLES = ("forward", "rollback")
SOURCE_FIELDS = {"release_sha", "tree_sha", "protocol_sha256"}


def _git(repo: Path, *arguments: str) -> bytes:
    # Use the named repository and real objects, including in worktree checkouts.
    env = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
    env.update(GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0")
    result = subprocess.run(
        ["git", "--no-replace-objects", "-C", str(repo), *arguments],
        capture_output=True, env=env, check=False,
    )
    if result.returncode:
        raise ReleaseUnsafe("DUAL_GIT_SOURCE_UNAVAILABLE")
    return result.stdout


def _staged_file(release: Path, relative: str) -> Path:
    parts = relative.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ReleaseUnsafe("DUAL_STAGED_PATH_INVALID")
    parent = release
    for part in parts[:-1]:
        parent /= part
        if parent.is_symlink() or not parent.is_dir():
            raise ReleaseUnsafe("DUAL_STAGED_DIRECTORY_INVALID")
    return _regular(parent / parts[-1])


def _source_evidence(repo: Path, root: Path, sha: str) -> tuple[dict, dict]:
    if not isinstance(sha, str) or not SHA_RE.fullmatch(sha):
        raise ReleaseUnsafe("DUAL_RELEASE_SHA_INVALID")
    if _git(repo, "rev-parse", "--verify", f"{sha}^{{commit}}").decode().strip() != sha:
        raise ReleaseUnsafe("DUAL_RELEASE_MUST_BE_COMMIT")
    tree = _git(repo, "rev-parse", "--verify", f"{sha}^{{tree}}").decode().strip()
    release = root / "releases" / sha
    for directory in (root, root / "releases", release):
        if directory.is_symlink() or not directory.is_dir():
            raise ReleaseUnsafe("DUAL_STAGED_DIRECTORY_INVALID")
    if _staged_file(release, "SOURCE_SHA.txt").read_text(encoding="utf-8").strip() != sha:
        raise ReleaseUnsafe("DUAL_STAGED_RELEASE_SHA_MISMATCH")

    protocol_files = {}
    for entry in _git(repo, "ls-tree", "-r", "-z", tree).split(b"\0"):
        if not entry:
            continue
        metadata, path = entry.split(b"\t", 1)
        mode, kind, blob = metadata.split(b" ")
        if kind != b"blob" or mode not in (b"100644", b"100755"):
            raise ReleaseUnsafe("DUAL_RELEASE_FILE_TYPE_UNSUPPORTED")
        relative = os.fsdecode(path)
        file = _staged_file(release, relative)
        raw = file.read_bytes()
        if (_git(repo, "cat-file", "blob", blob.decode("ascii")) != raw
                or bool(file.stat().st_mode & 0o100) != (mode == b"100755")):
            raise ReleaseUnsafe("DUAL_STAGED_TREE_MISMATCH")
        if relative in DUAL_SOURCE_MARKERS:
            if any(marker not in raw for marker in DUAL_SOURCE_MARKERS[relative]):
                raise ReleaseUnsafe("LIVE_DUAL_REQUIRED_PROTOCOL_CODE_MISSING")
            protocol_files[relative] = hashlib.sha256(raw).hexdigest()
    if protocol_files.keys() != DUAL_SOURCE_MARKERS.keys():
        raise ReleaseUnsafe("LIVE_DUAL_REQUIRED_PROTOCOL_CODE_MISSING")

    protocol = {"required_mode": DUAL_PROTOCOL, "verified_files": protocol_files}
    serialized = json.dumps(protocol, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {"release_sha": sha, "tree_sha": tree,
            "protocol_sha256": hashlib.sha256(serialized).hexdigest()}, protocol_files


def _review_pair(repo: Path, root: Path, shas: dict[str, str]) -> tuple[dict, dict]:
    if shas["forward"] == shas["rollback"]:
        raise ReleaseUnsafe("DUAL_FORWARD_AND_ROLLBACK_MUST_BE_DISTINCT")
    evidence, sources = {}, {}
    for role in ROLES:
        sha = shas[role]
        evidence[role], sources[sha] = _source_evidence(repo, root, sha)
    return evidence, sources


def _operator_json(path: Path) -> object:
    if _regular(path, trusted=True).stat().st_uid != os.geteuid():
        raise ReleaseUnsafe("DUAL_OPERATOR_FILE_OWNER_MISMATCH")

    def unique_keys(pairs):
        document = dict(pairs)
        if len(document) != len(pairs):
            raise ReleaseUnsafe("DUAL_OPERATOR_FILE_DUPLICATE_KEYS")
        return document

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_keys)


def _contract(repo: Path, root: Path, approval_path: Path) -> dict:
    approval = _operator_json(approval_path)
    if (not isinstance(approval, dict)
            or set(approval) != {"version", "required_mode", "approval_reference", *ROLES}
            or type(approval["version"]) is not int or approval["version"] != 1
            or approval["required_mode"] != DUAL_PROTOCOL
            or not isinstance(approval["approval_reference"], str)
            or not approval["approval_reference"].strip()
            or len(approval["approval_reference"]) > 200):
        raise ReleaseUnsafe("DUAL_OPERATOR_APPROVAL_INVALID")
    for role in ROLES:
        record = approval[role]
        if (not isinstance(record, dict) or set(record) != SOURCE_FIELDS
                or not all(isinstance(value, str) for value in record.values())
                or not SHA_RE.fullmatch(record["release_sha"])
                or not SHA_RE.fullmatch(record["tree_sha"])
                or not re.fullmatch(r"[0-9a-f]{64}", record["protocol_sha256"])):
            raise ReleaseUnsafe("DUAL_OPERATOR_APPROVAL_INVALID")
    evidence, sources = _review_pair(repo, root, {role: approval[role]["release_sha"] for role in ROLES})
    if any(evidence[role] != approval[role] for role in ROLES):
        raise ReleaseUnsafe("DUAL_APPROVED_SOURCE_EVIDENCE_MISMATCH")
    return {"version": 1, "required_mode": DUAL_PROTOCOL, "verified_sources": sources}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--git-repo", type=Path, required=True)
    parser.add_argument("--staging-root", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="emit read-only source evidence for review")
    for role in ROLES:
        inspect.add_argument(f"--{role}", required=True)
    commands.add_parser("prepare", help="emit the approved runtime JSON to stdout").add_argument(
        "--approval", type=Path, required=True)
    verify = commands.add_parser("verify", help="verify an external or installed contract read-only")
    verify.add_argument("--approval", type=Path, required=True)
    verify.add_argument("--contract", type=Path)
    args = parser.parse_args(argv)

    try:
        if args.command == "inspect":
            evidence, _ = _review_pair(args.git_repo, args.staging_root,
                                       {role: getattr(args, role) for role in ROLES})
            output = {"version": 1, "required_mode": DUAL_PROTOCOL, "evidence_only": True, **evidence}
        else:
            output = _contract(args.git_repo, args.staging_root, args.approval)
            if args.command == "verify":
                path = args.contract or args.staging_root / DUAL_CONTRACT_FILE
                installed = _operator_json(path)
                if (not isinstance(installed, dict) or type(installed.get("version")) is not int
                        or installed != output):
                    raise ReleaseUnsafe("DUAL_CONTRACT_VERIFICATION_MISMATCH")
                print("BP18_DUAL_CONTRACT_VERIFIED " + " ".join(sorted(output["verified_sources"])))
                return 0
    except ReleaseUnsafe as exc:
        print("BP18_DUAL_CONTRACT_DENIED:" + exc.code, file=sys.stderr)
        return EXIT_DENY
    except (OSError, ValueError):
        print("BP18_DUAL_CONTRACT_DENIED:DUAL_CONTRACT_INPUT_INVALID", file=sys.stderr)
        return EXIT_DENY
    print(json.dumps(output, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
