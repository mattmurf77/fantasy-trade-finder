# #238 — Lineup before/after table in the In-league calculator verdict (V2)

**Status:** BUILT (2026-08-03) — branch `teardown-remediation` worktree, calculator only; deck/featured cards are explicitly phase 2.

**Operator ask:** "Adding a visual of a user's starting lineup before/after a trade is a valuable tool to the trade summary. Let's mock up that addition." Approved design: **V2** (frame C1) of `mockups/polish-lab-2026-08/lineup-before-after.html` — the full before/after starting-lineup table, all slots, unchanged rows dimmed, changed rows arrow + signed delta, net line.

## Root data gap (per the mock's data notes) — CLOSED

`power_rankings.optimal_starters()` filled slots in order internally but discarded WHICH slot each starter landed in before returning a flat id list, so "RB2: Cook → Spears" was unbuildable from the existing payload.

- **`backend/power_rankings.py`** — the greedy fill is factored into `_fill_starter_slots()` (shared, single source of the fill semantics) and a new additive sibling **`optimal_starter_slots(roster, lineup_slots)`** returns the template-ordered slot layout: `[{slot, player|None}]`, dedicated slots first by value, flexes narrowest-eligibility-first (WRRB/REC → FLEX → SUPER_FLEX), unfillable slots `None`. `optimal_starters()` behavior is unchanged (derived from the same fill; all pre-existing tests pass untouched).
- **`backend/server.py` `_starter_impact()`** (Mode B of `POST /api/trade/evaluate`) — payload extended additively with **`slots`**: the CALLER's per-slot breakdown `[{slot, before, after, delta}]` in the league's `roster_positions` template order; `slot` labels number repeats (`RB1`/`RB2`), `before`/`after` = `{player_id, name, position, value}` or `null`, `delta` = after − before (consensus-priced, 0 for a null side). Existing summary fields (`your_delta`, `their_delta`, `note`) unchanged. Null-safe: a slot-breakdown build failure drops only `slots` (logged), never the summary; the whole field still omits exactly as before (no template / missing roster / Mode A).

## Mobile change

- **`mobile/src/shared/types.ts`** — additive `StarterSlotPlayer` + `StarterImpactSlot` wire types; `mobile/src/api/calc.ts`'s `CalcEvaluationInLeague.starter_impact` gains optional `slots?: StarterImpactSlot[]`.
- **`mobile/src/components/InLeagueCalculator.tsx`** (LeagueVerdict) — new `LineupImpactTable` renders the V2 table when `slots` is present: TickLabel "Your lineup — before → after", Slot/Before/After header, one row per slot (mono slot label, long flex names shortened: `SUPER_FLEX`→`SF`, `WRRB_FLEX`→`W/R`, `REC_FLEX`→`W/T`), unchanged rows at 0.5 opacity with a flat "—" chip, changed rows chevron arrow + signed green/red bordered delta chip, dashed-rule net line "Starting lineup total 5,422 → 5,712 (+290)". Replaces the `calc.starter-impact` one-line sentence; the sentence still renders when `slots` is absent (old servers). Chalkline tokens throughout (chalk/ink/semantic/radii/fonts, chalkline `Text` with `scale="dense"`); testID **`calc.lineup-impact`**, container is one accessibility element voicing the server's `note`.

## Verification

- New tests written FIRST and confirmed failing pre-change (`ImportError: optimal_starter_slots`; `KeyError: 'slots'`):
  - `backend/tests/test_power_rankings.py` — template order + dedicated fill, FLEX vs SUPER_FLEX eligibility (QB never in plain FLEX), narrowest-flex-first with template-order output, out-of-pool slots skipped + agreement with `optimal_starters`.
  - `backend/tests/test_trade_evaluate.py` — `slots` payload shape on the Mode B evaluate (before/after players, names/positions, per-slot deltas reconciling with `your_delta`, summary fields intact), duplicate-slot numbering (`RB1`/`RB2`) + `after: null` on an emptied slot.
- `python3 -m pytest backend/tests -q` → **1415 passed, 1 skipped** (was 1409 passed pre-change).
- `cd mobile && npx tsc --noEmit` → clean.

## Docs

- `docs/api-reference.md` — evaluate row's starter-impact section documents `slots`.
- `mobile/src/components/CLAUDE.md` — InLeagueCalculator registry row + `calc.lineup-impact` testID tranche.
- No schema change → data-dictionary untouched.

## Out of scope (phase 2)

Deck/featured `TradeCard` mounts (V1/V3 frames): `/api/trades/generate` and the asset-ideas endpoint don't compute `starter_impact`, and per-card optimal-lineup computation across a whole deck needs its own perf pass first (mock data-notes bullet 3).
