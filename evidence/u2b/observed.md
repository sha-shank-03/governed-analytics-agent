# Observed offline analytics contract

42 authored/exposed tasks; 84 intended actor attempts. Main's historical acceptance covers the exposed offline contract only. This export has 42 scorable pairs and 42 same-policy ties. These measure execution consistency.

| Split (unique tasks) | Numeric completions, baseline | Correct safe non-answers, baseline | First meaning correct | Clarification / synthetic corrections | Synthetic confirmations attempted / accepted |
| --- | ---: | ---: | ---: | ---: | ---: |
| development (18) | 13/13 | 5 | 18/18 | 2 / 2 | 15 / 13 |
| capability (24) | 16/16 | 8 | 24/24 | 4 / 4 | 18 / 16 |

`deterministic-v2`: 29/29 numeric completions, 13 correct safe non-answers; 0 attempts have unknown scoring. 6 synthetic semantic corrections; 33 confirmation attempts, 29 accepted. Local harness latency p50/p95: 1469.0 / 1625.0 ms over 42 observations.

`protocol-double`: 29/29 numeric completions, 13 correct safe non-answers; 0 attempts have unknown scoring. 6 synthetic semantic corrections; 33 confirmation attempts, 29 accepted. Local harness latency p50/p95: 1485.0 / 1672.0 ms over 42 observations.

No human approvals were collected. Contract-matched results use the same attempts and add no independent tasks.

Actual input/output tokens, estimated/actual cost and cost per successful task: **null / unavailable**. No measured inference cost is claimed.

Native terminal status can be `failed` for an expected tamper stop. Lifecycle, numerical completion and independent scoring are separate fields. Missing evidence yields unknown scoring; unexecuted attempts are not failures.

Historical main review: 12 commands passed, 902 independent assertions and six negative controls passed; all 139 source pins unchanged. RSS was sampled with 21 sampling races/errors. Lifetime peaks and transient regression fixture peaks were not established.

Live model, genuine BigQuery/IAM/billing sandbox, main-held unseen acceptance and publication remain pending. The partial-summary suspicion did not reproduce and is not a confirmed bug.
