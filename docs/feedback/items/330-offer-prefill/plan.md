# #330 — Offer prefill + auto-run — build plan (G4, 2026-08-16 wave)

> Phase-1 plan for group G4. Base: `origin/main` @ `d3fe3ac` (v1.13.4).
> Batch context: [`../304-positional-need-filter/batch-plan.md`](../304-positional-need-filter/batch-plan.md).
> Plan only — no production code was written. All file:line references are
> against `origin/main` @ `d3fe3ac`.

**Report (mattmurf77, v1.13.3, LeagueRankings):** tapping **Offer** in the
league-rankings drill-in should land on Find a Trade with the team being
offered to and the offered player prefilled, and the search should run
immediately — no "Find a Trade" tap, first found trade visible.

**Operator decisions (binding, chat 2026-08-16):**

1. The offered player is a **hard lock** — appears in every suggested trade,
   not a preference.
2. Zero results for the scoped search (that team + that player) → an
   **honest empty state with a link back to the league summary page**.
   Never silently relax the constraints.

## 1. Current-behavior trace

The Offer/Target row actions are the #300 handoff (flags
`league.pos_candidates` + `league.player_trade_handoff`, both shipped ON —
`mobile/src/screens/LeagueSummaryScreen.tsx:599-601`,
`config/features.json:150-151`).

**What happens on tap** — `handleRowAction`
(`mobile/src/screens/LeagueSummaryScreen.tsx:1155-1176`):

1. Builds a `Player` from the tapped `PowerRankedPlayer`, tracks
   `league_candidate_pinned`.
2. Pins via the zustand store: `store.setSide('give', [player])` /
   `setSide('receive', ...)` (`useFinderTargets`,
   `mobile/src/state/useFinderTargets.ts:41-58`). REPLACE semantics; the
   store self-clears on league switch (`useFinderTargets.ts:60-73`).
3. `navigation.navigate('Trades', { screen: 'TradesHome' })` — **no team, no
   run**. The `selected` counterparty team is in scope at the call site
   (`LeagueSummaryScreen.tsx:1033-1042` decides the verb from it) but is
   never passed.

**Why the team can't be prefilled today** — under `trades.sheet_targeting`
(shipped ON, `config/features.json:188`) the scoped opponent's only source is
`sheetOpponent`, a `useState` **local to TradesScreen**
(`mobile/src/screens/TradesScreen.tsx:595-597`), consumed as
`scopedOpponent` (`TradesScreen.tsx:613-620`) → `opponent_user_id` in the
generate payload (`TradesScreen.tsx:1394`). Route params are ignored while
the flag is ON — the comment at `LeagueSummaryScreen.tsx:1123-1129` says so
explicitly ("THE PIN STORE IS THE ONLY PRESELECTION CONTRACT THAT WORKS").
There is no external setter, so no caller anywhere can prescope a team.

**Why nothing auto-runs** — generation only starts from `handleFindTrades`
(`TradesScreen.tsx:834-847`), the in-place team-pick effect
(`TradesScreen.tsx:2176-2190`, gated on `finderScopeSeen.current` so a fresh
mount never fires it), or the onboarding first-run auto-start. A store-pin
handoff triggers none of them.

