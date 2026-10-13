"""Pure bounded per-attempt lifecycle. Execution and scoring are separate facts."""
import copy
import re

ACTORS = ("deterministic-v2", "protocol-double")
TERMINAL = ("completed", "handoff", "access_denied", "failed", "cancelled", "budget_exhausted")
MAX_ATTEMPTS = 84


class ReportingError(ValueError):
    """Fixed codes only; input bodies and machine paths never enter exports."""


def require(value, code):
    if not value:
        raise ReportingError(code)


def hash_value(value):
    return type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def new_ledger(plan, source_sha256):
    require(type(plan) is list and 0 < len(plan) <= MAX_ATTEMPTS and hash_value(source_sha256), "INVALID_PLAN")
    records = []
    seen = set()
    for item in plan:
        require(type(item) is dict and set(item) == {"case_id", "actor", "numeric_applicable"}, "INVALID_INTENT")
        key = (item["case_id"], item["actor"])
        require(type(key[0]) is str and re.fullmatch(r"[dc]\d{2}", key[0]) and key[1] in ACTORS and type(item["numeric_applicable"]) is bool and key not in seen, "INVALID_INTENT")
        seen.add(key)
        records.append({**item, "state": "INTENDED", "started_at": None, "terminal_status": None,
                        "report_sha256": None, "score_sha256": None, "reason": None})
    return {"version": "u2c-attempts-v1", "source_sha256": source_sha256,
            "batch_state": "OPEN", "sequence": 0, "attempts": records}


def validate(ledger):
    require(type(ledger) is dict and set(ledger) == {"version", "source_sha256", "batch_state", "sequence", "attempts"}, "INVALID_LEDGER")
    require(ledger["version"] == "u2c-attempts-v1" and hash_value(ledger["source_sha256"]) and ledger["batch_state"] in ("OPEN", "CLOSED"), "INVALID_LEDGER")
    require(type(ledger["sequence"]) is int and 0 <= ledger["sequence"] <= 2*MAX_ATTEMPTS+2, "INVALID_SEQUENCE")
    plan = [{k: item.get(k) for k in ("case_id", "actor", "numeric_applicable")} for item in ledger["attempts"]] if type(ledger["attempts"]) is list and all(type(i) is dict for i in ledger["attempts"]) else []
    new_ledger(plan, ledger["source_sha256"])
    running = 0
    for item in ledger["attempts"]:
        require(set(item) == {"case_id", "actor", "numeric_applicable", "state", "started_at", "terminal_status", "report_sha256", "score_sha256", "reason"}, "INVALID_ATTEMPT_FIELDS")
        state = item["state"]
        require(state in ("INTENDED", "STARTED", "TERMINAL", "INTERRUPTED_UNKNOWN"), "INVALID_ATTEMPT_STATE")
        if state == "INTENDED":
            require(all(item[k] is None for k in ("started_at", "terminal_status", "report_sha256", "score_sha256", "reason")), "INVALID_INTENDED")
        else:
            require(type(item["started_at"]) in (int, float) and 0 <= item["started_at"] < 10**12, "INVALID_START_TIME")
        if state == "TERMINAL":
            require(item["terminal_status"] in TERMINAL and hash_value(item["report_sha256"]) and hash_value(item["score_sha256"]) and item["reason"] is None, "INVALID_TERMINAL")
        elif state in ("STARTED", "INTERRUPTED_UNKNOWN"):
            require(item["terminal_status"] is None and item["report_sha256"] is None and item["score_sha256"] is None, "UNKNOWN_NOT_TERMINAL")
            require(item["reason"] in (None, "INTERRUPTED", "TERMINAL_EVIDENCE_MISSING"), "INVALID_REASON")
        if state == "STARTED":
            running += 1
    require(running <= 1 and not (ledger["batch_state"] == "CLOSED" and running), "SERIAL_ATTEMPT_INVARIANT")
    return ledger


def transition(ledger, case_id, actor, state, **receipt):
    validate(ledger)
    require(ledger["batch_state"] == "OPEN", "BATCH_CLOSED")
    result = copy.deepcopy(ledger)
    matches = [i for i in result["attempts"] if (i["case_id"], i["actor"]) == (case_id, actor)]
    require(len(matches) == 1, "ATTEMPT_NOT_PLANNED")
    item = matches[0]
    require((item["state"], state) in (("INTENDED", "STARTED"), ("STARTED", "TERMINAL"), ("STARTED", "INTERRUPTED_UNKNOWN")), "INVALID_TRANSITION_OR_REPLAY")
    if state == "STARTED":
        require(set(receipt) == {"started_at"}, "INVALID_START_RECEIPT")
    elif state == "TERMINAL":
        require(set(receipt) == {"terminal_status", "report_sha256", "score_sha256"}, "INVALID_TERMINAL_RECEIPT")
    else:
        require(set(receipt) == {"reason"}, "INVALID_UNKNOWN_RECEIPT")
    item.update(state=state, **receipt)
    result["sequence"] += 1
    return validate(result)


def close(ledger):
    validate(ledger)
    require(ledger["batch_state"] == "OPEN", "BATCH_CLOSED")
    result = copy.deepcopy(ledger)
    for item in result["attempts"]:
        if item["state"] == "STARTED":
            item.update(state="INTERRUPTED_UNKNOWN", reason="INTERRUPTED")
    result["batch_state"] = "CLOSED"
    result["sequence"] += 1
    return validate(result)


def lifecycle(record, *, closed=False, legacy_status=None, legacy_artifact_present=False):
    if record is None:
        if legacy_status in TERMINAL:
            return {"state": "terminal", "start_evidence": "legacy_terminal_artifact", "terminal_status": legacy_status}
        return {"state": "interrupted_unknown" if legacy_artifact_present and closed else "STARTED" if legacy_artifact_present else "execution_unknown",
                "start_evidence": "legacy_partial_artifact" if legacy_artifact_present else "absent_legacy_attempt_marker", "terminal_status": None}
    state = record["state"]
    return {"state": "unexecuted" if state == "INTENDED" else "terminal" if state == "TERMINAL" else "interrupted_unknown" if state == "INTERRUPTED_UNKNOWN" or closed else "STARTED",
            "start_evidence": "durable_start_marker" if state != "INTENDED" else "durable_intent_only",
            "terminal_status": record["terminal_status"]}
