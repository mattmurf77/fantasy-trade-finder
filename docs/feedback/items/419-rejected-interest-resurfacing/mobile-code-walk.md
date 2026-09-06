# G419 mobile code walk

2026-09-06 · runtime/guard commit `396d92fc` · R4/T7.
The implementation diff was read end-to-end. Line references below refer to
that commit. [Build evidence](mobile-build-evidence.md) separates executable
state/adapter checks, structural checks and unrun native acceptance.

## Actual identity and verified evidence

`mobile/src/utils/tradeDisposition.ts:11` builds a JSON key from acting account,
league, known counterparty and separately sorted/deduplicated give/receive sets.
It rejects missing scope/partner/empty sides and a conflicting card league.
Card IDs and array ordering cannot evade a pass; orientation, replacement assets,
other accounts/leagues or counterparties remain independent.

`TradesScreen.tsx:1956` freezes action context and the current session/deck epochs;
`:1964` clones the acted card and its asset arrays for the pass episode. Normal
per-card edits therefore keep their existing edited ID and changed package.
Canvas browse edits retain the existing separate meaning: they edit the canvas
used for queueing, while passing a browsed idea still acts on that engine idea.

`TradesScreen.tsx:5849` takes every progressive reason target from that frozen
acted card, including actual ID, league, give/receive IDs and counterpart.
`mobile/src/api/declineReasons.ts:98` serializes those already-supported fields
and returns the existing structured body or `null` for transport failure.
`:89` types the existing response fields; there is no new public response field.

`tradeDisposition.ts:31` settles independent writes. A true reason is sticky;
`:38` treats either an acknowledged ordinary swipe or verified reason as local
commitment. Only swipe failure with no pending or successful reason is total
failure. `TradesScreen.tsx:337` converts **only** `result?.passed === true` into
reason commitment. HTTP 200, `ok:true`, missing/false evidence and context echo
do not suffice. Swipe success at `:2426` retains best-effort acknowledgement
semantics and explicitly does not claim durable decision-row proof.

## Shared session record and stable deck position

`TradesScreen.tsx:293` owns one module-scoped in-memory record keyed by current
account, league and authenticated-session presence. The session subscription at
`:303` clears it and increments an epoch on a scope transition. Going A→B→A
cannot validate an old A callback. Remounts and stacked Trades screens reuse the
current record; there is no disk write or durable local ban.

`TradesScreen.tsx:328` commits idempotently only into the captured current scope.
`:584` subscribes each screen with `useSyncExternalStore`. The existing ordered
lane/browse/fairness logic is unchanged at `:4017`; the projection at `:4037`
applies the current mask on every render, not only when array length changes.
The helper at `tradeDisposition.ts:52` overlays ordinary card edits for identity,
preserves surviving raw cards/order, and retains an open reason episode's card.

The cursor is now a source position, with a visible-index adapter at
`TradesScreen.tsx:588`. It captures the current projection before queuing the
functional state update. Removing an acknowledged card behind the cursor no
longer shifts the cursor over its successor. `tradeDisposition.ts:72` maps
visible movement back into bounded source coordinates, preserving zero as the
existing reset sentinel. Backward, forward, exhaustion and reordered source
cases execute the real helper. Single-pin source snapshots at `:3659` save that
source position and restoration at `:3702` restores it directly.

The same existing reset effect now depends on both league and account at
`TradesScreen.tsx:2344`; it continues clearing deck and chooser. The only existing
test edit, `check-shop-deck.js:1743`, accepts this exact dependency change while
retaining its deck/chooser invariant.

## Held Undo, reason ownership and failure recovery

`TradesScreen.tsx:5550` keeps existing gesture/double-fire guards. A pass attempt
is created only for a dispatched action, and the reason path shares its first
attempt with the companion swipe. Four progressive calls remain at `:5880`,
`:5921`, `:5937` and `:5943`; the free-text bank still does not advance.

Held passes retain their captured attempt. `TradesScreen.tsx:2832` flushes the
existing delayed POST using its original context; `:2846` cancels a held action
without writing or committing. The mutation dispatch rejects a held old-account
action under a replacement account at `:2391`. An old-league request for the same
account still carries its original explicit league; it cannot commit into the
new local scope.

`TradesScreen.tsx:5868` clears the bank exactly once before advancing. A second
layer-2/overlay completion in the same batch is inert. Browse uses its existing
remove-and-return branch; ordinary deck advances once. The held reason card is
not simultaneously filtered out and counted in a second advancement.

`TradesScreen.tsx:2453` waits for pending reason evidence only in the detached
recovery task, not React Query's mutation lifecycle. Verified sibling success
suppresses rollback/toast. Total failure is fenced by mounted state, original
scope/epoch and current deck epoch (`:1970`), plus latest action identity and any
already committed exact key. The one-behind rewind reads the current deck ref,
not the callback's stale sorted array. It preserves a later/reordered fronted
card and cannot overwrite a newer action. The existing failure strings and hold
duration remain unchanged.

`TradesScreen.tsx:6104` keeps the synchronous browse mirror, functional removal,
existing tally and frozen sibling order. It maps the remaining projected rows
before clamping and retains the removed row/index/optional canvas edit on the
attempt. `:6157` restores it idempotently on total failure, restores its retry
position when appropriate, and preserves a later fronted card otherwise. This
fixes the old absent-row rollback gap rather than relying on a future refresh.

When the failed attempt still owns the panel, recovery clears its guards and
increments the retry key. `TradesScreen.tsx:8557` and `:9061` remount the relevant
panel/card controls so their internal once-only guards do not poison retry.

## Executed seams and held claims

`mobile/tests/check-trade-disposition.js:201` executes actual browse advance,
removal and restoration. `:234` executes the module session bus and stale-scope
sequence; `:245` executes the reason observer. `:281` executes the actual swipe
failure callback with pending/false/late-true evidence; `:297` tests current
reordered/later deck context; `:306` protects a newer action; `:312` protects
A→B→A. `:327` pins source-position snapshot wiring. Undo's no-write promise at
`:345` is source-wiring plus pure held-state evidence, not a native timer run.

No new control, string, event/property, feature flag, schema, dependency or
policy math was introduced. The test harness is not a mounted React screen or a
real network/DB test. Physical back/navigation/gesture behavior remains on the
pending checklist. Remote-only invalidation of a previously retained local card
without a locally observed pass remains explicitly held; server response
projection alone is not claimed to reconcile that retained screen.
