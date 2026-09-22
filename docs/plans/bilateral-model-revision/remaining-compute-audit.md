# Remaining exact-compute audit

September 22, 2026. Agent C; parent scope: `spec-remaining-compute-audit.md`.
Read-only source/artifact review. No prototype, benchmark, provider/database call,
scorer change or runtime edit was performed for this audit.

## Decision

Two bounded opportunities warrant **measurement if the parent authorizes it**:
presentation-local term-record preparation and search-local reuse of an identical
lineup assignment. Neither has a demonstrated post-integration speedup.
There is no evidence here that either closes the first-action latency gap, and
neither changes the existing release hold. Do not automatically combine them
with each other, proof-boundary reuse, detached-proof memoization or early order.

The first opportunity is duplicate work visible directly in the current code;
the second has a historically substantial compute region but an **unmeasured
exact-key hit rate**. A negative bounded result is a sufficient stopping point.

## What the measurements do and do not establish

The trusted, locally generated `candidate-profile/private-profile.pstats` under
the existing private latency-artifact directory was read without importing app
code. This is the earlier policy-2, pre-final-freeze/pre-compact-rejection profile,
not a fresh profile of the integration now in progress. Its profiled worker took
34.674 seconds; observer/export work and previously reported contention are
included. Cumulative times below overlap callers and are **not additive savings**.

| Historical function | Calls | Cumulative seconds |
|---|---:|---:|
| Owner proof `as_dict` | 169,466 | 9.085 |
| Candidate `term_precedence` | 2 | 1.634 |
| Presentation `_evidence` | 3,306 | 0.608 |
| Owner `_lineup` | 22,862 | 2.744 |
| Roster `assign`, nested within `_lineup` here | 22,862 | 2.136 |
| Ranking `tier_bands_for` | 18,787 | 0.045 |

The later, already-completed private round-7 compact-generation worker is a more
recent **stage observation**, not a new function profile: construction 7.222 s,
final owner revalidation 5.072 s, dispositions/policy-3 presentation and harness
assertions 1.800 s, durable evidence/publication 5.050 s; first durable 30 at
15.416 s and full completion at 20.421 s. It retained all 3,306 final cards.
The 1.800 s stage is not pure presentation cost, and the publication stage is not
all redundant work. These figures come from `round7-worker-compact/summary.json`;
they are reconstructed local-worker timings, not a production service-level test.

That private generation-only experiment left external final evaluation's old
core freeze path intact. The current shared integration also removes that
redundancy from normal candidate evaluation, so **5.072 s is not an estimate of
what will remain after integration**. The old 57,450 candidate `_decision` calls,
their 6.016 s cumulative time, and discarded rejected JSON must not be counted
again as opportunities. The later `evaluate` freeze that adds term-efficiency
evidence remains required. Both proposed regions below are outside that change.

Source review observed the new owner `_freeze_decision` hook and explicit
candidate `_GenerationSearch`; it did not assume their integration tests or
measurements had finished. Observed file fingerprints:

- `trade_gen_owner.py`: `cf76e4e79da318165812d94ff16a047ec3be7c2980b02b25fd5b5662ee4f39ad`
- `trade_gen_bilateral.py`: `978b09445652bf2f65c2bdb3e8f2f507788b08ea50fc5808cf95ad7d96ccde32`
- `trade_gen_bilateral_candidate.py`: `18d524ce1aab2d50118e976604e4c6ad123acc8da2bfbb44f231b49d17ab7b69`
- `trade_bilateral_presentment.py`: `fe79474c3864fb78372396a134fc7c9a5f9cd5e5fc34e98c803c569d36aed887`
- `trade_roster.py`: `ba20313ba741a5a6bced1b9300e0106334f3128dbf4914f9d947150adc54a6f1`

These identify the inspected source, not a guarded performance run.

## 1. Prepare a minimal term record once inside presentation

### Duplicate and required consumers

`trade_bilateral_presentment.present` calls `_evidence` for each occurrence.
For a normal compatible proof, `_evidence` calls `proof.matches(card)`, which
decodes the proof, and then `proof.as_dict()`, which decodes it again. It validates
term evidence while computing support, novelty and all four co-headliner profiles.
Then `_term_precedence` passes those same eligible occurrences to candidate
`term_precedence`, which again calls `matches`, again decodes the full proof, and
again validates term evidence. Thus an ordinary qualifying occurrence takes four
full proof decodes across these two passes. There is no presentation-local
decoded-view or term-record cache. The common immutable proof still implements
detached `as_dict` correctly; no persistent memo is assumed.

