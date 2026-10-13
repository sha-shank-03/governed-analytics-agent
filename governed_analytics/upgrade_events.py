"""Small allowlisted telemetry; transport bodies and exception text are never logs."""
import json
import re
import time
from datetime import datetime, timezone
from .data import digest

SECRET = re.compile(r"(?i)(?:bearer\s+[^\s\"']+|sk-[a-z0-9_-]{6,}|(?:api[_ -]?key|access[_ -]?token|secret)\s*[:=]\s*[^\s\"',;]+)")


def redact(value):
    if isinstance(value, str):
        return SECRET.sub("[REDACTED]", value)
    if type(value) is list:
        return [redact(item) for item in value]
    if type(value) is dict:
        return {key: "[REDACTED]" if any(part in key.lower() for part in
                ("authorization", "api_key", "access_token", "credential", "secret")) else redact(item)
                for key, item in value.items()}
    return value


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def append_event(out, state, kind, details=None):
    event = {"version": "u1-events-v1", "mode": state.get("provider_mode", "local_double"), "run_id": state["run_id"],
             "utc_time": datetime.now(timezone.utc).isoformat(), "monotonic": time.monotonic(),
             "kind": kind, "state": state["state"], "status": state["status"],
             "code_hash": state["code_hash"], "config_hash": state["config_hash"],
             "prompt_version": state.get("prompt_version", "gateway-u1-v1"), "dataset_hash": digest(state["source_fingerprints"]),
             "contract_id": state.get("contract", {}).get("contract_id"),
             "snapshot_hash": state.get("snapshot_hash"), "metrics": state["budget"],
             "details": details or {}}
    with (out / "events.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(encoded(redact(event)).decode("utf-8") + "\n")
