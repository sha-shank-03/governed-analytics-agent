# Implementation and validation evidence

Recorded 8 October 2026. Runtime: Windows, CPython 3.11.9 selected explicitly with `py -3.11`, bundled SQLite 3.45.1. Commands below were run from the repository checkout. Source authoring and lightweight checks used no lease; the later full batch used the granted `governed-analytics-agent-e2e` lease. No dependency installation, model request, credential acquisition or external-account action occurred.

M1 was independently accepted on 8 October 2026 at 09:26:44 UTC. M2 was independently accepted at 11:05:04 UTC: seven commands, 45 tests, three focused actual process probes and 96 independent artifact assertions. The main checker independently recomputed all six completed development totals/channels from raw JSON and checked scopes, safe stops, source hashes and child cleanup. M3 source/rubrics were accepted before the first frozen Windows integration, which passed all seven commands, 51 tests, 288 evaluation trials and both demos. An additional worker raw-data/artifact audit passed 4,491 assertions. Main final M3 acceptance and hosted CI remain pending/unexecuted. Earlier source-checkpoint evidence and all failed attempts remain below as historical checkpoints.

Decisions are scripted; authored faults are not recorded model behavior. The executed authored held-out results below are workflow evidence; no model quality, hosted CI execution or production result is claimed.

## Executed lightweight checks

| Attempt | Exact command | Exit | Actual result |
| --- | --- | ---: | --- |
| Unit 1 | `py -3.11 -m unittest discover -s tests/unit -p test_m1_unit.py -v` | 1 | 13 tests in 0.220 s; one failure and seven errors. Windows cleanup found an unclosed builder connection; empty-column/no-database authorizer callbacks wrongly rejected count and cross-join reads. |
| Unit 2 | `py -3.11 -m unittest discover -s tests/unit -p test_m1_unit.py -v` | 0 | 13 tests in 0.249 s; all passed after fixes. |
| Unit 3 | `py -3.11 -m unittest discover -s tests/unit -p test_m1_unit.py -v` | 0 | 13 tests in 0.203 s; rerun after copying provider observations and declaring provider metadata; all passed. |
| Syntax | `py -3.11 -c "import ast,pathlib,sys,sqlite3; paths=sorted(pathlib.Path('governed_analytics').glob('*.py'))+sorted(pathlib.Path('tests').rglob('*.py')); [ast.parse(p.read_text(encoding='utf-8'), filename=str(p)) for p in paths]; print('AST_FILES='+str(len(paths))); print('PYTHON='+sys.version.split()[0]); print('SQLITE='+sqlite3.sqlite_version)"` | 0 | Parsed 14 Python files; Python 3.11.9, SQLite 3.45.1. |
| Diff whitespace | `git diff --check` | 0 | No tracked diff error; source files are new/untracked, so this alone does not check their whitespace. |
| Personal-path scan | `rg -n 'C:[/\\]|shash|CodexPortfolios|coordination/workers' governed_analytics tests docs README.md LICENSE THIRD_PARTY_NOTICES.md fixtures` | 1 | No matching personal path/coordination reference in scanned shipped source/docs/data. |

Unit stdout/stderr were retained locally under ignored `work/unit-tests-attempt-1.txt`, `work/unit-tests-attempt-2.txt` and `work/unit-tests-attempt-3.txt`. Redirection used `*>` in PowerShell; the native exit code was captured immediately. The first failed attempt is preserved. Builder connections now explicitly close, and unit scratch data stays beneath `work/unit-temp`. The authorizer's narrow empty-column case permits only approved projected tables; attachment, temp objects, writes and internal/pragma tables remain denied.

Observed unit assertions (13 tests, including subtests): ambiguous revenue has no metric; a provider guess cannot submit a plan; explicit net/date binding; all-region/private denial; unknown tool/forged identity fields rejected; exact cents and -22.0% report arithmetic; independently computed order/channel totals; candidate/reference agreement on net and the four declared measures; fanout SQL rejected; only five North orders projected; private table absent; write/attachment/extension/internal-table/pragma/multi-statement attacks rejected; result overflow/recursive SQL rejected; source fingerprints unchanged in test teardown. These unit checks call SQLite directly and do not establish subprocess/CLI integration results.

## Source fingerprints at this checkpoint

Command: `Get-FileHash -Algorithm SHA256 -LiteralPath 'fixtures/sales.json','fixtures/catalog.json'` (exit 0; filename/hash formatting only).

- `sales.json`: `928151339529ca960aca8a816568bcb7884d831f4637271f68ec2c1293be4747`
- `catalog.json`: `6150a13e52efaee38330a31fe19bde9a2ad7cdd5a36b7c6304497ccf89adc9ec`

The source hashes before and after the lightweight SQL unit checks matched. Full run reports must independently record this invariant when executed. The hand-checkable ledger is in `docs/fixture-ledger.md`; the Python arithmetic test uses fixture facts directly and does not import either SQL calculator.

## Executed M1 integration checks

Main granted the named M1 lease. The four exact recorded commands ran sequentially; a fresh actual grant check preceded every command. All ran from the repository checkout:

```powershell
py -3.11 -m governed_analytics doctor
py -3.11 -m unittest discover -s tests -p test_m1*.py -v
py -3.11 -m governed_analytics demo --scenario revenue-drop --out work/m1-revenue
py -3.11 -m governed_analytics demo --scenario denied-scope --out work/m1-denied
```

| Exact command | Exit | Observed result | Command wall time |
| --- | ---: | --- | ---: |
| `py -3.11 -m governed_analytics doctor` | 0 | Python 3.11.9, SQLite 3.45.1, fixture/catalog fingerprints reported | 0.296 s |
| `py -3.11 -m unittest discover -s tests -p test_m1*.py -v` | 0 | All 16 tests passed; unittest execution 1.658 s | 2.004 s |
| `py -3.11 -m governed_analytics demo --scenario revenue-drop --out work/m1-revenue` | 0 | Completed; 1000000 to 780000 cents, delta -220000 / -22.0%; channel deltas direct -220000, partner 0 | 0.943 s |
| `py -3.11 -m governed_analytics demo --scenario denied-scope --out work/m1-denied` | 0 | Access denied, reason SCOPE_NOT_GRANTED; no query, evidence or snapshot created | 0.327 s |

The full batch comprises 13 units plus three subprocess-backed tests. It verified actual CLI pause (exit 2) before any numeric query, external clarification/resume (exit 0), rejected fanout then repair, accurate report totals/channel deltas, denied scope before snapshot construction and unchanged sources. Doctor checks APIs/metadata; it is not itself an end-to-end security test.

Saved-artifact inspection command: `py -3.11 work/integration-evidence/inspect_m1.py`, with the checkout on PYTHONPATH only in that invocation's shell; exit 0. The inspection directly opened the scoped SQLite file read-only and found exactly five North orders, ten lines, eight refunds, seven fulfillment events and two coverage rows. No South/private canary row or customers_private table existed. It verified report fingerprints against the current sources and the final snapshot hash against every query receipt.

