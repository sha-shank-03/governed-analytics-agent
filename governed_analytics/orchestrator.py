"""Single bounded decision/tool loop with host-owned authority and verification."""

import hashlib
import copy
import json
import time
import uuid
from pathlib import Path
from .catalog import make_contract, resolve_request
from .data import (create_projection, digest, load_catalog, load_fixture, schema_fingerprint,
                   scoped_rows, source_fingerprints, tables_for_schema)
from .providers import Decision, ScriptedProvider, FanoutChallengeProvider, FaultProvider
from .execution import run_sql
from .state import atomic_json, run_lock, read_checkpoint, check_request_reuse, check_context
from .reports import markdown, summarize
from .verification import compare, reference_sql

TOOLS = {
    "RECEIVED": ("describe_catalog",),
    "CATALOG_READY": ("request_clarification", "submit_plan"),
    "PLAN_READY": ("execute_query",),
    "REPAIR_REQUIRED": ("execute_query", "refresh_catalog"),
    "VERIFIED": ("execute_query", "finish_report"),
}
ARGUMENTS = {"describe_catalog": set(), "refresh_catalog": set(), "request_clarification": {"slot"},
             "submit_plan": {"metric", "groupings"},
             "execute_query": {"contract_id", "grouping", "sql"},
             "finish_report": {"result_ids"}}


def validate_decision(decision, allowed):
    if not isinstance(decision, Decision) or decision.tool not in allowed:
        raise ValueError("TOOL_NOT_ALLOWED")
    if not isinstance(decision.call_id, str) or not 1 <= len(decision.call_id) <= 100:
        raise ValueError("INVALID_CALL_ID")
    if type(decision.arguments) is not dict or set(decision.arguments) != ARGUMENTS[decision.tool]:
        raise ValueError("INVALID_ARGUMENT_FIELDS")
    if len(json.dumps(decision.arguments, allow_nan=False).encode()) > 40000:
        raise ValueError("ARGUMENTS_TOO_LARGE")


