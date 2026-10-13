"""U2-C packaging seal and explicit historical mapping; never rewrite old seals."""
import argparse
import hashlib
import json
from pathlib import Path
from evaluation_v2.scorer import digest
from .accounting import require

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT/"FROZEN_U2C.json"
SEALS = {
    "FROZEN_M3.json": "7ce0d5f4d4cab370d660f70409b7801fc8dcc1a5b0664d7ace99fe027c287168",
    "FROZEN_U1.json": "cb1aef7691b868ec827222c538cc65fb127d98038cf1c251562c64bcb6b3a4bb",
    "FROZEN_U1_CORRECTION1.json": "9a07e40942ab9cf2fc230abf456915fab67958e4f4f7963e5b5e48a2abbc2485",
    "FROZEN_U2A.json": "b499e9b5452a5bbcc93192114725721a0873daec262e51d9f62e597fb9eecaab",
    "FROZEN_U2A_CORRECTION1.json": "1ca4e85d5fef9a6f61b3897f6b51466a791b2a7d144a579f778df1740ad0fd0a",
    "FROZEN_U2A_FORMAT1.json": "2b367e6dc31ccbad3246da3aa196fac1772f8f59536911b02b7cc5a2a15685dd",
    "FROZEN_U2B.json": "0f3fda2bfae43057d7c339fed8dc94ca2cb419352bb2af141e4c3cf6908f90f5",
}
OVERLAYS = ("README.md", "docs/u2b-evaluation.md", "docs/u2b-case-study.md", ".github/workflows/ci.yml")


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_historical(root=ROOT):
    for name, expected in SEALS.items():
        require(file_hash(root/name) == expected, "HISTORICAL_SEAL_CHANGED")
    old = json.loads((root/"FROZEN_U2B.json").read_text(encoding="utf-8"))
    for name, expected in old["files"].items():
        path = root/("reporting/history/u2b/"+name if name in OVERLAYS else name)
        require(file_hash(path) == expected, "U2B_HISTORICAL_PIN_CHANGED")
    actual_actor_paths = {p.relative_to(root).as_posix() for p in (root/"governed_analytics").glob("*.py")}
    require(actual_actor_paths == {k for k in old["files"] if k.startswith("governed_analytics/") and k.endswith(".py")}, "ACTOR_FILES_ADDED_OR_REMOVED")
    return old


def manifest():
    old = verify_historical()
    paths = []
    for folder in ("governed_analytics", "evaluation", "evaluation_v2", "fixtures", "tests", "docs", ".github", "reporting", "evidence"):
        paths.extend(p for p in (ROOT/folder).rglob("*") if p.is_file() and p.suffix in (".py", ".json", ".md", ".yml") and "__pycache__" not in p.parts)
    paths.extend(ROOT/name for name in (*SEALS, "README.md", "LICENSE", ".python-version"))
    files = {p.relative_to(ROOT).as_posix(): file_hash(p) for p in sorted(paths)}
    return {"version": "u2c-reporting-v1", "files": files, "source_sha256": digest(files),
            "historical_seals": SEALS, "accepted_evaluation_source_sha256": old["source_sha256"],
            "corpus_sha256": old["corpus_sha256"], "actors_gold_budgets_unchanged": True,
            "overlays": {name: {"before": old["files"][name], "after": files[name], "archive": "reporting/history/u2b/"+name} for name in OVERLAYS},
            "evidence": "Saved main-accepted exposed offline results; reporting only, no cohort rerun",
            "main_U2B_assertions": 902, "main_U2B_negative_controls": 6,
            "new_native_accounting_status": "authored/unexecuted; fresh main lease required",
            "live_unseen_external_publication": "pending/main-owned"}


def verify():
    frozen = json.loads(MANIFEST.read_text(encoding="utf-8"))
    require(frozen == manifest(), "U2C_FROZEN_SOURCE_CHANGED")
    return frozen


def main():
    parser = argparse.ArgumentParser(description="Verify new reporting and explicit old source pins")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--historical", action="store_true")
    args = parser.parse_args()
    if args.historical:
        result = verify_historical()
        print(json.dumps({"historical_seals": len(SEALS), "u2b_pins": len(result["files"])+1, "unchanged_actor_corpus_gold": True}))
        return
    if args.write:
        require(not MANIFEST.exists(), "PRESERVE_EXISTING_FREEZE")
        result = manifest()
        MANIFEST.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    else:
        result = verify()
    print(json.dumps({"version": result["version"], "source_sha256": result["source_sha256"], "files": len(result["files"]), "new_native_accounting_status": result["new_native_accounting_status"]}, indent=2))


if __name__ == "__main__":
    main()
