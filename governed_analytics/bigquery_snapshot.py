"""Host-owned, bounded BigQuery SELECT import. No model-facing remote SQL tool.

Transport and durable checkpoint writer are injected. Construction performs no
network, credential discovery, account mutation, or dependency loading.
"""
import hashlib
import json
import re
import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from .data import digest, tables_for_schema
from .upgrade_budget import UpgradeError
from .upgrade_gateway import strict_json

RELATIONS = ("orders", "order_lines", "refunds", "period_coverage")
CAPS = {"seconds": 60, "requests": 20, "pages": 10, "rows": 5000,
        "response_bytes": 262144, "total_bytes": 2097152, "maximum_bytes_billed": 67108864}
OUTPUT_SCHEMA = [("relation", "STRING"), ("payload", "STRING")]


def view_definition_hash(sql):
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def fail(code):
    raise UpgradeError("BQ_" + code)


def bounded_text(value, maximum=256):
    if type(value) is not str or not value or len(value.encode("utf-8")) > maximum:
        fail("INVALID_TEXT")
    return value


def uint(value, maximum=2**63-1):
    if type(value) is not str or not re.fullmatch(r"0|[1-9][0-9]{0,18}", value):
        fail("INVALID_INTEGER")
    number = int(value)
    if number > maximum:
        fail("INTEGER_LIMIT")
    return number


