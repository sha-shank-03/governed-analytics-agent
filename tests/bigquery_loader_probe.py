"""Native synthetic probe helper. No credential discovery, socket or HTTP code."""
import json
import sys
import threading
import time
from unittest.mock import patch
from governed_analytics.bigquery_transport import BigQueryTransport, PreparedToken
from governed_analytics.upgrade_budget import UpgradeError
from tests.bigquery_contract import config


def main():
    value = json.loads(sys.stdin.buffer.read(129))
    case = value.get("case")
    if case == "wait":
        # The parent owns this bounded test process and must kill/reap it.
        time.sleep(5)
        sys.stdout.write(json.dumps({"error": "PROBE_WAIT_FINISHED"}))
        return
    if case not in ("slow_callback", "cancelled_inert"):
        raise ValueError("Unknown synthetic probe")
    counts = {"loader_calls": 0, "http_calls": 0}
    def slow_loader():
        counts["loader_calls"] += 1
        time.sleep(0.15)
        return "SYNTHETIC_INERT_TOKEN_ONLY"
    def no_http(*args, **kwargs):
        counts["http_calls"] += 1
        return {"http_status": 200, "body": "{}"}
    start = time.monotonic()
    error = None
    with patch("governed_analytics.bigquery_transport.owned_exchange", no_http):
        try:
            if case == "slow_callback":
                transport = BigQueryTransport(config(), sandbox_enabled=True, token_loader=slow_loader)
                transport("GET", "/projects/fictional-ga-test/datasets/ga_sandbox_north_views/tables/orders_north_v1",
                          None, timeout=0.05)
            else:
                event = threading.Event()
                event.set()
                transport = BigQueryTransport(config(), sandbox_enabled=True,
                                               prepared_token=PreparedToken("SYNTHETIC_INERT_TOKEN_ONLY"))
                transport("GET", "/projects/fictional-ga-test/datasets/ga_sandbox_north_views/tables/orders_north_v1",
                          None, timeout=0.05, cancel_event=event)
        except UpgradeError as exc:
            error = exc.code
    sys.stdout.write(json.dumps({"case": case, "error": error, **counts,
        "elapsed_seconds": time.monotonic() - start, "actual_network_calls": 0}))


if __name__ == "__main__":
    main()
