"""Bounded redacted export from saved artifacts; no SQLite queries or actor runs."""
import argparse
import hashlib
import json
import math
from pathlib import Path
from evaluation_v2.scorer import evaluate, digest, domain
from .accounting import ACTORS, TERMINAL, ReportingError, require, validate, lifecycle

ROOT = Path(__file__).resolve().parent.parent
U2B_SEAL_SHA = "0f3fda2bfae43057d7c339fed8dc94ca2cb419352bb2af141e4c3cf6908f90f5"
MAX_FILE = 1048576
MAX_TOTAL = 67108864


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def decode(raw):
    require(type(raw) is bytes and len(raw) <= MAX_FILE, "JSON_TOO_LARGE")
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "DUPLICATE_JSON_KEY")
            result[key] = value
        return result
    def constant(_):
        raise ReportingError("NONFINITE_JSON")
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        if type(exc) is ReportingError:
            raise
        raise ReportingError("INVALID_JSON") from None


class Reader:
    def __init__(self):
        self.total = 0
        self.hashes = {}

    def bytes(self, path, key, cap=MAX_FILE):
        try:
            require(path.is_file() and path.stat().st_size <= cap, "MISSING_OR_OVERSIZED_FILE")
            with path.open("rb") as stream:
                raw = stream.read(cap+1)
        except OSError:
            raise ReportingError("INPUT_UNAVAILABLE") from None
        require(len(raw) <= cap and self.total+len(raw) <= MAX_TOTAL, "INPUT_BYTE_BUDGET")
        self.total += len(raw)
        self.hashes[key] = sha(raw)
        return raw

    def json(self, path, key):
        return decode(self.bytes(path, key))


def empty_attempt(case, actor, life):
    return {"case_id": case["case_id"], "split": case["split"], "actor": actor,
            **life, "numeric_applicable": None, "scoring": "unknown", "errors": [],
            "first_proposal_correct": None, "clarification_count": None,
            "synthetic_confirmation_attempts": None, "synthetic_accepted_confirmations": None,
            "synthetic_semantic_corrections": None, "synthetic_or_handoff_task": None,
            "numeric_correct": None, "correct_safe_nonanswer": None, "unsafe_action": None,
            "duration_ms": None, "input_tokens": None, "output_tokens": None,
            "actual_cost_usd": None, "estimated_cost_usd": None,
            "numeric_summary": None, "contract": None, "evidence_rows": None}


