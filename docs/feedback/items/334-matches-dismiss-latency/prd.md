# PRD — G9 Matches polish · #334 dismiss resurrect-race + #335 segment/chip counts

> **Contract for the build agent.** Group G9, 2026-08-16 wave, Polish path
> (client-only, no new API fields — verified, see §V). Plan:
> [`plan.md`](plan.md). Scope: [`scope.md`](scope.md). Batch:
> [`../304-positional-need-filter/batch-plan.md`](../304-positional-need-filter/batch-plan.md).
> QA regime: **D-056** (`living-memory/DECISIONS.md`) — no Maestro, no
> simulator; evidence = structural suites + executed unit tests + code-walk
> proof + operator TestFlight checklist.
>
> **Base note (author verification, 2026-08-16):** the plan is labeled
> `origin/main @ d3fe3ac`, but its file:line cites match `origin/main @
> 0b2dcee` (guide-v2 + fit-congruence merged after the plan's label;
> `MatchesScreen.tsx` shifted +76 lines, mechanism unchanged at both
> revisions). All line cites in this PRD are against **`0b2dcee`**. Build
> branches from a freshly fetched `origin/main` per CLAUDE.md — re-run
> `git diff <base-you-branched>..origin/main -- mobile/src/screens/MatchesScreen.tsx`
> at branch time and re-anchor if it moved again.

**The decision in plain words:** #334 — the dismissed tile already vanishes
instantly, but a background list refresh can put it back for up to ~5–8
seconds; we make hidden tiles immune to every refresh. #335 — both counts are
already on the phone; we show them next to the segments and league chips, and
start fetching the Awaiting list when the screen opens so its count is there
from the first frame.

---

## Items

- **#334 (bug, Matches, v1.13.4, mattmurf77):** "Dismissing trades awaiting
  the other players review is slow to have the tile disappear."
- **#335 (polish, Matches, v1.13.4, mattmurf77):** "Add a count next to Mutual
  Matches, Awaiting them, and the team specific filters underneath."

## Verdicts (verified this session, §V)

- #334 is a **defect** (optimistic-removal resurrect race), not the 5s undo
  window. The tile is filtered out of the `['awaiting-trades']` /
  `['matches','all']` cache at tap time
  (`mobile/src/screens/MatchesScreen.tsx:433-438` / `:395-401`), the POST is
  parked behind a 5s timer (`UNDO_HOLD_MS`, `:56`), and **no
  `cancelQueries` exists anywhere in `MatchesScreen.tsx`** — so any list read
  that resolves after the tap overwrites the cache and resurrects the row
  until timer + POST + reconcile-refetch complete.
- #335 is **fully client-derivable**. No new or changed API field. The only
  behavioral data change is fetching the Awaiting list on screen mount instead
  of on first segment tap.

## Cache-repopulation paths (exhaustive hunt, §V — the fix must survive all)

| # | Path | Where |
|---|---|---|
| P1 | Refetch on mount / `enabled` flip while stale (`staleTime: 15_000`, default `refetchOnMount`) | `MatchesScreen.tsx:226-235`; defaults `mobile/src/state/queryClient.ts:24-31` |
| P2 | Pull-to-refresh (`onRefresh` → `refetch()`) | `MatchesScreen.tsx:650-653`; RefreshControls `:944-949`, `:1055-1060` |
| P3 | Reconnect refetch (`refetchOnReconnect: true`, NetInfo-wired onlineManager) | `queryClient.ts:28` |
| P4 | `switchLeague` invalidates both keys — reachable mid-undo-window via #319 open-in-calc (`MatchesScreen.tsx:475-490`) | `mobile/src/state/useSession.ts:455-456` |
| P5 | Matches tab-press prefetch of `['matches','all']` | `mobile/src/navigation/TabNav.tsx:746-750` |
| P6 | Guide-v2 N6.1 gate check: `fetchQuery({queryKey:['awaiting-trades']})` on TradesScreen focus — writes the cache from the server while a dismiss can still be pending | `mobile/src/screens/TradesScreen.tsx:3322-3325` |

Hunt result: these six are **all** repopulation paths on `origin/main @
0b2dcee`. `refetchOnWindowFocus: false` (`queryClient.ts:29`) — no focus
refetch. No `refetchInterval` on either key. No broad/unkeyed invalidations
touch them. P6 is new since the plan's base label (guide-v2) and is exactly
why the render-layer guard (R-1), not `cancelQueries` alone, is load-bearing:
P6 can start while the user is on another tab, after every tap-time
`cancelQueries` has run.

