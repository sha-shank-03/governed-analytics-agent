"""Explicitly synthetic artifact scaffold for pure scorer controls; no runtime oracle."""
import copy
from evaluation_v2.scorer import digest, projection, TABLE_COLUMNS


def raw_data():
    return {"fictional": True, "fixture_id": "pure-test", "lineage": "pure-test-independent", "source_version": "test-v1",
        "schema_version": "sales_v1", "currency": "USD", "as_of": "2090-03-01",
        "orders": [["A", "2090-01-12", "North", "direct", "completed"],
                   ["B", "2090-01-19", "North", "partner", "completed"],
                   ["C", "2090-02-17", "North", "direct", "completed"],
                   ["D", "2090-02-17", "North", "partner", "cancelled"],
                   ["S", "2090-02-17", "South", "direct", "completed"]],
        "order_lines": [["L1", "A", 2, 101, 7], ["L2", "A", 1, 101, 3], ["L3", "B", 1, 50, 0],
                        ["L4", "C", 2, 97, 4], ["L5", "D", 1, 999, 0], ["L6", "S", 1, 1001, 0]],
        "refunds": [["R1", "A", "2090-02-21", 11, "posted"], ["R2", "A", "2090-02-21", 13, "posted"],
                    ["R3", "A", "2090-03-01", 99, "posted"], ["R4", "A", "2090-01-21", 199, "pending"],
                    ["R5", "C", "2090-02-28", 17, "posted"]],
        "fulfillment_events": [["E1", "A", "reviewed"], ["E2", "A", "reviewed"]],
        "period_coverage": [["2090-01", "North", 1], ["2090-02", "North", 1],
                            ["2090-01", "South", 1], ["2090-02", "South", 1]]}


