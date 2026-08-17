# Plan — G9 Matches polish · #334 + #335 · 2026-08-16 wave

> **Plan only — no production code.** Base: `origin/main` @ `d3fe3ac` (v1.13.4).
> Group: G9 (Polish, mobile-only). Canonical folder per convention (lowest ID).
> Batch context: [`../304-positional-need-filter/batch-plan.md`](../304-positional-need-filter/batch-plan.md).
> QA regime: D-056 — Maestro/simulator retired; evidence = structural
> `mobile/tests/check-*.js` suites + unit-testable logic + code-walk proofs +
> operator TestFlight checklist.

**The decision in plain words:** the dismissed tile is *supposed* to vanish the
instant you tap Dismiss — and the code does remove it instantly. The bug is
that a background refresh of the list can land a moment later and put the tile
back, where it sits until the 5-second undo window plus a server round-trip
finishes. The fix makes the hidden tile immune to background refreshes. The
counts item needs no server change at all — both numbers are already on the
phone; we just have to start fetching the "Awaiting" list as soon as the screen
opens instead of waiting for the segment to be tapped.

## Items (verbatim)

- **#334 (bug, Matches, v1.13.4, mattmurf77):** "Dismissing trades awaiting
  the other players review is slow to have the tile disappear."
- **#335 (polish, Matches, v1.13.4, mattmurf77):** "Add a count next to Mutual
  Matches, Awaiting them, and the team specific filters underneath."

---

# Item #334 — dismiss-latency on "Awaiting them"

## Root-cause verdict: **defect (optimistic-removal resurrect race), NOT the deliberate 5s undo window**

The hypothesis "the perceived slowness IS the 5s undo window leaving the full
tile visible" is **ruled out by the code**: the tile is removed from the list
*at tap time*, before the undo window even starts.

Verified path on `origin/main` @ `d3fe3ac` (all file:line cites checked this
session):

1. **Tap** → `handleDismissAwaiting(a)` (`mobile/src/screens/MatchesScreen.tsx:420-452`).
   `ux.swipe_undo` is **true** in `config/features.json`, so the undo path is
   live in prod: the handler synchronously filters the row out of the
   `['awaiting-trades']` cache (`MatchesScreen.tsx:433-438`), parks the POST in
   `pendingDismissRef` behind a `setTimeout(…, UNDO_HOLD_MS)` (`:440-445`,
   `UNDO_HOLD_MS = 5000` at `:56`), and shows the 5s "Dismissed / Undo" toast
   (`:446-451`). Only the **toast** persists 5s — the tile is already gone.
2. **Timer fires** → `flushPendingDismiss()` (`:347-354`) →
   `dismissAwaitingMutation.mutate(row)` (`:296-321`) →
   `dismissAwaitingTrade` POST `/api/trades/awaiting/dismiss`
   (`mobile/src/api/trades.ts:564-583`).
3. **onSuccess** → `invalidateQueries(['awaiting-trades'])` (`:318-320`) —
   reconcile refetch. Backend suppression is correct: the GET filters
   `retracted_at IS NULL` (`backend/database.py:7089-7090`; the other
   suppression points at `:4646-4648`, `:6797-6798`, `:7247`), so the fix
   below is **entirely client-side**.

So mechanically the tile disappears in one frame. The defect is that **the
optimistic removal is written only into the query cache, and nothing protects
it from a competing list read**. The canonical TanStack optimistic-update step
— `await queryClient.cancelQueries(...)` before `setQueryData` — is missing at
**all four** optimistic-removal sites (`onMutate` of both mutations,
`MatchesScreen.tsx:264-274` and `:298-307`, and both tap-time handler paths,
`:395-401` and `:433-438`), and the 5s delayed POST stretches the race window
from milliseconds to 5+ seconds. Any of these puts the dismissed tile **back
on screen** until timer (≤5s) + POST round-trip + reconcile refetch complete —
i.e. "slow to have the tile disappear", typically 5–8s:

- **In-flight refetch at tap time** (the everyday repro): entering the
  Awaiting segment flips the query's `enabled` gate
  (`MatchesScreen.tsx:230-235`, `staleTime: 15_000`), so a background refetch
  fires on re-entry (default `refetchOnMount`; app defaults in
  `mobile/src/state/queryClient.ts:21-35`). Dismiss while that response is in
  flight → the response lands after the optimistic `setQueryData` and
  overwrites it, resurrecting the row (the row is still live server-side —
  the POST hasn't fired yet).
- **Refetch started during the 5s hold:** pull-to-refresh
  (`RefreshControl` → `onRefresh`, `:650-653`, `:1055-1060`);
  `refetchOnReconnect: true` (`queryClient.ts:29`) on a flaky connection;
  `useSession.switchLeague` invalidating both keys
  (`mobile/src/state/useSession.ts:455-456`) — reachable mid-window via the
  #319 open-in-calc league switch (`MatchesScreen.tsx:475-490`).
- **Mutual segment, same bug:** the Matches tab-press prefetch
  (`mobile/src/navigation/TabNav.tsx:746-750`, `['matches','all']`,
  `staleTime: 15_000`) plus `handleDismiss`'s identical unprotected removal
  (`:395-401`) gives the mutual list the same resurrect race. #334 was
  reported against Awaiting; fix both symmetrically.

**Undo-window verdict consequence:** the 5s window is a deliberate, shipped
design (S3 PRD-03, delayed-POST-because-no-un-dismiss-endpoint,
`MatchesScreen.tsx:323-330`) and is *not* what the user sees — no
presentational collapse-into-snackbar change is needed. The tile already
collapses instantly once the race is fixed; the toast staying 5s is the undo
affordance working as designed.

## Fix approach (client-only, `MatchesScreen.tsx`)

Two layers — the render-layer guard is the load-bearing one because it makes
tile visibility independent of *anything* the cache does:

1. **Render-layer suppression (primary).** New
   `const [hiddenKeys, setHiddenKeys] = useState<ReadonlySet<string>>()` —
   keys `match:<match_id>` / `awaiting:<league_id>:<trade_id>` (matching the
   lists' keyExtractors, `:943`, `:1054`). `visibleMatches` /
   `visibleAwaiting` memos (`:585-593`) additionally filter out hidden keys.
   Lifecycle:
   - **add** at tap time in `handleDismiss` / `handleDismissAwaiting`
     (both branches — undo-flag on *and* off);
   - **remove** on `undoDismiss` (row reappears instantly from the snapshot
     restore, `:358-372`);
   - **remove** in each mutation's `onSettled` (keyed from the mutation
     variables) — `onError` has already restored/refetched honestly
     (`:275-284`, `:308-317`; the S-9 fake-success guard is untouched), and
     `onSuccess`'s invalidate refetch returns a server list without the row.
     Removing on settle (not on success-refetch-complete) accepts a ≤1-refetch
     flicker only in the already-degraded "POST succeeded but GET still stale"
     case, which the backend filter makes impossible in practice.
   A `Set` (not a single key) because `flushPendingDismiss` allows a previous
   dismiss's POST to be in flight while a new one is pending (`:388-393`).
2. **`cancelQueries` hygiene (secondary).** Add
   `queryClient.cancelQueries({ queryKey: [...] })` immediately before every
   optimistic `setQueryData` (the four sites above) so an in-flight GET can't
   stomp the cache either — this keeps the *cache* coherent (undo snapshots,
   #335 counts), while layer 1 keeps the *tiles* honest.

Explicitly **not** doing: LayoutAnimation/exit animation (out of scope, not
the complaint); changing `UNDO_HOLD_MS`; any backend change; touching
`TradeCard.tsx` / `MatchValueSection.tsx` (S-2/S-6 pins in
`mobile/tests/check-awaiting-dismiss.js` stay green by construction).

**Runtime confirmation** (since this wave's diagnosis is static): the
TestFlight checklist below includes the deterministic repro — enter Awaiting
while the spinner/refresh is visible, dismiss immediately, watch for the
resurrect. If the operator cannot repro pre-fix on TestFlight, the fix still
stands as a correctness repair (the race is proven from code), but we note it
in the ship record.

---

# Item #335 — counts on segments and league chips

## Data-source verdict: **fully client-derivable — no new or changed API field**

Both lists are already full row arrays on the client:

- **Mutual count** = league-filtered length of `matchesQuery.data`
  (`['matches','all']`, `MatchesScreen.tsx:220-225`) — always fetched on this
  screen, plus tab-press prefetch (`TabNav.tsx:746-750`).
- **Awaiting count** = league-filtered length of `awaitingQuery.data`
  (`:230-235`). **The one required change:** this query is gated
  `enabled: segment === 'awaiting'`, so on landing the Awaiting count would be
  unknown. Drop the gate (`enabled: true`; keep `staleTime: 15_000`, add
  `placeholderData: (prev) => prev` for parity with the matches query). Cost:
  one extra GET `/api/trades/awaiting` per Matches visit — an existing,
  already-cheap endpoint (`TradesScreen.tsx:3323` already fetches it
  opportunistically). **No API surface, schema, flag, or analytics change — G9
  stays on the pure-Polish path.** (Rejected alternative: the league summary's
  `matches_awaiting` field (`mobile/src/api/league.ts:171-173`) is per-league
  and would need a new cross-league aggregate — a backend change for data the
  client already has.)
- **Per-chip counts** = per-league lengths over the same two arrays
  (`filterChips` memo, `:600-617`).

**Count semantics (so counts always equal what tapping shows):**

- Segment pills count rows under the **active league filter**; chips count
  rows in the **active segment**. Both derive from the *post-#334-fix*
  arrays (i.e. after `hiddenKeys` filtering), so a pending-dismiss tile and
  its count move together — one shared memo family, no second source of truth.
- **Never fabricate:** while a list's first fetch hasn't resolved
  (`data === undefined`), render **no count** on the affected pill/chips — not
  `0`. Once resolved, `0` renders honestly.

## Placement spec (Chalkline)

Counts are informational data → **Plex Mono inline count**, the shipped
convention for counts-next-to-labels (tier headers, TierBin headers, UnlockBar
— `docs/design/components.md:81,114-115`). Explicitly **not** `CountBadge`
(`components.md:37`): its `--neg` fill is the notification-urgency encoding —
wrong semantics for an inventory count, and a new red accent on this screen
would violate ADR-005 accent rules.

- **Segment pills** (`SegmentBtn`, `:1201-1229`; styles `:1333-1347`): label
  becomes a row — existing `type.label` text + count in `fonts.mono` 11,
  `chalk.dim` (inactive) / `chalk.base` (active), separated by `space.xs`.
  E.g. `MUTUAL MATCHES 3`. No box, no pill, no color — bare mono numeral
  (ScorePill precedent, `components.md:34`). `SegmentBtn` gains an optional
  `count?: number` prop; omitted → renders exactly as today.
- **League chips** (`:816-840`; styles `:1357-1371`): same construction inside
  the chip — chip name + mono 11 count, `chalk.dim` / active `chalk.base`.
  The "All" chip counts the whole active segment. Long-name chips truncate the
  name, never the count.
- **A11y:** extend existing `accessibilityLabel`s — segment: `"Mutual
  matches, 3 trades"`; chip: `"Filter: Dynasty Degens, 2 trades"`; count
  omitted from the label when unknown.
- **testIDs:** none new — counts asserted structurally (D-056), and the
  existing `matches.segment.mutual` / `matches.segment.awaiting` /
  `matches.league-chip.*` ids are untouched.

---

# Risks

| Risk | Mitigation |
|---|---|
| `hiddenKeys` desync — a key never cleared hides a live row forever | Single clear path: `onSettled` always runs (mutations `retry: 0`); undo clears; unmount flush commits the POST whose settle clears. Structural pin asserts the `onSettled` clear exists. |
| `cancelQueries` cancels a refetch some *other* consumer awaited | Both keys are consumed only by this screen + fire-and-forget prefetches (`TabNav.tsx:747`, `TradesScreen.tsx:3323` uses `fetchQuery` on a different code path — a cancelled promise there surfaces on its own catch). Accepted. |
| Always-on awaiting fetch adds backend load | One GET per Matches visit on an existing endpoint already called opportunistically elsewhere; 15s staleTime bounds it. |
| Counts vs. list disagreement during the undo hold | Both derive from the same post-hide memo family by construction. |
| Segment-pill row crowding on narrow devices | Count is 1-3 mono chars + `space.xs`; pills are `flex: 1` at 44px height with short labels — verified visually on TestFlight (checklist item). |
| Concurrent-wave file collisions | See ownership below — G9's files are touched by no other 2026-08-16 group (G6 is backend-only; G2/G3/G4/G5 touch other surfaces; G7/G8 held). |

# File ownership (all mobile — disjoint from G6's backend files)

| File | Change |
|---|---|
| `mobile/src/screens/MatchesScreen.tsx` | Both items — sole production-code file. #334: `hiddenKeys` state + memo filters + `cancelQueries` at 4 sites + lifecycle wiring. #335: `enabled` gate drop, count derivation memos, `SegmentBtn` count prop, chip count render, a11y labels, 2 style entries. |
| `mobile/tests/check-awaiting-dismiss.js` | Extend (new pins below); existing 21 checks must stay green. |
| `mobile/tests/check-matches-counts.js` | New structural suite for #335. |
| `docs/feedback/items/334-matches-dismiss-latency/` + `335-…/status.md` | Status updates at build/ship. |

**#334 stays fully client-side** — #318's suppression logic
(`backend/database.py`, `backend/server.py:13266` route) is correct and
untouched; no G6 overlap (G6 owns `backend/trade_service.py` /
`backend/server.py` presentment surfaces). Not touched, by design:
`TradeCard.tsx`, `MatchValueSection.tsx`, `mobile/src/api/trades.ts`,
`backend/*`, `config/features.json`.

**Docs table (gates §3):** `docs/api-reference.md` n/a (no route change);
`docs/cross-client-invariants.md` n/a (no new enum/threshold/color);
`docs/design/components.md` — one-line amendment noting Matches
segment/chip counts follow the mono-count convention; `living-memory/LLD.md`
n/a (reuses established grammars); HLD/architecture n/a. Analytics: no new
events (counts are render-only; dismiss events unchanged — server-fired
`awaiting_trade_dismissed` stays server-fired).

# Test plan (D-056: no Maestro)

**Unit (jest):** extract the two pure derivations into
`mobile/src/utils/matchesDerive.ts` — `filterVisible(rows, leagueFilter,
hiddenKeys, keyFn)` and `countsByLeague(rows)` — and unit-test: hidden-key
exclusion, league scoping, undefined-data → no-count sentinel, count/list
agreement with a pending hide. (Keeps MatchesScreen surgical: memos call the
helpers.)

**Structural (`mobile/tests/`), sabotage-pinned RED-then-green:**
- `check-awaiting-dismiss.js` additions — **S-10 resurrect-race:** (a)
  comment-stripped source has `cancelQueries` adjacent to each of the 4
  optimistic `setQueryData` sites; (b) `visibleAwaiting`/`visibleMatches`
  memos reference the hidden-keys filter; (c) `onSettled` clears the key in
  both mutations; (d) `undoDismiss` clears it. Existing pins 1-21 (S-6…S-9)
  must pass unmodified — proves no TradeCard leak, surface flip, contract
  drift, or fake-success regression.
- `check-matches-counts.js` (new) — **S-11 count-fabrication:** (a) counts
  derive from the shared visible/hidden-aware helpers, not raw `query.data`
  lengths; (b) `awaitingQuery` has no `enabled:` gate tied to `segment`; (c)
  undefined-data renders no `0`; (d) no `CountBadge`/`--neg`/new hex on this
  screen; (e) count text uses `fonts.mono`; (f) existing segment/chip testIDs
  unchanged.
- `mobile/scripts/testid-lint.sh` — no new testIDs, must stay green.
- `npx tsc --noEmit`.

**Operator TestFlight checklist (runtime proof):**
1. **#334 repro/fix:** open Matches → Awaiting while the refresh is in
   flight (or pull-to-refresh) → immediately Dismiss a tile → tile vanishes
   instantly and **never reappears**; toast shows Dismissed/Undo for ~5s.
2. Dismiss → tap Undo within 5s → tile returns instantly; still present after
   a pull-to-refresh (like was never retracted server-side).
3. Dismiss → let the window lapse → pull-to-refresh → tile stays gone
   (server retraction confirmed end-to-end).
4. Dismiss → immediately leave the screen → return → tile gone (unmount
   flush).
5. Airplane mode → Dismiss → window lapses → POST fails → tile honestly
   reappears with "Could not dismiss — try again" (S-9 unchanged).
6. Repeat 1 on the **Mutual** segment (tab re-tap prefetch racing a dismiss).
7. **#335:** counts appear next to both segments and every chip on landing
   (Awaiting count present *without* opening the segment); counts match
   visible tiles across segment toggles + chip filters; dismiss decrements
   the count in the same frame the tile leaves; zero states show `0`;
   narrow-device layout intact.