---

## Requirements

Each requirement maps to an item and at least one test (test IDs defined in
§Test plan).

### #334 — resurrect-race fix (all in `mobile/src/screens/MatchesScreen.tsx` + `mobile/src/utils/matchesDerive.ts`)

- **R-1 — Render-layer pending-dismiss suppression (primary, load-bearing).**
  New `hiddenKeys: ReadonlySet<string>` state; keys `match:<match_id>` and
  `awaiting:<league_id>:<trade_id>` (prefixed forms of the lists'
  keyExtractors, `:943` / `:1054`). The `visibleMatches` / `visibleAwaiting`
  memos (`:587-595`) additionally exclude hidden keys, via the shared pure
  helper `filterVisible` (R-9). A dismissed tile therefore leaves in the same
  frame as the tap and **cannot reappear via any of P1–P6**, because
  visibility no longer depends on cache contents. A `Set`, not a single key:
  `flushPendingDismiss` (`:347-354`) lets a previous dismiss's POST be in
  flight while a new dismiss is pending (single-slot `pendingDismissRef`,
  `:328-345`).
  *Item #334 · Tests: U-1, U-4, S-10b, code-walk CW-1, TF-1, TF-6.*

- **R-2 — `hiddenKeys` lifecycle (no tile hidden forever).**
  - **Add** in `handleDismiss` (`:379-413`) and `handleDismissAwaiting`
    (`:417-452`), in **both** branches — undo-flag on and off (`ux.swipe_undo`
    is `true` in prod, `config/features.json:117`, but the off-branch must not
    regress).
  - **Remove** in `undoDismiss` (`:358-372`) — the row reappears instantly
    from the snapshot restore.
  - **Remove with ordered unhide** (B-1, round 1 — keyed from the mutation
    variables, `id` for match / `row` for awaiting; **not** a bare
    `onSettled` clear):
    - `onError`: unhide **immediately** — the snapshot restore + refetch
      (`:275-284`, `:308-317`) has honestly restored the row, and it must
      render at once.
    - `onSuccess`: unhide **only after the reconcile refetch resolves** —
      `await queryClient.invalidateQueries({ queryKey })` (its promise
      settles when the refetch completes, and settles even if the refetch
      fails, so no tile is hidden forever), *then* clear the key.
    Why the ordering is load-bearing (corrected mechanism, B-1): the
    residual race is a GET racing the POST's commit — a refetch starting
    *after* `onMutate`'s `cancelQueries` (P2/P3/P6 during the POST
    round-trip) reads the row pre-commit server-side. A bare `onSettled`
    clear would unhide against that resurrected cache for one round-trip,
    reproducing the #334 symptom. The backend `retracted_at` filter cannot
    close this — it only governs GETs that read after the commit. Awaiting
    the invalidate guarantees the unhide lands on a post-commit list.
    Mutations are `retry: 0` (`queryClient.ts:32-34`), so exactly one of
    `onError`/`onSuccess` runs per dismiss.
  *Item #334 · Tests: U-2, U-3, S-10c (ordering-pinned), S-10d, TF-2, TF-4,
  TF-5.*

