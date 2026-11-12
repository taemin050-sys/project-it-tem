"""A3 Linux-only stdlib probe for the BP17 atomic renameat2 NOREPLACE primitive.

This is a kernel-level comparator, NOT the entire PIL/SQLite/production BP17
pipeline. Use in already-local Linux container with --network none.
"""
from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import tempfile
from uuid import uuid4


def no_replace(parentfd: int, source: str, destination: str) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    fn = libc.renameat2
    fn.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                   ctypes.c_char_p, ctypes.c_uint]
    fn.restype = ctypes.c_int
    if fn(parentfd, source.encode(), parentfd, destination.encode(), 1):
        code = ctypes.get_errno()
        if code in (errno.EEXIST, errno.ENOTEMPTY):
            raise FileExistsError("DESTINATION_MUST_BE_NEW")
        raise OSError(code, os.strerror(code))
    os.fsync(parentfd)


def racer(parent: str, gate, result_queue):
    directory = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    name = ".a3_private_" + uuid4().hex
    os.mkdir(name, mode=0o700, dir_fd=directory)
    stagefd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                      dir_fd=directory)
    try:
        filefd = os.open("payload", os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                         0o600, dir_fd=stagefd)
        with os.fdopen(filefd, "wb") as stream:
            stream.write(b"immutable-production-claim:" + name.encode())
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(stagefd)
        gate.wait(timeout=15)
        try:
            no_replace(directory, name, "published")
            result_queue.put("PUBLISHED")
        except FileExistsError:
            result_queue.put("EXISTS")
            os.unlink("payload", dir_fd=stagefd)
            os.rmdir(name, dir_fd=directory)
    finally:
        os.close(stagefd)
        os.close(directory)


def run(rounds: int) -> dict:
    if not 1 <= rounds <= 100:
        raise ValueError("ROUNDS_MUST_BE_1_TO_100")
    ctx = multiprocessing.get_context("spawn")
    for run_num in range(rounds):
        with tempfile.TemporaryDirectory(prefix="a3_linux_noreplace_") as temp:
            path = Path(temp)
            gate = ctx.Barrier(2)
            results = ctx.Queue()
            processes = [
                ctx.Process(target=racer, args=(str(path), gate, results))
                for _ in range(2)
            ]
            for process in processes:
                process.start()
            for process in processes:
                process.join(20)
            if [process.exitcode for process in processes] != [0, 0]:
                raise AssertionError(f"INVALID_CHILD_EXIT:{run_num}")
            if sorted((results.get(timeout=5),results.get(timeout=5))) != [
                "EXISTS","PUBLISHED"
            ]:
                raise AssertionError(f"MULTIPLE_PUBLICATION:{run_num}")
            published = path / "published" / "payload"
            actual = published.read_bytes()
            if not actual.startswith(b"immutable-production-claim:"):
                raise AssertionError(f"INCOMPLETE_PUBLISHED_BYTES:{run_num}")
            if hashlib.sha256(actual).hexdigest() != hashlib.sha256(
                published.read_bytes()
            ).hexdigest():
                raise AssertionError(f"POST_PUBLISH_MUTATION:{run_num}")
            if list(path.glob(".a3_private_*")):
                raise AssertionError(f"ORPHAN_STAGE:{run_num}")
            # Late replays never replace prior genuine published bytes.
            before = hashlib.sha256(actual).hexdigest()
            parentfd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
            os.mkdir("replay", dir_fd=parentfd)
            try:
                try:
                    no_replace(parentfd, "replay", "published")
                except FileExistsError:
                    pass
                else:
                    raise AssertionError(f"EXISTING_REPLACED:{run_num}")
                assert hashlib.sha256(published.read_bytes()).hexdigest() == before
            finally:
                os.rmdir("replay", dir_fd=parentfd)
                os.close(parentfd)
    return {
        "platform": "Linux", "primitive": "renameat2(RENAME_NOREPLACE)",
        "rounds": rounds, "winner_per_round": 1, "loser_per_round": 1,
        "existing_destination_changed": False,
        "partial_or_orphan_stage": False, "result": "PASS"
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=30)
    args = parser.parse_args()
    if os.uname().sysname != "Linux":
        raise SystemExit("LINUX_ONLY_PRIMITIVE")
    print(json.dumps(run(args.rounds), sort_keys=True))
