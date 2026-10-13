"""Reconstruct the original frozen app/benchmark for historical CI reproduction."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEGACY_TESTS = ("tests/__init__.py", "tests/unit/__init__.py", "tests/integration/__init__.py",
                "tests/unit/test_m1_unit.py", "tests/unit/test_m2_unit.py", "tests/unit/test_m3_unit.py",
                "tests/integration/test_m1_integration.py", "tests/integration/test_m2_integration.py")


def original_files():
    frozen = json.loads((ROOT/"FROZEN_M3.json").read_text(encoding="utf-8"))
    result = {}
    for name, expected in frozen["files"].items():
        source = ROOT/("evaluation_v2/legacy_ci.yml" if name == ".github/workflows/ci.yml" else name)
        if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
            raise ValueError("V1_FILE_CHANGED: "+name)
        result[name] = source
    return result


def main():
    parser = argparse.ArgumentParser(description="Verify v1 file mapping or copy it for isolated reproduction")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    files = original_files()
    if args.out is not None:
        if args.out.exists():
            parser.error("Preserve previous reconstruction; use fresh output")
        for name, source in files.items():
            dest = args.out/name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)
        for name in (*LEGACY_TESTS, "FROZEN_M3.json", "LICENSE"):
            dest = args.out/name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT/name, dest)
    print(json.dumps({"v1_manifest_files_verified": len(files), "copied": args.out is not None,
                      "workflow_executed": False}))


if __name__ == "__main__":
    main()
