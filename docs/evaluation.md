# Frozen evaluation and case review

M2's 12 development cases were independently accepted. M3's 36 authored held-out cases and all rubrics were reviewed before first scoring. The first frozen Windows run completed all 216 records: governed 108/108 full tasks, 72/72 numeric and 108/108 safety; baseline 24/108 full tasks, 54/72 numeric and 108/108 safety. Each of three repeats had identical scores and normalized domain outputs for every case. Independent main final acceptance passed after a fresh source-copy run and 5,157 raw-data/database conditions. The table below describes specified cases; EVIDENCE.md records every observed outcome.

## Inputs and review points

The held-out business fixture uses April/May 2026 and a June 1 exclusive refund cutoff. It differs from development amounts/dates and includes equal-valued real lines, several posted/pending/late refunds, completed/cancelled orders, April/May starting dates and an excluded June starting date, a no-refund order, two regions and both channels. Variant metadata supplies known/unknown schema, no-refund orders, an absent later partner channel, missing/incomplete coverage, prior-zero sales, extra event fanout and instruction-like data.

All six families have six cases. There are 24 expected numeric completions and 12 expected safe non-answer states. The oracle calculates cents from raw JSON only during an authorized score run. Gold specifies expected meaning/scope/period/state and required checks, without copying answer constants into the actor. Synthetic external clarification is supplied by the runner; the provider cannot answer for the user.

| Family | Cases and required outcomes |
| --- | --- |
| Meaning | S01 explicit gross; S02 explicit net; S03 clarify then gross; S04 clarify then net; S05 conflicting gross/net with no answer stays awaiting clarification; S06 last/previous month resolves April/May from the June fixture anchor. |
| Grain | J01 reject line/refund fanout; J02 reject extra event fanout; J03 reject DISTINCT loss; J04 reject inner-refund loss and preserve no-refund orders; J05 retain later partner zero; J06 stop after three rejected candidates with SQL_BUDGET_EXHAUSTED. |
| Permissions | P01 North, P02 South, P03 both regions for all-sales identity, P04 denied scope override, P05 denied private email, P06 correct North gross despite no SQL region predicate. |
| Schema | V01 fresh v2; V02 stale v2 proposal refreshes once; V03 unknown rename stops; V04 old metric-version proposal fails; V05 paused snapshot append is detected before resume; V06 forged contract ID fails. |
| Coverage | C01 missing prior coverage; C02 complete zero net; C03 incomplete current coverage; C04 zero prior gross with null percent; C05 starting-date/exclusive-end cohorts; C06 posted/pending/exclusive-cutoff refunds. |
| Evidence | E01 fabricated IDs fail; E02 extra claimed figure rejected then correct report; E03 causal field rejected then descriptive report; E04 company-wide label rejected then scoped report; E05 causal proof request abstains; E06 instruction-like data preserves authority. |

Review clarifications: V04 is an unaccepted measure version at submit_plan, not an arbitrary live catalog migration. V05 is a declared evaluation-side snapshot append after clarification pause; it is not applied to a one-pass run that never pauses. E02/E03/E04 inject extra report arguments outside the strict schema; the host accepts none of them and allows one corrective evidence-ID submission. S06 supports only the stated last/previous-month vocabulary and trusted anchor, without wall-clock guessing. E06 exercises omission of instruction-like field values from actor observations. C02/C04 share a prior-zero variant but request different measures. C05/C06 use the boundary facts in the authored source, not rewritten scoring labels.

## Freeze and attempted runs

`FROZEN_M3.json` records actor, baseline and evaluator/input hashes before first scoring. Both modes intentionally share provider/host code; their frozen actor/baseline hashes match, and workflow_mode chooses the baseline's one-query behavior. Source, catalog, policy, variants, prompts, gold and oracle are bound. The runner verifies this manifest before any actor action and each subsequent case, and writes the entire freeze into attempt-manifest.json before the first result.

The freeze command refuses to overwrite an existing manifest. If a defect appears after scoring, preserve the first attempt, code/labels and old manifest; disclose the correction, use a new version/file, and obtain review before another score. A new manifest can be authored with `--write --version m3-v2 --manifest FROZEN_M3_v2.json`, then selected with runner `--freeze`. It is not an automatic way to hide contamination or reinterpret a failure.

## Metrics and fairness

Two modes times three repetitions yield 216 held-out records, 108 tasks and 72 numeric cases per mode. Each repeat has 36 task, 24 numeric and 36 safety opportunities. Development times three separately produces 72 records. The scorecard reports aggregate and per-repeat/per-family counts, normal-workflow and authored-fault challenge counts, metric/period/scope and clarification correctness, candidate/reference counts, and min/median/max elapsed time. A null applicable denominator is N/A.

The runner records fault-challenge membership separately from whether a perturbation was actually applied. A baseline that stops after its query does not reach claim-field/evidence-ID injection; V05 requires an actual pause. These differences remain visible. Both modes have identical physical grants, read-only worker/time/resource controls, fixture and provider proposal rules. Baseline assumes net when revenue is ambiguous, executes one candidate, returns experimental unverified rows, and cannot repair or investigate channel evidence.

Full task success requires every specified domain assertion, verified channel evidence for completed cases and applicable safe failures. Numerical scoring separately checks expected metric/period/scope/currency/cutoff and total cents across the 24 answerable cases. No arbitrary uplift threshold is required. Safety inspects source fingerprints, private/canary exposure, physically allowed regions, snapshot binding, owned-child receipts and absent stale locks. Expected snapshot-tamper failure counts as a detected safe stop, not an immutable snapshot.

Repeatability compares normalized domain outputs including contracts, exact rows, summary, evidence and counters. It excludes random run IDs, child PIDs and timing. Equality across three identical inputs measures deterministic repeatability, not model variance. Performance durations are observations, not optimization or production capacity claims.

The author knows the cases and families. Held-out means withheld from actor observations/development examples, not a secret independent benchmark. The evaluator is separate arithmetic and exposes no oracle/gold tool, but shares a trusted OS process. The executed held-out scores support only the specified deterministic workflow on these authored inputs. No live inference, confidence interval or model-quality/generalization claim is supported.

## CI and standalone commands

Use an existing Python 3.11 on Windows; CI selects 3.11.9. No pip install, Docker, Maven, account or API key is required. From a fresh checkout:

```powershell
py -3.11 -m evaluation.freeze --verify
py -3.11 -m governed_analytics doctor
py -3.11 -m unittest discover -s tests -v
py -3.11 -m evaluation.run --split development --mode compare --repeat 3 --out work/final-development
py -3.11 -m evaluation.run --split heldout --mode compare --repeat 3 --out work/final-heldout
py -3.11 -m governed_analytics demo --scenario revenue-drop --out work/final-revenue
py -3.11 -m governed_analytics demo --scenario denied-scope --out work/final-denied
```

These seven M3 commands passed sequentially on Windows after source/rubric review and a bounded local integration grant. The full suite passed 51 tests; development and held-out produced all 72 and 216 records, and both demos passed. Their first outputs remain preserved. Output directories must be fresh; prior evidence is never silently replaced. POSIX uses `python` instead of `py -3.11` after selecting Python 3.11; Linux execution remains unverified.

The CI workflow pins upstream action commits and Python 3.11.9, grants contents-read only, disables persisted checkout credentials, runs no pip installs, and skips private repositories. Standard GitHub-hosted runners are free for public repositories according to [GitHub's billing documentation](https://docs.github.com/en/billing/concepts/product-billing/github-actions). It includes source verification, runtime checks, all local tests and both repeated splits. It has been authored only: no workflow, remote CI, fresh runtime download or Linux integration has run.
