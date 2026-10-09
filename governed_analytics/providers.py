"""Explicit decision boundary. M1 uses authored policies, never live inference."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Decision:
    call_id: str
    tool: str
    arguments: dict


class Provider(Protocol):
    mode: str
    decision_fixture: str | None

    def decide(self, observation: dict, allowed_tools: tuple[str, ...], remaining_budget: dict) -> Decision:
        ...


def proposed_sql(metric, grouping, schema_version="sales_v1"):
    # This authored proposal is separate from the runtime reference implementation.
    formulas = {"gross_sales_v1": "l.gross", "discounts_v1": "l.discount",
                "refunds_v1": "COALESCE(r.refund, 0)",
                "net_sales_v1": "l.gross - l.discount - COALESCE(r.refund, 0)"}
    group = "o.channel" if grouping == "channel" else "'all'"
    price = "unit_amount_cents" if schema_version == "sales_v2" else "unit_price_cents"
    groups = "SELECT 'direct' AS group_key UNION ALL SELECT 'partner'" if grouping == "channel" else "SELECT 'all' AS group_key"
    join = "AND values_by_group.group_key = g.group_key" if grouping == "channel" else ""
    return f"""WITH lines_at_order_grain AS (
  SELECT order_id, SUM(quantity * {price}) AS gross,
         SUM(discount_cents) AS discount FROM order_lines GROUP BY order_id
), refunds_at_order_grain AS (
  SELECT order_id, SUM(amount_cents) AS refund FROM refunds
  WHERE status = 'posted' AND posted_date < :as_of GROUP BY order_id
), values_by_group AS (
SELECT substr(o.order_date, 1, 7) AS period_key, {group} AS group_key,
       SUM({formulas[metric]}) AS value_cents
FROM orders o JOIN lines_at_order_grain l ON l.order_id = o.order_id
LEFT JOIN refunds_at_order_grain r ON r.order_id = o.order_id
WHERE o.status = 'completed' AND substr(o.order_date, 1, 7) IN (:previous, :current)
GROUP BY period_key, group_key
), periods AS (
  SELECT DISTINCT period_key FROM period_coverage WHERE complete=1 AND period_key IN (:previous, :current)
), groups AS ({groups})
SELECT p.period_key AS period_key, g.group_key AS group_key,
       COALESCE(values_by_group.value_cents, 0) AS value_cents
