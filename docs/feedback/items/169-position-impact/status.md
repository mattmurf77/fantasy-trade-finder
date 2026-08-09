# #169 — Position-specific trade impact framing ("TE 10 → 17 ppg") mockup lab

**Status:** mockup-only · 2026-08-08 · branch `teardown-remediation` worktree (`mockups/polish-lab-2026-08/trade-position-impact.html`) — no code shipped, no flag exists.

## Operator ask (verbatim)

> "But it's also nice if this is a bit objective and says hey you are a contender and only have 10 ppg in your TE position and we found a way to get that to 17 in your starting lineup etc. This ups your championship odds to X … This trade makes your playoff / champion odds in 2026 at ? 2027 @ _ 2028 @ _"

## Scope for this pass

Operator direction: start with the **position-specific improvement framing** ("TE 10 → 17 ppg in your starting lineup") only. The championship/playoff-odds half of the ask is explicitly **out of scope** for this mock — no odds numbers appear anywhere in the lab. This doc and the HTML are mockup-only; nothing here is wired to real code, and no feature-scope block was opened (mockup-only work is exempt from the four gates in root `CLAUDE.md` §Conventions — this becomes required the moment a variant moves toward a real build).

## What already exists (read before mocking)

- **Trade summary / lineup before-after:** `#238`, shipped 2026-08-03 (`docs/feedback/items/238-lineup-impact/status.md`). `POST /api/trade/evaluate` Mode B (`backend/server.py` `_starter_impact()`) returns, per starting slot in the league's template order, `{slot, before:{player_id,name,position,value}, after:{...}, delta}` — built by `backend/power_rankings.py` `optimal_starter_slots()`. Rendered by `mobile/src/components/InLeagueCalculator.tsx`'s `LineupImpactTable` (testID `calc.lineup-impact`): slot / before / after / delta chip per row, unchanged rows dimmed, net line at the bottom. This is the module Variant A folds into.
- **Per-position scoring data:** none, anywhere. `git grep -n "ppg\|points_per_game\|per_game" backend/*.py` (excluding tests) returns **zero hits**. The app has never ingested weekly fantasy points, projections, or any per-position scoring signal — dynasty **value** (Elo-derived) is the only quantity the trade engine reasons about.
- **The one place real points DO exist:** `backend/outlook/` (dark behind the unwired `outlook.odds` flag). `league_state.py` pulls real Sleeper matchup `points_for`/`points_against` (whole-team, per completed week). `strength.py`'s `RosterValueStrength` provider maps a team's **total roster value** to a **whole-team** weekly-points estimate via a documented, explicitly-unvalidated heuristic (`mu = outlook_mean_points(110) + outlook_points_per_value_sd(12) × z(starting_lineup_value)`, flagged in its own docstring as "CALIBRATION — FLAGGED FOR OPERATOR REVIEW"). There is no position-level breakdown anywhere in this module either — it's team totals only.
- **Position-value breakdown that DOES exist:** `GET /api/league/power-rankings` (`backend/power_rankings.py` `compute_power_rankings()`) returns every team's `positions: {QB|RB|WR|TE: {count, value}}` — but that's whole-roster dynasty value, not starting-lineup points, and it's a separate call the trade-summary flow doesn't currently make.

## Data-availability verdict

| Claim | Computable today? | Why |
|---|---|---|
| "Your TE goes 380 → 810 value, the biggest single-slot move in this trade" | **Yes — ships today, zero new backend.** | Pure client-side `max(abs(delta))` over the already-shipped `starter_impact.slots` array (position + before/after value are already on each row). No new route, field, or schema change. |
| "Your TE is below the league average / your weakest starting position" | **Computable, but needs light integration.** | Real data exists (`GET /api/league/power-rankings` → `positions_value`), but it's a second live endpoint the trade-summary flow doesn't call today, and reconciling whole-roster `positions_value` against one STARTING slot's value needs a defined comparison (different denominators). Would need its own scope block. |
| "Your TE: 10.2 → 17.1 ppg" | **No — needs new backend work.** | No fantasy-points data source exists anywhere in the codebase, position-level or otherwise. Building this means inventing a new per-position scoring model (own projections or an nflverse-style points source) — a backend research/design effort, not a UI follow-on. |
| Any of the above on the deck/featured `TradeCard` (before the user opens the full summary) | **No, for a different reason.** | Even the value-based framing (row 1) isn't wired there. `starter_impact` is computed on-demand for one Mode-B evaluate call; the deck (`/api/trades/generate` + asset-ideas) generates many candidate cards per sweep, and per-card optimal-lineup computation at that scale is the same "phase 2" gap #238's own status doc already deferred. |
| Championship / playoff odds by year | **No — explicitly out of scope for this pass**, and even if in scope: `backend/outlook/` is unwired (`outlook.odds` flag off), models whole-team scoring only (no position granularity), and its calibration is flagged unvalidated by its own author. |

