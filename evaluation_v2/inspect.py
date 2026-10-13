"""Post-run artifact inspection; SQLite reads require the native evaluation lease."""
import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from .scorer import digest

ROOT = Path(__file__).resolve().parent.parent
TABLES = ("orders", "order_lines", "refunds", "fulfillment_events", "period_coverage")


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect(out):
    out = Path(out)
    with closing(sqlite3.connect((out / "scoped.sqlite").resolve().as_uri()+"?mode=ro", uri=True)) as connection:
        names = [r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        if set(names) != set(TABLES):
            raise ValueError("UNEXPECTED_PHYSICAL_TABLE")
        columns = {table: [r[1] for r in connection.execute(f"PRAGMA table_info({table})")] for table in TABLES}
        rows = {table: [list(r) for r in connection.execute(f"SELECT * FROM {table} ORDER BY rowid")] for table in TABLES}
    code = {p.name: file_hash(p) for p in sorted((ROOT / "governed_analytics").glob("*.py"))}
    events = [json.loads(line) for line in (out/"events.jsonl").read_text(encoding="utf-8").splitlines()]
    confirmation_path = out/"external-confirmation-input.json"
    return {"rows": rows, "columns": columns,
            "external_confirmation_input": json.loads(confirmation_path.read_text(encoding="utf-8")) if confirmation_path.exists() else None,
            "checkpoint": json.loads((out/"checkpoint.json").read_text(encoding="utf-8")),
            "source_fixture": json.loads((out/"source_fixture.json").read_text(encoding="utf-8")),
            "file_hashes": {name: file_hash(out/name) for name in ("scoped.sqlite", "source_fixture.json")},
            "expected_code_hash": digest(code), "events": events,
            "trusted_measure_definitions": json.loads((ROOT/"fixtures/catalog.json").read_text(encoding="utf-8"))["measures"],
            "trusted_catalog_hash": file_hash(ROOT/"fixtures/catalog.json"),
            "trusted_policy_hash": file_hash(ROOT/"fixtures/policies.json")}
