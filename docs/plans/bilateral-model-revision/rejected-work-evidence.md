# Round 7 — internal final rejection serialization

September 22, 2026. Parent spec: `spec-round7-rejected-work.md`.
Private experiment completed. Recommend the narrow shared final-freeze seam plus
generation-only compact rejections for **dark integration**, not activation.
The exact unchanged full-worker output arrives sooner and uses less observed
memory, but still fails latency relative to the incumbent and three-second target.

## Consumer audit and exact boundary

The candidate generation search retains `_core_cache` and `_decisions`.
Repository search found their consumers only in the bilateral modules:

| Consumer | Rejected result fields read |
|---|---|
| `trade_gen_bilateral._Search._core` (244) | Cache/return same object; no snapshot read |
| `trade_gen_bilateral_candidate._Search.evaluate` (142–189) | `.eligible`; `as_dict()` only after eligibility succeeds |
| Candidate companion-removal `_core` checks (160–169) | `.eligible`; rejected alternatives immediately continue |
| `trade_gen_bilateral._Search.candidates` (368–375) | `.eligible` and `.reason` decide whether companion exploration can help |
| Shared `_generate_with_search` (484–490) | `.eligible` and `.reason` counter; rejection immediately continues |
| Candidate final rank/report and shared emitted-card metadata | Eligible survivors only, retaining full immutable snapshots |
| External single/batch evaluators | Their own original `_Search`; full rejection evidence unchanged |

No rejected snapshot is the durable served-offer evidence ledger. Durable
impressions are constructed only from eligible, subsequently revalidated cards.
The same rejection outcomes still govern companion exploration and all original
rejection/report counters. No eligibility precheck replaces a policy calculation.

## One private prototype

Scratch root: `/private/tmp/bilateral-latency-20260922.eGQ8r0`.
`compact_rejections.py` SHA256
`5d1f2f21d6174223803965bd8a586631c6ceee33a82b7a5534059a6a6b906200`.
Version: `internal-final-rejection-status-1`.

The copied candidate generation entry point explicitly creates a private
`GenerationSearch(compact_final_rejections=True)`. It does not modify the normal
candidate/owner/incumbent classes or external evaluator functions. Unsupported
or disabled mode delegates to the original generator. There is no class-name
inference, persistent/global cache, lazy proof replay or change to the first30.

All owner evaluation calls, pricing, authority, intent, compensation checks,
cache keys, candidate iteration and report logic remain shared. The private
`_decision` implementation is a source-exact copy of incumbent bilateral final
correction/reason-precedence logic with **only its final freeze dispatch replaced**;
an exact-one marker check rejects source drift. This is acceptable evidence of an
opportunity, **not an acceptable long-term duplicate policy implementation**.

After every correction has executed, a final rejected decision becomes a frozen
internal status/reason object. Its discarded-field access (including `as_dict`,
snapshot, exact terms or matching API) increments a diagnostic and raises. It
cannot quietly reconstruct evidence later. Eligible/core results still receive
the complete original immutable evidence via the previously validated single-
freeze path. Thus this experiment includes single-freeze for eligible generation
proofs, but no detached JSON memo, package cache, early ordering or C proof-boundary
reuse. External evaluator rejects still include their byte-exact full snapshots.

## Current exact evidence

`round7-native-compact` binds source, private wrapper, HEAD `6c53caf9` and fixed
`PYTHONHASHSEED=0`. Full real constructor output exactly matches the fresh current
and retained round5 exports:

- All 3,836 cards/proof strings/order: SHA256
  `5070cbcd96ca0bd77c1d287a9fe3231771c1bbb1f63e0cea932d051209a063c5`.
- Complete generation report including all rejection counts, pools and budgets:
  `3baf157d373843562b29dd6fc0a9781e22d92da4ab471204d7c208be81fcdc3a`.
- Exactly 49,334 finalized internal rejections were compacted, and **zero
  discarded fields were requested**. The original 53,170 evaluated terms and
  3,836 emitted offers are preserved.
