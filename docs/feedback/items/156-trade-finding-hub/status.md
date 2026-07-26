# #156 — Trade-Finding Hub · status

**State:** FINISHED + **flag flipped ON** (2026-07-25, operator-approved).
Branch: `teardown-remediation`.
**Variant:** B — Launcher Hub (operator-approved). Mockup:
`mockups/trade-finding-hub/variant-b-launcher-hub.html`.
**Flag:** `trades.finder_hub` — **true** in `config/features.json` +
`backend/tests/fixtures/flags/release.json` (was default-false; see the
original justification below, now superseded by the finish batch).

## Finish batch (2026-07-25)

Everything in the "Deferred / notes" list below that the operator approved
is now built:

1. **Two-column FOR/AWAY board (item 1)** — Specific Player mode
   (`TradeDeck` with `mode:'player'`) renders the mockup's two-column
   board in `TradesScreen`: TRADE FOR column (pinned_receive, pos-green
   top rule) + TRADE AWAY column (pinned_give, flare top rule), mini
   chips with per-chip remove, per-column dashed add buttons that open
   the existing FB-47 picker pre-directed. All other surfaces (standalone
   Trades home, Guided/Team modes) keep the original single-column
   direction-toggle section byte-for-byte.
2. **#174 package toggle (item 2)** — "Trade as one package"
   (`PackageToggle`, testID `trades.package-toggle`) renders whenever 2+
   give players are pinned (both board layouts). Default **ON**; ON sends
   `pinned_give_mode:'all'` so every generated card's give side carries
   EVERY pinned player. See `../174-package-constraint/status.md`.
3. **Live pin counts (item 3)** — pins moved from TradesScreen local
   state to the session-only zustand store
   `mobile/src/state/useFinderTargets.ts` (cleared on league switch via a
   `useSession` subscription — works even when the deck screen is
   unmounted). The hub's Specific Player card shows "N to trade for · M
   to trade away" (mono/chalk) whenever anything is pinned.
4. **Team-mode in-place switch (item 4)** — the mode bar's Team chip now
   opens an in-screen manager-picker sheet in `TradesScreen`
   (`trades.team-picker.<user_id>`) and lands via
   `navigation.setParams` — same screen instance, no re-navigation. An
   in-place scope change resets the deck AND auto-kicks generation for
   the new opponent; first entry from the hub keeps the manual
   Find-a-Trade start. The hub's own picker is unchanged.

Also on the deck card (operator feedback): **#186** per-side
"Keep · more offers" actions (`trade-card.keep-give`/`.keep-receive`) —
see `../186-see-other-side/status.md`; **#190** "Edit in calculator"
(`trade-card.edit-in-calc`) — see `../190-edit-in-calculator/status.md`.
Hub additions: **#173** untouchables management sheet from the Trade DNA
row (`finder-hub.dna.untouchables`) — see
`../173-untouchables-discoverability/status.md`; `FeedbackFAB` mounted on
the hub screen.

**#168/#172 (stretch)** — NOT built: the generate API exposes no intent
knobs (only fairness/pins/opponent scope), so an intent chip would need
new engine params — out of scope this round. PRD written instead:
`../168-looking-for-intents/prd.md`.

**On-device QA flag interaction:** the operator's allowlisted device runs
the `onboarding.trades_first` experiment arm, whose Trades-home behavior
(first-run auto-generate on the deck) the hub now displaces — QA that
combination on-device before release. The experiment itself was NOT
changed.

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

- Original build: `tsc --noEmit` clean; 967 passed (incl.
  `test_opponent_scope_limits_generation_to_one_leaguemate`).
- Finish batch (2026-07-25): `cd mobile && npx tsc --noEmit` — clean;
  `python3 -m pytest backend/tests/ -q` — **1086 passed, 1 skipped**
  (baseline 1083 + 3 new `pinned_give_mode` tests in
  `backend/tests/test_finder_targeting.py`, flag fixtures flipped).

## Deferred / notes (historical — resolved by the finish batch above)

- ~~Specific Player single-column board~~ → two-column FOR/AWAY board (item 1).
- ~~"Require both sides in every package" toggle~~ → shipped as the #174
  "Trade as one package" toggle + `pinned_give_mode:'all'` backend constraint.
- ~~Live pin-count static copy~~ → live counts via `useFinderTargets` (item 3).
- ~~Team scope re-navigates~~ → in-place setParams + auto-regen (item 4).
- Still open: the finder-card verdict value bar note is obsolete —
  `TradeValueBar` has been wired on deck cards since #157.

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
