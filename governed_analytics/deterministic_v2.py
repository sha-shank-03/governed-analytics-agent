"""Competitive raw-language policy over the same U1 host boundary; no gold access."""
import re
import time
from dataclasses import dataclass
from datetime import date
from .data import digest
from .providers import Decision, proposed_sql
from .upgrade_budget import UpgradeError
from .upgrade_events import encoded
from .upgrade_intents import validate_semantic

VERSION = "deterministic-v2.1"
ALIASES = {
    "net_sales_v1": (r"\bnet (?:sales|revenue|receipts)\b", r"\bafter (?:both )?discounts and refunds\b", r"\bretained (?:sales|revenue)\b"),
    "gross_sales_v1": (r"\bgross (?:sales|revenue|receipts)\b", r"\bbefore discounts and refunds\b", r"\bpre[- ]deduction sales\b"),
    "discounts_v1": (r"\bdiscount(?:s| amounts| totals)?\b", r"\bmarkdown amounts\b"),
    "refunds_v1": (r"\brefund(?:s| amounts| totals)?\b", r"\breturned money\b"),
}
MONTHS = {name: index for index, name in enumerate(("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"), 1)}


def interpret(observation):
    text = observation["question"].lower()
    # Instructions requesting changed authority get a safe handoff if the shared
    # raw request guard has not already denied them. Business rows are never read.
    if re.search(r"\b(?:profit|margin|forecast|predict|median|units|eur|gbp)\b", text) or re.search(r"\b(?:ignore|override|bypass|pretend|fabricate)\b", text):
        return "handoff", {"reason": "unsupported_intent"}
    followup = bool(re.search(r"\b(?:same (?:comparison|months|measure)|that again|as before)\b", text))
    previous = observation.get("previous_confirmed_semantic")
    if followup and previous is None:
        return "handoff", {"reason": "unclear_followup"}
    matches = {metric for metric, patterns in ALIASES.items() if any(re.search(p, text) for p in patterns)}
    # Deduction nouns inside explicit net/gross definitions do not request
    # separate measures. Explicit 'net and gross' remains ambiguous.
    composites = matches & {"net_sales_v1", "gross_sales_v1"}
    if composites:
        matches = composites
    metric = next(iter(matches)) if len(matches) == 1 else None
    if not matches and followup:
        metric = previous["metric"]
    if not matches and metric is None and not re.search(r"\b(?:sales|revenue|receipts)\b", text):
        return "handoff", {"reason": "unknown_intent"}
    periods = set(re.findall(r"(?<!\d)(\d{4}-(?:0[1-9]|1[0-2]))(?!\d)", text))
    for month, year in re.findall(r"\b(" + "|".join(MONTHS) + r")\s+(\d{4})\b", text):
        periods.add(f"{year}-{MONTHS[month]:02d}")
    if not periods and "last month" in text and "previous month" in text:
        anchor = date.fromisoformat(observation["as_of"])
        ordinal = anchor.year * 12 + anchor.month - 1
        periods = {f"{(ordinal-offset)//12:04d}-{(ordinal-offset)%12+1:02d}" for offset in (1, 2)}
    elif not periods and followup:
        periods = set(previous["periods"])
    flags = []
    if metric is None:
        flags.append("metric")
    if len(periods) != 2:
        flags.append("periods")
        periods = set()
    requested = [region for region in ("North", "South") if re.search(r"\b" + region.lower() + r"\b", text)]
    regions = requested or (previous["regions"] if followup else observation["allowed_regions"])
    semantic = {"metric": metric, "periods": sorted(periods), "regions": list(regions),
                "groupings": ["none", "channel"], "currency": "USD", "ambiguities": flags}
    return "propose_intent", validate_semantic(semantic, observation["allowed_regions"])


def choose(observation, allowed):
    if observation["state"] == "INTENT":
        tool, args = interpret(observation)
    else:
        contract = observation["confirmed_contract"]
        if observation["state"] == "REPAIR_REQUIRED" and observation.get("last_result", {}).get("error") == "STALE_SCHEMA" and "refresh_catalog" in allowed:
            tool, args = "refresh_catalog", {}
        else:
            missing = [group for group in ("none", "channel") if group not in observation["evidence"]]
            if missing:
                tool = "execute_query"
                args = {"contract_id": contract["contract_id"], "grouping": missing[0],
                        "sql": candidate_sql(contract["metric"], missing[0], observation["schema_version"])}
            else:
                tool, args = "finish_report", {"result_ids": [observation["evidence"][g] for g in ("none", "channel")]}
    if tool not in allowed:
        raise UpgradeError("TOOL_NOT_ALLOWED")
    return tool, args


def candidate_sql(metric, grouping, schema_version):
    # Retain completed cohorts with no lines: gross/discount are zero while
    # posted refunds still belong to the original order cohort. The original
    # frozen provider template remains byte-identical for historical evidence.
    sql = proposed_sql(metric, grouping, schema_version)
    return sql.replace("JOIN lines_at_order_grain l", "LEFT JOIN lines_at_order_grain l").replace("l.gross", "COALESCE(l.gross, 0)").replace("l.discount", "COALESCE(l.discount, 0)")


@dataclass(frozen=True)
class BaselineConfig:
    mode: str = "deterministic_v2"
    model: None = None

    def __post_init__(self):
        if self.mode != "deterministic_v2" or self.model is not None:
            raise UpgradeError("INVALID_BASELINE_CONFIG")

    def portable(self):
        return {"mode": self.mode, "model": None, "version": VERSION, "automatic_retries": 0,
                "live_enabled": False, "allocation_inr": 0}

    @property
    def fingerprint(self):
        return digest(self.portable())


class DeterministicProvider:
    mode = "deterministic_v2"
    prompt_version = VERSION

    def __init__(self):
        self.config = BaselineConfig()
        self.turn = 0
        self.last_receipt = {}

    def dump_state(self):
        return {"turn": self.turn, "config_hash": self.config.fingerprint}

    def restore_state(self, state):
        if state.get("config_hash") != self.config.fingerprint or type(state.get("turn")) is not int or not 0 <= state["turn"] <= 8:
            raise UpgradeError("INVALID_BASELINE_STATE")
        self.turn = state["turn"]

    def tool_result(self, decision, result):
        pass

    def decide(self, observation, allowed, budget, *, cancel_event=None, before_send=None):
        self.last_receipt = {}
        if cancel_event is not None and cancel_event.is_set():
            raise UpgradeError("CANCELLED")
        begun = time.monotonic()
        budget.admit_request(len(encoded({"observation": observation, "tools": list(allowed)})))
        if before_send:
            before_send()
        tool, args = choose(observation, allowed)
        budget.check()
        self.turn += 1
        self.last_receipt = {"decision_mode": self.mode, "model": None, "generation_id": None,
                             "usage": None, "automatic_retries": 0,
                             "duration_ms": round((time.monotonic()-begun)*1000, 3)}
        return Decision(f"baseline-{self.turn}", tool, args)