- Native generation 7.309 s and process peak RSS 522,272,768 bytes, versus the
  prior same-seed current native observation 10.088 s / 684,474,368 bytes. These
  are observational native/export process numbers, not a controlled actual-
  worker latency or production memory claim.

The wrapper `run_compact.py` binds its own/private implementation and reused
worker/native harness sources before/after each process plus HEAD. It does not
modify those harness files. Only scratch SQLite and blocked networking are used.
Eligible snapshot strings remain byte-exact; only nondeterministic card occurrence
IDs/timestamps and report elapsed are omitted from native equivalence, as before.

## Lifetime and proposed integration shape

Compaction reduces each *rejected* cache value, not the number of searches,
cache keys or outcomes. `_core_cache` and `_decisions` still share the same
final rejection object for an exact cached key. The compact object contains only
immutable reason/status and an audit-counter reference; the audit holds no
search/card/proof references. Rejection objects/caches remain search-local and
become unreachable with the generation search. Full eligible proofs can outlive
generation in cards and retain unchanged evidence. No new universal cache-byte
limit is claimed. Original computational budgets bound top-level enumeration,
not cache bytes: companion-removal core probes may add keys beyond the nominal
evaluated counter, especially for explicit larger packages. Player/config size
and Python/allocator overhead also affect memory. No eviction/cap was introduced.

The round6 observed 112.85 MB of retained decision snapshot bytes included both
eligible and rejected proofs; it is not valid to call that entire amount saved
here. Nor does local process RSS prove 2GB Render capacity or concurrent throughput.
External final revalidation, serialized/persisted evidence and downstream card
caches remain independent memory and CPU costs.

If actual-worker parity and benefit hold, the narrow runtime seam should be a
**single shared final-freeze hook** in the existing owner/bilateral/candidate
inheritance flow, with explicit generation-only rejection mode. Candidate version/
construction enrichment happens before that one freeze. Keep all policy checks
and final reason precedence in their existing shared implementation, default
external/off behavior full, eligible evidence unchanged, and compact results
unavailable to serving APIs. Do not maintain the private copied policy branches.

This targets generation's rejected proof serialization. Prior detached-proof
memoization targets repeated reads of full proof JSON but retained additional
binary payload and had a memory trade-off. C's boundary work targets duplicate
final owner evaluation and requires complete live authority/dependency binding.
They are different work regions with potential overlap; savings cannot be added
arithmetically. No combined optimization has been run or authorized here.

B's independent read-only review found no model-semantic defect in the bounded
single-worker experiment. B confirmed the rejected consumer/alias/companion
audit and unchanged external evaluators. The prototype's `LAST_AUDIT` dictionary
is shared global **instrumentation**, not a production concurrent-request-safe
audit: a future shared implementation must keep its audit state request-local.
Concurrent-request correctness is not inferred from these single-process runs.

## Final actual-worker result

The sequential exclusive-CPU group is `round7-worker-current`,
`round7-worker-compact`, `round7-worker-off`. Each uses `PYTHONHASHSEED=0`,
HEAD `6c53caf9`, final server source
`3fa92ee850dfc8eb01a69ab7d052a85f8cda5facc158ac84d730ad27d2ed19c6`
and age helper
`d294a4d049c00c4191d7e5964197452ff7c4fad3140572ff23cd98a8d0c27065`.
The common adapter binds those and ranking/roster/tier/flag dependencies plus
private implementation/harness bytes before and after each process. All guards
pass. Parent and C held heavy tests during this group; all processes/guards are
now released.

| Actual worker | Current candidate | Compact-generation candidate | Incumbent off |
|---|---:|---:|---:|
| First durable 30 | 18.388 s | 15.416 s | 8.453 s |
| Complete worker | 23.426 s | 20.421 s | 11.277 s |
| Native construction stage | 10.208 s | 7.222 s | 5.370 s |
| Final owner revalidation | 5.106 s | 5.072 s | 2.119 s |
| Durable evidence/publication stage | 5.088 s | 5.050 s | 2.856 s |
| Final served/durable inventory | 3,306 | 3,306 | 2,354 |
| Process peak RSS, bytes | 956,022,784 | 824,950,784 | 633,454,592 |