write_json = atomic_json


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Session:
    def __init__(self, out, state, provider, cancel_event=None):
        self.out = Path(out)
        self.state = state
        self.provider = provider
        self.started = time.monotonic()
        self.last_tick = self.started
        self.cancel_event = cancel_event

    def remaining_seconds(self):
        return max(0, 60 - self.state.get("active_seconds", 0) - time.monotonic() + self.last_tick)

    def save(self):
        now = time.monotonic()
        self.state["active_seconds"] = self.state.get("active_seconds", 0) + now - self.last_tick
        self.last_tick = now
        self.state["provider_state"] = self.provider.dump_state() if hasattr(self.provider, "dump_state") else {}
        write_json(self.out / "checkpoint.json", self.state)
        with (self.out / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"turn": self.state["turn"], "state": self.state["state"],
                                     "status": self.state["status"]}) + "\n")

    def finish(self, status, reason=None, summary=None):
        before = self.state["source_fingerprints"]
        after = source_fingerprints()
        unchanged = before == after
        if not unchanged:
            status, reason, summary = "failed", reason or "SOURCE_CHANGED", None
        report = {"status": status, "reason": reason, "provider_mode": self.state["provider_mode"],
                  "run_id": self.state.get("run_id"), "workflow_mode": self.state.get("workflow_mode", "governed"),
                  "decision_fixture": self.state["decision_fixture"],
                  "contract": self.state.get("contract"), "summary": summary,
                  "clarification": self.state.get("clarification"),
                  "evidence": self.state["evidence"], "query_receipts": self.state["query_receipts"],
                  "tool_trace": self.state["trace"],
                  "source_immutability": {"before": before, "after": after, "unchanged": unchanged},
                  "budgets": {"turns_used": self.state["turn"], "candidate_sql_used": self.state["attempts"],
                              "reference_sql_used": self.state["reference_queries"], "repairs_used": self.state["repairs"],
                              "schema_refreshes": self.state.get("schema_refreshes", 0),
                              "report_rejections": self.state.get("report_rejections", 0)},
                  "baseline_candidate": self.state.get("baseline_candidate"),
                  "provider_usage": getattr(self.provider, "usage", None),
                  "limitations": ["Authored fictional fixture; repository tests do not measure live model quality.",
                                  "Static demo identities are not production authentication.",
                                  "Verification covers four catalog measures on this snapshot."]}
        self.state["status"] = status
        self.state["final_reason"], self.state["final_summary"] = reason, summary
        self.save()
        # Return the persisted JSON representation, detached from mutable checkpoint state.
        report = json.loads(json.dumps(report, allow_nan=False))
        write_json(self.out / "report.json", report)
        (self.out / "report.md").write_text(markdown(report), encoding="utf-8")
        return report

    def drive(self):
        while self.state["turn"] < 12:
            if self.cancel_event is not None and self.cancel_event.is_set():
                return self.finish("cancelled", "CANCELLED")
            if self.state.get("active_seconds", 0) + time.monotonic() - self.last_tick > 60:
                return self.finish("budget_exhausted", "RUN_TIMEOUT")
            if source_fingerprints() != self.state["source_fingerprints"]:
                return self.finish("failed", "SOURCE_CHANGED")
            state = self.state["state"]
            observation = {"state": state, "turn": self.state["turn"],
                           "question": self.state["question"], "metric": self.state["slots"].get("metric"),
                           "catalog": self.state["catalog"] if state != "RECEIVED" else None,
                           "schema": self.state["schema"] if state != "RECEIVED" else None,
                           "periods": self.state["slots"].get("periods"),
                           "schema_version": self.state.get("schema_version", "sales_v1"),
                           "groupings": self.state.get("groupings", ["none", "channel"]),
                           "scope": self.state["slots"]["regions"],
                           "contract_id": self.state.get("contract", {}).get("contract_id"),
                           "evidence": {group: entry["result_id"] for group, entry in self.state["evidence"].items()},
                           "last_result": self.state.get("last_result")}
            allowed = TOOLS[state]
            if self.state.get("schema_refreshes", 0) >= 1:
                allowed = tuple(tool for tool in allowed if tool != "refresh_catalog")
            try:
                decision = self.provider.decide(copy.deepcopy(observation), allowed, {"turns": 12 - self.state["turn"],
                    "sql": 6 - self.state["attempts"],
                    "active_seconds": self.remaining_seconds()})
                if self.cancel_event is not None and self.cancel_event.is_set():
                    return self.finish("cancelled", "CANCELLED")
                if self.state.get("active_seconds", 0) + time.monotonic() - self.last_tick > 60:
                    return self.finish("budget_exhausted", "RUN_TIMEOUT")
                try:
                    validate_decision(decision, allowed)
                except ValueError as exc:
                    # Unsupported report fields cannot become verified prose or figures.
                    # Permit one bounded correction when the valid evidence field is present.
                    if (str(exc) == "INVALID_ARGUMENT_FIELDS" and isinstance(decision, Decision)
                        and decision.tool == "finish_report" and decision.tool in allowed
                        and type(decision.arguments) is dict and "result_ids" in decision.arguments
                        and self.state.get("report_rejections", 0) < 1):
                        self.state["report_rejections"] = self.state.get("report_rejections", 0) + 1
                        self.state["turn"] += 1
                        self.state["last_result"] = {"error": "UNSUPPORTED_REPORT_ARGUMENTS", "verified": False}
                        self.state["trace"].append({"tool": "host_report_field_check", "call_id": decision.call_id,
                            "rejected_fields": sorted(set(decision.arguments) - {"result_ids"}),
                            "result": self.state["last_result"]})
                        self.save()
                        continue
                    raise
                signature = digest({"tool": decision.tool, "arguments": decision.arguments,
                                    "sources": self.state["source_fingerprints"]})
                old_action = self.state.get("action_results", {}).get(decision.call_id)
                if old_action and old_action["signature"] != signature:
                    raise ValueError("CONFLICTING_CALL_ID")
                if decision.call_id in self.state["call_ids"] and old_action is None:
                    raise ValueError("DUPLICATE_CALL_ID")
                if decision.call_id not in self.state["call_ids"]:
                    self.state["call_ids"].append(decision.call_id)
                self.state["turn"] += 1
                record = {"call_id": decision.call_id, "tool": decision.tool,
                          "arguments": decision.arguments, "state_before": state}
                self.state["trace"].append(record)
                if old_action:
                    result = old_action["result"]
                    self.state["state"] = old_action["state_after"]
                    record["deduplicated"] = True
                else:
                    result = self.dispatch(decision.tool, decision.arguments)
                    self.state.setdefault("action_results", {})[decision.call_id] = {
                        "signature": signature, "result": result, "state_after": self.state["state"]}
                record["result"] = result
                record["state_after"] = self.state["state"]
                self.state["last_result"] = result
                self.save()
                if result.get("error") == "CANCELLED":
                    return self.finish("cancelled", "CANCELLED")
                if self.remaining_seconds() <= 0:
                    return self.finish("budget_exhausted", "RUN_TIMEOUT")
                if self.state.get("workflow_mode") == "one_pass_sql" and decision.tool == "execute_query":
                    return self.finish("experimental_unverified" if result.get("ok") else "failed", result.get("error"))
                if self.state["state"] == "NEEDS_CLARIFICATION":
                    return self.finish("awaiting_clarification")
                if decision.tool == "finish_report":
                    return self.finish("completed", summary=result)
            except (ValueError, KeyError, TypeError) as exc:
                reason = str(exc)
                return self.finish("budget_exhausted" if reason.endswith("BUDGET_EXHAUSTED") else "failed", reason)
            except KeyboardInterrupt:
                return self.finish("cancelled", "CANCELLED")
        return self.finish("budget_exhausted", "TURN_LIMIT")

    def dispatch(self, tool, args):
        if tool == "refresh_catalog":
            if self.state.get("schema_refreshes", 0) >= 1:
                raise ValueError("SCHEMA_REFRESH_LIMIT")
            self.state["schema_refreshes"] = self.state.get("schema_refreshes", 0) + 1
            self.state["state"] = "PLAN_READY"
            return {"schema": self.state["schema"], "schema_version": self.state["schema_version"]}
        if tool == "describe_catalog":
            self.state["state"] = "CATALOG_READY"
            return {"catalog": self.state["catalog"], "schema": self.state["schema"]}
        if tool == "request_clarification":
            if args["slot"] != "metric" or self.state["slots"]["metric"] is not None:
                raise ValueError("INVALID_CLARIFICATION")
            self.state["clarification"] = {"question": "Does revenue mean gross sales, or net sales after discounts and posted refunds?",
                                            "options": ["gross_sales_v1", "net_sales_v1"]}
            self.state["state"] = "NEEDS_CLARIFICATION"
            return self.state["clarification"]
        if tool == "submit_plan":
            slots = self.state["slots"]
            if slots["metric"] is None or args["metric"] != slots["metric"]:
                raise ValueError("UNRESOLVED_OR_CONFLICTING_METRIC")
            if args["groupings"] != self.state.get("groupings", ["none", "channel"]):
                raise ValueError("UNSUPPORTED_PLAN")
            self.state["contract"] = make_contract(slots, self.state["catalog"],
                self.state["source_fingerprints"], self.state["as_of"], self.state["schema_hash"], self.state["snapshot_hash"])
            self.state["contract"].pop("contract_id")
            self.state["contract"]["groupings"] = self.state.get("groupings", ["none", "channel"])
            self.state["contract"]["contract_id"] = digest(self.state["contract"])
            self.state["state"] = "PLAN_READY"
            return {"contract_id": self.state["contract"]["contract_id"]}
        if tool == "execute_query":
            if self.state["attempts"] >= 6 or self.state["repairs"] > 2:
                raise ValueError("SQL_BUDGET_EXHAUSTED")
            contract = self.state["contract"]
            group = args["grouping"]
            if args["contract_id"] != contract["contract_id"] or group not in contract["groupings"]:
                raise ValueError("INVALID_CONTRACT_ACTION")
            snapshot = self.out / "scoped.sqlite"
            if file_hash(snapshot) != self.state["snapshot_file_hash"]:
                raise ValueError("SNAPSHOT_CHANGED")
            parameters = {"previous": contract["periods"][0], "current": contract["periods"][1], "as_of": contract["as_of"]}
            self.state["attempts"] += 1
            candidate = run_sql(snapshot, args["sql"], parameters, self.state.get("schema_version", "sales_v1"),
                cancel_event=self.cancel_event, timeout=min(3, self.remaining_seconds()))
            if self.state.get("workflow_mode") == "one_pass_sql":
                self.state["baseline_candidate"] = {**candidate, "metric": contract["metric"], "grouping": group,
                                                      "verification": "unverified", "sql": args["sql"], "parameters": parameters}
                self.state["query_receipts"].append({"query_id": "query-1", "sql": args["sql"], "parameters": parameters,
                    "verification": "unverified", "child_pid": candidate.get("child_pid"), "child_reaped": candidate.get("child_reaped")})
                return candidate
            validation = {"verified": False, "error": candidate.get("error")}
            reference = None
            if candidate["ok"]:
                self.state["reference_queries"] += 1
                reference = run_sql(snapshot, reference_sql(contract["metric"], group, self.state.get("schema_version", "sales_v1")),
                    parameters, self.state.get("schema_version", "sales_v1"), cancel_event=self.cancel_event,
                    timeout=min(3, self.remaining_seconds()))
                if not reference["ok"]:
                    validation = {"verified": False, "error": "CANCELLED" if reference.get("error") == "CANCELLED" else "REFERENCE_QUERY_FAILED"}
                else:
                    validation = compare(candidate, reference)
            query_id = f"query-{self.state['attempts']}"
            receipt = {"query_id": query_id, "sql": args["sql"], "parameters": parameters,
                       "grouping": group, "duration_ms": candidate["duration_ms"],
                       "candidate_rows": candidate.get("rows", []),
                       "candidate_result_hash": digest(candidate.get("rows", [])),
                       "verification": "verified" if validation["verified"] else validation["error"],
                       "snapshot_file_hash": self.state["snapshot_file_hash"]}
            receipt.update({"child_pid": candidate.get("child_pid"), "child_reaped": candidate.get("child_reaped")})
            if reference:
                receipt["reference_execution"] = {key: reference.get(key) for key in ("duration_ms", "child_pid", "child_reaped")}
            self.state["query_receipts"].append(receipt)
            if reference and not reference["ok"]:
                if validation["error"] == "CANCELLED":
                    return {"verified": False, "error": "CANCELLED", "query_id": query_id}
                raise ValueError("REFERENCE_QUERY_FAILED")
            if not validation["verified"]:
                self.state["repairs"] += 1
                self.state["state"] = "REPAIR_REQUIRED"
                return {"verified": False, "error": validation["error"], "query_id": query_id,
                        "grain_hint": "Aggregate each child table separately at order grain."}
            result_id = "result-" + digest({"contract": contract["contract_id"], "group": group, "rows": validation["rows"]})[:16]
            self.state["evidence"][group] = {"result_id": result_id, "query_id": query_id,
                                               "rows": validation["rows"], "verified": True}
            self.state["state"] = "VERIFIED"
            return {"verified": True, **self.state["evidence"][group]}
        if tool == "finish_report":
            summary = summarize(self.state["contract"], self.state["evidence"], args["result_ids"])
            self.state["state"] = "COMPLETED"
            return summary
        raise ValueError("UNKNOWN_TOOL")


