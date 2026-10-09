"""Actual children and loopback HTTP; requires the M2 integration grant."""
import ctypes
import json
import os
import sqlite3
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch
from governed_analytics import data
from governed_analytics.__main__ import demo, QUESTION
from governed_analytics.execution import run_sql
from governed_analytics.orchestrator import Session, start, resume
from governed_analytics.providers import FaultProvider
from governed_analytics.responses import ResponsesProvider

ROOT = Path(__file__).resolve().parents[2]


def process_exited(pid):
    if os.name == "nt":
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        kernel.OpenProcess.restype = ctypes.c_void_p
        handle = kernel.OpenProcess(0x1000, 0, pid)
        if not handle:
            return True
        try:
            code = ctypes.c_uint32()
            kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
            kernel.CloseHandle.argtypes = [ctypes.c_void_p]
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value != 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return False
    except ProcessLookupError:
        return True


class M2ProcessTests(unittest.TestCase):
    def test_real_parent_timeout_kills_and_reaps_owned_child(self):
        result = run_sql(Path("unused"), "SELECT 1", {}, timeout=0.15,
                         _command=[sys.executable, "-c", "import time; time.sleep(30)"])
        self.assertEqual(result["error"], "QUERY_TIMEOUT")
        self.assertTrue(result["child_reaped"])
        self.assertTrue(process_exited(result["child_pid"]))

    def test_real_cancellation_kills_and_reaps_owned_child(self):
        cancel = threading.Event()
        timer = threading.Timer(0.15, cancel.set)
        timer.start()
        try:
            result = run_sql(Path("unused"), "SELECT 1", {}, cancel_event=cancel,
                             _command=[sys.executable, "-c", "import time; time.sleep(30)"])
        finally:
            timer.join()
        self.assertEqual(result["error"], "CANCELLED")
        self.assertTrue(result["child_reaped"])
        self.assertTrue(process_exited(result["child_pid"]))


