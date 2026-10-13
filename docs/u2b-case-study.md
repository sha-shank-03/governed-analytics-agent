# Case study: a numerical answer and two correct safe stops

A regional sales question can be wrong even when SQL executes: joining lines/refunds/events can multiply amounts; choosing the wrong definition, cohort or cutoff changes its meaning. The workflow narrows physical scope, requires external full-semantic confirmation and independently verifies totals/channels before reporting.

Main executed and accepted the exposed offline U2-B contract on 12 October 2026. Of 42 authored tasks, each arm completed 29 numerical comparisons and 13 correct safe nonanswers. The protocol wrapper and baseline share one policy, producing 42 ties. Six meaning corrections used trusted synthetic fixture answers. No actual human approvals, model inference, real BigQuery access or production impact were measured.

Three repeated demonstrations remained within the same 42 tasks:

| Case | Observed result | Interpretation |
| --- | --- | --- |
| d07, multiple lines/refunds | North net sales 34,880,539 cents in 2031-07 versus 34,883,085 in 2031-08; delta +2,546 cents, direct/partner +1,273 each | Exact verified arithmetic; exclusive refund cutoff 2031-09-01. Rounded percentage 0.0% does not mean a zero change. |
| d13, South request by North analyst | access_denied; no numerical summary | Correct scope refusal with an empty physical projection and no candidate SQL, independently checked by main. |
| d17, source mutation after proposal | native status failed; scoring correct safe nonanswer | Source-context change stopped before SQL; one synthetic confirmation attempt was not accepted. |

The baseline d07 harness observation was 1,609 ms; d13 was 172 ms and d17 was 328 ms. These are saved local observations, not model/service latency. The exported snapshot retains exact cents and raw-artifact SHA bindings; its replay recomputes the numeric facts using the unchanged corpus. Main's original physical SQLite/cleanup audit remains separate.

Run the case study from a checkout with Python 3.11 and no dependencies:

```powershell
py -3.11 -m reporting.freeze
py -3.11 -m reporting.replay --out work/case-study
```

This reproduces the source-bound JSON/Markdown report without SQL children or analytics execution. See [the reporting guide](u2c-reporting.md) for the split counts, 33 synthetic confirmation attempts/29 accepted per arm, six corrections, null usage/cost, lifecycle/unknown distinctions and the optional fresh-lease journal demo. New native accounting checks remain unexecuted.

The supported surface remains four USD measures, two months, total/channel grouping, trusted simulated identities and bounded read-only SQL. Causal claims, arbitrary formulas and production authentication remain outside that surface. Main-held unseen/live/external sandbox evidence, final acceptance and publication are still pending. No ROI or reasoning uplift is inferred from the authored results.