def start(question, identity, out, provider=None, *, variant="demo-v1", request_id=None,
          workflow_mode="governed", cancel_event=None):
    if workflow_mode not in ("governed", "one_pass_sql"):
        raise ValueError("UNKNOWN_WORKFLOW_MODE")
    if request_id is not None and (type(request_id) is not str or not 1 <= len(request_id) <= 128):
        raise ValueError("INVALID_REQUEST_ID")
    output, provider = Path(out), provider or ScriptedProvider()
    with run_lock(output):
        fingerprints = source_fingerprints()
        request_hash = digest({"question": question, "identity": identity, "variant": variant,
            "provider": provider.mode, "fault": provider.decision_fixture,
            "workflow_mode": workflow_mode, "sources": fingerprints, "prompt_version": "policy_v3"})
        if (output / "checkpoint.json").exists():
            prior = read_checkpoint(output)
            check_request_reuse(prior, request_id, request_hash)
            check_context(prior, fingerprints)
            if prior["status"] == "active":
                raise ValueError("ACTIVE_RUN_REQUIRES_RESUME")
            report_path = output / "report.json"
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError):
                report = None
            if report and report.get("status") == prior["status"] and report.get("run_id") == prior["run_id"]:
                return report
            # Checkpoint is authoritative if a crash interrupted terminal report publication.
            return Session(output, prior, provider, cancel_event).finish(prior["status"],
                prior.get("final_reason"), prior.get("final_summary"))
        if any(path.name != ".run.lock" for path in output.iterdir()):
            raise ValueError("Output directory must be empty; use resume for a pending question")
        data, catalog = load_fixture(variant), load_catalog()
        slots = resolve_request(question, identity, data["as_of"])
        schema_version = data["schema_version"]
        catalog = {**catalog, "schema_version": schema_version}
        known = schema_version in ("sales_v1", "sales_v2")
        state = {"state": "RECEIVED", "status": "active", "question": question, "identity": identity,
            "run_id": str(uuid.uuid4()), "request_id": request_id, "request_hash": request_hash,
            "fixture_variant": variant, "workflow_mode": workflow_mode, "active_seconds": 0,
            "slots": slots, "provider_mode": provider.mode, "decision_fixture": provider.decision_fixture,
            "source_fingerprints": fingerprints, "catalog": catalog, "as_of": data["as_of"],
            "schema_version": schema_version, "schema_refreshes": 0,
            "schema_hash": schema_fingerprint(schema_version) if known else digest(schema_version),
            "schema": tables_for_schema(schema_version) if known else {},
            "groupings": ["none"] if workflow_mode == "one_pass_sql" else ["none", "channel"],
            "evidence": {}, "trace": [], "query_receipts": [], "call_ids": [], "action_results": {},
            "turn": 0, "attempts": 0, "reference_queries": 0, "repairs": 0}
        session = Session(output, state, provider, cancel_event)
        if slots["denied"]:
            state["trace"].append({"tool": "host_scope_check", "result": "denied", "reason": slots["reason"]})
            return session.finish("access_denied", slots["reason"])
        if not known:
            return session.finish("schema_unsupported", "SCHEMA_UNSUPPORTED")
        if slots.get("insufficient_evidence"):
            return session.finish("insufficient_evidence", slots["reason"])
        if workflow_mode == "one_pass_sql" and slots["metric"] is None:
            slots["metric"], slots["metric_origin"] = "net_sales_v1", "baseline_assumption"
        rows = scoped_rows(data, slots["regions"])
        coverage = {(period, region) for period, region, complete in rows["period_coverage"] if complete}
        if any((period, region) not in coverage for period in slots["periods"] for region in slots["regions"]):
            return session.finish("insufficient_data", "INCOMPLETE_PERIOD_COVERAGE")
        create_projection(output / "scoped.sqlite", rows, schema_version)
        state["snapshot_hash"] = digest(rows)
        state["snapshot_file_hash"] = file_hash(output / "scoped.sqlite")
        session.save()
        return session.drive()


