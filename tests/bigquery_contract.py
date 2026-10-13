"""Authored protocol double, not a warehouse, evaluation corpus or hidden oracle."""
import copy
import json
from governed_analytics.bigquery_snapshot import (BigQueryConfig, OUTPUT_SCHEMA, RELATIONS,
    source_schema, view_definition_hash)
from governed_analytics.data import digest, tables_for_schema


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def config(version="sales_v1"):
    # These IDs and principal are fictional; no resource existence is asserted.
    return BigQueryConfig("fictional-ga-test", "ga_sandbox_north_views", "US",
        "north-test@example.invalid", tuple((r, r + "_north_v1") for r in RELATIONS),
        tuple((r, view_definition_hash("SELECT reviewed " + r)) for r in RELATIONS),
        "existing-contract-double-v1", "2026-03-01", version)


def schema(fields):
    return {"fields": [{"name": name, "type": kind, "mode": "NULLABLE"} for name, kind in fields]}


class ContractAPI:
    def __init__(self, configured=None, *, hook=None, page_size=500):
        self.config = configured or config()
        self.hook, self.page_size = hook, page_size
        self.calls, self.saved = [], []
        self.job_id, self.body = None, None
        # Minimal protocol rows; no task scoring or model output labels.
        self.data = {"schema_version": self.config.schema_version, "as_of": self.config.as_of,
            "currency": "USD", "fulfillment_events": [],
            "orders": [["O1", "2026-01-02", "North", "direct", "completed"],
                       ["O2", "2026-02-02", "North", "direct", "completed"]],
            "order_lines": [["L1", "O1", 1, 1000, 100], ["L2", "O2", 1, 800, 100]],
            "refunds": [["R1", "O1", "2026-02-03", 50, "posted"]],
            "period_coverage": [["2026-01", "North", 1], ["2026-02", "North", 1]]}

    def persist(self, state):
        self.saved.append(copy.deepcopy(state))

    def job(self, state="DONE"):
        return {"jobReference": {"projectId": self.config.project, "location": self.config.location, "jobId": self.job_id},
                "configuration": copy.deepcopy(self.body["configuration"]),
                "status": {"state": state}, "user_email": self.config.principal,
                "etag": "job-version-1", "statistics": {"totalBytesProcessed": "100",
                    "creationTime": "1", "startTime": "2", "endTime": "3",
                    "query": {"totalBytesProcessed": "100", "totalBytesBilled": "41943040",
                              "cacheHit": False, "statementType": "SELECT"}}}

    def rows(self):
        result = []
        for relation in RELATIONS:
            columns = tables_for_schema(self.config.schema_version)[relation]
            for row in self.data[relation]:
                payload = dict(zip(columns, row))
                if relation == "period_coverage":
                    payload["complete"] = bool(payload["complete"])
                payload["currency"] = "USD"
                result.append({"f": [{"v": relation}, {"v": json.dumps(payload)}]})
        return result

    def __call__(self, method, path, body, **kwargs):
        self.calls.append((method, path, copy.deepcopy(body), kwargs))
        if "/tables/" in path:
            view = path.rsplit("/", 1)[1]
            relation = next(r for r, v in self.config.views if v == view)
            result = {"type": "VIEW", "location": self.config.location, "etag": "view-version-1",
                "lastModifiedTime": "1", "view": {"query": "SELECT reviewed " + relation, "useLegacySql": False},
                "tableReference": {"projectId": self.config.project, "datasetId": self.config.dataset, "tableId": view},
                "schema": schema(source_schema(self.config, relation))}
        elif method == "POST" and path.endswith("/jobs"):
            if body["configuration"].get("dryRun"):
                result = {"statistics": {"totalBytesProcessed": "100"}}
            else:
                if not self.saved or not self.saved[-1]["owned_job_admitted"] or self.saved[-1]["job_id"] != body["jobReference"]["jobId"]:
                    raise AssertionError("Job ID was not persisted before transmission")
                self.job_id, self.body = body["jobReference"]["jobId"], copy.deepcopy(body)
                result = self.job("RUNNING")
        elif "/queries/" in path:
            from urllib.parse import parse_qs, urlsplit
            index = int(parse_qs(urlsplit(path).query).get("pageToken", ["0"])[0])
            all_rows = self.rows()
            result = {"jobComplete": True, "jobReference": self.job()["jobReference"],
                "schema": schema(OUTPUT_SCHEMA), "etag": "page-" + str(index),
                "totalRows": str(len(all_rows)), "rows": all_rows[index:index + self.page_size]}
            if index + self.page_size < len(all_rows):
                result["pageToken"] = str(index + self.page_size)
        elif "/cancel?" in path:
            result = {"job": self.job()}
        else:
            result = self.job()
        response = {"http_status": 200, "body": json.dumps(result)}
        return self.hook(self, method, path, body, result, response) if self.hook else response
