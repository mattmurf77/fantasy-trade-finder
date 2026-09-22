# Round 5 — equivalent evidence and worker optimization

The owner explicitly renewed the instruction to keep iterating and release only
when satisfied with evaluation. The single-freeze experiment saved14% but left
an86% first-durable regression, so it is evidence for a next experiment, not a
reason to abandon the latency gate or ship the slow candidate.

## Agent A: bounded performance lane after policy3 cross-review

Use the retained exact profiler and worker harness. Identify the largest remaining
avoidable repeated serialization/parsing, proof validation and per-offer setup.
The existing immutable `OwnerDecisionContext.as_dict()` detached-copy semantics,
exact snapshot bytes, `matches()` safety, dataclass replacement/deepcopy behavior,
and original historical proof must remain authoritative. No unchecked mutable
cached board, process-global request cache, skipped final validation, suppressed
diagnostics, reduced inventory/search budget or moved durability boundary.

Prototype privately first. Candidate options include the validated single-freeze
hook, extracting stable proof header fields once, read-only reuse within a single
immutable request, eliminating repeated identical same-family work, and avoiding
serialize→parse cycles where a genuinely detached/frozen representation can keep
the original evidence contract. Measure, do not assume a cache is faster. Track
peak memory as well as first-durable/completion time and full inventory.

You may inspect/experiment with `trade_gen_owner.py`, bilateral modules and pure
presentment privately. Do not edit shared runtime or server while C's policy
replay runs. After measured exact parity, send parent the smallest concrete patch
recommendation with tests; parent approves shared integration. No third-party
dependency or infrastructure purchase. Do not introduce persistent workers or
new background deployment without a separately scoped design.

Correctness comparison: native membership/order/terms; every public card and all
private proof/diagnostic bytes; full generation diagnostics excluding explicitly
named IDs/timestamps/elapsed; complete persisted evidence and stable first30 then
continuation prefixes. Check invalid/malformed proof, array order, stale terms,
deepcopy/replace, and mutated returned `as_dict()` data cannot alter the original.
Incumbent off-mode equality is also required if any shared helper changes.

First target is **no material regression from the matched incumbent actual-worker
boundary**, with all offers retained. The3s physical first-action target remains
separate, requiring dependency-valid preparation plus real device/load evidence;
do not label an isolated8s worker as a3s product success. Test at least alternating
matched pairs after source stabilization, coordinating CPU windows with C.

Stop this round after at most two substantial additional equivalent prototypes
or a clear safe patch. Report a negative result honestly if neither materially
closes the gap. Parent then decides the next code/data/rollout action from the
measured bottleneck; no endless micro-optimization or weakened release claim.
