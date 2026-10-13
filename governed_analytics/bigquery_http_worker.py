"""Private bounded HTTP helper. No proxy, redirect, ambient auth or raw errors."""
import json
import sys
import urllib.error
import urllib.request
from .bigquery_snapshot import BigQueryConfig, CAPS
from .bigquery_transport import validate_origin, validate_request
from .upgrade_http_worker import NoRedirect


def main():
    result = {"error": "TRANSPORT_FAILED"}
    try:
        raw = sys.stdin.buffer.read(140001)
        if len(raw) > 140000:
            raise ValueError()
        value = json.loads(raw)
        config = value["config"]
        config["views"] = tuple(tuple(v) for v in config["views"])
        config["view_sql_hashes"] = tuple(tuple(v) for v in config["view_sql_hashes"])
        config = BigQueryConfig(**config)
        mode = validate_origin(value["origin"], value["sandbox_enabled"])
        validate_request(config, value["method"], value["path"], value["body"])
        headers = {"Content-Type": "application/json"}
        token = value["token"]
        if mode == "sandbox_live":
            if type(token) is not str or not token or len(token) > 8192 or any(c.isspace() for c in token):
                raise ValueError()
            headers["Authorization"] = "Bearer " + token
        elif token is not None:
            raise ValueError()
        payload = None if value["body"] is None else json.dumps(value["body"]).encode()
        if payload is not None and len(payload) > 65536:
            raise ValueError()
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        request = urllib.request.Request(value["origin"] + value["path"], data=payload,
                                         headers=headers, method=value["method"])
        try:
            response = opener.open(request, timeout=max(0.001, min(8, value["timeout"])))
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            if response.code != 200:
                result = {"http_status": response.code, "body": ""}
            else:
                body = response.read(CAPS["response_bytes"] + 1)
                result = {"error": "RESPONSE_LIMIT"} if len(body) > CAPS["response_bytes"] else {
                    "http_status": response.code, "body": body.decode("utf-8")}
    except Exception:
        pass
    sys.stdout.write(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
