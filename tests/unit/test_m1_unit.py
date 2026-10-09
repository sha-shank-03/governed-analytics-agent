import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from governed_analytics.catalog import resolve_request
from governed_analytics.data import TABLES, create_projection, load_fixture, scoped_rows, source_fingerprints
from governed_analytics.orchestrator import Session, validate_decision
from governed_analytics.providers import Decision, FANOUT_SQL, ScriptedProvider, proposed_sql
from governed_analytics.reports import summarize
from governed_analytics.sql_worker import configure, execute
from governed_analytics.verification import compare, reference_sql

PARAMETERS = {"previous": "2026-01", "current": "2026-02", "as_of": "2026-03-01"}


class M1MeaningTests(unittest.TestCase):
    def test_unqualified_revenue_has_no_resolved_metric(self):
        slots = resolve_request("Revenue in January 2026 versus February 2026", "north_analyst")
        self.assertIsNone(slots["metric"])
        self.assertEqual(slots["regions"], ["North"])

    def test_provider_cannot_resolve_metric_by_submitting_a_guess(self):
        provider = ScriptedProvider()
        decision = provider.decide({"state": "CATALOG_READY", "turn": 1, "metric": None},
                                   ("request_clarification", "submit_plan"), {"turns": 11})
        self.assertEqual(decision.tool, "request_clarification")
        host = Session(Path("unused-unit-path"), {"slots": {"metric": None}}, provider)
        with self.assertRaisesRegex(ValueError, "UNRESOLVED_OR_CONFLICTING_METRIC"):
            host.dispatch("submit_plan", {"metric": "net_sales_v1", "groupings": ["none", "channel"]})

    def test_explicit_net_and_periods_are_bound(self):
        slots = resolve_request("Net sales in February 2026 versus January 2026", "north_analyst")
        self.assertEqual(slots["metric"], "net_sales_v1")
        self.assertEqual(slots["periods"], ["2026-01", "2026-02"])

    def test_all_scope_and_private_requests_are_denied(self):
        for question in ("Net sales for all regions in January 2026 and February 2026", "Show customer email"):
            self.assertTrue(resolve_request(question, "north_analyst")["denied"])

    def test_unknown_tool_and_forged_identity_argument_are_rejected(self):
        for decision in (Decision("x", "shell", {}), Decision("x", "describe_catalog", {"identity": "all_sales_analyst"})):
            with self.assertRaises(ValueError):
                validate_decision(decision, ("describe_catalog",))


