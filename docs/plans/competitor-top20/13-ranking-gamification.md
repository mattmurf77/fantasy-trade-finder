# 13. Ranking gamification: streaks, goals, coverage, leaderboard

> Tier 1 · #13 · ENH · Effort M · Sources: DDr (Vote Hub streaks/leaderboard) / FTF (cold-start watch item)

## Summary

DynastyDealer gamifies its data engine — the Vote Hub's Start/Sit/Drop game runs a streak mechanic, daily vote counter, and top-voter leaderboard (top voter: 3,393 votes) — because crowdsourced values die without volume. FTF's 3-player matchup ranking *is* its data engine, and the trade-engine-v2 cold-start watch item makes the stakes concrete: the divergence engine needs 2+ ranking sets per league, and per-player comparison counts (`confidence`) directly drive engine quality through shrinkage (`w = n/(n + shrink_pseudocount)`, pseudocount 4) and value-range width (`range_base/√(1+n)`, base 0.35) — which feed the range-overlap fairness gate. Ranking volume is an engine-quality input, not vanity engagement.

Crucially, FTF already shipped the skeleton: streaks (`get_user_streak`, advanced inside `record_event`; `GET /api/me/streak`; the 🔥 streak chip + toast in `RankScreen.tsx`), a leaderboard (`GET /api/leaderboard?scope=league|universal&metric=streak|ranks&window=...`, with `LeaderboardsSection.tsx` on mobile), per-position progress (`GET /api/progress`), and league-mate ranking coverage (`GET /api/league/coverage` + the web coverage-row with invite button). What's missing is the *loop*: a daily goal that points effort where the engine needs it ("12 matchups refines your RB curve"), coverage meters that show rankings as a quality input rather than a chore, and — the piece no competitor has — reward framing tied to output quality: "Your rankings updated — 3 new trade angles found." Streak says *come back*; this says *here's what coming back bought you*.

## PRD

### Problem & user story

> As a user, I want a reason to rank a few matchups every day and proof it's doing something, so refining my values feels like sharpening the tool rather than feeding the app.

The existing streak chip rewards consistency but is disconnected from output: nothing tells the user that 12 more RB matchups tighten their RB value ranges, unlock divergence trades, or surface new cards.

### Goals / Non-goals

