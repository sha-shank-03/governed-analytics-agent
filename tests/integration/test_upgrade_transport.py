"""LEASE REQUIRED: actual loopback HTTP, owned helpers, slow reads and cancellation."""
import json
import os
import threading
import time
import unittest
from governed_analytics.upgrade_budget import Budget, UpgradeError, new_budget
from governed_analytics.upgrade_double import local_double, tool_response
from governed_analytics.upgrade_gateway import GatewayProvider
from governed_analytics.upgrade_transport import http_exchange


def send(handler, body, status=200, retry=None):
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    if retry:
        handler.send_header("Retry-After", retry)
    handler.end_headers()
    handler.wfile.write(body)


class TransportTests(unittest.TestCase):
    def assert_reaped(self, receipt):
        self.assertTrue(receipt["child_reaped"], receipt)
        pid = receipt["child_pid"]
        self.assertIsInstance(pid, int)
        if os.name == "nt":
            import ctypes
            kernel = ctypes.windll.kernel32
            kernel.OpenProcess.restype = ctypes.c_void_p
            handle = kernel.OpenProcess(0x1000, False, pid)
            if handle:
                try:
                    code = ctypes.c_ulong()
                    self.assertTrue(kernel.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code)))
                    self.assertNotEqual(code.value, 259)
                finally:
                    kernel.CloseHandle(ctypes.c_void_p(handle))
        else:
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)

    def request(self, config, timeout=1.0, event=None):
        return http_exchange(config.endpoint, b'{"model":"local/synthetic-tool-model","messages":[]}',
                             timeout=timeout, cancel_event=event)

    def test_real_response_and_owned_child_exit(self):
        def responder(handler, payload, number):
            send(handler, b'{"ok":true}')
        with local_double(responder=responder) as (config, records):
            result = self.request(config, 3)
            self.assertEqual(result["http_status"], 200)
            self.assertEqual(result["body"], '{"ok":true}')
            self.assertEqual(len(records), 1)
            self.assert_reaped(result)

    def test_stalled_headers_parent_wall_deadline(self):
        def responder(handler, payload, number):
            time.sleep(1.25)
            send(handler, b'{}')
        with local_double(responder=responder) as (config, records):
            started = time.monotonic()
            with self.assertRaisesRegex(UpgradeError, "TRANSPORT_TIMEOUT") as raised:
                self.request(config, .7)
            elapsed = time.monotonic() - started
            self.assertLess(elapsed, 1.15, "0.7 second parent budget + 0.45 scheduling tolerance")
            self.assert_reaped(raised.exception.receipt)
            self.assertTrue(raised.exception.receipt["remote_outcome_unknown"])
            self.assertEqual(len(records), 1)

    def test_dripping_body_cannot_extend_total_deadline(self):
        def responder(handler, payload, number):
            handler.send_response(200)
            handler.send_header("Content-Length", "100")
            handler.end_headers()
            for _ in range(15):
                handler.wfile.write(b"x")
                handler.wfile.flush()
                time.sleep(.1)
        with local_double(responder=responder) as (config, records):
            started = time.monotonic()
            with self.assertRaisesRegex(UpgradeError, "TRANSPORT_TIMEOUT") as raised:
                self.request(config, .7)
            self.assertLess(time.monotonic() - started, 1.15)
            self.assert_reaped(raised.exception.receipt)
            self.assertEqual(len(records), 1)

    def test_cancel_reaps_child_without_resend(self):
        def responder(handler, payload, number):
            time.sleep(1.25)
            send(handler, b'{}')
        with local_double(responder=responder) as (config, records):
            event = threading.Event()
            timer = threading.Timer(.3, event.set)
            timer.start()
            started = time.monotonic()
            try:
                with self.assertRaisesRegex(UpgradeError, "CANCELLED") as raised:
                    self.request(config, 2, event)
                self.assertLess(time.monotonic() - started, .9)
                self.assert_reaped(raised.exception.receipt)
                self.assertLessEqual(len(records), 1)
            finally:
                timer.cancel()
                timer.join(timeout=1)

    def test_oversize_body_fails_closed(self):
        def responder(handler, payload, number):
            send(handler, b'x' * 262145)
        with local_double(responder=responder) as (config, records):
            with self.assertRaisesRegex(UpgradeError, "RESPONSE_TOO_LARGE") as raised:
                self.request(config, 3)
            self.assert_reaped(raised.exception.receipt)
            self.assertEqual(len(records), 1)

    def test_disconnect_after_send_is_unknown_without_retry(self):
        def responder(handler, payload, number):
            handler.connection.close()
        with local_double(responder=responder) as (config, records):
            provider = GatewayProvider(config)
            budget = Budget(new_budget())
            with self.assertRaises(UpgradeError):
                provider.decide({"state": "INTENT"}, ("handoff",), budget)
            self.assertEqual(len(records), 1)
            self.assertTrue(provider.last_receipt["remote_outcome_unknown"])
            self.assertEqual(budget.state["requests"], 1)
            self.assertEqual(budget.state["unknown_outcomes"], 1)
            self.assertEqual(budget.state["transport_retries"], 0)
            self.assertIsNone(budget.state["actual_cost_usd"])
            self.assert_reaped(provider.last_receipt)

    def test_real_http_failures_typed_single_request_and_redacted(self):
        for status, expected in ((401, "HTTP_AUTH"), (402, "HTTP_CREDIT"), (429, "HTTP_RATE_LIMIT"),
                                 (500, "HTTP_CAPACITY"), (503, "HTTP_CAPACITY")):
            with self.subTest(status=status):
                def responder(handler, payload, number):
                    send(handler, b'Bearer sk-canarySECRET123', status, "3")
                with local_double(responder=responder) as (config, records):
                    provider = GatewayProvider(config)
                    budget = Budget(new_budget())
                    with self.assertRaisesRegex(UpgradeError, expected):
                        provider.decide({"state": "INTENT"}, ("handoff",), budget)
                    self.assertEqual(len(records), 1)
                    self.assertEqual(provider.last_receipt["retry_after_seconds"], 3)
                    self.assertEqual(budget.state["transport_retries"], 0)
                    self.assertNotIn("canary", json.dumps(provider.dump_state()))
                    self.assert_reaped(provider.last_receipt)

    def test_redirect_never_follows_location(self):
        def responder(handler, payload, number):
            handler.send_response(302)
            handler.send_header("Location", "http://127.0.0.1:1/private")
            handler.send_header("Content-Length", "0")
            handler.end_headers()
        with local_double(responder=responder) as (config, records):
            result = self.request(config, 3)
            self.assertEqual(result["http_status"], 302)
            self.assertEqual(len(records), 1)
            self.assert_reaped(result)


if __name__ == "__main__":
    unittest.main()
