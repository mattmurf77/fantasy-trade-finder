# PRD — #330 Offer prefill + auto-run (G4, 2026-08-16 wave)

> Author-phase contract for group G4, **round 2** (incorporates
> [`review-round-1.md`](review-round-1.md); dispositions in
> [`reconciliation-log.md`](reconciliation-log.md)). Companion scope block:
> [`scope.md`](scope.md). Plan: [`plan.md`](plan.md). Batch context:
> [`../304-positional-need-filter/batch-plan.md`](../304-positional-need-filter/batch-plan.md).
> No production code was written in this phase.

**Item:** #330 (mattmurf77, v1.13.3, LeagueRankings) — tapping **Offer** in the
league-rankings drill-in should land on Find a Trade with the counterparty team
scoped, the offered player prefilled, and the search already running.

**Path:** Polish. Zero backend **production** files change (disjoint from G6's
`backend/trade_service.py` / `backend/server.py` ownership). One new backend
**test** file is added per review B-4 (R-5) — flagged to the orchestrator in
scope.md; a test file is not production backend code and does not change the
path.

**Operator decisions (binding, chat 2026-08-16):**

1. The offered player is a **hard lock** — in every suggested trade, not a
   preference.
2. Zero results for the scoped search → an **honest empty state with a link
   back to the league summary page**. Never silently relax pin or scope.

## Base and verification notes

Every file:line cite below was re-verified against **`origin/main` @
`0b2dcee`**. Corrections to the plan's framing, found during verification —
none changes the design's spine:

- **Base sha.** The plan's header pins `d3fe3ac`, but its line cites actually
  match the current `origin/main` tip `0b2dcee` (`d3fe3ac` is an ancestor;
  `TradesScreen.tsx` alone moved ~536 lines between the two). All cites in
  this PRD are against `0b2dcee`. Build branches start from a freshly fetched
  `origin/main` per CLAUDE.md; the builder must re-run the structural suite
  against whatever tip it branches from.
- **Server job cache (plan §7 risk 3) — resolved, no mitigation needed.**
  Both halves verified. Lookup half: `_any_pinned` (`backend/server.py:9909`,
  true when `pinned_give_players`, `pinned_receive_players`, **or**
  `opponent_user_id` is set) makes the cache lookup skip entirely
  (`server.py:9962`), and `_trade_job_key` (`server.py:2725`) never contained
  pins or opponent. Registration half (added per review): `_kickoff_trade_job`
  computes `is_pinned` (`server.py:5446`) and only registers **unpinned** jobs
  in the per-key index (`server.py:5466-5468`), so a scoped job can never be
  served to a *future unscoped* search either. No stale path in either
  direction; do **not** send `force: true`.
- **Fairness default (corrected per review N-2):** the server's 0.50 pinned
  default (`server.py:9911`) **never applies to this flow** — mobile always
  sends an explicit `fairness_threshold: effectiveFairness`
  (`TradesScreen.tsx:812`, `:1377`). Scoped auto-runs execute at the user's
  own fairness setting (0.75 with fairness ON); no builder should assume a
  server-side wide net exists.
- **`selected` dep nuance:** today's `handleRowAction` body
  (`mobile/src/screens/LeagueSummaryScreen.tsx:1155-1176`) does not read
  `selected`, so the missing dep is inert; it becomes a live stale-closure
  bug the moment R-2's code reads `selected.tc.team`. R-2 requires the dep;
  S-1 pins it structurally.

## Requirements

### R-1 — One-shot `handoff` extension to `useFinderTargets`, with a monotonic `seq`

`mobile/src/state/useFinderTargets.ts` gains:

```ts
handoff: {
  seq: number;   // monotonic, stamped by setHandoff on every call
  opponent: { userId: string; name: string };
  autoRun: true;
} | null;
/** Stamps seq internally — callers never supply it. */
setHandoff: (h: { opponent: { userId: string; name: string }; autoRun: true } | null) => void;
```

