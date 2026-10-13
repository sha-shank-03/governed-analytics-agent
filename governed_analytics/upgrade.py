"""U1 local workflow; optional host-validated U2-A snapshot input, no remote SQL tool."""
import argparse
import hashlib
import json
import time
import uuid
from pathlib import Path
from .catalog import make_contract
from .data import (create_projection, digest, load_catalog, load_fixture, scoped_rows,
                   schema_fingerprint, source_fingerprints, tables_for_schema)
from .reports import summarize
from .state import atomic_json, read_checkpoint, run_lock
from .verification import compare, reference_sql
from .upgrade_budget import Budget, LIMITS, UpgradeError, new_budget
from .upgrade_events import append_event, encoded, redact
from .upgrade_gateway import GatewayConfig, GatewayProvider, strict_json
from .upgrade_intents import FIELDS, confirm, proposal_receipt, request_guard, validate_semantic
from .upgrade_transport import query_exchange

BASE_COMMIT = "7f98434549fe65a93593c3717cea71c4d6270f71"


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def code_hash():
    root = Path(__file__).parent
    return digest({p.name: file_hash(p) for p in sorted(root.glob("*.py"))})


def snapshot_data(out, state):
    """Only an importer-validated, hash-bound host file can replace a fixture."""
    fixture = state.get("source_fixture")
    if fixture is not None:
        from .upgrade_fixture import FixtureSnapshot
        path = Path(out) / "source_fixture.json"
        if path.stat().st_size > 2000000 or file_hash(path) != fixture["file_hash"]:
            raise UpgradeError("SOURCE_FIXTURE_CHANGED")
        snapshot = FixtureSnapshot(path.read_text(encoding="utf-8"))
        if snapshot.binding() != fixture["binding"]:
            raise UpgradeError("SOURCE_FIXTURE_CHANGED")
        return snapshot.payload()
    context = state.get("source_snapshot")
    if context is None:
        return load_fixture(state["fixture_variant"])
    from .bigquery_snapshot import ValidatedSnapshot
    path = Path(out) / "source_snapshot.json"
    if file_hash(path) != context["file_hash"] or path.stat().st_size > 2300000:
        raise UpgradeError("SOURCE_SNAPSHOT_CHANGED")
    payload = strict_json(path.read_bytes())
    if type(payload) is not dict or set(payload) != {"data", "provenance"}:
        raise UpgradeError("SOURCE_SNAPSHOT_CHANGED")
    snapshot = ValidatedSnapshot(json.dumps(payload["data"]), json.dumps(payload["provenance"]))
    if snapshot.binding() != context["binding"]:
        raise UpgradeError("SOURCE_SNAPSHOT_CHANGED")
    return snapshot.payload()["data"]


def current_sources(out, state):
    fingerprints = source_fingerprints()
    if state.get("source_snapshot"):
        try:
            actual = file_hash(Path(out) / "source_snapshot.json")
        except OSError:
            actual = None
        context = state["source_snapshot"]
        fingerprints["bigquery_snapshot"] = context["binding"] if actual == context["file_hash"] else digest(actual)
    if state.get("source_fixture"):
        try:
            actual = file_hash(Path(out) / "source_fixture.json")
        except OSError:
            actual = None
        context = state["source_fixture"]
        fingerprints["evaluation_fixture"] = context["binding"] if actual == context["file_hash"] else digest(actual)
    return fingerprints


