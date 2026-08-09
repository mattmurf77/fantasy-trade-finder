# #169 — Position-specific trade impact framing mockup lab

**Status:** built · 2026-08-09 · branch `worktree-agent-a16b8c9e20f110454` — mockup-only pass (below) superseded by an operator build decision; live behind flag `trade.position_impact` (ON in `config/features.json`).

## Build (2026-08-09) — operator decision + what shipped

Operator decision: **build A1a — the fold-in to the shipped #238 lineup-changes table with POSITIONAL-RANK framing ("TE21 → TE4") — with two modifications:**

1. The pick-tier label **replaces** the "+430"-style numeric value-delta chip.
2. The player being traded **away** also gets a tier label (A1a's mockup only labeled the incoming player).

Implementation, resolved to preserve both modifications without inventing a second UI surface: `TierBadge` already carries an optional `posRank` slot (`mobile/src/components/TierBadge.tsx`, e.g. "4th · TE21") purpose-fit for exactly this — a single chip that shows both the tier label AND the rank movement. A CHANGED slot in `LineupImpactTable` now renders a second line under the row with two `TierBadge` chips (before → after), replacing the raw delta chip; unchanged rows are untouched. Reading the pair left-to-right ("4th · TE21" → "1 1st · TE4") is the "TE21 → TE4" rank-movement framing, without a separate sentence.

- **Backend** (`backend/server.py`): `_starter_impact()`'s `slot_entry()` builder gains a `tier_of` param (mirrors #277's `_evener_tier` pattern). When bound, each `slots[].before`/`after` entry gets additive `tier` (`RankingService.tier_for_elo` over the RAW seed Elo — the SAME call #277's `_evener_tier` closure already makes, reused verbatim, not duplicated) and `rank` (1-based positional rank within the universal pool, via `trends_service.compute_consensus_pos_ranks(elo_map, {}, players_meta)["pos_rank"]` — reusing the EXISTING canonical rank helper the Trends tile stats already ship, rather than hand-rolling a new sort, which is a cheaper and more precedented path than the mockup lab's write-up anticipated). `tier_of` is bound at the evaluate route only when `is_enabled("trade.position_impact")`; off ⇒ `tier_of=None` ⇒ neither key is added ⇒ `slots` is byte-identical to pre-#169.
- **Mobile** (`mobile/src/components/InLeagueCalculator.tsx`'s `LineupImpactTable`): field presence alone gates the new rendering (no separate client flag read) — a CHANGED slot with `tier` on BOTH `before` and `after` swaps the value-delta chip for the two `TierBadge` chips described above; any other case (flag off, old server, or one side unpriced) falls back to the legacy numeric delta chip untouched.
- **Types** (`mobile/src/shared/types.ts`): `StarterSlotPlayer` gains optional `tier?: Tier | null` and `rank?: number | null`.
- **Rank tie-break**: deterministic — descending value, then ascending `player_id` (inherited from `trends_service._pos_rank_map`, the same tie-break the Trends tile stats already ship and test).
- **Tests**: `backend/tests/test_trade_evaluate.py` — flag-on tier/rank correctness (both slots, both sides), flag-off absence (`slots[].before/after` key set unchanged from pre-#169), rank tie-break determinism, and a null-`after` slot carrying no tier/rank on the null side.
- **Docs**: `docs/api-reference.md` (`/api/trade/evaluate`'s `slots` description) and `docs/config-reference.md` (flag row) updated.
- **Not built this pass**: the summary-sentence framings (A1b/C1a/C1b) and the deck-hook mount (Variant C) — out of scope for the operator's build ask, which named A1a plus its two modifications only.

## Original mockup-lab pass (2026-08-08/09, superseded above)

Mockup-only, no code shipped, no flag existed. Kept as the design-exploration record; the build above resolved the open A1a/A1b framing question via the operator's explicit modifications rather than either mockup frame verbatim.

## Operator ask (verbatim, original pass)

> "But it's also nice if this is a bit objective and says hey you are a contender and only have 10 ppg in your TE position and we found a way to get that to 17 in your starting lineup etc. This ups your championship odds to X … This trade makes your playoff / champion odds in 2026 at ? 2027 @ _ 2028 @ _"

## Operator review of the first pass — verbatim directives (2026-08-09)

The first pass shipped three frames: **A1** (fold-in to the #238 lineup-changes table, raw dynasty-value sentence "TE value goes 380 → 810"), **B1** (standalone "Why this trade" strip, same sentence promoted above give/receive), **C1** (deck-card one-line hook, illustrative only). Operator review:

> B1: "Nope. Abandon." · A1: "Should be from TE x to TE x OR from Tier x to Tier x. Mock up both versions." · C1: "Same feedback as A. Mock up both versions."

## What changed in this revision

- **B1 removed entirely** — the standalone strip frame and its writeup are gone. Value narration, when it ships, stays inside either the shipped #238 lineup table (fold-in) or the deck hook — never a new mounted module.
- **A1 and C1 each split into two framings**, replacing the single raw-value sentence with the two alternatives the operator named:
  - **A1a / C1a — positional-rank framing:** "TE21 → TE4" (dynasty rank within position, pool-wide).
  - **A1b / C1b — tier framing:** the real shipped 8-tier pick-value ladder labels (`docs/cross-client-invariants.md`) — "4th → 1 1st", not invented "Tier N" numerals.
- This is a **UX-framing decision, not a new data-availability finding.** Raw dynasty value ("380 → 810") was and remains computable with zero backend changes — the operator simply doesn't want that unit shown to users. The ppg-infeasibility finding from the first pass is unchanged and orthogonal to this framing choice (see verdict table below).

## Scope for this pass

Operator direction, original pass: start with the **position-specific improvement framing** only; the championship/playoff-odds half of the ask stays explicitly **out of scope** — no odds numbers appear anywhere in the lab, this pass included. This doc and the HTML are mockup-only; nothing here is wired to real code, and no feature-scope block was opened (mockup-only work is exempt from the four gates in root `CLAUDE.md` §Conventions — this becomes required the moment a variant moves toward a real build).

## What already exists (read before mocking)

- **Trade summary / lineup before-after:** `#238`, shipped 2026-08-03 (`docs/feedback/items/238-lineup-impact/status.md`). `POST /api/trade/evaluate` Mode B (`backend/server.py` `_starter_impact()`) returns, per starting slot in the league's template order, `{slot, before:{player_id,name,position,value}, after:{...}, delta}` — built by `backend/power_rankings.py` `optimal_starter_slots()`. Rendered by `mobile/src/components/InLeagueCalculator.tsx`'s `LineupImpactTable` (testID `calc.lineup-impact`): slot / before / after / delta chip per row, unchanged rows dimmed, net line at the bottom. This is the module Variant A folds into. Neither `tier` nor a positional-rank index is on this payload today.
- **Positional-rank source:** `GET /api/trade/values` (`backend/server.py` `trade_calc_values_route()`) returns every universal-pool player — `{id, name, position, team, age, value, tier}` — sorted by `value` descending. A player's rank within their position ("TE4") is a 1-based index into that list filtered to one `position`. `_starter_impact()` already has this same pool loaded in memory as `_pool_players`; wiring rank into the slot builder means sorting it by `(position, value)` once per evaluate call and looking up each before/after player's index — no new endpoint, no new data source, no second network call, but a new sort/index step with no existing precedent elsewhere in the codebase for this purpose.
- **Tier source:** the same `/api/trade/values` route already returns `tier` per player — the pick-value ladder key from `RankingService.tier_for_elo(seed_elo, position, format)` (`docs/cross-client-invariants.md`'s 8-tier ladder). Better still, `_starter_impact()`'s own neighbor code already calls this exact function today: the `#277` evener-row `_evener_tier` closure (`backend/server.py`, right below where `_starter_impact` is invoked) does `RankingService.tier_for_elo(seed.get(pid, 1500.0), pos, fmt)` off the same raw seed dict already in scope. Threading that identical call into `_starter_impact()`'s `slot_entry()` builder is the smaller, more precedented of the two additions — no new endpoint, no new data source, no new pattern, just reusing a call this function's sibling code already makes.
- **Per-position scoring data:** none, anywhere. `git grep -n "ppg\|points_per_game\|per_game" backend/*.py` (excluding tests) returns **zero hits**. The app has never ingested weekly fantasy points, projections, or any per-position scoring signal — dynasty **value** (Elo-derived) is the only quantity the trade engine reasons about.
- **The one place real points DO exist:** `backend/outlook/` (dark behind the unwired `outlook.odds` flag). `league_state.py` pulls real Sleeper matchup `points_for`/`points_against` (whole-team, per completed week). `strength.py`'s `RosterValueStrength` provider maps a team's **total roster value** to a **whole-team** weekly-points estimate via a documented, explicitly-unvalidated heuristic (`mu = outlook_mean_points(110) + outlook_points_per_value_sd(12) × z(starting_lineup_value)`, flagged in its own docstring as "CALIBRATION — FLAGGED FOR OPERATOR REVIEW"). There is no position-level breakdown anywhere in this module either — it's team totals only.
- **Position-value breakdown that DOES exist:** `GET /api/league/power-rankings` (`backend/power_rankings.py` `compute_power_rankings()`) returns every team's `positions: {QB|RB|WR|TE: {count, value}}` — but that's whole-roster dynasty value, not starting-lineup points, and it's a separate call the trade-summary flow doesn't currently make.

## Data-availability verdict

| Claim | Computable today? | Why |
|---|---|---|
| "Your TE goes 380 → 810 value, the biggest single-slot move in this trade" (rejected framing, kept for completeness) | **Yes — zero new backend.** | Pure client-side `max(abs(delta))` over the already-shipped `starter_impact.slots` array (position + before/after value are already on each row). No new route, field, or schema change. This is the framing the operator's 2026-08-09 review rejected in favor of rank/tier — a UX call, not a capability gap. |
| "Your TE goes TE21 → TE4" (positional-rank framing) | **Yes — small additive backend change.** | Derived from `/api/trade/values`' already-served pool, already loaded server-side in `_starter_impact()` as `_pool_players`. Needs a new sort-by-position-then-value + index lookup inside `_starter_impact()`'s slot builder — no new data source, no schema change, no second network call, but not literally zero-code (no field for this exists on `starter_impact.slots` yet). |
| "Your TE moves 4th → 1 1st" (tier framing) | **Yes — small additive backend change, cheaper than rank.** | `tier` is already served per player on `/api/trade/values`, computed via `RankingService.tier_for_elo`. `_starter_impact()`'s sibling code (#277's `_evener_tier`) already calls this exact function in this exact file. Wiring the same call into the slot builder is a smaller, more precedented change than rank's new sort/index step. |
| "Your TE is below the league average / your weakest starting position" | **Computable, but needs light integration.** | Real data exists (`GET /api/league/power-rankings` → `positions_value`), but it's a second live endpoint the trade-summary flow doesn't call today, and reconciling whole-roster `positions_value` against one STARTING slot's value needs a defined comparison (different denominators). Would need its own scope block. |
| "Your TE: 10.2 → 17.1 ppg" | **No — needs new backend work.** | No fantasy-points data source exists anywhere in the codebase, position-level or otherwise. Building this means inventing a new per-position scoring model (own projections or an nflverse-style points source) — a backend research/design effort, not a UI follow-on. Unaffected by the rank-vs-tier framing decision. |
| Any of the above on the deck/featured `TradeCard` (before the user opens the full summary) | **No, for a different reason.** | None of the framings (value, rank, or tier) are wired there. `starter_impact` is computed on-demand for one Mode-B evaluate call; the deck (`/api/trades/generate` + asset-ideas) generates many candidate cards per sweep, and per-card optimal-lineup computation (plus a rank/tier lookup on top) at that scale is the same "phase 2" gap #238's own status doc already deferred. |
| Championship / playoff odds by year | **No — explicitly out of scope for this pass**, and even if in scope: `backend/outlook/` is unwired (`outlook.odds` flag off), models whole-team scoring only (no position granularity), and its calibration is flagged unvalidated by its own author. |

**Bottom line: the operator's literal ppg numbers still cannot be produced by anything in this codebase today** — that finding is unchanged from the first pass. What changed is the framing chosen from among the options that ARE computable: rank and tier are both buildable with a small, well-precedented backend addition (no new data source for either), and the operator has directed both get mocked head-to-head instead of the rejected raw-value sentence.

## Mockup lab

`mockups/polish-lab-2026-08/trade-position-impact.html` — Chalkline tokens (reused verbatim from the approved `lineup-before-after.html` base), 393×852pt phone frames. Structure: a "Current" reference frame (exact reproduction of the shipped #238 `LineupImpactTable`, real strings, Cook/Waddle example) followed by four framing frames, all built against the same cleaner example trade as the first pass (send bench WR + a 4th, receive a starting-caliber TE) so the trade's entire lineup impact is legible as "your TE spot" — unlike #238's own three-slot example. Every value/rank/tier number in every frame is internally consistent (Cade Otton ≈ TE21 / tier `4th`; Sam LaPorta ≈ TE4 / tier `1 1st`). Tier chips reuse the real ladder colors/labels verbatim from `docs/cross-client-invariants.md` (lime `4th`, teal `1 1st`) — no invented tier numerals.

1. **Variant A (required) — folded into the lineup-changes section, two framings.**
   - **A1a — positional-rank:** "Your starting TE jumps TE21 → TE4 — the steepest rank climb in this deal." Renders inside the existing `lineupmod` container, under the net line, TE row gets the subtle `--te` wash — same location as the first pass's rejected A1.
   - **A1b — tier:** "Your starting TE moves `4th` → `1 1st` — the steepest tier climb in this deal," using real `TierBadge`-style chips. Same location.
2. **Variant B — abandoned.** Operator: "Nope. Abandon." Removed from the lab entirely — no frame, no writeup.
3. **Variant C — deck card's one-line hook, two framings.** Both explicitly flagged illustrative-layout-only, same as the first pass — `starter_impact` doesn't reach the deck at all regardless of framing (same phase-2 gap #238 already called out).
   - **C1a — positional-rank:** "Upgrades your weakest starter: TE21 → TE4."
   - **C1b — tier:** "Upgrades your weakest starter: TE `4th` → `1 1st`."

## Recommendation

**Tier framing (A1b / C1b) over positional rank (A1a / C1a), if/when Variant A moves off mockup.** Three reasons:

1. **Cheaper, more precedented build.** Tier reuses an existing call already made inside `_starter_impact()`'s own function file (#277's `_evener_tier` pattern) verbatim. Positional rank needs a new sort/index step with no precedent elsewhere in the codebase for this purpose.
2. **Reuses vocabulary the app already teaches.** The 8-tier pick-value ladder is the mental model the Pick Anchor wizard, every `TierBadge` chip, and the tier-consolidation work elsewhere in this same polish batch (#277, `trades-home-inline.html`) already train users on. Tier framing extends a concept the user has seen; rank framing introduces a second, parallel one.
3. **Less noisy.** A tier only changes when a player crosses a real qualitative threshold on the ladder. A positional-rank number can swing by several slots on small value wobbles near a crowded position band — a real risk of the framing reading as jittery from one recompute to the next.

Positional rank's counter-case is real and shouldn't be dismissed: "TE12" reads instantly to anyone who's used KTC/FantasyCalc/Sleeper's own rankings, and it's more granular than an 8-bucket ladder can ever be. If user testing shows the tier chips read as too coarse, unfamiliar, or "made up" outside this app, rank is the fallback — not a dead end.

Either way: leave the deck mount (Variant C) and ppg framing out of the near-term build. Both need their own scope blocks (deck-scale per-card lineup + rank/tier computation; a new points-per-game data source) before any code is written.

## Open questions

- Between A1b (recommended) and A1a — does the operator have a gut preference before this goes to a scope block, or should it go to a quick user-facing test first?
- Does the operator want the "weakest position vs. league" comparison (computable via `power-rankings`, needs integration — see verdict table) as a near-term follow-on to Variant A, independent of the rank/tier choice?
- If PPG framing stays a goal long-term: which points source should the new per-position model use — trailing actual scores (in-season only, same pattern as `outlook/strength.py`'s `TrailingScoresStrength`), Sleeper's own projections (`SleeperProjectionsStrength`, currently a registered-but-unimplemented stub), or a new FTF/nflverse model? This is a real design decision, not decided by this mock.
- Should the chosen framing's TE-row highlight treatment (subtle position-hex background wash) be reused as a general "biggest mover" affordance elsewhere lineup deltas are shown, or is it specific to this feature?
