# Calculator polish trio (DTF / DynastyDealer teardowns) — status

**Source:** `docs/business/product/2026-07-26-dynastydealer-dtf-teardowns.md`
polish candidates #3 (starter-impact line), #6 (partner-picker positional
summary), #5 (share-as-image).
**Status:** BUILT + verified 2026-07-27 (branch `teardown-remediation`,
isolated worktree). No feature flags — all three are additive: new server
field + client UI that renders only with data (1, 2) and a new client-only
action (3); old servers/clients degrade silently.

## 1. Starter-impact line (DTF "Trade Snapshot")

- **Backend** (`backend/server.py`): `POST /api/trade/evaluate` Mode B
  additionally returns `starter_impact: {your_delta, their_delta, note}` —
  each side's optimal-lineup value BEFORE vs AFTER the trade (positive =
  that side's starting lineup gets stronger). `_starter_impact` reuses
  `power_rankings.optimal_starters` (the League Analyzer derived-starters
  math, READ-ONLY reuse) over the league's Sleeper slot template via the
  same `_sleeper_lineup_slots` path the power-rankings route uses; rosters
  from `load_league_members`. Consensus-priced (the route's `seed_value`),
  so deltas are in the same units as the displayed totals. Picks and
  out-of-pool assets can't start → contribute 0 to lineups by construction.
- **Thresholds (documented, honest):** noise floor
  `eps = max(50, 0.025 × caller's before-trade lineup total)`
  (`_STARTER_IMPACT_MIN_ABS` / `_STARTER_IMPACT_FRAC`). Note copy:
  - `your_delta ≥ eps` → "You likely gain immediate lineup value."
  - `your_delta ≤ −eps` and `receive_value > give_value` → "You gain future
    value but lose immediate lineup strength." (more raw value in, but the
    surplus lives in depth/picks)
  - `your_delta ≤ −eps` otherwise → "You likely lose immediate lineup value."
  - else → "This mostly trades bench depth — your starting lineup barely
    moves."
- **Omitted** (never fabricated, never fails the route): Mode A (no
  rosters), unknown slot template (non-Sleeper league ids — ESPN/MFL/
  Fleaflicker/demo — or meta fetch failure), either roster missing from
  `league_members`, any build failure (logged + omitted).
- **Client:** `mobile/src/api/calc.ts` `starter_impact?` on
  `CalcEvaluationInLeague`; one dim `bodySm` line under the Consensus
  totals in the In-league verdict card (`InLeagueCalculator` →
  `LeagueVerdict`), testID `calc.starter-impact`. Renders only when the
  server sent the field.

## 2. Partner-picker positional value summary (DTF Trade Analyzer)

- `InLeagueCalculator` opponent chips gain a second line: "QB 930 · RB 2225
  · WR 2948 · TE 856 · Picks 428" — position labels in the position hexes
  (data encoding, paired with the text label per the a11y floor), values
  Plex Mono at the 11px type floor, `numberOfLines={1}` truncation.
- **Data source:** `GET /api/league/power-rankings` (consensus basis) —
  `teams[].positions[pos].value` + `teams[].picks.value`, fetched with the
  SAME react-query key LeagueSummaryScreen uses
  (`['league-power-rankings', leagueId, 'consensus']`), so a league the
  user already viewed costs no extra request. No new endpoints.
- Picks segment renders only when `picks.count > 0`; no power-rankings data
  (error / old server) → chips render exactly as before (silent-fail
  enrichment). Chip a11y label spells the summary out ("…, ranked, QB 930,
  RB 2225, …, picks 428"). testID `calc.partner-summary.<user_id>` on the
  summary line; chip testIDs unchanged (chips never had ids — they assert
  via a11y label, per #192).

## 3. Share-as-image (DynastyDealer "Screenshot & Share")

- **Dependency:** `react-native-view-shot@4.0.3`, installed with
  `npx expo install` inside `mobile/` (SDK-pinned; package.json +
  package-lock changes ride this commit; rides the next EAS build — no
  config plugins, no eject).
- **Component:** `mobile/src/components/ShareTradeImage.tsx` — a
  "Share image" secondary Button (testID `calc.share-image`) plus an
  OFF-SCREEN Chalkline capture card (360px, ink-0, caption + both sides
  with PositionChip/name/value rows + per-side totals + verdict line +
  text-only "Dynasty Trade Finder" watermark in chalk-faint 11px — no
  gradients, tokens only). Press → `captureRef` PNG (tmpfile) →
  `Share.share({url})` (iOS). Capture/share failure → falls back to
  `Share.share({message: fallbackText})`; Android (core Share API is
  text-only for files) shares the text fallback directly.
- **Mounts:** In-league mode (`InLeagueCalculator` actions block, next to
  Send in Sleeper — caption "vs @opp · <format>", verdict line mirrors the
  two-board headline) and live mode (`TradeCalculatorScreen` actions row,
  next to the existing "Share trade" text share — caption "Trade idea ·
  <format>", consensus verdict line). Both require a settled server
  evaluation + both sides non-empty. Demo mode keeps text-only share.

## Verification

- `python3 -m pytest backend/tests -q` → 1340 passed, 1 skipped
  (baseline before change: 1336 passed, 1 skipped).
- New tests (`backend/tests/test_trade_evaluate.py`):
  `test_starter_impact_before_after_lineup_math` (exact before/after
  lineup totals on an RB+WR-template fixture, both sides, gain note),
  `test_starter_impact_bench_depth_and_future_value_notes`,
  `test_starter_impact_omitted_without_slot_template`,
  `test_starter_impact_omitted_in_mode_a`.
- `cd mobile && npx tsc --noEmit` → clean (worktree-local node_modules).

## Notes / follow-ups

- Mode B's board-priced deltas are value math; starter impact is
  deliberately consensus-priced to match the Consensus row it renders
  under. A personal-board variant would need per-board lineup fills.
- The share card renders off-screen at fixed 360px width; very long asset
  names ellipsize. If the operator wants league branding (league name in
  the caption), thread it from `useSession` — deferred, caption currently
  identifies opponent + format (in-league) or format (live).
- Partner summary uses consensus basis regardless of the calculator's
  format chip — power-rankings serves the session's active format; a
  format override inside the calculator does not re-price the summary
  line (acceptable v1; the line is a shape read, not a pricing surface).
