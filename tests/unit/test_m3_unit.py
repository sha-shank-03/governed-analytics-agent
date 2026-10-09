"""Pure/injected checks only. No held-out arithmetic, scoring, SQL child or HTTP."""
import copy
import json
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import Mock, patch
from governed_analytics.catalog import resolve_request
from governed_analytics.data import source_fingerprints
from governed_analytics.orchestrator import Session
from governed_analytics.providers import FaultProvider
from evaluation.freeze import manifest
from evaluation.metrics import normalized_domain, digest, summarize_records

ROOT=Path(__file__).resolve().parents[2]


class M3PureTests(unittest.TestCase):
    def test_manifest_has_six_cases_per_family_and_24_expected_completions(self):
        cases=json.loads((ROOT/"evaluation/cases/heldout.json").read_text())
        gold=json.loads((ROOT/"evaluation/gold/heldout.json").read_text())
        self.assertEqual(len(cases),36)
        self.assertEqual(set(gold),{row["id"] for row in cases})
        self.assertEqual(set(Counter(row["family"] for row in cases).values()),{6})
        self.assertEqual(sum(row["status"]=="completed" for row in gold.values()),24)
        self.assertTrue(all("result" not in row and "expected_rows" not in row for row in cases))

    def test_relative_periods_use_fixture_anchor_and_handle_year_boundary(self):
        slots=resolve_request("Net sales last month versus previous month","north_analyst","2026-01-01")
        self.assertEqual(slots["periods"],["2025-11","2025-12"])
        with self.assertRaises(ValueError):
            resolve_request("Net sales last month versus previous month","north_analyst")

    def test_normalized_output_excludes_run_ids_and_execution_timing(self):
        report={"status":"completed","reason":None,"run_id":"a","summary":{"delta_cents":1},
                "query_receipts":[{"child_pid":1,"duration_ms":7}],"baseline_candidate":{"ok":True,"rows":[[1]],"duration_ms":9}}
        other=copy.deepcopy(report)
        other["run_id"]="b"
        other["query_receipts"][0].update(child_pid=2,duration_ms=100)
        other["baseline_candidate"]["duration_ms"]=100
        self.assertEqual(digest(normalized_domain(report)),digest(normalized_domain(other)))
        other["summary"]["delta_cents"]=2
        self.assertNotEqual(digest(normalized_domain(report)),digest(normalized_domain(other)))

    def test_repeatability_and_null_denominators_use_synthetic_records(self):
        rows=[{"mode":"synthetic","case_id":"fake","family":"test","repeat":repeat,"task_success":True,
               "numeric_correct":None,"safety_passed":True,"fault_injected":False,
               "elapsed_seconds":repeat/10,"normalized_domain_sha256":"same"} for repeat in (1,2,3)]
        metrics=summarize_records(rows,3)["synthetic"]
        self.assertEqual(metrics["aggregate"]["numeric_tasks"],0)
        self.assertEqual(metrics["aggregate"]["metric_period_scope"],{"passed":0,"applicable":0})
        self.assertEqual(metrics["repeatability"]["identical_cases"],1)
        rows[1]["normalized_domain_sha256"]="changed"
        self.assertEqual(summarize_records(rows,3)["synthetic"]["repeatability"]["identical_cases"],0)

    def test_freeze_binds_actor_baseline_and_evaluator_without_scoring(self):
        frozen=manifest()
        self.assertEqual(frozen["actor_sha256"],frozen["baseline_sha256"])
        self.assertFalse(frozen["score_created"])
        self.assertIn("evaluation/gold/heldout.json",frozen["files"])
        self.assertIn("governed_analytics/providers.py",frozen["files"])

    def test_unsupported_report_fields_are_rejected_once_then_evidence_report_finishes(self):
        for fault in ("claim_value","claim_cause","claim_scope"):
            with self.subTest(fault=fault):
                provider=FaultProvider(fault)
                state={"state":"PLAN_READY","status":"active","question":"Net sales January 2026 and February 2026",
                    "slots":{"metric":"net_sales_v1","periods":["2026-01","2026-02"],"regions":["North"]},
                    "provider_mode":provider.mode,"decision_fixture":fault,"catalog":{},"schema":{},
                    "source_fingerprints":source_fingerprints(),"snapshot_file_hash":"fake",
                    "contract":{"contract_id":"fake","metric":"net_sales_v1","periods":["2026-01","2026-02"],
                                "regions":["North"],"currency":"USD","as_of":"2026-03-01","groupings":["none","channel"]},
                    "evidence":{},"trace":[],"query_receipts":[],"call_ids":[],"action_results":{},
                    "turn":0,"attempts":0,"reference_queries":0,"repairs":0}
                total={"ok":True,"columns":["period_key","group_key","value_cents"],"rows":[["2026-01","all",1000000],["2026-02","all",780000]],"duration_ms":1,"child_pid":42,"child_reaped":True}
                channel={**total,"rows":[["2026-01","direct",600000],["2026-01","partner",400000],["2026-02","direct",380000],["2026-02","partner",400000]]}
                session=Session(Path("unused-pure-test"),state,provider)
                session.save=Mock()
                with patch("governed_analytics.orchestrator.file_hash",return_value="fake"), \
                     patch("governed_analytics.orchestrator.run_sql",side_effect=[total,total,channel,channel]) as worker, \
                     patch("governed_analytics.orchestrator.write_json"),patch.object(Path,"write_text"):
                    report=session.drive()
                self.assertEqual(report["status"],"completed")
                self.assertEqual(report["budgets"]["report_rejections"],1)
                self.assertEqual(report["summary"]["delta_cents"],-220000)
                self.assertTrue(any(row.get("tool")=="host_report_field_check" for row in report["tool_trace"]))
                self.assertEqual(worker.call_count,4)