class M1SqlTests(unittest.TestCase):
    def setUp(self):
        self.before = source_fingerprints()
        scratch = Path(__file__).resolve().parents[2] / "work" / "unit-temp"
        scratch.mkdir(parents=True, exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=scratch)
        self.path = Path(self.directory.name) / "north.sqlite"
        self.data = load_fixture()
        create_projection(self.path, scoped_rows(self.data, ("North",)))
        self.connection = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, cached_statements=0)
        configure(self.connection)

    def tearDown(self):
        self.connection.close()
        self.directory.cleanup()
        self.assertEqual(source_fingerprints(), self.before)

    def test_fixture_totals_have_an_independent_python_arithmetic_check(self):
        # No verifier/query-builder reuse. These calculations follow the authored fixture definition.
        totals = {}
        for order_id, order_date, region, channel, status in self.data["orders"]:
            if region != "North" or status != "completed":
                continue
            lines = [line for line in self.data["order_lines"] if line[1] == order_id]
            refunds = [row for row in self.data["refunds"] if row[1] == order_id and row[4] == "posted" and row[2] < "2026-03-01"]
            value = sum(line[2] * line[3] - line[4] for line in lines) - sum(row[3] for row in refunds)
            key = (order_date[:7], channel)
            totals[key] = totals.get(key, 0) + value
        self.assertEqual(totals, {("2026-01", "direct"): 600000, ("2026-01", "partner"): 400000,
                                  ("2026-02", "direct"): 380000, ("2026-02", "partner"): 400000})

    def test_candidate_and_reference_totals_equal_hand_checked_values(self):
        candidate = execute(self.connection, proposed_sql("net_sales_v1", "none"), PARAMETERS)
        reference = execute(self.connection, reference_sql("net_sales_v1", "none"), PARAMETERS)
        self.assertTrue(compare(candidate, reference)["verified"])
        self.assertEqual(candidate["rows"], [["2026-01", "all", 1000000], ["2026-02", "all", 780000]])

    def test_wrong_join_rejected_then_correct_channel_query_verifies(self):
        bad = execute(self.connection, FANOUT_SQL, PARAMETERS)
        ref = execute(self.connection, reference_sql("net_sales_v1", "none"), PARAMETERS)
        self.assertTrue(bad["ok"], bad)
        self.assertEqual(compare(bad, ref)["error"], "GRAIN_OR_VALUE_MISMATCH")
        good = execute(self.connection, proposed_sql("net_sales_v1", "channel"), PARAMETERS)
        channel_ref = execute(self.connection, reference_sql("net_sales_v1", "channel"), PARAMETERS)
        self.assertTrue(compare(good, channel_ref)["verified"])

    def test_private_data_is_physically_absent_and_region_filter_is_unnecessary(self):
        result = execute(self.connection, "SELECT order_id, region FROM orders", {})
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["rows"]), 5)
        self.assertTrue(all(row[1] == "North" for row in result["rows"]))
        self.assertNotIn("CANARY", json.dumps(result))
        self.assertFalse(execute(self.connection, "SELECT * FROM customers_private", {})["ok"])

    def test_write_attach_introspection_and_extension_are_denied(self):
        attacks = ["DELETE FROM orders", "CREATE TABLE stolen(x)", "PRAGMA query_only=OFF",
                   "ATTACH DATABASE ':memory:' AS stolen", "SELECT * FROM sqlite_master",
                   "SELECT * FROM pragma_table_info('orders')", "SELECT load_extension('fake')",
                   "WITH x AS (SELECT 1) DELETE FROM orders", "SELECT 1; DELETE FROM orders"]
        for sql in attacks:
            with self.subTest(sql=sql):
                self.assertFalse(execute(self.connection, sql, {})["ok"])
        count = execute(self.connection, "SELECT count(*) FROM orders", {})
        self.assertEqual(count["rows"], [[5]])

    def test_four_catalog_measures_are_verified(self):
        expected = {"gross_sales_v1": [1200000, 1100000], "discounts_v1": [100000, 120000],
                    "refunds_v1": [100000, 200000], "net_sales_v1": [1000000, 780000]}
        for metric, amounts in expected.items():
            with self.subTest(metric=metric):
                candidate = execute(self.connection, proposed_sql(metric, "none"), PARAMETERS)
                reference = execute(self.connection, reference_sql(metric, "none"), PARAMETERS)
                self.assertTrue(compare(candidate, reference)["verified"])
                self.assertEqual([row[2] for row in candidate["rows"]], amounts)

    def test_oversized_results_and_recursive_sql_are_not_accepted(self):
        self.assertEqual(execute(self.connection,
            "SELECT a.order_id FROM orders a CROSS JOIN orders b CROSS JOIN orders c", {})["error"], "RESULT_OVERFLOW")
        recursive = "WITH RECURSIVE x(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM x WHERE n<5) SELECT n FROM x"
        self.assertFalse(execute(self.connection, recursive, {})["ok"])


class M1ReportTests(unittest.TestCase):
    def test_summary_derives_figures_and_reconciles_channel_contributions(self):
        contract = {"periods": ["2026-01", "2026-02"]}
        evidence = {"none": {"result_id": "total", "rows": [["2026-01", "all", 1000000], ["2026-02", "all", 780000]]},
                    "channel": {"result_id": "channel", "rows": [["2026-01", "direct", 600000], ["2026-01", "partner", 400000],
                                                                 ["2026-02", "direct", 380000], ["2026-02", "partner", 400000]]}}
        summary = summarize(contract, evidence, ["total", "channel"])
        self.assertEqual(summary["delta_cents"], -220000)
        self.assertEqual(summary["percent_change"], "-22.0")
        self.assertEqual(sum(summary["channel_deltas_cents"].values()), -220000)
        with self.assertRaisesRegex(ValueError, "INVALID_EVIDENCE_REFERENCE"):
            summarize(contract, evidence, ["invented", "channel"])


if __name__ == "__main__":
    unittest.main()
