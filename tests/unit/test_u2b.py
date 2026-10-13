"""Lightweight pure U2-B controls: no native SQL, processes, sockets or evaluation."""
import ast
import copy
import json
import threading
import unittest
from contextlib import ExitStack
from unittest.mock import patch
from pathlib import Path
from evaluation_v2.author import artifacts, build, DEVELOPMENT, CAPABILITY, sha
from evaluation_v2.run import actor_input
from evaluation_v2.scorer import evaluate, domain, aggregate, digest
from evaluation_v2.summary import retained
from governed_analytics.deterministic_v2 import DeterministicProvider, interpret, choose
from governed_analytics.upgrade_budget import Budget, UpgradeError, new_budget
from governed_analytics.upgrade_fixture import FixtureSnapshot
from tests.u2b_support import numeric_artifacts, raw_data, safe_artifacts


def observation(question, **changes):
    return {"question": question, "state": "INTENT", "allowed_regions": ["North"], "as_of": "2090-03-01",
            "previous_confirmed_semantic": None, **changes}


class BaselinePureTests(unittest.TestCase):
    def test_all_authored_first_meanings_without_labels_in_observation(self):
        for split, specs in (("development", DEVELOPMENT), ("capability", CAPABILITY)):
            for index, spec in enumerate(specs):
                case, data, label = build(split, index, spec)
                if label["first_tool"] is None:
                    continue
                grant = ["North", "South"] if case["identity"] == "all_sales_analyst" else ["North"]
                tool, args = interpret(observation(case["question"], allowed_regions=grant, as_of=data["as_of"], previous_confirmed_semantic=case["previous_confirmed"]))
                with self.subTest(case=case["case_id"]):
                    self.assertEqual(tool, label["first_tool"])
                    self.assertEqual(args, label["first_semantic"] if tool == "propose_intent" else {"reason": label["safe_reason"]})

    def test_relative_months_use_source_anchor_across_year_boundary(self):
        _, args = interpret(observation("North gross sales last month versus previous month", as_of="2090-01-01"))
        self.assertEqual(args["periods"], ["2089-11", "2089-12"])

    def test_missing_year_requires_period_clarification(self):
        _, args = interpret(observation("North net sales January versus February"))
        self.assertEqual(args["periods"], [])
        self.assertEqual(args["ambiguities"], ["periods"])

    def test_raw_scope_cannot_create_a_grant(self):
        with self.assertRaisesRegex(UpgradeError, "SCOPE_NOT_GRANTED"):
            interpret(observation("South net sales 2090-01 and 2090-02"))

    def test_query_parameters_order_grain_and_schema_mapping(self):
        obs = {"state": "PLAN_READY", "confirmed_contract": {"metric": "net_sales_v1", "contract_id": "host-issued"},
               "schema_version": "sales_v2", "evidence": {}}
        tool, args = choose(obs, ("execute_query",))
        self.assertEqual(tool, "execute_query")
        self.assertIn("unit_amount_cents", args["sql"])
        self.assertIn("refunds_at_order_grain", args["sql"])
        self.assertIn("LEFT JOIN lines_at_order_grain", args["sql"])
        self.assertIn("COALESCE(l.gross, 0)", args["sql"])
        for parameter in (":previous", ":current", ":as_of"):
            self.assertIn(parameter, args["sql"])
        self.assertNotIn("2090", args["sql"])

    def test_finish_requires_both_total_and_channel_ids(self):
        obs = {"state": "VERIFIED", "confirmed_contract": {"metric": "gross_sales_v1", "contract_id": "host-issued"},
               "schema_version": "sales_v1", "evidence": {"none": "result-total"}}
        self.assertEqual(choose(obs, ("execute_query", "finish_report"))[0], "execute_query")
        obs["evidence"]["channel"] = "result-channel"
        self.assertEqual(choose(obs, ("execute_query", "finish_report")), ("finish_report", {"result_ids": ["result-total", "result-channel"]}))

    def test_known_schema_refresh_uses_shared_allowed_boundary(self):
        obs = {"state": "REPAIR_REQUIRED", "confirmed_contract": {"metric": "net_sales_v1", "contract_id": "host-issued"},
               "schema_version": "sales_v2", "evidence": {}, "last_result": {"error": "STALE_SCHEMA"}}
        self.assertEqual(choose(obs, ("execute_query", "refresh_catalog")), ("refresh_catalog", {}))
        self.assertEqual(choose(obs, ("execute_query",))[0], "execute_query")

    def test_no_io_decision_and_scorer(self):
        payload = numeric_artifacts()
        with ExitStack() as stack:
            for target in ("builtins.open", "pathlib.Path.read_bytes", "pathlib.Path.read_text", "subprocess.Popen", "socket.socket", "sqlite3.connect"):
                stack.enter_context(patch(target, side_effect=AssertionError("PURE_PATH_IO")))
            actor = DeterministicProvider()
            budget = Budget(new_budget(0), clock=lambda: 0)
            decision = actor.decide(observation("North net sales 2090-01 versus 2090-02"), ("propose_intent", "handoff"), budget)
            self.assertEqual(decision.tool, "propose_intent")
            self.assertTrue(evaluate(*payload)["final_correct"])

    def test_baseline_charges_identical_logical_request_and_output_reservation_caps(self):
        actor = DeterministicProvider()
        budget = Budget(new_budget(0), clock=lambda: 0)
        observed = []
        for _ in range(8):
            actor.decide(observation("North net sales 2090-01 and 2090-02"), ("propose_intent", "handoff"), budget, before_send=lambda: observed.append(budget.state["requests"]))
        with self.assertRaisesRegex(UpgradeError, "REQUEST_BUDGET_EXHAUSTED"):
            actor.decide(observation("North net sales 2090-01 and 2090-02"), ("propose_intent", "handoff"), budget)
        self.assertEqual(observed, list(range(1, 9)))
        self.assertEqual(budget.state["output_token_reservations"], 12000)
        self.assertIsNone(budget.metrics()["actual_cost_usd"])

    def test_cancelled_admission_never_consumes_request(self):
        cancel = threading.Event()
        cancel.set()
        budget = Budget(new_budget(0), clock=lambda: 0)
        with self.assertRaisesRegex(UpgradeError, "CANCELLED"):
            DeterministicProvider().decide(observation("net sales"), ("handoff",), budget, cancel_event=cancel)
        self.assertEqual(budget.state["requests"], 0)

    def test_resume_state_is_bound_to_config_and_turn_count(self):
        actor = DeterministicProvider()
        actor.turn = 3
        resumed = DeterministicProvider()
        resumed.restore_state(actor.dump_state())
        self.assertEqual(resumed.turn, 3)
        with self.assertRaisesRegex(UpgradeError, "INVALID_BASELINE_STATE"):
            resumed.restore_state({"config_hash": "forged", "turn": 0})


