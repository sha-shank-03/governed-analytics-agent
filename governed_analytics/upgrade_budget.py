"""Persisted U1 admission counters; no keys, pricing guesses or shared ledger."""
import time


class UpgradeError(Exception):
    """Only host-defined codes and bounded receipts may reach artifacts."""
    def __init__(self, code, receipt=None):
        super().__init__(code)
        self.code = code
        self.receipt = receipt or {}


LIMITS = {"active_seconds": 60.0, "lifetime_seconds": 900.0,
          "requests": 8, "tools": 12, "input_bytes": 131072,
          "output_tokens": 12000, "request_bytes": 65536,
          "response_bytes": 262144, "sql_bytes": 8192,
          "history_bytes": 65536, "question_bytes": 4096,
          "per_request_tokens": 1500, "transport_seconds": 15.0,
          "sql_seconds": 3.0, "cleanup_seconds": 0.5}


def new_budget(now=None):
    return {"created_monotonic": time.monotonic() if now is None else now,
            "active_seconds": 0.0, "pause_seconds": 0.0,
            "requests": 0, "tools": 0, "input_bytes": 0,
            "output_token_reservations": 0, "known_input_tokens": 0,
            "known_output_tokens": 0, "usage_known_requests": 0,
            "transport_retries": 0, "live_allocation_inr": 0,
            "estimated_cost_usd": None, "actual_cost_usd": None,
            "unknown_outcomes": 0}


class Budget:
    def __init__(self, state, clock=time.monotonic, limits=None):
        self.state, self.clock = state, clock
        self.limits = {**LIMITS, **(limits or {})}
        self.tick = clock()

    def charge(self):
        now = self.clock()
        elapsed = now - self.tick
        if elapsed < 0 or now < self.state["created_monotonic"]:
            raise UpgradeError("CLOCK_CONTEXT_CHANGED")
        self.state["active_seconds"] += elapsed
        self.tick = now

    def remaining(self):
        now = self.clock()
        if now < self.tick or now < self.state["created_monotonic"]:
            raise UpgradeError("CLOCK_CONTEXT_CHANGED")
        active = self.limits["active_seconds"] - self.state["active_seconds"] - now + self.tick
        lifetime = self.limits["lifetime_seconds"] - now + self.state["created_monotonic"]
        return max(0, min(active, lifetime))

    def check(self):
        if self.remaining() <= 0:
            raise UpgradeError("RUN_DEADLINE")
        if self.state["known_output_tokens"] > self.limits["output_tokens"]:
            raise UpgradeError("TOKEN_BUDGET_EXHAUSTED")
        # UTF-8 request bytes provide a conservative admitted context bound; also
        # reject implausible observed input usage rather than silently accepting it.
        if self.state["known_input_tokens"] > self.limits["input_bytes"]:
            raise UpgradeError("INPUT_BUDGET_EXHAUSTED")

    def admit_request(self, size):
        self.check()
        if size > self.limits["request_bytes"]:
            raise UpgradeError("REQUEST_TOO_LARGE")
        if self.state["requests"] >= self.limits["requests"]:
            raise UpgradeError("REQUEST_BUDGET_EXHAUSTED")
        if self.state["input_bytes"] + size > self.limits["input_bytes"]:
            raise UpgradeError("INPUT_BUDGET_EXHAUSTED")
        cap = self.limits["per_request_tokens"]
        if self.state["output_token_reservations"] + cap > self.limits["output_tokens"]:
            raise UpgradeError("TOKEN_BUDGET_EXHAUSTED")
        self.state["requests"] += 1
        self.state["input_bytes"] += size
        self.state["output_token_reservations"] += cap

    def admit_tool(self):
        self.check()
        if self.state["tools"] >= self.limits["tools"]:
            raise UpgradeError("TOOL_BUDGET_EXHAUSTED")
        self.state["tools"] += 1

    def usage(self, usage):
        if usage is None:
            return
        self.state["usage_known_requests"] += 1
        self.state["known_input_tokens"] += usage["prompt_tokens"]
        self.state["known_output_tokens"] += usage["completion_tokens"]
        self.check()

    def metrics(self):
        self.charge()
        known = self.state["usage_known_requests"] == self.state["requests"] and self.state["requests"] > 0
        return {**self.state, "limits": self.limits,
                "input_tokens": self.state["known_input_tokens"] if known else None,
                "output_tokens": self.state["known_output_tokens"] if known else None,
                "cost_status": "unavailable_local_double",
                "usage_label": "synthetic_if_reported"}