@dataclass(frozen=True)
class BigQueryConfig:
    project: str
    dataset: str
    location: str
    principal: str
    views: tuple
    view_sql_hashes: tuple
    source_version: str
    as_of: str
    schema_version: str = "sales_v1"

    def __post_init__(self):
        if any(type(v) is not str for v in (self.project, self.dataset, self.location, self.principal,
                                           self.source_version, self.as_of, self.schema_version)):
            fail("INVALID_HOST_CONFIG")
        if not re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", self.project):
            fail("INVALID_PROJECT")
        if self.dataset != "ga_sandbox_north_views":
            fail("INVALID_DATASET")
        if not re.fullmatch(r"US|EU|[a-z]+-[a-z]+[0-9]", self.location):
            fail("INVALID_LOCATION")
        if not re.fullmatch(r"[A-Za-z0-9._+%-]+@[A-Za-z0-9.-]+", self.principal):
            fail("INVALID_PRINCIPAL")
        if type(self.views) is not tuple or type(self.view_sql_hashes) is not tuple:
            fail("INVALID_VIEW_BINDING")
        try:
            views, hashes = dict(self.views), dict(self.view_sql_hashes)
        except (ValueError, TypeError):
            fail("INVALID_VIEW_BINDING")
        if (len(self.views) != 4 or len(self.view_sql_hashes) != 4 or
                set(views) != set(RELATIONS) or set(hashes) != set(RELATIONS) or
                len(set(views.values())) != 4 or any(type(v) is not str or not
                re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", v) for v in views.values()) or
                any(type(h) is not str or not re.fullmatch(r"[0-9a-f]{64}", h) for h in hashes.values())):
            fail("INVALID_VIEW_BINDING")
        if self.schema_version not in ("sales_v1", "sales_v2"):
            fail("SCHEMA_UNSUPPORTED")
        bounded_text(self.source_version, 128)
        try:
            if type(self.as_of) is not str or date.fromisoformat(self.as_of).isoformat() != self.as_of:
                fail("INVALID_CUTOFF")
        except (ValueError, TypeError):
            fail("INVALID_CUTOFF")

    def portable(self):
        return {"project": self.project, "dataset": self.dataset, "location": self.location,
                "principal_hash": digest(self.principal.lower()), "views": dict(self.views),
                "view_sql_hashes": dict(self.view_sql_hashes), "source_version": self.source_version,
                "as_of": self.as_of, "schema_version": self.schema_version,
                "regions": ["North"], "currency": "USD"}


def source_schema(config, relation):
    columns = tables_for_schema(config.schema_version)[relation]
    integers = {"quantity", "unit_price_cents", "unit_amount_cents", "discount_cents", "amount_cents"}
    return [(c, "INTEGER" if c in integers else "DATE" if c in ("order_date", "posted_date")
             else "BOOLEAN" if c == "complete" else "STRING") for c in columns] + [("currency", "STRING")]


def check_schema(value, expected):
    if type(value) is not dict or set(value) != {"fields"} or type(value["fields"]) is not list:
        fail("SCHEMA_DRIFT")
    fields = value["fields"]
    if len(fields) != len(expected):
        fail("SCHEMA_DRIFT")
    for field, (name, kind) in zip(fields, expected):
        if (type(field) is not dict or field.get("name") != name or field.get("type") != kind or
                field.get("mode", "NULLABLE") not in ("NULLABLE", "REQUIRED") or
                set(field) - {"name", "type", "mode", "description"}):
            fail("SCHEMA_DRIFT")


def fixed_query(config):
    """Only reviewed identifiers interpolate; all source values are parameters."""
    names = {r: f"`{config.project}.{config.dataset}.{v}`" for r, v in config.views}
    pieces = []
    for relation in RELATIONS:
        columns = tables_for_schema(config.schema_version)[relation] + ("currency",)
        projection = ", ".join("v." + c + " AS " + c for c in columns)
        source = names[relation] + " AS v"
        if relation in ("order_lines", "refunds"):
            source += " JOIN " + names["orders"] + " AS o ON v.order_id = o.order_id"
            predicate = "o.region = @region AND o.order_date < @as_of"
            if relation == "refunds":
                predicate += " AND v.posted_date < @as_of"
        elif relation == "orders":
            predicate = "v.region = @region AND v.order_date < @as_of"
        else:
            predicate = "v.region = @region AND v.period_key < FORMAT_DATE('%Y-%m', @as_of)"
        pieces.append(f"SELECT '{relation}' AS relation, TO_JSON_STRING(STRUCT({projection})) AS payload "
                      f"FROM {source} WHERE {predicate}")
    return "\nUNION ALL\n".join(pieces) + "\nORDER BY relation, payload"


def query_config(config):
    return {"query": fixed_query(config), "useLegacySql": False, "useQueryCache": False,
            "maximumBytesBilled": str(CAPS["maximum_bytes_billed"]), "parameterMode": "NAMED",
            "queryParameters": [{"name": "region", "parameterType": {"type": "STRING"},
                                 "parameterValue": {"value": "North"}},
                                {"name": "as_of", "parameterType": {"type": "DATE"},
                                 "parameterValue": {"value": config.as_of}}]}


def validate_data(data):
    if (type(data) is not dict or set(data) != {"schema_version", "as_of", "currency", *RELATIONS,
            "fulfillment_events"} or data["schema_version"] not in ("sales_v1", "sales_v2") or
            data["currency"] != "USD" or data["fulfillment_events"] != []):
        fail("INVALID_SNAPSHOT")
    try:
        if date.fromisoformat(data["as_of"]).isoformat() != data["as_of"]:
            fail("INVALID_CUTOFF")
    except (ValueError, TypeError):
        fail("INVALID_CUTOFF")
    total, keys = 0, {}
    integers = {"quantity", "unit_price_cents", "unit_amount_cents", "discount_cents", "amount_cents", "complete"}
    for relation in RELATIONS:
        rows = data[relation]
        if type(rows) is not list:
            fail("INVALID_ROWS")
        total += len(rows)
        seen = set()
        columns = tables_for_schema(data["schema_version"])[relation]
        for row in rows:
            if type(row) is not list or len(row) != len(columns):
                fail("INVALID_ROW")
            for column, value in zip(columns, row):
                if column in integers:
                    if type(value) is not int or not 0 <= value <= 10**9:
                        fail("INVALID_AMOUNT")
                else:
                    bounded_text(value)
                    if column in ("order_date", "posted_date"):
                        try:
                            if date.fromisoformat(value).isoformat() != value or value >= data["as_of"]:
                                fail("INVALID_DATE")
                        except ValueError:
                            fail("INVALID_DATE")
            key = tuple(row[:2]) if relation == "period_coverage" else row[0]
            if key in seen:
                fail("DUPLICATE_KEY")
            seen.add(key)
            if relation == "orders" and (row[2] != "North" or row[3] not in ("direct", "partner") or
                                         row[4] not in ("completed", "cancelled", "pending")):
                fail("SCOPE_OR_ENUM")
            if relation == "order_lines" and (row[2] == 0 or row[4] > row[2] * row[3]):
                fail("INVALID_LINE")
            if relation == "refunds" and row[4] not in ("posted", "pending", "void"):
                fail("INVALID_REFUND")
            if relation == "period_coverage" and (row[1] != "North" or row[2] not in (0, 1) or
                    not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", row[0])):
                fail("INVALID_COVERAGE")
            if relation == "period_coverage":
                try:
                    period = date.fromisoformat(row[0] + "-01")
                    next_month = date(period.year + (period.month == 12), period.month % 12 + 1, 1)
                    if next_month.isoformat() > data["as_of"]:
                        fail("INVALID_COVERAGE")
                except ValueError:
                    fail("INVALID_COVERAGE")
        keys[relation] = seen
    if total > CAPS["rows"] or len(json.dumps(data).encode()) > CAPS["total_bytes"]:
        fail("SNAPSHOT_LIMIT")
    if any(r[1] not in keys["orders"] for t in ("order_lines", "refunds") for r in data[t]):
        fail("FOREIGN_KEY")
    if sum(r[2] * r[3] for r in data["order_lines"]) > 2**63 - 1:
        fail("AGGREGATE_INTEGER_LIMIT")
    coverage = {(r[0], r[1]) for r in data["period_coverage"]}
    if any((r[1][:7], r[2]) not in coverage for r in data["orders"]):
        fail("MISSING_COVERAGE")
    return data


@dataclass(frozen=True)
class ValidatedSnapshot:
    data_json: str
    provenance_json: str

    def payload(self):
        data, provenance = strict_json(self.data_json), strict_json(self.provenance_json)
        validate_data(data)
        if (type(provenance) is not dict or provenance.get("version") != "bq-snapshot-v1" or
                provenance.get("rows_hash") != digest(data) or provenance.get("job_state") != "DONE" or
                provenance.get("principal_verified") is not True or
                provenance.get("metadata_before") != provenance.get("metadata_after")):
            fail("INVALID_PROVENANCE")
        source = provenance.get("trusted_source", {})
        reference = provenance.get("job_reference", {})
        if (type(source) is not dict or set(source) != {"project", "dataset", "location", "principal_hash",
                "views", "view_sql_hashes", "source_version", "as_of", "schema_version", "regions", "currency"} or
                source.get("regions") != ["North"] or source.get("currency") != "USD" or
                source.get("as_of") != data["as_of"] or source.get("schema_version") != data["schema_version"] or
                provenance.get("config_hash") != digest(source) or type(reference) is not dict or
                set(reference) != {"projectId", "location", "jobId"} or
                reference.get("projectId") != source["project"] or reference.get("location") != source["location"] or
                type(reference.get("jobId")) is not str or not re.fullmatch(r"ga_[0-9a-f]{32}", reference["jobId"]) or
                provenance.get("row_count") != sum(len(data[r]) for r in RELATIONS) or
                provenance.get("mode") not in ("injected_contract", "local_double", "sandbox_live") or
                provenance.get("omitted_relations") != ["fulfillment_events"]):
            fail("INVALID_PROVENANCE")
        before = provenance["metadata_before"]
        if type(before) is not dict or set(before) != set(RELATIONS):
            fail("INVALID_PROVENANCE")
        return {"data": data, "provenance": provenance}

    def binding(self):
        return digest(self.payload())


class SnapshotImporter:
    def __init__(self, config, exchange, persist, *, clock=time.monotonic, sleep=time.sleep,
                 cancel_event=None):
        if not isinstance(config, BigQueryConfig) or not callable(exchange) or not callable(persist):
            fail("INVALID_HOST_CONFIG")
        self.config, self.exchange, self.persist = config, exchange, persist
        self.clock, self.sleep, self.cancel_event = clock, sleep, cancel_event
        self.used, self.last_request, self.inflight = False, None, False
        self.state = {"version": "bq-import-v1", "mode": getattr(exchange, "mode", "injected_contract"), "job_id": "ga_" + uuid.uuid4().hex,
                      "config_hash": digest(config.portable()), "query_hash": digest(query_config(config)),
                      "requests": 0, "pages": 0, "response_bytes": 0, "receipts": [],
                      "owned_job_admitted": False, "remote_outcome_unknown": False,
                      "ownership_verified": False,
                      "remote_state": "NOT_SUBMITTED", "snapshot_published": False}

    def save(self):
        try:
            self.persist(json.loads(json.dumps(self.state)))
        except Exception:
            fail("CHECKPOINT_FAILED")

    def check(self, *, cleanup=False):
        if self.clock() >= (self.deadline if cleanup else self.work_deadline):
            fail("DEADLINE")
        if not cleanup and self.cancel_event is not None and self.cancel_event.is_set():
            fail("CANCELLED")

    def request(self, method, path, body=None, *, cleanup=False):
        self.check(cleanup=cleanup)
        if self.inflight:
            fail("CONCURRENT_REQUEST")
        # Two calls remain available for cancellation and a terminal-state read.
        if self.state["requests"] >= CAPS["requests"] - (0 if cleanup else 2):
            fail("REQUEST_LIMIT")
        if self.last_request is not None:
            delay = max(0, self.last_request + 1 - self.clock())
            if delay:
                if delay >= (self.deadline if cleanup else self.work_deadline) - self.clock():
                    fail("DEADLINE")
                if not cleanup and self.cancel_event is not None:
                    self.cancel_event.wait(delay)
                else:
                    self.sleep(delay)
        self.check(cleanup=cleanup)
        self.last_request = self.clock()
        self.state["requests"] += 1
        record = {"method": method, "path_hash": digest(path), "body_hash": digest(body),
                  "request_number": self.state["requests"]}
        self.state["receipts"].append(record)
        self.save()  # Admission precedes all transmissions, including dry run.
        self.inflight = True
        try:
            result = self.exchange(method, path, body, timeout=min(8, (self.deadline if cleanup else
                self.work_deadline) - self.clock()), cancel_event=None if cleanup else self.cancel_event)
            self.check(cleanup=cleanup)
            if type(result) is not dict or type(result.get("http_status")) is not int:
                fail("MALFORMED_HTTP")
            record["http_status"] = result["http_status"]
            for key in ("child_pid", "child_reaped", "duration_ms"):
                if key in result:
                    record[key] = result[key]
            raw = result.get("body")
            if type(raw) is not str:
                fail("MALFORMED_HTTP")
            size = len(raw.encode("utf-8"))
            self.state["response_bytes"] += size
            record["response_bytes"], record["response_hash"] = size, digest(raw)
            if size > CAPS["response_bytes"] or self.state["response_bytes"] > CAPS["total_bytes"]:
                fail("RESPONSE_LIMIT")
            status = result["http_status"]
            if status != 200:
                code = {401: "AUTH_DENIED", 403: "ACCESS_OR_QUOTA_DENIED", 404: "RESOURCE_UNAVAILABLE",
                        409: "JOB_CONFLICT", 429: "RATE_LIMIT"}.get(status, "HTTP_FAILURE")
                fail(code)  # No raw provider errors, headers or principal in receipts.
            value = strict_json(raw)
            if type(value) is not dict:
                fail("MALFORMED_RESPONSE")
            return value
        except UpgradeError as exc:
            record["error"] = exc.code
            for key in ("child_pid", "child_reaped", "duration_ms", "remote_outcome_unknown"):
                if key in exc.receipt:
                    record[key] = exc.receipt[key]
            raise
        except Exception:
            record["error"] = "BQ_TRANSPORT_AMBIGUOUS"
            fail("TRANSPORT_AMBIGUOUS")
        finally:
            self.inflight = False
            self.save()

    def job_path(self):
        return f"/projects/{self.config.project}/jobs/{self.state['job_id']}"

    def job_get(self, *, cleanup=False):
        return self.request("GET", self.job_path() + "?location=" + self.config.location, cleanup=cleanup)

    def inspect_job(self, job):
        expected = {"projectId": self.config.project, "jobId": self.state["job_id"], "location": self.config.location}
        if job.get("jobReference") != expected:
            fail("JOB_IDENTITY_CHANGED")
        config = job.get("configuration", {})
        actual = config.get("query", {})
        desired = query_config(self.config)
        # BigQuery may supply defaults and its anonymous result destination. A named
        # destination or any non-query configuration is never sent by this host.
        if (any(actual.get(k) != v for k, v in desired.items()) or config.get("dryRun", False) or
                any(k in config for k in ("load", "copy", "extract", "reservation"))):
            fail("JOB_CONFIG_CHANGED")
        destination = actual.get("destinationTable")
        if destination and (destination.get("projectId") != self.config.project or
                            not destination.get("datasetId", "").startswith("_")):
            fail("JOB_DESTINATION_CHANGED")
        user = job.get("user_email")
        if type(user) is not str or user.lower() != self.config.principal.lower():
            fail("PRINCIPAL_UNVERIFIED")
        self.state["ownership_verified"] = True
        status = job.get("status", {})
        state = status.get("state")
        if state not in ("PENDING", "RUNNING", "DONE"):
            fail("INVALID_JOB_STATE")
        self.state["remote_state"] = state
        self.state["remote_outcome_unknown"] = state != "DONE"
        self.save()
        if status.get("errorResult") or status.get("errors"):
            fail("JOB_ERRORS")  # Conservative: warnings are held for host review too.
        return state

    def metadata(self):
        result = {}
        for relation, view in self.config.views:
            item = self.request("GET", f"/projects/{self.config.project}/datasets/{self.config.dataset}/tables/{view}")
            expected = {"projectId": self.config.project, "datasetId": self.config.dataset, "tableId": view}
            if item.get("tableReference") != expected or item.get("type") != "VIEW" or item.get("location") != self.config.location:
                fail("VIEW_IDENTITY_CHANGED")
            check_schema(item.get("schema"), source_schema(self.config, relation))
            definition = item.get("view", {})
            sql_hash = view_definition_hash(bounded_text(definition.get("query"), 65536))
            if definition.get("useLegacySql", True) or sql_hash != dict(self.config.view_sql_hashes)[relation]:
                fail("VIEW_DEFINITION_CHANGED")
            etag = bounded_text(item.get("etag"), 1024)
            modified = uint(item.get("lastModifiedTime"))
            expiration = item.get("expirationTime")
            if expiration is not None:
                if uint(expiration) <= int(datetime.now(timezone.utc).timestamp() * 1000):
                    fail("VIEW_EXPIRED")
            result[relation] = {"reference": expected, "etag": etag, "modified_ms": modified,
                                "expiration_ms": expiration, "schema_hash": digest(item["schema"]),
                                "view_sql_hash": sql_hash, "location": item["location"]}
        return result

    def cancel_owned(self):
        if not self.state["owned_job_admitted"] or self.state["remote_state"] == "DONE":
            return
        if not self.state["ownership_verified"]:
            self.state["cancellation"] = {"requested": False, "terminal_observed": False,
                                          "error": "BQ_OWNERSHIP_UNVERIFIED"}
            self.save()
            return
        self.state["remote_outcome_unknown"] = True
        try:
            self.request("POST", self.job_path() + "/cancel?location=" + self.config.location, cleanup=True)
            # The response is advisory; only an independent job read settles state.
            job = self.job_get(cleanup=True)
            try:
                self.inspect_job(job)
            except UpgradeError as exc:
                if exc.code != "BQ_JOB_ERRORS":
                    raise
            self.state["cancellation"] = {"requested": True, "terminal_observed": self.state["remote_state"] == "DONE"}
        except UpgradeError as exc:
            self.state["cancellation"] = {"requested": True, "terminal_observed": False, "error": exc.code}
        self.save()

    def run(self):
        if self.used:
            fail("IMPORT_NOT_REUSABLE")
        self.used = True
        self.started = self.clock()
        self.deadline, self.work_deadline = self.started + CAPS["seconds"], self.started + CAPS["seconds"] - 3
        try:
            before = self.metadata()
            query = query_config(self.config)
            dry = self.request("POST", f"/projects/{self.config.project}/jobs",
                {"jobReference": {"projectId": self.config.project, "location": self.config.location},
                 "configuration": {"dryRun": True, "query": query}})
            if dry.get("status", {}).get("errorResult") or dry.get("status", {}).get("errors"):
                fail("DRY_RUN_FAILED")
            statistics = dry.get("statistics", {})
            estimated = uint(statistics.get("totalBytesProcessed"), CAPS["maximum_bytes_billed"])
            # Conservatively allow 10 MiB per export relation for documented
            # 10 MB minimums. Underlying views may read more tables; the server
            # cap remains authoritative and is never raised by an estimate.
            if max(estimated, len(RELATIONS) * 10485760) > CAPS["maximum_bytes_billed"]:
                fail("ESTIMATE_LIMIT")
            self.state.update(owned_job_admitted=True, remote_outcome_unknown=True, remote_state="SUBMISSION_UNKNOWN")
            body = {"jobReference": {"projectId": self.config.project, "location": self.config.location,
                                      "jobId": self.state["job_id"]},
                    "configuration": {"query": query, "jobTimeoutMs": "50000"}}
            self.state["submitted_body_hash"] = digest(body)
            self.save()  # Owned ID and exact config durable BEFORE insert.
            try:
                inserted = self.request("POST", f"/projects/{self.config.project}/jobs", body)
                self.inspect_job(inserted)
            except UpgradeError as exc:
                if exc.code not in ("BQ_JOB_CONFLICT", "BQ_TRANSPORT_AMBIGUOUS", "TRANSPORT_TIMEOUT",
                                    "BQ_TRANSPORT_FAILED", "HELPER_FAILED", "BQ_HTTP_FAILURE"):
                    raise
                self.state["submission_reconciled"] = True
                self.save()
            # Even a successful insert is reconciled by owned ID; never trust a
            # returned resource path or create a replacement job on ambiguity.
            while True:
                job = self.job_get()
                if self.inspect_job(job) == "DONE":
                    break
            data = {"schema_version": self.config.schema_version, "as_of": self.config.as_of,
                    "currency": "USD", **{r: [] for r in RELATIONS}, "fulfillment_events": []}
            token, tokens, total, received, page_receipts = None, set(), None, 0, []
            from urllib.parse import urlencode
            while True:
                if self.state["pages"] >= CAPS["pages"]:
                    fail("PAGE_LIMIT")
                params = {"location": self.config.location, "maxResults": 500, "timeoutMs": 0}
                if token:
                    params["pageToken"] = token
                page = self.request("GET", self.job_path().replace("/jobs/", "/queries/") + "?" + urlencode(params))
                self.state["pages"] += 1
                if page.get("jobComplete") is not True or page.get("errors"):
                    fail("INCOMPLETE_RESULTS")
                if page.get("jobReference") != body["jobReference"]:
                    fail("JOB_IDENTITY_CHANGED")
                check_schema(page.get("schema"), OUTPUT_SCHEMA)
                count = uint(page.get("totalRows"), CAPS["rows"])
                if total is not None and count != total:
                    fail("RESULT_COUNT_CHANGED")
                total = count
                rows = page.get("rows", [])
                if type(rows) is not list or len(rows) > 500:
                    fail("INVALID_ROWS")
                received += len(rows)
                if received > total:
                    fail("RESULT_COUNT_CHANGED")
                for row in rows:
                    if type(row) is not dict or set(row) != {"f"} or type(row["f"]) is not list or len(row["f"]) != 2:
                        fail("INVALID_ROW")
                    if any(type(cell) is not dict or set(cell) != {"v"} or type(cell["v"]) is not str for cell in row["f"]):
                        fail("INVALID_ROW")
                    relation, raw = [c["v"] for c in row["f"]]
                    if relation not in RELATIONS or len(raw.encode()) > 8192:
                        fail("INVALID_RELATION")
                    payload = strict_json(raw)
                    columns = tables_for_schema(self.config.schema_version)[relation]
                    if type(payload) is not dict or set(payload) != {*columns, "currency"} or payload["currency"] != "USD":
                        fail("ROW_SCHEMA_OR_CURRENCY")
                    values = [payload[c] for c in columns]
                    if relation == "period_coverage":
                        if type(values[2]) is not bool:
                            fail("INVALID_COVERAGE")
                        values[2] = int(values[2])
                    data[relation].append(values)
                page_receipts.append({"etag": bounded_text(page.get("etag"), 1024), "rows": len(rows),
                                      "response_hash": self.state["receipts"][-1]["response_hash"]})
                token = page.get("pageToken")
                if token in (None, ""):
                    if received != total:
                        fail("TRUNCATED_RESULTS")
                    break
                bounded_text(token, 2048)
                if token in tokens or not rows or received >= total:
                    fail("PAGE_LOOP_OR_DUPLICATE")
                tokens.add(token)
            validate_data(data)
            after = self.metadata()
            if before != after:
                fail("METADATA_DRIFT")
            self.check()
            qstats = job.get("statistics", {}).get("query", {})
            if qstats.get("statementType") != "SELECT" or qstats.get("cacheHit") is not False:
                fail("UNEXPECTED_JOB_STATISTICS")
            billed = qstats.get("totalBytesBilled")
            if billed is not None:
                uint(billed, CAPS["maximum_bytes_billed"])
            provenance = {"version": "bq-snapshot-v1", "mode": self.state["mode"],
                "trusted_source": self.config.portable(), "config_hash": self.state["config_hash"],
                "query_hash": self.state["query_hash"], "job_reference": body["jobReference"],
                "job_state": "DONE", "job_etag": bounded_text(job.get("etag"), 1024),
                "principal_verified": True, "metadata_before": before, "metadata_after": after,
                "rows_hash": digest(data), "row_count": received, "page_receipts": page_receipts,
                "exported_at": datetime.now(timezone.utc).isoformat(), "dry_run_bytes": estimated,
                "job_statistics": {k: job.get("statistics", {}).get(k) for k in ("creationTime", "startTime", "endTime", "totalBytesProcessed")},
                "query_statistics": {k: qstats.get(k) for k in ("totalBytesProcessed", "totalBytesBilled", "cacheHit", "statementType")},
                "omitted_relations": ["fulfillment_events"], "actual_cost": None,
                "source_immutability": "main-owned seed declaration; metadata does not prove base-row immutability"}
            snapshot = ValidatedSnapshot(json.dumps(data), json.dumps(provenance))
            snapshot.payload()
            self.state.update(snapshot_published=True, snapshot_binding=snapshot.binding(), status="completed")
            self.save()
            self.check()
            return snapshot
        except UpgradeError as exc:
            self.state.update(status="failed", error=exc.code, snapshot_published=False)
            self.cancel_owned()
            self.save()
            raise UpgradeError(exc.code, {"job_id": self.state["job_id"],
                "remote_outcome_unknown": self.state["remote_outcome_unknown"], "requests": self.state["requests"]}) from None
        except KeyboardInterrupt:
            self.state.update(status="failed", error="BQ_CANCELLED", snapshot_published=False)
            self.cancel_owned()
            self.save()
            fail("CANCELLED")
        except Exception:
            self.state.update(status="failed", error="BQ_HOST_FAILURE", snapshot_published=False)
            self.cancel_owned()
            self.save()
            fail("HOST_FAILURE")
