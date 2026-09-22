# Parent specification — exact request-local assignment reuse

September22,2026. Agent C, after completing remaining-compute-audit.md. One
private prototype only; no shared runtime, new grader or selection policy.
Coordinate CPU/source guards with A's integrated round7 validation. Parent owns
the decision to integrate, compose further, or stop this probe.

## Opportunity and invariant

Owner `_lineup` builds ordered usable assets, calls `trade_roster.assign`, then
sums selected values in the original usable order. The solver sorts its inputs
by ID internally. Pick/inactive-only differences can require the same assignment
even when complete package/roster keys differ. Reuse **only the exact assignment**
within a single candidate Search; preserve the existing per-call usable order,
positional summation and bench calculation. Do not cache the whole lineup by an
unordered roster and thereby change floating addition or ranking ties.

Prototype the smallest solver-call seam, using original shared `_lineup` work
and the unchanged solver on every miss. The cache key must bind ordered slots,
all actually consumed sorted Asset inputs, exact value types/order semantics and
the relevant eligibility/code contract. Own all key material and cached outputs;
an ordinary caller gets a fresh assignment list. No global/session/persisted memo,
binary proof memo, proof-boundary fast path, changed solver, extra age/projection
claim, altered computation/search budget or early offer ordering.

Missing/invalid/unsupported inputs must behave like the original path, including
errors. Preserve duplicate-ID stable ordering if it can reach the solver; do not
canonicalize a case beyond what the actual solver does. Initialization may call
the hook before the rest of Search is ready; explicitly handle lifetime/setup.
State which dependencies are genuinely immutable in the supported process rather
than inventing general mutation epochs. A changed dependency cannot borrow a
stale result. Measure cache entries/hits and retained key/result material.

## Falsification and measurement

Compare original versus prototype on permuted usable rosters with floating values
that expose addition-order differences, tie cases, overlapping FLEX/Superflex,
empty/partial lineups, picks, inactive/injured players, changed slots, Asset values
and positions, duplicate IDs, malformed input, multiple managers and two Search
instances. Mutating returned lists must not contaminate subsequent results.
Use actual original solver calls/counters to prove repeat work is skipped while
outer sums still execute in original order. No approximate point/utility equality.

Then use fixed hash seed0 and source-bound actual-worker/native artifacts after
the shared round7 integration is frozen. Retain every native proof/report byte,
final public/persisted occurrence and publication prefix. External evaluations
and default-off behavior remain exact. Record unchanged first30/completion, RSS
and cache hit/lifetime evidence in an exclusive CPU window. Earlier profile
seconds are only prioritization evidence, not projected savings.

Write assignment-reuse-evidence.md. Any mismatch or negligible benefit is a
negative finding, not permission to round numbers, shrink inventory or retune
quality. No shared integration without parent review and a subsequent spec.
