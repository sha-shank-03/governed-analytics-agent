"""Authored local HTTP scenarios. These are protocol/failure checks, never model quality."""
import json
import re
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from .providers import proposed_sql
from .upgrade_gateway import GatewayConfig, GatewayProvider
from .upgrade_intents import FIELDS


def tool_response(name, arguments, call_id="call_1", *, usage=True):
    result = {"id": "gen_local_synthetic", "choices": [{"index": 0, "finish_reason": "tool_calls",
        "message": {"role": "assistant", "content": None, "tool_calls": [{"id": call_id,
            "type": "function", "function": {"name": name,
            "arguments": arguments if type(arguments) is str else json.dumps(arguments)}}]}}]}
    if usage:
        result["usage"] = {"prompt_tokens": 120, "completion_tokens": 60, "total_tokens": 180}
    return result


def authored_decision(payload, scenario, number):
    observation = json.loads([m for m in payload["messages"] if m["role"] == "user"][-1]["content"])
    if scenario == "malformed-call":
        return tool_response("propose_intent", '{"metric":null,"metric":"net_sales_v1"}', f"call_{number}")
    if observation["state"] == "INTENT":
        if scenario == "unknown-intent":
            return tool_response("handoff", {"reason": "unknown_intent"}, f"call_{number}")
        text = observation["question"].lower()
        measures = ("discounts_v1" if "discount total" in text else "refunds_v1" if "refund total" in text
                    else "gross_sales_v1" if "gross" in text else "net_sales_v1")
        periods = sorted(set(re.findall(r"\b\d{4}-(?:0[1-9]|1[0-2])\b", text)))
        # Authored fixture wording may refer to months without year; this is only a double.
        if len(periods) != 2:
            periods = observation["available_periods"][:2]
        semantic = {"metric": measures, "periods": periods, "regions": observation["allowed_regions"],
                    "groupings": ["none", "channel"], "currency": "USD", "ambiguities": []}
        return tool_response("propose_intent", semantic, f"call_{number}")
    contract, evidence = observation["confirmed_contract"], observation["evidence"]
    group = next((g for g in contract["groupings"] if g not in evidence), None)
    if group:
        sql = proposed_sql(contract["metric"], group, observation["schema_version"])
        if scenario == "unauthorized-query":
            sql = "SELECT load_extension('untrusted')"
        return tool_response("execute_query", {"contract_id": contract["contract_id"], "grouping": group,
                                               "sql": sql}, f"call_{number}")
    ids = list(evidence.values())
    if scenario == "false-completion":
        ids = ["forged-total", "forged-channel"]
    return tool_response("finish_report", {"result_ids": ids}, f"call_{number}")


@contextmanager
def local_double(scenario="freeform-confirmation", *, responder=None):
    records = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if self.path != "/v1/chat/completions" or not 0 < size <= 65536:
                    self.send_error(400)
                    return
                payload = json.loads(self.rfile.read(size))
                records.append(payload)
                if responder:
                    responder(self, payload, len(records))
                    return
                if scenario == "slow-provider":
                    time.sleep(1.5)
                body = json.dumps(authored_decision(payload, scenario, len(records))).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        config = GatewayConfig(f"http://127.0.0.1:{server.server_port}/v1/chat/completions", "local/synthetic-tool-model")
        yield config, records
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def run_demo(scenario, out):
    from .upgrade import start, resume
    from .state import atomic_json
    with local_double(scenario) as (config, records):
        limits = {"transport_seconds": 0.75} if scenario == "slow-provider" else None
        question = ("Show South sales for January and February" if scenario == "denied-scope" else
            "How much less did our North business retain after discounts and refunds in February compared with January?")
        report = start(question,
            "north_analyst", out, GatewayProvider(config), limits=limits)
        if report["status"] == "awaiting_confirmation":
            proposal = report["proposal"]
            answer = {"proposal_id": proposal["proposal_id"], "semantic": {k: proposal[k] for k in FIELDS}}
            # A demo uses an explicit authored external answer, never claims a human/live run.
            atomic_json(out / "authored-demo-confirmation.json", {"label": "authored_external_answer", **answer})
            report = resume(out, answer, GatewayProvider(config))
        atomic_json(out / "local-double-receipt.json", {"mode": "local_double", "scenario": scenario,
            "requests_observed": len(records), "external_confirmation": "authored_demo_answer_if_required",
            "live_inference_calls": 0, "external_sandbox_calls": 0})
        return report
