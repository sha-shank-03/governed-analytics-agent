"""Freeze and verify source/input hashes without executing or scoring an actor."""
import argparse
import hashlib
import json
from pathlib import Path
from .metrics import digest

ROOT=Path(__file__).resolve().parent.parent
MANIFEST=ROOT/"FROZEN_M3.json"


def source_hashes(root=ROOT):
    paths=[]
    for directory in ("governed_analytics","evaluation","fixtures"):
        paths.extend(path for path in (root/directory).rglob("*") if path.is_file() and path.suffix in (".py",".json") and "__pycache__" not in path.parts)
    paths.extend(root/name for name in (".github/workflows/ci.yml",".python-version") if (root/name).exists())
    return {path.relative_to(root).as_posix():hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(paths)}


def manifest(root=ROOT,version="m3-v1"):
    files=source_hashes(root)
    actor={name:value for name,value in files.items() if name.startswith("governed_analytics/") or name.startswith("fixtures/")}
    benchmark={name:value for name,value in files.items() if name.startswith("evaluation/")}
    return {"version":version,"evidence_kind":"authored_scripted_workflow","files":files,
            "actor_sha256":digest(actor),"baseline_sha256":digest(actor),"benchmark_sha256":digest(benchmark),
            "baseline_binding":"Same provider/host code, workflow_mode=one_pass_sql; one candidate, no verification/channel investigation.",
            "heldout_case_count":36,"expected_numeric_completions":24,"expected_non_answer_outcomes":12,
            "score_created":False,"heldout_author_knowledge":"Author knows cases; held out only from actor context/development inputs, not an independent secret benchmark."}


def verify(root=ROOT, path=MANIFEST):
    frozen=json.loads(path.read_text(encoding="utf-8"))
    current=manifest(root,frozen["version"])
    if frozen!=current:
        raise ValueError("FROZEN_SOURCE_CHANGED")
    return frozen


def main(argv=None):
    parser=argparse.ArgumentParser()
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write",action="store_true")
    mode.add_argument("--verify",action="store_true")
    parser.add_argument("--manifest",type=Path,default=MANIFEST)
    parser.add_argument("--version",default="m3-v1")
    args=parser.parse_args(argv)
    if args.write:
        if args.manifest.exists():
            parser.error("Existing freeze is preserved; explicit new version/review required before replacing it")
        if not args.version.startswith("m3-v") or not args.version[4:].isdigit():
            parser.error("Version must be m3-v followed by an integer")
        frozen=manifest(version=args.version)
        args.manifest.write_text(json.dumps(frozen,indent=2)+"\n",encoding="utf-8")
    else:
        frozen=verify(path=args.manifest)
    print(json.dumps({key:frozen[key] for key in ("version","actor_sha256","baseline_sha256","benchmark_sha256","heldout_case_count","score_created")},indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
