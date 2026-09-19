# 5. Post-trade impact preview

> Tier 1 · #5 · NEW · Effort M · Sources: DD

## Summary

Dynasty Daddy's strongest calculator feature is its post-trade simulation: a Team Position Ranks panel showing both teams' league rank per category (Starters, QB, RB, WR, TE, Picks) with rise/fall arrows *as if the trade went through*, team tier labels ("Contender," "Trust the Process"), and a Contender Mode toggle (teardown: `docs/competitor-teardown-web-tools.md`, Dynasty Daddy calculator section). Theirs is reactive — build a trade, see impact. FTF's version is proactive: every suggested card ships with its impact case attached.

The raw material already exists at suggestion time and is currently thrown away. Both generation paths call `analyze_roster_strengths()` for the user and every opponent (per-position `tier_depth` counts, `position_needs`, `position_surplus`), and only a thin slice survives onto the card as `match_context`. What's missing is (a) per-position *value totals* (the current profile counts players per tier, it doesn't sum value), (b) league-wide rank context (where each team's RB room ranks among all members), and (c) the post-trade recomputation. All three are cheap: rosters are already in memory for every league member inside `_generate_trades_v2`. Rendering the before/after for *both* teams is the explainability layer that makes an algorithmic suggestion trustworthy — showing the opponent's gain is the proof of the mutual-win claim, and it pre-arms the user with the pitch they'll paste into league chat.

## PRD

### Problem & user story

Cards today communicate scores (`mismatch_score`, `fairness_score`, narrative) but not consequences. *As a user*, before I like/send a trade I want to see what my roster looks like after — which position group gets stronger, whether I open a hole, where I move in the league pecking order — and the same for the other side, so I can judge "would they actually take this?" and explain the deal when I propose it.

### Goals / Non-goals

**Goals**

- Per-position group value (QB/RB/WR/TE) before and after, for both teams, on every trade card.
- League rank per position group before/after, with deltas (the rise/fall arrows).
- Needs filled / needs created: diff of `position_needs` pre vs post.
- Zero extra API round-trips: impact rides on the existing card payload.

**Non-goals**

- Contender Mode-style current-season vs dynasty toggle (needs season projections FTF doesn't have; revisit in-season).
- Picks as a ranked category (pick capital surfaces with #15).
- Standalone power-rankings page — that's #14 (it should reuse the same league position-value table built here).
- Impact for manually-entered hypothetical trades (that's the rescore endpoint, #3/#27).

### Functional requirements

1. **FR1** — New helper computing per-position value totals for a roster: sum of player values by position for QB/RB/WR/TE. Value basis = consensus `dynasty_value()` (comparable across teams; personal-value view is a non-goal v1 — see Open questions).
2. **FR2** — Once per generation job, build a league table: `{user_id: {pos: value}}` for all members, from rosters already iterated in `_generate_trades_v2`. League rank per position = rank of the team's positional total within that table.
3. **FR3** — Per surfaced card (after the top-K cut, NOT per candidate — candidate enumeration considers thousands of combos under a 1s deadline), compute post-trade rosters (user roster − give + receive; opponent mirror) and recompute FR1/FR2 plus `analyze_roster_strengths` for both sides.
4. **FR4** — Attach `impact` to the card: for each side, `{pos: {value_before, value_after, rank_before, rank_after}}`, `needs_filled`, `needs_created`.
5. **FR5** — Serialized only when the flag is ON, keeping flag-off payloads byte-identical (same pattern as `likes_you` / `sweetener` / `partner_fit` in `trade_card_to_dict`).
6. **FR6** — Works for divergence, consensus, and v3-optimizer cards identically (impact is computed in the orchestration loop, downstream of whichever generator produced the card).

### UX notes

- **Web** (`web/js/app.js` card renderer): collapsed "Impact" section under the narrative; expanded view = two columns (You / Them), per-position rows `RB 6,420 → 8,150 · #9 → #4 ▲5`, plus chips for "Fills your RB need" / "Opens a TE hole for them."
- **Mobile** (`mobile/src/components/TradeCard.tsx`): swipe deck must stay scannable — show a one-line summary chip on the card face ("You: RB #9→#4 ▲ · Them: WR #3→#1 ▲"), full panel behind a tap/expand. `StrengthBar.tsx` is a candidate for the per-position bars.
- **Extension:** not in v1; the Sleeper-overlay item (#19) reuses the same payload shape via the rescore endpoint later.
- Copy tone: advocate, not referee — lead with the user's gain, present the opponent's gain as the "why they say yes."

### Success metrics

- Like-rate (right-swipe) on cards with impact rendered vs. holdback.
- Expand-rate of the impact panel (instrument via the existing `record_event` user-events path).
- Match conversion (both-sides like) — impact framing should raise the opponent-side credibility of liked trades.

### Acceptance criteria

- [ ] For a fixture 1-for-1 trade, `impact` shows symmetric, arithmetically-correct value/rank deltas for both teams.
- [ ] Rank computation matches a brute-force recomputation over all league members.
- [ ] `needs_filled`/`needs_created` agree with re-running `analyze_roster_strengths` on post-trade rosters (incl. superflex QB threshold).
- [ ] Flag OFF ⇒ card JSON byte-identical to today.
- [ ] Generation wall-time regression < 5% on an 11-opponent league fixture.
- [ ] `docs/api-reference.md` card-shape table updated; `docs/glossary.md` gains "impact preview."

## HLD

### Components touched

- `backend/trade_service.py` — positional value helper; league table built in `_generate_trades_v2`; impact computation + new `TradeCard.impact: Optional[dict]` field.
- `backend/server.py` — `trade_card_to_dict` serializes `impact` behind the flag.
- `web/js/app.js` + CSS; `mobile/src/components/TradeCard.tsx` (+ `mobile/src/api/trades.ts` type).

### Data flow

`POST /api/trades/generate` → `_run_trade_job` → `_generate_trades_v2` builds the league position-value table once → per-pair generators return top-K cards → orchestration loop stamps `match_context`/`narrative` (existing) **and `impact` (new)** → `_dedup_and_sort` → job snapshot → `trade_card_to_dict` → clients render before/after panel.

### Flags & config interplay

- **New flag:** `trade.impact_preview`, default **false**, in `config/features.json`.
- Independent of `trade.outlook_blend` / `trade.marginal_value` — impact reports *consensus* positional reality, deliberately not the blended/marginal internals (those explain ranking; impact explains consequences).
- Interlocks with #1: if `trade.outlook_infer` is ON, the impact panel is the natural future home for the opponent's tier label (display only; no coupling in v1).
- Kill switch: flag off removes computation and payload; no stored state.

## LLD

### Engine changes

- `backend/trade_service.py`:
  - New `position_group_values(roster_ids, players) -> dict[str, float]` beside `analyze_roster_strengths` (same iteration pattern; sums `dynasty_value(player)` per position instead of binning into `_TIER_ELITE`/`_TIER_STARTER`/`_TIER_BENCH` counts).
  - In `_generate_trades_v2`: build `league_pos_values = {m.user_id: position_group_values(m.roster, ...)}` plus the user's own, computed once before the opponent loop (rosters are small; this is the same O(league × roster) work the `_fit_by_uid` pre-pass already does for FB-47).
  - New module-level `compute_trade_impact(card, user_roster, opp_roster, league_pos_values, players, scoring_format) -> dict` — applies the swap, recomputes both teams' `position_group_values` + `analyze_roster_strengths`, ranks within `league_pos_values` (post-trade table = pre-trade table with the two teams' entries replaced).
  - Stamped in the same loop that sets `c.match_context` / `c.narrative`, guarded by `FLAGS.trade_impact_preview`. Applies identically to `_generate_for_pair_v2`, `_generate_consensus_for_pair`, and `generate_pair_trades_v3` outputs.
  - `TradeCard` gains `impact: Optional[dict] = None` (default None keeps dataclass backward-compatible).
- No changes to scoring, fairness, or candidate enumeration — display-layer data, computed post-selection.

### API changes

- No new routes. `trade_card_to_dict` addition (flag-gated, omitted when absent):

```json
"impact": {
  "you":  {"groups": {"RB": {"value_before": 6420, "value_after": 8150, "rank_before": 9, "rank_after": 4}},
           "needs_filled": ["RB"], "needs_created": []},
  "them": {"groups": {"WR": {"value_before": 9800, "value_after": 11400, "rank_before": 3, "rank_after": 1}},
           "needs_filled": ["WR"], "needs_created": ["RB"]}
}
```

(Only changed groups could be trimmed client-side; serialize all four for simplicity.)

### Schema changes

None.

### Client changes

- `mobile/src/api/trades.ts` — extend the card type with optional `impact`.
- `mobile/src/components/TradeCard.tsx` — summary chip + expandable panel (reuse `StrengthBar.tsx`/`PositionChip.tsx`).
- `web/js/app.js` — card template: collapsed impact section; `web/css/` additions.
- Extension: none in v1.

### Rollout

- Flag `trade.impact_preview`, default `false`. Backend ships dark first (payload verified via fixture league), clients render behind the same flag from `GET /api/feature-flags`. Kill switch = flag off.

### Open questions

1. **Value basis:** consensus `dynasty_value` (proposed, comparable across teams) vs the user's personal/blended values (more "your market," but makes opponent-side ranks incoherent). A your-values toggle could come with #30.
2. **Picks column:** Dynasty Daddy includes Picks as a ranked group; FTF has `draft_picks.pick_value` per team. Include in v1 or wait for #15's dashboard? (Cheap to add; rank by summed pick value.)
3. **Payload weight:** decks stream up to ~30 cards via job snapshots polled repeatedly; if snapshot size becomes a problem, compute impact lazily on `/api/trades` reads instead of in the job loop *(verify snapshot sizes in practice)*.
4. **Tier labels in the panel:** hold for #1/#85 so naming ships once, consistently (per `docs/cross-client-invariants.md`).

## Dependencies & sequencing

- **Depends on:** nothing hard. Benefits from #1 (tier labels in the panel) and pairs naturally with #6 (verdict banner — same card real estate; design them together).
- **Feeds:** #14 league power rankings (reuse `position_group_values` league table), #19 extension overlay and #11 offer analyzer (same `impact` shape via the #3 rescore endpoint), #12 share cards (impact framing is the share-card content).
- Wave 3 per the backlog sequencing, but the backend helper can land earlier since #14 wants it too.
