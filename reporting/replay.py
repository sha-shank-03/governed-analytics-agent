"""Rebuild public summaries from the sealed redacted snapshot, without execution."""
import argparse
import json
from pathlib import Path
from .accounting import ACTORS, hash_value, require
from .export import Reader, summaries, markdown, domain, ROOT
from .freeze import verify, verify_historical


def check(snapshot, cases, labels, sources, frozen):
    require(snapshot["version"] == "u2c-observed-v1" and snapshot["evaluation_source_sha256"] == frozen["source_sha256"] and snapshot["corpus_sha256"] == frozen["corpus_sha256"], "SNAPSHOT_SOURCE_CONTEXT")
    attempts = snapshot["attempts"]
    expected = {(case, actor) for case in cases for actor in ACTORS}
    require(type(attempts) is list and len(attempts) == len(expected) <= 84, "SNAPSHOT_DENOMINATOR")
    seen = set()
    for item in attempts:
        key = (item["case_id"], item["actor"])
        require(key in expected and key not in seen, "SNAPSHOT_DUPLICATE_OR_UNKNOWN_ATTEMPT")
        seen.add(key)
        case, label = cases[key[0]], labels[key[0]]
        require(item["split"] == case["split"] and item["numeric_applicable"] is (label["kind"] == "numeric"), "SNAPSHOT_CASE_CONTEXT")
        require(item["state"] in ("terminal", "STARTED", "interrupted_unknown", "unexecuted", "execution_unknown") and item["scoring"] in ("correct", "incorrect", "unknown"), "SNAPSHOT_LIFECYCLE")
        for metric in ("input_tokens", "output_tokens", "actual_cost_usd", "estimated_cost_usd"):
            require(item[metric] is None, "SNAPSHOT_UNKNOWN_USAGE_COST")
        if item["scoring"] == "unknown":
            require(all(item[k] is None for k in ("first_proposal_correct", "numeric_correct", "correct_safe_nonanswer", "unsafe_action", "synthetic_confirmation_attempts", "synthetic_accepted_confirmations", "synthetic_semantic_corrections", "clarification_count")), "UNKNOWN_CANNOT_PASS")
        else:
            require(item["state"] == "terminal", "SCORING_REQUIRES_TERMINAL")
            require(all(type(item[k]) is bool for k in ("first_proposal_correct", "numeric_correct", "correct_safe_nonanswer", "synthetic_or_handoff_task")), "SNAPSHOT_TYPED_SCORE")
            require(all(type(item[k]) is int and 0 <= item[k] <= 1 for k in ("synthetic_confirmation_attempts", "synthetic_accepted_confirmations", "synthetic_semantic_corrections", "clarification_count")), "SNAPSHOT_TYPED_CONFIRMATION")
        if item["numeric_correct"] is True:
            require(label["kind"] == "numeric" and item["scoring"] == "correct", "SNAPSHOT_NUMERIC_APPLICABILITY")
            rows, summary = domain(sources[key[0]], label["semantic"])
            require(item["numeric_summary"] == summary and item["evidence_rows"] == rows, "SNAPSHOT_RAW_CENTS")
            require(all(type(item["numeric_summary"][k]) is int for k in ("previous_cents", "current_cents", "delta_cents")) and all(type(v) is int for v in item["numeric_summary"]["channel_deltas_cents"].values()) and all(type(r[2]) is int for group in item["evidence_rows"].values() for r in group), "SNAPSHOT_INTEGER_CENTS")
            require({k: item["contract"][k] for k in ("metric", "periods", "regions", "currency", "groupings")} == {k: label["semantic"][k] for k in ("metric", "periods", "regions", "currency", "groupings")} and item["contract"]["as_of"] == sources[key[0]]["as_of"] and hash_value(item["contract"]["contract_id"]), "SNAPSHOT_CONTRACT")
        if item["correct_safe_nonanswer"] is True:
            require(label["kind"] == "safe" and item["scoring"] == "correct" and item["numeric_summary"] is None and item["evidence_rows"] is None, "SNAPSHOT_SAFE_OUTCOME")
        require(type(item["raw_artifact_sha256"]) is dict and all(hash_value(value) for value in item["raw_artifact_sha256"].values()), "SNAPSHOT_RAW_HASHES")
    require(snapshot["summary"] == summaries(attempts), "SNAPSHOT_SUMMARY_CONTRADICTION")
    return snapshot["summary"]


def main():
    parser = argparse.ArgumentParser(description="Verify/replay sealed saved JSON; no native work")
    parser.add_argument("--snapshot", type=Path, default=ROOT/"evidence/u2b/observed.json")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    current = verify()
    old = verify_historical()
    reader = Reader()
    raw = reader.bytes(args.snapshot, "snapshot")
    require(reader.hashes["snapshot"] == current["files"]["evidence/u2b/observed.json"], "UNSEALED_SNAPSHOT")
    from .export import decode
    snapshot = decode(raw)
    require(snapshot["exporter_sha256"] == current["files"]["reporting/export.py"], "SNAPSHOT_EXPORTER_CONTEXT")
    cases, labels, sources = {}, {}, {}
    for split in ("development", "capability"):
        split_cases = reader.json(ROOT/"evaluation_v2/cases"/(split+".json"), "cases/"+split)
        labels.update(reader.json(ROOT/"evaluation_v2/labels"/(split+".json"), "labels/"+split))
        for case in split_cases:
            cases[case["case_id"]] = case
            sources[case["case_id"]] = reader.json(ROOT/"evaluation_v2"/case["source"], "source/"+case["case_id"])
    summary = check(snapshot, cases, labels, sources, old)
    if args.out:
        require(not args.out.exists(), "OUTPUT_EXISTS")
        args.out.mkdir(parents=True)
        (args.out/"summary.json").write_text(json.dumps(summary, indent=2)+"\n", encoding="utf-8")
        (args.out/"observed.md").write_text(markdown(snapshot), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return int(any(item["scoring"] == "unknown" for item in snapshot["attempts"]))


if __name__ == "__main__":
    raise SystemExit(main())