class UpgradeSession:
    def __init__(self, out, state, provider, *, cancel_event=None, query=query_exchange):
        self.out, self.state, self.provider = Path(out), state, provider
        self.cancel_event, self.query = cancel_event, query
        self.budget = Budget(state["budget"], limits=state["limits"])

    def save(self, kind="checkpoint", details=None):
        self.budget.charge()
        self.state["provider_state"] = self.provider.dump_state()
        atomic_json(self.out / "checkpoint.json", redact(self.state))
        append_event(self.out, self.state, kind, details)

    def check(self):
        self.budget.check()
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise UpgradeError("CANCELLED")
        if code_hash() != self.state["code_hash"] or current_sources(self.out, self.state) != self.state["source_fingerprints"]:
            raise UpgradeError("SOURCE_CONTEXT_CHANGED")
        if file_hash(self.out / "scoped.sqlite") != self.state["snapshot_file_hash"]:
            raise UpgradeError("SNAPSHOT_CHANGED")

    def finish(self, status, reason=None, summary=None):
        if status == "completed":
            self.check()
        self.state.update(status=status, final_reason=reason, final_summary=summary)
        self.save("outcome", {"reason": reason})
        metrics = self.budget.metrics()
        if self.provider.mode == "deterministic_v2":
            metrics["cost_status"] = "unavailable_deterministic_no_inference"
            metrics["usage_label"] = "not_model_usage"
        report = {"schema_version": "u1-report-v1", "mode": self.provider.mode, "status": status,
            "reason": reason, "run_id": self.state["run_id"], "base_commit": BASE_COMMIT,
            "code_hash": self.state["code_hash"], "config_hash": self.state["config_hash"],
            "prompt_version": getattr(self.provider, "prompt_version", "gateway-u1-v1"), "model": self.provider.config.model,
            "provider_id": None, "contract": self.state.get("contract"),
            "proposal": self.state.get("proposal"), "confirmation": self.state.get("confirmation"),
            "summary": summary, "evidence": self.state["evidence"],
            "query_receipts": self.state["query_receipts"], "tool_trace": self.state["trace"],
            "gateway_receipts": self.state["gateway_receipts"],
            "metrics": metrics,
            "source_immutability": {"before": self.state["source_fingerprints"],
                                   "after": current_sources(self.out, self.state),
                                   "unchanged": self.state["source_fingerprints"] == current_sources(self.out, self.state)},
            "source_snapshot": self.state.get("source_snapshot"),
            "source_fixture": self.state.get("source_fixture"),
            "limits": self.state["limits"], "host_counters": self.state["host_counters"],
            "limitations": ["Offline decision evidence; no live model quality or external sandbox evidence.",
                            "Static simulated identities; OS owner remains trusted.",
                            "Four catalog measures, total/channel reconciliation, USD, fixed source cutoff."]}
        atomic_json(self.out / "report.json", redact(report))
        # Keep persisted counters consistent with final telemetry charging.
        self.save("report_saved")
        if status == "completed":
            # Final artifact writes also consume active time. If they cross the
            # deadline, drive() replaces the report with a typed safe stop.
            self.check()
        report = json.loads((self.out / "report.json").read_text(encoding="utf-8"))
        return report

    def error(self, exc):
        status = "cancelled" if exc.code == "CANCELLED" else "budget_exhausted" if (
            exc.code.endswith("BUDGET_EXHAUSTED") or exc.code == "RUN_DEADLINE") else "access_denied" if (
            exc.code in ("PRIVATE_DATA_REQUEST", "SCOPE_NOT_GRANTED", "IDENTITY_NOT_GRANTED")) else "handoff" if (
            exc.code == "CAUSAL_EVIDENCE_UNAVAILABLE") else "failed"
        return self.finish(status, exc.code)

    def observation(self):
        s = self.state
        return {"state": s["state"], "question": s["question"], "catalog": s["catalog"],
                "schema": s["schema"], "schema_version": s["schema_version"],
                "allowed_regions": s["grant"], "as_of": s["as_of"],
                "available_periods": s["available_periods"],
                "previous_confirmed_semantic": s.get("previous_confirmed_semantic"),
                "confirmed_contract": s.get("contract"),
                "evidence": {g: e["result_id"] for g, e in s["evidence"].items()},
                "last_result": s.get("last_result")}

    def drive(self):
        try:
            while True:
                self.check()
                s = self.state
                allowed = ("propose_intent", "handoff") if s["state"] == "INTENT" else ("execute_query",)
                if s["state"] == "REPAIR_REQUIRED" and s["host_counters"]["schema_refreshes"] < 1:
                    allowed += ("refresh_catalog",)
                if s["state"] == "VERIFIED":
                    allowed += ("finish_report",)
                try:
                    decision = self.provider.decide(self.observation(), allowed, self.budget,
                        cancel_event=self.cancel_event, before_send=lambda: self.save("request_admitted"))
                finally:
                    if self.provider.last_receipt:
                        s["gateway_receipts"].append(self.provider.last_receipt)
                self.check()
                self.budget.admit_tool()
                signature = digest({"tool": decision.tool, "arguments": decision.arguments})
                if decision.call_id in s["call_ids"]:
                    raise UpgradeError("CONFLICTING_CALL_ID" if s["call_ids"][decision.call_id] != signature else "REPLAYED_CALL_ID")
                s["call_ids"][decision.call_id] = signature
                # Raw attempted function is separated from whether the host authorized it.
                record = {"call_id": decision.call_id, "tool": decision.tool,
                          "arguments_hash": digest(decision.arguments), "guarded_outcome": "pending"}
                s["trace"].append(record)
                try:
                    result = self.dispatch(decision)
                    record["guarded_outcome"] = "verified" if result.get("verified") else "accepted" if (
                        s["state"] in ("AWAITING_CONFIRMATION", "HANDOFF")) else "blocked" if result.get("error") else "accepted"
                    record["reason"] = result.get("error")
                except UpgradeError as exc:
                    record.update(guarded_outcome="blocked", reason=exc.code)
                    raise
                s["last_result"] = result
                self.provider.tool_result(decision, result)
                self.save("tool_result", record)
                self.check()
                if s["state"] == "AWAITING_CONFIRMATION":
                    # Exclusion is explicit, persisted, and limited by absolute lifetime.
                    s["pause"] = {"started_monotonic": time.monotonic(), "reason": "external_contract_confirmation"}
                    return self.finish("awaiting_confirmation", "EXTERNAL_CONFIRMATION_REQUIRED")
                if s["state"] == "HANDOFF":
                    return self.finish("handoff", result["reason"])
                if s["state"] == "COMPLETED":
                    return self.finish("completed", summary=result)
        except UpgradeError as exc:
            return self.error(exc)
        except KeyboardInterrupt:
            return self.error(UpgradeError("CANCELLED"))
        except Exception:
            # Actor/transport exception text can contain sensitive payloads.
            return self.error(UpgradeError("HOST_FAILURE"))

    def dispatch(self, decision):
        s, args, tool = self.state, decision.arguments, decision.tool
        if tool == "handoff":
            if args["reason"] not in ("unknown_intent", "unsupported_intent", "unclear_followup"):
                raise UpgradeError("INVALID_HANDOFF")
            s["state"] = "HANDOFF"
            return {"reason": args["reason"], "sql_executed": False}
        if tool == "propose_intent":
            semantic = validate_semantic(args, s["grant"])
            s["proposal"] = proposal_receipt(semantic, s)
            s["state"] = "AWAITING_CONFIRMATION"
            return {"proposal": s["proposal"], "confirmation_required": True}
        if s.get("confirmation") is None or s.get("contract") is None:
            raise UpgradeError("CONFIRMATION_REQUIRED")
        if tool == "refresh_catalog":
            if s["host_counters"]["schema_refreshes"] >= 1:
                raise UpgradeError("SCHEMA_REFRESH_LIMIT")
            s["host_counters"]["schema_refreshes"] += 1
            s["state"] = "PLAN_READY"
            return {"schema": s["schema"], "schema_version": s["schema_version"]}
        if tool == "finish_report":
            ids = args["result_ids"]
            if type(ids) is not list or len(ids) != 2 or any(type(i) is not str or len(i) > 100 for i in ids):
                raise UpgradeError("INVALID_EVIDENCE_IDS")
            try:
                summary = summarize(s["contract"], s["evidence"], ids)
            except (ValueError, TypeError, KeyError):
                raise UpgradeError("UNVERIFIED_COMPLETION") from None
            s["state"] = "COMPLETED"
            return summary
        if tool != "execute_query":
            raise UpgradeError("TOOL_NOT_ALLOWED")
        if args["contract_id"] != s["contract"]["contract_id"] or args["grouping"] not in s["contract"]["groupings"]:
            raise UpgradeError("INVALID_CONTRACT_ACTION")
        sql = args["sql"]
        if type(sql) is not str or not sql.strip() or len(sql.encode("utf-8")) > s["limits"]["sql_bytes"]:
            raise UpgradeError("INVALID_SQL")
        if s["host_counters"]["candidates"] >= 6 or s["host_counters"]["repairs"] > 2:
            raise UpgradeError("SQL_BUDGET_EXHAUSTED")
        self.check()
        contract, counters = s["contract"], s["host_counters"]
        parameters = {"previous": contract["periods"][0], "current": contract["periods"][1], "as_of": contract["as_of"]}
        counters["candidates"] += 1
        self.save("candidate_admitted", {"sql_hash": digest(sql)})
        receipt = {"query_id": "query-" + str(counters["candidates"]), "sql_hash": digest(sql),
                   "parameters": parameters, "grouping": args["grouping"], "snapshot_hash": s["snapshot_hash"]}
        s["query_receipts"].append(receipt)
        try:
            candidate = self.query(self.out / "scoped.sqlite", sql, parameters, s["schema_version"],
                timeout=min(s["limits"]["sql_seconds"], self.budget.remaining()), cancel_event=self.cancel_event)
        except UpgradeError as exc:
            receipt["candidate"] = {"ok": False, "error": exc.code, **exc.receipt}
            raise
        receipt["candidate"] = {k: candidate.get(k) for k in ("ok", "error", "duration_ms", "child_pid", "child_reaped")}
        self.check()
        if candidate.get("ok"):
            counters["references"] += 1
            self.save("reference_admitted", {"query_id": receipt["query_id"]})
            try:
                reference = self.query(self.out / "scoped.sqlite",
                    reference_sql(contract["metric"], args["grouping"], s["schema_version"]), parameters,
                    s["schema_version"], timeout=min(s["limits"]["sql_seconds"], self.budget.remaining()),
                    cancel_event=self.cancel_event)
            except UpgradeError as exc:
                receipt["reference"] = {"ok": False, "error": exc.code, **exc.receipt}
                raise
            receipt["reference"] = {k: reference.get(k) for k in ("ok", "error", "duration_ms", "child_pid", "child_reaped")}
            self.check()
            if not reference.get("ok"):
                raise UpgradeError("CANCELLED" if reference.get("error") == "CANCELLED" else "REFERENCE_QUERY_FAILED")
            validation = compare(candidate, reference)
        else:
            validation = {"verified": False, "error": candidate.get("error", "WORKER_FAILED")}
        receipt["verification"] = validation
        if not validation["verified"]:
            counters["repairs"] += 1
            s["state"] = "REPAIR_REQUIRED"
            if validation["error"] in ("POLICY_DENIED", "CANCELLED", "QUERY_TIMEOUT", "WORKER_FAILED"):
                raise UpgradeError(validation["error"])
            return {"verified": False, "error": validation["error"], "grain_hint": "Aggregate child tables separately at order grain."}
        group = args["grouping"]
        result_id = "result-" + digest({"contract": contract["contract_id"], "grouping": group, "rows": validation["rows"]})[:16]
        s["evidence"][group] = {"verified": True, "result_id": result_id,
                                  "query_id": receipt["query_id"], "rows": validation["rows"]}
        s["state"] = "VERIFIED"
        return s["evidence"][group]


