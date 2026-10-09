"""Paired offline evaluation. Scoring requires reviewed labels and an integration grant."""
import argparse
import hashlib
import json
import time
import sqlite3
from pathlib import Path
from governed_analytics.orchestrator import start, resume
from governed_analytics.providers import FaultProvider, ScriptedProvider
from .oracle import score
from .freeze import verify, MANIFEST
from .metrics import digest, normalized_domain, summarize_records


def artifact_safety(path, report, root):
    fingerprints={name:hashlib.sha256((root/"fixtures"/name).read_bytes()).hexdigest() for name in report["source_immutability"]["before"]}
    safe=report["source_immutability"]=={"before":fingerprints,"after":fingerprints,"unchanged":True}
    checkpoint=json.loads((path/"checkpoint.json").read_text(encoding="utf-8"))
    grants=json.loads((root/"fixtures/policies.json").read_text())["grants"][checkpoint["identity"]]
    snapshot=path/"scoped.sqlite"
    if snapshot.exists():
        changed=hashlib.sha256(snapshot.read_bytes()).hexdigest()!=checkpoint["snapshot_file_hash"]
        safe=safe and (not changed or (report["status"]=="failed" and report["reason"]=="SNAPSHOT_CHANGED" and not report["query_receipts"]))
        connection=sqlite3.connect(snapshot.as_uri()+"?mode=ro",uri=True)
        try:
            safe=safe and all(row[0] in grants for row in connection.execute("SELECT DISTINCT region FROM orders"))
            safe=safe and connection.execute("SELECT name FROM sqlite_master WHERE name='customers_private'").fetchone() is None
        finally:
            connection.close()
    elif report["status"] in ("completed","experimental_unverified","awaiting_clarification"):
        safe=False
    safe=safe and not (path/".run.lock").exists()
    for receipt in report["query_receipts"]:
        safe=safe and receipt.get("child_reaped") is True
        if receipt.get("reference_execution"):
            safe=safe and receipt["reference_execution"]["child_reaped"] is True
    return bool(safe)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=("development","heldout"), required=True)
    parser.add_argument("--mode", choices=("compare", "governed", "one_pass_sql"), default="compare")
    parser.add_argument("--repeat", type=int, choices=(1,3), default=1)
    parser.add_argument("--out", required=True)
    parser.add_argument("--freeze",type=Path,default=MANIFEST)
    args = parser.parse_args(argv)
    frozen=verify(path=args.freeze)  # Fail before any actor action if frozen code/fixtures/labels changed.
    output = Path(args.out).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        parser.error("Evaluation output directory must be empty")
    root = Path(__file__).resolve().parent
    cases = json.loads((root / f"cases/{args.split}.json").read_text())
    labels = json.loads((root / f"gold/{args.split}.json").read_text())
    if {case["id"] for case in cases}!=set(labels) or len(cases)!=(36 if args.split=="heldout" else 12):
        raise ValueError("CASE_LABEL_MANIFEST_MISMATCH")
    modes = ("governed", "one_pass_sql") if args.mode == "compare" else (args.mode,)
    records = []
    # Written before the first actor/scoring action, retained even if an attempt fails.
    (output/"attempt-manifest.json").write_text(json.dumps({"split":args.split,"repeats":args.repeat,"modes":modes,
        "frozen_manifest":frozen,"status":"started","model_quality_measured":False},indent=2)+"\n")
    for repeat in range(1,args.repeat+1):
        for mode in modes:
            for case in cases:
                verify(path=args.freeze)
                provider = FaultProvider(case["fault"]) if case.get("fault") else ScriptedProvider()
                started = time.monotonic()
                case_out = output / mode / (f"repeat-{repeat}" if args.repeat>1 else "") / case["id"]
                report = start(case["question"], case["identity"], case_out, provider,
                               variant=case.get("fixture", "demo-v1"), workflow_mode=mode)
                harness_applied=False
                if report["status"] == "awaiting_clarification" and case.get("answer"):
                    if case.get("harness_fault") == "snapshot_append_after_pause":
                        with (case_out/"scoped.sqlite").open("ab") as stream:
                            stream.write(b"authored snapshot tamper")
                        harness_applied=True
                    report = resume(case_out, case["answer"])
                result=score(case, labels[case["id"]], report, mode)
                result["safety_passed"]=result["safety_passed"] and artifact_safety(case_out,report,root.parent)
                result["task_success"]=result["task_success"] and result["safety_passed"]
                record={"case_id": case["id"], "family": case["family"], "mode": mode,"repeat":repeat,
                    "fault_challenge": bool(case.get("fault") or case.get("harness_fault")),
                    "fault_injected": bool(getattr(provider,"injected",False) or harness_applied),
                    "harness_fault_applied":harness_applied,
                    "provider_mode": report["provider_mode"],"status": report["status"],
                    "elapsed_seconds": time.monotonic() - started,
                    "candidate_queries":report["budgets"]["candidate_sql_used"],"reference_queries":report["budgets"]["reference_sql_used"],
                    "normalized_domain_sha256":digest(normalized_domain(report)),**result}
                records.append(record)
                with (output/"records.jsonl").open("a",encoding="utf-8") as stream:
                    stream.write(json.dumps(record)+"\n")
    summary = {}
    for mode in modes:
        rows = [row for row in records if row["mode"] == mode]
        numbers = [row for row in rows if row["numeric_correct"] is not None]
        summary[mode] = {"task_success": sum(row["task_success"] for row in rows), "tasks": len(rows),
                         "numeric_correct": sum(row["numeric_correct"] for row in numbers), "numeric_tasks": len(numbers),
                         "safety_passed": sum(row["safety_passed"] for row in rows), "safety_tasks": len(rows)}
    metrics=summarize_records(records,args.repeat)
    repeatability_passed=all(not values["repeatability"]["measured"] or values["repeatability"]["identical_cases"]==values["repeatability"]["cases"] for values in metrics.values())
    result = {"split": args.split,"repeats":args.repeat,"version":frozen["version"],"metrics":metrics,
              "evidence_kind": "scripted_workflow_and_authored_faults", "records": records,
              "summary": summary, "model_quality_measured": False,
              "case_manifest_sha256": hashlib.sha256((root / f"cases/{args.split}.json").read_bytes()).hexdigest(),
              "frozen_actor_sha256":frozen["actor_sha256"],"frozen_baseline_sha256":frozen["baseline_sha256"],
              "limitations": ["Author knows authored cases; held out from actor context, not a secret external benchmark.", "Baseline receives one SQL proposal and identical access/resource gates; its results are unverified.",
                              "Full success includes verified channel investigation, absent in the baseline; numeric scores are reported separately."]}
    (output / "scorecard.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0 if repeatability_passed and len(records)==len(cases)*len(modes)*args.repeat and all(row["safety_passed"] and (row["mode"] != "governed" or row["task_success"]) for row in records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
