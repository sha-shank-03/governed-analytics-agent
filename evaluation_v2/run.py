"""LEASE REQUIRED: fixed authored task denominators, same host/tools/approval/bounds."""
import argparse
import json
import time
from pathlib import Path
from governed_analytics.deterministic_v2 import DeterministicProvider, choose
from governed_analytics.upgrade import start, resume
from governed_analytics.upgrade_fixture import FixtureSnapshot
from governed_analytics.upgrade_gateway import GatewayConfig, GatewayProvider
from .freeze import verify
from .inspect import inspect
from .scorer import evaluate, aggregate
from .summary import retained

ROOT = Path(__file__).resolve().parent
ACTORS = ("deterministic-v2", "protocol-double")


def actor_input(case, data):
    """Allowlist: no IDs, split, family, scenario, label or fault enters observations."""
    return {"question": case["question"], "identity": case["identity"],
            "previous_confirmed": case["previous_confirmed"],
            "trusted_fixture": FixtureSnapshot(json.dumps(data))}


def protocol_response(observation, allowed, turn):
    tool, args = choose(observation, allowed)
    return {"id": f"synthetic-u2b-{turn}", "choices": [{"finish_reason": "tool_calls", "message": {
        "role": "assistant", "content": None, "tool_calls": [{"id": f"protocol-{turn}", "type": "function",
            "function": {"name": tool, "arguments": json.dumps(args)}}]}}]}


def provider(mode):
    if mode == "deterministic-v2":
        return DeterministicProvider()
    if mode != "protocol-double":
        raise ValueError("UNKNOWN_ACTOR")
    # Pure in-memory protocol fixture, no HTTP socket. Uses the same language
    # policy as the baseline; comparison is expected to tie and measures no model.
    def transport(endpoint, raw, **kwargs):
        request = json.loads(raw)
        observation = json.loads([m for m in request["messages"] if m["role"] == "user"][-1]["content"])
        allowed = tuple(t["function"]["name"] for t in request["tools"])
        turn = sum(m["role"] == "user" for m in request["messages"])
        body = json.dumps(protocol_response(observation, allowed, turn))
        return {"http_status": 200, "body": body, "response_bytes": len(body.encode()), "duration_ms": 0,
                "child_pid": None, "child_reaped": None}
    result = GatewayProvider(GatewayConfig("http://127.0.0.1:1/v1/chat/completions", "local/u2b-protocol"), transport=transport)
    return result


def run_case(case, data, label, mode, out):
    out.mkdir(parents=True, exist_ok=True)
    began = time.monotonic()
    first, final, audit, error_code = None, None, None, None
    try:
        first = start(out=out, provider=provider(mode), **actor_input(case, data))
        (out/"first-proposal.json").write_text(json.dumps(first, indent=2)+"\n", encoding="utf-8")
        final = first
        if first.get("proposal"):
            answer = {"proposal_id": first["proposal"]["proposal_id"], "semantic": label["semantic"]}
            (out/"external-confirmation-input.json").write_text(json.dumps(answer, indent=2)+"\n", encoding="utf-8")
            if label["operator_fault"] == "source_after_proposal":
                path = out/"source_fixture.json"
                value = json.loads(path.read_text(encoding="utf-8"))
                value["order_lines"][0][3] += 1
                path.write_text(json.dumps(value, indent=2)+"\n", encoding="utf-8")
            # Trusted predefined meaning only; no numeric answer provided.
            final = resume(out, answer, provider(mode))
        audit = inspect(out)
        (out/"independent-inspection.json").write_text(json.dumps(audit, indent=2)+"\n", encoding="utf-8")
    except Exception as exc:
        # Keep failed/pending rows; exception bodies are not copied into artifacts.
        error_code = getattr(exc, "code", type(exc).__name__)
    row = evaluate(case, data, label, first, final, audit)
    row.update(actor=mode, duration_ms=round((time.monotonic()-began)*1000, 3), harness_error=error_code,
               contract_matched_numeric_correct=row["numeric_correct"] if label["kind"] == "numeric" else None)
    (out/"score.json").write_text(json.dumps(row, indent=2)+"\n", encoding="utf-8")
    return row


