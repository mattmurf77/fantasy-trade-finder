# 14. League power rankings + team audit page
> Tier 1 · #14 · NEW · Effort M · Sources: GM/DD/DDr (folds #21 home rank chips, #85 tier naming)

## Summary

Every serious competitor ships a league power-rankings view; DynastyGM's is the benchmark: stacked positional value bars per team, tap-through team drill-down with collapsible position groups whose headers carry count, group value, and league rank (`QUARTERBACKS (5) — 6,535 (3/12)`), a Draft Picks group, and color-coded rank chips on the home league list (`1 / 14` green → `10 / 12` red). FTF computes every input already — `analyze_roster_strengths` profiles each roster's tier depth/needs/surplus during candidate generation, `dynasty_value`/`elo_to_value` price every player, and `draft_picks.pick_value` covers pick capital — then throws it all away after generating cards.

FTF's version adds the one thing no competitor can copy: a **dual view** of the same league, priced by consensus *or* by the user's personal Elo. "By market, you're 6th. By your own rankings, you're 3rd — these three teams are overrated by the market you trade in." That is the power-rankings page as a divergence instrument, not a leaderboard. The page is also the natural home for #1's outlook tier chips (named with personality per #85, consistent with the existing outlook enum `championship | contender | not_sure | rebuilder | jets` in `league_preferences.team_outlook`) and the visual feeder into trade discovery ("they're 11th in RB value and rebuilding — here's the deal"). Web page first, mobile screen second; home league cards get rank chips from the same computation (#21).

## PRD

### Problem & user story
As a league member, I want to see where every team stands — overall and per position, in market values and in *my* values — so I can spot trade partners and know my own window. Today FTF has no league-wide standings surface at all; the engine knows the answers but never shows them.