- **Shape:** `opponent` is exactly the `{ userId, name }` shape TradesScreen's
  `sheetOpponent` state already holds (`TradesScreen.tsx:596-598`), so
  consumption is a plain `setSheetOpponent(handoff.opponent)`.
- **`seq` (review B-1):** a store-internal counter, incremented on every
  non-null `setHandoff`. It exists because `scopedOpponent` is a derived
  **string** (`sheetOpponent?.userId`, `TradesScreen.tsx:613-614`): a repeat
  Offer to the *same* team changes no dep the choke-point effect watches, so
  without a per-handoff nonce the second handoff would never auto-run (the
  original #330 symptom reborn). R-3 threads `seq` into that effect's deps.
- **Lifecycle (one-shot):** set only by `handleRowAction` (R-2); consumed and
  **nulled** by TradesScreen (R-3). An **un-consumed** handoff (e.g. the user
  never visits the Trades tab) simply persists until it is consumed, cleared
  by `clear()`, or garbage-collected by the league-switch/sign-out
  subscription — no timeout (review N-3).
- **When it clears:** (a) on consume (R-3 step 1); (b) in `clear()`; (c) via
  the existing module-level league-switch subscription that already clears
  pins (`useFinderTargets.ts:63-76`). Initial value `null`. The seq counter
  itself never resets (monotonic for the session).
- `setSide` REPLACE semantics and `packageMode` behavior are untouched.

*Maps to:* #330 prefill. *Tests:* U-1, U-2, U-3, S-2.

### R-2 — `handleRowAction` sets the handoff (and its dep array gains `selected`)

In `mobile/src/screens/LeagueSummaryScreen.tsx` `handleRowAction`
(`:1155-1176`), after the existing `setSide` calls (`:1171-1172`):

```ts
store.setHandoff({
  opponent: {
    userId: selected.tc.team.user_id,
    name: selected.tc.team.display_name ||
          selected.tc.team.username || selected.tc.team.user_id,
  },
  autoRun: true,
});
```

- Name fallback chain is copied verbatim from `focusedTeamName`
  (`:1199-1203`).
- `selected` **must** be added to the callback's dep array (today
  `[navigation, candidatePos, candidateDir, selectedIdx, route.name]`,
  `:1176`) — without it the closure captures a stale drill-in team.
- Both verbs get the handoff symmetrically: **Offer** scopes to the
  drilled-in team the player is offered to; **Target** scopes to the team
  that owns the pinned receive player (a results no-op — the player pin
  already constrains the counterparty — but it makes the "Trading with" UI
  truthful). One code path, no verb branching beyond the existing
  give/receive `setSide` split.
- The route-param channel stays dead — per the on-file contract comment
  (`:1124-1129`), route params are ignored while `trades.sheet_targeting` is
  ON (`config/features.json:188`); the store is the only preselection
  contract.

*Maps to:* #330 prefill (team half). *Tests:* S-1, T-1, T-4.

### R-3 — TradesScreen consumption: exactly ONE deck generation per handoff, including same-team repeats

Consumption is **focus-gated** (review N-3): a TradesScreen effect gated on
screen focus (`isFocused` or a focus listener) — not a raw store
subscription — consumes the handoff. `navigation.navigate` in R-2 focuses
Trades immediately after `setHandoff`, so consumption is prompt and
cold-mount ordering is deterministic; an already-mounted Trades tab consumes
on refocus. On a non-null handoff, the effect:

1. Calls `setSheetOpponent(handoff.opponent)` (state at
   `TradesScreen.tsx:596-598`, feeding `scopedOpponent` `:613-620` →
   `opponent_user_id` in the generate payload `:1395`); records
   `handoff.seq` into local state (`autoRunSeq`); arms `autoRunPendingRef`;
   nulls the store's `handoff`. **Flag matrix (review N-3):** if
   `trades.finder_hub` is OFF or `finderMode` is absent — the choke-point
   effect early-returns in that state — the ref is **not armed** (and
   `autoRunSeq` not bumped): the handoff degrades to prefill-without-autorun
   instead of leaving an armed ref to detonate later. See R-8.
