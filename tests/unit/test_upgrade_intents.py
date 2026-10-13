import copy
import unittest
from governed_analytics.upgrade_budget import UpgradeError
from governed_analytics.upgrade_intents import (MEASURES, confirm, proposal_receipt,
                                              request_guard, validate_semantic)

SEMANTIC = {"metric": "net_sales_v1", "periods": ["2026-01", "2026-02"], "regions": ["North"],
            "groupings": ["none", "channel"], "currency": "USD", "ambiguities": []}


class IntentTests(unittest.TestCase):
    def setUp(self):
        self.state = {"as_of": "2026-03-01", "catalog": {"measures": {m: m for m in MEASURES}},
            "grant": ["North"], "request_hash": "request", "config_hash": "config", "code_hash": "code",
            "source_fingerprints": {"policies.json": "policy"}, "schema_hash": "schema", "snapshot_hash": "snapshot"}
        self.receipt = proposal_receipt(SEMANTIC, self.state)

    def test_all_four_measures_and_supported_groupings(self):
        for measure in MEASURES:
            with self.subTest(measure=measure):
                value = {**SEMANTIC, "metric": measure}
                self.assertEqual(validate_semantic(value, ["North"], confirmed=True), value)

    def test_full_confirmation_and_human_correction(self):
        corrected = {**SEMANTIC, "metric": "gross_sales_v1"}
        self.assertEqual(confirm(self.receipt, {"proposal_id": self.receipt["proposal_id"], "semantic": corrected},
                                 self.state), corrected)

    def test_missing_metric_dates_ambiguity_never_confirm(self):
        for changed in ({"metric": None}, {"periods": []}, {"ambiguities": ["metric"]},
                        {"ambiguities": ["followup"]}, {"ambiguities": ["unsupported"]}):
            value = {**SEMANTIC, **changed}
            validate_semantic(value, ["North"])
            with self.assertRaisesRegex(UpgradeError, "INTENT_REQUIRES_CLARIFICATION"):
                validate_semantic(value, ["North"], confirmed=True)

    def test_unknown_measure_formula_and_scope_are_rejected(self):
        for changed in ({"metric": "profit"}, {"metric": "gross - costs"}, {"metric": {}},
                        {"regions": ["South"]}, {"regions": ["North", "South"]},
                        {"groupings": ["region"]}, {"currency": "INR"}):
            with self.subTest(changed=changed), self.assertRaises(UpgradeError):
                validate_semantic({**SEMANTIC, **changed}, ["North"])

    def test_dates_order_duplicates_and_invalid_shapes(self):
        for periods in (["2026-02", "2026-01"], ["2026-01", "2026-01"], ["2026-13", "2026-14"],
                        ["2026-01"], [1, 2], ["0000-01", "2026-02"], "2026-01"):
            with self.subTest(periods=periods), self.assertRaises(UpgradeError):
                validate_semantic({**SEMANTIC, "periods": periods}, ["North"])

    def test_model_cannot_add_identity_cutoff_or_sql(self):
        for key in ("identity", "as_of", "sql", "contract_id", "source_url"):
            with self.subTest(key=key), self.assertRaisesRegex(UpgradeError, "INVALID_INTENT_FIELDS"):
                validate_semantic({**SEMANTIC, key: "attacker"}, ["North"])

    def test_confirmation_is_bound_to_all_host_context(self):
        answer = {"proposal_id": self.receipt["proposal_id"], "semantic": SEMANTIC}
        for key in ("request_hash", "config_hash", "code_hash", "schema_hash", "snapshot_hash", "as_of"):
            changed = {**self.state, key: "changed"}
            with self.subTest(key=key), self.assertRaisesRegex(UpgradeError, "CONFIRMATION_CONTEXT_CHANGED"):
                confirm(self.receipt, answer, changed)
        changed = copy.deepcopy(self.state)
        changed["source_fingerprints"]["policies.json"] = "changed"
        with self.assertRaises(UpgradeError):
            confirm(self.receipt, answer, changed)

    def test_stale_forged_extra_confirmation(self):
        with self.assertRaisesRegex(UpgradeError, "STALE_CONFIRMATION"):
            confirm(self.receipt, {"proposal_id": "forged", "semantic": SEMANTIC}, self.state)
        with self.assertRaisesRegex(UpgradeError, "INVALID_CONFIRMATION_FIELDS"):
            confirm(self.receipt, {"proposal_id": self.receipt["proposal_id"], "semantic": SEMANTIC, "approved": True}, self.state)

    def test_host_private_scope_and_causal_guard(self):
        for question, code in (("Show South sales", "SCOPE_NOT_GRANTED"),
                               ("Show private customer email", "PRIVATE_DATA_REQUEST"),
                               ("Explain what caused the decline", "CAUSAL_EVIDENCE_UNAVAILABLE"),
                               ("Show company-wide sales", "SCOPE_NOT_GRANTED")):
            with self.subTest(question=question), self.assertRaisesRegex(UpgradeError, code):
                request_guard(question, "north_analyst")
        self.assertEqual(request_guard("How much did North retain after refunds?", "north_analyst"), ["North"])