FROM periods p CROSS JOIN groups g LEFT JOIN values_by_group
ON values_by_group.period_key = p.period_key {join}
ORDER BY p.period_key, g.group_key"""


FANOUT_SQL = """SELECT substr(o.order_date, 1, 7) AS period_key, 'all' AS group_key,
SUM(l.quantity * l.unit_price_cents - l.discount_cents - COALESCE(r.amount_cents, 0)) AS value_cents
FROM orders o JOIN order_lines l ON l.order_id = o.order_id
LEFT JOIN refunds r ON r.order_id = o.order_id AND r.status = 'posted' AND r.posted_date < :as_of
WHERE o.status = 'completed' AND substr(o.order_date, 1, 7) IN (:previous, :current)
GROUP BY period_key, group_key ORDER BY period_key, group_key"""


class ScriptedProvider:
    mode = "scripted_policy"
    decision_fixture = None

    def dump_state(self):
        return {}

    def restore_state(self, value):
        pass

    def decide(self, observation, allowed_tools, remaining_budget):
        state = observation["state"]
        call_id = f"call-{observation['turn'] + 1}"
        if state == "RECEIVED":
            return Decision(call_id, "describe_catalog", {})
        if state == "CATALOG_READY":
            if observation["metric"] is None:
                return Decision(call_id, "request_clarification", {"slot": "metric"})
            return Decision(call_id, "submit_plan", {"metric": observation["metric"],
                                                      "groupings": observation.get("groupings", ["none", "channel"])})
        if state in ("PLAN_READY", "REPAIR_REQUIRED", "VERIFIED"):
            if state == "REPAIR_REQUIRED" and observation.get("last_result", {}).get("error") == "STALE_SCHEMA" and "refresh_catalog" in allowed_tools:
                return Decision(call_id, "refresh_catalog", {})
            missing = [group for group in observation.get("groupings", ["none", "channel"]) if group not in observation["evidence"]]
            if missing:
                return Decision(call_id, "execute_query", {
                    "contract_id": observation["contract_id"], "grouping": missing[0],
                    "sql": proposed_sql(observation["metric"], missing[0], observation.get("schema_version", "sales_v1"))})
            return Decision(call_id, "finish_report", {"result_ids": list(observation["evidence"].values())})
        raise ValueError("No scripted decision for state")


class FanoutChallengeProvider(ScriptedProvider):
    """Authored fault at the decision boundary; no case ID or gold answer is read."""

    mode = "scripted_policy_with_authored_fault"
    decision_fixture = "initial_net_join_fanout"

    def __init__(self):
        self.injected = False

    def dump_state(self):
        return {"injected": self.injected}

    def restore_state(self, value):
        self.injected = value.get("injected", False)

    def decide(self, observation, allowed_tools, remaining_budget):
        decision = super().decide(observation, allowed_tools, remaining_budget)
        if decision.tool == "execute_query" and observation["metric"] == "net_sales_v1" and not self.injected:
            self.injected = True
            return Decision(decision.call_id, decision.tool, {**decision.arguments, "sql": FANOUT_SQL})
        return decision


class FaultProvider(FanoutChallengeProvider):
    """Named authored perturbations, not evaluation answers or model recordings."""
    mode = "authored_replay"

    def __init__(self, fault):
        super().__init__()
        if fault not in ("fanout", "distinct", "stale_schema", "forged_evidence", "always_fanout",
                         "events_fanout", "inner_refunds", "semantic_version", "forged_contract",
                         "claim_value", "claim_cause", "claim_scope"):
            raise ValueError("UNKNOWN_AUTHORED_FAULT")
        self.fault = fault
        self.decision_fixture = fault

    def decide(self, observation, allowed_tools, remaining_budget):
        decision = ScriptedProvider.decide(self, observation, allowed_tools, remaining_budget)
        if decision.tool == "submit_plan" and self.fault == "semantic_version" and not self.injected:
            self.injected = True
            return Decision(decision.call_id, decision.tool, {**decision.arguments, "metric": "net_sales_v999"})
        if decision.tool == "execute_query" and self.fault == "forged_contract" and not self.injected:
            self.injected = True
            return Decision(decision.call_id, decision.tool, {**decision.arguments, "contract_id": "forged-catalog-contract"})
        if decision.tool == "finish_report" and self.fault in ("claim_value", "claim_cause", "claim_scope") and not self.injected:
            self.injected = True
            field, value = {"claim_value": ("claimed_value_cents", 999999999),
                            "claim_cause": ("claimed_cause", "A campaign caused the change"),
                            "claim_scope": ("claimed_scope", "company-wide")}[self.fault]
            return Decision(decision.call_id, decision.tool, {**decision.arguments, field: value})
        if decision.tool == "execute_query" and self.fault in ("fanout", "always_fanout", "events_fanout", "inner_refunds", "distinct", "stale_schema") and (not self.injected or self.fault == "always_fanout"):
            self.injected = True
            sql = decision.arguments["sql"]
            if self.fault in ("fanout", "always_fanout"):
                sql = FANOUT_SQL
            elif self.fault == "events_fanout":
                sql = FANOUT_SQL.replace("LEFT JOIN refunds r", "JOIN fulfillment_events f ON f.order_id=o.order_id LEFT JOIN refunds r")
            elif self.fault == "inner_refunds":
                sql = sql.replace("LEFT JOIN refunds_at_order_grain", "JOIN refunds_at_order_grain")
            elif self.fault == "distinct":
                sql = sql.replace("SUM(quantity * unit_price_cents)", "SUM(DISTINCT quantity * unit_price_cents)")
            elif self.fault == "stale_schema":
                sql = sql.replace("unit_amount_cents", "unit_price_cents")
            return Decision(decision.call_id, decision.tool, {**decision.arguments, "sql": sql})
        if decision.tool == "finish_report" and self.fault == "forged_evidence":
            self.injected = True
            return Decision(decision.call_id, decision.tool, {"result_ids": ["invented", "invented"]})
        return decision
