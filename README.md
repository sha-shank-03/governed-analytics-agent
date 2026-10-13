# Governed analytics agent

A small Python workflow for fictional sales questions: clarify gross versus net sales, propose read-only SQL, check the result, and produce an inspectable evidence report. It catches a plausible join that multiplies sales or refunds and refuses a regional analyst's request for company-wide data.

**Current scope: final local MVP independently accepted.** All seven final commands passed on their first attempt on Windows: 51 tests, 72 development trials, 216 frozen held-out trials and two demos. An additional worker audit passed 4,491 assertions against raw facts and saved artifacts. M1/M2 were independently accepted; M3 source/rubrics were reviewed before scoring. Decisions are scripted or explicitly labeled authored faults. No live model call or model-quality score is claimed. EVIDENCE.md preserves all earlier failures and the actual M3 results. Main also reproduced all seven commands from a fresh 48-file source copy: 51 tests, 288 comparison trials, two demos and 5,157 additional raw-data/database conditions passed. Hosted CI is authored and unexecuted.

## U1 local-double workflow accepted; live evidence pending

An additive Gateway-native local-double path now supports free-form proposals,
external full-contract confirmation, all four catalog measures and independently
verified SQLite totals/channels. Main independently accepted U1 on 11 October
2026: all 109 tests and seven documented demos passed with expected exits,
196 direct fixture/SQLite/checkpoint checks passed, and four deliberately
corrupted reports were rejected. The earlier worker test and launcher failures
remain preserved. These are local-double results; live model quality and external
integration remain pending. See the [U1 walkthrough](docs/u1-local-gateway.md).

## U2-A local BigQuery contract accepted; external sandbox pending

Main accepted U2-A, its deadline correction and formatting overlay on 12 October
2026. Main passed 43 targeted pure, four admission/deadline native, five connector
native and 20 U1 native regression methods. Independent review passed 138
saved-domain/SQLite assertions including four corrupt-result controls, plus 73
format/receipt checks and 76 unchanged non-README file hashes. The original
callback deadline finding, README whitespace exit 2 and main oracle typo remain
preserved. No BigQuery principal, IAM, billing state or genuine sandbox access has
been verified. See [connector boundaries](docs/u2a-bigquery-snapshot.md).

## U2-B exposed offline contract accepted; U2-C reporting ready for review

Main accepted the exposed offline U2-B contract on 12 October 2026: 31 pure and
35 native/affected regression methods, 42 paired tasks and three repeated demos
passed; 902 independent assertions and six negative controls passed. All 139
source pins remained unchanged. Per arm: **29 numeric completions and 13 correct
safe non-answers**, six synthetic semantic corrections, 33 synthetic confirmation
attempts and 29 accepted confirmations. No human approvals were collected.

Both exposed splits (18 development, 24 capability) and both arms use the same
policy; 42 ties establish execution consistency. Live-model reasoning uplift,
actual BigQuery/IAM/billing sandbox, main-held unseen acceptance and publication
remain pending. Tokens and estimated/actual cost remain null.

The source-bound redacted snapshot and runnable case study are in
[evidence/u2b/observed.md](evidence/u2b/observed.md) and the
[reporting guide](docs/u2c-reporting.md). Reproduce the report without rerunning
analytics:

```powershell
py -3.11 -m reporting.freeze
py -3.11 -m reporting.replay --out work/review-report
```

U2-C adds separate durable attempt accounting and pure packaging. New native
accounting checks are authored/unexecuted pending a fresh main lease; no cohort
rerun is needed. Seven prior seals, original 48 tasks, current 42-task corpus,
actors, gold, budgets, initial overlap findings and raw results are preserved.
The versioned offline CI defaults to pure checks/replay; hosted execution remains
unexecuted. See the [case study](docs/u2b-case-study.md).

## Run locally on Windows

Use Python 3.11 and run from this checkout. No package installation, Docker or service account is required. Use a fresh output directory for each run; completed outputs are preserved.

```powershell
py -3.11 -m governed_analytics doctor
py -3.11 -m governed_analytics demo --scenario revenue-drop --out work/m1-revenue
py -3.11 -m governed_analytics demo --scenario denied-scope --out work/m1-denied
```

