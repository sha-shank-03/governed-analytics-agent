"""Supervise trusted HTTP/SQL helpers under one wall deadline, including cleanup."""
import json
import subprocess
import sys
import time
from pathlib import Path
from .upgrade_budget import UpgradeError


def owned_exchange(module, payload, *, timeout, cancel_event=None, max_output=330000,
                   _popen=subprocess.Popen, _clock=time.monotonic, absolute_deadline=None):
    start = _clock()
    deadline = start + max(0, timeout)
    if absolute_deadline is not None:
        deadline = min(deadline, absolute_deadline)
    window = max(0, deadline - start)
    cleanup = min(0.5, window / 4)
    work_deadline = deadline - cleanup
    receipt = {"child_pid": None, "child_reaped": True, "remote_outcome_unknown": False}
    if cancel_event is not None and cancel_event.is_set():
        raise UpgradeError("CANCELLED", receipt)
    if window <= 0:
        raise UpgradeError("TRANSPORT_TIMEOUT", receipt)
    process, output, code = None, None, None
    try:
        process = _popen([sys.executable, "-m", module], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
            cwd=Path(__file__).resolve().parent.parent)
        receipt.update(child_pid=process.pid, child_reaped=False, remote_outcome_unknown=True)
        send = json.dumps(payload, ensure_ascii=False, allow_nan=False)
        while True:
            if cancel_event is not None and cancel_event.is_set():
                code = "CANCELLED"
                break
            remaining = work_deadline - _clock()
            if remaining <= 0:
                code = "TRANSPORT_TIMEOUT"
                break
            try:
                stdout, _ = process.communicate(input=send, timeout=min(0.05, remaining))
                if process.returncode != 0 or len(stdout.encode("utf-8")) > max_output:
                    code = "HELPER_FAILED"
                else:
                    output = json.loads(stdout)
                    if type(output) is not dict:
                        code = "HELPER_FAILED"
                break
            except subprocess.TimeoutExpired:
                send = None
    except (OSError, ValueError, RecursionError):
        code = "HELPER_FAILED"
    except KeyboardInterrupt:
        code = "CANCELLED"
    finally:
        if process is not None:
            try:
                if process.poll() is None:
                    process.kill()
                remaining = max(0, deadline - _clock())
                process.wait(timeout=remaining)
                receipt["child_reaped"] = True
            except (OSError, subprocess.TimeoutExpired):
                code = "CHILD_CLEANUP_FAILED"
                receipt["child_reaped"] = process.poll() is not None
            finally:
                for stream in (process.stdin, process.stdout, process.stderr):
                    if stream is not None:
                        stream.close()
    receipt["duration_ms"] = round((_clock() - start) * 1000, 3)
    if code:
        raise UpgradeError(code, receipt)
    if output is None:
        raise UpgradeError("HELPER_FAILED", receipt)
    return {**output, **receipt}


def http_exchange(endpoint, raw, *, timeout, cancel_event=None):
    # Endpoint was validated by trusted GatewayConfig. The child checks it again.
    result = owned_exchange("governed_analytics.upgrade_http_worker",
        {"endpoint": endpoint, "body": raw.decode("utf-8"), "timeout": timeout},
        timeout=timeout, cancel_event=cancel_event, max_output=330000)
    if result.get("error"):
        raise UpgradeError(result["error"], {key: result.get(key) for key in
            ("child_pid", "child_reaped", "duration_ms", "remote_outcome_unknown")})
    result["remote_outcome_unknown"] = False
    return result


def query_exchange(path, sql, parameters, schema_version, *, timeout, cancel_event=None):
    try:
        result = owned_exchange("governed_analytics.sql_worker",
            {"path": str(Path(path).resolve()), "sql": sql, "parameters": parameters,
             "schema_version": schema_version}, timeout=timeout, cancel_event=cancel_event,
             max_output=33000)
        result.pop("remote_outcome_unknown", None)
        return result
    except UpgradeError as exc:
        if exc.code == "CHILD_CLEANUP_FAILED":
            raise
        return {"ok": False, "error": "CANCELLED" if exc.code == "CANCELLED" else "QUERY_TIMEOUT"
                if exc.code == "TRANSPORT_TIMEOUT" else "WORKER_FAILED", **exc.receipt}
