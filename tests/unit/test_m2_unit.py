import json
import sqlite3
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from governed_analytics.data import create_projection, load_fixture, scoped_rows, price_column, source_fingerprints
from governed_analytics.execution import run_sql
from governed_analytics.orchestrator import Session, file_hash
from governed_analytics.providers import Decision, ScriptedProvider, proposed_sql
from governed_analytics.responses import ResponsesProvider, strict_json, tool_schema, NoRedirect
from governed_analytics.sql_worker import configure, execute
from governed_analytics.state import atomic_json, run_lock, read_checkpoint, check_request_reuse, check_context
from governed_analytics.verification import reference_sql, compare
from evaluation.oracle import expected_rows, score

ROOT = Path(__file__).resolve().parents[2]
PARAMS = {"previous": "2026-01", "current": "2026-02", "as_of": "2026-03-01"}


class M2ArithmeticTests(unittest.TestCase):
    def test_v2_and_complete_zero_month_use_independent_oracle(self):
        scratch = ROOT / "work/unit-temp"
        scratch.mkdir(parents=True, exist_ok=True)
        for variant in ("demo-v2", "zero-previous"):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory(dir=scratch) as directory:
                data = load_fixture(variant)
                path = Path(directory) / "scoped.sqlite"
                create_projection(path, scoped_rows(data, ["North"]), data["schema_version"])
                connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, cached_statements=0)
                try:
                    configure(connection, data["schema_version"])
                    for grouping in ("none", "channel"):
                        candidate = execute(connection, proposed_sql("net_sales_v1", grouping, data["schema_version"]), PARAMS)
                        reference = execute(connection, reference_sql("net_sales_v1", grouping, data["schema_version"]), PARAMS)
                        self.assertTrue(compare(candidate, reference)["verified"], (candidate, reference))
                        self.assertEqual(candidate["rows"], expected_rows("net_sales_v1", variant, grouping=grouping))
                finally:
                    connection.close()

    def test_missing_incomplete_and_unknown_variants_are_explicit(self):
        self.assertNotIn("2026-01", [row[0] for row in load_fixture("missing-period")["period_coverage"]])
        self.assertTrue(all(row[2] == 0 for row in load_fixture("incomplete-period")["period_coverage"] if row[0] == "2026-02"))
        with self.assertRaisesRegex(ValueError, "SCHEMA_UNSUPPORTED"):
            price_column(load_fixture("unknown-schema")["schema_version"])


class M2StateTests(unittest.TestCase):
    def test_checkpoint_survives_partial_trace_and_lock_excludes_concurrent_resume(self):
        scratch = ROOT / "work/unit-temp"
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            path = Path(directory)
            value = {"request_id": "r1", "request_hash": "h1", "status": "awaiting_clarification"}
            with run_lock(path):
                atomic_json(path / "checkpoint.json", value)
                (path / "events.jsonl").write_text('{"partial":')
                with self.assertRaisesRegex(ValueError, "RUN_LOCKED"):
                    with run_lock(path):
                        pass
            self.assertEqual(read_checkpoint(path), value)
            self.assertFalse((path / ".run.lock").exists())

    def test_changed_policy_catalog_or_request_are_rejected(self):
        state = {"request_id": "r1", "request_hash": "h1", "source_fingerprints": {"catalog": "a", "policy": "p"}}
        check_request_reuse(state, "r1", "h1")
        for request_id, request_hash in (("r2", "h1"), ("r1", "different"), (None, "h1")):
            with self.assertRaisesRegex(ValueError, "IDEMPOTENCY_CONFLICT"):
                check_request_reuse(state, request_id, request_hash)
        for current in ({"catalog": "b", "policy": "p"}, {"catalog": "a", "policy": "q"}):
            with self.assertRaisesRegex(ValueError, "CONTEXT_CHANGED"):
                check_context(state, current)