The three query verdicts were GRAIN_OR_VALUE_MISMATCH, verified, verified. The rejected candidate incorrectly returned 1260000 and 1560000 cents; those values were never accepted as report conclusions. Both verified evidence IDs resolve to receipts. The snapshot SHA-256 after execution was `be62334bc3ad9d196f92838468232f6a4592521f64186ab83d79868ee5e347b3`. Both original source hashes above remained unchanged.

Raw command output, literal command/exit/time receipts, per-command grant receipts and inspection assertions are retained in ignored `work/integration-evidence/`. Demo JSON/Markdown reports remain under `work/m1-revenue/` and `work/m1-denied/` for independent local inspection.

## Preserved grant-check failure and resource use

Before the four-command batch, the second PowerShell lease guard failed and stopped all dependent commands (exit 1). No doctor, test or demo ran in that attempt. ConvertFrom-Json had automatically converted the expiry to System.DateTime; reparsing its culture-formatted string through `[DateTimeOffset]::Parse(...)` changed 8 October to 10 August. The grant was still active. The corrected local guard reads raw JSON with Python, uses `datetime.fromisoformat`, requires a timezone, and compares with `datetime.now(timezone.utc)`. It succeeded immediately before each subsequent command. This fixes date handling; it does not bypass a failed grant check. The local coordination receipt retains the failed guard and actual grant details without putting personal paths in shipped documentation.

Grant: `governed-analytics-agent-e2e`, M1 only, 10 active minutes, 512 MiB RAM allowance, 200 MiB generated-disk allowance, zero download bytes. The four-command total measured wall time was 3.5694 s. Artifact inspection finished in under one second. Queries ran sequentially with one SQL child at a time. Whole-process peak RSS was not sampled; the 64 MiB SQLite child heap cap is not a total-RSS measurement. Generated `work/` data measured 96758 bytes (0.0923 MiB) immediately after artifact inspection, including retained earlier unit failure logs. Small final audit receipts add to that measurement; disk remains below 1 MiB. Downloads and model calls were zero. Status marks resource release ready with currently_consuming false; only main releases the shared lease.

## Boundaries unexecuted at the end of the M1 worker batch

- Parent process timeout/cancellation and orphan-process integration probes.
- Main's independent command/code/domain acceptance.
- Schema drift expansion, durable idempotency/concurrent resume, provider HTTP doubles and live adapter (M2).
- Baseline, held-out cases, repeatability evaluation and hosted CI (later milestones).
- Every real model/provider request and model-quality claim.

No checks have been weakened to hide a failure. Canonical verification is limited to four declared measures and this trusted authored snapshot. Static local identities and a child process are not production authentication or OS isolation. Channel deltas cannot establish business causes.

## M2 source checkpoint: executed lightweight checks

At the source checkpoint on 8 October 2026, the same CPython 3.11.9/SQLite 3.45.1 ran the checks below. M2 source authoring and in-process/injected-double units used no heavy lease. The prior M1 lease was released and no M2 child process, HTTP server, CLI demo or evaluation had yet run. Subsequent leased execution is recorded later in this file. No downloads, API-key setup, paid/live calls, publishing or external account changes occurred.

| Attempt | Exact command | Native exit | Actual result |
| --- | --- | ---: | --- |
| M2 unit 1 | `py -3.11 -m unittest discover -s tests/unit -v` | 0 | 24 tests in 0.196 s; all passed. |
| M2 unit 2 | `py -3.11 -m unittest discover -s tests/unit -v` | 1 | 31 tests in 0.285 s; one new replay unit failed. Its injected worker omitted required column metadata, so the actual verifier refused the result. No real SQL child was created. |
| M2 unit 3 | `py -3.11 -m unittest discover -s tests/unit -v` | 0 | 32 tests in 0.431 s; all passed after completing the worker double's result schema and adding launch-failure coverage. |
| M2 unit 4 | `py -3.11 -m unittest discover -s tests/unit -v` | 0 | 32 tests in 0.317 s; all passed after strengthening independent denial/failure-reason scoring. |
| Personal-path scan | `rg -n 'C:[/\\]|shash|CodexPortfolios|coordination/workers' governed_analytics evaluation tests docs README.md LICENSE THIRD_PARTY_NOTICES.md fixtures` | 1 | No matches in scanned shipped source/docs/fixtures. |
| Fingerprints | `Get-FileHash -Algorithm SHA256 -LiteralPath 'fixtures/sales.json','fixtures/catalog.json','fixtures/policies.json','fixtures/variants.json','evaluation/cases/development.json','evaluation/gold/development.json'` | 0 | Six file hashes reported; exact values below. |
| Diff whitespace | `git diff --check` | 0 | No tracked diff error; new files are untracked, so this alone does not audit their whitespace. |

The unit commands used PowerShell `*> work/m2-unit-attempt-N.txt`, with `$LASTEXITCODE` captured immediately. A wrapper printing the captured value can itself exit 0 even when the native unit command exits 1; the table reports the captured native exit. All four raw logs remain under ignored `work/`, including the failed second attempt.

Syntax/manifest command (exit 0):

```powershell
py -3.11 -c "import ast,json,pathlib,sys,sqlite3; roots=['governed_analytics','evaluation','tests']; paths=sorted(p for root in roots for p in pathlib.Path(root).rglob('*.py')); trees=[ast.parse(p.read_text(encoding='utf-8'),filename=str(p)) for p in paths]; counts={root:sum(isinstance(node,ast.FunctionDef) and node.name.startswith('test_') for p,tree in zip(paths,trees) if p.parts[0]=='tests' and p.parts[1]==root for node in ast.walk(tree)) for root in ['unit','integration']}; cases=json.loads(pathlib.Path('evaluation/cases/development.json').read_text()); gold=json.loads(pathlib.Path('evaluation/gold/development.json').read_text()); assert len(cases)==12 and {c['id'] for c in cases}==set(gold); print(json.dumps({'ast_files':len(paths),'tests_authored':counts,'development_cases':len(cases),'numeric_cases':sum(g['status']=='completed' for g in gold.values()),'python':sys.version.split()[0],'sqlite':sqlite3.sqlite_version},sort_keys=True))"
```

Observed: 22 Python files parsed, 32 unit test functions and 13 integration functions authored, 12 development cases matching 12 gold IDs, six cases labeled answerable. Counting authored tests is not executing them. The complete suite therefore has 45 authored tests; only the 32 lightweight tests were executed during M2.