- **R-3 — `cancelQueries` hygiene (secondary).** `await
  queryClient.cancelQueries({ queryKey: [...] })` immediately before each of
  the **four** optimistic `setQueryData` sites: `dismissMutation.onMutate`
  (`:264-274`), `dismissAwaitingMutation.onMutate` (`:298-307`),
  `handleDismiss` tap-time removal (`:395-401`), `handleDismissAwaiting`
  tap-time removal (`:433-438`). This keeps the *cache* coherent (undo
  snapshots, #335 counts) while R-1 keeps the *tiles* honest. Known accepted
  side effect (corrected round 1 NB-1, verified `TradesScreen.tsx:3252-3268`):
  a cancelled P6 `fetchQuery` rejects into its own `.catch` →
  `decide(false)` → `v2ShowN61(false)` — the N6.1 beat **shows immediately
  with its router-less copy variant**; nothing defers. Benign and
  vanishingly rare.
  *Item #334 · Tests: S-10a, CW-1.*

- **R-4 — Undo semantics and the #318 contract untouched.** `UNDO_HOLD_MS`
  stays 5000 (`:56`). The POST still fires only after the window (or on
  flush: second dismiss, unmount `:374-377`). The wire contract is
  byte-identical — `dismissAwaitingTrade` (`mobile/src/api/trades.ts:562-588`)
  and the backend (`POST /api/trades/awaiting/dismiss`,
  `backend/server.py:13254`; `retracted_at` suppression at
  `backend/database.py:4648`, `:6798`, `:7090`, `:7247`) are **not touched**.
  Undo within 5s restores the tile instantly (R-2); the 5s toast is the undo
  affordance working as designed — no presentational change to it.
  Two pre-existing edge behaviors are declared **known, unchanged, out of
  scope** (round 1, NB-2/NB-3 — G9 must not silently absorb them):
  - **Background/kill during the undo window:** iOS suspends JS timers in
    background — a dismiss backgrounded mid-window fires its POST on
    **resume** (the hidden tile persists meanwhile; fine); an app **killed**
    before resume never sends the POST, so the row honestly returns next
    launch ("my dismiss didn't stick"). Shipped #318/S3-PRD-03 semantics;
    the hardening, if ever wanted, is an `AppState → 'background'` flush —
    an orchestrator decision, not part of this Polish group.
  - **Undo racing the flush timer:** Undo tapped after `flushPendingDismiss`
    has run is a no-op (`pendingDismissRef` already null, `:358-361`) —
    frame-level exposure only, since the toast `holdMs` and the timer are
    the same 5000ms started in the same tick. Likewise, undo's
    snapshot-restore (`p.prev`) can overwrite a fresher mid-window refetch
    result until the next refetch. Both shipped, both unchanged.
  *Item #334 · Tests: existing pins 7–12 + 13–21 of
  `check-awaiting-dismiss.js` (unmodified), TF-2, TF-3.*

- **R-5 — Honest failure preserved.** The S-9 guarantees are unchanged:
  `onError` restores the snapshot, refetches under the undo flag, and shows
  "Could not dismiss — try again" (`:275-284`, `:308-317`). With R-2, a
  failed dismiss's row is also **unhidden immediately in `onError`** — it
  visibly returns, never invisibly archived and never invisibly hidden.
  *Item #334 · Tests: existing pins 15–18 (unmodified), S-10c, TF-5.*

- **R-6 — Mutual segment fixed symmetrically.** #334 was reported against
  Awaiting; the identical unprotected removal exists on the mutual path
  (`:264-274`, `:395-401`) with its own racer (P5). R-1/R-2/R-3 apply to both
  segments.
  *Item #334 · Tests: U-1, S-10a/b, TF-6.*

### #335 — counts (same files, plus 2 style entries)

- **R-7 — Mount-time Awaiting fetch.** `awaitingQuery` (`:226-235`) drops
  `enabled: segment === 'awaiting'` (becomes always-enabled); keeps
  `staleTime: 15_000`; gains `placeholderData: (prev) => prev` for parity
  with `matchesQuery` (`:220-225`). **Data-usage tradeoff, stated honestly:**
  one extra GET `/api/trades/awaiting` per Matches visit for users who never
  open the segment — an existing endpoint already called opportunistically on
  TradesScreen focus (P6), bounded by the 15s staleTime; and P3 reconnect
  refetches now include it even off-segment. Accepted for a count that must
  be correct on landing. Rejected alternative (verified): the league
  summary's `matches_awaiting` (`mobile/src/api/league.ts:172-173`) is
  per-league — a cross-league aggregate would be a backend change for data
  the client already has.
  *Item #335 · Tests: S-11b, TF-7.*

- **R-8 — Count semantics.** Segment pills count rows under the **active
  league filter**; league chips count rows in the **active segment**; the
  "All" chip counts the whole active segment. All counts derive from the
  **post-R-1 arrays** (hidden-aware), so a pending-dismiss tile and its count
  move together — one shared memo family, no second source of truth. A
  dismiss decrements the count in the same frame the tile leaves; an undo
  restores both in the same frame.
  *Item #335 · Tests: U-4, U-5, S-11a, TF-7, TF-8.*

- **R-9 — Shared pure derivations.** New `mobile/src/utils/matchesDerive.ts`
  (pure, zero runtime imports — the transpile-under-node test idiom requires
  this): `filterVisible(rows, leagueFilter, hiddenKeys, keyFn)` and
  `countsByLeague(rows)` (or equivalent signatures the builder finalizes —
  the *purity* and *single-source* properties are the requirement).
  `MatchesScreen`'s memos call these helpers; counts are never computed from
  raw `query.data` lengths at a second site.
  *Items #334 + #335 · Tests: U-1…U-5, S-11a.*

- **R-10 — Never fabricate.** While a list's first fetch is unresolved
  (`data === undefined`), the affected pill/chips render **no count** — not
  `0`. Once resolved, an empty list renders an honest `0`. (The unresolved
  state is real on cold mount for the awaiting list even after R-7.)
  *Item #335 · Tests: U-3-count, S-11c, TF-7.*

- **R-11 — Chalkline construction (verified against
  `docs/design/components.md` + `docs/design/design-system.md:107`).** Counts
  are informational inventory data → **bare Plex Mono inline numeral**, the
  shipped counts-next-to-labels convention (ScorePill `components.md:34`
  "no box — bare number"; tier headers / TierBin headers / UnlockBar mono
  counts, `components.md:81` and § Tier bins). Explicitly **not**
  `CountBadge` (`components.md:37`): its `--neg` fill is the
  notification-urgency encoding — wrong semantics, and a new red accent on
  this screen would violate ADR-005.
  - **Token correction (§V):** the mono font token is **`fonts.data`**
    (`IBMPlexMono_500Medium`, `mobile/src/theme/chalkline.ts:93`) — the
    plan's `fonts.mono` does not exist. Size **11** (the type floor,
    `design-system.md:107` — nothing below 11px).
  - **Segment pills** (`SegmentBtn`, `:1201-1229`; styles `:1333-1347`):
    label row = existing `type.label` text + count in `fonts.data` 11,
    `chalk.dim` inactive / `chalk.base` active, separated by `space.xs`.
    E.g. `MUTUAL MATCHES 3`. `SegmentBtn` gains an optional
    `count?: number` prop; omitted → renders exactly as today.
  - **League chips** (`:816-840`; styles `:1349-1371`): same construction —
    chip name + `fonts.data` 11 count, `chalk.dim` / active `chalk.base`.
    Long names truncate the **name**, never the count.
  - **A11y:** segment pill gains/extends `accessibilityLabel`: `"Mutual
    matches, 3 trades"`; chip label extends the existing `Filter: ${name}`
    (`:826`) to `"Filter: Dynasty Degens, 2 trades"`. Count omitted from the
    label while unknown (R-10).
  *Item #335 · Tests: S-11d, S-11e, TF-8.*

