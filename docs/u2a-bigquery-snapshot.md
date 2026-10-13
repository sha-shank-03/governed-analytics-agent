# U2-A fixed BigQuery snapshot

Main accepted the LOCAL U2-A contract, correction1 and format1 on 12 October
2026. Main passed 43 targeted pure methods, four admission/deadline native controls,
five connector native controls and 20 U1 native regressions. Independent review
passed 138 saved-domain/SQLite assertions including four corrupt-result controls,
plus 73 format/receipt checks and 76 unchanged non-README file hashes. No BigQuery
project, account, principal, IAM grant or billing state has been inspected or
verified. No external BigQuery API call or live inference has occurred.

Main's 12 October 2026 source probe found a deadline gap: a synthetic 0.15-second
parent token callback exceeded a 0.05-second request limit and still dispatched
a stub exchange with the full limit. No real token or network was used. The
bounded correction is versioned in `FROZEN_U2A_CORRECTION1.json`; the original
`FROZEN_U2A.json` and probe evidence are preserved. Main executed and accepted the
native correction controls. The historical README whitespace failure (exit 2),
format-only overlay and main oracle reason-code typo remain attributable to their
original receipts. Genuine external sandbox integration remains pending.

## Authority and data boundary

`BigQueryConfig` is host input: one project, the exact `ga_sandbox_north_views`
dataset, pinned location, expected email principal, four distinct reviewed view
IDs and SHA-256 hashes of each definition's exact UTF-8 SQL text, source version,
cutoff and `sales_v1` or `sales_v2`.
The model has no import tool. Questions, retrieved rows and Gateway function
arguments cannot override these settings. The only submitted SQL is
`fixed_query(config)`, a single SELECT/UNION over orders, order_lines, refunds and
period_coverage. Resource identifiers are syntax-checked trusted configuration;
North and the date cutoff are named bound parameters. Parameters cannot replace
resource identifiers in BigQuery. [Parameterized queries](https://docs.cloud.google.com/bigquery/docs/parameterized-queries)

Each view must expose exactly the existing local relation columns, in order,
plus STRING `currency`. Dates use DATE, amounts/quantity use INTEGER and coverage
uses BOOLEAN; all other fields use STRING. Only the reviewed v2 price rename
`unit_amount_cents` is admitted. The export names every column and wraps each
relation row as a JSON STRING. Unknown fields, nested fields, NULLs, wrong types,
other currencies/regions, unsupported enums, duplicate keys, broken order
references, invalid dates, missing coverage, negative amounts and unsafe integer
aggregates stop the import. These constraints deliberately cover this small USD
monthly-sales contract, not arbitrary warehouse schemas.

The four measures do not depend on fulfillment events. This import records that
relation as omitted and creates its empty compatibility table in the local
projection; it never claims that remote fulfillment evidence was extracted.
Use an immutable main-owned seed with a closed-month cutoff. Updating source
facts requires a new explicit import, never an automatic refresh during analysis.

## REST behavior and limits

The importer reads the four view schemas and reviewed definition hashes before
and after extraction. ETag/last-modified/location changes stop publication of a
usable snapshot. Tables metadata does not attest the underlying seed rows are
immutable; main must retain the seed/version and independently compare source
facts during genuine acceptance. The result of one query job becomes a fixed
local snapshot; the adapter does not claim remote time-travel isolation.
[Table metadata](https://docs.cloud.google.com/bigquery/docs/reference/rest/v2/tables)

The host first submits a dry run, checks the estimate against 64 MiB and retains
that same `maximumBytesBilled` cap on the real job. A conservative 40 MiB floor
allows for the documented per-table/query minimum; underlying view sources can
make the real charge larger, so the server cap remains decisive. No destination,
load, copy, extract, DML, permission or reservation change is sent.
[Query job fields](https://docs.cloud.google.com/bigquery/docs/reference/rest/v2/Job),
[analysis minimums](https://cloud.google.com/bigquery/pricing)

| Host bound | Limit |
| --- | ---: |
| Active import, including pacing/transport/cleanup | 60 seconds |
| REST requests, including cancellation/reconciliation | 20 |
| Concurrent requests / execution jobs | 1 / 1 |
| Request start rate | at most 1 per second |
| Result pages / relation rows | 10 / 5,000 |
| One response / cumulative responses / normalized snapshot | 256 KiB / 2 MiB / 2 MiB |
| One transport including helper cleanup | at most 8 seconds |
| Billed-byte cap | 64 MiB |
| Retries with a new job ID | 0 |

Three seconds and two REST admissions are reserved inside the import budget
for cancellation and a final status read. These maxima are independent; a long
pagination sequence can exhaust the total request limit before ten pages. The
subsequent U1 analysis retains its separate existing 60-second active budget.

Before `jobs.insert`, the caller's synchronous durable writer receives the
owned random job ID, trusted config/query hashes and exact submitted-body hash.
A lost response, HTTP 409 or ambiguous server failure leads to `jobs.get` for
that same ID and location, with no replacement job. Reference, query config and
returned `user_email` must match before ownership is verified. A conflict with
another job/principal is never cancelled. Unverified delivery remains remote
outcome unknown. There is no automatic resume or repeat of a failed importer.
[Job insertion](https://docs.cloud.google.com/bigquery/docs/reference/rest/v2/jobs/insert),
[job reconciliation](https://docs.cloud.google.com/bigquery/docs/reference/rest/v2/jobs/get)

Only a matched DONE job without `errorResult` or `errors` can enter pagination.
BigQuery's `errors` array can include nonfatal errors; this adapter conservatively
requires host review for any such array. Results must have `jobComplete=true`,
the exact output schema, stable total row count, complete nonlooping page tokens
and unique valid relation keys. `timeoutMs=0` is a server wait hint; the supervised
helper enforces the client wall deadline. Truncation produces no usable snapshot.
[Paginated query results](https://docs.cloud.google.com/bigquery/docs/reference/rest/v2/jobs/getQueryResults)

Cancellation targets only the admitted and verified owned job. The host polls
its status independently after the cancel response. Running/unreachable state,
exhausted cleanup budget or unverified ownership remains explicitly unknown.
A killed HTTP helper does not prove cancellation of the server job. Server
`jobTimeoutMs` is best effort, and cancelled jobs can still incur costs.
[Cancellation semantics](https://docs.cloud.google.com/bigquery/docs/reference/rest/v2/jobs/cancel)

## Local handoff and provenance

`SnapshotImporter(config, exchange, persist).run()` returns a
`ValidatedSnapshot` only after complete validation. Its immutable JSON binds
trusted resource/principal hashes, source/schema version, cutoff, view versions,
job identity/ETag/statistics, page response hashes, export time, row count and
normalized row hash. Unknown actual monetary cost stays null. Checkpoints retain
bounded request admissions, typed failures and owned-helper cleanup receipts.
Raw auth headers, HTTP error bodies, exception text and principal email are not
telemetry. The expected principal is configured privately and compared to the
job response; its hash is the portable provenance binding.

The host passes this value through
`start(..., trusted_snapshot=snapshot)` in the existing upgrade workflow. A
plain model dictionary is rejected. The North identity, normal semantic proposal
and external full-contract confirmation remain required. The snapshot JSON,
its binding and the physical SQLite file hash are retained. Resume checks the
source binding, rebuilds only the confirmed scope, and uses the existing
separate candidate/reference SQL processes and exact-cents verifier. No remote
connector call occurs during proposal, confirmation, SQL repair or resume.

`BigQueryTransport` defaults to external transport disabled. Local doubles use
only a numeric loopback origin and forbid prepared tokens. A later, separately
authorized main host may enable the fixed Google endpoint with
`prepared_token=PreparedToken(main_prepared_value)`. The value must already be
in memory before import; acquiring it is a separate main-owned, bounded preflight
operation. This transport has no credential discovery or executable loader.
The obsolete `token_loader` keyword rejects every non-None value before
invocation. Only the exact inert token type is admitted; subclasses, mappings
and callables are rejected, its value is immutable and its repr is redacted.

Request admission, inert token access, HTTP supervision and bounded cleanup
share one monotonic absolute deadline. The remaining duration and that same
deadline reach `owned_exchange`; the supervisor cannot restart or extend it.
Expired/cancelled admission launches no HTTP helper, and a late helper result
cannot be accepted. No loader thread exists. Tokens travel in the private helper
pipe, never argv or artifacts. Host enablement expresses operator authorization;
it does not prove billing, IAM or token identity. Server principal checks remain
required before the imported snapshot can be admitted.

## Sandbox feasibility and remaining evidence

Current official docs describe a no-card, no-billing-account sandbox with a
lifetime 10 GiB storage allowance (deletion does not refund it), 1 TiB monthly
query allowance, and 60-day expiration of tables/views/partitions. Streaming,
DML and Data Transfer Service are excluded. Small fictional read-only views
appear feasible within those limits, but this is a design inference, not an
observed account capability. [Current sandbox documentation](https://docs.cloud.google.com/bigquery/docs/sandbox)

Main must establish an isolated billing-disabled project, immutable source
dataset and authorized North-only views with no private columns. The dedicated
principal needs dataViewer on the view dataset and jobUser on the execution
project; source/South/all-view/editor/admin grants are excluded. View
authorization and all account/IAM/seeding changes belong to main. The runtime
uses the BigQuery OAuth scope, not a read-only scope that cannot create/cancel
query jobs. [Authorized-view permissions](https://docs.cloud.google.com/bigquery/docs/authorized-views),
[job OAuth scopes](https://docs.cloud.google.com/bigquery/docs/reference/rest/v2/jobs/insert)

Genuine acceptance still needs exact seed-to-projection/result comparisons and
independent South/unrelated-resource denials with that principal, job receipts,
billing-disabled evidence and bounded query usage. The adapter cannot probe
arbitrary resources to prove IAM denial. Local contract doubles and the checks
below establish no external integration or live model quality.

## Historical pure checks and main-executed native batch

Before the correction, 23 connector methods and 38 U1 pure methods passed in a
61-method injected batch. Earlier batches passed 18 connector methods and then
60 total methods. The correction's needed pure batch passed 43 methods:
ten new loader/admission/deadline controls, 23 existing connector checks and ten
existing budget/owned-supervisor checks. No socket, subprocess,
SQLite creation, credential discovery or external service was used by either
pure batch. Contract rows are small authored protocol inputs, not a fresh
evaluation corpus or blind task set.

Main executed the following batch after source rereview and its named
`governed-analytics-agent-u2a-loader-deadline-local-integration` lease. These
historical commands are recorded for attribution; U2-B requires its own fresh lease:

```powershell
py -3.11 -m unittest tests.integration.test_bigquery_loader_deadline -v
py -3.11 -m unittest tests.integration.test_bigquery_native -v
py -3.11 -m unittest tests.integration.test_upgrade_transport tests.integration.test_upgrade_workflow -v
```

All three commands returned exit 0 in main's accepted batch. The
first has four native controls: reject a slow synthetic callback without
invoking it or HTTP; refuse a cancelled inert request; enforce the absolute
deadline and reap a waiting synthetic helper; cancel and reap that helper. The
probe module contains no socket/HTTP/credential code. Its stub discards the
would-be HTTP payload, and artifacts contain only counters/timings/errors/PIDs.
They prove inert-seam rejection and owned-helper behavior, not acquisition of a
real credential. The second has five authored methods: real local
REST import/pacing and confirmed local SQL, post-query metadata drift, stalled
headers/dripping body deadlines, cancellation cleanup and source-file tamper
before resume. It retains `work/u2a-native-*` directories containing checkpoints,
HTTP arrivals, reports, physical SQLite and assertion receipts for independent
review. The third reruns the 20 U1 native methods after the snapshot handoff and
shared supervisor deadline changes. Correction controls retain
`work/u2a-loader-native-*` receipts. Record actual command exits/PIDs/wall time/source hashes and
memory-coverage limitations with the supported ordinary Python recorder.

`FROZEN_U2A_CORRECTION1.json` labels native/external execution as pending at its
creation time; it remains unchanged. Main subsequently accepted the local native
batch. Original v1/U1/U2-A manifests and earlier failure archives are preserved.
U2-B source/pure work is separate; its native tasks, genuine sandbox and U3 live
provider work remain unexecuted.
