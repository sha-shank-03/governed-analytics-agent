# U2-B authored evaluation and deterministic baseline

U2-B is at source/pure review. Native workflow checks, 42-task comparisons and
three demonstrations are authored and **unexecuted**. A fresh main resource lease
is required for SQLite workflows and owned helpers. There are no U2-B task-success,
latency, model-quality, external BigQuery or deployment results yet.

## What the new evaluation measures

`evaluation_v2/` contains 18 development tasks and 24 capability tasks. Development
has six language/ambiguity, six SQL/schema/domain and six scope/injection/provenance
tasks. Capability has six paraphrase/follow-up, six ambiguity/unsupported, four
grain, four scope/injection, two coverage/schema and two provenance/cost tasks.
The labels specify 29 numeric tasks and 13 safe non-answers. A handoff on one of
the 29 answerable tasks is a failed completion.

Every task has a distinct fictional lineage, IDs, months and monetary range,
also separate from the original data. Facts and prompts are newly authored MIT
material. `PROVENANCE.json` records normalized source/case/question/label hashes;
`author.py` is the reproducible specification. Both sets were exposed to the
worker during authoring. Neither is blind or an independent population sample.
Main's unseen acceptance set is private, absent and unassigned.

The original 48 tasks, labels, numerical facts and freezes remain intact.
The original one-pass comparator remains a historical diagnostic. It does not
enter the new competitive comparison. Repeated demos, two actors and two views
do not increase the 42-task sample count.

## Equal host boundaries

The deterministic-v2 policy parses raw language using reviewed aliases for gross,
net, discounts and refunds. It handles ISO and named month/year pairs, anchors
last/previous-month language to the source cutoff, reuses only caller-provided
previously confirmed context and flags ambiguity. Unsupported requests hand off.
Both total and channel reports are required. Business event strings cannot become
instructions or permissions.

Both actors use `upgrade.start/resume`, the same raw facts, grants, external
full-semantic confirmation interface, physical scope projection, parameterized
order-grain candidate templates, independent runtime verification, repair/refresh
rules and finish criteria. Both have 60 active seconds, 900 lifetime seconds,
eight logical decisions, twelve host tools, six candidates, two repairs and one
refresh, with the same existing byte/token/SQL bounds. The deterministic actor
consumes the same request-count and output-reservation caps; its input uses the
current observation rather than a model transcript. Actual wire bytes differ and
are counted honestly. Neither actor receives labels or numeric gold.

The offline `protocol-double` wraps the **same deterministic language policy** in
Gateway tool-call responses. It tests protocol/host consistency and is expected
to tie. It does not simulate a model's reasoning quality. Genuine model smoke,
pricing, live allocation and unseen scoring remain main-owned U3 work.

## Independent scoring and interventions

`scorer.py` has no actor or SQL-reference imports. It computes completed-order
cohorts, quantity times price, discounts and posted refunds strictly before the
source cutoff with dictionary/Decimal arithmetic. It verifies totals, each
channel, empty groups, undefined zero-prior percentages, negative net values,
coverage, scope and the declared semantic contract. Completed orders with no
lines retain posted refunds while gross/discounts are zero.

The post-run inspector reads physical SQLite rows/columns, checkpoint, events,
source bytes and trusted catalog/policy/code hashes. The scorer checks these
against original raw facts, source and snapshot bindings, proposal/confirmation,
query parameters, result IDs, exact integer cents and finish references. Report
status and `verified` flags alone cannot pass. Unknown cost/tokens stay null.
Safe non-answers need the expected reason, no numeric claims or SQL and the
appropriate raw coverage/schema/tamper proof.

The first proposal is saved before correction and scored separately. The harness
then supplies the frozen expert semantic answer, including clarification where
needed, through the same trusted interface. These are simulated external answers,
not evidence that a human actually approved each run. Reports separate external
confirmation attempts, accepted confirmations and semantic corrections.

