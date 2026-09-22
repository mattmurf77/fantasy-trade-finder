# Private assignment-only reuse — negative result

September 22, 2026. Agent C; parent specification:
`spec-assignment-reuse-probe.md`. **Do not integrate this prototype.** It preserved
the checked outputs and avoided solver calls, but made the paired worker slower.
The experiment is stopped; no cache tuning, additional prototype or shared
runtime/grader change was made. Existing release holds remain unchanged.

## Scope and implementation

Private directory: `/private/tmp/bilateral-assignment-reuse-20260922.24WsLp`.
Version: `private-assignment-reuse-1`.

- `assignment_reuse.py`: `841c95aced3fca67df0e12b2790b90b56485a32050f397770fcca2b7d9d2568b`
- `run_assignment.py`: `e0dda538ffab0ec301c963215710b650707b4b60cd4e1d21ace15b6ebe4e9645`
- Final `test_assignment_reuse.py`: `03721bf60f8a94d3f4487fac9b02f385e53baf6e86b826bf6ce51a03af776576`

The prototype substitutes exactly one solver call in the original owner `_lineup`
AST and installs that function on the candidate Search class only. It does not
copy/change the solver or the outer usable-list iteration, positional floating
additions, bench maxima or 15% backup calculation. Incumbent/owner classes are
unchanged. Existing integrated round-7 final-freeze and compact-rejection behavior
is the baseline, not an additional private optimization. There is no binary proof
memo, proof-boundary reuse, altered search budget, card cap or ordering change.

The fixed limit is 512 LRU entries per Search. Initialization is lazy at the first
solver call, including calls during parent `_team` initialization. Eviction changes
only which exact assignments are recomputed. A miss calls the unchanged solver;
errors are propagated and never cached. Every normal call returns a fresh list
from an immutable cached assignment tuple.

## Exact dependencies and review repairs

Keys own the ordered slot tuple and the Asset descriptors in the solver's stable
ID-sort order, preserving duplicate-ID relative order and multiplicity. Consumed
Asset fields are exact string ID, frozenset-of-string positions and typed numeric
value; float values use `hex()` so int/float/bool aliases and signed zero do not
collide. Custom/unsupported input types use the original solver path without
pre-consuming unfamiliar iterators. Unused Asset metadata is not a solver input.

Agent B found a key/consumption race before testing: a caller could mutate its
list after key creation but before the original solver read it. The repair copies
plain slot/asset selections to tuples once; both key creation and the miss solver
consume those same tuples. A deterministic mutation-after-key regression passes.
Exact built-in frozen Assets, frozenset positions and scalar values supply the
supported immutable-element contract; this does not promise safety against an
arbitrary concurrent `object.__setattr__` attack on frozen objects.

The unchanged solver/eligibility tables are process-static code dependencies, not
live provider/config state. The private memo also detects a different solver/code
or typed eligibility-table contents between calls and passes through rather than
borrowing a stale entry. Tests exercise those changes. No atomic hotpatch/reload
framework is claimed. Current `_lineup` makes no new crown/board/config read;
changed captured Asset values/positions or ordered slots produce different keys.
No entry is reused across Search instances or generation/final-evaluation scopes.

## Verification and oracle correction

The initial 42 tests passed in 0.27 s. B and the parent then identified a synthetic
oracle coverage gap: `asdict(TradeCard)` omitted dynamically attached proof/group
attributes. That initial synthetic helper therefore did **not** establish full
private native-proof parity. It was replaced with `vars(card)` plus dataclass
serialization, and a named sabotage now detects changed proof snapshot strings
and group attributes. The corrected **43 tests passed in 0.29 s** after timings.
The runtime prototype did not change and no expensive run was repeated. Actual
native export had used `vars(card)` all along and independently retained proofs.

Agent B independently reran the repaired suite: **43 passed in 0.32 s**, and
reviewed the source-bound paired artifacts. B found no remaining defect under the
declared frozen-Asset/process-static dependency contract and also recommended no
integration because of the measured slowdown.

Contracts cover actual original-solver call counts, stable duplicate-ID sorting,
overlapping FLEX/Superflex, ties, partial/empty assignment, picks/inactive/injured
assets, slots/values/positions/types, malformed-input exception parity, untouched
iterators, returned-list mutation, key/selection isolation, 512-entry eviction,
two managers/two Search instances and released memo lifetime. An order-sensitive
`1e16 + 1 + 1` example proves permuted inputs can reuse an assignment while the
original distinct floating sums remain intact. A whole-lineup sorted-key sabotage
fails that check. Corrected synthetic native/report/external rejection/default-off
comparisons preserve full dynamic evidence, not only dataclass card fields.

## Source-bound native and full-worker parity

All measured processes used fixed `PYTHONHASHSEED=0`, fresh offline process/scratch
SQLite isolation and blocked networking through the existing worker/native
harnesses. The CPU window was exclusive; the parent full suite began only after
explicit release. HEAD stayed `6c53caf987fc814ac78656f96dad84f6fe5e4997`.
Every wrapper/harness source and HEAD guard passed before/after each run. The
manifest covers the final age helper and server as well as model, policy, roster,
ranking, tier, flag and trade-service dependencies. Principal shared hashes:

- Owner: `cf76e4e79da318165812d94ff16a047ec3be7c2980b02b25fd5b5662ee4f39ad`
- Candidate: `18d524ce1aab2d50118e976604e4c6ad123acc8da2bfbb44f231b49d17ab7b69`
- Policy 3: `fe79474c3864fb78372396a134fc7c9a5f9cd5e5fc34e98c803c569d36aed887`
- Server: `3fa92ee850dfc8eb01a69ab7d052a85f8cda5facc158ac84d730ad27d2ed19c6`
- Input helper: `d294a4d049c00c4191d7e5964197452ff7c4fad3140572ff23cd98a8d0c27065`

The single retained development input/config matches the integrated round-7
worker. This is not a rerun of the full diagnostic panel or an independent blind
quality test. No grader or quality threshold changed.

`native-probe` matches the fresh `round7-integrated-native` byte-for-byte:

- All 3,836 native occurrences including exact immutable proof strings:
  `5070cbcd96ca0bd77c1d287a9fe3231771c1bbb1f63e0cea932d051209a063c5`.
- Complete report, preserving pools/budgets/rejection counts:
  `3baf157d373843562b29dd6fc0a9781e22d92da4ab471204d7c208be81fcdc3a`.

Only native occurrence `trade_id`, `created_at`, `expires_at` and report
`elapsed_seconds` were excluded, as in the existing harness. Native proof JSON
strings were neither decoded/reformatted nor stripped by this comparison.

Fresh `worker-baseline` versus `worker-probe` passes strict canonical SHA **and**
value equality for all 3,306 final public occurrences and all persisted row
columns with diagnostic references expanded. Public SHA:
`414f3bfddaddb0dccea5de413995ef0ae225506cb2ee9d29635c40e40c8d9fe8`;
persisted SHA: `baa60140cd0a3a0a25a55cdb7023cde4e2d88c4582c31807eb121e95f79dcafa`.
All 34 cumulative publication boundaries retain prior byte-content fingerprints,
and the first 30 are read back as durable. Captured persistence inputs match all
corresponding reread database fields; final indices/order/proof versions match.

`worker-off` likewise exactly matches the fresh integrated off worker for all
2,354 public/persisted occurrences and 25 cumulative boundaries. Public SHA:
`3ff38c9ea4ec30730f5f6785c66d1915cc266716bfe39c2531eaf560d0358cc2`;
persisted SHA: `1b9ec1e4563ac05fc4ccc1405d17ab357cd2586ce285eab2a7b0f1d44cfa2a6c`.
Installing the candidate-only hook while off creates zero memos. A separate full
off-native export and new failed-write worker were not run after the negative
result; no broader failure-path claim is inferred.

Worker comparisons exclude only public `trade_id`, `impression_id`, `expires_at`;
row `impression_id`, `candidate_set_id`, `served_at`; and private-feature
`owner_request.captured_at`, `roster_evaluation.observed_at`,
`owner_generation.elapsed_seconds`. Private valuation JSON is retained. These
are the unchanged existing comparison rules, not exclusions selected from a diff.

## Negative performance and lifetime result

| Same-source actual worker | Integrated baseline | Assignment prototype |
|---|---:|---:|
| First durable 30 | 14.593 s | 16.087 s |
| Full worker | 19.830 s | 21.284 s |
| Worker CPU | 19.522 s | 21.132 s |
| Construction | 7.171 s | 8.111 s |
| Final owner revalidation | 4.333 s | 4.875 s |
| Durable evidence/publication | 5.293 s | 5.269 s |
| Process peak RSS, bytes | 667,009,024 | 684,507,136 |
| Final served/durable inventory | 3,306 | 3,306 |

First durable 30 worsened approximately 10.24%; full completion worsened 7.33%.
The negative direction also appears in CPU and the two stages using the memo.
This is one local paired diagnostic, not a statistical population or production
capacity result. The off run observed 8.772 s / 11.702 s with no memo activity.

Generation avoided 5,106 of 14,958 solver calls; final revalidation avoided 2,427
of 7,904. Total: **7,533 / 22,862 (32.95%)** avoided, while 15,329 calls still
executed the unchanged solver. Generation evicted 9,340 entries; revalidation
evicted 4,965. Both stayed at or below 512 entries and had zero unsupported-input,
dependency, or error fallbacks for this captured case. Key/sort/memo/return-copy
work and still-required original-order sums outweighed the observed avoided work
in this measured implementation, including its instrumentation.

Per-entry deep-size instrumentation is inside this prototype's timed miss path;
its own overhead has **not** been separated from cache overhead. Therefore this
result rejects this implementation and does not prove every possible assignment
cache is slower. No instrumentation removal, capacity tuning or second favorable
search was attempted after seeing the result.

Generation/revalidation peak summed per-entry size estimates were 4,420,883 and
4,374,964 bytes. These overcount shared immutable payloads across entries and omit
the OrderedDict object overhead; they are not allocator or RSS measurements.
Keys/assignments are private Search-local data. Global diagnostic storage contains
only scalar counters and weak references, not Search/Asset/key/result ownership.
Both memos report released, and live memo count is zero after completion. The RSS
increase in this pair is observed, not precisely attributed or a 2GB-host fit claim.

## Disposition

Keep the private artifacts for reproducibility, record the negative result, and
stop. Parent accepted **no integration**. All CPU/source/HEAD guards are released;
no production setting, runtime file, independent grader or offer inventory changed
because of this probe.