class M2ProtocolTests(unittest.TestCase):
    def response(self, name="describe_catalog", arguments="{}", output=None, status="completed", usage=None):
        return json.dumps({"status": status, "output": output if output is not None else [
            {"type": "reasoning", "id": "reasoning-fixture"},
            {"type": "function_call", "call_id": "c1", "name": name, "arguments": arguments}], "usage": usage}).encode()

    def test_continuation_preserves_reasoning_and_binds_tool_output(self):
        requests = []
        def transport(url, body, timeout):
            requests.append(json.loads(body))
            return 200, self.response(usage={"input_tokens": 10, "output_tokens": 2})
        provider = ResponsesProvider("http://127.0.0.1:1/v1/responses", "local-protocol-double", transport=transport)
        provider.decide({"state": "RECEIVED", "question": "fictional"}, ("describe_catalog",), {})
        provider.decide({"last_result": {"catalog": "scoped"}}, ("describe_catalog",), {})
        self.assertFalse(requests[0]["store"])
        self.assertFalse(requests[0]["parallel_tool_calls"])
        self.assertTrue(any(item.get("type") == "reasoning" for item in requests[1]["input"]))
        output = requests[1]["input"][-1]
        self.assertEqual(output["call_id"], "c1")
        self.assertEqual(json.loads(output["output"]), {"catalog": "scoped"})
        self.assertEqual(provider.usage[0]["status"], "observed")

    def test_nonlocal_endpoint_disabled_before_any_transport(self):
        transport = Mock()
        with self.assertRaisesRegex(ValueError, "EXTERNAL_PROVIDER_DISABLED"):
            ResponsesProvider("https://example.invalid/v1/responses", "no-model-call", transport=transport)
        transport.assert_not_called()

    def test_refusal_incomplete_multiple_calls_and_plain_text_fail(self):
        responses = [self.response(status="incomplete"), self.response(output=[]),
                     self.response(output=[{"type": "message", "content": [{"type": "refusal"}]}]),
                     self.response(output=[{"type":"function_call","call_id":"a","name":"describe_catalog","arguments":"{}"}]*2)]
        for payload in responses:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                provider = ResponsesProvider("http://127.0.0.1:1/v1/responses", "local-double", transport=lambda *args: (200, payload))
                provider.decide({}, ("describe_catalog",), {})

    def test_retry_is_bounded_and_timeout_is_not_retried(self):
        transport = Mock(side_effect=[(429, b"{}"), (200, self.response())])
        provider = ResponsesProvider("http://127.0.0.1:1/v1/responses", "local-double", transport=transport)
        provider.decide({}, ("describe_catalog",), {})
        self.assertEqual(transport.call_count, 2)
        self.assertEqual(provider.usage[0]["status"], "unavailable")
        timeout = Mock(side_effect=TimeoutError)
        provider = ResponsesProvider("http://127.0.0.1:1/v1/responses", "local-double", transport=timeout)
        with self.assertRaisesRegex(ValueError, "TIMEOUT_NO_RETRY"):
            provider.decide({}, ("describe_catalog",), {})
        self.assertEqual(timeout.call_count, 1)

    def test_strict_json_and_response_size_are_checked(self):
        for payload in ('{"x":1,"x":2}', '{"x":NaN}', '{"truncated"'):
            with self.assertRaises(ValueError):
                strict_json(payload)
        provider = ResponsesProvider("http://127.0.0.1:1/v1/responses", "local-double", transport=lambda *args: (200, b" "*262145))
        with self.assertRaisesRegex(ValueError, "RESPONSE_LIMIT"):
            provider.decide({}, ("describe_catalog",), {})
        schema = tool_schema("submit_plan")["parameters"]
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["required"]), set(schema["properties"]))

    def test_host_deadline_and_redirect_policy_do_not_enable_external_requests(self):
        transport = Mock(return_value=(200, self.response()))
        provider = ResponsesProvider("http://127.0.0.1:1/v1/responses", "local-double", transport=transport,
                                     clock=lambda: 10)
        with self.assertRaisesRegex(ValueError, "PROVIDER_DEADLINE"):
            provider.decide({}, ("describe_catalog",), {"active_seconds": 0})
        transport.assert_not_called()
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://example.invalid"))