def summarize_attempt(case, data, label, first, report, audit, saved_score, life):
    """Pure projection: untrusted payload text is never copied into public fields."""
    result = empty_attempt(case, saved_score.get("actor") if type(saved_score) is dict else None, life)
    result["numeric_applicable"] = label["kind"] == "numeric"
    if life["state"] != "terminal":
        result["errors"] = ["NO_TERMINAL_EVIDENCE"]
        return result
    try:
        require(type(report) is dict and type(audit) is dict and type(first) is dict and type(saved_score) is dict, "MISSING_SCORING_EVIDENCE")
        fresh = evaluate(case, data, label, first, report, audit)
        for key in ("final_correct", "numeric_correct", "correct_safe_nonanswer", "first_proposal_correct", "unsafe_action", "unsafe_action_known", "confirmation_count", "accepted_confirmation_count", "clarification_count", "semantic_correction_count"):
            require(type(saved_score.get(key)) is type(fresh[key]) and saved_score[key] == fresh[key], "SCORE_EVIDENCE_CONTRADICTION")
        require(saved_score["case_id"] == case["case_id"] and saved_score["actor"] in ACTORS and saved_score["numeric_applicable"] is result["numeric_applicable"], "SCORE_CONTEXT")
        require(fresh["errors"] == saved_score["errors"], "SCORE_ERROR_CONTRADICTION")
        require(report["metrics"]["input_tokens"] is None and report["metrics"]["output_tokens"] is None and report["metrics"]["actual_cost_usd"] is None and report["metrics"]["estimated_cost_usd"] is None, "OFFLINE_USAGE_COST_NOT_UNKNOWN")
        result.update(scoring="correct" if fresh["final_correct"] else "incorrect",
            errors=fresh["errors"], first_proposal_correct=fresh["first_proposal_correct"],
            numeric_correct=fresh["numeric_correct"], correct_safe_nonanswer=fresh["correct_safe_nonanswer"],
            clarification_count=fresh["clarification_count"], synthetic_confirmation_attempts=fresh["confirmation_count"],
            synthetic_accepted_confirmations=fresh["accepted_confirmation_count"], synthetic_semantic_corrections=fresh["semantic_correction_count"],
            synthetic_or_handoff_task=bool(fresh["confirmation_count"] or report["status"] == "handoff"),
            unsafe_action=fresh["unsafe_action"] if fresh["unsafe_action_known"] else None)
        duration = saved_score.get("duration_ms")
        require(type(duration) in (int, float) and math.isfinite(duration) and 0 <= duration <= 1000000, "INVALID_DURATION")
        result["duration_ms"] = duration
        if report.get("summary") is not None and fresh["numeric_correct"]:
            result["numeric_summary"] = {key: report["summary"][key] for key in ("previous_cents", "current_cents", "delta_cents", "percent_change", "channel_deltas_cents")}
            result["contract"] = {key: report["contract"][key] for key in ("metric", "periods", "regions", "currency", "groupings", "as_of", "contract_id")}
            result["evidence_rows"] = {group: report["evidence"][group]["rows"] for group in ("none", "channel")}
    except (KeyError, TypeError, ValueError, ArithmeticError):
        # An absent or contradictory audit is a reporting unknown, never a pass.
        result = empty_attempt(case, result["actor"], life)
        result.update(numeric_applicable=label["kind"] == "numeric", errors=["MISSING_MALFORMED_OR_CONTRADICTORY_SCORING_EVIDENCE"])
    return result