def start(question, identity, out, provider, *, variant="demo-v1", previous_confirmed=None,
          cancel_event=None, limits=None, query=query_exchange, trusted_snapshot=None, trusted_fixture=None):
    started = time.monotonic()
    output = Path(out)
    with run_lock(output):
        if any(p.name != ".run.lock" for p in output.iterdir()):
            raise UpgradeError("OUTPUT_EXISTS_USE_RESUME")
        source_snapshot = None
        source_fixture = None
        if trusted_fixture is not None and trusted_snapshot is not None:
            raise UpgradeError("AMBIGUOUS_SOURCE_INPUT")
        if trusted_snapshot is not None:
            from .bigquery_snapshot import ValidatedSnapshot
            if not isinstance(trusted_snapshot, ValidatedSnapshot):
                raise UpgradeError("VALIDATED_HOST_SNAPSHOT_REQUIRED")
            payload = trusted_snapshot.payload()
            data = payload["data"]
            atomic_json(output / "source_snapshot.json", payload)
            source_snapshot = {"binding": trusted_snapshot.binding(),
                "file_hash": file_hash(output / "source_snapshot.json"), "provenance": payload["provenance"]}
            variant = "bigquery-fixed-snapshot"
        elif trusted_fixture is not None:
            from .upgrade_fixture import FixtureSnapshot
            if type(trusted_fixture) is not FixtureSnapshot:
                raise UpgradeError("VALIDATED_AUTHORED_FIXTURE_REQUIRED")
            data = trusted_fixture.payload()
            atomic_json(output / "source_fixture.json", data)
            source_fixture = {"binding": trusted_fixture.binding(),
                "file_hash": file_hash(output / "source_fixture.json"),
                "fixture_id": data["fixture_id"], "lineage": data["lineage"]}
            variant = "authored-v2-fixture"
        else:
            data = load_fixture(variant)
        catalog = load_catalog()
        catalog = {**catalog, "schema_version": data["schema_version"]}
        configured_limits = {**LIMITS, **(limits or {})}
        # Smaller local test limits are allowed; an input cannot expand published bounds.
        if any(key not in LIMITS or type(value) not in (int, float) or value <= 0 or value > LIMITS[key]
               for key, value in configured_limits.items()):
            raise UpgradeError("INVALID_LIMITS")
        fingerprints = source_fingerprints()
        if source_snapshot:
            fingerprints["bigquery_snapshot"] = source_snapshot["binding"]
        if source_fixture:
            fingerprints["evaluation_fixture"] = source_fixture["binding"]
        request = {"question": question, "identity": identity, "variant": variant,
                   "config": provider.config.portable(), "limits": configured_limits,
                   "previous_confirmed": previous_confirmed, "sources": fingerprints}
        grant = []
        guard_error = None
        try:
            grant = request_guard(question, identity)
            if source_snapshot and identity != "north_analyst":
                grant = []
                raise UpgradeError("SCOPE_NOT_GRANTED")
        except UpgradeError as exc:
            guard_error = exc
        known = data["schema_version"] in ("sales_v1", "sales_v2")
        rows = scoped_rows(data, grant)
        create_projection(output / "scoped.sqlite", rows, "sales_v1" if not known else data["schema_version"])
        state = {"version": "u1-checkpoint-v1", "run_id": str(uuid.uuid4()),
            "state": "INTENT", "status": "active", "question": redact(question), "identity": identity,
            "grant": grant, "fixture_variant": variant, "request_hash": digest(request),
            "source_snapshot": source_snapshot, "source_fixture": source_fixture,
            "provider_mode": provider.mode,
            "prompt_version": getattr(provider, "prompt_version", "gateway-u1-v1"),
            "source_fingerprints": fingerprints, "code_hash": code_hash(),
            "config_hash": digest({"gateway": provider.config.portable(), "limits": configured_limits}),
            "limits": configured_limits, "gateway_config": provider.config.portable(),
            "catalog": catalog, "as_of": data["as_of"], "schema_version": data["schema_version"],
            "schema": tables_for_schema(data["schema_version"]) if known else {},
            "schema_hash": schema_fingerprint(data["schema_version"]) if known else digest(data["schema_version"]),
            "snapshot_hash": digest(rows), "snapshot_file_hash": file_hash(output / "scoped.sqlite"),
            "available_periods": sorted({r[0] for r in rows["period_coverage"]}),
            "budget": new_budget(started), "trace": [], "gateway_receipts": [], "query_receipts": [],
            "evidence": {}, "call_ids": {},
            "host_counters": {"candidates": 0, "references": 0, "repairs": 0, "schema_refreshes": 0}}
        state["budget"]["active_seconds"] = time.monotonic() - started
        session = UpgradeSession(output, state, provider, cancel_event=cancel_event, query=query)
        if guard_error:
            return session.error(guard_error)
        if not known:
            return session.finish("handoff", "SCHEMA_UNSUPPORTED")
        if previous_confirmed is not None:
            # Follow-up context comes from a trusted confirmed slot interface, never provider IDs.
            validate_semantic(previous_confirmed, grant, confirmed=True)
            state["previous_confirmed_semantic"] = previous_confirmed
        session.save("started")
        return session.drive()


