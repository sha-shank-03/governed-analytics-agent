"""Private pipe input, fixed loopback, no proxy/redirect, capped body; parent owns time."""
import json
import sys
import urllib.error
import urllib.request
from .upgrade_gateway import GatewayConfig


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def main():
    result = {"error": "TRANSPORT_FAILED"}
    try:
        # JSON-in-JSON pipe escaping may double the admitted 64 KiB request.
        raw = sys.stdin.buffer.read(140001)
        if len(raw) > 140000:
            raise ValueError()
        request = json.loads(raw)
        GatewayConfig(request["endpoint"], "local/synthetic-tool-model")
        body = request["body"].encode("utf-8")
        if len(body) > 65536:
            raise ValueError()
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        call = urllib.request.Request(request["endpoint"], data=body,
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            response = opener.open(call, timeout=max(0.001, min(15, request["timeout"])))
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            payload = response.read(262145)
            if len(payload) > 262144:
                result = {"error": "RESPONSE_TOO_LARGE"}
            else:
                retry = response.headers.get("Retry-After", "")
                result = {"http_status": response.code, "body": payload.decode("utf-8"),
                          "response_bytes": len(payload),
                          "retry_after_seconds": int(retry) if retry.isdigit() and len(retry) <= 6 else None}
    except Exception:
        # No raw exception, URL, headers, response body or pipe payload on stderr.
        pass
    sys.stdout.write(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