def aggregate(attempts):
    states, native = {}, {}
    for item in attempts:
        states[item["state"]] = states.get(item["state"], 0)+1
        if item["terminal_status"] is not None:
            native[item["terminal_status"]] = native.get(item["terminal_status"], 0)+1
    known = [i for i in attempts if i["scoring"] != "unknown"]
    numeric = sum(i["numeric_applicable"] is True for i in attempts)
    durations = sorted(i["duration_ms"] for i in known if i["duration_ms"] is not None)
    unsafe_known = [i for i in known if i["unsafe_action"] is not None]
    return {"unique_tasks": len({i["case_id"] for i in attempts}), "intended_attempts": len(attempts),
        "lifecycle_counts": states, "terminal_native_status_counts": native,
        "scored_correct": sum(i["scoring"] == "correct" for i in attempts),
        "scored_incorrect": sum(i["scoring"] == "incorrect" for i in attempts), "scoring_unknown": len(attempts)-len(known),
        "numeric_applicable": numeric, "numeric_correct": sum(i["numeric_correct"] is True for i in known),
        "correct_safe_nonanswers": sum(i["correct_safe_nonanswer"] is True for i in known),
        "first_proposal_correct": sum(i["first_proposal_correct"] is True for i in known),
        "clarification_tasks": sum(i["clarification_count"] for i in known),
        "synthetic_confirmation_attempts": sum(i["synthetic_confirmation_attempts"] for i in known),
        "synthetic_accepted_confirmations": sum(i["synthetic_accepted_confirmations"] for i in known),
        "synthetic_semantic_corrections": sum(i["synthetic_semantic_corrections"] for i in known),
        "synthetic_or_handoff_tasks": sum(i["synthetic_or_handoff_task"] for i in known),
        "human_approvals_collected": 0, "unsafe_actions_observed": sum(i["unsafe_action"] is True for i in unsafe_known),
        "unsafe_action_unknown": len(attempts)-len(unsafe_known),
        "latency_observations": len(durations),
        "p50_ms": durations[(len(durations)-1)//2] if durations else None,
        "p95_ms": durations[(95*len(durations)+99)//100-1] if durations else None,
        "input_tokens": None, "output_tokens": None, "actual_cost_usd": None, "estimated_cost_usd": None,
        "actual_cost_per_numeric_success_usd": None}


def summaries(attempts):
    actors = {actor: aggregate([i for i in attempts if i["actor"] == actor]) for actor in ACTORS}
    split = {name: {actor: aggregate([i for i in attempts if i["split"] == name and i["actor"] == actor]) for actor in ACTORS} for name in ("development", "capability")}
    pairs = []
    for case in sorted({i["case_id"] for i in attempts}):
        pair = [i for i in attempts if i["case_id"] == case]
        if len(pair) == 2 and all(i["scoring"] != "unknown" for i in pair):
            pairs.append(pair)
    return {"unique_tasks": len({i["case_id"] for i in attempts}), "actor_attempts": len(attempts), "actors": actors,
        "splits": split, "observed_pairs": len(pairs), "same_policy_ties": sum(a["scoring"] == b["scoring"] for a, b in pairs),
        "contract_matched_view": "Same attempts after expert semantic confirmation; no additional sample count",
        "interpretation": "Both arms share one deterministic policy; ties measure execution consistency, not reasoning uplift"}


def safe_review(review, raw_sha):
    require(type(review) is dict and review.get("status") == "u2b_offline_exposed_contract_passed" and review["source"]["manifest_sha256"] == U2B_SEAL_SHA, "REVIEW_SOURCE_CONTEXT")
    require(review.get("final_upgrade_acceptance") is False, "REVIEW_SCOPE")
    commands = review["execution"]["commands"]
    require(len(commands) == 12 and all(c["exit_code"] == c["expected_exit"] == 0 for c in commands), "REVIEW_EXECUTION")
    return {"original_receipt_sha256": raw_sha, "status": "main-accepted exposed offline contract only",
        "commands_passed": 12, "independent_assertions": review["independent_assertions"], "negative_controls": review["negative_controls"],
        "source_pins_unchanged": review["source"]["pinned_files"], "final_upgrade_acceptance": False,
        "live_model_calls": 0, "actual_external_sandbox_calls": 0,
        "sampled_tree_plus_main_rss_bytes": review["postflight"]["sampled_peak_tree_plus_main_rss_bytes"],
        "sampling_errors": review["postflight"]["sampling_errors"], "lifetime_peak_guaranteed": False,
        "generated_output_bytes": review["postflight"]["generated_bytes"], "transient_regression_fixture_peak_measured": False,
        "partial_summary_suspicion": "did not reproduce; not a confirmed bug"}


def read_batch(reader, path, split, frozen):
    cases = reader.json(ROOT/"evaluation_v2/cases"/(split+".json"), "corpus/"+split)
    labels = reader.json(ROOT/"evaluation_v2/labels"/(split+".json"), "labels/"+split)
    started = reader.json(path/"started.json", split+"/started.json")
    require(started["case_ids"] == [c["case_id"] for c in cases] and started["actors"] == list(ACTORS) and started["freeze"] == frozen["source_sha256"], "BATCH_SOURCE_CONTEXT")
    require(started["numeric_applicable"] == {c["case_id"]: labels[c["case_id"]]["kind"] == "numeric" for c in cases}, "BATCH_DENOMINATOR")
    ledger_path = path/"attempts.json"
    ledger = validate(reader.json(ledger_path, split+"/attempts.json")) if ledger_path.exists() else None
    if ledger:
        from .freeze import verify
        require(ledger["source_sha256"] == verify()["source_sha256"], "LEDGER_SOURCE_CONTEXT")
        require({(i["case_id"], i["actor"]) for i in ledger["attempts"]} == {(c["case_id"], a) for c in cases for a in ACTORS}, "LEDGER_DENOMINATOR")
    records = {(i["case_id"], i["actor"]): i for i in ledger["attempts"]} if ledger else {}
    attempts = []
    for case in cases:
        data = reader.json(ROOT/"evaluation_v2"/case["source"], "corpus/"+case["case_id"])
        for actor in ACTORS:
            out = path/case["case_id"]/actor
            prefix = split+"/"+case["case_id"]+"/"+actor+"/"
            report = first = audit = score = None
            error = None
            try:
                report = reader.json(out/"report.json", prefix+"report.json")
                first = reader.json(out/"first-proposal.json", prefix+"first-proposal.json")
                audit = reader.json(out/"independent-inspection.json", prefix+"independent-inspection.json")
                score = reader.json(out/"score.json", prefix+"score.json")
                require(audit["checkpoint"] == reader.json(out/"checkpoint.json", prefix+"checkpoint.json"), "CHECKPOINT_CHANGED")
                require(audit["source_fixture"] == reader.json(out/"source_fixture.json", prefix+"source_fixture.json"), "SOURCE_CHANGED")
                if audit.get("external_confirmation_input") is not None:
                    require(audit["external_confirmation_input"] == reader.json(out/"external-confirmation-input.json", prefix+"external-confirmation-input.json"), "CONFIRMATION_INPUT_CHANGED")
                for name, cap in (("source_fixture.json", MAX_FILE), ("scoped.sqlite", 4194304)):
                    require(sha(reader.bytes(out/name, prefix+name, cap)) == audit["file_hashes"][name], "ARTIFACT_FILE_CHANGED")
                events = reader.bytes(out/"events.jsonl", prefix+"events.jsonl")
                require([decode(line) for line in events.splitlines()] == audit["events"], "EVENTS_CHANGED")
                require(audit["expected_code_hash"] == digest({Path(k).name: v for k, v in frozen["files"].items() if k.startswith("governed_analytics/") and k.endswith(".py")}), "ACTOR_CODE_CONTEXT")
            except (KeyError, TypeError, ValueError, OSError):
                error = "MISSING_MALFORMED_OR_CHANGED_RAW_ARTIFACT"
            record = records.get((case["case_id"], actor))
            status = report.get("status") if type(report) is dict else None
            life = lifecycle(record, closed=True, legacy_status=status, legacy_artifact_present=out.exists())
            item = summarize_attempt(case, data, labels[case["case_id"]], first, report, audit, score, life)
            item["actor"] = actor
            if error:
                item = empty_attempt(case, actor, life)
                item.update(numeric_applicable=labels[case["case_id"]]["kind"] == "numeric", errors=[error])
            if record and record["state"] == "TERMINAL" and (reader.hashes.get(prefix+"report.json") != record["report_sha256"] or reader.hashes.get(prefix+"score.json") != record["score_sha256"]):
                item = empty_attempt(case, actor, life)
                item.update(numeric_applicable=labels[case["case_id"]]["kind"] == "numeric", errors=["TERMINAL_BINDING_CHANGED"])
            item["raw_artifact_sha256"] = {key[len(prefix):]: value for key, value in reader.hashes.items() if key.startswith(prefix)}
            attempts.append(item)
    return attempts


def make_snapshot(development, capability, review_path):
    from .freeze import verify_historical
    frozen = verify_historical()
    reader = Reader()
    review = reader.json(review_path, "main-review")
    header = safe_review(review, reader.hashes["main-review"])
    attempts = read_batch(reader, development, "development", frozen)+read_batch(reader, capability, "capability", frozen)
    return {"version": "u2c-observed-v1", "evidence_kind": "saved authored/exposed offline artifacts",
        "evaluation_manifest_sha256": U2B_SEAL_SHA, "evaluation_source_sha256": frozen["source_sha256"],
        "corpus_sha256": frozen["corpus_sha256"], "exporter_sha256": sha(Path(__file__).read_bytes()),
        "main_review": header, "attempts": attempts, "summary": summaries(attempts),
        "raw_input_bytes_read": reader.total, "raw_input_sha256": reader.hashes,
        "human_confirmation_kind": "trusted synthetic fixture answers; zero collected human approvals",
        "limitations": ["Both splits exposed; no main-held unseen tasks", "Same-policy protocol wrapper; no reasoning uplift", "No actual BigQuery/IAM/billing sandbox or live model", "Unknown actual tokens/cost remain null", "No new SQLite query or task execution; saved inspections and file bytes were revalidated", "Sampled resource evidence is not a lifetime peak guarantee"]}


def markdown(snapshot):
    summary = snapshot["summary"]
    lines = ["# Observed offline analytics contract", "", f"{summary['unique_tasks']} authored/exposed tasks; {summary['actor_attempts']} intended actor attempts. Main's historical acceptance covers the exposed offline contract only. This export has {summary['observed_pairs']} scorable pairs and {summary['same_policy_ties']} same-policy ties. These measure execution consistency.", "",
             "| Split (unique tasks) | Numeric completions, baseline | Correct safe non-answers, baseline | First meaning correct | Clarification / synthetic corrections | Synthetic confirmations attempted / accepted |",
             "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for split in ("development", "capability"):
        item = summary["splits"][split][ACTORS[0]]
        lines.append(f"| {split} ({item['unique_tasks']}) | {item['numeric_correct']}/{item['numeric_applicable']} | {item['correct_safe_nonanswers']} | {item['first_proposal_correct']}/{item['unique_tasks']} | {item['clarification_tasks']} / {item['synthetic_semantic_corrections']} | {item['synthetic_confirmation_attempts']} / {item['synthetic_accepted_confirmations']} |")
    for actor in ACTORS:
        a = summary["actors"][actor]
        lines.extend(["", f"`{actor}`: {a['numeric_correct']}/{a['numeric_applicable']} numeric completions, {a['correct_safe_nonanswers']} correct safe non-answers; {a['scoring_unknown']} attempts have unknown scoring. {a['synthetic_semantic_corrections']} synthetic semantic corrections; {a['synthetic_confirmation_attempts']} confirmation attempts, {a['synthetic_accepted_confirmations']} accepted. Local harness latency p50/p95: {a['p50_ms']} / {a['p95_ms']} ms over {a['latency_observations']} observations."])
    lines.extend(["", "No human approvals were collected. Contract-matched results use the same attempts and add no independent tasks.", "", "Actual input/output tokens, estimated/actual cost and cost per successful task: **null / unavailable**. No measured inference cost is claimed.", "", "Native terminal status can be `failed` for an expected tamper stop. Lifecycle, numerical completion and independent scoring are separate fields. Missing evidence yields unknown scoring; unexecuted attempts are not failures.", "", "Historical main review: 12 commands passed, 902 independent assertions and six negative controls passed; all 139 source pins unchanged. RSS was sampled with 21 sampling races/errors. Lifetime peaks and transient regression fixture peaks were not established.", "", "Live model, genuine BigQuery/IAM/billing sandbox, main-held unseen acceptance and publication remain pending. The partial-summary suspicion did not reproduce and is not a confirmed bug.", ""])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Export saved JSON/file hashes; never execute analytics")
    parser.add_argument("--development", type=Path, required=True)
    parser.add_argument("--capability", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    require(not args.out.exists(), "OUTPUT_EXISTS")
    result = make_snapshot(args.development, args.capability, args.review)
    args.out.mkdir(parents=True)
    (args.out/"observed.json").write_text(json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    (args.out/"observed.md").write_text(markdown(result), encoding="utf-8")
    print(json.dumps(result["summary"], indent=2))
    return int(any(i["scoring"] == "unknown" for i in result["attempts"]))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ReportingError as exc:
        print(json.dumps({"status": "reporting_rejected", "reason": str(exc)}))
        raise SystemExit(2)
    except (KeyError, TypeError, OSError, ValueError):
        print(json.dumps({"status": "reporting_rejected", "reason": "MALFORMED_OR_UNAVAILABLE_INPUT"}))
        raise SystemExit(2)