def resume(out, answer, provider, *, cancel_event=None, query=query_exchange):
    output = Path(out)
    with run_lock(output):
        state = read_checkpoint(output)
        if state.get("version") != "u1-checkpoint-v1" or state["status"] != "awaiting_confirmation":
            raise UpgradeError("RUN_NOT_RESUMABLE")
        if provider.config.portable() != state["gateway_config"]:
            raise UpgradeError("PROVIDER_CONFIG_CHANGED")
        provider.restore_state(state["provider_state"])
        session = UpgradeSession(output, state, provider, cancel_event=cancel_event, query=query)
        try:
            session.check()
            paused = time.monotonic() - state["pause"]["started_monotonic"]
            if paused < 0:
                raise UpgradeError("CLOCK_CONTEXT_CHANGED")
            state["budget"]["pause_seconds"] += paused
            state["pause"]["ended_monotonic"] = time.monotonic()
            semantic = confirm(state["proposal"], answer, state)
            rows = scoped_rows(snapshot_data(output, state), semantic["regions"])
            coverage = {(p, r) for p, r, complete in rows["period_coverage"] if complete}
            if any((p, r) not in coverage for p in semantic["periods"] for r in semantic["regions"]):
                return session.finish("handoff", "INCOMPLETE_PERIOD_COVERAGE")
            # Narrow the physical projection again if confirmation selected a smaller granted scope.
            # Rebuild in a temporary sibling, then replace atomically; old evidence does not exist yet.
            projection = output / "confirmed.sqlite"
            create_projection(projection, rows, state["schema_version"])
            projection.replace(output / "scoped.sqlite")
            state["snapshot_hash"], state["snapshot_file_hash"] = digest(rows), file_hash(output / "scoped.sqlite")
            slots = {**semantic, "metric_origin": "external_contract_confirmation"}
            state["contract"] = make_contract(slots, state["catalog"], state["source_fingerprints"],
                state["as_of"], state["schema_hash"], state["snapshot_hash"])
            state["confirmation"] = {"proposal_id": answer["proposal_id"], "semantic": semantic,
                                     "contract_id": state["contract"]["contract_id"], "pause": state["pause"],
                                     "authority": "trusted_external_cli_confirmation"}
            state.update(state="PLAN_READY", status="active", last_result={"confirmed_contract": state["contract"]})
            session.save("external_confirmation", {"proposal_id": answer["proposal_id"]})
            return session.drive()
        except UpgradeError as exc:
            return session.error(exc)
        except KeyboardInterrupt:
            return session.error(UpgradeError("CANCELLED"))
        except Exception:
            return session.error(UpgradeError("HOST_FAILURE"))