### Goals / Non-goals
**Goals**
- League power-rankings page: stacked positional value bars (QB/RB/WR/TE/Picks) per team, ranked list with totals.
- Team drill-down: position-group cards with count, group value, group league rank; per-player values; pick group (summary from #15's data).
- Basis toggle: consensus vs your-Elo, league-wide.
- Tier chips per team from #1's outlook classifier when available.
- Rank chips on home league cards (web league picker + `mobile/src/screens/LeaguePickerScreen.tsx`).

**Non-goals**
- No playoff odds simulation (#32) or season projections — value-based only.
- No standings/record ingestion in v1 (record feeds #1's classifier, not this page) (verify what Sleeper standings data session_init already pulls).
- No team-vs-team comparison tool (#28).

### Functional requirements
- FR1: `compute_power_rankings(league, players, basis, scoring_format)` returns, per member: total roster value, per-position group `{count, value, rank}`, pick capital `{count, value, rank}` (from `draft_picks`), overall rank, and tier-depth counts (reusing `analyze_roster_strengths` bins: `_TIER_ELITE`/`_TIER_STARTER`/`_TIER_BENCH`).
- FR2: Basis `consensus` prices every player via `elo_to_value(seed_elo)` from the universal pool; basis `personal` prices every roster in the league with the *requesting user's* shrunk Elo (`_shrink_user_elo`) — same value space the v2 engine trades in.
- FR3: Ranks are dense (1..N) per metric; ties broken by total value then username for determinism.
- FR4: Tier chip per team: #1 classifier output when shipped; until then, the user's own team shows their stored `team_outlook` from `league_preferences`, other teams show no chip (never fabricate).
- FR5: Rank chips: each league card on home shows `overall_rank / league_size`, color-banded green/amber/red (thresholds in `docs/cross-client-invariants.md`; proposal: top third green, middle amber, bottom red — DynastyGM precedent).
- FR6: Results cacheable per (league, basis, format) with an `updated_at` timestamp + manual refresh affordance (DynastyGM shows per-screen sync timestamps; backlog #36).
- FR7: Drill-down rows link to player profiles (#17) once those exist.

### UX notes
- **Web:** new page `web/league-rankings.html`, linked from the league tab in `web/index.html` (same pattern as the `positional-tiers.html` tab link). Stacked bars in plain CSS/JS per the vanilla-stack convention; position color palette must match existing tier colors per `docs/cross-client-invariants.md` — do not invent a new palette.
- **Basis toggle** is the hero control, top of page: "League by Market / League by You." Default: consensus (defensible numbers first; personal view is the hook).
- **Mobile:** new `mobile/src/screens/LeagueRankingsScreen.tsx`, registered in `mobile/src/navigation/` (per root CLAUDE.md convention), entered from `LeagueScreen.tsx`. Bars become horizontal for thumb-scroll.
- Drill-down header format copies the benchmark: `RUNNING BACKS (7) — 12,480 (2/12)`.
- Chips on `LeaguePickerScreen.tsx` and the web league list; tapping a chip deep-links to this page.

### Success metrics
- Page reached by ≥40% of users who open a league in week 1.
- Basis toggle used in ≥25% of page views (validates the differentiator).
- Click-through from a team drill-down to trade generation (CTA "find trades with this team") ≥10% of drill-down views.

### Acceptance criteria
- [ ] Totals on the page reconcile with the values the v2 engine uses for the same rosters (same `elo_to_value` space, same format handling).
- [ ] Personal basis with zero user rankings ≈ consensus basis (shrinkage guarantees this) — verified by test.
- [ ] Pick group totals match `/api/league/picks` data for the same league.
- [ ] Superflex leagues rank QB groups using `sf_tep` seed (universal pool is per-format).
- [ ] Rank chips render on web + mobile league cards and agree with the page.
- [ ] `docs/api-reference.md`, `docs/cross-client-invariants.md` (chip colors, tier names), `docs/glossary.md` ("power rank", "basis") updated.

## HLD

### Components touched
New `backend/power_rankings.py` (pure computation; mirrors how `trade_service` keeps math out of routes), `backend/server.py` (route), `web/league-rankings.html` (+ link from `web/index.html`, shared `web/css/styles.css`), `web/js/app.js` (league-card chips), `mobile/src/screens/LeagueRankingsScreen.tsx`, `mobile/src/screens/LeaguePickerScreen.tsx`, `mobile/src/navigation/`.

### Data flow
Session holds `league.members` with rosters (synced from Sleeper; persisted in `league_members.roster_data`). Route loads members + universal seed (+ requester's rankings for personal basis) + `draft_picks` rows → `compute_power_rankings` → JSON. Chips: a slim variant (overall rank only) computed on demand per league and cached server-side (TTL ~1h) so the home list doesn't trigger N full computations.

### Flags & config interplay
- New flag `league.power_rankings` (default false) gates route + UI.
- Reads `trade.outlook_blend`-style config only indirectly: values are **un-blended** (a power ranking is a wealth measure, not a window-adjusted measure; #1's chips carry the window signal instead).
- #85 tier naming lands here: display names for outlook tiers defined once in `docs/cross-client-invariants.md` (the `jets` enum value is the personality precedent already in the codebase).

## LLD

### Engine/backend changes
- `backend/power_rankings.py`: `compute_power_rankings(members, players, seed_elo, user_elo_or_none, confidence, picks_by_owner, scoring_format) -> dict`. Reuses `elo_to_value`, `_shrink_user_elo` (import from `trade_service`), `analyze_roster_strengths` for tier-depth annotation. No engine behavior changes.
- Chip cache: module-level dict keyed `(league_id, format)` with timestamp; invalidated on league re-sync.

### API changes
- `GET /api/league/power-rankings?league_id=...&basis=consensus|personal` (session-authed):
```json
{
  "league_id": "12345", "basis": "personal", "scoring_format": "sf_tep",
  "updated_at": "2026-06-11T17:02:00Z",
  "teams": [{
    "user_id": "u1", "username": "bkey5", "overall_rank": 1, "total_value": 60251,
    "tier": null,
    "groups": {
      "QB":   {"count": 5, "value": 6535, "rank": 3},
      "RB":   {"count": 7, "value": 12480, "rank": 2},
      "WR":   {"count": 9, "value": 18990, "rank": 1},
      "TE":   {"count": 3, "value": 2210, "rank": 6},
      "PICKS":{"count": 20, "value": 29988, "rank": 1, "summary": "9 1st, 4 2nd, 4 3rd, 3 4th"}
    },
    "players": [{"player_id": "4034", "name": "...", "position": "RB", "value": 6116, "pos_rank": "RB2"}]
  }]
}
```
- `GET /api/league/rank-chip?league_id=...` → `{"rank": 5, "size": 12, "basis": "consensus"}` (cheap, cached; consumed by league cards). Alternative: enrich `/api/leagues` — but that route currently returns only the active session league (verified), so a dedicated chip endpoint callable per league id is cleaner for the picker.

### Schema changes
None required. Optional later: a `power_rank_cache` table if the in-memory cache proves insufficient across Render restarts — defer.

### Client changes
- `web/league-rankings.html` — standalone page, inline `<style>` using the established `:root` palette (`--bg:#0f1117` etc., as in `web/ranking-method.html`), fetches the route, renders bars + drill-down accordions.
- `web/index.html` league tab link; `web/js/app.js` chip on the league card.
- `mobile/src/screens/LeagueRankingsScreen.tsx` + nav registration; chip on `LeaguePickerScreen.tsx`.

### Rollout (flag name proposal, default state)
`league.power_rankings`, default false. Ship web behind flag → flip after QA → mobile screen in the following release (EAS → TestFlight per deploy convention). Chips ship with the same flag (they advertise the page; no page, no chips).

### Open questions
1. Personal basis prices *opponent* rosters with the user's Elo — players the user never ranked sit at consensus via shrinkage; is that legible enough, or should unranked players be visually marked in drill-down?
2. Pick-value scale: `draft_picks.pick_value` (mid-1st ≈ 67.5 from `compute_pick_value`) is not on the player 0–10000 value scale — #15 must reconcile before the Picks segment can sit in the same stacked bar (see 15-pick-capital-dashboard.md). Until then, render Picks as a separate column, not a bar segment.
3. Chip basis: consensus only, or user-personal? Consensus recommended (stable across league members; chips may eventually be public-facing).

## Dependencies & sequencing
- **Feeds on:** #1 (outlook classifier) for opponent tier chips — page ships without chips, chips light up when #1 lands; #15 for the pick-capital group (shared data; agree on scale first); #85 naming decision at chip time.
- **Feeds:** #5 (post-trade impact preview reuses per-position group values + ranks — build `compute_power_rankings` so #5 can call it with hypothetical rosters), #17 (drill-down rows link to profiles), #21 shipped here, #23/#49 (cross-league portfolio views reuse the chip computation).
- Wave 3 per the backlog sequencing; safe to build the computation module any time since it's read-only.
