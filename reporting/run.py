"""LEASE REQUIRED: optional journal wrapper, unchanged frozen actors/cases/budgets."""
import argparse
import json
import time
from pathlib import Path
from evaluation_v2.run import run_case
from .accounting import ACTORS, TERMINAL, new_ledger, transition, close, require
from .journal import persist
from .export import Reader, sha
from .freeze import ROOT, verify, verify_historical


def execute(plan, source_sha256, invoke, save, terminal_receipt, clock=time.monotonic):
    """Pure injectable boundary. Durable STARTED must succeed before invoke."""
    ledger = new_ledger(plan, source_sha256)
    save(ledger)
    rows = []
    try:
        for intent in plan:
            case, actor = intent["case_id"], intent["actor"]
            proposed = transition(ledger, case, actor, "STARTED", started_at=clock())
            save(proposed)
            ledger = proposed
            row = invoke(intent)
            rows.append(row)
            receipt = terminal_receipt(intent)
            if receipt is None:
                proposed = transition(ledger, case, actor, "INTERRUPTED_UNKNOWN", reason="TERMINAL_EVIDENCE_MISSING")
            else:
                proposed = transition(ledger, case, actor, "TERMINAL", **receipt)
            save(proposed)
            ledger = proposed
            if row.get("final_correct") is not True or receipt is None:
                break
    except (KeyboardInterrupt, Exception):
        # No automatic retry/resume. A kill can leave STARTED durable; exporting
        # a caller-declared closed run then labels that attempt outcome unknown.
        ledger = close(ledger)
        save(ledger)
        return ledger, rows
    ledger = close(ledger)
    save(ledger)
    return ledger, rows


def main():
    parser = argparse.ArgumentParser(description="Journalled offline attempt; new native lease required")
    parser.add_argument("--split", choices=("development", "capability"), required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--actor", choices=ACTORS, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--lease-ack", choices=("main-authorized-local-u2c",), required=True)
    args = parser.parse_args()
    frozen = verify()
    old = verify_historical()
    require(not args.out.exists(), "OUTPUT_EXISTS")
    cases = json.loads((ROOT/"evaluation_v2/cases"/(args.split+".json")).read_text(encoding="utf-8"))
    labels = json.loads((ROOT/"evaluation_v2/labels"/(args.split+".json")).read_text(encoding="utf-8"))
    selected = [c for c in cases if c["case_id"] == args.case]
    require(len(selected) == 1, "CASE_NOT_ASSIGNED")
    case = selected[0]
    data = json.loads((ROOT/"evaluation_v2"/case["source"]).read_text(encoding="utf-8"))
    args.out.mkdir(parents=True)
    plan = [{"case_id": args.case, "actor": args.actor, "numeric_applicable": labels[args.case]["kind"] == "numeric"}]
    (args.out/"started.json").write_text(json.dumps({"version": "u2c-run-v1", "case_ids": [args.case], "actors": [args.actor], "numeric_applicable": {args.case: plan[0]["numeric_applicable"]}, "freeze": old["source_sha256"], "reporting_freeze": frozen["source_sha256"]}, indent=2)+"\n", encoding="utf-8")
    out = args.out/args.case/args.actor
    def invoke(intent):
        return run_case(case, data, labels[args.case], args.actor, out)
    def receipt(intent):
        reader = Reader()
        report = reader.json(out/"report.json", "report")
        if report.get("status") not in TERMINAL:
            return None
        score_raw = reader.bytes(out/"score.json", "score")
        return {"terminal_status": report["status"], "report_sha256": reader.hashes["report"], "score_sha256": sha(score_raw)}
    ledger, rows = execute(plan, frozen["source_sha256"], invoke, lambda value: persist(args.out/"attempts.json", value), receipt)
    (args.out/"rows.json").write_text(json.dumps(rows, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"lifecycle": ledger["attempts"][0]["state"], "native_status": ledger["attempts"][0]["terminal_status"], "scored_rows": len(rows), "cohort_rerun": False}, indent=2))
    return int(ledger["attempts"][0]["state"] != "TERMINAL" or not rows or any(row.get("final_correct") is not True for row in rows))


if __name__ == "__main__":
    raise SystemExit(main())