The first demo uses synthetic user clarification, then an authored incorrect join followed by a scripted repair. Its verified result is North net sales of 1,000,000 cents in January and 780,000 cents in February: a -220,000-cent change. Direct-channel sales account arithmetically for that decrease; the partner channel is unchanged. The bad query is rejected before accepting figures. The second demo denies all-region access without running SQL. Source fingerprints stayed unchanged in both executed demos.

Each run writes `report.json`, `report.md`, and a checkpoint. Permitted runs also create a physically scoped SQLite snapshot. Reports contain the selected definition, scope, executed candidate SQL and parameters, query receipts, evidence IDs, tool decisions and source fingerprints.

## Clarify a question yourself

```powershell
py -3.11 -m governed_analytics run --identity north_analyst --fixture demo-v1 --provider scripted --request-id question-1 --question "Why did revenue fall in February 2026 versus January 2026?" --out work/question
py -3.11 -m governed_analytics resume --run work/question --answer net_sales_v1
```

The first command returns exit code 2 while awaiting clarification. Only external input resolves the metric; a provider guess cannot authorize query execution. A completed analysis or expected access denial returns 0; invalid commands, exhausted budgets and failed runs return 1. Cancellation returns 130.

The supported language is deliberately small: gross/net revenue or sales, two explicit month/year pairs or ISO `YYYY-MM` values, and North/South/all-region scope. Identity is selected by the trusted demo caller and is not production authentication. Private customer information is outside scope.

M3 also supports the exact last/previous-month vocabulary, anchored to the selected fixture's reference date. It never silently uses wall-clock today. The new held-out fixture uses April/May 2026 and a June 1 exclusive refund cutoff.

## Checks

```powershell
# Lightweight unit checks, without spawning a SQL child or running the full demo
py -3.11 -m unittest discover -s tests/unit -v

# Complete suite, including owned child-process and loopback HTTP checks
py -3.11 -m unittest discover -s tests -v
```

The complete M3 suite passed all 51 tests: 38 units and 13 integration tests, including actual owned-child cleanup, loopback HTTP, read-only SQL, timeout/cancellation and recovery. The full-suite test timer reported 7.596 seconds. Lightweight tests use manifest reads, synthetic outputs and injected process/SQL doubles.

## M2 demos and development evaluation

```powershell
py -3.11 -m governed_analytics demo --scenario schema-drift --out work/m2-drift
py -3.11 -m governed_analytics demo --scenario missing-period --out work/m2-missing
py -3.11 -m governed_analytics demo --scenario schema-unsupported --out work/m2-unsupported
py -3.11 -m governed_analytics demo --scenario zero-previous --out work/m2-zero
py -3.11 -m evaluation.run --split development --mode compare --repeat 1 --out work/m2-evaluation
```

All four demos passed locally. They exercise a known price-column rename with one metadata refresh, missing comparison-period coverage, an unsupported schema, and a covered month with zero sales. Missing coverage and unknown schema stop before SQL; a covered zero month remains zero and makes percent change undefined.

The comparator has 12 authored development cases and separate gold labels. It compares the governed workflow with a single SQL proposal using identical permission, projection and query limits. Baseline rows remain explicitly unverified; it cannot provide the full verified channel investigation. Results from one local development run:

| Mode | Numerical correctness | Full workflow success | Safety |
| --- | ---: | ---: | ---: |
| Governed scripted workflow | 6/6 | 12/12 | 12/12 |
| One-pass authored SQL baseline | 2/6 | 5/12 | 12/12 |

The baseline assumes net sales for ambiguous revenue and cannot repair faults or verify channel evidence. Full workflow scoring includes that investigation, so numerical accuracy is reported separately. These are authored development outcomes, not held-out or model-quality results. See [M2 behavior and protocol](docs/m2.md) and [EVIDENCE.md](EVIDENCE.md).

## Executed frozen M3 comparison

The first frozen run evaluated both modes three times on 36 authored held-out cases: 24 expected numeric completions and 12 expected non-answer outcomes per repeat. Every governed non-answer matched its specified safe stop or clarification pause. Output counts were complete; no frozen source, label or gate changed after scoring began.