def read_config(path):
    value = strict_json(Path(path).read_bytes())
    if type(value) is not dict or set(value) != {"endpoint", "model", "mode"}:
        raise UpgradeError("INVALID_CONFIG_FIELDS")
    return GatewayConfig(**value)


def main():
    parser = argparse.ArgumentParser(description="U1 Gateway-native local-double analytics")
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo")
    demo.add_argument("--scenario", choices=("freeform-confirmation", "slow-provider", "unknown-intent", "denied-scope", "unauthorized-query", "malformed-call", "false-completion"), required=True)
    demo.add_argument("--provider", choices=("local-double",), required=True)
    demo.add_argument("--out", type=Path, required=True)
    begin = commands.add_parser("start")
    begin.add_argument("--question", required=True)
    begin.add_argument("--identity", choices=("north_analyst", "south_analyst", "all_sales_analyst"), default="north_analyst")
    begin.add_argument("--variant", default="demo-v1")
    begin.add_argument("--config", type=Path, required=True)
    begin.add_argument("--out", type=Path, required=True)
    again = commands.add_parser("resume")
    again.add_argument("--config", type=Path, required=True)
    again.add_argument("--out", type=Path, required=True)
    answer = again.add_mutually_exclusive_group(required=True)
    answer.add_argument("--accept", help="Exact displayed proposal_id")
    answer.add_argument("--answer", type=Path, help="Full externally confirmed semantic JSON")
    args = parser.parse_args()
    try:
        if args.command == "demo":
            from .upgrade_double import run_demo
            report = run_demo(args.scenario, args.out)
        else:
            provider = GatewayProvider(read_config(args.config))
            if args.command == "start":
                report = start(args.question, args.identity, args.out, provider, variant=args.variant)
            else:
                if args.accept:
                    receipt = read_checkpoint(args.out)["proposal"]
                    confirmed = {"proposal_id": args.accept, "semantic": {k: receipt[k] for k in FIELDS}}
                else:
                    confirmed = strict_json(args.answer.read_bytes())
                report = resume(args.out, confirmed, provider)
        print(json.dumps({"mode": report["mode"], "status": report["status"], "reason": report["reason"],
                          "proposal": report.get("proposal"), "summary": report.get("summary"),
                          "metrics": report["metrics"]}, indent=2, allow_nan=False))
        return 0 if report["status"] in ("completed", "awaiting_confirmation", "handoff", "access_denied") else 2
    except (UpgradeError, OSError, KeyError, ValueError):
        print('{"status":"failed","reason":"CLI_INPUT_OR_CONTEXT_REJECTED","mode":"local_double"}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