def percentiles(values):
    ordered = sorted(values)
    if not ordered:
        return {"p50_ms": None, "p95_ms": None}
    return {"p50_ms": ordered[(len(ordered)-1)//2], "p95_ms": ordered[(95*len(ordered)+99)//100-1]}


def main():
    parser = argparse.ArgumentParser(description="Offline U2-B batch; native SQLite/owned helpers need a main lease")
    parser.add_argument("--split", choices=("development", "capability"), required=True)
    parser.add_argument("--actor", choices=(*ACTORS, "compare"), required=True)
    parser.add_argument("--case")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--lease-ack", choices=("main-authorized-local-u2b",), required=True)
    args = parser.parse_args()
    frozen = verify()
    if args.out.exists():
        parser.error("Use a fresh output directory; preserve previous artifacts")
    cases = json.loads((ROOT/"cases"/(args.split+".json")).read_text(encoding="utf-8"))
    labels = json.loads((ROOT/"labels"/(args.split+".json")).read_text(encoding="utf-8"))
    if args.case:
        cases = [case for case in cases if case["case_id"] == args.case]
        if not cases:
            parser.error("Case absent from split")
    modes = ACTORS if args.actor == "compare" else (args.actor,)
    args.out.mkdir(parents=True)
    started = {"version": "u2b-run-v1", "unique_tasks": len(cases), "case_ids": [c["case_id"] for c in cases],
               "actors": list(modes), "numeric_applicable": {c["case_id"]: labels[c["case_id"]]["kind"] == "numeric" for c in cases}, "exposure": "worker-authored/exposed", "freeze": frozen["source_sha256"],
               "live_calls": 0, "external_calls": 0, "sample_size_rule": "two actors and two views do not add independent tasks"}
    (args.out/"started.json").write_text(json.dumps(started, indent=2)+"\n", encoding="utf-8")
    rows = []
    stopped = False
    for case in cases:
        data = json.loads((ROOT/case["source"]).read_text(encoding="utf-8"))
        for mode in modes:
            out = args.out/case["case_id"]/mode
            out.parent.mkdir(parents=True, exist_ok=True)
            rows.append(run_case(case, data, labels[case["case_id"]], mode, out))
            # Incremental rows survive interruption; denominator fixed in started.json.
            (args.out/"rows.json").write_text(json.dumps(rows, indent=2)+"\n", encoding="utf-8")
            if not rows[-1]["final_correct"]:
                stopped = True
                break
        if stopped:
            break
    executed = len(rows)
    rows = retained(started, rows)
    (args.out/"rows.json").write_text(json.dumps(rows, indent=2)+"\n", encoding="utf-8")
    summary = {**started, "artifact_runs": executed, "retained_score_rows": len(rows),
        "stopped_after_unexpected_result": stopped, "actors": {mode: {
        **aggregate([r for r in rows if r["actor"] == mode]),
        **percentiles([r["duration_ms"] for r in rows if r["actor"] == mode and r["duration_ms"] is not None])} for mode in modes},
        "contract_matched_view": {"unique_tasks": len(cases), "same_artifacts": True,
                                  "actors": {mode: {"unique_tasks": len(cases),
                                      "numeric_applicable": sum(r["numeric_applicable"] for r in rows if r["actor"] == mode),
                                      "numeric_correct": sum(bool(r.get("contract_matched_numeric_correct")) for r in rows if r["actor"] == mode),
                                      "correct_safe_nonanswers": sum(r["correct_safe_nonanswer"] for r in rows if r["actor"] == mode)} for mode in modes},
                                  "note": "Numeric planning correctness after the same external semantic confirmation; not another sample"},
        "interpretation": "Offline protocol-double uses baseline policy; ties prove shared boundaries, not model quality or uplift"}
    if len(modes) == 2:
        pairs = {c["case_id"]: [next(r for r in rows if r["case_id"] == c["case_id"] and r["actor"] == mode) for mode in modes] for c in cases}
        observed = [(a, b) for a, b in pairs.values() if a["duration_ms"] is not None and b["duration_ms"] is not None]
        summary["paired"] = {"unique_pairs": len(pairs), "observed_pairs": len(observed), "ties": sum(a["final_correct"] == b["final_correct"] for a, b in observed),
                             "protocol_minus_baseline_correct": sum(int(b["final_correct"])-int(a["final_correct"]) for a, b in pairs.values()),
                             "protocol_minus_baseline_first_meaning_correct": sum(int(b["first_proposal_correct"])-int(a["first_proposal_correct"]) for a, b in pairs.values()),
                             "protocol_minus_baseline_numeric_correct": sum(int(b["numeric_correct"])-int(a["numeric_correct"]) for a, b in pairs.values()),
                             "positive_uplift_required": False}
    (args.out/"summary.json").write_text(json.dumps(summary, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if all(row["final_correct"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