class M2LoopUnitTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / "work/unit-temp"
        scratch.mkdir(parents=True, exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=scratch)
        self.path = Path(self.directory.name)
        # A file-hash seam only. All worker calls in these unit tests are injected doubles.
        (self.path / "scoped.sqlite").write_bytes(b"unit snapshot identity")
        self.provider = ScriptedProvider()
        self.state = {"state": "PLAN_READY", "status": "active", "question": "Net sales in January 2026 and February 2026",
            "slots": {"metric": "net_sales_v1", "periods": ["2026-01", "2026-02"], "regions": ["North"]},
            "provider_mode": self.provider.mode, "decision_fixture": None, "catalog": {}, "schema": {},
            "source_fingerprints": source_fingerprints(), "snapshot_file_hash": file_hash(self.path / "scoped.sqlite"),
            "contract": {"contract_id": "unit-contract", "metric": "net_sales_v1", "metric_origin": "explicit_question",
                "periods": ["2026-01", "2026-02"], "regions": ["North"], "currency": "USD", "as_of": "2026-03-01",
                "groupings": ["none", "channel"]},
            "evidence": {}, "trace": [], "query_receipts": [], "call_ids": [], "action_results": {},
            "turn": 0, "attempts": 0, "reference_queries": 0, "repairs": 0}
        self.session = Session(self.path, self.state, self.provider)

    def tearDown(self):
        self.directory.cleanup()

    def query(self, call_id="q1", grouping="none"):
        return Decision(call_id, "execute_query", {"contract_id": "unit-contract", "grouping": grouping,
            "sql": proposed_sql("net_sales_v1", grouping)})

    def worker(self, grouping="none"):
        return {"ok": True, "rows": expected_rows("net_sales_v1", grouping=grouping),
                "columns": ["period_key", "group_key", "value_cents"],
                "duration_ms": 1, "child_pid": 42, "child_reaped": True}

    def test_repeated_query_call_id_reuses_saved_result_without_another_worker(self):
        decisions = [self.query(), self.query(), self.query("q2", "channel")]
        def decide(*args):
            if decisions:
                return decisions.pop(0)
            return Decision("end", "finish_report", {"result_ids": [entry["result_id"] for entry in self.state["evidence"].values()]})
        with patch.object(self.provider, "decide", side_effect=decide), patch("governed_analytics.orchestrator.run_sql",
                side_effect=[self.worker(), self.worker(), self.worker("channel"), self.worker("channel")]) as worker:
            report = self.session.drive()
        self.assertEqual(report["status"], "completed")
        self.assertEqual(worker.call_count, 4)  # Two candidates plus two separate references.
        self.assertEqual(len(report["query_receipts"]), 2)
        self.assertTrue(report["tool_trace"][1]["deduplicated"])

    def test_conflicting_query_call_id_fails_without_a_second_candidate(self):
        with patch.object(self.provider, "decide", side_effect=[self.query(), self.query("q1", "channel")]), \
             patch("governed_analytics.orchestrator.run_sql", side_effect=[self.worker(), self.worker()]) as worker:
            report = self.session.drive()
        self.assertEqual(report["reason"], "CONFLICTING_CALL_ID")
        self.assertEqual(worker.call_count, 2)
        self.assertIsNone(report["summary"])

    def test_turn_sql_repair_and_active_time_caps_stop_before_a_worker(self):
        for field, value, reason in (("turn", 12, "TURN_LIMIT"), ("attempts", 6, "SQL_BUDGET_EXHAUSTED"),
                                     ("repairs", 3, "SQL_BUDGET_EXHAUSTED"), ("active_seconds", 61, "RUN_TIMEOUT")):
            with self.subTest(field=field):
                state = {**self.state, field: value, "trace": [], "call_ids": [], "action_results": {}}
                session = Session(self.path, state, self.provider)
                with patch.object(self.provider, "decide", return_value=self.query()), \
                     patch("governed_analytics.orchestrator.run_sql") as worker:
                    report = session.drive()
                self.assertEqual(report["status"], "budget_exhausted")
                self.assertEqual(report["reason"], reason)
                worker.assert_not_called()

    def test_reference_cancellation_retains_both_child_cleanup_receipts(self):
        cancelled = {"ok": False, "error": "CANCELLED", "duration_ms": 2, "child_pid": 43, "child_reaped": True}
        with patch("governed_analytics.orchestrator.run_sql", side_effect=[self.worker(), cancelled]):
            result = self.session.dispatch("execute_query", self.query().arguments)
        self.assertEqual(result["error"], "CANCELLED")
        receipt = self.state["query_receipts"][0]
        self.assertTrue(receipt["child_reaped"])
        self.assertEqual(receipt["reference_execution"]["child_pid"], 43)
        self.assertTrue(receipt["reference_execution"]["child_reaped"])
        self.assertEqual(self.state["evidence"], {})

    def test_oracle_rejects_correct_amounts_bound_to_the_wrong_scope(self):
        report = {"status": "completed", "contract": self.state["contract"], "source_immutability": {"unchanged": True},
            "evidence": {"none": {"rows": expected_rows("net_sales_v1"), "result_id":"r1", "query_id":"q1", "verified":True},
                         "channel": {"rows": expected_rows("net_sales_v1", grouping="channel"), "result_id":"r2", "query_id":"q2", "verified":True}},
            "summary": {"previous_cents":1000000,"current_cents":780000,"delta_cents":-220000,"percent_change":"-22.0",
                        "channel_deltas_cents":{"direct":-220000,"partner":0},"evidence_ids":["r1","r2"]},
            "query_receipts":[{"query_id":"q1","verification":"verified"},{"query_id":"q2","verification":"verified"}]}
        case, gold = {"identity": "north_analyst"}, {"status": "completed", "metric": "net_sales_v1"}
        self.assertTrue(score(case, gold, report, "governed")["task_success"])
        report["contract"] = {**report["contract"], "regions": ["South"]}
        self.assertFalse(score(case, gold, report, "governed")["task_success"])
        failed = {"status": "failed", "reason": "UNRELATED_FAILURE", "summary": None,
                  "source_immutability": {"unchanged": True}}
        self.assertFalse(score(case, {"status": "failed", "reason": "INVALID_EVIDENCE_REFERENCE"}, failed, "governed")["task_success"])


