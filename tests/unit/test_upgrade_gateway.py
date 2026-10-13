"""Pure protocol tests: injected functions only, no sockets or children."""
import json
import unittest
from governed_analytics.upgrade_budget import Budget, UpgradeError, new_budget
from governed_analytics.upgrade_double import tool_response
from governed_analytics.upgrade_events import encoded, redact
from governed_analytics.upgrade_gateway import GatewayConfig, GatewayProvider, strict_json, tool_schema

SEMANTIC = {"metric": "net_sales_v1", "periods": ["2026-01", "2026-02"],
            "regions": ["North"], "groupings": ["none", "channel"], "currency": "USD", "ambiguities": []}


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.config = GatewayConfig("http://127.0.0.1:12345/v1/chat/completions", "local/synthetic-tool-model")
        self.budget = Budget(new_budget())
        self.sent = []

    def provider(self, body, status=200):
        def exchange(endpoint, raw, **kwargs):
            self.sent.append((endpoint, json.loads(raw), kwargs))
            return {"http_status": status, "body": body if type(body) is str else json.dumps(body),
                    "retry_after_seconds": 3, "child_reaped": True}
        return GatewayProvider(self.config, exchange)

    def decide(self, provider):
        return provider.decide({"state": "INTENT", "question": "May compared with April"},
                               ("propose_intent", "handoff"), self.budget)

    def test_native_nested_functions_and_matching_tool_result(self):
        provider = self.provider(tool_response("propose_intent", SEMANTIC))
        decision = self.decide(provider)
        provider.tool_result(decision, {"confirmation_required": True})
        payload = self.sent[0][1]
        self.assertEqual(payload["model"], "local/synthetic-tool-model")
        self.assertEqual(payload["max_tokens"], 1500)
        self.assertFalse(payload["stream"])
        self.assertFalse(payload["parallel_tool_calls"])
        self.assertEqual(payload["tools"][0]["function"]["name"], "propose_intent")
        self.assertEqual(provider.messages[-2]["tool_calls"][0]["id"], provider.messages[-1]["tool_call_id"])
        self.assertEqual(provider.messages[-1]["role"], "tool")
        self.assertEqual(self.budget.state["requests"], 1)
        self.assertEqual(provider.last_receipt["usage"]["completion_tokens"], 60)

    def test_no_extra_authority_in_tool_schema(self):
        fields = tool_schema("propose_intent")["function"]["parameters"]["properties"]
        self.assertNotIn("identity", fields)
        self.assertNotIn("sql", fields)
        self.assertNotIn("url", fields)
        self.assertNotIn("formula", fields)
        self.assertFalse(tool_schema("execute_query")["function"]["parameters"]["additionalProperties"])

    def test_live_endpoints_and_unspecified_models_rejected(self):
        for endpoint in ("https://ai-gateway.vercel.sh/v1/chat/completions", "http://localhost:123/v1/chat/completions",
                         "http://127.0.0.1:123/elsewhere", "http://x:y@127.0.0.1:123/v1/chat/completions",
                         "http://127.0.0.1:123/v1/chat/completions?q=x"):
            with self.subTest(endpoint=endpoint), self.assertRaises(UpgradeError):
                GatewayConfig(endpoint, self.config.model)
        with self.assertRaises(UpgradeError):
            GatewayConfig(self.config.endpoint, "openai/a-real-model")

    def test_duplicate_nonfinite_and_nested_duplicates(self):
        for raw in ('{"a":1,"a":2}', '{"x":NaN}', '{"x":{"a":0,"a":1}}', '{"x":Infinity}'):
            with self.subTest(raw=raw), self.assertRaises(UpgradeError):
                strict_json(raw)

    def test_malformed_arguments_preserve_usage(self):
        provider = self.provider(tool_response("propose_intent", '{"metric":null,"metric":"net_sales_v1"}'))
        with self.assertRaisesRegex(UpgradeError, "DUPLICATE_JSON_KEY"):
            self.decide(provider)
        self.assertEqual(provider.last_receipt["usage"]["total_tokens"], 180)
        self.assertEqual(self.budget.state["known_output_tokens"], 60)
        self.assertEqual(len(self.sent), 1)

    def test_unknown_multiple_truncated_refused_and_extra_arguments(self):
        cases = []
        cases.append(tool_response("shell", {}))
        multiple = tool_response("propose_intent", SEMANTIC)
        multiple["choices"][0]["message"]["tool_calls"] *= 2
        cases.append(multiple)
        truncated = tool_response("propose_intent", SEMANTIC)
        truncated["choices"][0]["finish_reason"] = "length"
        cases.append(truncated)
        refusal = tool_response("propose_intent", SEMANTIC)
        refusal["choices"][0]["message"]["refusal"] = "no"
        cases.append(refusal)
        cases.append(tool_response("propose_intent", {**SEMANTIC, "identity": "all_analyst"}))
        for body in cases:
            with self.subTest(body=body):
                provider = self.provider(body)
                with self.assertRaises(UpgradeError):
                    self.decide(provider)
                self.assertEqual(provider.last_receipt["usage"]["total_tokens"], 180)
        self.assertEqual(len(self.sent), len(cases))

    def test_http_errors_never_retry_and_ignore_body(self):
        for status, code in ((401, "HTTP_AUTH"), (403, "HTTP_AUTH"), (402, "HTTP_CREDIT"),
                             (429, "HTTP_RATE_LIMIT"), (500, "HTTP_CAPACITY"), (503, "HTTP_CAPACITY")):
            with self.subTest(status=status):
                provider = self.provider("Bearer sk-canarySECRET123", status)
                before = len(self.sent)
                with self.assertRaisesRegex(UpgradeError, code):
                    self.decide(provider)
                self.assertEqual(len(self.sent) - before, 1)
                self.assertEqual(provider.last_receipt["retry_after_seconds"], 3)
                self.assertNotIn("canary", json.dumps(provider.dump_state()))
        self.assertEqual(self.budget.state["transport_retries"], 0)

    def test_unknown_usage_and_cost_stay_null(self):
        provider = self.provider(tool_response("propose_intent", SEMANTIC, usage=False))
        self.decide(provider)
        self.assertIsNone(provider.last_receipt["usage"])
        metrics = self.budget.metrics()
        self.assertIsNone(metrics["input_tokens"])
        self.assertIsNone(metrics["actual_cost_usd"])
        self.assertIsNone(metrics["estimated_cost_usd"])

    def test_transport_secret_exception_is_typed_and_unknown(self):
        def exchange(*args, **kwargs):
            raise RuntimeError("Bearer sk-canarySECRET123")
        provider = GatewayProvider(self.config, exchange)
        with self.assertRaisesRegex(UpgradeError, "TRANSPORT_FAILED") as raised:
            self.decide(provider)
        self.assertNotIn("canary", str(raised.exception))
        self.assertNotIn("canary", json.dumps(provider.dump_state()))
        self.assertEqual(self.budget.state["unknown_outcomes"], 1)
        self.assertEqual(self.budget.state["requests"], 1)

    def test_sensitive_arguments_are_not_persisted(self):
        provider = self.provider(tool_response("propose_intent", {**SEMANTIC, "regions": ["sk-canarySECRET123"]}))
        with self.assertRaisesRegex(UpgradeError, "SENSITIVE_OUTPUT_REJECTED"):
            self.decide(provider)
        self.assertNotIn("canary", json.dumps(provider.dump_state()))
        self.assertEqual(redact({"authorization": "x", "text": "Bearer sk-canarySECRET123"}),
                         {"authorization": "[REDACTED]", "text": "[REDACTED]"})

    def test_observation_is_redacted_before_transmission(self):
        provider = self.provider(tool_response("handoff", {"reason": "unknown_intent"}))
        provider.decide({"question": "api_key=sk-canarySECRET123"}, ("handoff",), self.budget)
        self.assertNotIn("canary", json.dumps(self.sent))

    def test_request_bound_and_admission_are_before_transport(self):
        provider = self.provider(tool_response("handoff", {"reason": "unknown_intent"}))
        with self.assertRaises(UpgradeError):
            provider.decide({"question": "a" * 70000}, ("handoff",), self.budget)
        self.assertEqual(len(self.sent), 0)
        self.assertEqual(self.budget.state["requests"], 0)

    def test_restore_is_bound_to_config_and_history_cap(self):
        provider = self.provider(tool_response("propose_intent", SEMANTIC))
        self.decide(provider)
        clone = GatewayProvider(self.config, provider.transport)
        clone.restore_state(provider.dump_state())
        self.assertEqual(clone.messages, provider.messages)
        changed = {**provider.dump_state(), "config_hash": "changed"}
        with self.assertRaisesRegex(UpgradeError, "PROVIDER_CONFIG_CHANGED"):
            clone.restore_state(changed)

    def test_response_size_bound(self):
        provider = self.provider(" " * 262145)
        with self.assertRaisesRegex(UpgradeError, "RESPONSE_TOO_LARGE"):
            self.decide(provider)

    def test_reported_per_request_token_violation_rejected_before_tool(self):
        body = tool_response("propose_intent", SEMANTIC)
        body["usage"] = {"prompt_tokens": 120, "completion_tokens": 1501, "total_tokens": 1621}
        provider = self.provider(body)
        with self.assertRaisesRegex(UpgradeError, "PROVIDER_TOKEN_LIMIT"):
            self.decide(provider)
        self.assertEqual(self.budget.state["known_output_tokens"], 1501)
        self.assertEqual(provider.last_receipt["usage"]["completion_tokens"], 1501)
        self.assertFalse(any(m["role"] == "assistant" for m in provider.messages))


if __name__ == "__main__":
    unittest.main()