def restore_provider(state):
    if state["provider_mode"] not in ("scripted_policy", "scripted_policy_with_authored_fault", "authored_replay"):
        raise ValueError("PROVIDER_RECONFIGURATION_REQUIRED")
    fault = state["decision_fixture"]
    provider = (FanoutChallengeProvider() if fault == "initial_net_join_fanout" else
                FaultProvider(fault) if fault else ScriptedProvider())
    provider.restore_state(state.get("provider_state", {}))
    return provider


def resume(out, answer=None, *, cancel_event=None):
    output = Path(out)
    with run_lock(output):
        state = read_checkpoint(output)
        if state["status"] not in ("awaiting_clarification", "active"):
            raise ValueError("Run is not resumable; completed evidence is preserved")
        session = Session(output, state, restore_provider(state), cancel_event)
        try:
            check_context(state, source_fingerprints())
        except ValueError:
            return session.finish("failed", "CONTEXT_CHANGED")
        if file_hash(output / "scoped.sqlite") != state["snapshot_file_hash"]:
            return session.finish("failed", "SNAPSHOT_CHANGED")
        if state["status"] == "awaiting_clarification":
            if answer not in state["clarification"]["options"]:
                raise ValueError("Choose one of the pending metric options")
            state["slots"]["metric"], state["slots"]["metric_origin"] = answer, "external_clarification"
            state["trace"].append({"tool": "external_user_answer", "slot": "metric", "answer": answer})
            state["clarification"] = None
            state["state"] = "CATALOG_READY"
        else:
            state["trace"].append({"tool": "host_recovery", "read_repeat_may_occur": True})
        state["status"] = "active"
        session.save()
        return session.drive()
