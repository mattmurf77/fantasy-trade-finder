# #303 · #306 · #320 — calculator group (2026-08-16 wave, G1)

**Status:** built · 2026-08-16 · branch `feat/fb303-calc` (worktree `fb303-calc`,
base = specs commit `56856f7` on `origin/main` `96f6945`)
**Plan:** `wave-calc:docs/feedback/items/303-calc-send-placement/plan-2026-08-13.md`
(authored against `origin/main` @ `60fccc7`; drift log below).
Multi-ID group → lowest ID owns this folder.

## What shipped

- **#303 (D-303-1):** the `SendInSleeperButton` block (the whole platform
  router) moved above `LeagueVerdict` in
  `mobile/src/components/InLeagueCalculator.tsx` — order is now trade window →
  eveners (#251 pin holds) → **Send** → verdict → balance suggestions →
  Share/Clear. Only the send block moved; Share (renders the verdict) and the
  destructive Clear stay end-of-flow. Verbatim props, same render guard.
- **#306 (D-306-1 = option A, graduate):** the `aggregate_tier_labels`
  experiment guard is REMOVED from `/api/league/power-rankings`
  (`backend/server.py`) — `total_value_label` + positional `value_label` emit
  ungated for every caller (the #285 literal-pick-count fold intact). The
  calculator's partner chips (and, automatically, LeagueSummary's per-team /
  per-position rows, which already rendered the keys when present) now show
  "≈N firsts" for everyone; raw numerics remain only as the old-server
  fallback. **D-306-2:** new additive `picks.value_label` per team — the #285
  literal count expressed alone (`_aggregate_pick_label(0.0, pick_firsts)`),
  never a conversion of the dollar-priced `picks.value`. Chip renders it as
  `Picks ≈N firsts`.
- **#320 (D-320-1/2/3):** `GET /api/league/picks` rows gain additive `tier` —
  `RankingService.tier_for_elo(seed_elo_for_value(pool_value), None, fmt)`,
  the band the pick's DISCOUNTED value sits in today (D-320-2 accepted: a
  2029 1st can badge `second`). Mobile merges `OwnedPick.tier` into
  `tierById` and all four `tierOf` call sites drop the #263 `'PICK' → null`
  carve-out, so `TradeSide` rows and both `PlayerPickerModal` mounts badge
  picks through the existing `TierBadge` machinery. The share image alone
  keeps picks numeric (D-320-3, #277/#280 stands). Alignment defect:
  `PositionChip` is wrapped in a fixed 44pt `chipCol` slot in BOTH row
  layouts (`TradeSide.tsx`, `PlayerPickerModal.tsx`) so pick and player rows
  start the name column at one x; `PositionChip` itself untouched (shared
  with Tiers/Trades/Matches — no drive-by).

## Operator decisions applied (chat, 2026-08-16)

| ID | Decision |
|---|---|
| D-306-1 | **A — graduate `aggregate_tier_labels`**; labels ship to everyone on calculator chips AND LeagueSummary rows. Code sheds the `variant_for` guard; experiment record retires via admin stop→decide. |
| D-306-2 | Yes — emit `picks.value_label` (literal-count firsts, #285 rule). |
| D-303-1 | Yes — send-only moves; Share + Clear stay at the bottom. |
| D-320-1 | Yes — pick rows get tier badges on calculator surfaces (supersedes #263's "picks stay numeric"). |
| D-320-2 | Accepted — badges reflect discounted value. |
| D-320-3 | Yes — share-image pick rows stay numeric. |

**For the session's living-memory write-back (orchestrator):** D-306-1's
graduation and D-320-1's #263 supersession belong in
`living-memory/DECISIONS.md`; deliberately not appended from this parallel
worktree to avoid D-id collisions across concurrent G-groups.

## Verification (D-056/D-057 — no Maestro/sim)

- Backend: `pytest backend/tests/test_power_rankings.py
  backend/tests/test_league_picks_tier.py` → **65 passed**. Sabotages proven
  RED then reverted: re-gate (`variant_for` guard back) → 7 failures;
  dollar-space `picks.value_label` → 1 failure (fixture chosen so literal
  "≈0.5 firsts" ≠ dollar "≈1 firsts"); pick-tier wrong-scale (`pool_value`
  straight into `tier_for_elo`) → 3 failures; platform-only tiers (skip
  `source:'user'`) → 1 failure.
- Mobile: `npm ci` (real install, no symlink), `npx tsc --noEmit` clean,
  `mobile/scripts/testid-lint.sh` OK. Four new structural suites (all green;
  each sabotage proven RED then reverted): `check-calc-send-placement.js`
  (revert-move, duplicate-mount), `check-calc-partner-labels.js`
  (numeric-first, sighted-only-a11y), `check-calc-pick-tiers.js`
  (picker-only fix, share-card exception), `check-picker-chip-alignment.js`
  (width removed, shared-chip drive-by).

## Operator TestFlight checklist

1. Trades tab → Manual calc → In-league mode, pick a league with picks.
2. **Partner chips (#306):** each opponent chip's summary line reads
   `QB ≈N firsts · RB … · Picks ≈N firsts` — no raw thousands anywhere.
   Verify on a NON-operator account too (labels are no longer
   allowlist-gated — this is the graduation's whole point).
3. **League tab:** team rows / per-position values show the same labels for
   that non-operator account.
4. Build a trade with a player on each side: the **Send in Sleeper** button
   sits directly under the "Recommended to even it" rows and ABOVE the
   verdict card; Share + Clear are still at the bottom.
5. **Pick badges (#320):** add a draft pick to a side — its row shows a tier
   badge (e.g. `2nd`), not a number; open "Send from your roster" → pick
   rows and player rows start their names at the same left edge, pick rows
   badged. Expect a far-out pick to badge BELOW its round (discounted —
   intended, D-320-2).
6. Share-as-image: pick rows on the PNG still show numeric values (D-320-3).
7. VoiceOver spot-check: an opponent chip speaks "QB about N firsts …",
   not raw numbers.
8. Prod experiment retirement (operator, after deploy): run the #279
   runbook's `transition` (stop) then `decide` curls for
   `aggregate_tier_labels` — code no longer reads it either way.

## Drift log (plan cite → current tree)

| Plan cite | Reality at build |
|---|---|
| `_aggregate_pick_label` at `server.py:837` | `:844` (region intact) |
| Experiment gate at `server.py:20100-20107` | `:21122-21158` |
| #300 medians bypass `:19965-19970`, `_position_medians` `:19993` | `:21010-21015`, `:20985` |
| Picks route serializer `:9106-9108` | `:9460-9464` (`/api/league/picks` route at `:9430`; W3 M-C added `_pick_wire_source`/`tradeable` to the dict since the plan's base — tier key added alongside, no conflict) |
| `seed_elo_for_value` at `data_loader.py:96` | `:103` |
| InLeagueCalculator line map (§1.1 table, 674-827) | shifted (~682-835 pre-edit) but structurally identical; all anchors found |
| `partnerSummaries` `161-178`, chip summary `620-641`, a11y `592-599` | `161-178` / `~628-661` / `~601-607` — same shapes |
| Plan's Maestro flows `calc/01-03` + sim-gate tier 1 (§1.3/§2.4/§3.3/§6) | **NOT built** — D-056/D-057 retired Maestro/sim; replaced with the structural suites + this TestFlight checklist |
| Plan §2.3 "operator `decide`s via admin route and code sheds the guard" | No prior in-code graduation pattern exists; done surgically (guard removed, docs updated, prod decide left to the operator per checklist step 8) |
| `tierBands.ts:12-14` position-uniform note | now in the file-top comment (same fact) |
| `PositionChip.tsx:40-48`, `PlayerPickerModal.tsx:156/326-333`, `TradeSide.tsx:50/110-117` | `:40-48` / `:156-ish (renderRow)/styles.row` / `:50/styles.row` — all matched |
| §3.2 "no `CalcPlayer` type change" | held — `pickById` untouched; tier flows via `tierById` only |
| `TradeCalculatorScreen.tsx` | zero edits, as predicted (live/demo pools hold no picks; its own `tierFor` PICK-null at `:405` intentionally left — that surface has no pick assets) |

## PRD deviations

- `chipCol` width fixed at 44 by measurement-free reasoning (sm PICK chip ≈
  38-42pt incl. border); plan wanted an on-sim verification — sim retired,
  so the TestFlight checklist step 5 is the verification. Constant pinned
  identical across both files by the structural test.
- a11y phrasing: labels are spoken as "about N firsts" (plan's "QB about 3
  firsts" example followed; implemented as one shared `segmentSpoken`
  helper so visible/spoken can never diverge).
- `picks` chip segment renders `Picks ≈N firsts` including "≈0 firsts" for
  all-3rd+ holdings (server emits honestly; client still hides the segment
  entirely when the team owns zero picks — plan's count-fallback wasn't
  needed since D-306-2 was approved).

## Proposed (NOT applied — shared-docs owner)

`docs/cross-client-invariants.md`: add the `≈N firsts` aggregate-label
format + the no-raw-numerics presentation rule now that the keys are
ungated and consumed by mobile on two screens (plan §2.5's seed).