**Goals**
- Daily goal per league: a target matchup count, aimed at the positions where the user's confidence is thinnest.
- Ranking-coverage meters: how well the user has ranked the players that matter in *this* league (their own and league-mates' rosters), per position.
- Goal completion triggers a trade-deck refresh and reports the delta: "N new trade angles found."
- League leaderboard of ranking activity surfaced prominently per league (machinery exists; placement/copy is the work).
- All reward copy tied to output quality, never bare points.

**Non-goals**
- No badges/points/levels economy (the `league.unlock_badges_per_member` dark flag stays a separate decision).
- No changes to Elo math, K-factors, or matchup selection (the smart matchup generator keeps choosing trios; the goal *counts*, it doesn't *select* — see open question 1).
- No streak redesign (mechanic exists; we add a goal layered on it).
- No push notifications in v1 (that's #18; #88 is the push variant of coverage prompts).

### Functional requirements

- FR1: Daily goal = `daily_goal_matchups` (config, default 12) rank3 submissions per local day, scoped per league+format; progress visible on the rank screen ("7/12 today").
- FR2: Goal card names the payoff position: the position whose league-relevant players have the lowest mean comparison count `n` for this user — copy template "12 matchups refines your {POS} curve." Computed from the same per-player confidence counts the engine's shrinkage uses.
- FR3: Coverage meter per league: % of league-rostered players (rosters from league sync) the user has compared at least `coverage_min_n` times (config, default 3 — below that, shrinkage holds them ≈ consensus). Per-position breakdown on tap. Distinct from `/api/league/coverage`, which counts *league-mates who rank*; this measures *the user's own sample over the league player pool*. Both render together: "Your coverage" + "League coverage."
- FR4: On goal completion: server kicks (or client triggers) a fresh trade job; response compares new deck against the user's recent `trade_impressions` asset-set keys and reports the count of genuinely new cards → "Your rankings updated — 3 new trade angles found." Zero-delta copy stays honest: "Rankings sharpened — no new angles yet, your values are stabilizing."
- FR5: League leaderboard of ranking activity (existing `metric=ranks`, `scope=league`) gets a first-class slot on the league screen (web + mobile) with self-row anchoring (`get_self_leaderboard_row` exists).
- FR6: Streak chip remains; goal completion is the streak's daily qualifying event where possible (a goal-day always also extends the streak since both key off rank events — verify event-type overlap with `_RANK_STREAK_EVENTS`).
- FR7: All counters derive from existing `user_events` rank-class events — no double-write; a missed goal has no penalty state beyond the unfilled meter.
- FR8: Flag off → current behavior byte-identical (streak chip et al. unaffected — they're already shipped surface).

### UX notes

- **Mobile** (`RankScreen.tsx`): goal ring next to the existing streak chip; completion micro-celebration → "finding new angles…" → result toast deep-linking to `TradesScreen`. `LeagueScreen.tsx`: coverage meters + leaderboard module (`LeaderboardsSection.tsx` precedent; `ContrarianLeaderboard.tsx` shows a second flavor exists).
- **Web** (`web/index.html` + `web/js/app.js`): goal ring on the ranking view; coverage meters beside the existing coverage-row (which keeps its invite button — *league* coverage low → invite is still the fix, per the #37 growth lever).
- Tone per repo norms: quality-framing, light on fire emojis beyond the existing streak chip. The leaderboard is "most market-shaping rankers," not "top grinders."
- Empty/cold states matter (Tier-5 #81): a brand-new user's coverage meter starts near zero — frame as map-filling ("You've mapped 12% of this league's players"), not failure.

### Success metrics

- Median daily rank3 submissions per active user (primary — this is the engine input).
- Leagues with ≥2 members holding established rankings (the cold-start watch item, directly).
- D7/D30 retention of users who complete ≥3 goals in week 1 vs matched non-completers.
- Goal→trade-screen click-through on the "new angles" toast (proves the loop reads as causal).
- Mean per-player confidence `n` on league-rostered players (range tightening, feeds #16's display).

### Acceptance criteria

- [ ] Goal progress counts only rank-class events for the active league+format and resets on the user's local day boundary (same convention as streak's `last_rank_local_date`).
- [ ] Payoff-position selection matches lowest mean confidence (unit test on fixture confidence maps).
- [ ] Coverage % matches a hand-computed fixture league; per-position breakdown sums correctly.
- [ ] New-angle count: cards whose (give,receive) asset-set key is absent from the user's last `angle_lookback_days` of `trade_impressions` (test with seeded impressions).
- [ ] Leaderboard module renders league scope with self-row; no change to `/api/leaderboard` contract.
- [ ] Flag off → no new UI, no new endpoints called.
- [ ] `docs/api-reference.md`, `docs/config-reference.md`, `docs/glossary.md` ("coverage", "trade angle"), `docs/cross-client-invariants.md` (goal size + copy templates if shared) updated.

## HLD

### Components touched

`backend/server.py` (two new routes + goal-completion deck-delta helper), `backend/database.py` (queries over existing `user_events`/`trade_impressions`; one small prefs addition at most), `backend/ranking_service.py` (read-only: expose per-player comparison counts if not already queryable — confidence counts currently flow into trade generation; verify the cleanest read path), `mobile/src/screens/RankScreen.tsx`, `LeagueScreen.tsx`, `mobile/src/api/rankings.ts` + `leaderboard.ts`, `web/js/app.js`.

### Data flow

`POST /api/rank3` already calls `record_event` (which returns post-event streak inline — `RankScreen` consumes it today). Extend the same inline response with goal progress (`goal: {done: 7, target: 12, position: "RB"}`) so no extra polling. Goal completion → client calls `POST /api/trades/generate` (existing) → on completion, client calls `GET /api/rankings/goal/angles` which diffs the fresh deck against recent `trade_impressions` (`load_recent_*` accessors exist for impressions) → toast. Coverage: `GET /api/rankings/coverage?league_id=...` aggregates league rosters × user confidence counts, cacheable ~5 min like `_leaderboard_cached`.

### Flags & config interplay

- New flag `rankings.daily_goal` (default `false`). Note: this introduces a `rankings.*` namespace — existing groups are swipe/tiers/trades/league/invite/mobile/profiles/landing/trade_math/trade_engine/trade; a ranking-loop feature fits none of them, and `_key_to_attr` handles any dotted key, so the new group is mechanical. Coverage meters + leaderboard placement can ride the same flag (one coherent surface) — split only if rollout needs it.
- Config keys (`model_config` + `_DEFAULT_CFG` is for trade engine; these are server-side knobs — house in `model_config` via the ranking-service config pattern, which already loads `elo_k` etc.): `daily_goal_matchups` (12), `coverage_min_n` (3), `angle_lookback_days` (7, matching `diversity_window_days`' lookback spirit).
- Interplay: #16 (confidence ranges) is the same confidence data displayed on values — copy should agree ("more matchups tighten your ranges"). #37 (invite flow): league-coverage low-state keeps routing to invites; the two meters must not blur (yours vs your league's). `swipe.qc_compliments` (ON) already injects QC trios into ranking — goal counting includes them (they're rank3 submissions) — fine, they're throttled (QC-trio throttle 100/operator).

## LLD

### Engine changes

None to ranking or trade math. The feature *reads* engine internals and *feeds* them volume:

- Confidence counts: per-player comparison counts for the goal's payoff position and coverage meter — same data the server passes as `confidence` into `generate_trades_v2` (used by `_shrink_user_elo` / `_value_uncertainty`). Reuse that read path in the new endpoints; do not re-derive from raw swipe rows in route code. (verify exact accessor name in `server.py`'s job setup)
- New-angle diff: pure query — fresh job's cards vs `trade_impressions` rows for (user, league) within `angle_lookback_days`, keyed on `frozenset(give) + frozenset(receive)` (the same set-key idea `_past_decision_keys` uses in `TradeService.__init__`).

### API changes

```
GET /api/rankings/coverage?league_id=...
→ {"overall": 0.42, "by_position": {"QB": 0.61, "RB": 0.33, "WR": 0.45, "TE": 0.38},
   "thinnest_position": "RB", "rostered_players": 142, "covered": 60}

GET /api/rankings/goal?league_id=...
→ {"target": 12, "done": 7, "position": "RB",
   "copy": "12 matchups refines your RB curve", "completed_today": false}

GET /api/rankings/goal/angles?league_id=...&job_id=...
→ {"new_angles": 3, "sample": [{"trade_id": "...", "target_username": "..."}]}
```

Plus payload delta: `/api/rank3` inline response gains `goal` next to the existing inline `streak`. No changes to `/api/leaderboard` or `/api/me/streak`.

### Schema changes

None required for counting (derives from `user_events` + `trade_impressions`). One optional addition if per-user goal sizing ships later: a `goal_target` column on an existing prefs row — deferred; v1 is one global config value. (The no-new-tables shape is a feature: SQLite/Postgres parity is free.)

### Client changes

- `mobile/src/api/rankings.ts`: `getCoverage`, `getGoal`, `getGoalAngles`; `RankScreen.tsx`: goal ring + completion flow (extends the existing inline-streak handling at the rank3 response); `LeagueScreen.tsx`: coverage module + ranks-metric leaderboard slot.
- `web/js/app.js`: goal ring on ranking view; coverage meters adjacent to the existing `coverage-row`; leaderboard rendering for `metric=ranks&scope=league`.
- New shared copy strings documented once (cross-client invariants) since the goal copy template renders on both clients.

### Rollout

Flag `rankings.daily_goal`, default `false`. Order: coverage + goal endpoints dark → web surface (fast iteration on copy) → mobile → enable for operator league → watch submission volume and the zero-new-angles rate (if most completions find 0 angles, tune `angle_lookback_days` or the copy before broad enable). Cheap to ship before the seasonal traffic window; compounds with every later feature (better Elo → better everything).

### Open questions

1. Should the daily goal *bias matchup selection* toward the thin position (the smart matchup generator / `smart_matchup_enabled` path could take a position hint)? Big quality win, but touches the trio-selection flow — proposal: v2, after v1 proves the count-only goal moves volume.
2. Goal scope: per league+format (proposed) vs global per user. Multi-league users could face 4 goals/day — consider a global cap or "primary league" goal.
3. Anti-gaming: rapid random swipes inflate counts and *pollute Elo*. The QC-trio mechanism (`swipe.qc_compliments` infrastructure) already measures consistency — should goal credit require passing QC rate? Lean yes, silently (don't advertise the check).
4. Leaderboard psychology in small leagues: a 12-person league with 2 rankers makes a thin leaderboard — minimum-participant threshold before the module renders? (Empty-state polish, #81.)
5. Does the "new angles" job kick respect the `_PREGEN_TTL_SECONDS` cache (a 30-min-fresh job returns instantly with *old* cards → 0 new angles, falsely)? Likely needs `_invalidate_trade_jobs` on goal completion or an explicit freshness bypass — decide with latency data. **(verify cache behavior in this flow)**

## Dependencies & sequencing

- **Attacks the cold-start watch item directly**; pairs with **#37** (invite flow) — invites raise league coverage, goals raise own coverage; the league screen shows both levers side by side.
- **Feeds #16** (confidence ranges): same confidence counts, same "more matchups tighten your ranges" story — ship #16's display before or with this so the payoff claim is visible in the product.
- **Feeds #9** (community-diff angles): divergence angles literally require the ranking volume this generates.
- **#88/#18**: push variants ("league-mate ranked 20 matchups — divergence map updated") wait for push infra.
- Independent of #1–#4; Wave 2 in backlog sequencing.
