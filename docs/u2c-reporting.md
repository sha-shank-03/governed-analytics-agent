# Source-bound offline report and attempt accounting

Main accepted the **exposed offline U2-B contract** on 12 October 2026. Twelve
documented commands returned exit zero, including 31 pure methods, 35 native and
affected regression methods, 18 development and 24 capability paired tasks and
three repeated demos. Main checked 902 independent conditions and six negative
controls; all 139 source pins stayed unchanged. This is not final upgrade acceptance.

## Observed task denominators

| Exposed split | Unique tasks | Numeric completions per arm | Correct safe non-answers per arm | First meaning correct per arm | Clarification / semantic corrections per arm | Synthetic confirmations attempted / accepted per arm |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Development | 18 | 13/13 | 5 | 18/18 | 2 / 2 | 15 / 13 |
| Capability | 24 | 16/16 | 8 | 24/24 | 4 / 4 | 18 / 16 |
| Combined | 42 | 29/29 | 13 | 42/42 | 6 / 6 | 33 / 29 |

Each arm had 29 numerical answers and 13 correct safe stops. First-meaning
accuracy includes correctly identifying ambiguity; it does not imply autonomous
meaning resolution. Six cases needed trusted synthetic semantic corrections.
All 29 numerical answers used accepted synthetic confirmation. Four additional
confirmation attempts stopped before acceptance because of coverage or provenance.
No human approvals were collected. The saved `human_intervention_tasks` field is
relabelled as 38 synthetic-confirmation-or-handoff tasks per arm, not measured
human work or approvals.

The two actors share the same deterministic language/SQL policy. Their 42 ties
establish execution/protocol consistency. Eighty-four actor attempts, the second
contract-matched view and three repeated demos add no independent tasks. Both
splits were authored and exposed; neither is main's private unseen acceptance set.

Local saved harness latency p50/p95 was 1,469/1,625 ms for deterministic-v2 and
1,485/1,672 ms for the protocol wrapper, each over 42 attempts including safe stops.
These are one offline pass, not model latency or a population estimate. Actual
input/output tokens, estimated/actual cost and cost per success remain **null**.
No measured inference cost, reasoning uplift or business impact is claimed.

## Reproduce the report without running analytics

Python 3.11 standard library is sufficient; no service, package install or key is
needed. Use a fresh output directory:

```powershell
py -3.11 -m reporting.freeze
py -3.11 -m reporting.freeze --historical
py -3.11 -m reporting.replay --out work/review-report
py -3.11 -m unittest tests.unit.test_u2c tests.unit.test_u2b -v
```

The shipped `evidence/u2b/observed.json` is a 333,387-byte redacted snapshot derived
from main's saved raw results. It records the old source/corpus/exporter hashes,
84 curated attempts, exact numeric evidence, artifact hashes and the sanitized
main-review receipt. Replay verifies the new seal, recomputes numeric cents from
the unchanged fictional corpus and rebuilds summaries. It does not create a
SQLite database, query SQLite, call a model, rerun a task or inspect credentials.

To derive the snapshot again where the ignored raw main outputs and private review
receipt are available, use the exporter with a new output directory:

```powershell
py -3.11 -m reporting.export --development work/main-1012-1009-development-comparison --capability work/main-1012-1009-capability-comparison --review ../coordination/upgrades/2026-10-11/acceptance/governed-analytics-agent/20261012T1009/MAIN_REVIEW.json --out work/rederived-report
```

The exporter reads bounded saved JSON and file bytes, checks the old source pins,
revalidates saved inspections with the original pure dictionary/Decimal scorer,
and verifies checkpoint/source/event/SQLite file hashes. It never queries SQLite
again. Only whitelisted derived fields and hashes are exported: no questions,
provider transcript, raw exception body, credentials or machine paths. Inputs are
limited to 1 MiB per JSON file, 4 MiB per SQLite byte hash and 64 MiB cumulative.
This derivation read 12,705,810 bytes. Raw main results stay unchanged.

