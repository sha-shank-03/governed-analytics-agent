import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from governed_analytics.__main__ import demo, QUESTION
from governed_analytics.data import source_fingerprints

ROOT = Path(__file__).resolve().parents[2]


class M1IntegrationTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / "work" / "integration-temp"
        scratch.mkdir(parents=True, exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=scratch)
        self.before = source_fingerprints()

    def tearDown(self):
        self.directory.cleanup()
        self.assertEqual(source_fingerprints(), self.before)

    def test_revenue_demo_completes_with_rejection_and_repair(self):
        output = Path(self.directory.name) / "revenue"
        report = demo("revenue-drop", output)
        self.assertEqual(report["status"], "completed")
        self.assertEqual(report["summary"]["previous_cents"], 1000000)
        self.assertEqual(report["summary"]["current_cents"], 780000)
        self.assertEqual(report["summary"]["delta_cents"], -220000)
        self.assertEqual(sum(report["summary"]["channel_deltas_cents"].values()), -220000)
        self.assertEqual(report["budgets"]["repairs_used"], 1)
        self.assertEqual(report["budgets"]["candidate_sql_used"], 3)
        self.assertEqual(report["provider_mode"], "scripted_policy_with_authored_fault")
        self.assertNotIn("CANARY", (output / "report.json").read_text())
        self.assertTrue((output / "report.md").exists())

    def test_scope_denial_has_no_query_or_projection(self):
        output = Path(self.directory.name) / "denial"
        report = demo("denied-scope", output)
        self.assertEqual(report["status"], "access_denied")
        self.assertEqual(report["query_receipts"], [])
        self.assertFalse((output / "scoped.sqlite").exists())

    def test_cli_pauses_before_query_then_accepts_external_answer(self):
        output = Path(self.directory.name) / "question"
        first = subprocess.run([sys.executable, "-m", "governed_analytics", "run",
            "--identity", "north_analyst", "--question", QUESTION, "--out", str(output)],
            cwd=ROOT, capture_output=True, text=True, timeout=10)
        self.assertEqual(first.returncode, 2, first.stderr)
        paused = json.loads((output / "report.json").read_text())
        self.assertEqual(paused["query_receipts"], [])
        second = subprocess.run([sys.executable, "-m", "governed_analytics", "resume",
            "--run", str(output), "--answer", "net_sales_v1"],
            cwd=ROOT, capture_output=True, text=True, timeout=15)
        self.assertEqual(second.returncode, 0, second.stderr)
        completed = json.loads((output / "report.json").read_text())
        self.assertEqual(completed["summary"]["delta_cents"], -220000)
        self.assertEqual(completed["contract"]["metric_origin"], "external_clarification")


if __name__ == "__main__":
    unittest.main()
