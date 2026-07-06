# 9. Community-diff trade angles
> Tier 1 · #9 · ENH · Effort M · Sources: FTF/GM

## Summary

FTF's defining asset is two value sets per player: the user's personal Elo (from 3-player matchups) and the DynastyProcess-seeded consensus (`g_universal_by_format[fmt]["seed"]` built in `build_universal_pool`, `backend/server.py`). The v2 engine already trades on user-vs-opponent divergence internally (`_generate_for_pair_v2` prunes candidates by `_vo(p) >= user_value[p] * 0.97` and its mirror), and a dark flag `tiers.community_diff` plus a fully built, flag-gated route `GET /api/tiers/community-diff` (user tier vs community tier per player) already exist. What's missing is making divergence a *visible strategy*: nowhere does the app say "you're higher than market on this player — that's a buy-low angle."

This feature has three surfaces: (1) per-player **diff badges** ("You: WR12 · Market: WR24") wherever player values render; (2) a per-league **angles list** — buy-low candidates (players you value above market/the leaguemate who rosters them) and sell-high candidates (your players the market values above your number); (3) **narrative hooks** on trade cards ("This works because you two disagree on these players"), extending the existing template narrative in `backend/trade_narrative.py`. DynastyGM's DIFF column (rank vs ADP, green/red) is the visual precedent, but theirs compares two global numbers — no competitor can personalize it, because no competitor has a personal value set.

## PRD

### Problem & user story
The divergence engine is invisible. Users see trade cards but not the *system* behind them, so the app reads as "a trade generator" rather than "an advocate that knows where your opinions differ from the market." As a dynasty manager, I want to see which players I'm higher/lower on than market and my leaguemates, so I know who to buy low, who to sell high, and why a suggested trade is genuinely in my favor.

### Goals / Non-goals
**Goals**
- Surface user-vs-consensus diff per player as a badge, app-wide where values display.
- Per-league buy-low / sell-high angles list, ranked by diff magnitude × player relevance.
- Divergence sentence in trade-card narratives when divergence drove the card (`basis == "divergence"`).
- Define what flipping `tiers.community_diff` ON means (see Rollout).

