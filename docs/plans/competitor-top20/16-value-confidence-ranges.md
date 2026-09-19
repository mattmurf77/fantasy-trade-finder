# 16. Value confidence ranges (bid/ask display)

> Tier 1 · #16 · ENH · Effort S · Sources: DTC / FTF

## Summary

DynastyTradeCalculator is the only competitor whose valuation concept admits uncertainty: their displayed value is "the mean of a player's buy line and sell line" — a bid/ask spread, not a single number (`docs/competitor-teardown-web-tools.md` §3). FTF already computes something strictly better and shows none of it. The v2 engine carries per-player confidence end-to-end: `comparison_counts()` (unique ranking opponents faced per player, `backend/ranking_service.py`) feeds `_shrink_user_elo` (w = n/(n + `shrink_pseudocount`), n₀ = 4 — an unranked player sits at consensus, a heavily-ranked one keeps full personal value) and `_value_uncertainty` (half-width fraction `range_base`/√(1+n), `range_base` 0.35), and the fairness gate already passes trades whose *value intervals* overlap even when the point ratio misses `fairness_threshold` (amendment A4, `_fairness` in `_generate_for_pair_v2`). The math exists; this item is the display layer.

Surface it three ways: show "5,800–6,400" instead of false-precision "6,100" where a player's matchup count is low; mark which values are *yours* vs. consensus-anchored (the shrinkage weight is exactly that statement); and close the motivation loop — "rank more matchups to tighten YOUR ranges" — which converts honesty into ranking volume, the engine-quality input the cold-start watch item needs and the habit #13's gamification will reward. No competitor shows uncertainty at all; DTC's spread is editorial, FTF's is computed per-user from their own behavior. Small effort, three wins: honest UX, a visible reason to rank, and a published differentiator that #20's transparency page can document as a named mechanism.

## PRD

### Problem & user story

Every value FTF displays is a point estimate, including for players the user has never once compared — where the "personal" value is, by construction, ~100% consensus. *As a user*, I want to know which of my values the app actually trusts came from me, and how precise they are, so I can trust trade math built on them. *As a product*, every wide range is a free, specific, non-nagging prompt to do the activity (3-player matchups) that powers the entire engine.

### Goals / Non-goals

**Goals**

- Serve per-player value, range bounds, and comparison count on ranking/player payloads, derived from the exact engine math (same shrinkage, same `range_base` formula — one source of truth).
- Render ranges where confidence is low (rankings list, player rows on trade cards), with a "rank to tighten" affordance linking to the trio flow.
- Keep the engine untouched: display-only feature.

**Non-goals**

