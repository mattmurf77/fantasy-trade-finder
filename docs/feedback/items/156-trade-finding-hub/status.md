# #156 — Trade-Finding Hub · status

**State:** Built (flag-dark), tests green. Branch: `teardown-remediation`.
**Variant:** B — Launcher Hub (operator-approved). Mockup:
`mockups/trade-finding-hub/variant-b-launcher-hub.html`.
**Flag:** `trades.finder_hub` — **default false** (justification below).

## What shipped, per mode

The Trades-tab home becomes a mode launcher (`TradeFinderHubScreen`) with a
**Trade DNA** panel + four launcher cards. Each deck mode opens the `TradeDeck`
route (a re-entry of the existing `TradesScreen`) carrying a lateral
quick-switch chip row (`TradeFinderModeBar`) so modes swap in place.

| Mode | How it works | Reused vs new |
|---|---|---|
| **Fully Guided** | `TradeDeck` with `mode:'guided'` → the existing deck/generation flow | 100% reuse (`TradesScreen`) |
| **Specific Player** | `TradeDeck` with `mode:'player'` → the FB-47 for/away targeting board (`pinned_give`/`pinned_receive` + Target-players controls) already in `TradesScreen` | Reuse FB-47 (flag `trade.finder_targeting`, already ON) |
| **Specific Team** | Hub manager-picker sheet → `TradeDeck` with `mode:'team'` + `opponentUserId`; `TradesScreen` threads `opponent_user_id` into `/api/trades/generate`, which scopes the sweep to that one league-mate | **New** small backend param (below) + picker UI |
| **Manual Calculator** | `navigate('TradeCalculator')` | 100% reuse (`TradeCalculatorScreen`) |

**Trade DNA panel** — outlook (`OutlookSheet` for "Edit prefs"), untouchables
count (FB-95 `asset_prefs`), Chasing/Shopping position chips
(`acquire_positions`/`trade_away_positions` — the OutlookSheet chips), plus
**recommendation chips** ("need"/"deep") from the roster's
`position_needs`/`position_surplus`.

## New backend (thin, additive)

1. **Needs/surplus on the prefs response** — `GET /api/league/preferences` now
   always returns `position_needs` + `position_surplus` (from the existing
   `analyze_roster_strengths`, scoped to the session roster like
   `inferred_outlook`; best-effort). Chosen over a new endpoint so the hub
   reuses its existing prefs query with **zero** new client call.
2. **Specific Team scope** — new `opponent_user_id` param threaded
   `generate route → _kickoff_trade_job → _run_trade_job →
   trade_service.generate_trades → _generate_trades_v2` (+ legacy path);
   filters the `eligible` opponent list to one member. Opponent-scoped jobs
   bypass the shared cache and skip likes-you injection (like pinned jobs).
   All additive-with-default → byte-identical when unset.

## Reused, NOT rebuilt

FB-47 finder targeting (Specific Player), the deck/generation flow (Guided),
`TradeCalculatorScreen` (Calculator), `OutlookSheet` (Edit prefs / DNA),
FB-95 `asset_prefs` (untouchables), `analyze_roster_strengths` (recommendation
chips), the RankHome card-launcher pattern.

## Flag default = **false** (justification)

- Repo convention: teardown-branch flags default false (byte-identical when off).
- `onboarding.trades_first` first-run flow **auto-generates on the deck as the
  Trades home**; a default-ON hub would displace that reviewed onboarding path.
- Large new surface — validate before default-on. Backend additions are always
  live and harmless when unused, so flipping the flag later needs no backend change.

## Verification

- `cd mobile && npx tsc --noEmit` — clean.
- `python3 -m pytest backend/tests/ -q` — 967 passed (incl. new
  `test_opponent_scope_limits_generation_to_one_leaguemate` in
  `test_trade_phase2.py`; `release.json` mirror fixture updated for the new flag).

## Deferred / notes

- Specific Player reuses the existing single-column FB-47 direction-toggle
  board rather than the mockup's two-column FOR/AWAY board — functional parity
  (both-side pinning works); two-column visual is polish, not wired.
- The "require both sides in every package" toggle from the mockup is not
  implemented as a hard backend constraint (pinning both sides already works).
- The finder-card verdict value bar (shared `TradeValueBar`, another agent's
  component) is **not** wired — `TradeCard.tsx` was left untouched.
- Live pin-count summary on the hub's Specific Player card is static copy (pins
  live in `TradesScreen` session state, not readable from the hub).
- Mode-switch persistence: Guided/Player switch in place (setParams) so pinned
  targets persist; changing team scope re-navigates and resets the deck.

## Files

Backend: `backend/server.py`, `backend/trade_service.py`,
`backend/feature_flags.py`, `config/features.json`,
`backend/tests/fixtures/flags/release.json`,
`backend/tests/test_trade_phase2.py`.
Mobile: `mobile/src/screens/TradeFinderHubScreen.tsx` (new),
`mobile/src/components/TradeFinderModeBar.tsx` (new),
`mobile/src/screens/TradesScreen.tsx`, `mobile/src/navigation/TabNav.tsx`,
`mobile/src/utils/deepLinks.ts`, `mobile/src/api/league.ts`,
`mobile/src/api/trades.ts`.
Docs: `docs/api-reference.md`, `docs/config-reference.md`, `docs/glossary.md`,
`docs/design/components.md`, `mobile/src/screens/CLAUDE.md`,
`mobile/src/components/CLAUDE.md`.