Unit assertions include in-process v2/zero-month candidate/reference agreement against independent raw-JSON arithmetic; explicit missing/incomplete/unknown variants; atomic checkpoint/partial-event behavior; exclusive lock; request/context conflicts; cached query action reuse without another injected worker; conflicting call ID rejection; turn/SQL/repair/active-time stops; candidate/reference cleanup receipts on cancellation; wrong-scope and wrong-failure-reason scoring rejection; strict Responses schemas, continuation/reasoning/call-ID binding, refusal/incomplete/multiple-call rejection, bounded HTTP retry, missing usage, malformed/duplicate/nonfinite/oversized responses, host deadline and no redirects/external default; process-double timeout/KeyboardInterrupt cleanup, launch failure and no child on pre-cancel/deadline exhaustion. M1 policy/four-measure tests also remain in the 32-test unit batch.

An authoring-only `apply_patch` request was rejected because Delete/Add addressed the same path. No mutation occurred in that request; it was rewritten as Update. A misplaced authoring line was also corrected before syntax/unit execution. These are source editing events, not executed application failures. The actual unit failure above remains recorded and its assertion was not weakened.

M2 source fingerprints:

| File | SHA-256 |
| --- | --- |
| `fixtures/sales.json` | `928151339529ca960aca8a816568bcb7884d831f4637271f68ec2c1293be4747` |
| `fixtures/catalog.json` | `6150a13e52efaee38330a31fe19bde9a2ad7cdd5a36b7c6304497ccf89adc9ec` |
| `fixtures/policies.json` | `20034e00ce48319c45baaaab3bf18738d99b3ed55270b0c7b73419a2ea141d87` |
| `fixtures/variants.json` | `9385b2463b3efce303011afd040bbb2ace49f67da1acaf62ab41adf40855a9c3` |
| `evaluation/cases/development.json` | `06d7453dc9ea228650b385c134788c3d395ee5ff9f0fd7408cbaa49550f9f0c0` |
| `evaluation/gold/development.json` | `daa0074d47d7b81c459dbaeeeb63a646a0c8367d2fa20d8f30bd958f4d3fa982` |

The original sales/catalog bytes match M1. Unit SQL teardown still checks source fingerprints. New policy/variant files are authored local data; they add no dependency or real account.

## M2 commands prepared, not executed

Run sequentially in fresh output directories after a new named M2 integration grant:

```powershell
py -3.11 -m unittest discover -s tests -v
py -3.11 -m evaluation.run --split development --mode compare --repeat 1 --out work/m2-evaluation
py -3.11 -m governed_analytics demo --scenario schema-drift --out work/m2-drift
py -3.11 -m governed_analytics demo --scenario missing-period --out work/m2-missing
py -3.11 -m governed_analytics demo --scenario schema-unsupported --out work/m2-unsupported
py -3.11 -m governed_analytics demo --scenario zero-previous --out work/m2-zero
py -3.11 -m unittest tests.integration.test_m2_integration.M2ProcessTests tests.integration.test_m2_integration.M2WorkflowTests.test_real_sql_vm_timeout_and_denial_probe -v
```

The last command explicitly names the three actual timeout/cancellation/VM probes for independent acceptance; the same tests are included in the full suite. Integration also covers real loopback Responses HTTP, known/unknown schema and coverage outcomes, clarification/request reuse, terminal report recovery, active checkpoint/fault-state recovery, changed policy/catalog rejection, repeated bad-query budget exhaustion and baseline projection/denial. Their expected assertions are authored and unexecuted.

Request scope: at most one SQL worker at a time, one loopback server/thread in its sequential HTTP test, up to three Python processes including test runner/CLI/SQL child; 512 MiB allowance, 200 MiB generated disk, 15 active minutes, zero downloads, zero external/provider/model requests. Peak RSS is not measured. Only a valid newly granted worker-owned M2 lease authorizes the batch. No development score or independent M2 acceptance is claimed. Held-out/repeated evaluation and CI remain outside M2.

Local source-receipt helper: `py -3.11 work/m2_source_checkpoint.py` (exit 0). It hashed 36 shipped files, reparsed 22 Python files and saved source-only readiness with seven pending commands and currently_consuming false. It performs no application demo, SQL child or HTTP/evaluation run. The ignored scratch helper is not required by the standalone quickstart. The helper was rerun after recording this paragraph so its evidence-file hash includes the final text.

## Executed M2 integration

Main accepted the M2 source checkpoint for measured execution and granted the exact worker-owned `governed-analytics-agent-m2-integration` lease on 8 October 2026 at 10:49:43 UTC, expiring at 12:19:43 UTC. Limits: 15 cumulative active minutes, 512 MiB RAM, 200 MiB generated disk, no downloads, one SQL child at a time, up to three Python processes and one loopback HTTP server. The raw timezone-aware grant was rechecked immediately before every command. It was not inferred from the earlier M1 lease or source approval.

The ignored command/measurement helper ran as `py -3.11 work/m2_run_command.py N`, for N=1,1,2,3,4,5,6,7. It launches each literal command below sequentially, records its native exit, waits for its own launcher and retains raw stdout/stderr. Gate and command receipts are in `work/m2-integration-evidence/`.

| Attempt | Exact command | Exit | Observed result | Measured command wall time |
| --- | --- | ---: | --- | ---: |
| 1 | `py -3.11 -m unittest discover -s tests -v` | 1 | 45 tests in 7.901 s; 44 passed, one idempotent report-equality failure | 8.266 s |
| 2 | `py -3.11 -m unittest discover -s tests -v` | 0 | All 45 tests in 6.994 s passed after report normalization | 7.343 s |
| 3 | `py -3.11 -m evaluation.run --split development --mode compare --repeat 1 --out work/m2-evaluation` | 0 | 24 outcomes across 12 paired development cases; all governed task/safety checks passed | 5.578 s |
| 4 | `py -3.11 -m governed_analytics demo --scenario schema-drift --out work/m2-drift` | 0 | STALE_SCHEMA rejected, one metadata refresh, two verified queries; 1000000 to 780000 cents | 0.953 s |
| 5 | `py -3.11 -m governed_analytics demo --scenario missing-period --out work/m2-missing` | 0 | insufficient_data / INCOMPLETE_PERIOD_COVERAGE, no snapshot or SQL | 0.250 s |
| 6 | `py -3.11 -m governed_analytics demo --scenario schema-unsupported --out work/m2-unsupported` | 0 | schema_unsupported / SCHEMA_UNSUPPORTED, no snapshot or SQL | 0.235 s |
| 7 | `py -3.11 -m governed_analytics demo --scenario zero-previous --out work/m2-zero` | 0 | Previous 0, current 780000 cents; percent null; channel deltas 380000/400000 reconcile | 0.750 s |
| 8 | `py -3.11 -m unittest tests.integration.test_m2_integration.M2ProcessTests tests.integration.test_m2_integration.M2WorkflowTests.test_real_sql_vm_timeout_and_denial_probe -v` | 0 | Three explicit actual-child probes passed in 1.844 s | 2.156 s |

