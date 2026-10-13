"""Pure summarization of saved score rows, retaining every frozen pending task."""
import argparse
import json
from pathlib import Path
from .scorer import aggregate


def retained(started, rows):
    keys = [(case, actor) for case in started["case_ids"] for actor in started["actors"]]
    mapping = {}
    for row in rows:
        key = (row["case_id"], row["actor"])
        if key not in keys or key in mapping:
            raise ValueError("UNEXPECTED_OR_DUPLICATE_SCORE_ROW")
        mapping[key] = row
    output = []
    for case, actor in keys:
        output.append(mapping.get((case, actor), {"case_id": case, "actor": actor,
            "reported_status": "pending", "numeric_applicable": started["numeric_applicable"][case],
            "first_proposal_correct": False, "final_correct": False, "numeric_correct": False,
            "correct_safe_nonanswer": False, "unsafe_action": False, "unsafe_action_known": False, "confirmation_count": 0,
            "semantic_correction_count": 0, "errors": ["NOT_FINISHED"], "duration_ms": None}))
    return output


def main():
    parser = argparse.ArgumentParser(description="Read retained scores; no SQLite, subprocess or network")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    started = json.loads((args.out/"started.json").read_text(encoding="utf-8"))
    path = args.out/"rows.json"
    rows = retained(started, json.loads(path.read_text(encoding="utf-8")) if path.exists() else [])
    print(json.dumps({"unique_tasks": started["unique_tasks"], "actors": {
        actor: aggregate([r for r in rows if r["actor"] == actor]) for actor in started["actors"]}}, indent=2))


if __name__ == "__main__":
    main()
