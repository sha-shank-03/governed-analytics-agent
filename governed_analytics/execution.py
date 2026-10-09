"""Own one query child, terminate only that child, and always reap it."""
import json
import subprocess
import sys
import time
from pathlib import Path


def run_sql(path, sql, parameters, schema_version="sales_v1", *, cancel_event=None,
            timeout=3.0, _command=None, _popen=subprocess.Popen):
    # _command/_popen are trusted test seams. Neither is an actor/tool parameter.
    if cancel_event is not None and cancel_event.is_set():
        return {"ok": False, "error": "CANCELLED", "duration_ms": 0, "child_pid": None, "child_reaped": True}
    if timeout <= 0:
        return {"ok": False, "error": "QUERY_TIMEOUT", "duration_ms": 0, "child_pid": None, "child_reaped": True}
    started = time.monotonic()
    command = _command or [sys.executable, "-m", "governed_analytics.sql_worker"]
    payload = json.dumps({"path": str(Path(path).resolve()), "sql": sql, "parameters": parameters,
                          "schema_version": schema_version})
    try:
        process = _popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, cwd=Path(__file__).resolve().parent.parent)
    except OSError:
        return {"ok": False, "error": "WORKER_FAILED", "duration_ms": round((time.monotonic() - started) * 1000, 3),
                "child_pid": None, "child_reaped": True}
    result, send_input = None, payload
    try:
        while True:
            cancelled = cancel_event is not None and cancel_event.is_set()
            remaining = timeout - (time.monotonic() - started)
            if cancelled or remaining <= 0:
                process.kill()
                process.communicate()
                result = {"ok": False, "error": "CANCELLED" if cancelled else "QUERY_TIMEOUT"}
                break
            try:
                stdout, stderr = process.communicate(input=send_input, timeout=min(0.05, remaining))
                if process.returncode != 0 or len(stdout.encode()) > 33000:
                    result = {"ok": False, "error": "WORKER_FAILED"}
                else:
                    result = json.loads(stdout)
                    if type(result) is not dict or type(result.get("ok")) is not bool:
                        result = {"ok": False, "error": "WORKER_FAILED"}
                break
            except subprocess.TimeoutExpired:
                send_input = None
    except (ValueError, OSError):
        result = {"ok": False, "error": "WORKER_FAILED"}
    finally:
        # Includes KeyboardInterrupt or an unexpected parent exception.
        if process.poll() is None:
            process.kill()
        process.wait()
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                stream.close()
    return {**result, "duration_ms": round((time.monotonic() - started) * 1000, 3),
            "child_pid": process.pid, "child_reaped": process.poll() is not None}
