"""Versioned U2-B freeze; preserve v1/U1/U2-A manifests and explicit CI overlay."""
import argparse
import hashlib
import json
from pathlib import Path
from .scorer import digest

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT/"FROZEN_U2B.json"


def source_hashes(root=ROOT):
    paths = []
    for directory in ("governed_analytics", "evaluation", "evaluation_v2", "fixtures", "tests", "docs", ".github"):
        paths.extend(p for p in (root/directory).rglob("*") if p.is_file() and p.suffix in (".py", ".json", ".md", ".yml") and "__pycache__" not in p.parts)
    paths.extend(root/name for name in ("README.md", "LICENSE", ".python-version", "FROZEN_M3.json", "FROZEN_U1.json", "FROZEN_U1_CORRECTION1.json", "FROZEN_U2A.json", "FROZEN_U2A_CORRECTION1.json", "FROZEN_U2A_FORMAT1.json") if (root/name).exists())
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def manifest():
    files = source_hashes()
    return {"version": "u2b-source-v1", "files": files, "source_sha256": digest(files),
            "baseline_sha256": files["governed_analytics/deterministic_v2.py"],
            "prompt_sha256": files["governed_analytics/upgrade_gateway.py"],
            "scorer_sha256": files["evaluation_v2/scorer.py"],
            "corpus_sha256": digest({k: v for k, v in files.items() if k.startswith(("evaluation_v2/cases/", "evaluation_v2/labels/", "evaluation_v2/sources/"))}),
            "integration_batch_sha256": files["evaluation_v2/INTEGRATION_BATCH.json"],
            "unique_development": 18, "unique_capability": 24, "original_tasks": 48,
            "worker_exposure": "authored/exposed", "main_unseen_acceptance": "absent/private/unassigned",
            "scored": False, "executed_before_freeze": "Only static/light pure checks; no U2-B native or evaluation run",
            "native_and_demo_status": "authored/unexecuted; fresh main lease required", "live_calls": 0, "external_calls": 0,
            "legacy_ci_overlay": "Only frozen v1 CI file is versioned; original bytes in evaluation_v2/legacy_ci.yml. v1 app/corpus/freezes unchanged."}


def verify():
    frozen = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if frozen != manifest():
        raise ValueError("U2B_FROZEN_SOURCE_CHANGED")
    return frozen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if args.write:
        if MANIFEST.exists():
            parser.error("Preserve freeze; correction requires a new reviewed version")
        result = manifest()
        MANIFEST.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    else:
        result = verify()
    print(json.dumps({k: result[k] for k in ("version", "source_sha256", "unique_development", "unique_capability", "scored", "native_and_demo_status")}, indent=2))


if __name__ == "__main__":
    main()