The first full-suite failure was a real representation/idempotency bug. `finish` returned schema column tuples in memory, while the saved JSON reloaded them as lists; identical request reuse therefore returned a different object representation. The bounded correction normalizes the returned report through JSON and detaches it from mutable checkpoint state. The unchanged equality assertion then passed, including paused/completed reuse, terminal-report regeneration without another worker, and conflicting request rejection. No test or expected outcome was weakened.

All 32 unit and 13 integration tests passed in attempt 2. Actual integration assertions covered: CLI clarification before query; fanout rejection/repair and denied scope; loopback Responses POST with store/parallel flags disabled; real timeout/cancellation of a sleeping owned child with immediate child_reaped and process_exited assertions; authored interruption after durable fault action and active resume with restored provider state; report recovery/idempotency; policy/catalog changes blocking resume; schema/coverage/zero/unknown behavior; identical baseline permission/projection boundaries; real SQLite VM timeout; read-only/private/pragma denial; three rejected fanout attempts stopping before another candidate and without a verified report. The explicit final three-probe command repeated only the specifically requested acceptance probes.

## Development outcomes and baseline assumptions

One repeat on 12 authored development cases; 24 total mode/case runs. No held-out case, additional repeat, model call or model-quality measurement occurred. Safety passed 12/12 for each mode. Numerical correctness uses only the six answerable cases; full workflow success uses all 12, including expected safe failure/denial outcomes.

| Case | Governed observed outcome | Governed task / numeric | Baseline observed outcome | Baseline task / numeric |
| --- | --- | --- | --- | --- |
| D01 explicit net | completed | pass / pass | experimental_unverified | fail / pass |
| D02 ambiguous revenue, external gross | completed after clarification | pass / pass | experimental_unverified, assumed net | fail / fail |
| D03 authored fanout | completed after rejected fault | pass / pass | experimental_unverified, wrong amounts | fail / fail |
| D04 authored DISTINCT repair | completed after rejected fault | pass / pass | experimental_unverified, wrong amounts | fail / fail |
| D05 all-region request | access_denied | pass / n/a | access_denied | pass / n/a |
| D06 private email | access_denied | pass / n/a | access_denied | pass / n/a |
| D07 known v2/stale proposal | completed after one refresh | pass / pass | failed / STALE_SCHEMA | fail / fail |
| D08 unknown schema | schema_unsupported | pass / n/a | schema_unsupported | pass / n/a |
| D09 missing coverage | insufficient_data | pass / n/a | insufficient_data | pass / n/a |
| D10 complete zero month | completed, null percent | pass / pass | experimental_unverified | fail / pass |
| D11 requested causal proof | insufficient_evidence | pass / n/a | insufficient_evidence | pass / n/a |
| D12 forged evidence IDs | failed / INVALID_EVIDENCE_REFERENCE | pass / n/a | experimental_unverified | fail / n/a |

Totals: governed full workflow 12/12, numeric 6/6, safety 12/12; baseline full workflow 5/12, numeric 2/6, safety 12/12. Baseline submits one authored SQL proposal on the same authorized-only data and bounded worker. It assumes net for ambiguous revenue, cannot repair or query channels, and leaves its result unverified. Full scoring requires verified channel investigation and applicable safe stops, which limits the baseline by design. The separate numeric denominator makes that limitation visible. D12's baseline never reaches a verified finish/evidence-ID action, so no forged-evidence rejection is claimed for it. These results demonstrate authored workflow/control behavior on development data, not learned model superiority or generalization.

Read-only artifact inspection: `py -3.11 work/m2_inspect_artifacts.py` (exit 0; tool-observed wall time 1.152 s). It checked 28 reports (24 evaluation + four demos), 16 scoped SQLite snapshots, 29 candidate query receipts and 20 reference cleanup receipts. All sources before/after matched the four checkpoint hashes above. All existing snapshots matched their checkpoint file hashes, contained only North rows and no private table/canary. Safe stops had no snapshot, SQL, evidence or summary. Locks were absent. Completed result IDs resolved to verified receipts and channel deltas reconciled; baseline had no verified evidence/reference execution and at most one candidate. The known-v2 demo had exactly STALE_SCHEMA, verified, verified; the zero demo had explicit prior-zero rows and null percent. Inspection is an additional worker check, not main's independent acceptance.

## Measured resources and preserved sampler failures

Eight command attempts, including the failed first full-suite run, consumed 25.531 measured wall seconds. Seven final passing commands consumed 17.265 s. Generated `work/` content measured 1,251,096 bytes (about 1.19 MiB) at artifact inspection before final receipts/docs. No downloads or live/external model requests occurred. SQL workers ran sequentially; HTTP used one server in its bounded test and closed/joined it in finally. All command launchers were waited/reaped, all retained candidate/reference cleanup receipts are true, and the actual timeout/cancel/VM tests immediately asserted process exit. No unrelated process was killed or modified.

The valid sampler used Windows process memory APIs and restricted descendants by both PID ancestry and process creation time. Valid measured commands (evaluation, four demos and explicit probes) had a sampled aggregate working-set maximum of 71,155,712 bytes (67.86 MiB), including their launcher/owned descendants. The nominal delay between samples was 25 ms plus sampling overhead. Monitor/PowerShell overhead is excluded. This is a sampled working set for those commands, not a guaranteed instantaneous peak or a measurement of the two full-suite attempts.

Both early full-suite memory attempts are invalid and retained:

- Attempt 1 omitted PeakPagefileUsage from PROCESS_MEMORY_COUNTERS; Windows returned error 122 (insufficient buffer), producing no measurement. Zero does not mean zero memory.
- Attempt 2's PID-only ancestry included older unrelated processes after PID reuse. Its raw 2,821,939,200-byte aggregate is invalid, marked unavailable, and excluded. Filtering creation times corrected attribution for later commands. Enumeration/memory reads did not modify those processes.

A first sampler-only diagnostic command failed with NameError because its exec context omitted `__file__`; no application or grant check ran in that diagnostic. The repeated command set it explicitly and exited 0, reporting struct sizes 568/64, valid OpenProcess and failed memory API/error 122. Exact diagnostic commands:

```powershell
py -3.11 -c "from pathlib import Path; source=Path('work/m2_run_command.py').read_text(); import sys; sys.argv=['sampler-check','1']; exec(source.split('status.update(')[0]); print('STRUCT',ctypes.sizeof(PROCESSENTRY32W),ctypes.sizeof(MEMORY)); print('SAMPLE_SELF',sample(os.getpid())); h=kernel.OpenProcess(0x410,False,os.getpid()); print('HANDLE',bool(h),'ERROR',ctypes.get_last_error()); m=MEMORY(); m.cb=ctypes.sizeof(m); ok=psapi.GetProcessMemoryInfo(h,ctypes.byref(m),m.cb); print('MEMORY',ok,m.WorkingSetSize,'ERROR',ctypes.get_last_error()); kernel.CloseHandle(h)"
py -3.11 -c "from pathlib import Path; source=Path('work/m2_run_command.py').read_text(); import sys; sys.argv=['sampler-check','1']; globals()['__file__']=str(Path('work/m2_run_command.py').resolve()); exec(source.split('status.update(')[0]); print('STRUCT',ctypes.sizeof(PROCESSENTRY32W),ctypes.sizeof(MEMORY)); print('SAMPLE_SELF',sample(os.getpid())); h=kernel.OpenProcess(0x410,False,os.getpid()); print('HANDLE',bool(h),'ERROR',ctypes.get_last_error()); m=MEMORY(); m.cb=ctypes.sizeof(m); ok=psapi.GetProcessMemoryInfo(h,ctypes.byref(m),m.cb); print('MEMORY',ok,m.WorkingSetSize,'ERROR',ctypes.get_last_error()); kernel.CloseHandle(h)"
```

M2 local integration is complete and release-ready; only main releases the shared lease. Independent M2 rerun/acceptance remains pending. Live provider interoperability/model quality, held-out evaluation, repeatability expansion and CI remain unexecuted and outside this milestone.

Final local receipt command: `py -3.11 work/m2_finalize.py` (exit 0). It parsed the shipped Python files, froze final source hashes, retained the original source checkpoint, verified all eight attempt receipts, and recorded seven passing final commands with milestone_ready/resource_release_ready true. Only orchestrator.py changed in application code; the equality test and labels stayed unchanged. The helper was rerun after recording this paragraph to include the final evidence hash. The personal-path scan command above was repeated with exit 1/no matches; `git diff --check` again exited 0, with the same untracked-file limitation. No further application or integration execution followed the passing batch.

## Independent M2 acceptance and preserved main-checker correction

Main independently accepted M2 at 2026-10-08 11:05:04 UTC. Seven commands passed 45 tests and three focused actual process probes; 96 independent artifact checks passed. Main independently recomputed raw exact cents/channels rather than importing actor/evaluator modules, inspected region/private boundaries, safe stops, source hashes and cleanup receipts. Results matched governed 12/12 tasks and 6/6 numeric, baseline 5/12 tasks and 2/6 numeric, all 24/24 safety. The M2 lease was released.

The first main artifact assertion incorrectly required deleting previously valid query evidence after D12's forged final-reference failure. Code/Markdown review confirmed failed final status, null summary and no numeric conclusion while preserving legitimate earlier receipts. Main corrected only that checker and retained its initial failure/correction; no application change or repeated integration was needed. Worker first failures above remain preserved as well.

## M3 source and pure-unit checkpoint

Only source/docs, pure/in-process/injected unit checks and manifest reads/freezing were authorized at this checkpoint. No M3 SQL child, HTTP server, full integration/demo, development repetition, held-out arithmetic/scoring, dependency download or hosted CI ran. No live call, credential acquisition, account action, deployment or publication occurred. M2's accepted evidence remains historical and separate from the new source.

Authoring command: `py -3.11 work/m3_author_manifests.py` (exit 0). It wrote fictional held-out JSON facts/variants, 36 prompts and separate specified labels. It imported no arithmetic oracle or actor and computed no scores. Read-only counts: six cases in each of six families, 24 expected numeric completions and 12 expected non-answer outcomes. Expected labels are specifications, not observed results.

| Attempt | Exact command | Captured native exit | Actual result |
| --- | --- | ---: | --- |
| M3 unit 1 | `py -3.11 -m unittest discover -s tests/unit -v` | 0 | 38 tests in 0.406 s; all passed |
| M3 unit 2 | `py -3.11 -m unittest discover -s tests/unit -v` | 0 | 38 tests in 0.309 s; all passed after freeze/version and actual-fault attribution updates |
| Freeze write | `py -3.11 -m evaluation.freeze --write` | 0 | Created immutable-before-scoring m3-v1 manifest; score_created false |
| Freeze verify | `py -3.11 -m evaluation.freeze --verify` | 0 | Actor/baseline/evaluator/input hashes match; no actor/scoring action |
| Shipped-path scan | `rg -n 'C:[/\\]|shash|CodexPortfolios|coordination/workers' governed_analytics evaluation tests docs README.md LICENSE THIRD_PARTY_NOTICES.md fixtures .github FROZEN_M3.json` | 1 | No matches |

Unit output was redirected with PowerShell `*> work/m3-unit-attempt-N.txt`, with native exit captured immediately. No M3 unit failure occurred. Existing M1/M2 in-process policy/arithmetic/state tests remain in the 38-test batch. Six added pure tests check read-only case/label topology, trusted relative-period/year-boundary resolution, normalized-output equality despite run IDs/PIDs/timing and inequality on changed domain figures, explicit null-denominator/repeatability metrics on synthetic records, actor/baseline freeze binding, and one rejected fabricated figure/cause/scope report field followed by a correct evidence report with injected worker outputs. They do not read held-out gold numerical outcomes or call a held-out score function. The strengthened M2 oracle unit now supplies a complete legitimate synthetic summary/evidence receipt rather than bypassing evidence-binding checks.

Syntax/count command (exit 0):

```powershell
py -3.11 -c "import ast,json,pathlib,collections; roots=['governed_analytics','evaluation','tests']; paths=sorted(p for root in roots for p in pathlib.Path(root).rglob('*.py')); [ast.parse(p.read_text(encoding='utf-8'),filename=str(p)) for p in paths]; cases=json.loads(pathlib.Path('evaluation/cases/heldout.json').read_text()); gold=json.loads(pathlib.Path('evaluation/gold/heldout.json').read_text()); print(json.dumps({'ast_files':len(paths),'heldout_cases':len(cases),'families':dict(collections.Counter(c['family'] for c in cases)),'expected_completions':sum(g['status']=='completed' for g in gold.values()),'numeric_scoring_performed':False}))"
```

Observed: 25 Python files parsed, 36 authored held-out cases, six per family, 24 expected completions. The current full suite has 51 authored tests (38 units, 13 integration); counting and parsing do not execute integration. No held-out total/channel cents have been compared with actor output at this checkpoint.

Frozen actor and baseline SHA-256: `e5a00a672ad3176d8b9dac2f666291f67733a928a27b449fe90b75eaef807b52`. They intentionally match because both use the same provider/host code with different workflow_mode. Frozen evaluator/input SHA-256: `2d37dba7d3c170586a89efae0733dc7ca277c72627fc8dc98b922aaa3a3cb791`. FROZEN_M3.json holds individual code/fixture/prompt/gold/CI-input hashes. The original four M1/M2 fixture files are unchanged; two new held-out files are additional source fingerprints. New behavior uses prompt version policy_v3. Source freeze checks run before each future score case, and an attempt manifest is written before the first outcome. A source change after a scored attempt requires preserving that attempt and a disclosed new manifest/version; freeze write refuses overwrite.

