"""Pure reporting/journal controls; never invokes SQLite, children or actors."""
import copy
import json
import unittest
from contextlib import ExitStack
from unittest.mock import patch
from reporting.accounting import new_ledger, transition, close, validate, lifecycle, ReportingError
from reporting.export import decode, summarize_attempt, aggregate, summaries, markdown, empty_attempt
from reporting.run import execute
from reporting.replay import check
from tests.u2b_support import numeric_artifacts, safe_artifacts

SOURCE = "a"*64
PLAN = [{"case_id": "d01", "actor": "deterministic-v2", "numeric_applicable": True},
        {"case_id": "d02", "actor": "deterministic-v2", "numeric_applicable": True}]
RECEIPT = {"terminal_status": "completed", "report_sha256": "b"*64, "score_sha256": "c"*64}


def curated(payload=None, actor="deterministic-v2"):
    case, data, label, first, report, audit = payload or numeric_artifacts()
    from evaluation_v2.scorer import evaluate
    score = evaluate(case, data, label, first, report, audit)
    score.update(actor=actor, duration_ms=2)
    case.update(split="development")
    return summarize_attempt(case, data, label, first, report, audit, score, lifecycle(None, legacy_status=report["status"]))


class AccountingTests(unittest.TestCase):
    def test_intended_closed_is_unexecuted_not_failed(self):
        ledger = close(new_ledger(PLAN, SOURCE))
        self.assertEqual(lifecycle(ledger["attempts"][0])["state"], "unexecuted")

    def test_start_precedes_invoke_and_terminal_is_bound(self):
        saved, invocations = [], []
        def invoke(intent):
            self.assertEqual(saved[-1]["attempts"][len(invocations)]["state"], "STARTED")
            invocations.append(intent)
            return {"final_correct": True}
        ledger, rows = execute(PLAN, SOURCE, invoke, lambda d: saved.append(copy.deepcopy(d)), lambda _: RECEIPT, clock=lambda: 1)
        self.assertEqual(len(invocations), 2)
        self.assertTrue(all(i["state"] == "TERMINAL" for i in ledger["attempts"]))

    def test_interruption_keeps_next_attempt_unexecuted(self):
        def interrupted(_):
            raise KeyboardInterrupt()
        ledger, rows = execute(PLAN, SOURCE, interrupted, lambda _: None, lambda _: RECEIPT, clock=lambda: 1)
        self.assertEqual([lifecycle(i)["state"] for i in ledger["attempts"]], ["interrupted_unknown", "unexecuted"])
        self.assertEqual(rows, [])

    def test_failed_start_persistence_never_invokes_actor(self):
        saved, calls = [], []
        def save(value):
            if value["batch_state"] == "OPEN" and value["attempts"][0]["state"] == "STARTED":
                raise OSError("synthetic persistence failure")
            saved.append(value)
        ledger, _ = execute(PLAN, SOURCE, lambda i: calls.append(i), save, lambda _: RECEIPT, clock=lambda: 1)
        self.assertEqual(calls, [])
        self.assertEqual(lifecycle(ledger["attempts"][0])["state"], "unexecuted")

    def test_terminal_write_failure_is_unknown_not_passed(self):
        def save(value):
            if value["batch_state"] == "OPEN" and value["attempts"][0]["state"] == "TERMINAL":
                raise OSError("synthetic terminal write failure")
        ledger, _ = execute(PLAN, SOURCE, lambda _: {"final_correct": True}, save, lambda _: RECEIPT, clock=lambda: 1)
        self.assertEqual(lifecycle(ledger["attempts"][0])["state"], "interrupted_unknown")

    def test_missing_terminal_evidence_is_unknown(self):
        ledger, _ = execute(PLAN, SOURCE, lambda _: {"final_correct": True}, lambda _: None, lambda _: None, clock=lambda: 1)
        self.assertEqual(ledger["attempts"][0]["state"], "INTERRUPTED_UNKNOWN")
        self.assertEqual(ledger["attempts"][1]["state"], "INTENDED")

    def test_native_failed_terminal_and_scoring_failure_are_separate(self):
        ledger, _ = execute(PLAN, SOURCE, lambda _: {"final_correct": False}, lambda _: None, lambda _: {**RECEIPT, "terminal_status": "failed"}, clock=lambda: 1)
        self.assertEqual(ledger["attempts"][0]["state"], "TERMINAL")
        self.assertEqual(ledger["attempts"][0]["terminal_status"], "failed")
        self.assertEqual(lifecycle(ledger["attempts"][1])["state"], "unexecuted")

    def test_open_started_does_not_claim_interruption(self):
        ledger = transition(new_ledger(PLAN, SOURCE), "d01", "deterministic-v2", "STARTED", started_at=1)
        self.assertEqual(lifecycle(ledger["attempts"][0])["state"], "STARTED")
        self.assertEqual(lifecycle(ledger["attempts"][0], closed=True)["state"], "interrupted_unknown")

    def test_legacy_absence_never_proves_unexecuted(self):
        self.assertEqual(lifecycle(None, closed=True)["state"], "execution_unknown")
        self.assertEqual(lifecycle(None, closed=True, legacy_artifact_present=True)["state"], "interrupted_unknown")

    def test_duplicate_and_replayed_start_rejected(self):
        with self.assertRaises(ReportingError):
            new_ledger([PLAN[0], PLAN[0]], SOURCE)
        ledger = transition(new_ledger(PLAN, SOURCE), "d01", "deterministic-v2", "STARTED", started_at=1)
        with self.assertRaises(ReportingError):
            transition(ledger, "d01", "deterministic-v2", "STARTED", started_at=2)

    def test_serial_execution_and_closed_resume_rejected(self):
        ledger = transition(new_ledger(PLAN, SOURCE), "d01", "deterministic-v2", "STARTED", started_at=1)
        with self.assertRaises(ReportingError):
            transition(ledger, "d02", "deterministic-v2", "STARTED", started_at=2)
        with self.assertRaises(ReportingError):
            transition(close(ledger), "d02", "deterministic-v2", "STARTED", started_at=2)

    def test_plan_and_sequence_limits_are_bounded(self):
        with self.assertRaises(ReportingError):
            new_ledger(PLAN*43, SOURCE)
        ledger = new_ledger(PLAN, SOURCE)
        ledger["sequence"] = 171
        with self.assertRaises(ReportingError):
            validate(ledger)


