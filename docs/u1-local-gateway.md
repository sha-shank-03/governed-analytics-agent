# U1 local Gateway path — source ready, integration pending

This additive path speaks Vercel AI Gateway's OpenAI-compatible Chat Completions
function-call protocol. U1 accepts only a numeric loopback HTTP double and an
explicit `local/...` synthetic model. It cannot load a real credential or invoke
live inference. The published scripted MVP and its original evidence remain
at commit `7f98434549fe65a93593c3717cea71c4d6270f71`.

The new workflow is question → returned intent function → displayed proposal →
external full-contract confirmation → returned SQL functions → independent
reference verification → returned evidence IDs → reconciled report. Every next
provider decision receives matching assistant/tool messages. The host never
replaces a failed Gateway decision with a scripted answer.

Four measure IDs are supported: `gross_sales_v1`, `discounts_v1`, `refunds_v1`
and `net_sales_v1`. Completion includes total and channel evidence, integer cents,
USD, completed-order cohorts and the fixture's exclusive refund cutoff. A
proposal cannot supply identity, permissions, source paths, URLs, SQL or formulas.
Unknown semantics can hand off; ambiguity must be externally resolved in catalog
slots. A malformed call, unauthorized query or false completion cannot produce a
numeric summary. The host physically projects permitted rows before queries and
narrows that projection again if the external confirmation chooses a smaller scope.

## Proposed offline walkthrough (not executed yet)

Run from the repository with Python 3.11. No packages, accounts or keys are needed.
Use fresh output paths. These demos open a loopback server and spawn owned helpers,
so the current implementation assignment requires a named integration lease first.

```powershell
py -3.11 -m governed_analytics.upgrade demo --scenario freeform-confirmation --provider local-double --out work/u1-freeform
py -3.11 -m governed_analytics.upgrade demo --scenario unknown-intent --provider local-double --out work/u1-unknown
py -3.11 -m governed_analytics.upgrade demo --scenario denied-scope --provider local-double --out work/u1-denied
py -3.11 -m governed_analytics.upgrade demo --scenario unauthorized-query --provider local-double --out work/u1-unauthorized
py -3.11 -m governed_analytics.upgrade demo --scenario malformed-call --provider local-double --out work/u1-malformed
py -3.11 -m governed_analytics.upgrade demo --scenario false-completion --provider local-double --out work/u1-false-completion
py -3.11 -m governed_analytics.upgrade demo --scenario slow-provider --provider local-double --out work/u1-slow
```

The success demo uses an explicitly labeled authored external confirmation. It
does not claim a human participant, real model or external sandbox. Expected exit
codes are 0 for success/handoff and 2 for the four deliberate failure demos.
Inspect `report.json`, `checkpoint.json`, `events.jsonl`,
`authored-demo-confirmation.json` and `local-double-receipt.json`. Query receipts
contain SQL hashes, bound parameters, child cleanup and verification; sanitized
Gateway history in the checkpoint retains legitimate returned SQL.

For an independently managed persistent local double, save this nonsecret config
with its actual port, then run the separate start/resume commands:

```json
{"endpoint":"http://127.0.0.1:12345/v1/chat/completions","model":"local/synthetic-tool-model","mode":"local_double"}
```

```powershell
py -3.11 -m governed_analytics.upgrade start --question "How much did North retain in February compared with January?" --identity north_analyst --config work/local-gateway.json --out work/u1-question
py -3.11 -m governed_analytics.upgrade resume --config work/local-gateway.json --out work/u1-question --accept DISPLAYED_PROPOSAL_ID
```

`--accept` confirms the entire displayed proposal. An ambiguous proposal instead
needs `--answer` pointing to JSON with exactly `proposal_id` and `semantic` fields.
`semantic` contains metric, sorted distinct month pair, granted regions,
`["none","channel"]` groupings, USD and an empty ambiguity list. The caller may
correct those slots, never cutoff/definitions/identity/permissions. The confirmation
receipt binds request, code, config, policy/source, schema and original snapshot.
Changed config, code, sources, snapshot or stale proposal IDs fail closed. Reusing
an output directory cannot start a new budget; only a pending confirmation is
resumable. A failed or interrupted active run is preserved for review, not retried.

