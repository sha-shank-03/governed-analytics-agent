"""Bounded language slots; unresolved meaning cannot be supplied by a provider."""

import re
from datetime import date
from .data import digest, load_policy

MONTHS = {name: f"{number:02d}" for number, name in enumerate(
    ("january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"), 1)}


def resolve_request(question, identity, reference_date=None):
    grants = load_policy()["grants"]
    if identity not in grants:
        raise ValueError("Unknown simulated identity")
    text = question.lower()
    regions = grants[identity]
    if any(word in text for word in ("customer", "email", "private", "payroll")):
        return {"denied": True, "reason": "PRIVATE_DATA_REQUEST", "regions": regions}
    requested = ("North", "South") if any(term in text for term in (
        "all-region", "all region", "company-wide", "company wide", "both regions")) else tuple(
        region for region in ("North", "South") if region.lower() in text)
    if requested and not set(requested).issubset(regions):
        return {"denied": True, "reason": "SCOPE_NOT_GRANTED", "regions": regions}
    regions = requested or regions
    if "prove" in text and "caused" in text:
        return {"denied": False, "insufficient_evidence": True,
                "reason": "CAUSAL_EVIDENCE_UNAVAILABLE", "regions": list(regions)}
    named = {f"{year}-{MONTHS[month]}" for month, year in re.findall(
        r"\b(" + "|".join(MONTHS) + r")\s+(\d{4})\b", text)}
    named.update(re.findall(r"\b(\d{4}-(?:0[1-9]|1[0-2]))\b", text))
    if not named and "last month" in text and "previous month" in text and reference_date:
        anchor = date.fromisoformat(reference_date)
        ordinal = anchor.year * 12 + anchor.month - 1
        named = {f"{(ordinal-offset)//12:04d}-{(ordinal-offset)%12+1:02d}" for offset in (1, 2)}
    periods = sorted(named)
    if len(periods) != 2:
        raise ValueError("Requires two explicit months, or last/previous month with a fixture reference date")
    for period in periods:
        date.fromisoformat(period + "-01")
    metric = None
    choices = []
    if re.search(r"\bnet\b", text):
        choices.append("net_sales_v1")
    if re.search(r"\bgross\b", text):
        choices.append("gross_sales_v1")
    if len(choices) == 1:
        metric = choices[0]
    elif not any(word in text for word in ("revenue", "sales")):
        raise ValueError("Supports gross/net sales questions")
    return {"denied": False, "regions": list(regions), "periods": periods,
            "metric": metric, "metric_origin": "explicit_question" if metric else None}


def make_contract(slots, catalog, fingerprints, as_of, schema_hash, snapshot_hash):
    if slots["metric"] not in catalog["measures"]:
        raise ValueError("Metric is unresolved or unsupported")
    contract = {"metric": slots["metric"], "metric_origin": slots["metric_origin"],
                "periods": slots["periods"], "regions": slots["regions"],
                "currency": "USD", "as_of": as_of, "catalog_hash": fingerprints["catalog.json"],
                "policy_hash": fingerprints.get("policies.json"),
                "schema_hash": schema_hash, "snapshot_hash": snapshot_hash,
                "groupings": ["none", "channel"]}
    return {**contract, "contract_id": digest(contract)}
