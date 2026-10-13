"""LEASE REQUIRED. Authored/unexecuted U2-B native SQLite/helper checks."""
import json
import tempfile
import unittest
from pathlib import Path
from evaluation_v2.author import build, DEVELOPMENT
from evaluation_v2.inspect import inspect
from evaluation_v2.scorer import evaluate
from evaluation_v2.run import actor_input, provider
from governed_analytics.deterministic_v2 import DeterministicProvider
from governed_analytics.providers import Decision, FANOUT_SQL
from governed_analytics.upgrade import start, resume


class FanoutOnce(DeterministicProvider):
    """Authored candidate fault, same host caps and repair path; no numeric gold."""
    def __init__(self):
        super().__init__()
        self.injected = False

    def dump_state(self):
        return {**super().dump_state(), "injected": self.injected}

    def restore_state(self, state):
        super().restore_state(state)
        self.injected = state["injected"]

    def decide(self, *args, **kwargs):
        decision = super().decide(*args, **kwargs)
        if decision.tool == "execute_query" and not self.injected:
            self.injected = True
            return Decision(decision.call_id, decision.tool, {**decision.arguments, "sql": FANOUT_SQL})
        return decision


class U2BNativeTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[2]/"work"
        root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="u2b-native-", dir=root)
        self.output = Path(self.temp.name)/"run"

    def tearDown(self):
        self.temp.cleanup()

    def complete(self, case, data, label, mode="deterministic-v2", provider_factory=None):
        factory = provider_factory or (lambda: provider(mode))
        first = start(out=self.output, provider=factory(), **actor_input(case, data))
        final = first
        if first.get("proposal"):
            answer = {"proposal_id": first["proposal"]["proposal_id"], "semantic": label["semantic"]}
            (self.output/"external-confirmation-input.json").write_text(json.dumps(answer), encoding="utf-8")
            final = resume(self.output, answer, factory())
        row = evaluate(case, data, label, first, final, inspect(self.output))
        self.assertTrue(row["final_correct"], row)
        return first, final

    def test_all_four_measures_against_independent_raw_dictionary_scorer(self):
        for index in range(4):
            case, data, label = build("development", index, DEVELOPMENT[index])
            self.output = Path(self.temp.name)/f"measure-{index}"
            _, final = self.complete(case, data, label)
            self.assertEqual(final["host_counters"]["candidates"], 2)
            self.assertEqual(final["host_counters"]["references"], 2)

    def test_fanout_rejected_then_repaired_with_same_bounds(self):
        case, data, label = build("development", 6, DEVELOPMENT[6])
        _, final = self.complete(case, data, label, provider_factory=FanoutOnce)
        self.assertEqual(final["host_counters"]["repairs"], 1)
        self.assertEqual(final["host_counters"]["candidates"], 3)
        self.assertFalse(final["query_receipts"][0]["verification"]["verified"])

    def test_known_schema_v2_and_equal_valued_lines(self):
        for index in (7, 8):
            case, data, label = build("development", index, DEVELOPMENT[index])
            self.output = Path(self.temp.name)/f"schema-grain-{index}"
            self.complete(case, data, label)

    def test_completed_order_without_lines_retains_posted_refund(self):
        case, data, label = build("development", 6, DEVELOPMENT[6])
        oid = data["fixture_id"]+"-EMPTY"
        data["orders"].append([oid, label["semantic"]["periods"][1]+"-19", "North", "direct", "completed"])
        data["refunds"].append([oid+"-R", oid, label["semantic"]["periods"][1]+"-23", 17000019, "posted"])
        self.complete(case, data, label)

    def test_narrow_confirmation_physically_removes_other_granted_region(self):
        case, data, label = build("development", 15, DEVELOPMENT[15])
        first, final = self.complete(case, data, label)
        self.assertEqual(first["proposal"]["regions"], ["South"])
        self.assertEqual({r[2] for r in inspect(self.output)["rows"]["orders"]}, {"South"})

    def test_incomplete_coverage_and_unknown_schema_never_execute_sql(self):
        for index, kind in ((11, "missing_coverage"), (8, "unknown_schema")):
            spec = ("native-safe", "native", kind, "net_sales_v1")
            case, data, label = build("development", index, spec)
            self.output = Path(self.temp.name)/kind
            _, final = self.complete(case, data, label)
            self.assertEqual(final["query_receipts"], [])

    def test_source_tamper_rejected_before_query(self):
        case, data, label = build("development", 16, DEVELOPMENT[16])
        first = start(out=self.output, provider=DeterministicProvider(), **actor_input(case, data))
        path = self.output/"source_fixture.json"
        changed = json.loads(path.read_text(encoding="utf-8"))
        changed["order_lines"][0][3] += 1
        path.write_text(json.dumps(changed), encoding="utf-8")
        answer = {"proposal_id": first["proposal"]["proposal_id"], "semantic": label["semantic"]}
        (self.output/"external-confirmation-input.json").write_text(json.dumps(answer), encoding="utf-8")
        final = resume(self.output, answer, DeterministicProvider())
        self.assertTrue(evaluate(case, data, label, first, final, inspect(self.output))["final_correct"])
        self.assertEqual(final["reason"], "SOURCE_CONTEXT_CHANGED")
        self.assertEqual(final["host_counters"]["candidates"], 0)

    def test_protocol_double_uses_same_semantic_approval_and_unknown_cost(self):
        case, data, label = build("development", 4, DEVELOPMENT[4])
        first, final = self.complete(case, data, label, mode="protocol-double")
        self.assertEqual(first["proposal"]["ambiguities"], ["metric"])
        self.assertEqual(final["mode"], "local_double")
        self.assertIsNone(final["metrics"]["actual_cost_usd"])
        self.assertTrue(all(e["mode"] == "local_double" for e in inspect(self.output)["events"]))

    def test_scope_and_private_requests_have_empty_physical_projection(self):
        for index in (12, 13, 17):
            case, data, label = build("development", index, DEVELOPMENT[index])
            self.output = Path(self.temp.name)/f"denied-{index}"
            _, final = self.complete(case, data, label)
            self.assertEqual(inspect(self.output)["rows"]["orders"], [])
            self.assertEqual(final["host_counters"]["candidates"], 0)

    def test_pending_proposal_has_no_query_and_baseline_event_identity(self):
        case, data, label = build("development", 5, DEVELOPMENT[5])
        first = start(out=self.output, provider=DeterministicProvider(), **actor_input(case, data))
        self.assertEqual(first["status"], "awaiting_confirmation")
        self.assertEqual(first["proposal"]["ambiguities"], ["periods"])
        self.assertEqual(first["query_receipts"], [])
        self.assertEqual(first["mode"], "deterministic_v2")
        self.assertTrue(all(e["mode"] == "deterministic_v2" for e in inspect(self.output)["events"]))