The precedence builder retains each entire decoded proof in `records` for its
family comparisons even though, after validation, it consumes only exact
participants/terms, worst adjusted market loss, avoidable-companion IDs, and each
side's consideration profile. It does not need all assets, roster snapshots,
support diagnostics or selection trees to perform those comparisons. This is
avoidable private materialization as well as repeated parsing.

Native `_rank` also invokes `term_precedence`, but **its edges cannot simply be
reused after filtering**. Family representatives are the first 32 lower-cost
members of the supplied inventory. Removing a representative can expose a later
one. Survivor families and edges must be rebuilt with the same sorting and
comparison logic; filtering old edges is not equivalent.

### Minimal seam and full dependencies

Factor the existing precedence algorithm into a record builder plus a pure
record-consuming comparator. The public/internal existing `term_precedence(cards)`
entry point still validates arbitrary supplied cards and uses that same builder.
Presentation can build the identical minimal record while its already-decoded
proof is in scope, then discard the full tree. Its later precedence pass consumes
these records with occurrence indices unchanged. Do not retain one full decoded
proof per card to implement this optimization.

Record construction depends on the exact proof's league/viewer/partner and ordered
give/receive binding; finite card prices and ratio under the existing matching
tolerance; generator/schema/eligibility/reason and term-order version; explicit
selection state; worst market loss; avoidable IDs; both manager IDs and strict
known-personal booleans; raw outgoing/incoming personal values; plan means;
outgoing/incoming positions and availability shapes. Presentation additionally
requires unchanged protected/source fields, basis/lane, support, focal identity,
personal provenance, all exact market-max ties and Unknown counts. Family building
depends on the surviving occurrence order, exact participant/side sets, cost
ordering, existing EPS and 32-member comparison bound. No live flag, board,
provider or pricing lookup is needed at this stage.

The seam must preserve malformed/foreign/subclass handling, not merely common
happy-path records. Existing code accepts proof subclasses; an exact built-in
type fast path with the original path for unfamiliar types is safer than assuming
overridden `matches`/`as_dict` are equivalent. Reuse is valid only while the same
proof/header/snapshot and card binding remain intact within this synchronous
owned-card presentation call. A replacement or mutation must fall back to original
validation, not bless stale metadata. This is not authority to reuse a constructor
decision in final evaluation or to skip any final serving check.

### Falsification and bounded criterion

Before any timing claim, compare the old and proposed implementations on the
**same complete retained inventories and post-filter subsets**: exact occurrence
order, edges, diagnostics, unchanged public fields and byte-exact proof strings.
Include removal of one of the first 32 family representatives; repeated identical
card occurrences; both directions of term precedence; explicit search; protected
and mixed-source slots; missing/malformed/foreign proofs; subclass behavior;
known/Unknown transitions; equal-market co-headliners; and proof/card replacement
between extraction and consumption. A deliberately omitted validation or reused
native edge set must make a named test fail.

Instrument decode/record counts without changing ordering. Proceed to one fixed
source/seed paired worker only if qualifying built-in occurrences demonstrably
avoid the second full-data materialization and full proof trees do not remain in
the record collection. Require exact native/public/persisted/prefix parity and
report both total timing and peak RSS; no timing win may trade away validation.
If bookkeeping erases the benefit or increases retained memory materially, stop.
No percentage win or fixed seconds saved is established by the old profile.

Lifetime is one call to `present`/`term_precedence`. Records must not escape to
public cards, logs or global caches: personal costs and plan profiles remain
private evidence. Store only the fields consumed after validation, with detached
or immutable small containers so a mutation cannot leak to another occurrence.

## 2. Candidate-only memo of the exact assignment, not lineup sums

### Duplicate and existing cache boundaries

Owner `_lineup` builds a usable list, calls Hungarian `trade_roster.assign`, then
reduces assigned values plus a single 15%-weighted backup by position. Consumers
are `_team`'s initial `lineup_before`, bilateral `_asset_interest`'s one-asset
counterfactuals, and owner `_owner`'s post-exchange roster proxy.

`team['asset_interest']` already caches `(asset, direction)`; `_side_cache` caches
`(manager, sorted give IDs, sorted receive IDs)`; `_core_cache` and `_decisions`
cache exact terms. These prevent many repeated evaluations. They do not identify
distinct packages with the same usable lineup: changing pick companions or
unavailable/inactive assets can change full terms without changing the list of
usable player assets supplied to this calculation. Such packages still require
all separate market, preference, plan, term-efficiency and eligibility work.
Only their identical assignment subcalculation is a reuse candidate. The parent
identified the narrower seam below during this audit; it is preferable to caching
the entire `_lineup` result.

The historical 22,862 calls establish cost, **not 22,862 duplicates**. No exact-key
trace or cache-hit fraction was collected for this audit. A low-hit result rejects
this optimization. The historically attributable region is `assign`'s 2.136 s,
not the full 2.744 s `_lineup` region, and neither is a current savings forecast.