class M2WorkflowTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / "work/integration-temp"
        scratch.mkdir(parents=True, exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=scratch)
        self.path = Path(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()

    def test_known_schema_missing_period_zero_and_unknown_schema(self):
        for scenario, status in (("schema-drift", "completed"), ("missing-period", "insufficient_data"),
                                 ("schema-unsupported", "schema_unsupported"), ("zero-previous", "completed")):
            report = demo(scenario, self.path / scenario)
            self.assertEqual(report["status"], status)
            self.assertTrue(report["source_immutability"]["unchanged"])

    def test_clarification_request_idempotency_and_conflicting_reuse(self):
        out = self.path / "request"
        first = start(QUESTION, "north_analyst", out, request_id="request-1")
        again = start(QUESTION, "north_analyst", out, request_id="request-1")
        self.assertEqual(first, again)
        self.assertEqual(first["query_receipts"], [])
        report = resume(out, "net_sales_v1")
        (out / "report.json").unlink()  # Authored interruption after terminal checkpoint publication.
        with patch("governed_analytics.orchestrator.run_sql") as worker:
            recovered = start(QUESTION, "north_analyst", out, request_id="request-1")
        self.assertEqual(recovered["summary"], report["summary"])
        worker.assert_not_called()
        same = start(QUESTION, "north_analyst", out, request_id="request-1")
        self.assertEqual(recovered, same)
        with self.assertRaisesRegex(ValueError, "IDEMPOTENCY_CONFLICT"):
            start("Gross sales in January 2026 and February 2026", "north_analyst", out, request_id="request-1")

    def test_active_checkpoint_restores_fault_state_after_authored_interruption(self):
        out = self.path / "interrupted"
        save = Session.save
        def interrupted_save(session):
            save(session)
            if session.state["attempts"] == 1 and session.state["state"] == "REPAIR_REQUIRED":
                raise RuntimeError("authored interruption after durable action")
        with patch.object(Session, "save", interrupted_save), self.assertRaisesRegex(RuntimeError, "authored interruption"):
            start("Net sales in January 2026 and February 2026", "north_analyst", out, FaultProvider("fanout"))
        report = resume(out)
        self.assertEqual(report["status"], "completed")
        self.assertEqual([row["verification"] for row in report["query_receipts"]],
                         ["GRAIN_OR_VALUE_MISMATCH", "verified", "verified"])
        self.assertTrue(any(row.get("tool") == "host_recovery" for row in report["tool_trace"]))

    def test_policy_and_catalog_changes_block_resume(self):
        fixture_copy = self.path / "fixtures"
        fixture_copy.mkdir()
        for source in data.FIXTURES.glob("*.json"):
            (fixture_copy / source.name).write_bytes(source.read_bytes())
        with patch("governed_analytics.data.FIXTURES", fixture_copy):
            for filename in ("policies.json", "catalog.json"):
                out = self.path / filename
                start(QUESTION, "north_analyst", out)
                source = fixture_copy / filename
                original = source.read_bytes()
                value = json.loads(original)
                value["version"] += "-changed"
                source.write_text(json.dumps(value))
                report = resume(out, "net_sales_v1")
                self.assertEqual(report["status"], "failed")
                self.assertEqual(report["reason"], "CONTEXT_CHANGED")
                self.assertEqual(report["query_receipts"], [])
                source.write_bytes(original)

    def test_repeated_bad_queries_exhaust_budget_without_verified_report(self):
        report = start("Net sales in January 2026 and February 2026", "north_analyst", self.path / "bad",
                       FaultProvider("always_fanout"))
        self.assertEqual(report["status"], "budget_exhausted")
        self.assertIsNone(report["summary"])
        self.assertEqual(report["budgets"]["candidate_sql_used"], 3)

    def test_baseline_denial_and_projection_keep_same_security_boundary(self):
        denied = start("Net sales for all regions in January 2026 and February 2026", "north_analyst",
                       self.path / "denied", workflow_mode="one_pass_sql")
        self.assertEqual(denied["status"], "access_denied")
        self.assertEqual(denied["query_receipts"], [])
        baseline = start("Net sales in January 2026 and February 2026", "north_analyst",
                         self.path / "baseline", workflow_mode="one_pass_sql")
        self.assertEqual(baseline["status"], "experimental_unverified")
        self.assertEqual(baseline["evidence"], {})
        connection = sqlite3.connect((self.path / "baseline/scoped.sqlite").as_uri() + "?mode=ro", uri=True)
        try:
            self.assertEqual(connection.execute("SELECT DISTINCT region FROM orders").fetchall(), [("North",)])
            self.assertIsNone(connection.execute("SELECT name FROM sqlite_master WHERE name='customers_private'").fetchone())
        finally:
            connection.close()

    def test_real_sql_vm_timeout_and_denial_probe(self):
        out = self.path / "scope"
        start(QUESTION, "north_analyst", out)
        path = out / "scoped.sqlite"
        expensive = "SELECT count(*) FROM " + " CROSS JOIN ".join(f"orders o{index}" for index in range(16))
        result = run_sql(path, expensive, {})
        self.assertEqual(result["error"], "QUERY_TIMEOUT")
        self.assertTrue(result["child_reaped"])
        self.assertTrue(process_exited(result["child_pid"]))
        for sql in ("DELETE FROM orders", "SELECT * FROM customers_private", "SELECT * FROM pragma_table_info('orders')"):
            self.assertFalse(run_sql(path, sql, {})["ok"])


class M2LocalHttpTests(unittest.TestCase):
    def test_actual_loopback_responses_round_trip(self):
        requests = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                payload = json.dumps({"status":"completed", "output":[{"type":"function_call","call_id":"local-call",
                    "name":"describe_catalog","arguments":"{}"}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            def log_message(self, *args):
                pass
        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            provider = ResponsesProvider(f"http://127.0.0.1:{server.server_port}/v1/responses", "local-protocol-double")
            decision = provider.decide({"question":"fictional"}, ("describe_catalog",), {})
            self.assertEqual(decision.tool, "describe_catalog")
            self.assertEqual(provider.mode, "local_provider_protocol")
            self.assertFalse(requests[0]["store"])
            self.assertFalse(requests[0]["parallel_tool_calls"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