**What the user actually lands on** — with exactly one give pin and
`trade.asset_ideas` ON, the `singlePin` derivation
(`TradesScreen.tsx:1173-1180`) swaps the deck slot for the
FeaturedTradeWindow/asset-ideas surface (#286/#298) — an
Upgrade/Lateral/Downgrade sweep that is **not scoped to the offered team**
and is not the deck. No team shown, no deck run: the reported experience.

**Zero-result behavior today** — a complete job with 0 cards produces only a
toast (`TradesScreen.tsx:1408-1427`) and the deck slot falls through to the
never-searched card ("Hit \"Find a Trade\" to start",
`TradesScreen.tsx:5782`) — dishonest for a search the user never manually
started, and no route back to the league summary.

## 2. Param contract for the prefill

**Reuse the pin store — extend `useFinderTargets`, do not invent a route-param
channel** (route params are dead under `trades.sheet_targeting`; prior art
#250/#269 moved the opponent source to sheet state, #300 moved player
preselection to the store).

New store fields (`mobile/src/state/useFinderTargets.ts`):

```ts
/** #330 — one-shot handoff from the league-rankings Offer/Target actions.
 *  Consumed (and nulled) by TradesScreen; cleared on league switch with
 *  the pins. */
handoff: { opponent: { userId: string; name: string }; autoRun: true } | null;
setHandoff: (h: FinderTargetsState['handoff']) => void;
```

- `opponent` uses the exact `{ userId, name }` shape `sheetOpponent` already
  holds (`TradesScreen.tsx:595-597`) — TradesScreen consumes it by calling
  its existing `setSheetOpponent`, so everything downstream
  (`scopedOpponent` → `opponent_user_id`, the #269 sheet's "Trade with" row,
  the #270 "Trading with" pill) lights up with zero new plumbing.
- One-shot: TradesScreen nulls it on consume. `clear()` and the league-switch
  subscription also null it.
- Player prefill contract is **unchanged**: `setSide` as today
  (`LeagueSummaryScreen.tsx:1171-1172`).

`handleRowAction` change (`LeagueSummaryScreen.tsx:1155-1176`): after the
`setSide` calls, `store.setHandoff({ opponent: { userId:
selected.tc.team.user_id, name: selected.tc.team.display_name ||
selected.tc.team.username || selected.tc.team.user_id }, autoRun: true })`
(name fallback chain copied from `focusedTeamName`,
`LeagueSummaryScreen.tsx:1180-1185`). Add `selected` to the callback's dep
array — it is not there today (`LeagueSummaryScreen.tsx:1175`).

Both verbs get the scoping: for **Offer** the counterparty is the drilled-in
team the player is offered to; for **Target** the pinned receive player is on
that same team, so scoping `opponent_user_id` to it is a no-op on results but
makes the "Trading with" UI truthful. One code path, symmetric.

## 3. Auto-run — client-only, no backend change

TradesScreen consumes the handoff in a focus-scoped effect (subscribe to
`useFinderTargets((s) => s.handoff)` so an **already-mounted** TradesScreen
reacts — the Trades tab usually is mounted):

1. `setSheetOpponent(handoff.opponent)`; arm `autoRunPendingRef`; null the
   store's `handoff`.
2. Dispatch through **one** choke point: extend the existing scoped-opponent
   effect (`TradesScreen.tsx:2176-2190`) — when `autoRunPendingRef.current`
   is set, generate even on the first observation (`!finderScopeSeen.current`)
   and clear the ref. This reuses the effect's existing
   `resetDeckForNewTargets()` + prefs-nudge clearing and guarantees exactly
   one generation per handoff (the effect already fires on the
   `scopedOpponent` change we just caused — the ref only widens its gate for
   the fresh-mount case; it must never produce a second `mutate`).
3. Analytics: route the dispatch so `find_trades_tapped` carries
   `source: 'league_offer'` — both props (`source`, `mode`) are already
   registered (`backend/analytics_taxonomy.py:523`), so **no taxonomy edit
   and no backend file touched**.

The generate payload needs nothing new: `pinned_give_players` +
`opponent_user_id` are existing fields (`TradesScreen.tsx:1380-1394`;
`backend/server.py:9882-9893`). "See the first found trade" is the deck's
normal streaming behavior once the job starts; per #298, once the deck lands
it takes the slot from the single-pin featured window
(`TradesScreen.tsx:1191-1203`) — auto-run therefore also fixes the
featured-window hijack described in §1. This is an explicit user intent (the
Offer tap), not an automatic snap-back, so it does not violate #298
assertion 7.

## 4. Hard-lock semantics — already the backend contract, verify, don't build

`pinned_give_players: [X]` means the give side must include **at least one
of** the pinned set (`backend/trade_service.py:2348-2350`; enforced at
`trade_service.py:3405-3411` v2 and `3824-3826` v3) — with exactly one pin
that *is* a hard lock: X is in every card. Same for a single
`pinned_receive_players` pin (`pinned_recv_set`, `trade_service.py:3410-3411`).
`pinned_give_mode` is irrelevant at one pin (`backend/server.py:9890-9893`
normalizes it away). The #189 relaxed targeted pass re-runs with the same
kwargs, so the pin and the opponent scope survive relaxation (verified for
#250 — `docs/feedback/items/250-team-targeting/status.md` §"Surfaces
audited"). **Build step: a written code-walk proof re-confirming both, plus a
backend unit assert if one doesn't already exist in
`backend/tests/test_finder_targeting.py` — read-only w.r.t. backend source.**

Never relax: no client code path may drop the pin or the opponent scope in
response to zero results. The empty state's only actions are navigation and
manual, visible edits (the #269 sheet remains reachable).

## 5. Honest empty state

**Trigger:** a handoff-originated search (ref survives until the job
resolves) completes — instant `onSuccess` complete (`TradesScreen.tsx:1408`)
**or** polled completion — with `job.cards.length === 0`. Rendered in the
deck slot with priority over the never-searched card, alongside the P0-2
failure card's branch (`TradesScreen.tsx:5761-5789`); suppress the generic
zero-result toast (`TradesScreen.tsx:1418-1426`) for this case so the card is
the single surface. State: extend the deck-slot state machine with e.g.
`scopedEmpty: { playerName, teamName } | null`, cleared everywhere
`deckFailure` is cleared (search start, league switch, retry).

**Copy (Chalkline tone — plain, honest, no emoji, decision first):**

- Title: `No trade found`
- Body: `We couldn't build a trade that sends {player} to {team} under your
  current settings. Nothing was hidden — there's no deal that works right
  now.`
- Primary action (Button, secondary variant, testID
  `trades.scoped-empty.back`): `Back to league rankings` →
  `navigation.navigate('League', { screen: 'LeagueRankings' })` (tab-root
  registration, `mobile/src/navigation/TabNav.tsx:451-455`; navigate bubbles
  from the Trades stack to the tab navigator).

The offered player stays pinned and the team stays scoped after the empty
state — returning to Trades shows the same honest scope, editable through
the existing sheet ("Trade with" tap-again-to-clear, pin chips).

## 6. Flag / gating posture

No new flag. The whole behavior change is reachable only through the
Offer/Target actions gated by `league.player_trade_handoff` (kill switch
already exists); the TradesScreen consumption path is inert unless the store
handoff is set. Record this in the scope block as the gating decision.

## 7. Risks

- **Double-generation** — the handoff consume changes `scopedOpponent`,
  whose effect can itself generate. Mitigated by routing all dispatch through
  that one effect (§3.2); the structural check pins "exactly one
  `generateMutation.mutate` site gains the auto-run ref".
- **`trades_home_inline` experiment (#270/#272)** — strip/canvas variants
  restyle the guided landing (`TradesScreen.tsx:566-580`). The deck slot is
  shared, but build must verify the handoff lands correctly under all three
  variants (the reporter is likely an assigned unit).
- **Server job cache** — a repeat Offer tap re-uses a warm complete job
  (fine: instant deck). Verify the cache key covers `opponent_user_id` +
  pins so a prior unscoped deck can never be returned for a scoped request;
  if not, send `force: true` on the auto-run path.
- **G6 interplay (batch-plan §G6)** — G6's presentment gates (#304
  positional-need, #340/#341/#339 construction) filter the same deck this
  auto-run consumes, making scoped zero-results more common — the honest
  empty state is load-bearing. **Open question for G6/operator:** should an
  explicitly pinned + team-scoped search bypass the #304 eligibility filter
  (the user asked for exactly this trade shape, analogous to the Q21
  likes-you exemption)? Default if unanswered: no bypass; the empty state
  carries the honesty.
- **Stale `selected` in the callback** — dep array fix (§2) is required, or
  the handoff could scope to a previously drilled team.
- **Legacy root-stack `LeagueSummary` variant** (deep-link entry,
  `LeagueSummaryScreen.tsx:160-165`) shares `handleRowAction`; the empty
  state's link targets the League tab root regardless of origin — accepted
  (operator asked for "the league summary page", and the tab root is its
  canonical home).

## 8. File ownership (disjoint from G6's backend files)

| File | Change |
|---|---|
| `mobile/src/state/useFinderTargets.ts` | `handoff` field + setter; clear on `clear()`/league switch |
| `mobile/src/screens/LeagueSummaryScreen.tsx` | `handleRowAction` sets handoff; dep-array fix |
| `mobile/src/screens/TradesScreen.tsx` | consume handoff; auto-run gate in the scoped-opponent effect; `scopedEmpty` state + card; toast suppression |
| `mobile/tests/check-offer-prefill-330.js` | new structural suite |
| `mobile/tests/` (unit) | store unit tests (see §9) |
| `docs/feedback/items/330-offer-prefill/*` | scope block, status, QA checklist |

Docs table: `docs/api-reference.md` n/a (no route or payload-shape change —
existing fields only); `docs/cross-client-invariants.md` n/a;
`living-memory/LLD.md` — one line: the finder preselection contract
(store, not params) now also carries the opponent + auto-run intent.
Backend files: **none** (G6 owns `backend/trade_service.py` /
`backend/server.py`; §4's proof is read-only; a new assert in
`backend/tests/test_finder_targeting.py`, if needed, must be coordinated
with G6's test ownership before touching it — default is to keep the proof
as a written code-walk only).

## 9. Test plan (D-056 — Maestro retired)

**Unit (jest / node):**
- `useFinderTargets`: `setHandoff` stores; `clear()` nulls it; league-switch
  subscription nulls it with the pins; `setSide` REPLACE semantics untouched.

**Structural (`mobile/tests/check-offer-prefill-330.js`):**
1. `handleRowAction` calls `setHandoff` with `selected.tc.team.user_id` and
   includes `selected` in its dep array.
2. TradesScreen consumes `handoff` exactly once (nulls it) and routes
   dispatch through the scoped-opponent effect; no second `mutate` call is
   introduced.
3. The auto-run dispatch emits `find_trades_tapped` with
   `source: 'league_offer'` (props already registered — cross-check against
   `backend/analytics_taxonomy.py` the way `check-league-candidates-300.js`
   §1 cross-checks flags).
4. Empty-state card exists with testID `trades.scoped-empty.back` navigating
   to `{ screen: 'LeagueRankings' }`, and no code path clears
   `pinnedGive`/`sheetOpponent` on a zero-card completion (never-relax).

**Code-walk proofs (written into status.md):** single-pin hard-lock semantics
(§4); relaxed-pass constraint survival; cache-key coverage (§7).

**Operator TestFlight checklist:**
1. League tab → single-position filter → drill into a team below the line →
   tap Offer on one of your players → lands on Find a Trade with that team
   in "Trading with" and the player pinned, search already running.
2. Every resulting card gives that exact player to that exact team.
3. Pick a pairing with no plausible deal → empty state appears (no bare
   "Hit Find a Trade" card, no toast-only), link returns to league rankings.
4. Repeat via Target on the drilled team's roster — receive-side mirror.
5. Sheet "Trade with" tap-again-to-clear still works after a handoff; league
   switch drops pin + scope.
