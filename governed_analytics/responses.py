"""Responses wire protocol. M2 exercises injected transports/loopback doubles only."""
import json
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
from .providers import Decision


def strict_json(payload):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("DUPLICATE_JSON_KEY")
            result[key] = value
        return result
    return json.loads(payload, object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("NONFINITE_JSON")))


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def tool_schema(name):
    text = {"type": "string"}
    props = {
        "describe_catalog": {}, "refresh_catalog": {},
        "request_clarification": {"slot": {"type": "string", "enum": ["metric"]}},
        "submit_plan": {"metric": {"type": "string", "enum": ["gross_sales_v1", "discounts_v1", "refunds_v1", "net_sales_v1"]},
                        "groupings": {"type": "array", "items": {"type": "string", "enum": ["none", "channel"]}}},
        "execute_query": {"contract_id": text, "grouping": {"type": "string", "enum": ["none", "channel"]}, "sql": text},
        "finish_report": {"result_ids": {"type": "array", "items": text}},
    }[name]
    return {"type": "function", "name": name, "description": "Use this host-validated analysis tool.",
            "strict": True, "parameters": {"type": "object", "properties": props,
                                            "required": list(props), "additionalProperties": False}}


class ResponsesProvider:
    decision_fixture = None

    def __init__(self, endpoint, model, *, transport=None, allow_external=False, credential=None,
                 clock=time.monotonic):
        url = urlsplit(endpoint)
        local = url.hostname in ("127.0.0.1", "localhost", "::1") and url.scheme == "http"
        if not local and (not allow_external or not credential or url.scheme != "https"):
            raise ValueError("EXTERNAL_PROVIDER_DISABLED")
        if url.username or url.password or url.fragment or url.query or not model:
            raise ValueError("INVALID_PROVIDER_CONFIGURATION")
        self.endpoint, self.model = endpoint, model
        self.mode = "local_provider_protocol" if local else "live_model"
        self.clock, self.deadline = clock, clock() + 180
        self.credential = credential if not local else None
        self.transport = transport or self._http
        self.context, self.last_call_id, self.usage = [], None, []

    def _http(self, endpoint, body, timeout):
        headers = {"Content-Type": "application/json"}
        if self.credential:
            headers["Authorization"] = "Bearer " + self.credential
        request = Request(endpoint, data=body, headers=headers, method="POST")
        opener = build_opener(ProxyHandler({}), NoRedirect())
        try:
            with opener.open(request, timeout=timeout) as response:
                return response.status, response.read(262145)
        except HTTPError as response:
            return response.code, response.read(262145)

    def dump_state(self):
        # Credentials and endpoint are never serialized. Operator reconfiguration is required to resume.
        return {"context": self.context, "last_call_id": self.last_call_id, "usage": self.usage}

    def restore_state(self, value):
        self.context, self.last_call_id = value["context"], value["last_call_id"]
        self.usage = value.get("usage", [])

    def decide(self, observation, allowed_tools, remaining_budget):
        host_seconds = remaining_budget.get("active_seconds", 180)
        call_deadline = min(self.deadline, self.clock() + host_seconds)
        if self.last_call_id:
            self.context.append({"type": "function_call_output", "call_id": self.last_call_id,
                                 "output": json.dumps(observation.get("last_result"), allow_nan=False)})
        elif not self.context:
            self.context = [{"role": "user", "content": json.dumps(observation, allow_nan=False)}]
        request = {"model": self.model, "store": False, "parallel_tool_calls": False,
                   "max_output_tokens": 1500, "tool_choice": "required",
                   "instructions": "Analyze only the scoped catalog. Use one allowed tool at a time. Do not infer unresolved metric choices or business causes.",
                   "input": self.context, "tools": [tool_schema(name) for name in allowed_tools]}
        body = json.dumps(request, allow_nan=False).encode()
        if len(body) > 262144:
            raise ValueError("PROVIDER_CONTEXT_LIMIT")
        for attempt in range(2):
            remaining = call_deadline - self.clock()
            if remaining <= 0:
                raise ValueError("PROVIDER_DEADLINE")
            try:
                status, payload = self.transport(self.endpoint, body, min(20, remaining))
            except TimeoutError:
                raise ValueError("PROVIDER_TIMEOUT_NO_RETRY") from None
            except OSError:
                raise ValueError("PROVIDER_TRANSPORT_FAILURE") from None
            if status in (429, 503) and attempt == 0:
                continue
            if status != 200:
                raise ValueError("PROVIDER_HTTP_" + str(status))
            break
        if self.clock() > call_deadline:
            raise ValueError("PROVIDER_DEADLINE")
        if not isinstance(payload, bytes) or len(payload) > 262144:
            raise ValueError("PROVIDER_RESPONSE_LIMIT")
        response = strict_json(payload)
        if type(response) is not dict or response.get("status") != "completed":
            raise ValueError("PROVIDER_INCOMPLETE")
        output = response.get("output")
        if type(output) is not list or any(type(item) is not dict for item in output):
            raise ValueError("PROVIDER_OUTPUT_INVALID")
        for item in output:
            if item.get("type") == "message":
                blocks = item.get("content")
                if type(blocks) is not list or any(type(block) is not dict for block in blocks):
                    raise ValueError("PROVIDER_OUTPUT_INVALID")
                if any(block.get("type") == "refusal" for block in blocks):
                    raise ValueError("PROVIDER_REFUSAL")
        calls = [item for item in output if item.get("type") == "function_call"]
        if len(calls) != 1:
            raise ValueError("PROVIDER_EXPECTED_ONE_CALL")
        call = calls[0]
        if call.get("name") not in allowed_tools or type(call.get("call_id")) is not str:
            raise ValueError("PROVIDER_TOOL_INVALID")
        if type(call.get("arguments")) is not str:
            raise ValueError("PROVIDER_ARGUMENTS_INVALID")
        arguments = strict_json(call["arguments"])
        if type(arguments) is not dict:
            raise ValueError("PROVIDER_ARGUMENTS_INVALID")
        self.usage.append({"status": "observed" if response.get("usage") is not None else "unavailable",
                           "usage": response.get("usage")})
        self.context.extend(output)  # Preserve reasoning and function-call items for continuation.
        self.last_call_id = call["call_id"]
        return Decision(call["call_id"], call["name"], arguments)
