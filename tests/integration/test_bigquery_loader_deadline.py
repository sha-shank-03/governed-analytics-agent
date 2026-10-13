"""LEASE REQUIRED: synthetic native controls. No external HTTP or real credentials."""
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from governed_analytics.bigquery_transport import BigQueryTransport, PreparedToken
from governed_analytics.state import atomic_json
from governed_analytics.upgrade_budget import UpgradeError
from governed_analytics.upgrade_transport import owned_exchange
from tests.bigquery_contract import config

PATH = "/projects/fictional-ga-test/datasets/ga_sandbox_north_views/tables/orders_north_v1"


class NativeLoaderDeadlineTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[2] / "work"
        root.mkdir(exist_ok=True)
        self.output = Path(tempfile.mkdtemp(prefix="u2a-loader-native-", dir=root))
        print("U2A_LOADER_ARTIFACT_DIR=" + str(self.output))

    def test_slow_dynamic_loader_is_rejected_before_invocation_and_http(self):
        result = owned_exchange("tests.bigquery_loader_probe", {"case": "slow_callback"}, timeout=2)
        atomic_json(self.output / "probe.json", result)
        self.assertEqual(result["error"], "BQ_DYNAMIC_TOKEN_LOADER_FORBIDDEN")
        self.assertEqual(result["loader_calls"], 0)
        self.assertEqual(result["http_calls"], 0)
        self.assertEqual(result["actual_network_calls"], 0)
        self.assertLess(result["elapsed_seconds"], 0.05)
        self.assertTrue(result["child_reaped"])

    def test_cancelled_inert_request_is_rejected_before_http(self):
        result = owned_exchange("tests.bigquery_loader_probe", {"case": "cancelled_inert"}, timeout=2)
        atomic_json(self.output / "probe.json", result)
        self.assertEqual(result["error"], "CANCELLED")
        self.assertEqual(result["loader_calls"], 0)
        self.assertEqual(result["http_calls"], 0)
        self.assertEqual(result["actual_network_calls"], 0)
        self.assertTrue(result["child_reaped"])

    def inert(self):
        return BigQueryTransport(config(), sandbox_enabled=True,
                                 prepared_token=PreparedToken("SYNTHETIC_INERT_TOKEN_ONLY"))

    @staticmethod
    def synthetic_owned(module, payload, **kwargs):
        # Ignore the would-be HTTP payload, including the synthetic token. The
        # only launched helper is this no-network test module with inert input.
        return owned_exchange("tests.bigquery_loader_probe", {"case": "wait"}, **kwargs)

    def test_inert_request_deadline_kills_and_reaps_synthetic_owned_wait(self):
        before = time.monotonic()
        with patch("governed_analytics.bigquery_transport.owned_exchange", self.synthetic_owned):
            with self.assertRaises(UpgradeError) as caught:
                self.inert()("GET", PATH, None, timeout=0.6)
        elapsed = time.monotonic() - before
        atomic_json(self.output / "deadline.json", {"error": caught.exception.code,
            "receipt": caught.exception.receipt, "elapsed_seconds": elapsed, "actual_network_calls": 0})
        self.assertEqual(caught.exception.code, "TRANSPORT_TIMEOUT")
        self.assertTrue(caught.exception.receipt["child_reaped"])
        self.assertIsNotNone(caught.exception.receipt["child_pid"])
        self.assertLessEqual(elapsed, 0.8)

    def test_inert_request_cancellation_kills_and_reaps_synthetic_owned_wait(self):
        cancel = threading.Event()
        timer = threading.Timer(0.25, cancel.set)
        timer.start()
        try:
            before = time.monotonic()
            with patch("governed_analytics.bigquery_transport.owned_exchange", self.synthetic_owned):
                with self.assertRaises(UpgradeError) as caught:
                    self.inert()("GET", PATH, None, timeout=2, cancel_event=cancel)
            elapsed = time.monotonic() - before
            atomic_json(self.output / "cancel.json", {"error": caught.exception.code,
                "receipt": caught.exception.receipt, "elapsed_seconds": elapsed, "actual_network_calls": 0})
            self.assertEqual(caught.exception.code, "CANCELLED")
            self.assertTrue(caught.exception.receipt["child_reaped"])
            self.assertIsNotNone(caught.exception.receipt["child_pid"])
            self.assertLessEqual(elapsed, 0.8)
        finally:
            timer.cancel()
            timer.join(timeout=1)
            self.assertFalse(timer.is_alive())


if __name__ == "__main__":
    unittest.main()