The paired candidate improvement is 16.16% first-durable and 12.83% completion.
The measured change is concentrated in construction; final revalidation and
durable evidence work remain. Peak RSS falls 13.7% in this pair, but absolute
RSS varies materially from previous native/worker observations, including C's
independent measurements. This is not a reliable per-instance capacity estimate.
The compact candidate remains approximately 82% slower than off at first durable
publication and nowhere near the three-second target. No combined savings are
inferred from C's separate boundary result.

`round7-persisted-parity.json` requires both type-sensitive canonical hashes and
full Python value equality. Public ordered rows match at
`414f3bfddaddb0dccea5de413995ef0ae225506cb2ee9d29635c40e40c8d9fe8`;
complete persisted rows (expanded private diagnostic snapshot references) match
at `baa60140cd0a3a0a25a55cdb7023cde4e2d88c4582c31807eb121e95f79dcafa`.
All 34 cumulative publications retain exact within-run impression identity and
immutable public-card prefixes; the first30 and complete normalized order are
unchanged. Committed impressions precede every observed first publication.
All persistence input fields also match their re-read stored values, and every
served proof remains full, eligible, correctly versioned and exact-card bound.

`round7-off-persisted-parity.json` compares the off prototype against C's pristine
same-source `inc-current-final2`. All 2,354 public and complete persisted rows
match exactly, preserving hashes `3ff38c9e…` and `1b9ec1e4…` from prior rounds.
The candidate generation hook is never invoked on this path. The comparison
excludes only occurrence IDs/times, captured-at/roster observed-at and constructor
elapsed, with every excluded field explicitly listed; valuation JSON strings
are never normalized away. No rows, private fields or output cap are removed.

Final tests: **31 private contracts pass**, including the baseline rejected-JSON
trap and compact GREEN control, invalid/neutral/Unknown inputs, partial/exact
selection, expired/untouchable/tanking/disposition precedence, pair/global budgets,
external single/batch rejection bytes, cache aliases, immutable compact status,
new-consumer fail-loud instrumentation and unsupported/off mode fallback. Another
**221 existing constructor/presentment tests pass with the prototype installed**.
B independently reviewed the consumer and final-freeze boundary; no semantic
defect found. Actual failure/cancellation controls remain in the unchanged
publication path; this private round did not introduce a new serving shortcut.

The measured opportunity favors this small generation-only seam before the prior
binary detached-proof memo (extra retained payload) or C's broader final-proof
authority machinery. Shared integration must retain one policy implementation,
the later legitimate term-efficiency proof freeze, full external rejection
diagnostics and off defaults. Parent approval, independent shared-code review,
exact integrated-worker parity and full tests are still required. No deployment
or flag change is authorized by this private result alone.

## Shared dark integration — verified

Parent explicitly authorized the narrow integration under
`spec-round7-integration.md` after the private result. The shared implementation
adds owner `_freeze_decision`, leaving the existing `_decision` final status and
the entire bilateral correction/reason method unchanged. Candidate version and
construction metadata are applied before that single core freeze. Its private
`_GenerationSearch` alone substitutes a frozen reason/status for finalized
rejections; external single/batch evaluators still produce full diagnostic JSON.
The later eligible term-efficiency freeze remains. There is no copied policy
branch, model flag, cache, binary payload, replay or runtime audit/global state.

Source-bound integration hashes:

- Owner `cf76e4e79da318165812d94ff16a047ec3be7c2980b02b25fd5b5662ee4f39ad`.
- Candidate `18d524ce1aab2d50118e976604e4c6ad123acc8da2bfbb44f231b49d17ab7b69`.
- Bilateral unchanged `978b09445652bf2f65c2bdb3e8f2f507788b08ea50fc5808cf95ad7d96ccde32`.
- Policy3 unchanged `fe79474c3864fb78372396a134fc7c9a5f9cd5e5fc34e98c803c569d36aed887`.

