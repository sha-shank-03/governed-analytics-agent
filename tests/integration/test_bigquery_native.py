"""LEASE REQUIRED. Authored native HTTP/SQLite checks, never a real BigQuery call."""
import json
import sqlite3
import tempfile
import threading
import time
import unittest
from contextlib import closing, contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from governed_analytics.bigquery_snapshot import SnapshotImporter
from governed_analytics.bigquery_transport import BigQueryTransport
from governed_analytics.data import digest
from governed_analytics.state import atomic_json
from governed_analytics.upgrade import start, resume
from governed_analytics.upgrade_budget import UpgradeError
from governed_analytics.upgrade_double import local_double
from governed_analytics.upgrade_gateway import GatewayProvider
from tests.bigquery_contract import ContractAPI, Clock
from tests.integration.test_upgrade_workflow import answer


@contextmanager
def native_double(api, behavior=None):
    arrivals = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.respond()

        def do_POST(self):
            self.respond()

        def respond(self):
            try:
                arrivals.append({"monotonic": time.monotonic(), "path": self.path,
                                 "authorization_present": "Authorization" in self.headers})
                if behavior == "slow":
                    time.sleep(1.0)
                size = int(self.headers.get("Content-Length", "0"))
                if size > 65536 or not self.path.startswith("/bigquery/v2/"):
                    self.send_error(400)
                    return
                body = json.loads(self.rfile.read(size)) if size else None
                response = api(self.command, self.path[len("/bigquery/v2"):], body)
                raw = response["body"].encode()
                self.send_response(response["http_status"])
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                if behavior == "drip":
                    for byte in raw:
                        self.wfile.write(bytes([byte]))
                        self.wfile.flush()
                        time.sleep(0.05)
                else:
                    self.wfile.write(raw)
            except (OSError, ValueError):
                pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield "http://127.0.0.1:" + str(server.server_port) + "/bigquery/v2", arrivals
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class NativeSnapshotTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[2] / "work"
        root.mkdir(exist_ok=True)
        self.output = Path(tempfile.mkdtemp(prefix="u2a-native-", dir=root))
        # Retain exact import state, local source/report/database and assertions.
        print("U2A_ARTIFACT_DIR=" + str(self.output))

    def importer(self, api, origin):
        def persist(state):
            api.persist(state)
            atomic_json(self.output / "import.json", state)
        return SnapshotImporter(api.config, BigQueryTransport(api.config, origin=origin), persist)

    def test_native_import_to_confirmed_independent_local_sql(self):
        api = ContractAPI()
        with native_double(api) as (origin, arrivals):
            importer = self.importer(api, origin)
            snapshot = importer.run()
            self.assertEqual(snapshot.payload()["provenance"]["mode"], "local_double")
            self.assertTrue(all(not r["authorization_present"] for r in arrivals))
            gaps = [b["monotonic"] - a["monotonic"] for a, b in zip(arrivals, arrivals[1:])]
            self.assertTrue(all(g >= 0.85 for g in gaps), gaps)
            self.assertTrue(all(r.get("child_reaped") is True for r in importer.state["receipts"]))
            atomic_json(self.output / "native-http.json", {"arrivals": arrivals, "minimum_gap": min(gaps)})
        with local_double() as (gateway, records):
            out = self.output / "run"
            pending = start("Compare North net sales in 2026-01 and 2026-02", "north_analyst", out,
                            GatewayProvider(gateway), trusted_snapshot=snapshot)
            self.assertEqual(pending["status"], "awaiting_confirmation")
            final = resume(out, answer(pending), GatewayProvider(gateway))
            self.assertEqual(final["status"], "completed", final)
            # Direct arithmetic over injected source rows, not actor/reference SQL.
            expected = {}
            for oid, ordered, region, channel, status in api.data["orders"]:
                lines = [r for r in api.data["order_lines"] if r[1] == oid]
                refund = sum(r[3] for r in api.data["refunds"] if r[1] == oid and r[4] == "posted" and r[2] < api.data["as_of"])
                expected[ordered[:7]] = sum(r[2] * r[3] - r[4] for r in lines) - refund
            actual = {r[0]: r[2] for r in final["evidence"]["none"]["rows"]}
            self.assertEqual(actual, expected)
            for period, value in expected.items():
                self.assertEqual(sum(r[2] for r in final["evidence"]["channel"]["rows"] if r[0] == period), value)
            self.assertEqual(final["contract"]["snapshot_hash"], digest({k: v for k, v in api.data.items() if type(v) is list}))
            self.assertEqual(final["source_snapshot"]["binding"], snapshot.binding())
            self.assertEqual(final["host_counters"]["candidates"], 2)
            self.assertEqual(final["host_counters"]["references"], 2)
            with closing(sqlite3.connect(out / "scoped.sqlite")) as database:
                self.assertEqual(database.execute("SELECT order_id,region FROM orders ORDER BY order_id").fetchall(), [("O1", "North"), ("O2", "North")])
                self.assertEqual(database.execute("SELECT COUNT(*) FROM fulfillment_events").fetchone()[0], 0)
            denied = start("Compare North net sales in 2026-01 and 2026-02", "all_sales_analyst",
                           self.output / "denied", GatewayProvider(gateway), trusted_snapshot=snapshot)
            self.assertEqual(denied["status"], "access_denied")
            self.assertEqual(denied["metrics"]["requests"], 0)
            self.assertEqual(len(records), 4)
        atomic_json(self.output / "assertions.json", {"status": "passed", "independent_cents": expected,
            "verified_cents": actual, "native_http_calls": len(arrivals), "gateway_calls": 4,
            "scope": "North", "external_integration": False})

    def test_drift_never_emits_usable_snapshot(self):
        def drift(api, method, path, body, result, response):
            if api.job_id and "/tables/" in path:
                result["etag"] = "changed-after-query"
            return {"http_status": 200, "body": json.dumps(result)}
        api = ContractAPI(hook=drift)
        with native_double(api) as (origin, arrivals):
            importer = self.importer(api, origin)
            with self.assertRaises(UpgradeError) as caught:
                importer.run()
            self.assertEqual(caught.exception.code, "BQ_METADATA_DRIFT")
            self.assertFalse(importer.state["snapshot_published"])
            self.assertFalse(importer.state["remote_outcome_unknown"])
            self.assertFalse((self.output / "scoped.sqlite").exists())
            self.assertTrue(all(r.get("child_reaped") is True for r in importer.state["receipts"]))
            atomic_json(self.output / "assertions.json", {"status": "passed", "reason": caught.exception.code,
                                                         "native_http_calls": len(arrivals)})

    def test_native_header_and_drip_deadlines_reap_owned_helper(self):
        for behavior in ("slow", "drip"):
            api = ContractAPI()
            with native_double(api, behavior) as (origin, arrivals):
                transport = BigQueryTransport(api.config, origin=origin)
                before = time.monotonic()
                with self.assertRaises(UpgradeError) as caught:
                    transport("GET", "/projects/fictional-ga-test/datasets/ga_sandbox_north_views/tables/orders_north_v1", None, timeout=0.7)
                elapsed = time.monotonic() - before
                self.assertEqual(caught.exception.code, "TRANSPORT_TIMEOUT")
                self.assertTrue(caught.exception.receipt["child_reaped"])
                self.assertLessEqual(elapsed, 0.9)
                atomic_json(self.output / (behavior + ".json"), {"elapsed": elapsed, "error": caught.exception.code,
                    "receipt": caught.exception.receipt, "external_integration": False})

    def test_native_cancel_before_header_reaps_owned_helper(self):
        api, cancel = ContractAPI(), threading.Event()
        with native_double(api, "slow") as (origin, arrivals):
            timer = threading.Timer(0.25, cancel.set)
            timer.start()
            try:
                with self.assertRaises(UpgradeError) as caught:
                    BigQueryTransport(api.config, origin=origin)("GET",
                        "/projects/fictional-ga-test/datasets/ga_sandbox_north_views/tables/orders_north_v1",
                        None, timeout=2, cancel_event=cancel)
                self.assertEqual(caught.exception.code, "CANCELLED")
                self.assertTrue(caught.exception.receipt["child_reaped"])
                atomic_json(self.output / "cancel.json", {"error": caught.exception.code, "receipt": caught.exception.receipt})
            finally:
                timer.cancel()
                timer.join(timeout=1)

    def test_source_tamper_stops_resume_without_query(self):
        api, clock = ContractAPI(), Clock()
        snapshot = SnapshotImporter(api.config, api, api.persist, clock=clock, sleep=clock.sleep).run()
        with local_double() as (gateway, records):
            out = self.output / "run"
            pending = start("Compare North net sales in 2026-01 and 2026-02", "north_analyst", out,
                            GatewayProvider(gateway), trusted_snapshot=snapshot)
            self.assertEqual(pending["status"], "awaiting_confirmation")
            source = json.loads((out / "source_snapshot.json").read_text(encoding="utf-8"))
            source["data"]["order_lines"][0][3] = 900000
            atomic_json(out / "source_snapshot.json", source)
            final = resume(out, answer(pending), GatewayProvider(gateway))
            self.assertEqual(final["status"], "failed")
            self.assertEqual(final["reason"], "SOURCE_CONTEXT_CHANGED")
            self.assertEqual(final["host_counters"]["candidates"], 0)
            self.assertEqual(len(records), 1)
            self.assertIsNone(final["summary"])
            self.assertFalse((out / ".run.lock").exists())
        atomic_json(self.output / "assertions.json", {"status": "passed", "reason": final["reason"],
                                                     "native_queries": 0, "source_tamper_rejected": True})


if __name__ == "__main__":
    unittest.main()
