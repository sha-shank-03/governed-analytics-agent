"""LEASE REQUIRED: scoped SQLite, actual Gateway-native HTTP and SQL helper chain."""
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from governed_analytics.data import load_fixture
from governed_analytics.state import read_checkpoint
from governed_analytics.upgrade import start, resume
from governed_analytics.upgrade_double import local_double, authored_decision, tool_response
from governed_analytics.upgrade_gateway import GatewayProvider
from governed_analytics.upgrade_intents import FIELDS
from tests.integration.test_upgrade_transport import send


def answer(report, changes=None):
    proposal = report["proposal"]
    return {"proposal_id": proposal["proposal_id"], "semantic": {
            **{key: proposal[key] for key in FIELDS}, **(changes or {})}}


def oracle(metric, regions, periods):
    """Test-only direct fixture arithmetic; no actor query or runtime reference import."""
    data = load_fixture("demo-v1")
    orders = {row[0]: row for row in data["orders"] if row[2] in regions and row[4] == "completed"}
    totals = {period: 0 for period in periods}
    for oid, order in orders.items():
        period = order[1][:7]
        if period not in totals:
            continue
        gross = sum(r[2] * r[3] for r in data["order_lines"] if r[1] == oid)
        discount = sum(r[4] for r in data["order_lines"] if r[1] == oid)
        refund = sum(r[3] for r in data["refunds"] if r[1] == oid and r[4] == "posted" and r[2] < data["as_of"])
        totals[period] += {"gross_sales_v1": gross, "discounts_v1": discount,
                           "refunds_v1": refund, "net_sales_v1": gross - discount - refund}[metric]
    return totals


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        # Resource artifacts live under the allowed repository, never a system temp path.
        root = Path(__file__).resolve().parents[2] / "work"
        root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="u1-test-", dir=root)
        self.output = Path(self.temp.name) / "run"

    def tearDown(self):
        self.temp.cleanup()

    def begin(self, config, **kwargs):
        return start("How much less did North retain after discounts and refunds in February compared with January?",
                     "north_analyst", self.output, GatewayProvider(config), **kwargs)

    def test_freeform_pauses_then_actual_verified_totals_and_channels(self):
        with local_double() as (config, records):
            pending = self.begin(config)
            self.assertEqual(pending["status"], "awaiting_confirmation")
            self.assertEqual(pending["host_counters"]["candidates"], 0)
            self.assertEqual(len(records), 1)
            final = resume(self.output, answer(pending), GatewayProvider(config))
            self.assertEqual(final["status"], "completed", final)
            self.assertEqual(set(final["evidence"]), {"none", "channel"})
            expected = oracle("net_sales_v1", ["North"], ["2026-01", "2026-02"])
            actual = {row[0]: row[2] for row in final["evidence"]["none"]["rows"]}
            self.assertEqual(actual, expected)
            for period in expected:
                self.assertEqual(sum(row[2] for row in final["evidence"]["channel"]["rows"] if row[0] == period), expected[period])
            self.assertEqual(final["host_counters"]["candidates"], 2)
            self.assertEqual(final["host_counters"]["references"], 2)
            self.assertEqual(final["metrics"]["requests"], 4)
            self.assertEqual(final["metrics"]["transport_retries"], 0)
            self.assertGreaterEqual(final["metrics"]["pause_seconds"], 0)
            self.assertIsNone(final["metrics"]["actual_cost_usd"])
            self.assertFalse((self.output / ".run.lock").exists())
            for receipt in final["query_receipts"]:
                self.assertTrue(receipt["candidate"]["child_reaped"])
                self.assertTrue(receipt["reference"]["child_reaped"])
            for request in records:
                self.assertNotIn("reference_sql", json.dumps(request))
                calls = [call["id"] for m in request["messages"] for call in m.get("tool_calls", [])]
                results = [m["tool_call_id"] for m in request["messages"] if m["role"] == "tool"]
                self.assertEqual(calls, results)

    def test_confirmation_supports_each_measure_with_independent_oracle(self):
        for measure in ("gross_sales_v1", "discounts_v1", "refunds_v1"):
            with self.subTest(measure=measure), local_double() as (config, records):
                output = self.output.parent / measure
                pending = start("Compare North gross totals in 2026-01 and 2026-02", "north_analyst", output, GatewayProvider(config))
                final = resume(output, answer(pending, {"metric": measure}), GatewayProvider(config))
                self.assertEqual(final["status"], "completed", final)
                actual = {row[0]: row[2] for row in final["evidence"]["none"]["rows"]}
                self.assertEqual(actual, oracle(measure, ["North"], ["2026-01", "2026-02"]))

    def test_physical_projection_contains_only_granted_orders(self):
        with local_double() as (config, records):
            pending = self.begin(config)
            with closing(sqlite3.connect(self.output / "scoped.sqlite")) as db:
                self.assertEqual(db.execute("SELECT DISTINCT region FROM orders").fetchall(), [("North",)])
                names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                self.assertNotIn("private_customers", names)
                self.assertFalse(db.execute("SELECT l.order_id FROM order_lines l LEFT JOIN orders o ON o.order_id=l.order_id WHERE o.order_id IS NULL").fetchall())
            self.assertEqual(pending["host_counters"]["candidates"], 0)

    def test_host_scope_denial_before_any_provider_request(self):
        with local_double() as (config, records):
            report = start("Show South sales for January and February", "north_analyst", self.output, GatewayProvider(config))
            self.assertEqual(report["status"], "access_denied")
            self.assertEqual(report["reason"], "SCOPE_NOT_GRANTED")
            self.assertEqual(records, [])
            self.assertEqual(report["metrics"]["requests"], 0)

    def test_unknown_intent_hands_off_without_sql(self):
        with local_double("unknown-intent") as (config, records):
            report = self.begin(config)
            self.assertEqual(report["status"], "handoff")
            self.assertEqual(report["reason"], "unknown_intent")
            self.assertEqual(report["query_receipts"], [])

    def test_unauthorized_query_is_attempted_but_never_accepted(self):
        with local_double("unauthorized-query") as (config, records):
            pending = self.begin(config)
            final = resume(self.output, answer(pending), GatewayProvider(config))
            self.assertEqual(final["status"], "failed")
            self.assertEqual(final["reason"], "POLICY_DENIED")
            self.assertEqual(final["evidence"], {})
            self.assertEqual(final["tool_trace"][-1]["guarded_outcome"], "blocked")
            self.assertEqual(final["host_counters"]["candidates"], 1)
            self.assertEqual(final["host_counters"]["references"], 0)

    def test_malformed_call_retains_usage_but_no_action(self):
        with local_double("malformed-call") as (config, records):
            report = self.begin(config)
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["reason"], "DUPLICATE_JSON_KEY")
            self.assertEqual(report["host_counters"]["candidates"], 0)
            self.assertEqual(report["gateway_receipts"][0]["usage"]["total_tokens"], 180)

    def test_false_completion_has_no_numeric_summary(self):
        with local_double("false-completion") as (config, records):
            pending = self.begin(config)
            report = resume(self.output, answer(pending), GatewayProvider(config))
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["reason"], "UNVERIFIED_COMPLETION")
            self.assertIsNone(report["summary"])
            self.assertEqual(len(report["evidence"]), 2)

    def test_slow_transport_stops_and_reserves_unknown_outcome(self):
        with local_double("slow-provider") as (config, records):
            report = self.begin(config, limits={"transport_seconds": .7})
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["reason"], "TRANSPORT_TIMEOUT")
            self.assertEqual(report["metrics"]["requests"], 1)
            self.assertEqual(report["metrics"]["unknown_outcomes"], 1)
            self.assertEqual(report["query_receipts"], [])
            self.assertTrue(report["gateway_receipts"][0]["child_reaped"])

    def test_stale_confirmation_or_mutated_snapshot_never_executes(self):
        with local_double() as (config, records):
            pending = self.begin(config)
            bad = {**answer(pending), "proposal_id": "forged"}
            report = resume(self.output, bad, GatewayProvider(config))
            self.assertEqual(report["reason"], "STALE_CONFIRMATION")
            self.assertEqual(report["metrics"]["requests"], 1)
            self.assertEqual(report["query_receipts"], [])
        with local_double() as (config, records):
            output = self.output.parent / "mutated"
            pending = start("North January compared with February", "north_analyst", output, GatewayProvider(config))
            with closing(sqlite3.connect(output / "scoped.sqlite")) as db:
                with db:
                    db.execute("UPDATE orders SET region='South'")
            report = resume(output, answer(pending), GatewayProvider(config))
            self.assertEqual(report["reason"], "SNAPSHOT_CHANGED")
            self.assertEqual(report["metrics"]["requests"], 1)

    def test_telemetry_canary_redaction_across_artifacts(self):
        def responder(handler, payload, number):
            send(handler, b'Bearer sk-canarySECRET123', 401)
        with local_double(responder=responder) as (config, records):
            report = start("api_key=sk-canarySECRET123 North totals", "north_analyst", self.output, GatewayProvider(config))
            self.assertEqual(report["reason"], "HTTP_AUTH")
            for file in self.output.glob("*"):
                if file.suffix in (".json", ".jsonl"):
                    self.assertNotIn("canarySECRET123", file.read_text(encoding="utf-8"), file.name)
            self.assertNotIn("canarySECRET123", json.dumps(records))
            self.assertEqual(read_checkpoint(self.output)["budget"]["requests"], 1)

    def test_cumulative_request_limit_persists_after_pause(self):
        with local_double() as (config, records):
            pending = self.begin(config, limits={"requests": 1})
            report = resume(self.output, answer(pending), GatewayProvider(config))
            self.assertEqual(report["status"], "budget_exhausted")
            self.assertEqual(report["reason"], "REQUEST_BUDGET_EXHAUSTED")
            self.assertEqual(len(records), 1)
            self.assertEqual(report["metrics"]["requests"], 1)
            self.assertEqual(report["host_counters"]["candidates"], 0)


if __name__ == "__main__":
    unittest.main()