2. Dispatches through **one choke point**: the existing scoped-opponent
   effect (`TradesScreen.tsx:2176-2190` — `finderScopeSeen` ref + effect;
   verified: gated on `finderHubOn && finderMode`, fires
   `generateMutation.mutate({})` only when `finderScopeSeen.current &&
   scopedOpponent`, and already calls `resetDeckForNewTargets()` and clears
   the #257 prefs nudge). Two changes inside it, none adding a `mutate`
   site:
   - **deps gain `autoRunSeq`** (review B-1): a repeat Offer to the same
     team changes `autoRunSeq` even though the `scopedOpponent` string is
     unchanged, so the effect re-fires, resets the old deck, and generates
     the new scoped sweep. Without this the second handoff lands its pin on
     the stale deck silently.
   - when `autoRunPendingRef.current` is set, generate even on the first
     observation (`!finderScopeSeen.current`) and clear the ref. The ref
     only widens the fresh-mount gate; combined with the seq dep it
     guarantees **exactly one generation per handoff** and **must never
     produce a second `mutate`**. No new `generateMutation.mutate` call
     site may be introduced anywhere.
3. Result: exactly one generation per Offer/Target tap, streaming into the
   deck normally. Per #298, once the deck lands it takes the slot from the
   single-pin FeaturedTradeWindow (`singlePinDeckActive`,
   `TradesScreen.tsx:1208-1209`) — auto-run therefore also fixes the
   featured-window hijack in plan §1. This is explicit user intent (the
   tap), not an automatic snap-back, so #298 assertion 7 is not violated.

Preconditions verified ON at base: `trades.finder_hub`
(`config/features.json:11`), `trades.sheet_targeting` (`:188`),
`trade.finder_targeting` (`:36`), `trade.asset_ideas` (`:55`). The handoff
consume must behave correctly under all three `trades_home_inline` variants
(control/strip/canvas, `TradesScreen.tsx:573-579`) — the deck slot is shared.

*Maps to:* #330 auto-run. *Tests:* S-2, T-1, T-2, T-6.

### R-4 — Analytics: the auto-run emits `find_trades_tapped` with `source: 'league_offer'`

The auto-run dispatch carries `source: 'league_offer'` (plus the existing
`mode` prop) on `find_trades_tapped`. **No taxonomy edit, no backend
production file touched** — verified:

- `find_trades_tapped` registers props `{source, mode}` at
  `backend/analytics_taxonomy.py:523` (`frozenset({"source", "mode"})`).
- Ingest validation is **prop-name-level**, not value-level:
  `CLIENT_EVENT_PROPS` holds prop-name frozensets; `source` carries no
  closed-enum contract (unlike e.g. `via`/`error_code` rows that are
  comment-marked CLOSED), and free-form values are already sent today
  (`'deck_error_retry'`, `TradesScreen.tsx:5776`). A new *value* of a
  registered prop is not dropped.

*Maps to:* #330 measurement. *Tests:* S-3.

### R-5 — Hard lock: executable backend assert in a NEW test file, plus the narrative proof

`pinned_give_players: [X]` with one element means X is on the give side of
**every** card — existing backend behavior, anchors below. Review B-4's
finding is accepted: a written proof alone cannot guard operator decision 1
while **G6 is concurrently rewriting the enforcing functions**
(`backend/trade_service.py` — the #340/#341/#339 construction gates land
exactly where `_consider` enforces the pin, `:3568-3576`) and lands *before*
G4 ships. Therefore:

- **New file `backend/tests/test_offer_hard_lock_330.py`** (BT-1) — G4-owned,
  colliding with no G6 file. Asserts, mirroring the existing harness in
  `backend/tests/test_finder_targeting.py` (which verifiably has **no**
  single-pin assert — every `pinned_give_players` use there is `None` or
  two-pin): single-give-pin ⇒ the pin is in every card's give side (v2 pair
  generator + v3 optimizer paths); single-receive-pin ⇒ mirror on the
  receive side. This is the executable tripwire G6's merge must keep green.