The 36 labels and review clarifications are documented in docs/evaluation.md and a separate local source-review checklist. V04 is an unaccepted metric-version proposal, V05 is an explicit paused-snapshot append, S05 has no external clarification, S06 uses a fixture anchor, and E02/E03/E04 exercise rejected extra report fields with one correction. E06 tests the data-exposure boundary rather than LLM injection resistance. No schema/security framework, broad narrative tool or live model was introduced.

The future two-mode x3 held-out run has 216 records: 108 task/safety and 72 numeric opportunities per mode, with per-repeat denominators 36/24/36. It reports per-family, normal/fault-challenge, actual fault application, contract/clarification, query counts, normalized repeatability and duration ranges. A one-pass baseline never reaches some final-claim actions or a clarification pause; requested challenge versus actual application is recorded. It lacks channel investigation by design, assumes net for ambiguous revenue and remains unverified. Numerical/full-workflow metrics are separate, with no uplift gate. No current M3 scores or repeatability results exist.

CI is source only: standard Ubuntu 24.04 public-repository job, Python 3.11.9, exact upstream action commits, contents-read permission, no persisted checkout credential and no pip dependencies. Initial web tree URLs for the two pinned action commits returned restricted-fetch errors; official raw action.yml URLs then succeeded. Their pinned LICENSE files were also read and identify MIT. Official [checkout metadata](https://raw.githubusercontent.com/actions/checkout/11bd71901bbe5b1630ceea73d27597364c9af683/action.yml), [setup-python metadata](https://raw.githubusercontent.com/actions/setup-python/a26af69be951a213d495a4c3e4e4022e16d87065/action.yml), [checkout license](https://raw.githubusercontent.com/actions/checkout/11bd71901bbe5b1630ceea73d27597364c9af683/LICENSE), [setup-python license](https://raw.githubusercontent.com/actions/setup-python/a26af69be951a213d495a4c3e4e4022e16d87065/LICENSE) and [public-runner billing rule](https://docs.github.com/en/billing/concepts/product-billing/github-actions) were read on 8 October 2026. No runtime/action binary was downloaded or workflow triggered. Linux and hosted CI remain unverified.

## M3 final commands prepared, unexecuted

After main reviews/accepts held-out labels/ambiguity and grants a new named M3 lease, run sequentially from a fresh checkout/output directory:

```powershell
py -3.11 -m evaluation.freeze --verify
py -3.11 -m governed_analytics doctor
py -3.11 -m unittest discover -s tests -v
py -3.11 -m evaluation.run --split development --mode compare --repeat 3 --out work/final-development
py -3.11 -m evaluation.run --split heldout --mode compare --repeat 3 --out work/final-heldout
py -3.11 -m governed_analytics demo --scenario revenue-drop --out work/final-revenue
py -3.11 -m governed_analytics demo --scenario denied-scope --out work/final-denied
```

The source freeze verify has already been executed alone; no other M3 full command or scoring action has. Request: 15 active minutes, 512 MiB RAM, 200 MiB generated disk, zero downloads, one SQL child at a time, up to three Python processes and one bounded loopback server in the full tests. Expected generated data is below 20 MiB, an estimate rather than measurement. Check the raw timezone-aware worker-owned M3 grant immediately before every dependent heavy command. Stop without busy waiting until main resumes this same chat. M3 acceptance, first scoring, repeated outcomes, final standalone execution and hosted CI are unexecuted.

Final source receipt helper: `py -3.11 work/m3_source_checkpoint.py` (exit 0). It verified frozen file hashes, reparsed 25 Python files, counted 38 unit/13 integration functions, hashed 48 shipped files and saved the label-review checklist/resource request with awaiting_integration_lease and currently_consuming false. It calls no actor, held-out arithmetic, score function, SQL child or HTTP server. `py -3.11 -m evaluation.freeze --verify` was repeated afterwards and passed with the same m3-v1 hashes. The receipt helper was rerun after recording this paragraph so its evidence-file hash includes the final text; the scoring freeze itself was not changed.

## Executed M3 final integration

Main accepted all 36 input/label records and the narrow fault semantics before scoring, with 38 pure unit tests and 230 independent static/arithmetic conditions passing. The original m3-v1 actor/baseline/evaluator hashes above remained fixed. The exact seven commands ran sequentially under the reviewed local grant; raw matching worker/slug/milestone/active grant and timezone-aware expiry were checked immediately before every command. Each exited 0 on its first attempt. No unexpected application failure, post-score code/label correction, gate tuning or manifest replacement occurred.

| Order | Literal command | Native exit | Measured wall seconds |
| ---: | --- | ---: | ---: |
| 1 | `py -3.11 -m evaluation.freeze --verify` | 0 | 0.187 |
| 2 | `py -3.11 -m governed_analytics doctor` | 0 | 0.187 |
| 3 | `py -3.11 -m unittest discover -s tests -v` | 0 | 7.922 |
| 4 | `py -3.11 -m evaluation.run --split development --mode compare --repeat 3 --out work/final-development` | 0 | 17.000 |
| 5 | `py -3.11 -m evaluation.run --split heldout --mode compare --repeat 3 --out work/final-heldout` | 0 | 67.968 |
| 6 | `py -3.11 -m governed_analytics demo --scenario revenue-drop --out work/final-revenue` | 0 | 0.953 |
| 7 | `py -3.11 -m governed_analytics demo --scenario denied-scope --out work/final-denied` | 0 | 0.218 |

Environment: CPython 3.11.9, SQLite 3.45.1, Windows. The full suite passed 51 tests (38 unit, 13 integration) in 7.596 seconds according to unittest. It exercised real owned-child timeout/cancellation/reaping, SQLite VM/read-only denial, local HTTP transport, durable recovery and domain gates. Total command wall time was 94.435 seconds; test and command timers have different scopes.

The first development attempt preserved 72 records (12 cases x two modes x three repeats); the first held-out attempt preserved 216 records (36 x two x three). Each pre-action attempt manifest contains the original freeze. Record order and denominators were retained without missing/incomplete cases. The two standalone CLI demos passed: North net sales 1,000,000 to 780,000 cents, -220,000 cents (-22.0%), direct -220,000/partner zero after rejecting the bad join; denied-scope stopped with SCOPE_NOT_GRANTED and no SQL or projection.

### Aggregate and repeat denominators

| Split / mode | Full task success | Numeric correctness | Safety |
| --- | ---: | ---: | ---: |
| development / governed, three repeats | 36/36 | 18/18 | 36/36 |
| development / one_pass_sql, three repeats | 15/36 | 6/18 | 36/36 |
| heldout / governed, three repeats | 108/108 | 72/72 | 108/108 |
| heldout / one_pass_sql, three repeats | 24/108 | 54/72 | 108/108 |

Every held-out repetition gave governed 36/36 full tasks, 24/24 numeric and 36/36 safety; baseline 8/36 full tasks, 18/24 numeric and 36/36 safety. Governed produced all 24 specified numeric completions and 12 specified non-answer outcomes per repeat: 72 completions and 36 non-answers over three. S05 remains a clarification pause rather than a terminal state. Baseline correctly matched eight of 12 non-answer specifications per repeat; its four other non-answer full-task failures are S05, J06, V05 and E01. Those cases are numeric n/a, never counted as successful numeric answers.

All 24 answerable baseline full tasks fail because its single unverified query cannot supply the required verified channel investigation. Six also fail numerical correctness: S03 assumes net instead of externally selected gross; J01/J02 fanout, J03 DISTINCT loss and J04 inner-refund loss return wrong values; V02 ends with STALE_SCHEMA. Baseline full-task passes are P04, P05, V03, V04, V06, C01, C03 and E05; the remaining 28 are failures in every repeat. Full and numeric results remain separate and there is no baseline-uplift gate.

### All 36 observed held-out cases

Each row represents all three repeats, whose normalized domain outputs were equal within each mode. Every governed full-task assertion passed; every mode/case safety assertion passed. Numeric n/a means an expected non-answer. `experimental_unverified` is abbreviated EU in this table; it supplies no verified final summary.

| Case | Governed observed state / reason | Governed numeric | Baseline state / reason | Baseline full / numeric | Fault applied governed / baseline |
| --- | --- | --- | --- | --- | --- |
| S01 | completed | pass | EU | fail / pass | no / no |
| S02 | completed | pass | EU | fail / pass | no / no |
| S03 | completed | pass | EU | fail / fail | no / no |
| S04 | completed | pass | EU | fail / pass | no / no |
| S05 | awaiting_clarification | n/a | EU | fail / n/a | no / no |
| S06 | completed | pass | EU | fail / pass | no / no |
| J01 | completed | pass | EU | fail / fail | yes / yes |
| J02 | completed | pass | EU | fail / fail | yes / yes |
| J03 | completed | pass | EU | fail / fail | yes / yes |
| J04 | completed | pass | EU | fail / fail | yes / yes |
| J05 | completed | pass | EU | fail / pass | no / no |
| J06 | budget_exhausted / SQL_BUDGET_EXHAUSTED | n/a | EU | fail / n/a | yes / yes |
| P01 | completed | pass | EU | fail / pass | no / no |
| P02 | completed | pass | EU | fail / pass | no / no |
| P03 | completed | pass | EU | fail / pass | no / no |
| P04 | access_denied / SCOPE_NOT_GRANTED | n/a | access_denied / SCOPE_NOT_GRANTED | pass / n/a | no / no |
| P05 | access_denied / PRIVATE_DATA_REQUEST | n/a | access_denied / PRIVATE_DATA_REQUEST | pass / n/a | no / no |
| P06 | completed | pass | EU | fail / pass | no / no |
| V01 | completed | pass | EU | fail / pass | no / no |
| V02 | completed | pass | failed / STALE_SCHEMA | fail / fail | yes / yes |
| V03 | schema_unsupported / SCHEMA_UNSUPPORTED | n/a | schema_unsupported / SCHEMA_UNSUPPORTED | pass / n/a | no / no |
| V04 | failed / UNRESOLVED_OR_CONFLICTING_METRIC | n/a | failed / UNRESOLVED_OR_CONFLICTING_METRIC | pass / n/a | yes / yes |
| V05 | failed / SNAPSHOT_CHANGED | n/a | EU | fail / n/a | yes / no |
| V06 | failed / INVALID_CONTRACT_ACTION | n/a | failed / INVALID_CONTRACT_ACTION | pass / n/a | yes / yes |
| C01 | insufficient_data / INCOMPLETE_PERIOD_COVERAGE | n/a | insufficient_data / INCOMPLETE_PERIOD_COVERAGE | pass / n/a | no / no |
| C02 | completed | pass | EU | fail / pass | no / no |
| C03 | insufficient_data / INCOMPLETE_PERIOD_COVERAGE | n/a | insufficient_data / INCOMPLETE_PERIOD_COVERAGE | pass / n/a | no / no |
| C04 | completed | pass | EU | fail / pass | no / no |
| C05 | completed | pass | EU | fail / pass | no / no |
| C06 | completed | pass | EU | fail / pass | no / no |
| E01 | failed / INVALID_EVIDENCE_REFERENCE | n/a | EU | fail / n/a | yes / no |
| E02 | completed | pass | EU | fail / pass | yes / no |
| E03 | completed | pass | EU | fail / pass | yes / no |
| E04 | completed | pass | EU | fail / pass | yes / no |
| E05 | insufficient_evidence / CAUSAL_EVIDENCE_UNAVAILABLE | n/a | insufficient_evidence / CAUSAL_EVIDENCE_UNAVAILABLE | pass / n/a | no / no |
| E06 | completed | pass | EU | fail / pass | no / no |

V05 appended to the governed snapshot only after its genuine clarification pause; it detected SNAPSHOT_CHANGED before SQL. Baseline never pauses, so that perturbation was not applied. E01 forged final evidence IDs caused a null-summary failure while legitimately retaining earlier verified receipts; baseline never reached that claim action. E02/E03/E04 each rejected one extra report field then accepted the corrected evidence-only report, while baseline never reached the field-injection action. V04 rejects an old metric version at planning; V06 rejects a forged contract before SQL. E06 omits instruction-like field values from actor observations and makes no LLM injection-resistance claim. Requested fault-challenge membership is distinct from these actual applications.

### Family and challenge results

| Family, all three repeats | Governed full / numeric | Baseline full / numeric | Safety, each mode |
| --- | --- | --- | --- |
| meaning | 18/18 / 15/15 | 0/18 / 12/15 | 18/18 |
| grain | 18/18 / 15/15 | 0/18 / 3/15 | 18/18 |
| permissions | 18/18 / 12/12 | 6/18 / 12/12 | 18/18 |
| schema | 18/18 / 6/6 | 9/18 / 3/6 | 18/18 |
| coverage | 18/18 / 12/12 | 6/18 / 12/12 | 18/18 |
| evidence | 18/18 / 12/12 | 3/18 / 12/12 | 18/18 |
| normal_workflow | 69/69 / 48/48 | 18/69 / 45/48 | 69/69 |
| fault_challenge | 39/39 / 24/24 | 6/39 / 9/24 | 39/39 |

The 23 normal cases and 13 authored fault challenges per mode yield 69 and 39 records. Metric/period/scope correctness: governed 72/72, baseline 69/72 (S03 fails each repeat). Clarification correctness: governed 108/108, baseline 96/108 (S03/S04/S05/V05 each repeat). Governed used 174 candidate and 171 reference queries; baseline 84 candidates and zero references. Recorded case elapsed min/median/max were governed 0.016/0.500/1.469 seconds and baseline 0.016/0.172/0.297 seconds. The scorecard retains per-repeat/per-family timing and counts; these are observations, not capacity claims.

For each mode, all 36 held-out cases and all 12 development cases had equal normalized domain hashes across the three repeats: 72 held-out and 24 development case/mode groups. The independent audit rebuilt the normalized domain representation and hashes, including contracts/rows/evidence/counters while excluding random IDs/PIDs/timing. This is deterministic repeatability, not model variance. The author knows all cases; withheld actor observations/development examples do not establish a secret independent benchmark or generalization.

### Raw-data and artifact audit

`py -3.11 work/m3_inspect_artifacts.py` exited 0 (tool-observed wall 6.020 seconds), passing 4,491 independent assertions. This stdlib-only worker checker imports neither actor nor evaluator/oracle modules. It computes order/line/refund cents directly from fictional JSON, applying original-order cohort/status, identity scope, posted status and exclusive cutoff. It separately calculates percentages and channel contributions, using reviewed labels only for intended meaning/scope/period/state. Candidate SQL is never treated as gold.

It inspected 288 evaluation reports plus two demo reports, 222 read-only SQLite snapshots, 330 evaluation candidate cleanup receipts and 219 reference cleanup receipts. All 90 governed numeric reports (18 development, 72 held-out) matched exact raw cents/channels/percentages and verified evidence bindings; all 54 governed non-answers had null summaries and specified states. All 90 baseline numerical observations were independently checked, including each failure. It checked exact authorized order IDs/regions, absence of private tables, snapshot binding, all six original source fingerprints, grain/schema/claim rejections, no stale locks, complete ordered records and scorecard/JSONL consistency. All retained query cleanup receipts and command-launcher reaping flags were true. This additional worker audit is separate from main final acceptance.

### Resources, release and remaining limits

The seven commands consumed 94.435 measured wall seconds (1.574 active minutes), below the 15-minute execution budget. Sampled aggregate launcher/owned-process working set peaked at 98,680,832 bytes (94.109 MiB), below 512 MiB. Every command had a valid sample. Sampling used Windows process APIs, PID ancestry and creation-time attribution, at a nominal 25 ms delay plus overhead; monitor/PowerShell overhead is excluded and a sampled value is not a guaranteed instantaneous peak. The full-suite peak included three Python processes plus the py.exe launcher. SQL children were sequential and the one bounded loopback server was closed/joined by its test. The metadata/audit helpers ran separately and are outside this command-memory measurement.

Generated work content was 15,497,437 bytes (14.780 MiB) at artifact inspection, including historical attempts and scratch files; the final receipt records the slightly later total. It stayed below 200 MiB. No dependency downloads, live model calls, credential acquisition, remote/account action, deployment or publication occurred. No unrelated process was killed or modified. Earlier M1/M2 failures and invalid historical samplers remain preserved above; no new M3 command/audit failure occurred.

Only README/EVIDENCE and explanatory documentation changed after this first score. Frozen application/baseline/evaluator/fixture/prompt/gold/CI/pin files, all tests and FROZEN_M3.json stayed unchanged. Source-checkpoint and first-score artifacts remain preserved. Local integration is complete and resource-release-ready; main owns release and independent final acceptance. The pinned public-repository free CI remains authored/unexecuted; no Linux runtime/integration or live provider/model-quality evaluation ran. Physical demo identities are not production authentication, and a child-process boundary is not an OS sandbox.

Documentation recording: `py -3.11 work/m3_document_results.py` exited 0 and saved the results and all 36 case rows without importing or executing the application. A subsequent metadata helper, `py -3.11 work/m3_finalize.py`, exited 1 with `AssertionError: EVIDENCE.md`. Before that assertion, it verified the unchanged freeze/manifest, all seven first-pass command receipts and pre-command grants, and that only the six documentation files changed. Its personal-path scan also matched literal search terms in the historical scan commands printed in this evidence file; it therefore did not complete or write its receipt/status. The raw failure is preserved. This is a bookkeeping-check failure, separate from the passing seven commands and 4,491-assertion domain audit. In accordance with the stop-on-unexpected-failure instruction, the helper was neither corrected nor rerun, and no further application/test/evaluation command ran. The handoff records this open metadata issue for main's independent review instead of claiming a passing finalizer.



## Independent final local acceptance

On 8 October 2026 the main reviewer copied all 48 shipping files to a fresh directory without package installation and reran the seven documented M3 commands. All exited 0: 51 tests, 72 development and216 held-out comparison trials, plus both standalone demos. The fresh command wall times were 0.203,0.234,9.813,22.516,76.781,1.094 and0.203 seconds. These are main observations, separate from worker timings.

The main reviewer then ran a separate stdlib-only checker importing neither actor nor evaluator. All5,157 conditions passed against290 raw reports and223 read-only SQLite snapshots. It recomputed original-order revenue, discounts, posted-refund cutoff, exact scoped order IDs, channel deltas and percentages, checked evidence bindings and owned-child cleanup receipts, reconstructed comparator success/numeric denominators, and compared96 case/mode groups across three repeats. All48 copied shipping files stayed unchanged during execution.

Held-out scores reproduced: governed108/108 full tasks,72/72 numeric and108/108 safety; one-pass baseline24/108 full tasks,54/72 numeric and108/108 safety. Development reproduced36/36 governed and15/36 baseline full tasks. Baseline numeric failures and its structural lack of verified channel investigation remain in the reported denominators. These are authored offline results, not live model quality.

The earlier metadata-helper failure remains preserved. Main inspected its three matches: literal historical search patterns in this file, with no runtime dependency on a personal path. No application correction or retest was necessary. The ignored helper was not rerun. Main final acceptance is passed. Only the final status/evidence documentation changed afterward; static freeze and Git whitespace checks passed. Hosted CI, Linux integration, live inference, production authentication and real account operation remain unexecuted. Main did not sample peak RAM; worker sampling is separate evidence. No publication or deployment occurred.

## Public source release — 9 October 2026

All three local MVP milestones passed independent acceptance on 8 October 2026, including final documentation review. The review was executed separately from the implementation worker and included documented quickstarts, meaningful success/failure tests and direct domain-state checks. The results and limitations above remain unchanged.

This source release includes application code, authored fixtures, evaluator/tests, quickstart, architecture, license/attribution and the prepared CI workflow. Private orchestration records, machine-specific paths, runtime caches and generated local runs are excluded. Offline scripted/rule/replay outcomes and local provider doubles do not establish live model quality, employer adoption or production impact. Hosted CI results are available in this repository's Actions tab after publication; historical local reports retain their original execution dates.
