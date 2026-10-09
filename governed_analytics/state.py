"""Small local checkpoint/lock contract; no stale-lock takeover or exactly-once claim."""

import json
import os
from contextlib import contextmanager
from pathlib import Path


def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


@contextmanager
def run_lock(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / ".run.lock"
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError("RUN_LOCKED") from None
    try:
        os.write(descriptor, str(os.getpid()).encode())
        os.close(descriptor)
        descriptor = None
        yield
    finally:
        if descriptor is not None:
            os.close(descriptor)
        path.unlink()


def read_checkpoint(directory):
    # Trace JSONL is diagnostic; an incomplete trailing line never supersedes this file.
    return json.loads((Path(directory) / "checkpoint.json").read_text(encoding="utf-8"))


def check_request_reuse(state, request_id, request_hash):
    if request_id is None or state.get("request_id") != request_id or state.get("request_hash") != request_hash:
        raise ValueError("IDEMPOTENCY_CONFLICT")


def check_context(state, current_fingerprints):
    if state["source_fingerprints"] != current_fingerprints:
        raise ValueError("CONTEXT_CHANGED")