- **P-1 is demoted to the narrative companion** of BT-1 (still written into
  `status.md`), with these verified anchors:
  - Docstring contract: give side "includes at least one of these player
    IDs" (`backend/trade_service.py:2348-2350`); with exactly one pin,
    ≥1-of ⇒ the pin is in every card.
  - v2: sets at `:3405-3411`; enforcement `:3569-3575`. v3: `:3854-3857`,
    `:3872-3873`, `:3885`. Consensus: `:3824-3826`, `:4161`, `:4210`,
    `:4255`, `:4321`.
  - `pinned_give_mode` irrelevant at one pin — `backend/server.py:9887-9894`
    normalizes to `"any"` unless 2+ pins and an explicit `"all"`.
  - #189 relaxed targeted pass widens only the fairness band and surplus
    floors (`trade_service.py:156-168`); pins and `opponent_user_id` are
    re-passed unchanged (prior verification:
    `docs/feedback/items/250-team-targeting/status.md:29`). P-2 re-walks
    this.

*Maps to:* operator decision 1. *Tests:* BT-1, P-1, P-2, T-2.

### R-6 — Honest zero-result empty card, scope-based (origin-independent)

**Trigger (review B-3):** **any** trade-generation job that completes with
zero cards **while a player is pinned and an opponent is scoped**
(`pinnedGive.length + pinnedReceive.length > 0` AND `scopedOpponent` set) —
regardless of whether the handoff or a manual "Find a Trade" tap started it.
The operator's decision is about the scoped search, not which button ran it;
a manual re-run from the empty state that finds nothing again must show the
same honest card, not the old toast. The round-1 "surviving handoff ref"
mechanism is **dropped**; `scopedEmpty`'s `{ playerName, teamName }` is
derived at completion time from the pinned player and `scopedOpponentName`.

**Explicit exclusions:**

- Job **error** → the P0-2 `deckFailure` card owns that state
  (`TradesScreen.tsx:5761-5779`); `scopedEmpty` is never set on error.
- An **exhausted** scoped deck (cards existed, user swiped them all) → the
  deck-summary state, never `scopedEmpty`. Zero cards *generated* is the
  only trigger.

**Behavior:**

- Rendered in the deck slot with priority over the never-searched card
  (`"Hit \"Find a Trade\" to start"`, `TradesScreen.tsx:5781`), as a sibling
  branch of the `deckFailure` card. State: `scopedEmpty: { playerName,
  teamName } | null`, cleared everywhere `deckFailure` is cleared (search
  start, league switch, retry).
- The generic zero-result toast (`:1411-1426`) is **suppressed** whenever
  the trigger condition holds — the card is the single surface.
- **The #189 relaxed pass shapes the copy (review N-1):** a zero-card
  targeted job has *already* auto-run the server's relaxed fallback
  (fairness band widened to 0.55, surplus floors dropped; pins, scope, and
  untouchables never relaxed — `backend/trade_service.py:156-168`). The
  copy therefore must not say "under your current settings" — the server
  searched beyond them and still found nothing, which is the stronger
  honest claim. Builders: do not "fix" this copy back.
- **Copy (Chalkline tone — plain, decision first, no emoji):**
  - Title: `No trade found`
  - Body (Offer): `We couldn't build a trade that sends {player} to {team}
    — even after stretching the fairness band. Your player and team stayed
    locked.`
  - Body (Target mirror): `We couldn't build a trade that gets {player}
    from {team} — even after stretching the fairness band. Your target and
    team stayed locked.`
  - Action: `Button` secondary variant, compact, testID
    `trades.scoped-empty.back`, label `Back to league rankings` →
    `navigation.navigate('League', { screen: 'LeagueRankings' })`
    (registration verified `mobile/src/navigation/TabNav.tsx:449-453`;
    navigate bubbles from the Trades stack to the tab navigator). The link
    targets the tab root regardless of which LeagueSummary variant
    originated the handoff (legacy root-stack variant at
    `LeagueSummaryScreen.tsx:161-168`) — accepted per plan §7.