**Bottom line: the operator's literal ppg numbers cannot be produced by anything in this codebase today.** The dynasty-value version of the same insight ("TE: 380 → 810, +430") is real, ships from data the backend already returns, and needs one new client-side line of arithmetic.

## Mockup lab

`mockups/polish-lab-2026-08/trade-position-impact.html` — Chalkline tokens (reused verbatim from the approved `lineup-before-after.html` base), 393×852pt phone frames. Structure: a "Current" reference frame (exact reproduction of the shipped #238 `LineupImpactTable`, real strings, Cook/Waddle example) followed by three variants, all built against a cleaner example trade (send bench WR + a 4th, receive a starting-caliber TE) chosen so the trade's entire lineup impact is legible as "your TE spot" — unlike #238's own three-slot example. Every value number in every frame is internally consistent (before/after totals tie to the shown deltas). Every ppg-framed line is visually flagged dashed/amber "NEEDS NEW DATA — illustrative only, not built" so nobody mistakes it for a working feature.

1. **Variant A (required) — folded into the lineup-changes section.** The position-impact line ("Your starting TE value goes 380 → 810 — the biggest single-slot upgrade in this deal") renders *inside* the existing `lineupmod` container, directly under the net line — no new card, no new section. The changed TE row gets a subtle `--te`-tinted background wash (existing position hex, no new color per `docs/cross-client-invariants.md`). A dashed illustrative ppg line sits directly beneath it so the operator can react to the literal phrasing in context. **Recommended** — cheapest to build (one new client-side line inside an already-shipped module) and matches the operator's own framing of "add this to the trade summary," not a new surface.
2. **Variant B — standalone "Why this trade" strip.** Same sentence, but promoted to its own module that leads the card, above the give/receive split — "opens with the headline" rather than ending with it, closer to how the operator's example reads ("hey you are a contender and…"). Same data source as A, same zero-new-backend cost, but ~44pt heavier (a whole new mounted block vs. one line in an existing one).
3. **Variant C — deck card's one-line hook.** A subtitle line under the opponent name on the swipe-deck `TradeCard`, before the user opens the full summary ("Upgrades your weakest starter: TE +430 value"). **Explicitly flagged in the mock as illustrative-layout-only** — this is the one variant that isn't computable today even in value terms, because `starter_impact` doesn't reach the deck at all (same phase-2 gap #238 already called out).

## Recommendation

Ship Variant A first if/when this moves off mockup: it's additive to a payload that already exists, costs one new client-side computation, and needs no backend PR. Variant B is a layout preference on the same data — pick it only if the operator wants the headline to lead rather than live inside the table. Leave the ppg framing and the deck mount out of the near-term build; both need their own scope blocks (new points-per-game data source; deck-scale lineup computation) before any code is written.

## Open questions

- Does the operator want the "weakest position vs. league" comparison (Tier 2 above — computable via `power-rankings`, needs integration) as a near-term follow-on to Variant A, or is "biggest mover within this trade" framing (Tier 1, zero integration) sufficient?
- If PPG framing stays a goal long-term: which points source should the new per-position model use — trailing actual scores (in-season only, same pattern as `outlook/strength.py`'s `TrailingScoresStrength`), Sleeper's own projections (`SleeperProjectionsStrength`, currently a registered-but-unimplemented stub), or a new FTF/nflverse model? This is a real design decision, not decided by this mock.
- Should Variant A's TE-row highlight treatment (subtle position-hex background wash) be reused as a general "biggest mover" affordance elsewhere lineup deltas are shown, or is it specific to this feature?
