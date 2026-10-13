import subprocess
import unittest
from governed_analytics.upgrade_budget import Budget, UpgradeError, new_budget


class Clock:
    def __init__(self):
        self.now = 0.0
    def __call__(self):
        return self.now


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.state = new_budget(0)
        self.budget = Budget(self.state, self.clock)

    def test_active_time_transport_and_cleanup_share_deadline(self):
        self.clock.now = 59
        self.assertEqual(self.budget.remaining(), 1)
        self.budget.charge()
        self.clock.now = 60.1
        with self.assertRaisesRegex(UpgradeError, "RUN_DEADLINE"):
            self.budget.check()

    def test_resume_preserves_counters_and_excludes_only_recorded_pause(self):
        self.budget.admit_request(100)
        self.budget.admit_tool()
        self.clock.now = 5
        self.budget.charge()
        self.clock.now = 105
        self.state["pause_seconds"] += 100
        resumed = Budget(self.state, self.clock)
        self.assertEqual(resumed.remaining(), 55)
        self.assertEqual(resumed.state["requests"], 1)
        self.assertEqual(resumed.state["tools"], 1)
        self.assertEqual(resumed.state["pause_seconds"], 100)
        self.clock.now = 901
        with self.assertRaisesRegex(UpgradeError, "RUN_DEADLINE"):
            resumed.check()

    def test_request_and_tool_exhaustion_cannot_reset_on_resume(self):
        for _ in range(8):
            self.budget.admit_request(100)
        for _ in range(12):
            self.budget.admit_tool()
        resumed = Budget(self.state, self.clock)
        with self.assertRaisesRegex(UpgradeError, "REQUEST_BUDGET_EXHAUSTED"):
            resumed.admit_request(1)
        with self.assertRaisesRegex(UpgradeError, "TOOL_BUDGET_EXHAUSTED"):
            resumed.admit_tool()
        self.assertEqual(self.state["output_token_reservations"], 12000)

    def test_request_input_and_output_caps(self):
        with self.assertRaisesRegex(UpgradeError, "REQUEST_TOO_LARGE"):
            self.budget.admit_request(65537)
        self.state["input_bytes"] = 131070
        with self.assertRaisesRegex(UpgradeError, "INPUT_BUDGET_EXHAUSTED"):
            self.budget.admit_request(3)
        self.state["output_token_reservations"] = 12000
        with self.assertRaisesRegex(UpgradeError, "TOKEN_BUDGET_EXHAUSTED"):
            self.budget.admit_request(1)

    def test_observed_usage_exhaustion_before_action(self):
        with self.assertRaisesRegex(UpgradeError, "TOKEN_BUDGET_EXHAUSTED"):
            self.budget.usage({"prompt_tokens": 5, "completion_tokens": 12001})
        self.assertEqual(self.state["known_output_tokens"], 12001)

    def test_unknown_is_not_zero_and_partial_coverage_is_explicit(self):
        self.budget.admit_request(1)
        self.budget.usage(None)
        self.assertIsNone(self.budget.metrics()["output_tokens"])
        self.budget.admit_request(1)
        self.budget.usage({"prompt_tokens": 5, "completion_tokens": 10})
        self.assertIsNone(self.budget.metrics()["output_tokens"])
        self.assertEqual(self.state["known_output_tokens"], 10)
        self.assertIsNone(self.state["actual_cost_usd"])
        self.assertEqual(self.state["live_allocation_inr"], 0)

    def test_clock_reset_is_not_new_budget(self):
        self.clock.now = -1
        with self.assertRaisesRegex(UpgradeError, "CLOCK_CONTEXT_CHANGED"):
            self.budget.check()


class OwnedHelperTests(unittest.TestCase):
    """Injected process handles only: no Popen, sockets or filesystem writes."""
    def test_parent_kills_and_reaps_inside_remaining_deadline(self):
        from governed_analytics.upgrade_transport import owned_exchange
        clock = Clock()
        observed = {}

        class Stream:
            closed = False
            def close(self):
                self.closed = True

        class Process:
            pid = 42
            returncode = None
            stdin, stdout, stderr = Stream(), Stream(), Stream()
            def communicate(self, input=None, timeout=None):
                if input is not None:
                    observed["private_pipe"] = input
                clock.now += timeout
                raise subprocess.TimeoutExpired("owned", timeout)
            def poll(self):
                return self.returncode
            def kill(self):
                observed["killed"] = True
            def wait(self, timeout):
                observed["cleanup_bound"] = timeout
                clock.now += min(.01, timeout)
                self.returncode = -1

        process = Process()
        def factory(command, **kwargs):
            observed["command"] = command
            return process
        with self.assertRaisesRegex(UpgradeError, "TRANSPORT_TIMEOUT") as raised:
            owned_exchange("governed_analytics.upgrade_http_worker", {"body": "synthetic input"},
                           timeout=1, _popen=factory, _clock=clock)
        self.assertTrue(raised.exception.receipt["child_reaped"])
        self.assertTrue(observed["killed"])
        self.assertLessEqual(clock.now, 1)
        self.assertLessEqual(observed["cleanup_bound"], .251)
        self.assertNotIn("synthetic input", repr(observed["command"]))
        self.assertIn("synthetic input", observed["private_pipe"])
        self.assertTrue(all(s.closed for s in (process.stdin, process.stdout, process.stderr)))

    def test_pre_cancel_never_creates_child(self):
        from governed_analytics.upgrade_transport import owned_exchange
        class Cancel:
            def is_set(self):
                return True
        def forbidden(*args, **kwargs):
            self.fail("must not spawn")
        with self.assertRaisesRegex(UpgradeError, "CANCELLED") as raised:
            owned_exchange("unused", {}, timeout=1, cancel_event=Cancel(), _popen=forbidden)
        self.assertIsNone(raised.exception.receipt["child_pid"])

    def test_unreaped_child_is_explicit_failure(self):
        from governed_analytics.upgrade_transport import owned_exchange
        clock = Clock()
        class Process:
            pid = 43
            returncode = None
            stdin = stdout = stderr = None
            def communicate(self, input=None, timeout=None):
                clock.now += timeout
                raise subprocess.TimeoutExpired("owned", timeout)
            def poll(self):
                return None
            def kill(self):
                pass
            def wait(self, timeout):
                clock.now += timeout
                raise subprocess.TimeoutExpired("owned", timeout)
        with self.assertRaisesRegex(UpgradeError, "CHILD_CLEANUP_FAILED") as raised:
            owned_exchange("unused", {}, timeout=1, _popen=lambda *a, **k: Process(), _clock=clock)
        self.assertFalse(raised.exception.receipt["child_reaped"])
        self.assertEqual(clock.now, 1)


if __name__ == "__main__":
    unittest.main()