**Non-goals**
- No change to candidate generation or scoring — this is presentation over existing engine math.
- No multi-source ADP diff lens (backlog #56) — consensus seed only for v1.
- No new ranking inputs; cold-start mitigation is messaging, not synthetic data.

### Functional requirements
- FR1: Compute per-player diff = user value − consensus value, in the v2 value space (`elo_to_value` of shrunk Elo vs `elo_to_value` of seed Elo), per scoring format. Shrinkage via `_shrink_user_elo` is mandatory so unranked players show ~zero diff instead of fake divergence.
- FR2: Badge states: `higher` / `lower` / `even` with both rank framings (your positional rank vs market positional rank), thresholded so noise doesn't badge (proposal: |diff| ≥ 15% of consensus value AND comparison count n ≥ 3; threshold config-tunable).
- FR3: Angles list per league: **sell-high** = own-roster players with user value < consensus (and, where the leaguemate-market exists, < a leaguemate's `member_rankings` Elo); **buy-low** = players on other rosters with user value > consensus, annotated with which roster holds them and whether that member's own rankings value them below consensus ("they're cold on him too").
- FR4: Trade cards with `basis == "divergence"` carry a `diff_highlights` payload (top 1–2 players per side with the user-vs-opponent value gap) and the narrative includes one divergence sentence built from it.
- FR5: Empty/cold states: with <2 ranking sets in a league, leaguemate angles degrade to consensus-only angles with copy explaining that more league rankings unlock partner-specific angles (cold-start watch item).
- FR6: Flipping `tiers.community_diff` ON enables the existing tiers overlay AND the badges (same signal, same flag). The angles list + narrative hooks ship behind a new flag (see Rollout) so they can roll out independently.

### UX notes
- **Web:** badges in rankings/tiers views (`web/index.html` rankings screens, `web/positional-tiers.html` overlay already gated client-side per the route docstring); new "Trade Angles" panel on the league view in `web/index.html`, linked from the trades tab. Green = you're higher than market (buy-low when on someone else's roster), red = lower (sell-high when on yours) — match DynastyGM's DIFF color semantics and keep colors consistent with `docs/cross-client-invariants.md`.
- **Mobile:** badges on `TiersScreen.tsx` / `ManualRanksScreen.tsx` rows; angles list as a section on `LeagueScreen.tsx`. Card narrative change arrives for free via the `narrative` field already serialized in `trade_card_to_dict`.
- Tone is advocate, not referee: "You're higher than the market on Pacheco — see who's selling."

### Success metrics
- ≥30% of weekly-active users view the angles list in week 1 after launch.
- Swipe-right rate on divergence-basis cards with diff narrative vs without (A/B by flag) — target +10% relative.
- Ranking volume lift in leagues where angles are visible (angles motivate ranking; feeds #13).

### Acceptance criteria
- [ ] Badge math uses shrunk Elo; a brand-new user sees zero badges, not 700.
- [ ] `tiers.community_diff` ON shows the tiers overlay and badges; OFF returns the current empty-diffs behavior unchanged.
- [ ] Angles endpoint returns correct buy-low/sell-high split on a fixture league with known rankings.
- [ ] Divergence cards include `diff_highlights`; consensus-basis cards do not.
- [ ] Narrative renders the divergence sentence only when `diff_highlights` present; snapshot tests updated (`trade_narrative.py` is deterministic by design).
- [ ] `docs/api-reference.md` + `docs/config-reference.md` + `docs/cross-client-invariants.md` updated.

## HLD

### Components touched
`backend/trade_service.py` (TradeCard field + populate in `_generate_for_pair_v2`), `backend/trade_narrative.py`, `backend/server.py` (new angles route; badge data can reuse `/api/tiers/community-diff` + rankings payloads), `backend/feature_flags.py` (new flag key), `web/js/app.js` + `web/index.html` + `web/positional-tiers.html`, `mobile/src/screens/{TiersScreen,LeagueScreen}.tsx`.

### Data flow
Session init builds the universal pool + seed → angles route reads session `service.get_rankings()` (user Elo with overrides/swipes), seed from `_get_universal_pool(fmt)`, and `member_rankings` rows for leaguemates → computes diffs server-side → clients render. Trade path: `_generate_for_pair_v2` already holds `user_value` and `_vo` per candidate; it stamps `diff_highlights` on the card at construction; `build_narrative` consumes it.

### Flags & config interplay
- `tiers.community_diff` (exists, false): tiers overlay + diff badges.
- New `trade.diff_angles` (proposed): angles list + card narrative hooks.
- Interacts with `trade.outlook_blend` (ON): user values used by the *engine* are outlook-blended; badge/angle diffs should use **pre-blend** values so the diff reflects opinion, not strategy. Document this distinction on the #20 transparency page.
- Config keys (new, `model_config`): `diff_badge_min_pct` (default 0.15), `diff_badge_min_comparisons` (3), `angles_max_per_list` (10).

## LLD

### Engine/backend changes
- `TradeCard`: add optional `diff_highlights: list[dict]` (`{player_id, side, user_value, other_value}`). Populate in `_generate_for_pair_v2` when building cards from heap entries (values available via `user_value[pid]` and `_vo(pid)`); the v3 path (`trade_optimizer.generate_pair_trades_v3`) needs the same stamp (verify field availability there).
- `trade_narrative.build_narrative`: new sentence template, e.g. "You rate {recv_name} {pct}% above {opponent}'s number — that gap is the deal." Only when highlights exist and flag ON.
- New helper `compute_diff_angles(user_rankings, seed_elo, league_members_rankings, rosters, players, cfg)` — pure function, lives in `backend/server.py` or a small `backend/diff_angles.py` module (preference: new module, mirroring `trade_narrative.py` precedent).

### API changes
- `GET /api/league/diff-angles?league_id=...` (session-authed, format from `_active_format(sess)`):
```json
{
  "scoring_format": "1qb_ppr",
  "buy_low":  [{"player_id": "4034", "name": "...", "position": "RB",
                "your_value": 3100, "market_value": 2300, "diff_pct": 0.35,
                "rostered_by": "twilson2320", "holder_view": "below_market"}],
  "sell_high": [{"player_id": "6786", "name": "...", "position": "WR",
                 "your_value": 1500, "market_value": 2400, "diff_pct": -0.38,
                 "best_payer": "bkey5"}]
}
```
- `trade_card_to_dict`: serialize `diff_highlights` only when present (follow the `likes_you`/`sweetener` only-when-truthy pattern).
- Badges: extend `/api/rankings` rows with `community_elo` (gated on `tiers.community_diff`) rather than a second round-trip (verify payload size impact on mobile).

### Schema changes
None. All inputs exist (`member_rankings`, universal seed, session rankings).

### Client changes
- `web/js/app.js`: badge renderer + angles panel; `web/positional-tiers.html` overlay already consumes the community-diff route.
- `mobile/src/screens/TiersScreen.tsx` (badges), `LeagueScreen.tsx` (angles section), `mobile/src/api/` client for the new route.

### Rollout (flag name proposal, default state)
- Flip `tiers.community_diff` → true once badge thresholds verified against real data (it's been dark since the 2026-04-19 sprint; QA the overlay first).
- New flag `trade.diff_angles`, default false; add to `FLAG_KEYS` and `config/features.json`.

### Open questions
1. Should badge diffs use pre-outlook-blend values (recommended) — confirm no client currently displays blended values anywhere that would contradict.
2. Buy-low list across *all* leaguemate rosters can be large — cap per position or overall?
3. Does the v3 optimizer expose per-side per-player values cleanly enough to stamp `diff_highlights` without recompute? (verify)

## Dependencies & sequencing
No hard dependencies; pure presentation over shipped engine math, threadable through Waves per the backlog's sequencing view ("#9 threaded throughout"). Synergies: #13 (ranking gamification — angles are the payoff message), #16 (confidence ranges share the "rank more, learn more" loop), #17 (player profile shows the per-player diff this computes — share the helper), #20 (transparency page documents the divergence rule this makes visible). Feeds #56 (multi-source ADP) later as an extra lens.
