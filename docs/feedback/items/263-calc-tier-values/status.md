# #263 — Trade calculator: pick-tier labels instead of raw values

> Status doc for the operator polish request: "Update the value next to all
> players from a numerical value to the pick assigned tier values" in the
> mobile Trade Calculator.

## What shipped

Every **player** row in the Trade Calculator (`mobile/src/screens/TradeCalculatorScreen.tsx`
Live/Demo modes and `mobile/src/components/InLeagueCalculator.tsx` In-league
mode) now shows its **pick-value ladder tier** (`TierBadge` — e.g. "1 1st",
"2nd", "FA") instead of a raw numeric value. This covers both give/receive
sides (`TradeSide`) and the search/add picker sheets (`PlayerPickerModal`)
across all three calculator modes, since all three funnel player rows
through those two shared components.

**Draft-pick rows are unchanged** (still numeric) — a pick's own name
("2027 1st Round") already reads as a rung on the same ladder, so tier-
labeling a pick would be circular. `TradeSide`/`PlayerPickerModal` treat
`pos === 'PICK'` as "no tier" and fall back to the numeric value for that
row only.

Totals, fairness verdicts, gap math, and sort order are all **untouched** —
this is a display-only change. Every row's underlying numeric value is still
what drives `/api/trade/evaluate` and the picker's value-desc sort; only the
number shown to the user changed.

## Why a backend field was needed (not purely a client relabel)

The ticket's framing assumed mobile already had a value→tier mapping that
would "just work" on the calculator's displayed values. That's true for
**Demo mode only** — its mock board (`data/tradeCalcMock.ts` `base`) is
explicitly on the same raw-Elo scale (~900–2600) the client's
`tierForElo`/`TIER_LABEL` (`utils/tierBands.ts`) already expects, so demo
mode's tier is computed client-side, reusing that existing util unchanged.

**Live and In-league modes could not reuse that path as-is.** The number
those modes display (`CalcValueRow.value` from `GET /api/trade/values`) is
`elo_to_value(seed_elo)` — a *different, non-linear-transformed* scale (the
same 0–10k "pick value" numbers shown elsewhere in the app), not the raw
seed Elo the tier bands (`/api/tier-config`, 1150–1972) are defined over.
Feeding that transformed value into `tierForElo` would have silently
mis-bucketed every live/in-league player. Re-deriving the transform's
inverse client-side (`elo_value_base`/`k`/`ref` are `model_config`-tunable,
per `backend/trade_service.py:value_to_elo`) would have forked a second,
driftable mapping — exactly what the ticket said not to do.

**Resolution:** `GET /api/trade/values` now additionally returns a `tier`
field per player, computed server-side from the RAW seed Elo via
`RankingService.tier_for_elo` — the same canonical band-walk
`/api/extension/rankings` and `/api/anchor/save` already use to hand tiers
to a client. This reuses the backend's single source of truth (no new tier
logic invented) and lets the client reuse its own single source of truth
(`TIER_LABEL`, via `TierBadge`) for display — no math forked on either side.
`value` is unchanged; `tier` is additive. See `docs/api-reference.md`
(`GET /api/trade/values` entry) for the updated response shape.

## Scoped out (numeric value still shown) — for operator awareness

- **`PlayerPickerModal` secondary value line** (`you: 1,200` / `them: 950`,
  demo mode only). This is the dual-board arbitrage comparison the
  "Sell high"/"Target" badges are built on — collapsing two nearby numbers
  into the same coarse 8-tier label would frequently show the SAME tier on
  both lines and erase the fine-grained disagreement that's the whole point
  of that line. Left numeric; primary value on the same row already
  converted to tier.
- **`EvenerRows`** ("Recommended to even it" / "Trade options" rows) and
  **`SuggestionCard`** (fair-package suggestion cards). Eveners can be a
  player, a pick, or a 2-piece `PKG` combo, and their value is the actual
  decision input ("does this closeness this gap?") — precision matters more
  than the ladder label there, and combos don't map cleanly to a single
  tier. `SuggestionCard` doesn't display a per-player number at all today
  (name + position chip only), so there was nothing to convert.
- **`ShareTradeImage`** (share-as-PNG card) and the text-share fallback —
  package totals, not per-player rows; out of scope for a per-player
  relabel and untouched.

If the operator wants any of these converted too, flag it and I'll size it
separately — the eveners/suggestions path in particular would need
`POST /api/trade/evaluate`'s `eveners[]`/candidate math to also carry a tier,
which is a larger surface than this ticket's "player rows" scope.

## Files touched

- `backend/server.py` — `trade_calc_values_route` (`GET /api/trade/values`):
  added `tier` per row.
- `backend/tests/test_trade_evaluate.py` — `test_values_endpoint_shape_and_etag`
  updated for the new field.
- `docs/api-reference.md` — `GET /api/trade/values` entry updated.
- `mobile/src/api/calc.ts` — `CalcValueRow.tier: Tier`.
- `mobile/src/components/TradeSide.tsx` — new optional `tierOf` prop; renders
  `TierBadge` when resolved, else the existing numeric `Text`.
- `mobile/src/components/PlayerPickerModal.tsx` — new optional `tierOf` prop
  on the primary value column + composed a11y label; same fallback pattern.
- `mobile/src/screens/TradeCalculatorScreen.tsx` — `liveTierById` map off
  `/api/trade/values`'s new field; `tierFor()` helper (demo mode: client-side
  `tierForElo` over the mock board; live mode: the server tier); wired into
  both `TradeSide` and both `PlayerPickerModal` instances.
- `mobile/src/components/InLeagueCalculator.tsx` — same `tierById` map +
  wiring for its 2 `TradeSide` + 2 `PlayerPickerModal` instances.

## Gates

- `cd mobile && npx tsc --noEmit` — clean, no errors (symlinked
  `node_modules` from the sibling worktree for the check, removed after).
- `python3 -m pytest backend/tests -q` — `2041 passed, 1 skipped` (matches
  the stated baseline exactly — one existing test was extended, no test was
  added or removed).

## Flag

Shipped unflagged — display-only relabel, and the underlying numeric value
that was "load-bearing" (per-row comprehension) is preserved everywhere a
tier can't cleanly stand in for it (see "Scoped out" above), so nothing
regresses in comprehension on those surfaces either.