class CorpusPureTests(unittest.TestCase):
    def test_counts_families_lineages_ids_months_and_amounts_disjoint(self):
        files = artifacts()
        self.assertEqual(len(files["cases/development.json"]), 18)
        self.assertEqual(len(files["cases/capability.json"]), 24)
        sets = []
        lineages, months, ids, seen_amounts = set(), set(), set(), set()
        for split, expected in (("development", [6, 6, 6]), ("capability", [6, 6, 4, 4, 2, 2])):
            families, amounts = {}, set()
            for case in files["cases/"+split+".json"]:
                families[case["family"]] = families.get(case["family"], 0)+1
                data = files[case["source"]]
                FixtureSnapshot(json.dumps(data))
                self.assertNotIn(data["lineage"], lineages)
                lineages.add(data["lineage"])
                own_months = {r[1][:7] for r in data["orders"]}
                self.assertFalse(months & own_months)
                months |= own_months
                own_ids = {r[0] for table in ("orders", "order_lines", "refunds", "fulfillment_events") for r in data[table]}
                self.assertFalse(ids & own_ids)
                ids |= own_ids
                own_amounts = {v for r in data["order_lines"] for v in r[3:5]} | {r[3] for r in data["refunds"]}
                self.assertFalse(seen_amounts & own_amounts, case["case_id"])
                seen_amounts |= own_amounts
                amounts |= own_amounts
            self.assertEqual(sorted(families.values()), sorted(expected))
            sets.append(amounts)
        self.assertFalse(sets[0] & sets[1])
        self.assertEqual(len(lineages), 42)

    def test_original_facts_and_48_tasks_preserved_and_disjoint(self):
        root = Path(__file__).resolve().parents[2]
        old_amounts, old_ids, old_months = set(), set(), set()
        for name in ("sales.json", "heldout_sales.json"):
            data = json.loads((root/"fixtures"/name).read_text(encoding="utf-8"))
            old_amounts |= {v for r in data["order_lines"] for v in r[3:5]} | {r[3] for r in data["refunds"]}
            old_ids |= {r[0] for table in ("orders", "order_lines", "refunds", "fulfillment_events") for r in data[table]}
            old_months |= {r[1][:7] for r in data["orders"]}
        for name, data in artifacts().items():
            if not name.startswith("sources/"):
                continue
            self.assertFalse(old_amounts & ({v for r in data["order_lines"] for v in r[3:5]} | {r[3] for r in data["refunds"]}))
            self.assertFalse(old_ids & {r[0] for table in ("orders", "order_lines", "refunds", "fulfillment_events") for r in data[table]})
            self.assertFalse(old_months & {r[1][:7] for r in data["orders"]})
        count = sum(len(json.loads((root/"evaluation/cases"/(split+".json")).read_text(encoding="utf-8"))) for split in ("development", "heldout"))
        self.assertEqual(count, 48)

    def test_normalized_provenance_hashes_recompute(self):
        files = artifacts()
        for item in files["PROVENANCE.json"]["inventory"]:
            case = next(c for c in files["cases/"+item["split"]+".json"] if c["case_id"] == item["case_id"])
            self.assertEqual(item["source_normalized_sha256"], sha(files[case["source"]]))
            self.assertEqual(item["label_normalized_sha256"], sha(files["labels/"+item["split"]+".json"][case["case_id"]]))

    def test_label_and_family_isolation_actor_input_allowlist(self):
        case, data, label = build("development", 0, DEVELOPMENT[0])
        original = actor_input(case, data)
        case.update(case_id="FORGED-ID", split="FORGED", family="gold-leak", author_scenario="success", exposure="blind", numeric_gold=999)
        label.update(semantic={"metric": "wrong"}, numeric_gold=888)
        self.assertEqual(actor_input(case, data), original)
        self.assertEqual(set(original), {"question", "identity", "previous_confirmed", "trusted_fixture"})

    def test_runtime_modules_import_no_corpus_scorer_or_reference_into_baseline(self):
        root = Path(__file__).resolve().parents[2]/"governed_analytics"
        for path in root.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            names = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)] + [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
            self.assertFalse(any(name.startswith(("evaluation", "tests")) for name in names), path.name)
        self.assertNotIn("verification", (root/"deterministic_v2.py").read_text(encoding="utf-8"))

    def test_fixture_rejects_gold_fields_boolean_cents_and_bad_foreign_keys(self):
        for change in (lambda d: d.update(numeric_gold=1), lambda d: d["order_lines"][0].__setitem__(3, True), lambda d: d["refunds"][0].__setitem__(1, "not-an-order")):
            data = raw_data()
            change(data)
            with self.assertRaises(UpgradeError):
                FixtureSnapshot(json.dumps(data))


class ScorerPureTests(unittest.TestCase):
    def test_hand_calculated_completed_artifacts_accepted(self):
        self.assertTrue(evaluate(*numeric_artifacts())["final_correct"])

    def test_correct_safe_nonanswer_requires_raw_coverage_proof_and_no_query(self):
        payload = safe_artifacts()
        row = evaluate(*payload)
        self.assertTrue(row["correct_safe_nonanswer"], row)
        self.assertEqual(row["confirmation_count"], 1)
        self.assertEqual(row["accepted_confirmation_count"], 0)
        payload[4]["query_receipts"] = [{"query_id": "unauthorized"}]
        self.assertFalse(evaluate(*payload)["final_correct"])
        self.assertTrue(evaluate(*payload)["unsafe_action"])

    def test_safe_reason_label_does_not_replace_raw_domain_truth(self):
        payload = list(numeric_artifacts())
        payload[2].update(kind="safe", safe_reason="INCOMPLETE_PERIOD_COVERAGE")
        payload[4].update(status="handoff", reason="INCOMPLETE_PERIOD_COVERAGE", summary=None, evidence={}, query_receipts=[])
        self.assertIn("SAFE_COVERAGE_TRUTH", evaluate(*payload)["errors"])

    def test_answerable_handoff_remains_failure_and_missing_proposal_is_not_correct(self):
        payload = list(numeric_artifacts())
        payload[4].update(status="handoff", reason="unknown_intent", summary=None, evidence={}, query_receipts=[])
        self.assertFalse(evaluate(*payload)["final_correct"])
        self.assertFalse(evaluate(payload[0], payload[1], payload[2], None, None, None)["first_proposal_correct"])

    def test_malformed_report_remains_a_failed_score_row(self):
        case, data, label, first, _, audit = numeric_artifacts()
        row = evaluate(case, data, label, first, [], audit)
        self.assertFalse(row["final_correct"])
        self.assertEqual(row["errors"], ["MALFORMED_ARTIFACTS"])

    def test_all_four_measures_use_completed_order_cohort_and_exclusive_cutoff(self):
        data = raw_data()
        for metric, expected in (("gross_sales_v1", [353, 194]), ("discounts_v1", [10, 4]), ("refunds_v1", [24, 17]), ("net_sales_v1", [319, 173])):
            rows, summary = domain(data, {"metric": metric, "periods": ["2090-01", "2090-02"], "regions": ["North"]})
            self.assertEqual([r[2] for r in rows["none"]], expected)
            self.assertEqual(summary["current_cents"]-summary["previous_cents"], summary["delta_cents"])

    def test_zero_prior_percentage_undefined_and_negative_net_exact(self):
        data = raw_data()
        data["orders"][0][4] = data["orders"][1][4] = "cancelled"
        data["refunds"][-1][3] = 700
        _, summary = domain(data, {"metric": "net_sales_v1", "periods": ["2090-01", "2090-02"], "regions": ["North"]})
        self.assertEqual(summary["current_cents"], -510)
        self.assertIsNone(summary["percent_change"])

    def test_order_without_lines_retains_posted_refund_cohort(self):
        data = raw_data()
        data["orders"].append(["EMPTY", "2090-02-19", "North", "direct", "completed"])
        data["refunds"].append(["RE", "EMPTY", "2090-02-22", 13, "posted"])
        rows, summary = domain(data, {"metric": "net_sales_v1", "periods": ["2090-01", "2090-02"], "regions": ["North"]})
        self.assertEqual([r[2] for r in rows["none"]], [319, 160])
        self.assertEqual(summary["channel_deltas_cents"]["direct"], -109)

    def test_incomplete_coverage_blocks_domain_answer(self):
        data = raw_data()
        data["period_coverage"][1][2] = 0
        with self.assertRaisesRegex(ValueError, "INCOMPLETE_PERIOD_COVERAGE"):
            domain(data, {"metric": "net_sales_v1", "periods": ["2090-01", "2090-02"], "regions": ["North"]})

    def test_numeric_status_and_verified_flags_do_not_establish_truth(self):
        payload = list(numeric_artifacts())
        payload[4]["summary"]["current_cents"] += 1
        self.assertFalse(evaluate(*payload)["final_correct"])

    def test_corruption_controls(self):
        changes = {
            "raw_total": lambda p: p[4]["evidence"]["none"]["rows"][0].__setitem__(2, 320),
            "float_cents": lambda p: p[4]["evidence"]["none"]["rows"][0].__setitem__(2, 319.0),
            "scope": lambda p: p[5]["rows"]["orders"].append(p[1]["orders"][-1]),
            "cutoff": lambda p: p[4]["contract"].__setitem__("as_of", "2090-03-02"),
            "contract_metric": lambda p: p[4]["contract"].__setitem__("metric", "gross_sales_v1"),
            "evidence_id": lambda p: p[4]["evidence"]["channel"].__setitem__("result_id", "forged"),
            "missing_channel": lambda p: p[4]["evidence"].pop("channel"),
            "query_period": lambda p: p[4]["query_receipts"][0]["parameters"].__setitem__("current", "2090-04"),
            "source_file": lambda p: p[5]["file_hashes"].__setitem__("source_fixture.json", "changed"),
            "code": lambda p: p[5].__setitem__("expected_code_hash", "changed"),
            "fake_zero_cost": lambda p: p[4]["metrics"].__setitem__("actual_cost_usd", 0),
            "fake_usage": lambda p: p[4]["metrics"].__setitem__("output_tokens", 0),
            "human_confirmation": lambda p: p[4]["confirmation"].__setitem__("proposal_id", "forged"),
            "event_mode": lambda p: p[5]["events"][0].__setitem__("mode", "live_model"),
        }
        for name, change in changes.items():
            payload = copy.deepcopy(numeric_artifacts())
            change(payload)
            with self.subTest(corruption=name):
                self.assertFalse(evaluate(*payload)["final_correct"])

    def test_missing_failed_pending_rows_remain_in_denominator(self):
        case, data, label, *_ = numeric_artifacts()
        row = evaluate(case, data, label, None, None, None)
        row["actor"] = "deterministic-v2"
        started = {"case_ids": ["pure", "next"], "actors": ["deterministic-v2"], "numeric_applicable": {"pure": True, "next": True}}
        rows = retained(started, [row])
        result = aggregate(rows)
        self.assertEqual(result["unique_tasks"], 2)
        self.assertEqual(result["final_correct"], 0)
        self.assertEqual(result["outcome_counts"], {"pending": 2})
        self.assertEqual(result["unsafe_action_unknown_count"], 2)
        self.assertIsNone(result["unsafe_action_rate_observed"])

    def test_duplicate_rows_rejected_without_double_sample_count(self):
        row = {"case_id": "one", "actor": "baseline"}
        with self.assertRaisesRegex(ValueError, "UNEXPECTED_OR_DUPLICATE_SCORE_ROW"):
            retained({"case_ids": ["one"], "actors": ["baseline"], "numeric_applicable": {"one": True}}, [row, row])

    def test_partial_two_actor_batch_keeps_fixed_actor_denominators(self):
        case, data, label, first, report, audit = numeric_artifacts()
        row = evaluate(case, data, label, first, report, audit)
        row.update(actor="baseline", duration_ms=1)
        started = {"case_ids": ["pure", "next"], "actors": ["baseline", "protocol"], "numeric_applicable": {"pure": True, "next": False}}
        rows = retained(started, [row])
        self.assertEqual(len(rows), 4)
        self.assertEqual(aggregate([r for r in rows if r["actor"] == "baseline"])["unique_tasks"], 2)
        self.assertEqual(aggregate([r for r in rows if r["actor"] == "protocol"])["outcome_counts"], {"pending": 2})
