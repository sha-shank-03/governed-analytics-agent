"""Deny-by-default SQL execution; parent owns the path and process timeout."""

import json
import sqlite3
import sys
import time
from pathlib import Path
from .data import TABLES, tables_for_schema

FUNCTIONS = {"sum", "coalesce", "ifnull", "count", "substr", "min", "max", "abs"}


def authorize(tables, action, arg1, arg2, database, source):
    if action == sqlite3.SQLITE_SELECT:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_READ:
        # count(*) and unused cross-join tables may have an empty column and no DB name.
        # ATTACH, temp objects and all unapproved tables remain forbidden on this connection.
        if arg1 in tables and ((database == "main" and arg2 in tables[arg1]) or
                              (arg2 == "" and database in ("main", None))):
            return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_FUNCTION and (arg2 or "").lower() in FUNCTIONS:
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def authorizer(action, arg1, arg2, database, source):
    return authorize(TABLES, action, arg1, arg2, database, source)


def configure(connection, schema_version="sales_v1"):
    connection.execute("PRAGMA query_only=ON")
    connection.execute("PRAGMA trusted_schema=OFF")
    connection.execute("PRAGMA temp_store=MEMORY")
    actual_heap = connection.execute("PRAGMA hard_heap_limit=67108864").fetchone()[0]
    if not 0 < actual_heap <= 67108864:
        raise RuntimeError("Required SQLite heap limit unavailable")
    limits = {sqlite3.SQLITE_LIMIT_SQL_LENGTH: 32768, sqlite3.SQLITE_LIMIT_LENGTH: 1048576,
              sqlite3.SQLITE_LIMIT_COLUMN: 32, sqlite3.SQLITE_LIMIT_EXPR_DEPTH: 32,
              sqlite3.SQLITE_LIMIT_COMPOUND_SELECT: 3, sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER: 16,
              sqlite3.SQLITE_LIMIT_ATTACHED: 0, sqlite3.SQLITE_LIMIT_VDBE_OP: 50000}
    for category, value in limits.items():
        connection.setlimit(category, value)
    tables = tables_for_schema(schema_version)
    connection.set_authorizer(lambda *args: authorize(tables, *args))


def execute(connection, sql, parameters, seconds=1.0):
    if type(sql) is not str or len(sql.encode()) > 32768 or not isinstance(parameters, dict):
        return {"ok": False, "error": "INVALID_QUERY"}
    if any(type(value) not in (str, int) or len(str(value)) > 128 for value in parameters.values()):
        return {"ok": False, "error": "INVALID_PARAMETERS"}
    started = time.monotonic()
    connection.set_progress_handler(lambda: int(time.monotonic() - started > seconds), 1000)
    try:
        cursor = connection.execute(sql, parameters)
        if cursor.description is None:
            return {"ok": False, "error": "RESULT_SHAPE_MISMATCH"}
        columns = [field[0] for field in cursor.description]
        rows = cursor.fetchmany(101)
        if len(rows) > 100:
            return {"ok": False, "error": "RESULT_OVERFLOW"}
        result = {"ok": True, "columns": columns, "rows": [list(row) for row in rows]}
        if len(json.dumps(result, allow_nan=False).encode()) > 32768:
            return {"ok": False, "error": "RESULT_OVERFLOW"}
        return result
    except (sqlite3.Error, MemoryError, ValueError) as exc:
        message = str(exc).lower()
        error = "QUERY_TIMEOUT" if "interrupted" in message else "SQL_REJECTED"
        if "not authorized" in message or "prohibited" in message or "authorization denied" in message:
            error = "POLICY_DENIED"
        elif "no such column" in message:
            error = "STALE_SCHEMA"
        return {"ok": False, "error": error}
    finally:
        connection.set_progress_handler(None, 0)


def main():
    payload = sys.stdin.buffer.read(65537)
    if len(payload) > 65536:
        raise ValueError("Oversized worker payload")
    request = json.loads(payload)
    path = Path(request["path"]).resolve()
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, cached_statements=0)
    try:
        configure(connection, request.get("schema_version", "sales_v1"))
        result = execute(connection, request["sql"], request["parameters"])
    finally:
        connection.close()
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