- Changing how ranges gate fairness (already shipped, A4).
- Consensus-value uncertainty (DP seeds have no per-user sample count; consensus stays a point value).
- Player profile pages (#17) and value history (#57) — this item adds fields to existing surfaces only.
- Gamification mechanics (streaks/goals) — #13 consumes this loop, doesn't ship with it.

### Functional requirements

1. **FR1** — Backend exposes, per player on ranking payloads: `value` (rounded `elo_to_value(shrunk_elo)`), `value_low`/`value_high` (= value × (1 ∓ unc), `unc = range_base/√(1+n)`), and `comparisons` (n from `comparison_counts()`). Implemented in/beside `ranked_player_to_dict` (`backend/server.py`), reusing `trade_service._value_uncertainty` and `elo_to_value` — no formula duplication.
2. **FR2** — Display rule (client-side, config-served): show a range when `unc ≥ range_display_min_frac` (new `model_config` key, proposed 0.10 — with `range_base` 0.35 that means n ≤ ~11 comparisons); show a point value with a subtle "±" affordance otherwise.
3. **FR3** — n = 0 players render as "consensus value" state, *not* a ±35% range (an unranked player's personal range is meaninglessly wide and reads as broken; their shrunk value IS consensus). Copy: "Market value — rank him to make it yours."
4. **FR4** — Range elements carry a tap/click action deep-linking to the ranking flow filtered to that player's position (web: trio section; mobile: `RankScreen`).
5. **FR5** — Trade-card player rows may show a compact range indicator; full ranges live on rankings surfaces (cards stay scannable).
6. **FR6** — Flag OFF ⇒ payloads and UI byte-identical to today.

### UX notes

- **Web** (`web/js/app.js` rankings render + `web/positional-tiers.html` tiers view): value column becomes "5,800–6,400" or "6,100 ±" with a tooltip: "Based on 3 matchups — rank more to tighten your range." Consensus-state players get the muted "market value" treatment.
- **Mobile** (`mobile/src/components/PlayerCard.tsx`, `TierBin.tsx`, rankings in `RankScreen.tsx`/`ManualRanksScreen.tsx`): range as a thin band under the value, or "5.8k–6.4k" text at narrow widths; tap → ranking flow. `TradeCard.tsx`: optional small "~" / band glyph per player row only.
- **Extension:** none in v1; the #19 overlay inherits the payload fields when built.
- Copy framing is the differentiator: ranges are *yours* ("YOUR range", "make it yours"), never an apology for imprecision. Tone per `docs/glossary.md` + brand: advocate, not referee.

### Success metrics

- Matchups-per-user-per-week before/after (the loop's whole point); specifically trio sessions initiated from a range tap (instrument via `record_event`).
- Median displayed `unc` for active users trending down (ranges tightening = engagement working).
- Qualitative: support/feedback mentions of "why this number" should fall (pairs with #20).

### Acceptance criteria

- [ ] For a player with n comparisons, served bounds equal the A4 formula exactly (unit test pinning `value_low/high` to `_value_uncertainty` output).
- [ ] n = 0 → consensus state, no range; n large → point display; threshold n renders per FR2.
- [ ] Range tap lands in the correct position-filtered ranking flow on web and mobile.
- [ ] Flag OFF: ranking payloads byte-identical (fields omitted, not nulled).
- [ ] `docs/api-reference.md` (payload fields), `docs/config-reference.md` (flag + display key), `docs/cross-client-invariants.md` (display threshold + formatting shared by web/mobile), `web/ranking-method.html` gains a ranges paragraph (feeds #20).

## HLD

### Components touched

- `backend/server.py` — `ranked_player_to_dict` (and the rankings routes that use it); flag-gated field assembly; `comparison_counts()` already available in-session (it's fetched for trade jobs at `_run_trade_job`).
- `backend/trade_service.py` — no logic changes; `_value_uncertainty` + `elo_to_value` imported by the serializer (they're module-level functions).
- `web/js/app.js`, `web/css/`, `web/positional-tiers.html`, `web/ranking-method.html`.
- `mobile/src/components/PlayerCard.tsx`, `TierBin.tsx`, `TradeCard.tsx`; `mobile/src/screens/RankScreen.tsx`; API types in `mobile/src/api/`.

### Data flow

Rankings request → `RankingService` per-session → serializer joins elo + `comparison_counts()` → shrunk value + bounds computed with trade-engine functions → client formats per display rule → range tap → trio flow → new swipes raise n → next fetch shows tighter range. (The loop is visible within a single session — that immediacy is the retention hook.)

### Flags & config interplay

- **New flag:** `trade.value_ranges`, default **false**. (Named in the `trade.*` group because the value space and uncertainty math live in the trade engine; the alternative `trades.*` UI group was considered — decide at implementation, it's one string.)
- Reads existing keys `shrink_pseudocount`, `range_base`, `elo_value_*` — display stays automatically consistent with the fairness gate if those are ever retuned.
- New `model_config` key: `range_display_min_frac` (0.10) — display threshold only, never touches engine math.
- Interplay with #13: gamification's "tighten your ranges" goal copy requires this flag ON.
- Kill switch: flag off removes fields + UI; zero stored state.

## LLD

### Engine changes

None. Verified inventory of what's reused as-is: `_shrink_user_elo` (w = n/(n+n₀), `shrink_pseudocount` 4.0), `_value_uncertainty` (`range_base` 0.35, unc = 0.35/√(1+n)), `elo_to_value` (`elo_value_base`·exp(`elo_value_k`·(elo−`elo_value_ref`))), `comparison_counts()` (unique-opponent counts; memoized per ranking-service version). One nuance to verify at implementation: `comparison_counts` is per user **per scoring-format service session**, global across leagues — ranges are therefore format-scoped, not league-scoped, which matches how rankings themselves work.

### API changes

- No new routes. Rankings payload delta (flag-gated, e.g. `/api/rankings`-family routes that serialize via `ranked_player_to_dict` — enumerate exact routes at implementation):

```json
{"id": "4046", "name": "Patrick Mahomes", "elo": 1742, "rank": 3,
 "value": 3354, "value_low": 2963, "value_high": 3745, "comparisons": 8}
```

- n = 0 ⇒ `"comparisons": 0` with `value_low`/`value_high` omitted (consensus state is explicit, not encoded as a huge range).

### Schema changes

None.

### Client changes

- `mobile/src/api/` types + `PlayerCard.tsx`/`TierBin.tsx` range band + `RankScreen` deep-link target; `TradeCard.tsx` compact glyph (optional, can trail).
- `web/js/app.js` rankings/tiers renderers + tooltip + trio deep-link; `web/css/` band styles; `web/ranking-method.html` explainer copy.
- Both clients share formatting rules via `docs/cross-client-invariants.md` (rounding, "k" abbreviation, threshold).

### Rollout

- Flag `trade.value_ranges`, default `false`. Backend fields land dark → web renders (fastest iteration surface) → mobile in the next EAS/TestFlight cycle → enable. Kill switch = flag off.

### Open questions

1. **Which routes:** exact list of endpoints serializing ranked players (`ranked_player_to_dict` call sites) to extend — keep to rankings surfaces in v1, or also enrich the player dicts inside trade cards (`player_to_dict` has no elo/value today; adding value fields there is a bigger payload decision)?
2. **Format scoping copy:** ranges are per scoring format (1QB vs SF rankings are separate services) — does the UI need to say so, or is it implicit because rankings screens are already format-scoped?
3. **Range floor:** even a heavily-ranked player (n = 50) shows unc ≈ 4.9% — always display the ± affordance on tap, or hard-hide below the threshold? (Proposed: hide band, keep tooltip.)
4. **Anchoring risk:** does showing wide ranges on barely-ranked *elite* players make the product feel unsure of obvious calls? Mitigation is FR3's consensus state plus copy; validate in launch QA (#81 polish pass).

## Dependencies & sequencing

- **Depends on:** nothing — pure display over shipped math. Smallest item in the tier alongside #6/#20.
- **Feeds:** #13 ranking gamification (the motivation loop's visible payoff), #20 engine transparency page (a named, documented mechanism), #9 community-diff angles (confidence context for divergence claims), #17 player profiles (range belongs on the profile when built), #90 positioning refresh ("confidence honesty" is named there as a marketing pillar).
- Wave 1 (ship with #6 + #20 as the trust/explainability batch).