- **R-12 — No testID changes.** `matches.segment.mutual` /
  `matches.segment.awaiting` / `matches.league-chip.*` unchanged; no new
  testIDs (counts asserted structurally per D-056).
  `mobile/scripts/testid-lint.sh` stays green.
  *Item #335 · Tests: S-11f, CI testid-lint.*

### Out of scope (both items)

No exit animation / LayoutAnimation; no `UNDO_HOLD_MS` change; no backend,
flag, schema, or analytics change; `TradeCard.tsx`, `MatchValueSection.tsx`,
`mobile/src/api/trades.ts`, `backend/*`, `config/features.json` untouched.
File ownership disjoint from G6 (backend-only) per plan § File ownership.

---

## Test plan (D-056 — no Maestro, no simulator)

### Executed unit tests (proven-to-fail, named sabotages)

Mobile has **no jest harness** (§V — the plan's "Unit (jest)" line is
corrected here, not silently patched): the established idiom is
`ts.transpileModule` on the real pure module, run under plain node
(`mobile/tests/check-trade-text.js:20-23` states it; same as
`check-session-rerank.js`). The executed tests live inside
`check-matches-counts.js` (keeping the plan's file set) and exercise the real
`matchesDerive.ts`:

- **U-1** hidden-key exclusion: a row whose key is in `hiddenKeys` is absent
  from `filterVisible` output (both key shapes). *Sabotage: drop the
  hiddenKeys test from the implementation → RED.*
- **U-2** hide/unhide round-trip: removing the key restores the row (undo
  path). *Sabotage: make the filter latch permanently → RED.*
- **U-3** league scoping: `'all'` vs a league id; **U-3-count**
  undefined-data → no-count sentinel (never `0`). *Sabotage: return `0` for
  undefined → RED.*
- **U-4** count/list agreement with a pending hide: `countsByLeague(visible)`
  totals equal the visible array's per-league lengths while a key is hidden.
  *Sabotage: derive counts from the raw array → RED.*
- **U-5** segment-pill vs chip scoping: pill count respects the league
  filter; chip counts respect the segment array they're fed. *Sabotage: swap
  the inputs → RED.*

Each sabotage is applied to a scratch copy during suite authoring and the RED
run is recorded in the QA notes (proven-to-fail rule).

### Structural suites (`mobile/tests/`, run by CI `for f in tests/check-*.js`)

- **`check-awaiting-dismiss.js` — extend with S-10 (resurrect-race), keeping
  existing assertions 1–21 (S-6…S-9) byte-unmodified:**
  - S-10a: comment-stripped source has `cancelQueries` adjacent to each of
    the 4 optimistic `setQueryData` sites (both keys).
  - S-10b: `visibleMatches` / `visibleAwaiting` derive through the
    hidden-keys filter (`filterVisible` referenced, not a raw league filter).
  - S-10c **(ordering-pinned, B-1)**: in both mutations, comment-stripped
    source shows (i) the hidden-key clear inside `onError`, and (ii) in
    `onSuccess`, `await queryClient.invalidateQueries(...)` **preceding**
    the hidden-key clear — and **no** bare `onSettled` clear. *Named
    sabotage — exactly "unhide before await": move the `onSuccess` clear
    above the awaited invalidate (or revert to an `onSettled` clear) → RED.
    This sabotage reproduces the pre-fix ordering, so the pin fails on it
    by construction; RED run recorded in QA notes like the U-series.*
  - S-10d: `undoDismiss` clears the hidden key.
  - S-10e **(NB-5 insurance)**: `queryClient.ts` keeps
    `refetchOnWindowFocus: false` and neither `matchesQuery` nor
    `awaitingQuery` sets `refetchOnWindowFocus: true` — guards CW-1's
    "no focus refetch" premise (the focusManager IS AppState-bridged,
    `mobile/App.tsx:211-216`) against a future per-query override minting
    an unanalyzed seventh repopulation path.
- **`check-matches-counts.js` (new) — S-11 (count-fabrication) + U-1…U-5
  above:**
  - S-11a: counts derive from the shared hidden-aware helpers — no raw
    `matchesQuery.data.length` / `awaitingQuery.data.length` render sites.
  - S-11b: `awaitingQuery` has no `enabled:` tied to `segment`, and has
    `placeholderData`.
  - S-11c: undefined-data renders no `0` (sentinel branch present).
  - S-11d: no `CountBadge` / `--neg` / new hex literal on this screen; count
    text uses `fonts.data` (not a hardcoded family, not `fonts.mono`).
  - S-11e: count numeral fontSize ≥ 11.
  - S-11f: `matches.segment.mutual`, `matches.segment.awaiting`,
    `matches.league-chip.` all still present.
- `mobile/scripts/testid-lint.sh` and `npx tsc --noEmit` green.

### Code-walk proof (race-shaped behavior, per D-056)

- **CW-1** (build deliverable, `qa-code-walk.md` in this folder): file:line
  commit-sequence trace showing, for each of P1–P6: (a) where the path
  writes the cache, (b) why the written row cannot render (R-1 filter), and
  (c) for P1–P5, where tap-time `cancelQueries` additionally kills any
  in-flight read. Must also trace: (d) the **B-1 unhide ordering** — a GET
  racing the POST's commit resolves pre-commit, and the `onSuccess` clear
  runs only after the awaited invalidate's post-commit refetch, so the
  unhide never exposes a resurrected row; (e) P6's off-screen timing
  (starts after tap-time cancel — render guard is the only defense; why
  that suffices: `hiddenKeys` is component state that survives tab switches
  because tab screens stay mounted — verified, `TabNav.tsx` sets no
  `unmountOnBlur`/`freezeOnBlur`/`detachInactiveScreens`); and (f) the
  **unmounted-tab dual** (NB-4): if the screen ever *were* unmounted, the
  unmount cleanup flushes the POST first (`:374-377`), so lost `hiddenKeys`
  state is harmless — the row is being retracted and `onMutate` re-filters
  the cache. The proof must not rest on today's navigation config alone.

### Operator TestFlight checklist (runtime proof — the only runtime gate)

1. **#334 race repro, concrete:** Matches → Awaiting with ≥2 tiles →
   pull-to-refresh and, **while the spinner is still visible**, dismiss a
   tile → it vanishes instantly and never reappears; watch a full 10s
   (undo window + round-trip). Toast shows Dismissed/Undo ~5s.
   (Pre-fix on the current build this same sequence should resurrect the
   tile; if it won't repro, note it in the ship record — the fix stands as a
   correctness repair, race proven from code.)
2. Dismiss → tap Undo within 5s → tile returns instantly; still present
   after a pull-to-refresh (never retracted server-side).
3. Dismiss → let the window lapse → pull-to-refresh → tile stays gone
   (server retraction end-to-end).
4. Dismiss → immediately switch tabs → return → tile gone (flush-on-unmount
   / pending state held across the switch).
5. Airplane mode → Dismiss → window lapses → POST fails → tile honestly
   reappears with "Could not dismiss — try again".
6. Repeat step 1 on **Mutual**, racing the tab re-tap prefetch: leave
   Matches, re-tap the Matches tab and dismiss immediately on landing.
7. **#335:** on landing, counts show next to both segments and every chip
   **without** opening the Awaiting segment; toggling segments/chips keeps
   count = visible tiles; a league with zero shows `0`; a still-loading list
   shows no count rather than `0`.
8. Dismiss decrements the segment + chip count in the same frame the tile
   leaves; Undo restores both. Narrow device (SE-class): pill row and chip
   row don't wrap or clip the count.

---

## §V — Verification appendix (author, 2026-08-16, against `origin/main @ 0b2dcee`)

**Confirmed:** tap-time optimistic removal + delayed POST mechanism
(`:379-452`); zero `cancelQueries` in `MatchesScreen.tsx` (repo-wide grep:
only `PickAssignmentScreen.tsx:459`); all six repopulation paths above and
**no others** (`refetchOnWindowFocus: false`; no `refetchInterval`; no broad
invalidations on these keys); `ux.swipe_undo: true`
(`config/features.json:117`); backend suppression correct and untouched
(`database.py:4648/6798/7090/7247`, route `server.py:13254`); #318 wire
contract (`trades.ts:562-588`); single-slot `pendingDismissRef` justifying
the Set; `matches_awaiting` per-league only (`league.ts:172-173`);
`check-awaiting-dismiss.js` = 21 assertions (S-6…S-9); ScorePill/CountBadge/
mono-count conventions (`components.md:34/37/81` + § Tier bins); 11px floor
(`design-system.md:107`); server-fired `awaiting_trade_dismissed`
(`server.py:13320`, taxonomy `analytics_taxonomy.py:433`); D-056 verbatim.

**Failed / corrected verifications (documented, not silently patched):**
1. **Plan base label:** cites say "verified at d3fe3ac" but match
   `0b2dcee` (+76-line guide-v2 shift in `MatchesScreen.tsx`). Substance
   identical at both; this PRD re-anchors to `0b2dcee`.
2. **P6 is a repopulation path the plan under-weighted:** guide-v2's
   `TradesScreen.tsx:3322-3325` `fetchQuery` writes `['awaiting-trades']`
   from another tab. The plan's risk table mentions it only as a
   cancellation risk; CW-1 must prove the render guard covers it.
3. **"Unit (jest)"** — no jest harness exists in `mobile/` (no dependency,
   no config); corrected to the transpile-under-node idiom.
4. **`fonts.mono`** does not exist — corrected to `fonts.data`
   (`chalkline.ts:93`).
5. Cosmetic: plan's "S-2/S-6 pins" — the suite's sabotages are S-6…S-9 (no
   S-2); plan's `server.py:13266` — route decorator is at `:13254`.

None of these upgrade the path: still client-only, no new API fields, Polish.

**Round 1 incorporation (2026-08-16, [`review-round-1.md`](review-round-1.md)
→ [`reconciliation-log.md`](reconciliation-log.md)):** B-1 adopted — R-2 now
specifies the ordered unhide (`onError` immediate; `onSuccess` after awaited
invalidate) and the original "backend filter makes it impossible" rationale
is retracted as mechanically wrong; S-10c pins the ordering with the
"unhide before await" sabotage. NB-1 (P6 consequence corrected —
`v2ShowN61(false)` shows now, verified `TradesScreen.tsx:3252-3268`), NB-2/
NB-3 (R-4 edge declarations), NB-4 (CW-1 unmounted dual), NB-5 (S-10e pin;
focusManager bridge verified `App.tsx:211-216`) all incorporated. NB-6:
half-accepted — `match_dismiss_undone` is `MatchesScreen.tsx:365` (scope.md
fixed); half-**rejected with evidence** — `fonts` spans `chalkline.ts:86-95`
and `data:` is at `:93` as this PRD cites (critic's `:92` is `uiBold`).
