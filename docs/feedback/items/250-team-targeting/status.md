# #250 — Specific-Team acquire options limited to target roster

**Screen:** TradeDeck (TradesScreen in `mode:'team'`)
**Report:** "Acquire options when doing a specific team trade should only list players from that team."
**Status:** Fixed 2026-08-05 (branch `teardown-remediation`, worktree agent-a0d2eb20f30acda42)

## Root cause

The Trade-Finding Hub's Specific Team mode opens TradeDeck with
`mode:'team'` + `opponentUserId`. The deck job itself was correctly scoped —
but two acquire-side surfaces ignored the scope entirely:

1. **Acquire target picker (client).** `TradesScreen.tsx` renders the
   "Target players" section in team mode (the non-player-mode branch of the
   FB-47 targeting section), and its `targetPickerPool` memo built the
   `'acquire'` pool as `[...ownerByPlayerId.keys()]` — **every leaguemate's
   roster**. `scopedOpponent` was never consulted, so "Target players to
   acquire" listed the whole league. (The pool logic predates #156 team
   mode: its comment even said "Acquire → every LEAGUEMATE roster".)

2. **Asset-ideas surface (backend + client).** With exactly one pin, the
   `singlePin` gate (which never checks `finderMode`) replaces the deck with
   the featured-trade window + Upgrade/Lateral/Downgrade list (#216/#241).
   `POST /api/trades/asset-ideas` → `TradeService.generate_asset_ideas`
   swept **all** `league.members` — the route accepted no opponent scope and
   the client sent none. So in team mode with one pin, every "acquire"
   package could come from any team.

Surfaces audited and found already correct (no change):

- **Deck generation** — `generate_trades` / `_generate_trades_v2` both filter
  `eligible` to `opponent_user_id`; the #189 `_relaxed_targeted_pass` reruns
  with the same kwargs, so the scope survives relaxation.
- **Eveners / Swap suggestions / #194 remove-asset repricing** — all go
  through `/api/trade/evaluate` Mode B with the card's `opponent_user_id`;
  receive-side eveners are built by `_roster_eveners(league_id, owner)` where
  owner is that opponent (one-sided reads included).

## Fix

Backend (targeting/pool code only — no crown/package-adjustment math touched):

- `backend/trade_service.py` `generate_asset_ideas(...)`: new optional
  `opponent_user_id` param. Give direction filters the counterparty sweep to
  that member; receive direction returns empty groups when the pin's owner is
  not the scoped opponent (never off-team acquire ideas).
- `backend/server.py` `/api/trades/asset-ideas`: reads optional body
  `opponent_user_id` and passes it through (docstring updated).

Client (`mobile/`):

- `src/api/trades.ts` `fetchAssetIdeas`: optional `opponent_user_id` field.
- `src/screens/TradesScreen.tsx`:
  - `assetIdeasQuery` sends `opponent_user_id: scopedOpponent` in team mode
    (and keys the query on it, so an in-place team switch refetches).
  - `targetPickerPool`: `'acquire'` direction draws from
    `rosterByOwner.get(scopedOpponent)` when a team is scoped; trade-away
    (own roster) and all non-team modes are unchanged.

Scope guard: `scopedOpponent` is only ever defined when
`finderMode === 'team'`, so guided / player / classic launches produce
byte-identical requests and picker pools.

## Verification

- **Backend regression tests** (`backend/tests/test_asset_ideas.py`, +3):
  - `test_give_direction_scoped_to_opponent` — two-opponent league; unscoped
    sweep returns both counterparties, scoped sweep returns only the target
    team with only its players on the receive side.
  - `test_receive_direction_scope_mismatch_returns_empty` — a pin owned by a
    non-scoped member yields empty groups; matching scope equals unscoped.
  - `test_route_passes_opponent_scope` — body `opponent_user_id` threads
    through the route (off-team scope ⇒ empty groups).
  - All three **failed before the fix** (service: unexpected-kwarg TypeError;
    route: off-team scope still returned ideas) and pass after.
- Full suite: `python3 -m pytest backend/tests -q` → **1423 passed, 1
  skipped** (baseline 1420 + 3 new).
- `npx tsc --noEmit` in `mobile/` → clean.
- Manual (client-side picker filtering, no unit harness for the memo):
  1. Hub → Specific Team → pick a manager → deck opens in team mode.
  2. Controls card → direction "Acquire" → Add player: the picker should list
     ONLY that manager's players (every row badge reads the same `@owner`).
  3. Switch direction to "Trade away": your full roster still listed.
  4. Pin exactly one of their players (acquire) → featured window + "More
     trades": every idea's counterparty is the scoped manager.
  5. Mode-bar Team chip → pick a different manager: ideas refetch for the new
     team; picker pool follows.
  6. Switch to Specific Player / Guided mode: acquire picker lists the whole
     league again (unchanged behavior).

## Known edge (pre-existing, out of scope)

Pins created in another mode (or for a previous team) persist in
`useFinderTargets` when entering/switching team scope. An off-team acquire
pin now honestly yields empty idea groups instead of off-team packages; the
picker fix prevents creating new off-team pins while scoped. Auto-clearing
stale pins on scope change was not in the report and is left alone.
