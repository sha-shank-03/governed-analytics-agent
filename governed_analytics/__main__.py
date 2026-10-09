"""Run from the checkout with py -3.11 -m governed_analytics."""

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from .data import GRANTS, load_catalog, load_fixture, source_fingerprints, available_variants
from .orchestrator import start, resume
from .providers import FanoutChallengeProvider, FaultProvider

QUESTION = "Why did revenue fall in February 2026 versus January 2026?"


def doctor():
    required = ("set_authorizer", "setlimit", "set_progress_handler")
    if sys.version_info[:2] != (3, 11) or not all(hasattr(sqlite3.Connection, name) for name in required):
        raise ValueError("Use Python 3.11 with the required SQLite connection APIs")
    data, catalog = load_fixture(), load_catalog()
    if data["schema_version"] != catalog["schema_version"]:
        raise ValueError("Schema/catalog version mismatch")
    return {"status": "ready", "python": sys.version.split()[0], "sqlite": sqlite3.sqlite_version,
            "decision_mode": "scripted_policy", "fixture": "authored_fictional",
            "source_fingerprints": source_fingerprints(),
            "note": "API and fixture checks only; SQL guards and demos require separate execution."}


def demo(scenario, out):
    if scenario in ("schema-drift", "missing-period", "schema-unsupported", "zero-previous"):
        variants = {"schema-drift": "demo-v2", "missing-period": "missing-period",
                    "schema-unsupported": "unknown-schema", "zero-previous": "zero-previous"}
        provider = FaultProvider("stale_schema") if scenario == "schema-drift" else None
        report = start("Compare net sales in January 2026 and February 2026", "north_analyst", out,
                       provider, variant=variants[scenario])
        expected = {"schema-drift": "completed", "missing-period": "insufficient_data",
                    "schema-unsupported": "schema_unsupported", "zero-previous": "completed"}[scenario]
        if report["status"] != expected:
            raise ValueError("DEMO_VARIANT_ASSERTION_FAILED")
        if scenario == "schema-drift" and report["budgets"]["schema_refreshes"] != 1:
            raise ValueError("DEMO_SCHEMA_REFRESH_ASSERTION_FAILED")
        if scenario == "zero-previous" and (report["summary"]["previous_cents"] != 0 or report["summary"]["percent_change"] is not None):
            raise ValueError("DEMO_ZERO_PERCENT_ASSERTION_FAILED")
        if not report["source_immutability"]["unchanged"]:
            raise ValueError("DEMO_SOURCE_IMMUTABILITY_ASSERTION_FAILED")
        return report
    if scenario == "revenue-drop":
        report = start(QUESTION, "north_analyst", out, FanoutChallengeProvider())
        if report["status"] != "awaiting_clarification" or report["query_receipts"]:
            raise ValueError("DEMO_CLARIFICATION_ASSERTION_FAILED")
        report = resume(out, "net_sales_v1")
        summary = report["summary"]
        if report["status"] != "completed" or (summary["previous_cents"], summary["current_cents"], summary["delta_cents"]) != (1000000, 780000, -220000):
            raise ValueError("DEMO_NUMERIC_ASSERTION_FAILED")
        if summary["channel_deltas_cents"] != {"direct": -220000, "partner": 0}:
            raise ValueError("DEMO_CHANNEL_ASSERTION_FAILED")
        if not any(item["verification"] == "GRAIN_OR_VALUE_MISMATCH" for item in report["query_receipts"]):
            raise ValueError("DEMO_JOIN_REJECTION_ASSERTION_FAILED")
    else:
        report = start("Compare net sales for all regions in January 2026 and February 2026",
                       "north_analyst", out)
        if report["status"] != "access_denied" or report["query_receipts"] or report["evidence"]:
            raise ValueError("DEMO_DENIAL_ASSERTION_FAILED")
    serialized = json.dumps(report)
    if any(canary in serialized for canary in ("PRIVATE_EMAIL_CANARY", "SOUTH_ORDER_CANARY")):
        raise ValueError("DEMO_PRIVATE_EXPOSURE_ASSERTION_FAILED")
    if not report["source_immutability"]["unchanged"]:
        raise ValueError("DEMO_SOURCE_IMMUTABILITY_ASSERTION_FAILED")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Governed analytics on authored fictional sales; scripted decisions.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Check Python 3.11 APIs and fixture metadata; no model call")
    demo_parser = commands.add_parser("demo", help="Run an offline scenario with synthetic user replies")
    demo_parser.add_argument("--scenario", choices=("revenue-drop", "denied-scope", "schema-drift", "missing-period", "schema-unsupported", "zero-previous"), required=True)
    demo_parser.add_argument("--out", required=True)
    run_parser = commands.add_parser("run", help="Ask a question; ambiguous revenue pauses for external clarification")
    run_parser.add_argument("--question", required=True)
    run_parser.add_argument("--identity", choices=tuple(GRANTS), required=True)
    run_parser.add_argument("--fixture", choices=available_variants(), default="demo-v1")
    run_parser.add_argument("--request-id")
    run_parser.add_argument("--provider", choices=("scripted",), default="scripted")
    run_parser.add_argument("--out", required=True)
    resume_parser = commands.add_parser("resume", help="Provide an external answer to the pending metric question")
    resume_parser.add_argument("--run", required=True)
    resume_parser.add_argument("--answer", choices=("gross_sales_v1", "net_sales_v1"))
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            print(json.dumps(doctor(), indent=2))
            return 0
        if args.command == "demo":
            result = demo(args.scenario, args.out)
        elif args.command == "run":
            result = start(args.question, args.identity, args.out, variant=args.fixture, request_id=args.request_id)
        else:
            result = resume(args.run, args.answer)
        output = args.run if args.command == "resume" else args.out
        print(json.dumps({"status": result["status"], "provider_mode": result["provider_mode"],
                          "reason": result["reason"], "summary": result["summary"],
                          "report": (Path(output) / "report.json").as_posix()}, indent=2))
        return 130 if result["status"] == "cancelled" else (2 if result["status"] == "awaiting_clarification" else (1 if result["status"] in ("failed", "budget_exhausted") else 0))
    except KeyboardInterrupt:
        print("Cancelled; owned query cleanup runs before returning.", file=sys.stderr)
        return 130
    except (ValueError, OSError, KeyError, TypeError, RuntimeError) as exc:
        print(json.dumps({"status": "error", "reason": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
