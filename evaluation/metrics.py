"""Pure output normalization and explicit-denominator comparison metrics."""
import hashlib
import json
import statistics


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()


def normalized_domain(report):
    candidate = report.get("baseline_candidate") or {}
    return {"status":report["status"],"reason":report.get("reason"),"contract":report.get("contract"),
            "summary":report.get("summary"),"evidence":report.get("evidence",{}),"budgets":report.get("budgets",{}),
            "baseline":{key:candidate.get(key) for key in ("ok","error","metric","grouping","rows","verification")}}


def counts(rows):
    def fraction(key):
        applicable=[row[key] for row in rows if row.get(key) is not None]
        return {"passed":sum(bool(value) for value in applicable),"applicable":len(applicable)}
    times=[row["elapsed_seconds"] for row in rows]
    return {"task_success":sum(row["task_success"] for row in rows),"tasks":len(rows),
            "numeric_correct":sum(bool(row["numeric_correct"]) for row in rows if row.get("numeric_correct") is not None),
            "numeric_tasks":sum(row.get("numeric_correct") is not None for row in rows),
            "safety_passed":sum(row["safety_passed"] for row in rows),"safety_tasks":len(rows),
            "metric_period_scope":fraction("metric_period_scope_correct"),"clarification":fraction("clarification_correct"),
            "candidate_queries":sum(row.get("candidate_queries",0) for row in rows),
            "reference_queries":sum(row.get("reference_queries",0) for row in rows),
            "durations_seconds":{"min":min(times),"median":statistics.median(times),"max":max(times)} if times else None}


def summarize_records(records, repeats):
    result={}
    for mode in sorted({row["mode"] for row in records}):
        rows=[row for row in records if row["mode"]==mode]
        groups={case:[row for row in rows if row["case_id"]==case] for case in sorted({row["case_id"] for row in rows})}
        result[mode]={"aggregate":counts(rows),
            "per_repeat":{str(repeat):counts([row for row in rows if row["repeat"]==repeat]) for repeat in range(1,repeats+1)},
            "per_family":{family:counts([row for row in rows if row["family"]==family]) for family in sorted({row["family"] for row in rows})},
            "normal_workflow":counts([row for row in rows if not row.get("fault_challenge",row["fault_injected"])]),
            "fault_challenge":counts([row for row in rows if row.get("fault_challenge",row["fault_injected"])]),
            "repeatability":{"measured":repeats==3,"cases":len(groups),
                "identical_cases":sum(len(group)==repeats and len({row["normalized_domain_sha256"] for row in group})==1 for group in groups.values()) if repeats==3 else None}}
    return result