Named RED tests failed before implementation for two core freezes and internal
rejected JSON serialization; both now pass. New focused tests total **32 passed**.
They bind complete external eligible/rejected diagnostic strings; 12 synthetic
contexts also bind the full dynamic generated proofs/groups, complete reports,
and off outputs to immutable checkpoint `6c53caf9` source-loader references.
The original declared-dataclass card golden omitted dynamically attached proof
fields; B caught this and a separate `vars(card)` full-proof reference corrected
the coverage before acceptance. No current-candidate-generated golden is used.
Malformed caller provenance at the supported preferences seam still raises for
nonfinite/non-JSON data. The all-rejected control explicitly confirms zero
survivors with valid provenance first; final report serialization then preserves
fail-closed behavior when rejected internal JSON is skipped. Earlier exploratory
malformed references with the wrong top-level kwarg or a compensated survivor
are retained privately but are not cited as this control.

B independently reviewed the final runtime and references without outstanding
findings, ran **406 combined tests**, then independently reran the final **32**
after the zero-survivor fixture correction. The earlier author group had **330**
passing constructor/presentation/route/publication tests. Existing publication
tests include evidence-write failures, model/input revocation, timeout and
supersession after the first committed batch, plus selected-route rollback.
Parent's fresh full-suite result remains separate from this focused evidence.

Five fresh fixed-seed guarded processes used the shared implementation only:
`round7-integrated-worker`, `round7-integrated-off-worker`,
`round7-integrated-native`, `round7-integrated-off-native`, and
`round7-integrated-failed-write`. `run_integrated.py` adds source/HEAD checks to
the unchanged native/actual-worker harnesses; it installs no private model hook.
All guards include final server `3fa92ee8…`, age helper `d294a4d0…`, ranking,
roster, tiers, flags, persistence and publication sources. All remain stable at
HEAD `6c53caf9`. No subprocess or source/CPU guard remains active.

| Integrated actual worker | Candidate | Incumbent off |
|---|---:|---:|
| First durable 30 | 14.538 s | 8.576 s |
| Complete worker | 19.702 s | 11.389 s |
| Process CPU | 19.437 s | 11.321 s |
| Native construction | 7.071 s | 5.408 s |
| Final served/persisted inventory | 3,306 | 2,354 |
| Process peak RSS, bytes | 634,945,536 | 583,385,088 |

Candidate final revalidation is 4.333 s and evidence/publication 5.210 s.
Unlike the generation-only private prototype, the shared single-freeze seam also
removes the duplicate core JSON serialization in external candidate revalidation;
it does **not** reuse original proofs or skip revalidation. Timing observations
are local offline, single-request and single sequential runs, not production
percentiles. RSS differs materially across runs and is not a Render capacity or
parallel-throughput estimate. Native integrated process RSS is 526,630,912 bytes
(candidate) and 426,000,384 bytes (off); those processes include full export work.
Compact rejection values retain only a frozen reason/status for the request's
existing cache lifetime. No new process-wide payload or hard memory bound exists.

All candidate 3,836 native card/proof strings and report retain the exact hashes
above; all 2,843 incumbent native cards/report also retain their frozen hashes
`d2d450f8…` / `2c7c4ab6…`. Strict hash **and** value comparisons of complete
persisted rows and public order pass against both the preintegration baseline
and private compact prototype (`round7-integrated-parity.json` and
`round7-integrated-vs-private-parity.json`), preserving candidate hashes
`414f3bfd…` / `baa60140…`. Off parity preserves `3ff38c9e…` / `1b9ec1e4…` in
`round7-integrated-off-parity.json`. The same explicit volatile-only whitelist
above applies; no proof JSON normalization is introduced. All 34 candidate and
25 incumbent cumulative public snapshots retain immutable within-run prefixes,
exact final inventory and committed-first-publication evidence. The actual
failed-write run reaches the complete validated 3,306-offer inventory but
publishes **zero** cards, stores **zero** impressions and never becomes actionable.

The integration is accepted as a narrowly reviewed **dark** performance change,
not release evidence: first durable publication remains about **69.5% slower**
than the incumbent and fails the three-second target. No weights, model version,
order, eligible inventory, computational budget, source/provenance meaning or
grading input changed. No deployment, activation or infrastructure change occurred.