Snapshot replay can independently check numerical arithmetic and summary
consistency. The public snapshot is not a replacement for main's original physical
SQLite/cleanup audit; full raw artifacts remain in the accepted local run folders.

## Durable attempt accounting

The original whole-batch `started.json` fixes the intended denominator. It lacks a
per-attempt STARTED marker, so absent legacy artifacts cannot prove that an attempt
was unexecuted. The existing partial-summary suspicion did not reproduce; this is
an added accounting capability, not a claimed correction to that suspicion.

The separate `reporting.run` wrapper preserves the old actors, labels, tools,
grants, confirmation policy and budgets. It writes an atomic bounded `attempts.json`:

| Evidence | Export lifecycle | Scoring |
| --- | --- | --- |
| Durable INTENDED only | unexecuted | unknown; not a failed task |
| Durable STARTED, batch still open | STARTED | unknown |
| STARTED without terminal evidence in a closed run | interrupted_unknown | unknown |
| Bound terminal report/score receipt | terminal | correct, incorrect or unknown according to complete evidence |
| Legacy missing marker and no artifact | execution_unknown | unknown; start cannot be established |

STARTED persistence must succeed before invocation. Failed start persistence leaves
the attempt unexecuted; failed terminal persistence leaves the outcome unknown.
One attempt runs at a time, at most 84 are intended, ledger size is at most 64 KiB
and transitions cannot be replayed or resumed automatically. Caller-declared closed
export is a reporting assumption, not proof of process cleanup. A native `failed`
status can be a correct expected provenance stop; lifecycle and scoring stay separate.

Twenty-six new pure methods passed, covering malformed/oversized/duplicate JSON,
interruption, missing audit evidence, persistence failures, typed cents, unknown
scoring, redaction, summary consistency and no-I/O operation. New native wrapper
checks are authored and unexecuted. After main assigns a fresh lease, the bounded
proposal runs only two existing cases (d07 and d17), not the 42-task cohort:

```powershell
py -3.11 -m unittest tests.integration.test_u2c_accounting -v
# Optional single-case walkthrough, also requiring a fresh main lease:
py -3.11 -m reporting.run --split development --case d07 --actor deterministic-v2 --out work/journal-demo --lease-ack main-authorized-local-u2c
```

`reporting/PACKAGING_BATCH.json` fixes the future commands. Packaging is bounded
to 60 seconds/256 MiB/5 MiB; the optional two native methods to 90 seconds/256 MiB/
5 MiB, one SQL child and no socket server. No native wrapper check or demo was run
by the worker. No cohort rerun is needed because actor/domain behavior is unchanged.

## Preservation, CI and remaining gates

Seven historical source seals, the original 48 tasks, current 42 cases, gold,
actors, budgets, initial author-overlap evidence and raw main results are preserved.
Changed README/U2-B guides/CI bytes have explicit original archives under
`reporting/history/u2b/`; `FROZEN_U2C.json` binds the reporting overlay and verifies
all original U2-B pins. Whole-tree historical verifiers remain historical; use
`reporting.freeze --historical` on this upgraded tree.

Default CI uses a public hosted runner, pinned checkout/Python setup, read-only Git
permissions, pure checks and snapshot replay. No application dependencies or paid
inference are installed. Native accounting is an optional manual job; hosted CI
remains authored and unexecuted. Existing cohort jobs are preserved in the archived
workflow rather than rerun for reporting-only changes.

Main's RSS/process/listener evidence was sampled, with 21 process-exit sampling
races/errors. The sampled tree-plus-main RSS was 109,666,304 bytes; lifetime peaks
were not guaranteed. Generated outputs were 11,988,681 bytes, excluding transient
regression fixtures whose peak footprint was not separately measured.

Real BigQuery/IAM/billing-disabled sandbox access, live-model spend/usage, main-held
unseen acceptance, final upgrade acceptance and publication remain pending. These
gates do not change the observed scope of the exposed offline result.