class ExportTests(unittest.TestCase):
    def test_duplicate_truncated_nonfinite_and_oversized_json_rejected(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":', b'{"a":NaN}', b' '*1048577):
            with self.assertRaises(ReportingError):
                decode(raw)

    def test_raw_numeric_artifacts_revalidate_and_unknown_usage_stays_null(self):
        item = curated()
        self.assertEqual(item["scoring"], "correct")
        self.assertEqual(item["numeric_summary"]["current_cents"], 173)
        for key in ("input_tokens", "output_tokens", "actual_cost_usd", "estimated_cost_usd"):
            self.assertIsNone(item[key])

    def test_missing_audit_cannot_use_saved_score_pass(self):
        payload = list(numeric_artifacts())
        case, data, label, first, report, _ = payload
        case["split"] = "development"
        score = {"actor": "deterministic-v2", "final_correct": True}
        item = summarize_attempt(case, data, label, first, report, None, score, lifecycle(None, legacy_status="completed"))
        self.assertEqual(item["scoring"], "unknown")
        self.assertIsNone(item["numeric_correct"])

    def test_malformed_score_and_false_zero_cost_do_not_pass(self):
        case, data, label, first, report, audit = numeric_artifacts()
        case["split"] = "development"
        for score in ({"actor": "deterministic-v2", "final_correct": True}, [], None):
            item = summarize_attempt(case, data, label, first, report, audit, score, lifecycle(None, legacy_status="completed"))
            self.assertEqual(item["scoring"], "unknown")
        report["metrics"]["actual_cost_usd"] = 0
        self.assertEqual(curated((case, data, label, first, report, audit))["scoring"], "unknown")

    def test_safe_stop_is_counted_separately_from_numeric_completion(self):
        item = curated(safe_artifacts())
        self.assertEqual(item["scoring"], "correct")
        self.assertTrue(item["correct_safe_nonanswer"])
        self.assertFalse(item["numeric_correct"])
        self.assertEqual(aggregate([item])["correct_safe_nonanswers"], 1)
        self.assertEqual(aggregate([item])["numeric_correct"], 0)

    def test_unknown_and_unexecuted_remain_in_denominator_without_false_failure(self):
        case = {"case_id": "d01", "split": "development"}
        unknown = empty_attempt(case, "deterministic-v2", lifecycle(None, closed=True))
        unknown["numeric_applicable"] = True
        unexecuted = empty_attempt({**case, "case_id": "d02"}, "deterministic-v2", lifecycle(new_ledger(PLAN, SOURCE)["attempts"][1]))
        unexecuted["numeric_applicable"] = True
        summary = aggregate([unknown, unexecuted])
        self.assertEqual(summary["intended_attempts"], 2)
        self.assertEqual(summary["scored_incorrect"], 0)
        self.assertEqual(summary["scoring_unknown"], 2)
        self.assertEqual(summary["lifecycle_counts"], {"execution_unknown": 1, "unexecuted": 1})

    def test_same_task_two_arms_adds_no_independent_sample(self):
        result = summaries([curated(), curated(actor="protocol-double")])
        self.assertEqual(result["unique_tasks"], 1)
        self.assertEqual(result["actor_attempts"], 2)
        self.assertEqual(result["same_policy_ties"], 1)

    def test_payload_text_and_machine_paths_never_reach_projection(self):
        payload = list(numeric_artifacts())
        payload[4]["untrusted_text"] = "Bearer synthetic-secret C:/Users/private-owner/file"
        payload[5]["untrusted_text"] = payload[4]["untrusted_text"]
        item = curated(payload)
        self.assertNotIn("Bearer", json.dumps(item))
        self.assertNotIn("private-owner", json.dumps(item))

    def test_no_io_or_native_calls_in_accounting_and_projection(self):
        payload = numeric_artifacts()
        with ExitStack() as stack:
            for target in ("builtins.open", "pathlib.Path.read_bytes", "pathlib.Path.read_text", "subprocess.Popen", "socket.socket", "sqlite3.connect"):
                stack.enter_context(patch(target, side_effect=AssertionError("PURE_PATH_IO")))
            ledger, _ = execute(PLAN, SOURCE, lambda _: {"final_correct": True}, lambda _: None, lambda _: RECEIPT, clock=lambda: 1)
            self.assertEqual(ledger["batch_state"], "CLOSED")
            self.assertEqual(curated(payload)["scoring"], "correct")


class ReplayTests(unittest.TestCase):
    def fixture(self):
        case, data, label, *_ = numeric_artifacts()
        case["split"] = "development"
        rows = [curated(), curated(actor="protocol-double")]
        for row in rows:
            row["raw_artifact_sha256"] = {"report.json": "b"*64}
        frozen = {"source_sha256": SOURCE, "corpus_sha256": "c"*64}
        snapshot = {"version": "u2c-observed-v1", "evaluation_source_sha256": SOURCE, "corpus_sha256": "c"*64,
                    "attempts": rows, "summary": summaries(rows)}
        return snapshot, {"pure": case}, {"pure": label}, {"pure": data}, frozen

    def test_snapshot_recomputes_raw_cents_and_summary(self):
        snapshot, *context = self.fixture()
        self.assertEqual(check(snapshot, *context)["unique_tasks"], 1)

    def test_summary_contradiction_and_duplicate_attempt_rejected(self):
        for mutate in (lambda s: s["summary"].__setitem__("same_policy_ties", 99), lambda s: s["attempts"].__setitem__(1, copy.deepcopy(s["attempts"][0]))):
            snapshot, *context = self.fixture()
            mutate(snapshot)
            with self.assertRaises(ReportingError):
                check(snapshot, *context)

    def test_changed_numeric_or_float_cents_rejected(self):
        for value in (174, 173.0):
            snapshot, *context = self.fixture()
            snapshot["attempts"][0]["numeric_summary"]["current_cents"] = value
            snapshot["summary"] = summaries(snapshot["attempts"])
            with self.assertRaises(ReportingError):
                check(snapshot, *context)

    def test_unknown_score_cannot_retain_passed_fields(self):
        snapshot, *context = self.fixture()
        snapshot["attempts"][0]["scoring"] = "unknown"
        snapshot["summary"] = summaries(snapshot["attempts"])
        with self.assertRaisesRegex(ReportingError, "UNKNOWN_CANNOT_PASS"):
            check(snapshot, *context)

    def test_markdown_renders_unknown_counts_without_claiming_full_completion(self):
        case = {"case_id": "d01", "split": "development"}
        rows = [empty_attempt(case, actor, lifecycle(None)) for actor in ("deterministic-v2", "protocol-double")]
        for row in rows:
            row["numeric_applicable"] = True
        rendered = markdown({"summary": summaries(rows)})
        self.assertIn("0/1 numeric completions", rendered)
        self.assertIn("1 attempts have unknown scoring", rendered)
        self.assertNotIn("Per arm: 29 numeric completions", rendered)
