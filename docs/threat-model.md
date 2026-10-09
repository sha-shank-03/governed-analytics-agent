# Threat model, tradeoffs and original contribution

This is a local, fictional business workflow with a trusted OS owner and trusted fixture builder. The acting provider may propose incorrect SQL, invalid tool fields, stale metadata, fabricated evidence references or unsupported report claims. It may misinterpret business wording. Those are inside the tested boundary. Host code, raw source files, local identity selection, dependency/runtime installation and evaluation harness are trusted.

## Assets and enforcement

Private customer columns and rows outside the selected identity grant are removed before a query child opens its database. Read-only SQLite mode, query_only, a deny-by-default operation/column/function authorizer, fresh connections and reduced limits then constrain statements. An omitted WHERE region predicate cannot recover removed rows. The authorizer is not row security; physical projection supplies that boundary.

The provider can select an allowed tool and propose SQL but cannot select database paths, identity, parameters, shell commands, HTTP routes or writes. Host-bound metric, scope, period, currency and cutoff form the accepted contract. SQL proposals must match independent runtime reference rows before entering the evidence registry. The final report uses only registered IDs and derives figures itself. Unknown schema and incomplete coverage stop early; a covered zero remains zero.

Unrecognized report fields are rejected and excluded from final facts. One corrective submission is allowed; repeated invalid output stops under the turn limit or validation failure. A fabricated evidence-ID submission remains terminal. Diagnostic traces retain rejection field names and legitimate earlier receipts; a failed final report has null summary and no numeric conclusion. Keeping prior verified receipts is not accepting the final invalid claim.

Query workers have heap/input/result/VM limits and an owned-child parent timeout. Cancellation and KeyboardInterrupt cleanup kill/wait only the spawned child. A fresh reference execution has the same controls. Loopback provider tests validate protocol; external HTTPS is opt-in with an explicit credential. No redirects, proxy inheritance, environment-key discovery or automatic retry after uncertain transport failure occurs.

## Outside the claim

This is not production authentication, a general SQL semantic proof, a malicious-code OS sandbox, or protection against hostile native libraries, hostile database files, a compromised runtime, a local administrator or an OS owner editing code/files. Simulated identity selection is trusted. Python provider implementations execute in a trusted process and can access the filesystem if maliciously rewritten. Evaluation labels are withheld from tool inputs, not encrypted or hidden from that OS process.

File hashes establish reproducibility against a trusted manifest; they are not signed authenticity. Local exclusive locks reject concurrent runs but do not supply distributed locking or automatic stale-lock recovery. A crash before checkpointing can repeat a read; exactly-once execution is not claimed. An interrupted terminal report can be regenerated from the checkpoint. Whole-run timing is cooperative application enforcement; arbitrary Python provider code is not forcibly preempted.

Instruction-like text in the held-out fixture remains an authorized fulfillment-event value. The normal actor sees scoped schema and aggregate observations, so that field grants no tools and is not read as an instruction. This tests the chosen data-exposure boundary, not an LLM's prompt-injection resistance.

## Why this architecture

Python 3.11 and SQLite keep the standalone workflow inspectable and require no package/server/download. Java would add a service boundary without a useful responsibility for this bounded catalog. Four measures and total/channel groupings make exact arithmetic/reference checks possible. A canonical query handles this catalog only; a dictionary arithmetic evaluator separately checks raw facts and final outcomes.

The constrained report sacrifices arbitrary narrative and causal explanations for accountable facts. Channel deltas are descriptive arithmetic contributions. The one-pass baseline shares access/resource gates but cannot clarify, repair or investigate channels. Full-workflow scores therefore have a structural difference; numerical correctness is reported separately and there is no uplift gate.

## Contribution and limits of the evidence

The contribution is an authored business-semantics and join-grain testbed, with an actual decision/tool loop, independently enforced authority, inspectable recovery, and outcome scoring. Permission-aware natural-language SQL already exists in tools such as [Databricks Genie](https://docs.databricks.com/aws/en/genie-agents/concepts) and [Vanna](https://github.com/vanna-ai/vanna). No new general agent framework, SQL-security algorithm or employer endorsement is claimed.

M1/M2 were independently accepted on Windows. M3 local integration passed 51 tests and the frozen 36-case comparison in both modes across three repetitions. Governed matched all 24 numeric completions and 12 non-answer outcomes per repeat; all safety checks passed in both modes. Main independently accepted the final local MVP with fresh-source execution and 5,157 raw-data/database conditions. Hosted CI remains unexecuted. All decisions are scripted or authored perturbations. These scores show the specified controls on authored data, not learned model quality, employment experience, enterprise deployment or statistical generalization.