The contract-matched view uses the same saved runs after expert confirmation,
isolating numeric planning/verification. It is not a second set or an independent
execution. Every failed/pending/cancelled/handoff row stays in the fixed denominator;
`started.json` plus the pure summary tool recover missing rows after interruption.
Paired output records ties and differences, without a positive-uplift gate.
Cost per success is unavailable for these offline actors. Missing inspection
leaves unsafe actions unknown; observed rates use inspected tasks only. Unsafe action counts
cover unauthorized physical scope or numerical/query activity on a required safe
non-answer; incorrect numerical completions are also reported as failures.

## Commands and frozen native batch

The final new pure batch passed 31 methods, including 14 corrupt-artifact
controls, label isolation and no-I/O checks. An earlier targeted batch passed 100
methods (29 then-current U2-B methods and 71 unchanged U1/U2-A regressions). A static
audit found overlapping monetary values in the initial draft; its bytes and the
first 24-method receipt were preserved before assigning disjoint ranges. Native
methods and task scores remain pending.

Lightweight checks require only Python 3.11 standard library:

```powershell
py -3.11 -m unittest tests.unit.test_u2b -v
py -3.11 -m evaluation_v2.author --check
py -3.11 -m evaluation_v2.freeze
py -3.11 -m evaluation_v2.legacy
```

After main grants the fresh local lease, the exact six-command batch is
`evaluation_v2/INTEGRATION_BATCH.json`: 35 native methods (ten new, 20 U1 and five
connector regressions), one development comparison, one capability comparison
and the three demos below. Maximum batch lifetime is 900 seconds, RAM 512 MiB,
generated disk 200 MiB; no downloads, inference or external calls. Stop at the
first unexpected result, preserve raw receipts and request a new correction review.

```powershell
py -3.11 -m evaluation_v2.run --split development --actor compare --out work/u2b-development --lease-ack main-authorized-local-u2b
py -3.11 -m evaluation_v2.run --split capability --actor compare --out work/u2b-capability --lease-ack main-authorized-local-u2b
py -3.11 -m evaluation_v2.run --split development --case d07 --actor deterministic-v2 --out work/u2b-demo-grain --lease-ack main-authorized-local-u2b
py -3.11 -m evaluation_v2.run --split development --case d13 --actor deterministic-v2 --out work/u2b-demo-scope --lease-ack main-authorized-local-u2b
py -3.11 -m evaluation_v2.run --split development --case d17 --actor deterministic-v2 --out work/u2b-demo-provenance --lease-ack main-authorized-local-u2b
```

These commands are instructions for the future lease, not executed results.
Expected outcomes are checked independently; exit zero for the scope/tamper demos
means a correct safe stop, not a numerical completion. A fresh output directory is
mandatory. `first-proposal.json`, `external-confirmation-input.json`, `report.json`,
`checkpoint.json`, `events.jsonl`, `scoped.sqlite`, `independent-inspection.json`
and `score.json` make each run reviewable. Summarize even an interrupted batch:

```powershell
py -3.11 -m evaluation_v2.summary --out work/u2b-capability
```

## Offline CI and historical reproduction

The versioned CI workflow uses public hosted runners, pinned checkout/setup steps
and Python 3.11.9; it installs no application dependencies and has read-only Git
permissions. It runs local/pure/native checks and authored comparisons. It never
enables paid inference or external accounts. Hosted execution is unexecuted.

The original whole-tree v1 freeze correctly rejects additive upgrade modules.
Its manifest is preserved. The only changed v1-bound file is the CI workflow;
its exact old bytes are retained in `evaluation_v2/legacy_ci.yml`. The new U2-B
freeze declares this overlay. `legacy --out work/v1-ci` reconstructs the original
29 manifest files and original tests in a separate directory; the unchanged v1
verifier can then operate there. This is explicit historical reconstruction,
not a regenerated v1 freeze. Current code must pass `FROZEN_U2B.json` separately.

No project/customer/private data, external datasets or third-party dependencies
were added. SQLite is bundled with Python. Static and pure checks establish
implementation controls; they do not establish a completed analytics workflow,
external connector success or business impact.