| Split / mode | Full task success | Numeric correctness | Safety |
| --- | ---: | ---: | ---: |
| Held-out governed, each repeat | 36/36 | 24/24 | 36/36 |
| Held-out baseline, each repeat | 8/36 | 18/24 | 36/36 |
| Held-out governed, all three | 108/108 | 72/72 | 108/108 |
| Held-out baseline, all three | 24/108 | 54/72 | 108/108 |
| Development governed, all three | 36/36 | 18/18 | 36/36 |
| Development baseline, all three | 15/36 | 6/18 | 36/36 |

Baseline numerical failures were S03, J01, J02, J03, J04 and V02 in every repeat. All 24 answerable baseline full tasks fail because one unverified query cannot supply the required verified channel investigation; four non-answer tasks also fail. This structural limitation makes the full-task comparison narrower than a model comparison. There is no uplift gate.

For each mode, all 36 held-out case outputs were identical across three repeats after excluding random IDs, PIDs and timing; all 12 development cases were also identical. This measures deterministic repeatability. The author knows the cases; held-out means withheld from actor observations/development examples, not a secret independent benchmark. See [evaluation protocol](docs/evaluation.md) and [all 36 observed outcomes](EVIDENCE.md#executed-m3-final-integration).

## How it works

```text
Question + simulated identity -> metric/scope gate -> scripted decision
 -> host-validated plan -> candidate SQL on authorized-only data
 -> canonical reference comparison -> verified evidence -> report
```

The `Provider` interface receives observations and allowed tools, and returns a `Decision`. The host controls authority and arithmetic. The provider's SQL aggregates child tables into order grain; the separate canonical query uses correlated per-order aggregates. A test independently computes the tiny fixture totals in Python without either query implementation. The fixture can also be checked manually using [the order ledger](docs/fixture-ledger.md).

Four catalog measures are declared: gross sales, discounts, posted refunds and net sales. Groupings are total or channel. Refunds belong to the original order month and use the same exclusive 2026-03-01 cutoff in both months; tax and freight are excluded. This authored definition does not establish an accounting standard.

Original contribution: an inspectable demonstration of business meaning and join-grain errors alongside permission enforcement. [Databricks Genie](https://docs.databricks.com/aws/en/genie-agents/concepts) and [Vanna](https://github.com/vanna-ai/vanna) already address governed natural-language SQL; this project does not claim that capability is new.

## Limits and next boundaries

Physical projection removes unauthorized rows and private columns before SQL runs. A deny-by-default SQLite authorizer blocks changes, attachments, introspection and unapproved functions. Query/result limits, a SQLite heap cap, and a parent-owned timeout bound SQL execution. Details and unverified boundaries are in [architecture.md](docs/architecture.md).

M1 is a tiny authored dataset and a deterministic workflow, not an LLM benchmark. Canonical checks validate only the declared catalog on the current snapshot. Channel differences show arithmetic contributions, not causes. The process boundary is not an OS sandbox. An OS owner can alter files or select another simulated identity.

M2 adds request IDs, an exclusive run lock, atomic checkpoints, active-run recovery, known schema handling and coverage gates, now covered by local unit/integration checks. A crash before a read action is checkpointed can repeat that read; this is not an exactly-once system. Stale locks need operator investigation and are never automatically removed.

The optional Responses wire adapter is validated with injected transports and an actual loopback HTTP double. External HTTPS requires explicit opt-in and a supplied credential, with no environment-key discovery or redirects. That route is unexecuted. There are no arbitrary file, shell, HTTP or write tools available to the acting provider.

M3 evaluated 36 authored held-out cases in both modes across three repetitions. FROZEN_M3.json bound actor/baseline code, source fixtures, prompts, gold and oracle before first scoring; the hashes stayed unchanged. The runner preserved the pre-action attempt manifest, all 216 records and separate scorecard metrics. Windows standalone execution passed; Linux and the pinned public-repository CI workflow remain unexecuted. These outcomes demonstrate the specified controls on authored data, not learned model quality or statistical generalization. See [evaluation and final commands](docs/evaluation.md) and [threat model/tradeoffs](docs/threat-model.md).

Source, documentation and fictional fixtures are MIT licensed. Runtime attribution is in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