### Minimal seam and full dependencies

Add one private owner-Search assignment hook whose default calls the unchanged
`trade_roster.assign`. The candidate alone overrides that hook with a bounded,
Search-local memo; initialize it before parent initialization because `_team`
calls `_lineup` during that phase. On a miss call the original solver, not a copied
Hungarian/utility algorithm. Cache the assignment as an immutable tuple of IDs or
None and return a fresh list. **Leave `_lineup`'s existing usable-list iteration,
set membership, positional additions and bench maxima untouched.** A cache-entry
cap/eviction affects only recomputation, never pools, budgets, considered offers
or returned inventory. Parent should freeze the memory bound before measurement.

`assign` first sorts assets by ID. Its full result depends on that sorted sequence
(including multiplicity), each Asset's ID, positions and exact numeric value,
the ordered slots including duplicates, and process-static `ELIGIBILITY`/solver
code. It computes the occupancy bonus and cost matrix in sorted-asset order, then
executes the same tie-breaking comparisons. No other Asset fields are read in
this solver. A key can therefore use the **same sorted sequence of immutable
Asset descriptors plus the exact ordered slots**, preserving numeric type/value
and signed-zero distinctions rather than relying on Python numeric alias equality.
Do not reduce the key to a set that loses multiplicity. A captured-substrate ID
shortcut would require proving that immutable binding separately; the full
descriptor form avoids assuming it. Unknown/custom inputs must use the original
solver if exact key construction cannot be justified.

This makes assignment reusable even when incoming roster iteration order differs,
because only the solver's own already-sorted computation is reused. Caching a
whole lineup under a sorted/frozenset key would instead be unsafe: `_lineup`
subsequently sums floats in original usable-list order, and existing cross-process
hash-order differences have already demonstrated that numeric order matters.
Fixed `PYTHONHASHSEED=0` helps reproducibility, not the correctness of that shortcut.

The substrate was built from captured market values, pick/position classification,
injury availability and `age_now_mult`; each Asset is frozen. Team inactive IDs are
filtered before calling the hook. Exact changed values/positions change its key;
the assignment does not itself read age, outlook, boards, crown or config. The
uncached remainder still consumes `_positions`, the original usable order and
the .15 backup rule on every call. Loaded solver and eligibility tables are
process-static under the existing no-hotpatch contract. No reuse crosses Search
instances or generation/final-evaluation lifetimes; no global solver cache or
thread-local inter-request cache is introduced.

### Falsification and bounded criterion

Use the unchanged `assign` and base `_lineup` as independent oracles. Compare exact
assignment IDs, float representations and resulting proof strings, not approximate
utility equality. Tests must cover equal usable lists reached through different
pick terms, inactive/unavailable companions, distinct slots/FLEX assignments, slot
permutations, the same set with different usable orders, duplicate multiplicity,
empty lineups, tie-valued players, changed Asset values/positions, numeric aliases,
and mutations of a previously returned assignment list. Two usable orders should
hit the assignment cache yet retain their distinct original floating sums where
applicable. Eviction and disabled cache must reproduce identical results and no
request may see another's records. Sabotages that cache the whole lineup under a
sorted key, omit values/positions from an unbound key, or return a mutable shared
assignment must fail named tests.

The first authorized probe should record total calls, exact hits, original
assignment calls avoided and peak entries/retained key bytes on a fixed
development capture. If hits are negligible, stop before an expanded experiment.
If meaningful, one isolated same-source worker pair must preserve every native
proof/report, final public/persisted row and cumulative prefix, then report net
wall/CPU/RSS after sorting/key-building, return-copy and still-required lineup-sum
work. The memory bound is entry count times sorted Asset-descriptor/slot keys plus
assignment-ID tuples and container overhead; measure it. No full Player, board
or proof trees belong in this cache. It is private, dies with Search, and grants
no final authority.

## Stop boundaries

Tier-band preparation is visibly repeated, but the historical 0.045 s cumulative
cost does not justify a third optimization experiment. Full two-sided pricing,
term-removal comparisons, roster/significance/disposition gates and each durable
offer's independent evidence are not redundant merely because they are expensive.
The private proof-boundary proposal remains separate and unintegrated, including
its memory/provenance limitations. This audit neither changes the evaluator nor
uses acceptance outcomes or quality metrics to excuse incomplete inventories.

Recommended parent decision: finish and measure the already-authorized narrow
integration first. Then, only if further work is worthwhile, authorize **one** of
these exact seams with the above falsification and stopping criteria. Current
post-integration dominance and production memory/latency capacity remain unknown.