class M2OwnedProcessUnitTests(unittest.TestCase):
    def test_child_launch_failure_returns_a_bounded_failure_receipt(self):
        result = run_sql(Path("unused"), "SELECT 1", {}, _popen=Mock(side_effect=OSError("authored launch failure")))
        self.assertEqual(result["error"], "WORKER_FAILED")
        self.assertIsNone(result["child_pid"])
        self.assertTrue(result["child_reaped"])

    def test_precancel_or_exhausted_deadline_never_creates_a_child(self):
        cancel = threading.Event()
        cancel.set()
        popen = Mock()
        cancelled = run_sql(Path("unused"), "SELECT 1", {}, cancel_event=cancel, _popen=popen)
        expired = run_sql(Path("unused"), "SELECT 1", {}, timeout=0, _popen=popen)
        self.assertEqual(cancelled["error"], "CANCELLED")
        self.assertEqual(expired["error"], "QUERY_TIMEOUT")
        popen.assert_not_called()

    def test_parent_timeout_kills_and_reaps_only_owned_fake(self):
        process = Mock(pid=42, returncode=None)
        process.poll.side_effect = [None, -9]
        process.communicate.side_effect = [subprocess.TimeoutExpired("owned", 0.05), ("", "")]
        with patch("governed_analytics.execution.time.monotonic", side_effect=[0, 0.01, 4, 4.01]):
            result = run_sql(Path("unused"), "SELECT 1", {}, _popen=lambda *args, **kwargs: process)
        self.assertEqual(result["error"], "QUERY_TIMEOUT")
        self.assertTrue(result["child_reaped"])
        process.kill.assert_called()
        process.wait.assert_called_once()

    def test_keyboard_interrupt_reaps_owned_fake_before_propagating(self):
        process = Mock(pid=42, returncode=None)
        process.poll.return_value = None
        process.communicate.side_effect = KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            run_sql(Path("unused"), "SELECT 1", {}, _popen=lambda *args, **kwargs: process)
        process.kill.assert_called_once()
        process.wait.assert_called_once()