class HostGateTests(unittest.TestCase):
    """Pure dispatch seams: verify blocked actions never invoke SQL."""
    def session(self, query):
        from pathlib import Path
        from governed_analytics.upgrade import UpgradeSession
        from governed_analytics.upgrade_budget import Budget, new_budget
        session = object.__new__(UpgradeSession)
        session.out = Path("unused")
        session.state = {"evidence": {}, "host_counters": {"candidates": 0, "references": 0,
            "repairs": 0, "schema_refreshes": 0}, "query_receipts": []}
        session.cancel_event = None
        session.query = query
        session.budget = Budget(new_budget())
        session.check = session.budget.check
        session.save = lambda *a, **k: None
        return session

    def test_confirmation_and_contract_gates_before_sql(self):
        from governed_analytics.providers import Decision
        called = []
        session = self.session(lambda *a, **k: called.append(True))
        action = Decision("c1", "execute_query", {"contract_id": "forged", "grouping": "none", "sql": "SELECT 1"})
        with self.assertRaisesRegex(UpgradeError, "CONFIRMATION_REQUIRED"):
            session.dispatch(action)
        session.state.update(confirmation={"authority": "external"}, contract={"contract_id": "real", "groupings": ["none", "channel"]})
        with self.assertRaisesRegex(UpgradeError, "INVALID_CONTRACT_ACTION"):
            session.dispatch(action)
        self.assertEqual(called, [])
        self.assertEqual(session.state["host_counters"]["candidates"], 0)

    def test_false_completion_cannot_invent_evidence(self):
        from governed_analytics.providers import Decision
        session = self.session(lambda *a, **k: self.fail("must not query"))
        session.state.update(confirmation={}, contract={"periods": ["2026-01", "2026-02"]})
        with self.assertRaisesRegex(UpgradeError, "UNVERIFIED_COMPLETION"):
            session.dispatch(Decision("c1", "finish_report", {"result_ids": ["fake1", "fake2"]}))

    def test_query_cleanup_failure_receipt_is_retained(self):
        from governed_analytics.providers import Decision
        from governed_analytics.upgrade_budget import LIMITS
        def failed(*a, **k):
            raise UpgradeError("CHILD_CLEANUP_FAILED", {"child_pid": 44, "child_reaped": False})
        session = self.session(failed)
        session.state.update(confirmation={}, contract={"contract_id": "real", "groupings": ["none", "channel"],
            "periods": ["2026-01", "2026-02"], "as_of": "2026-03-01"}, schema_version="sales_v1",
            snapshot_hash="snapshot", limits=LIMITS)
        with self.assertRaisesRegex(UpgradeError, "CHILD_CLEANUP_FAILED"):
            session.dispatch(Decision("c1", "execute_query", {"contract_id": "real", "grouping": "none", "sql": "SELECT 1"}))
        self.assertEqual(session.state["query_receipts"][0]["candidate"]["child_pid"], 44)
        self.assertFalse(session.state["query_receipts"][0]["candidate"]["child_reaped"])

    def test_completion_deadline_includes_final_artifact_writes(self):
        from unittest.mock import patch
        from governed_analytics.upgrade_budget import Budget, LIMITS, new_budget
        from governed_analytics.upgrade_gateway import GatewayConfig, GatewayProvider
        session = self.session(lambda *a, **k: self.fail("must not query"))
        now = [0.0]
        session.budget = Budget(new_budget(0), clock=lambda: now[0])
        now[0] = 59.9
        session.provider = GatewayProvider(GatewayConfig("http://127.0.0.1:123/v1/chat/completions", "local/synthetic-tool-model"), lambda *a, **k: None)
        session.state.update(run_id="run", code_hash="code", config_hash="config", proposal={},
            gateway_receipts=[], source_fingerprints={}, trace=[], limits=LIMITS)
        session.check = session.budget.check
        def save(kind, *a, **k):
            if kind == "report_saved":
                now[0] += .2
        session.save = save
        with patch("governed_analytics.upgrade.atomic_json"), patch("governed_analytics.upgrade.source_fingerprints", return_value={}):
            with self.assertRaisesRegex(UpgradeError, "RUN_DEADLINE"):
                session.finish("completed", summary={"delta_cents": 1})


if __name__ == "__main__":
    unittest.main()