## Limits and telemetry

The run admits at most eight inference requests, twelve validated tools, six
candidate queries, two repairs and one schema refresh. It shares 60 monotonic
active seconds across start/resume, transport and owned-child cleanup; the
15-minute absolute monotonic lifetime also includes human wait. A persisted pause
receipt explicitly records external confirmation wait. Transport uses the lesser
of 15 seconds and remaining time; SQL uses at most three parent seconds and the
existing one-second SQLite VM guard. Cleanup reserves up to 0.5 seconds inside
that parent budget. OS scheduling/process creation is not a hard real-time guarantee;
a cleanup failure reports `child_reaped=false` and stops the workflow.

Question/request/response/SQL/history caps are 4/64/256/8/64 KiB. Output admission
reserves 1,500 tokens per request, at most 12,000 cumulatively. Cumulative request
bytes cap admitted context at 128 KiB; reported input/output usage is also bounded.
Unknown usage and actual/estimated cost remain null. Returned usage is synthetic
in U1. Zero live allocation is independent of the worker chat's model.

Automatic transport retries are zero for every status, timeout and lost response.
Normal subsequent model decisions after a host observation are distinct from a
transport retry. Admission is checkpointed before transmission; unknown outcomes
retain request/token counters. Killing a local helper proves local cleanup only;
it cannot prove a remote provider cancelled processing or avoided billing.

Events contain code/prompt/config/dataset/contract/snapshot bindings, cumulative
counters, typed outcomes and safe receipts. Auth headers and exception/HTTP error
bodies are discarded. Credential patterns are redacted before question transmission
and persistence; sensitive returned arguments are rejected. Arbitrary unmarked
secrets cannot be recognized reliably, so authorized inputs must remain synthetic.
The static demo identity and trusted local OS owner remain the MVP trust boundary.

## Evidence and independent U1 acceptance

38 new pure tests passed in four bounded batches: 30 initial protocol/intent/budget
checks, six newly authored helper/host gate checks, one per-request usage-cap
check and one final artifact deadline check. They used injected process
handles and functions, with no sockets, SQL children or end-to-end runs.

Main independently accepted U1 on 11 October 2026. All 109 tests, including the
eight transport and twelve workflow integration methods, and all seven documented
demos passed with expected exits. Their subcases include actual stalled headers, dripping body,
disconnect after send, cancellation, oversized response, HTTP 401/402/429/5xx,
redaction, scoped orders, all four measures, false completion and stale confirmation.
Main also passed 196 direct fixture/SQL/checkpoint predicates and rejected four
deliberately corrupted in-memory reports. The independent review is identified
as `20261011T0839`; raw execution and checks remain in main's acceptance archive.
Full process-tree lifetime memory peaks remain unmeasured.

The worker's first leased integration batch had three test errors (two SQLite
test connections left open on Windows and one report-key lookup). A subsequent
native recorder could not launch the protected WindowsApps binary (Win32 error 5)
before any corrected test ran. Both failures are retained. After the authorized
test-only correction, a supported ordinary Python recorder passed the three
corrected methods, all seven demos and 202 direct artifact/domain checks. This
worker evidence is separate from main's independent acceptance above.

`FROZEN_U1.json` binds the original source-ready slice; its historically false
integration/acceptance flags describe that gate and are not current status.
`FROZEN_U1_CORRECTION1.json` binds the later test-only correction. Both manifests
are preserved without rewriting their history. Neither is a scored evaluation
freeze. `FROZEN_M3.json` and original evidence are unchanged;
the v1 whole-tree verifier must be used against the published base because new
additive modules change its enumerated file set. The subsequent U2-A connector
source is versioned separately in `FROZEN_U2A.json`; its native integration,
genuine sandbox access, U2-B evaluation/baseline and U3 live-cost/quality work
remain pending. Local doubles establish no live model or external sandbox result.

Protocol reference: [Gateway OpenAI-compatible API](https://vercel.com/docs/ai-gateway/sdks-and-apis/openai-compat).