**Out of scope (pre-existing, separate task chip per review N-1b):** relaxed
cards that *do* appear in a deck carry no label — `TradeCard.tsx` and
`TradesScreen.tsx` never read `relaxed` (verified: zero grep hits; the only
label is `AssetIdeasPanel.tsx:112` "Stretch"). G4 does not absorb this.

*Maps to:* operator decision 2. *Tests:* S-4, T-3, T-7.

### R-7 — Never relax (code-walk-proof requirement)

No client code path may drop `pinnedGive`/`pinnedReceive` or clear
`sheetOpponent` in response to a zero-card completion. After the empty state,
the player stays pinned and the team stays scoped; the only ways out are
navigation (R-6's link) and manual, visible edits (the #269 sheet's "Trade
with" tap-again-to-clear and pin chips remain reachable, T-5). P-3 walks
every zero-card handler and asserts none touches pin or scope state.

*Maps to:* operator decision 2. *Tests:* S-4, P-3, T-5.

### R-8 — Gating: no new flag; kill switch = `league.player_trade_handoff`; degradation matrix

No new flag. The behavior is reachable only through the Offer/Target row
actions gated by the existing `league.player_trade_handoff` flag —
**verified:** defined and ON at `config/features.json:151`, read at
`LeagueSummaryScreen.tsx:600`; its documented OFF state ("rows carry no
action") removes the only writer of the handoff. The TradesScreen consumption
path is inert unless the store handoff is set, so flipping the flag OFF is a
complete deploy-free kill switch.

**Degradation matrix (review N-3):** with `trades.finder_hub` OFF (currently
ON, `config/features.json:11`) or no `finderMode`, the choke-point effect
early-returns, so auto-run is impossible; per R-3 step 1 the consume path
then does **not** arm `autoRunPendingRef` — the handoff degrades to
prefill-without-autorun (pins + scope set, user taps Find a Trade manually).
Acceptable degradation; no armed ref may survive it.

*Maps to:* rollback safety. *Tests:* S-2 (consumption inert on null handoff;
no ref armed when the choke point is gated off).

### R-9 — Symmetry: Target verb mirrors Offer

Everything above applies to **Target** (receive pin) with the roles mirrored;
`pinned_receive_players` single-pin enforcement is asserted by BT-1 (R-5).
Note `pinned_receive_players` is honored server-side only under
`trade.finder_targeting` (`backend/server.py:9885-9886`) — verified ON.

*Maps to:* #330 (both row actions ship together, as #300 shipped them).
*Tests:* U-1..U-3, BT-1, T-4.

### R-10 — Generation-epoch guard: an in-flight stale result can never overwrite a scoped run (review B-2)

Nothing orders two in-flight React Query mutations: an Offer tap while a
prior search is streaming would reset the deck and dispatch the scoped run,
but the **old** mutation's `onSuccess` (`setJob(snapshot)`,
`TradesScreen.tsx:1402`) can land *after* the new dispatch and resurrect the
pre-scope snapshot. The exposure pre-exists via the in-place team pick, but
auto-run makes it a first-class flow. Required:

- A monotonic **generation epoch** (ref), incremented by every
  `resetDeckForNewTargets()`.
- Every dispatch stamps the current epoch into the mutation (e.g. via
  `onMutate`/mutation variables).
- Result application (`onSuccess`/`onError`, and the polling attach for
  `running` jobs) is routed through a **pure, unit-testable helper** —
  e.g. `applyJobResult(snapshot, dispatchEpoch, currentEpoch)` — that drops
  the result entirely when the epochs differ: no `setJob`, no toast, no
  `scopedEmpty`, no `deckFailure` from a stale mutation.
- **Deterministic repro (coordinator requirement):** U-4 calls the helper
  with mismatched epochs and asserts nothing is applied — this test **fails
  without the guard**. The full async race itself is not deterministically
  reproducible at unit level; its runtime coverage is TestFlight step T-6,
  stated honestly as such.
- Scope note: two *manual* rapid "Find a Trade" taps share an epoch unless a
  reset intervenes — last-write-wins there is pre-existing behavior and out
  of G4 scope; the guard covers every path that goes through
  `resetDeckForNewTargets()` (which includes every handoff and every scope
  change).

*Maps to:* #330 auto-run correctness. *Tests:* U-4, S-5, T-6.

## Dependencies

- **Cross-group question (G6 / #304) — RESOLVED by orchestrator arbitration
  (2026-08-16, G6 review round 1):** the boundary is **targeted-vs-untargeted**.
  Any targeted job — pinned give player, scoped opponent, or explicit
  `acquire_positions` — **bypasses** G6's R-5 need gate; untargeted discovery
  decks are filtered. The bypass is derived **server-side** in `_run_trade_job`
  from job fields (never client-passable); exact field list in G6's
  `lld-delta.md`. G6's construction rules (overpay cap, net-±1, pick-gap) and
  R-4 dedup still apply to targeted jobs, including this flow. Consequence for
  G4: the #330 Offer handoff (pin + scope) will never be emptied by the need
  gate; R-6's honest empty state remains reachable via the construction rules
  and genuine no-candidate outcomes, so its spec is unchanged. This section's
  earlier "default: NO bypass" posture is superseded. G4 makes no backend
  production change either way.
- **Build order (batch-plan §Groups):** G6's backend contract lands before
  G4's auto-run ships. G4's production file set is disjoint from G6's;
  BT-1's new test file (R-5) is G4-owned and G6-neutral by construction,
  and doubles as the tripwire G6's rewrite must keep green.

## Test plan (D-056 — Maestro/simulator retired; DECISIONS.md:600)

Evidence classes per D-056: structural `check-*.js` suites + unit tests +
written code-walk proofs; runtime proof is the operator TestFlight checklist.

### Unit (jest/node)

- **U-1:** `setHandoff` stores the object and stamps a strictly increasing
  `seq` across consecutive calls (same payload twice ⇒ different seqs);
  initial `handoff` is `null`.
- **U-2:** `clear()` nulls `handoff`; the league-switch subscription nulls it
  together with the pins (simulate `useSession` league change).
- **U-3:** `setSide` REPLACE semantics and `packageMode` default are
  unchanged by the extension.
- **U-4 (fails without the R-10 guard):** the result-application helper
  drops a snapshot whose dispatch epoch ≠ current epoch — no state applied;
  applies it when equal.

### Backend pytest — new `backend/tests/test_offer_hard_lock_330.py` (BT-1)

- Single `pinned_give_players` pin ⇒ pin present in every generated card's
  give side — v2 pair-generator and v3 optimizer paths (harness mirrored
  from `test_finder_targeting.py`'s existing two-pin tests).
- Single `pinned_receive_players` pin ⇒ mirror on the receive side.
- New file only — no G6-owned file is touched.

### Structural — new `mobile/tests/check-offer-prefill-330.js`

- **S-1:** `handleRowAction` calls `setHandoff` with
  `selected.tc.team.user_id`, uses the
  `display_name || username || user_id` fallback chain, and its dep array
  contains `selected`.
- **S-2:** TradesScreen consumes `handoff` exactly once — the (focus-gated)
  consume site nulls the store field, sets `setSheetOpponent`, and dispatch
  is routed through the existing scoped-opponent effect; that effect's dep
  array contains the handoff seq (`autoRunSeq`); the file's count of
  `generateMutation.mutate` call sites does not increase over base; the
  ref-arm is guarded by the same `finderHubOn && finderMode` condition the
  choke point uses (R-8 degradation).
- **S-3:** the auto-run dispatch emits `find_trades_tapped` with
  `source: 'league_offer'`, cross-checked against
  `backend/analytics_taxonomy.py`'s registered props for the event (the
  same source-of-truth cross-check pattern
  `mobile/tests/check-league-candidates-300.js` uses for flags).
- **S-4:** the empty-state card exists with testID
  `trades.scoped-empty.back` navigating to
  `{ screen: 'LeagueRankings' }`; the zero-card handling is conditioned on
  pin-present AND opponent-scoped (never on handoff origin) and sets
  `scopedEmpty` / suppresses the toast under exactly that condition; **no**
  zero-card code path calls `setSide`, `clear`, `removeGive/Receive`, or
  `setSheetOpponent(null)` (never-relax).
- **S-5:** the generation epoch is incremented in
  `resetDeckForNewTargets()`, stamped at dispatch, and compared in the
  result-application path; result application goes through the R-10 helper.

### Written code-walk proofs (into `status.md`)

- **P-1 (narrative companion to BT-1):** single-pin hard lock — both sides,
  all three generators + mode normalization (anchors in R-5).
- **P-2:** #189 relaxed-pass constraint survival — pins and
  `opponent_user_id` re-passed unchanged into the relaxed pass.
- **P-3:** never-relax — every zero-card handler walked; none mutates pin or
  scope state. (Cache-key coverage needs no proof — resolved in §Base notes:
  pinned/scoped jobs bypass the cache in both lookup and registration,
  `server.py:9909,9962,5446,5466-5468`.)

### Operator TestFlight checklist (8 steps)

1. League tab → single-position filter → drill into a team **below** the
   line → tap **Offer** on one of your players → lands on Find a Trade with
   that team named in "Trading with" and the player pinned, search already
   running — no "Find a Trade" tap needed.
2. Every resulting card sends that exact player to that exact team (swipe
   several to confirm; hard lock, not preference).
3. Force a zero-result: with **fairness ON**, offer a junk bench piece to
   the league's strongest roster → the "No trade found" card appears — not
   the bare "Hit Find a Trade" card, not a toast-only — and its link returns
   to League rankings. (The server's relaxed pass exists to prevent exactly
   this, so expect a few tries to find a pairing that yields zero.)
4. Drill into a team **above** the line → tap **Target** on one of their
   players → mirror of step 1 with the receive side pinned; cards all
   acquire that player from that team.
5. After a handoff: open the sheet — "Trade with" tap-again-to-clear still
   works and the pin chips are editable; switch leagues → pin, scope, and
   any pending handoff are all dropped.
6. **Repeat Offer, same team (B-1/B-2):** from a scoped deck (or the empty
   state), return to rankings and Offer a *different* player **to the same
   team** → a fresh scoped search runs for the new player (the old deck
   does not survive). Also: tap Offer while a previous search is still
   spinning → the deck that lands is the scoped one, never the older
   league-wide sweep.
7. **Manual re-run honesty (B-3):** from the empty state, open the sheet,
   change nothing, tap Find a Trade manually → zero results again shows the
   same "No trade found" card, not the old toast.
8. Confirm the auto-run deck's cards look sane (no unlabeled nonsense) —
   note for context: relaxed "stretch" cards are unlabeled in the deck
   today; that gap is tracked separately, not part of this checklist's
   pass/fail.

## Traceability

| Req | Feedback | Tests |
|---|---|---|
| R-1 | #330 | U-1, U-2, U-3, S-2 |
| R-2 | #330 | S-1, T-1, T-4 |
| R-3 | #330 | S-2, T-1, T-2, T-6 |
| R-4 | #330 | S-3 |
| R-5 | #330 / operator decision 1 | BT-1, P-1, P-2, T-2 |
| R-6 | #330 / operator decision 2 | S-4, T-3, T-7 |
| R-7 | #330 / operator decision 2 | S-4, P-3, T-5 |
| R-8 | #330 | S-2 |
| R-9 | #330 | U-1..U-3, BT-1, T-4 |
| R-10 | #330 | U-4, S-5, T-6 |
