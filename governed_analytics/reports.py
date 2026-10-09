"""Render numeric claims only from verified evidence and trusted context."""

import json
from decimal import Decimal, ROUND_HALF_UP


def summarize(contract, evidence, requested_ids):
    if set(requested_ids) != {item["result_id"] for item in evidence.values()} or len(requested_ids) != 2:
        raise ValueError("INVALID_EVIDENCE_REFERENCE")
    if set(evidence) != {"none", "channel"}:
        raise ValueError("MISSING_EVIDENCE")
    previous, current = contract["periods"]
    totals = {row[0]: row[2] for row in evidence["none"]["rows"] if row[1] == "all"}
    if set(totals) != {previous, current}:
        raise ValueError("MISSING_COMPARISON_PERIOD")
    delta = totals[current] - totals[previous]
    percent = None if totals[previous] == 0 else str(
        (Decimal(delta) * 100 / Decimal(totals[previous])).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
    channels = {}
    for period, group, cents in evidence["channel"]["rows"]:
        channels.setdefault(group, {})[period] = cents
    if any(set(values) != {previous, current} for values in channels.values()):
        raise ValueError("MISSING_CHANNEL_PERIOD")
    changes = {channel: values[current] - values[previous] for channel, values in channels.items()}
    if sum(changes.values()) != delta:
        raise ValueError("CHANNEL_RECONCILIATION_FAILED")
    return {"previous_cents": totals[previous], "current_cents": totals[current],
            "delta_cents": delta, "percent_change": percent, "channel_deltas_cents": changes,
            "evidence_ids": requested_ids,
            "interpretation": "Channel deltas describe arithmetic contributions; business causes are unmeasured."}


def money(cents):
    return f"USD {Decimal(cents) / 100:,.2f}"


def markdown(report):
    mode = report["provider_mode"]
    model_note = "Explicit live provider configuration; repository tests do not measure model quality." if mode == "live_model" else "Offline scripted/protocol evidence; model quality unmeasured."
    text = ["# Governed sales analysis", "", f"Status: **{report['status']}**.",
            f"Decision mode: `{mode}`. {model_note}", ""]
    if report.get("decision_fixture"):
        text.extend([f"Authored decision fault: `{report['decision_fixture']}`.", ""])
    if report["status"] == "awaiting_clarification":
        text.extend([report["clarification"]["question"], "",
                     "Choices: " + ", ".join(report["clarification"]["options"])])
    elif report["status"] == "completed":
        contract, summary = report["contract"], report["summary"]
        text.extend([f"Metric: `{contract['metric']}`; scope: {', '.join(contract['regions'])}.",
                     f"Refund cutoff (exclusive): {contract['as_of']}; order-date cohorts.", "",
                     "| Period | Verified sales |", "| --- | ---: |",
                     f"| {contract['periods'][0]} | {money(summary['previous_cents'])} |",
                     f"| {contract['periods'][1]} | {money(summary['current_cents'])} |", "",
                     f"Change: {money(summary['delta_cents'])}; percent: {str(summary['percent_change']) + '%' if summary['percent_change'] is not None else 'undefined because prior sales were zero'}.", "",
                     "| Channel | Arithmetic contribution to change |", "| --- | ---: |"])
        text.extend(f"| {group} | {money(value)} |" for group, value in summary["channel_deltas_cents"].items())
        text.extend(["", summary["interpretation"], "",
                     "Evidence: " + ", ".join(f"`{value}`" for value in summary["evidence_ids"]) + ".", "",
                     "## Executed candidate SQL", ""])
        for receipt in report["query_receipts"]:
            text.extend([f"Query `{receipt['query_id']}`: {receipt['verification']}.",
                         "```sql", receipt["sql"], "```", "Parameters:",
                         "```json", json.dumps(receipt["parameters"], sort_keys=True), "```", ""])
    else:
        text.extend([f"Reason: `{report.get('reason', 'UNSPECIFIED')}`.",
                     "No verified numeric conclusion is available."])
    text.extend(["", f"Source fingerprints unchanged: {report['source_immutability']['unchanged']}.",
                 "", "JSON includes source, catalog, schema and snapshot fingerprints, verification receipts and the tool trace."])
    return "\n".join(text) + "\n"
