"""Small bounded atomic ledger writes. No subprocess, SQLite or socket access."""
import json
import os
from .accounting import validate, require


def persist(path, ledger):
    validate(ledger)
    raw = (json.dumps(ledger, sort_keys=True, indent=2, allow_nan=False)+"\n").encode("utf-8")
    require(len(raw) <= 65536, "LEDGER_TOO_LARGE")
    temporary = path.with_suffix(".tmp")
    with temporary.open("wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
