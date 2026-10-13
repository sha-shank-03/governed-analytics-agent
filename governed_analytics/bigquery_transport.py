"""Explicit host transport: numeric loopback or a separately enabled sandbox.

No credential discovery or executable loader. A host-prepared in-memory token
travels through a private pipe. Admission and HTTP share one absolute deadline.
"""
import re
import math
import time
from urllib.parse import parse_qs, urlsplit
from .bigquery_snapshot import BigQueryConfig, CAPS, query_config, fail
from .upgrade_transport import owned_exchange
from .upgrade_budget import UpgradeError

REMOTE = "https://bigquery.googleapis.com/bigquery/v2"


class PreparedToken:
    """Inert secret value prepared by the authorized host before import.

    Exact types prevent executable getters/subclasses at the transport boundary.
    This is not a credential loader, authorization permit or identity proof.
    """
    __slots__ = ("_value",)

    def __init__(self, value):
        if type(value) is not str or not value or len(value) > 8192 or any(c.isspace() for c in value):
            fail("INVALID_RUNTIME_TOKEN")
        object.__setattr__(self, "_value", value)

    def __setattr__(self, name, value):
        raise AttributeError("PreparedToken is immutable")

    def __repr__(self):
        return "PreparedToken([REDACTED])"


def validate_origin(origin, sandbox_enabled):
    if origin == REMOTE and sandbox_enabled is True:
        return "sandbox_live"
    parsed = urlsplit(origin)
    try:
        port = parsed.port
    except ValueError:
        fail("INVALID_ORIGIN")
    if (parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "::1") or
            not port or parsed.username or parsed.password or parsed.path != "/bigquery/v2" or
            parsed.query or parsed.fragment):
        fail("EXTERNAL_TRANSPORT_DISABLED")
    return "local_double"


def validate_request(config, method, path, body):
    parsed = urlsplit(path)
    if parsed.scheme or parsed.netloc or parsed.fragment or not path.startswith("/"):
        fail("INVALID_RESOURCE_PATH")
    prefix = "/projects/" + config.project
    views = {prefix + "/datasets/" + config.dataset + "/tables/" + v for _, v in config.views}
    params = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
    if any(len(v) != 1 for v in params.values()):
        fail("INVALID_RESOURCE_PATH")
    if parsed.path in views and method == "GET" and not params and body is None:
        return
    if parsed.path == prefix + "/jobs" and method == "POST" and not params:
        if type(body) is not dict or set(body) != {"jobReference", "configuration"}:
            fail("INVALID_REQUEST_BODY")
        reference, configuration = body["jobReference"], body["configuration"]
        if type(reference) is not dict or type(configuration) is not dict:
            fail("INVALID_REQUEST_BODY")
        dry = configuration.get("dryRun") is True
        if (configuration.get("query") != query_config(config) or
                set(configuration) != ({"query", "dryRun"} if dry else {"query", "jobTimeoutMs"}) or
                (not dry and configuration["jobTimeoutMs"] != "50000") or
                reference.get("projectId") != config.project or reference.get("location") != config.location or
                set(reference) != ({"projectId", "location"} if dry else {"projectId", "location", "jobId"}) or
                (not dry and (type(reference["jobId"]) is not str or
                              not re.fullmatch(r"ga_[0-9a-f]{32}", reference["jobId"])) )):
            fail("INVALID_REQUEST_BODY")
        return
    job = re.fullmatch(re.escape(prefix) + r"/(jobs|queries)/(ga_[0-9a-f]{32})(/cancel)?", parsed.path)
    if not job or params.get("location") != [config.location] or body is not None:
        fail("INVALID_RESOURCE_PATH")
    if job[1] == "jobs" and set(params) == {"location"}:
        if method == ("POST" if job[3] else "GET"):
            return
    if (job[1] == "queries" and job[3] is None and method == "GET" and
            set(params) in ({"location", "maxResults", "timeoutMs"}, {"location", "maxResults", "timeoutMs", "pageToken"}) and
            params["maxResults"] == ["500"] and params["timeoutMs"] == ["0"] and
            len(params.get("pageToken", [""])[0].encode()) <= 2048):
        return
    fail("INVALID_RESOURCE_PATH")


class BigQueryTransport:
    def __init__(self, config, *, origin=REMOTE, sandbox_enabled=False, prepared_token=None, token_loader=None):
        # Keep the obsolete keyword only to fail closed for existing callers.
        # Never call or introspect a supplied loader, including callable objects.
        if token_loader is not None:
            fail("DYNAMIC_TOKEN_LOADER_FORBIDDEN")
        if not isinstance(config, BigQueryConfig):
            fail("INVALID_HOST_CONFIG")
        self.mode = validate_origin(origin, sandbox_enabled)
        if self.mode == "sandbox_live" and type(prepared_token) is not PreparedToken:
            fail("PREPARED_TOKEN_REQUIRED")
        if self.mode == "local_double" and prepared_token is not None:
            fail("TOKEN_FORBIDDEN_IN_DOUBLE")
        self.config, self.origin = config, origin
        self.sandbox_enabled, self.prepared_token = sandbox_enabled, prepared_token

    def __call__(self, method, path, body, *, timeout, cancel_event=None):
        started = time.monotonic()
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
            raise UpgradeError("TRANSPORT_TIMEOUT", {"child_pid": None, "child_reaped": True,
                                                     "remote_outcome_unknown": False})
        deadline = started + min(8, timeout)

        def remaining(owned=None):
            receipt = {"child_pid": None, "child_reaped": True, "remote_outcome_unknown": False,
                       "duration_ms": round((time.monotonic() - started) * 1000, 3)}
            if owned is not None:
                receipt.update({k: owned[k] for k in ("child_pid", "child_reaped", "remote_outcome_unknown") if k in owned})
            if cancel_event is not None and cancel_event.is_set():
                raise UpgradeError("CANCELLED", receipt)
            left = deadline - time.monotonic()
            if left <= 0:
                raise UpgradeError("TRANSPORT_TIMEOUT", receipt)
            return left

        remaining()
        validate_request(self.config, method, path, body)
        # No I/O or callable seam here. Only the exact inert type admitted above.
        token = None
        if self.mode == "sandbox_live":
            if type(self.prepared_token) is not PreparedToken:
                fail("PREPARED_TOKEN_REQUIRED")
            token = self.prepared_token._value
        payload = {
            "config": {**self.config.__dict__}, "origin": self.origin,
            "sandbox_enabled": self.sandbox_enabled, "token": token, "method": method,
            "path": path, "body": body}
        left = remaining()
        payload["timeout"] = left
        result = owned_exchange("governed_analytics.bigquery_http_worker", payload, timeout=left,
            absolute_deadline=deadline, cancel_event=cancel_event, max_output=CAPS["response_bytes"] * 3)
        remaining(result)
        if result.get("error"):
            fail(result["error"])
        return result
