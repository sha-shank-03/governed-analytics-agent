"""Untrusted proposals are slots, never permissions or executable formulas."""
import re
from datetime import date
from .data import digest, load_policy
from .upgrade_budget import UpgradeError

MEASURES = ("gross_sales_v1", "discounts_v1", "refunds_v1", "net_sales_v1")
FIELDS = {"metric", "periods", "regions", "groupings", "currency", "ambiguities"}
AMBIGUITIES = ("metric", "periods", "grouping", "followup", "unsupported")


def request_guard(question, identity):
    grants = load_policy()["grants"]
    if identity not in grants:
        raise UpgradeError("IDENTITY_NOT_GRANTED")
    if type(question) is not str or not question.strip() or len(question.encode("utf-8")) > 4096:
        raise UpgradeError("INVALID_QUESTION")
    text = question.lower()
    if any(word in text for word in ("customer", "email", "private", "payroll")):
        raise UpgradeError("PRIVATE_DATA_REQUEST")
    requested = {region for region in ("North", "South") if region.lower() in text}
    if any(term in text for term in ("company-wide", "company wide", "all region", "both regions")):
        requested = {"North", "South"}
    if not requested.issubset(grants[identity]):
        raise UpgradeError("SCOPE_NOT_GRANTED")
    if any(word in text for word in ("caused", "causal", "causation")):
        raise UpgradeError("CAUSAL_EVIDENCE_UNAVAILABLE")
    return grants[identity]


def validate_semantic(value, grant, *, confirmed=False):
    if type(value) is not dict or set(value) != FIELDS:
        raise UpgradeError("INVALID_INTENT_FIELDS")
    if value["metric"] is not None and (type(value["metric"]) is not str or value["metric"] not in MEASURES):
        raise UpgradeError("UNSUPPORTED_MEASURE")
    periods = value["periods"]
    if type(periods) is not list or len(periods) not in (0, 2):
        raise UpgradeError("INVALID_PERIODS")
    if periods:
        if any(type(p) is not str or not re.fullmatch(r"\d{4}-(?:0[1-9]|1[0-2])", p) for p in periods):
            raise UpgradeError("INVALID_PERIODS")
        try:
            for p in periods:
                date.fromisoformat(p + "-01")
        except ValueError:
            raise UpgradeError("INVALID_PERIODS") from None
        if periods != sorted(set(periods)) or len(set(periods)) != 2:
            raise UpgradeError("INVALID_PERIODS")
    regions = value["regions"]
    if type(regions) is not list or not regions or any(type(r) is not str for r in regions):
        raise UpgradeError("INVALID_REGIONS")
    if len(set(regions)) != len(regions) or not set(regions).issubset(grant):
        raise UpgradeError("SCOPE_NOT_GRANTED")
    # Completion requires both totals and channel reconciliation, as in the MVP.
    if value["groupings"] != ["none", "channel"] or value["currency"] != "USD":
        raise UpgradeError("UNSUPPORTED_GROUPING_OR_CURRENCY")
    flags = value["ambiguities"]
    if type(flags) is not list or any(type(f) is not str or f not in AMBIGUITIES for f in flags):
        raise UpgradeError("INVALID_AMBIGUITIES")
    if len(flags) != len(set(flags)) or len(flags) > 5:
        raise UpgradeError("INVALID_AMBIGUITIES")
    if confirmed and (value["metric"] is None or not periods or flags):
        raise UpgradeError("INTENT_REQUIRES_CLARIFICATION")
    return value


def proposal_receipt(semantic, state):
    full = {**semantic, "as_of": state["as_of"],
            "measure_definition": state["catalog"]["measures"].get(semantic["metric"]),
            "source_cutoff_rule": "posted refunds before as_of; original completed-order cohort",
            "binding": {key: state[key] for key in ("request_hash", "config_hash", "code_hash",
                        "source_fingerprints", "schema_hash", "snapshot_hash")}}
    return {**full, "proposal_id": digest(full)}


def confirm(receipt, answer, state):
    if type(answer) is not dict or set(answer) != {"proposal_id", "semantic"}:
        raise UpgradeError("INVALID_CONFIRMATION_FIELDS")
    if answer["proposal_id"] != receipt["proposal_id"]:
        raise UpgradeError("STALE_CONFIRMATION")
    current = proposal_receipt({key: receipt[key] for key in FIELDS}, state)
    if current != receipt:
        raise UpgradeError("CONFIRMATION_CONTEXT_CHANGED")
    semantic = validate_semantic(answer["semantic"], state["grant"], confirmed=True)
    # Human correction may select catalog slots; definitions/cutoff/scope are host-owned.
    return semantic
