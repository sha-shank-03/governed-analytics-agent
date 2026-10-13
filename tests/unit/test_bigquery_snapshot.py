"""Pure injected protocol checks. No HTTP, child, SQLite, file write or credentials."""
import copy
import json
import unittest
from dataclasses import replace
from governed_analytics.bigquery_snapshot import (CAPS, SnapshotImporter, ValidatedSnapshot,
    fixed_query, query_config, validate_data)
from governed_analytics.bigquery_transport import BigQueryTransport, REMOTE, validate_request
from governed_analytics.data import digest
from governed_analytics.upgrade_budget import UpgradeError
from governed_analytics.upgrade_gateway import tool_schema
from tests.bigquery_contract import ContractAPI, Clock, config


class SnapshotTests(unittest.TestCase):
    def run_import(self, hook=None, *, configured=None, page_size=500):
        api = ContractAPI(configured, hook=hook, page_size=page_size)
        clock = Clock()
        importer = SnapshotImporter(api.config, api, api.persist, clock=clock, sleep=clock.sleep)
        self.api, self.clock, self.importer = api, clock, importer
        return importer.run()

    def assert_failure(self, hook, code):
        with self.assertRaises(UpgradeError) as caught:
            self.run_import(hook)
        self.assertEqual(caught.exception.code, code)
        self.assertFalse(self.importer.state["snapshot_published"])
        self.assertLessEqual(self.importer.state["requests"], CAPS["requests"])

    def test_fixed_query_and_bound_parameters_have_no_model_authority(self):
        value = config()
        query = query_config(value)
        self.assertEqual(query["parameterMode"], "NAMED")
        self.assertEqual(query["queryParameters"][0]["parameterValue"]["value"], "North")
        self.assertEqual(query["queryParameters"][1]["parameterType"]["type"], "DATE")
        self.assertEqual(query["maximumBytesBilled"], "67108864")
        self.assertFalse(query["useLegacySql"])
        self.assertNotIn("destinationTable", query)
        self.assertNotIn("SELECT *", fixed_query(value))
        self.assertEqual(fixed_query(value).count("UNION ALL"), 3)
        for field in ("dataset", "views", "principal", "location"):
            changes = {"dataset": "other", "views": (("orders", "a`; DELETE"),),
                       "principal": "Bearer invalid", "location": "US;SQL"}
            with self.subTest(field=field), self.assertRaises(UpgradeError):
                replace(value, **{field: changes[field]})

    def test_complete_pagination_validates_scope_and_provenance(self):
        snapshot = self.run_import(page_size=3)
        payload = snapshot.payload()
        self.assertEqual(payload["data"], self.api.data)
        self.assertEqual(payload["provenance"]["rows_hash"], digest(self.api.data))
        self.assertEqual(payload["provenance"]["row_count"], 7)
        self.assertEqual(payload["provenance"]["metadata_before"], payload["provenance"]["metadata_after"])
        self.assertEqual(self.importer.state["pages"], 3)
        self.assertFalse(self.importer.state["remote_outcome_unknown"])
        self.assertEqual(len([c for c in self.api.calls if c[0] == "POST" and c[2] and not c[2]["configuration"].get("dryRun")]), 1)
        self.assertEqual(self.clock.now, len(self.api.calls) - 1)
        self.assertTrue(all(c[3]["timeout"] <= 8 for c in self.api.calls))
        self.assertNotIn(self.api.config.principal, json.dumps(self.api.saved))
        self.assertNotIn(self.api.config.principal, snapshot.provenance_json)
        with self.assertRaises(UpgradeError):
            self.importer.run()

    def test_reviewed_schema_v2_mapping_is_explicit(self):
        snapshot = self.run_import(configured=config("sales_v2"))
        self.assertEqual(snapshot.payload()["data"]["schema_version"], "sales_v2")
        self.assertIn("v.unit_amount_cents", fixed_query(self.api.config))
        self.assertNotIn("v.unit_price_cents", fixed_query(self.api.config))

    def test_access_quota_expiration_fail_before_submission(self):
        for status, code in ((401, "BQ_AUTH_DENIED"), (403, "BQ_ACCESS_OR_QUOTA_DENIED"),
                             (404, "BQ_RESOURCE_UNAVAILABLE"), (429, "BQ_RATE_LIMIT"), (503, "BQ_HTTP_FAILURE")):
            with self.subTest(status=status):
                self.assert_failure(lambda *a: {"http_status": status, "body": "Bearer SECRET_CANARY"}, code)
                self.assertEqual(len(self.api.calls), 1)
                self.assertNotIn("SECRET_CANARY", json.dumps(self.api.saved))
        def expired(api, method, path, body, result, response):
            result["expirationTime"] = "1"
            return {"http_status": 200, "body": json.dumps(result)}
        self.assert_failure(expired, "BQ_VIEW_EXPIRED")

    def test_schema_extra_private_renamed_nested_and_wrong_type_are_denied(self):
        mutations = [lambda fields: fields.append({"name": "private_email", "type": "STRING"}),
                     lambda fields: fields[0].update(name="renamed"),
                     lambda fields: fields[0].update(type="RECORD", fields=[]),
                     lambda fields: fields[0].update(type="INTEGER")]
        for mutation in mutations:
            def hook(api, method, path, body, result, response):
                mutation(result["schema"]["fields"])
                return {"http_status": 200, "body": json.dumps(result)}
            with self.subTest(mutation=mutation):
                self.assert_failure(hook, "BQ_SCHEMA_DRIFT")

    def test_view_sql_and_metadata_drift_stop_without_snapshot(self):
        def sql(api, method, path, body, result, response):
            result["view"]["query"] += " altered"
            return {"http_status": 200, "body": json.dumps(result)}
        self.assert_failure(sql, "BQ_VIEW_DEFINITION_CHANGED")
        def etag(api, method, path, body, result, response):
            if "/tables/" in path and api.job_id:
                result["etag"] = "view-version-2"
            return {"http_status": 200, "body": json.dumps(result)}
        self.assert_failure(etag, "BQ_METADATA_DRIFT")
        self.assertFalse(any("/cancel?" in c[1] for c in self.api.calls))

    def test_estimate_and_reported_billing_cap_are_enforced(self):
        def estimate(api, method, path, body, result, response):
            if body and body["configuration"].get("dryRun"):
                result["statistics"]["totalBytesProcessed"] = "67108865"
            return {"http_status": 200, "body": json.dumps(result)}
        self.assert_failure(estimate, "BQ_INTEGER_LIMIT")
        self.assertFalse(self.importer.state["owned_job_admitted"])
        def billed(api, method, path, body, result, response):
            if method == "GET" and "/jobs/" in path:
                result["statistics"]["query"]["totalBytesBilled"] = "67108865"
            return {"http_status": 200, "body": json.dumps(result)}
        self.assert_failure(billed, "BQ_INTEGER_LIMIT")

    def test_lost_insert_response_and_conflict_reconcile_same_owned_id(self):
        for conflict in (False, True):
            def hook(api, method, path, body, result, response):
                if body and not body["configuration"].get("dryRun"):
                    if conflict:
                        return {"http_status": 409, "body": ""}
                    raise OSError("Bearer NEVER_LOG_THIS")
                return response
            with self.subTest(conflict=conflict):
                self.run_import(hook)
                self.assertTrue(self.importer.state["submission_reconciled"])
                posts = [c for c in self.api.calls if c[0] == "POST" and c[2] and not c[2]["configuration"].get("dryRun")]
                self.assertEqual(len(posts), 1)
                self.assertEqual(posts[0][2]["jobReference"]["jobId"], self.importer.state["job_id"])
                self.assertNotIn("NEVER_LOG_THIS", json.dumps(self.api.saved))

    def test_conflicting_job_principal_or_config_is_not_cancelled(self):
        for field in ("principal", "query", "location", "destination"):
            def hook(api, method, path, body, result, response):
                if body and not body["configuration"].get("dryRun"):
                    return {"http_status": 409, "body": ""}
                if "/jobs/" in path:
                    if field == "principal": result["user_email"] = "other@example.invalid"
                    if field == "query": result["configuration"]["query"]["query"] = "SELECT private"
                    if field == "location": result["jobReference"]["location"] = "EU"
                    if field == "destination": result["configuration"]["query"]["destinationTable"] = {"projectId": api.config.project, "datasetId": "private", "tableId": "x"}
                return {"http_status": 200, "body": json.dumps(result)}
            expected = {"principal": "BQ_PRINCIPAL_UNVERIFIED", "query": "BQ_JOB_CONFIG_CHANGED",
                        "location": "BQ_JOB_IDENTITY_CHANGED", "destination": "BQ_JOB_DESTINATION_CHANGED"}
            with self.subTest(field=field):
                self.assert_failure(hook, expected[field])
                self.assertFalse(any("/cancel?" in c[1] for c in self.api.calls))
                self.assertTrue(self.importer.state["remote_outcome_unknown"])

    def test_terminal_job_errors_and_incomplete_results_are_not_success(self):
        for warning in (False, True):
            def hook(api, method, path, body, result, response):
                if "/jobs/" in path:
                    result["status"]["errors" if warning else "errorResult"] = [{"message": "SECRET_CANARY"}] if warning else {"reason": "accessDenied", "message": "SECRET_CANARY"}
                return {"http_status": 200, "body": json.dumps(result)}
            with self.subTest(warning=warning):
                self.assert_failure(hook, "BQ_JOB_ERRORS")
                self.assertFalse(self.importer.state["remote_outcome_unknown"])
                self.assertNotIn("SECRET_CANARY", json.dumps(self.api.saved))
        def incomplete(api, method, path, body, result, response):
            if "/queries/" in path:
                result["jobComplete"] = False
            return {"http_status": 200, "body": json.dumps(result)}
        self.assert_failure(incomplete, "BQ_INCOMPLETE_RESULTS")

    def test_truncated_duplicate_empty_loop_and_changed_count_pages_fail(self):
        for fault, code in (("truncated", "BQ_TRUNCATED_RESULTS"), ("loop", "BQ_PAGE_LOOP_OR_DUPLICATE"),
                            ("empty", "BQ_PAGE_LOOP_OR_DUPLICATE"), ("count", "BQ_RESULT_COUNT_CHANGED")):
            def hook(api, method, path, body, result, response):
                if "/queries/" in path:
                    if fault == "truncated": result["rows"].pop()
                    if fault == "loop": result["pageToken"] = "0"
                    if fault == "empty": result.update(rows=[], pageToken="1")
                    if fault == "count": result["totalRows"] = "0"
                return {"http_status": 200, "body": json.dumps(result)}
            with self.subTest(fault=fault):
                self.assert_failure(hook, code)

    def test_rows_cannot_change_scope_currency_schema_keys_or_foreign_keys(self):
        for fault in ("scope", "currency", "private", "duplicate", "fk", "float", "date", "coverage"):
            def hook(api, method, path, body, result, response):
                if "/queries/" in path:
                    row = result["rows"][0]
                    payload = json.loads(row["f"][1]["v"])
                    if fault == "scope": payload["region"] = "South"
                    if fault == "currency": payload["currency"] = "INR"
                    if fault == "private": payload["private_email"] = "not allowed"
                    if fault == "duplicate":
                        result["rows"][1] = copy.deepcopy(row)
                    if fault == "fk":
                        payload["order_id"] = "OTHER"
                    if fault == "float":
                        other = result["rows"][2]
                        value = json.loads(other["f"][1]["v"])
                        value["quantity"] = 1.0
                        other["f"][1]["v"] = json.dumps(value)
                    if fault == "date": payload["order_date"] = "2026-02-30"
                    if fault == "coverage":
                        other = result["rows"][-1]
                        value = json.loads(other["f"][1]["v"])
                        value["complete"] = 1
                        other["f"][1]["v"] = json.dumps(value)
                    row["f"][1]["v"] = json.dumps(payload)
                return {"http_status": 200, "body": json.dumps(result)}
            with self.subTest(fault=fault), self.assertRaises(UpgradeError):
                self.run_import(hook)
            self.assertFalse(self.importer.state["snapshot_published"])

    def test_response_row_and_request_limits(self):
        def large(api, method, path, body, result, response):
            return {"http_status": 200, "body": " " * (CAPS["response_bytes"] + 1)}
        self.assert_failure(large, "BQ_RESPONSE_LIMIT")
        def rows(api, method, path, body, result, response):
            if "/queries/" in path: result["totalRows"] = "5001"
            return {"http_status": 200, "body": json.dumps(result)}
        self.assert_failure(rows, "BQ_INTEGER_LIMIT")
        def pending(api, method, path, body, result, response):
            if "/jobs/" in path and "/cancel?" not in path:
                result["status"]["state"] = "RUNNING"
            return {"http_status": 200, "body": json.dumps(result)}
        self.assert_failure(pending, "BQ_REQUEST_LIMIT")
        self.assertEqual(self.importer.state["requests"], 20)
        self.assertTrue(self.importer.state["remote_outcome_unknown"])
        self.assertFalse(self.importer.state["cancellation"]["terminal_observed"])

    def test_deadline_reserves_cleanup_and_does_not_accept_late_success(self):
        def late(api, method, path, body, result, response):
            if "/queries/" in path:
                self.clock.now = 57.0
            return response
        self.assert_failure(late, "BQ_DEADLINE")
        self.assertLessEqual(self.clock.now, 60)

    def test_known_owned_job_cancel_requires_independent_terminal_read(self):
        def interrupted(api, method, path, body, result, response):
            if "/jobs/" in path and "/cancel?" not in path and not any("/cancel?" in c[1] for c in api.calls):
                raise UpgradeError("BQ_CANCELLED")
            return response
        self.assert_failure(interrupted, "BQ_CANCELLED")
        self.assertTrue(self.importer.state["cancellation"]["terminal_observed"])
        self.assertFalse(self.importer.state["remote_outcome_unknown"])
        self.assertEqual(sum("/cancel?" in c[1] for c in self.api.calls), 1)
        self.assertIn(self.importer.state["job_id"], self.api.calls[-1][1])

    def test_ambiguous_unverified_submission_keeps_remote_unknown(self):
        def unknown(api, method, path, body, result, response):
            if body and not body["configuration"].get("dryRun"):
                raise OSError()
            if "/jobs/" in path:
                return {"http_status": 404, "body": ""}
            return response
        self.assert_failure(unknown, "BQ_RESOURCE_UNAVAILABLE")
        self.assertTrue(self.importer.state["remote_outcome_unknown"])
        self.assertFalse(self.importer.state["cancellation"]["requested"])
        self.assertEqual(sum(c[0] == "POST" and c[2] is not None and not c[2]["configuration"].get("dryRun") for c in self.api.calls), 1)

    def test_snapshot_payload_is_revalidated_not_a_mutable_dictionary(self):
        snapshot = self.run_import()
        payload = snapshot.payload()
        payload["data"]["orders"][0][2] = "South"
        self.assertEqual(snapshot.payload()["data"]["orders"][0][2], "North")
        with self.assertRaises(UpgradeError):
            ValidatedSnapshot(json.dumps(payload["data"]), snapshot.provenance_json).payload()

    def test_remote_gate_loader_and_resource_paths_are_host_owned(self):
        calls = []
        with self.assertRaises(UpgradeError):
            BigQueryTransport(config(), token_loader=lambda: calls.append("loaded"))
        self.assertEqual(calls, [])
        with self.assertRaises(UpgradeError):
            BigQueryTransport(config(), origin="https://attacker.invalid/bigquery/v2", sandbox_enabled=True)
        transport = BigQueryTransport(config(), origin="http://127.0.0.1:12345/bigquery/v2")
        self.assertEqual(transport.mode, "local_double")
        for method, path, body in (("POST", "/projects/fictional-ga-test/jobs", {"query": "SELECT private"}),
                                  ("GET", "https://example.invalid/", None),
                                  ("DELETE", "/projects/fictional-ga-test/jobs/ga_" + "a"*32 + "?location=US", None),
                                  ("GET", "/projects/fictional-ga-test/datasets/private/tables/base", None)):
            with self.subTest(path=path), self.assertRaises(UpgradeError):
                validate_request(config(), method, path, body)

    def test_model_tool_arguments_cannot_request_import_or_remote_authority(self):
        for name in ("propose_intent", "execute_query", "refresh_catalog", "finish_report", "handoff"):
            fields = tool_schema(name)["function"]["parameters"]["properties"]
            self.assertFalse(set(fields) & {"project", "dataset", "view", "principal", "location", "destination", "remote_sql", "token"})

    def test_cancellation_at_entry_sends_nothing(self):
        class Cancel:
            def is_set(self): return True
        api, clock = ContractAPI(), Clock()
        importer = SnapshotImporter(api.config, api, api.persist, clock=clock, sleep=clock.sleep, cancel_event=Cancel())
        with self.assertRaises(UpgradeError) as caught:
            importer.run()
        self.assertEqual(caught.exception.code, "BQ_CANCELLED")
        self.assertEqual(api.calls, [])
        self.assertFalse(importer.state["remote_outcome_unknown"])

    def test_malformed_result_schema_duplicate_json_null_and_oversized_page_stop(self):
        for fault, code in (("schema", "BQ_SCHEMA_DRIFT"), ("json", "DUPLICATE_JSON_KEY"),
                            ("null", "BQ_INVALID_ROW"), ("oversized", "BQ_INVALID_ROWS")):
            def hook(api, method, path, body, result, response):
                if "/queries/" in path:
                    if fault == "schema": result["schema"]["fields"][0]["name"] = "private"
                    if fault == "json": result["rows"][0]["f"][1]["v"] = '{"currency":"USD","currency":"INR"}'
                    if fault == "null": result["rows"][0]["f"][1]["v"] = None
                    if fault == "oversized": result["rows"] = [result["rows"][0]] * 501
                return {"http_status": 200, "body": json.dumps(result)}
            with self.subTest(fault=fault):
                self.assert_failure(hook, code)

    def test_total_response_bytes_and_page_cap_are_separate_from_per_response_cap(self):
        def padded(api, method, path, body, result, response):
            raw = json.dumps(result)
            return {"http_status": 200, "body": raw + " " * (200000 - len(raw))}
        self.assert_failure(padded, "BQ_RESPONSE_LIMIT")
        self.assertGreater(self.importer.state["response_bytes"], CAPS["total_bytes"])
        api, clock = ContractAPI(page_size=1), Clock()
        api.data["refunds"].extend([["R" + str(i), "O1", "2026-02-03", 1, "posted"] for i in range(2, 10)])
        importer = SnapshotImporter(api.config, api, api.persist, clock=clock, sleep=clock.sleep)
        with self.assertRaises(UpgradeError) as caught:
            importer.run()
        self.assertEqual(caught.exception.code, "BQ_PAGE_LIMIT")
        self.assertEqual(importer.state["pages"], 10)
        self.assertFalse(importer.state["snapshot_published"])

    def test_failed_durable_admission_cannot_transmit_execution_job(self):
        api, clock = ContractAPI(), Clock()
        def persist(state):
            if state["owned_job_admitted"]:
                raise OSError("Bearer NEVER_PERSIST_THIS")
            api.persist(state)
        importer = SnapshotImporter(api.config, api, persist, clock=clock, sleep=clock.sleep)
        with self.assertRaises(UpgradeError) as caught:
            importer.run()
        self.assertEqual(caught.exception.code, "BQ_CHECKPOINT_FAILED")
        self.assertEqual(sum(c[0] == "POST" and not c[2]["configuration"].get("dryRun") for c in api.calls), 0)
        self.assertFalse(importer.state["snapshot_published"])
        self.assertNotIn("NEVER_PERSIST_THIS", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
