"""LEASE REQUIRED. Two bounded reporting-wrapper checks, no cohort rerun."""
import json
import tempfile
import unittest
from pathlib import Path
from reporting.accounting import validate
from reporting.export import Reader, sha
from reporting.freeze import verify, ROOT
from reporting.journal import persist
from reporting.run import execute
from evaluation_v2.run import run_case


class JournalNativeTests(unittest.TestCase):
    def check_case(self, case_id):
        frozen = verify()
        cases = json.loads((ROOT/"evaluation_v2/cases/development.json").read_text(encoding="utf-8"))
        labels = json.loads((ROOT/"evaluation_v2/labels/development.json").read_text(encoding="utf-8"))
        case = next(c for c in cases if c["case_id"] == case_id)
        data = json.loads((ROOT/"evaluation_v2"/case["source"]).read_text(encoding="utf-8"))
        work = ROOT/"work"
        work.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="u2c-accounting-", dir=work) as temporary:
            path = Path(temporary)
            out = path/case_id/"deterministic-v2"
            def invoke(_):
                ledger = validate(json.loads((path/"attempts.json").read_text(encoding="utf-8")))
                self.assertEqual(ledger["attempts"][0]["state"], "STARTED")
                return run_case(case, data, labels[case_id], "deterministic-v2", out)
            def receipt(_):
                reader = Reader()
                report = reader.json(out/"report.json", "report")
                score = reader.bytes(out/"score.json", "score")
                return {"terminal_status": report["status"], "report_sha256": reader.hashes["report"], "score_sha256": sha(score)}
            ledger, rows = execute([{"case_id": case_id, "actor": "deterministic-v2", "numeric_applicable": labels[case_id]["kind"] == "numeric"}], frozen["source_sha256"], invoke, lambda d: persist(path/"attempts.json", d), receipt)
            self.assertEqual(ledger, validate(json.loads((path/"attempts.json").read_text(encoding="utf-8"))))
            self.assertEqual(ledger["attempts"][0]["state"], "TERMINAL")
            self.assertTrue(rows[0]["final_correct"], rows)
            self.assertEqual(ledger["attempts"][0]["terminal_status"], "completed" if case_id == "d07" else "failed")

    def test_numeric_attempt_has_durable_start_and_bound_terminal(self):
        self.check_case("d07")

    def test_expected_tamper_failed_status_remains_correct_safe_terminal(self):
        self.check_case("d17")