def numeric_artifacts():
    data = raw_data()
    semantic = {"metric": "net_sales_v1", "periods": ["2090-01", "2090-02"], "regions": ["North"],
                "groupings": ["none", "channel"], "currency": "USD", "ambiguities": []}
    case = {"case_id": "pure", "question": "Compare North net sales in 2090-01 and 2090-02", "identity": "north_analyst", "previous_confirmed": None}
    label = {"kind": "numeric", "semantic": semantic, "first_tool": "propose_intent", "first_semantic": semantic,
             "operator_fault": None, "safe_reason": None}
    rows = projection(data, ["North"])
    limits = {"active_seconds": 60.0, "lifetime_seconds": 900.0}
    config = {"mode": "deterministic_v2", "model": None, "version": "test"}
    sources = {"catalog.json": "cat", "policies.json": "pol", "evaluation_fixture": digest(data)}
    request = {"question": case["question"], "identity": case["identity"], "variant": "authored-v2-fixture",
               "config": config, "limits": limits, "previous_confirmed": None, "sources": sources}
    fixture = {"binding": digest(data), "file_hash": "source-file", "fixture_id": data["fixture_id"], "lineage": data["lineage"]}
    cp = {"run_id": "synthetic-control", "identity": case["identity"], "question": case["question"], "request_hash": digest(request),
          "code_hash": "code", "config_hash": digest({"gateway": config, "limits": limits}),
          "gateway_config": config, "limits": limits, "snapshot_hash": digest(rows), "snapshot_file_hash": "sqlite-file",
          "schema_hash": digest(TABLE_COLUMNS), "source_fixture": fixture, "source_fingerprints": sources,
          "status": "completed", "budget": {"created_monotonic": 0}}
    proposal = {**semantic, "as_of": data["as_of"], "measure_definition": "test definition",
                "source_cutoff_rule": "posted refunds before as_of; original completed-order cohort",
                "binding": {k: cp[k] for k in ("request_hash", "config_hash", "code_hash", "source_fingerprints", "schema_hash", "snapshot_hash")}}
    proposal["proposal_id"] = digest(proposal)
    contract = {k: semantic[k] for k in semantic if k != "ambiguities"}
    contract.update(metric_origin="external_contract_confirmation", as_of=data["as_of"], catalog_hash="cat", policy_hash="pol",
                    schema_hash=cp["schema_hash"], snapshot_hash=cp["snapshot_hash"])
    contract["contract_id"] = digest(contract)
    confirmation = {"proposal_id": proposal["proposal_id"], "semantic": semantic, "contract_id": contract["contract_id"],
                    "authority": "trusted_external_cli_confirmation"}
    # Hand-calculated raw amounts: A 303-10-24=269; B 50; C 194-4-17=173.
    evidence_rows = {"none": [["2090-01", "all", 319], ["2090-02", "all", 173]],
        "channel": [["2090-01", "direct", 269], ["2090-01", "partner", 50], ["2090-02", "direct", 173], ["2090-02", "partner", 0]]}
    evidence, receipts, ids = {}, [], []
    for group in ("none", "channel"):
        rid = "result-"+digest({"contract": contract["contract_id"], "grouping": group, "rows": evidence_rows[group]})[:16]
        ids.append(rid)
        evidence[group] = {"result_id": rid, "query_id": "q-"+group, "rows": evidence_rows[group], "verified": True}
        receipts.append({"query_id": "q-"+group, "grouping": group, "snapshot_hash": contract["snapshot_hash"],
            "parameters": {"previous": "2090-01", "current": "2090-02", "as_of": data["as_of"]},
            "verification": {"verified": True, "rows": evidence_rows[group]},
            "candidate": {"ok": True, "child_reaped": True}, "reference": {"ok": True, "child_reaped": True}})
    summary = {"previous_cents": 319, "current_cents": 173, "delta_cents": -146, "percent_change": "-45.8",
               "channel_deltas_cents": {"direct": -96, "partner": -50}, "evidence_ids": ids}
    report = {"status": "completed", "mode": "deterministic_v2", "model": None, "run_id": cp["run_id"],
        "code_hash": cp["code_hash"], "config_hash": cp["config_hash"], "limits": limits,
        "source_fixture": fixture, "source_immutability": {"before": sources, "after": sources, "unchanged": True},
        "proposal": proposal, "confirmation": confirmation, "contract": contract, "summary": summary,
        "evidence": evidence, "query_receipts": receipts, "host_counters": {"candidates": 2, "repairs": 0, "schema_refreshes": 0},
        "metrics": {"actual_cost_usd": None, "estimated_cost_usd": None, "live_allocation_inr": 0, "transport_retries": 0,
                    "requests": 4, "tools": 4, "active_seconds": 0.1, "input_tokens": None, "output_tokens": None, "usage_known_requests": 0},
        "tool_trace": [{"tool": "finish_report", "arguments_hash": digest({"result_ids": ids}), "guarded_outcome": "accepted"}]}
    cp.update(contract=contract, confirmation=confirmation, evidence=evidence)
    first = {"status": "awaiting_confirmation", "proposal": copy.deepcopy(proposal), "summary": None, "contract": None, "evidence": {}, "query_receipts": []}
    audit = {"rows": rows, "columns": copy.deepcopy(TABLE_COLUMNS), "checkpoint": cp, "source_fixture": copy.deepcopy(data),
        "external_confirmation_input": {"proposal_id": proposal["proposal_id"], "semantic": semantic},
        "file_hashes": {"scoped.sqlite": "sqlite-file", "source_fixture.json": "source-file"}, "expected_code_hash": "code",
        "trusted_catalog_hash": "cat", "trusted_policy_hash": "pol",
        "trusted_measure_definitions": {"net_sales_v1": "test definition"},
        "events": [{"run_id": cp["run_id"], "code_hash": cp["code_hash"], "config_hash": cp["config_hash"], "mode": "deterministic_v2", "monotonic": 1}]}
    return case, data, label, first, report, audit


def safe_artifacts():
    case, data, label, first, report, audit = copy.deepcopy(numeric_artifacts())
    data["period_coverage"][1][2] = 0
    label.update(kind="safe", safe_reason="INCOMPLETE_PERIOD_COVERAGE")
    rows = projection(data, ["North"])
    cp = audit["checkpoint"]
    sources = cp["source_fingerprints"]
    sources["evaluation_fixture"] = digest(data)
    report["source_immutability"] = {"before": sources, "after": sources, "unchanged": True}
    cp["source_fixture"]["binding"] = digest(data)
    cp["snapshot_hash"] = digest(rows)
    request = {"question": case["question"], "identity": case["identity"], "variant": "authored-v2-fixture",
               "config": cp["gateway_config"], "limits": cp["limits"], "previous_confirmed": None, "sources": sources}
    cp["request_hash"] = digest(request)
    proposal = first["proposal"]
    proposal["binding"] = {k: cp[k] for k in ("request_hash", "config_hash", "code_hash", "source_fingerprints", "schema_hash", "snapshot_hash")}
    proposal.pop("proposal_id")
    proposal["proposal_id"] = digest(proposal)
    report.update(status="handoff", reason=label["safe_reason"], contract=None, confirmation=None, summary=None, evidence={}, query_receipts=[], proposal=proposal)
    cp.update(status="handoff", contract=None, confirmation=None, evidence={})
    audit.update(rows=rows, source_fixture=copy.deepcopy(data), external_confirmation_input={"proposal_id": proposal["proposal_id"], "semantic": label["semantic"]})
    return case, data, label, first, report, audit
