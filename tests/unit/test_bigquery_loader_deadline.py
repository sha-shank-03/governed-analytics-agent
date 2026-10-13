"""Pure deadline/admission probes. No process, socket, credential or file access."""
import math
import threading
import unittest
from unittest.mock import patch
from governed_analytics.bigquery_transport import BigQueryTransport, PreparedToken
from governed_analytics.upgrade_budget import UpgradeError
from governed_analytics.upgrade_transport import owned_exchange
from tests.bigquery_contract import Clock, config

PATH = "/projects/fictional-ga-test/datasets/ga_sandbox_north_views/tables/orders_north_v1"


def inert_transport():
    return BigQueryTransport(config(), sandbox_enabled=True,
                             prepared_token=PreparedToken("SYNTHETIC_INERT_TOKEN_ONLY"))


class LoaderDeadlineTests(unittest.TestCase):
    def test_obsolete_executable_loader_is_rejected_without_invocation(self):
        calls = []
        class Loader:
            def __call__(self):
                calls.append("loader")
                raise AssertionError("Never invoke a dynamic loader")
            def __bool__(self):
                raise AssertionError("Never introspect a dynamic loader")
        with patch("governed_analytics.bigquery_transport.owned_exchange", side_effect=AssertionError("No HTTP")):
            with self.assertRaises(UpgradeError) as caught:
                BigQueryTransport(config(), sandbox_enabled=True, token_loader=Loader())
        self.assertEqual(caught.exception.code, "BQ_DYNAMIC_TOKEN_LOADER_FORBIDDEN")
        self.assertEqual(calls, [])

    def test_only_exact_inert_token_type_can_cross_transport_boundary(self):
        class ExecutableToken(PreparedToken):
            def __getattribute__(self, name):
                raise AssertionError("Subclass getter must not execute")
        for token in ({"token": "SYNTHETIC"}, lambda: "SYNTHETIC", ExecutableToken("SYNTHETIC")):
            with self.subTest(kind=type(token).__name__), self.assertRaises(UpgradeError) as caught:
                BigQueryTransport(config(), sandbox_enabled=True, prepared_token=token)
            self.assertEqual(caught.exception.code, "BQ_PREPARED_TOKEN_REQUIRED")

    def test_inert_value_is_immutable_and_repr_hides_synthetic_value(self):
        token = PreparedToken("SYNTHETIC_INERT_TOKEN_ONLY")
        self.assertNotIn("SYNTHETIC", repr(token))
        with self.assertRaises(AttributeError):
            token._value = "OTHER"
        with self.assertRaises(UpgradeError):
            BigQueryTransport(config(), origin="http://127.0.0.1:12345/bigquery/v2", prepared_token=token)

    def test_exhausted_nonfinite_and_invalid_windows_never_initiate_http(self):
        transport = inert_transport()
        for timeout in (0, -1, math.inf, math.nan, True, "0.05"):
            calls = []
            def exchange(*args, **kwargs):
                calls.append("http")
                raise AssertionError("No HTTP")
            with self.subTest(timeout=str(timeout)), patch("governed_analytics.bigquery_transport.owned_exchange", exchange):
                with self.assertRaises(UpgradeError) as caught:
                    transport("GET", PATH, None, timeout=timeout)
            self.assertEqual(caught.exception.code, "TRANSPORT_TIMEOUT")
            self.assertEqual(calls, [])

    def test_cancelled_inert_request_never_initiates_http(self):
        cancel = threading.Event()
        cancel.set()
        calls = []
        with patch("governed_analytics.bigquery_transport.owned_exchange", lambda *a, **k: calls.append("http")):
            with self.assertRaises(UpgradeError) as caught:
                inert_transport()("GET", PATH, None, timeout=0.05, cancel_event=cancel)
        self.assertEqual(caught.exception.code, "CANCELLED")
        self.assertEqual(calls, [])
        self.assertFalse(caught.exception.receipt["remote_outcome_unknown"])

    def test_elapsed_admission_budget_cannot_initiate_http(self):
        clock, calls = Clock(), []
        def admission(*args):
            clock.sleep(0.15)
        with patch("governed_analytics.bigquery_transport.time.monotonic", clock), \
                patch("governed_analytics.bigquery_transport.validate_request", admission), \
                patch("governed_analytics.bigquery_transport.owned_exchange", lambda *a, **k: calls.append("http")):
            with self.assertRaises(UpgradeError) as caught:
                inert_transport()("GET", PATH, None, timeout=0.05)
        self.assertEqual(caught.exception.code, "TRANSPORT_TIMEOUT")
        self.assertEqual(calls, [])
        self.assertTrue(caught.exception.receipt["child_reaped"])

    def test_cancellation_during_admission_cannot_initiate_http(self):
        cancel, calls = threading.Event(), []
        def admission(*args):
            cancel.set()
        with patch("governed_analytics.bigquery_transport.validate_request", admission), \
                patch("governed_analytics.bigquery_transport.owned_exchange", lambda *a, **k: calls.append("http")):
            with self.assertRaises(UpgradeError) as caught:
                inert_transport()("GET", PATH, None, timeout=0.05, cancel_event=cancel)
        self.assertEqual(caught.exception.code, "CANCELLED")
        self.assertEqual(calls, [])

    def test_admission_and_http_keep_one_absolute_deadline(self):
        clock, safe_calls = Clock(), []
        clock.now = 100
        def admission(*args):
            clock.sleep(0.012)
        def exchange(module, payload, **kwargs):
            safe_calls.append({"module": module, "timeout": kwargs["timeout"],
                               "absolute_deadline": kwargs["absolute_deadline"],
                               "child_timeout": payload["timeout"], "token_in_private_payload": type(payload["token"]) is str})
            return {"http_status": 200, "body": "{}", "child_pid": 42, "child_reaped": True}
        with patch("governed_analytics.bigquery_transport.time.monotonic", clock), \
                patch("governed_analytics.bigquery_transport.validate_request", admission), \
                patch("governed_analytics.bigquery_transport.owned_exchange", exchange):
            inert_transport()("GET", PATH, None, timeout=0.05)
        self.assertEqual(len(safe_calls), 1)
        self.assertAlmostEqual(safe_calls[0]["absolute_deadline"], 100.05)
        self.assertAlmostEqual(safe_calls[0]["timeout"], 0.038)
        self.assertEqual(safe_calls[0]["child_timeout"], safe_calls[0]["timeout"])
        self.assertTrue(safe_calls[0]["token_in_private_payload"])
        self.assertNotIn("SYNTHETIC", str(safe_calls))

    def test_late_owned_response_cannot_be_accepted_or_retried(self):
        clock, calls = Clock(), []
        def exchange(*args, **kwargs):
            calls.append("http")
            clock.sleep(0.06)
            return {"http_status": 200, "body": "{}", "child_pid": 42, "child_reaped": True,
                    "remote_outcome_unknown": True}
        with patch("governed_analytics.bigquery_transport.time.monotonic", clock), \
                patch("governed_analytics.bigquery_transport.owned_exchange", exchange):
            with self.assertRaises(UpgradeError) as caught:
                inert_transport()("GET", PATH, None, timeout=0.05)
        self.assertEqual(caught.exception.code, "TRANSPORT_TIMEOUT")
        self.assertEqual(caught.exception.receipt["child_pid"], 42)
        self.assertTrue(caught.exception.receipt["child_reaped"])
        self.assertEqual(calls, ["http"])

    def test_owned_supervisor_cannot_restart_an_expired_parent_deadline(self):
        clock, processes = Clock(), []
        clock.now = 10
        def popen(*args, **kwargs):
            processes.append("process")
            raise AssertionError("No child")
        with self.assertRaises(UpgradeError) as caught:
            owned_exchange("governed_analytics.bigquery_http_worker", {}, timeout=0.05,
                           absolute_deadline=9.99, _clock=clock, _popen=popen)
        self.assertEqual(caught.exception.code, "TRANSPORT_TIMEOUT")
        self.assertEqual(processes, [])


if __name__ == "__main__":
    unittest.main()
