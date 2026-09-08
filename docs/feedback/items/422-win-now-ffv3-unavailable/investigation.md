# FB-422 — investigation: why Win Now refuses FFV3

**Date:** 2026-09-08 · **Planner:** G-422 investigating planner (read-only on code) · **Branch:** `claude/feedback-422-428` at `b8d37085`

**Report:** #422, mattmurf77, 2026-09-06 17:50:36Z, app 1.17.1 (149), screen WinNow: "Winnow still not working on ffv3". Filed 17 s after the server answered `GET /api/league/season-projections?league_id=1312140920132497408` with **200 / 98 bytes** at 17:50:19Z, preceded (17:50:09–17:50:18Z) by 17 Sleeper projection fetches (`/projections/nfl/2026/1..17`).

## 1. Verdict in one paragraph

FFV3 is refused by design, not by a bug in #420's fix. Its starting lineup is `QB RB RB WR WR TE FLEX K DL DL LB LB DB DB IDP_FLEX` (15 active slots, 8 of them K/IDP). The Win Now simulator only models QB/RB/WR/TE lineups (`backend/season_simulator.py:21-23` `SLOT_POSITIONS`) and refuses any league whose active slots fall outside that set or exceed 12 (`:54-56` → `unsupported_roster_slots`). `win_now_service.load_bundle` turns the first simulator reason into `Unavailable("unsupported_roster_slots")` (`backend/win_now_service.py:261-263`), whose auto-generated message is the literal string **"Unsupported roster slots"** (`:34-38`). The route serialises that as `{"message":"Unsupported roster slots","reason":"unsupported_roster_slots","status":"unavailable"}` + newline = **exactly 98 bytes** (`backend/win_now_api.py:48-49`, Flask compact + sorted keys). The phone rendered that four-word string under `win-now.unavailable` (`mobile/src/screens/WinNowScreen.tsx:195`) with nothing else — which the user reasonably read as "still not working". Two real defects follow: (a) the message is opaque and says nothing about *what* is unsupported or whether anything can be done; (b) the server spends ~10 s fetching 17 weeks of projections *before* discovering a slot shape it could have refused from the league metadata alone.

## 2. Evidence tiers

| Tier | Evidence | Result |
|---|---|---|
| 1 — production | Render log 2026-09-06 17:50:19Z, 200 / **98 bytes** for FFV3; 17 projection fetches immediately before | Size matches only three reasons with auto-messages: `unsupported_roster_slots`, `missing_scoring_settings`, `missing_forecast_week:17`. FFV3 has 55 scoring keys (rules out #2); week 17 was fetched and Lakeview's identical fetch burst produced week-17 rows (rules out #3). |
| 1 — local reproduction | `service.load_league` + `service.load_bundle` executed unmodified against live public Sleeper data for FFV3 (scratch SQLite; `python3 scratchpad/repro.py`, 2026-09-08) | `load_league OK … slots=['QB','RB','RB','WR','WR','TE','FLEX','K','DL','DL','LB','LB','DB','DB','IDP_FLEX']` → `load_bundle REFUSED reason='unsupported_roster_slots' message='Unsupported roster slots' body_bytes=98 projection_weeks_fetched_before_refusal=17 elapsed=32.7s`. `season_simulator._validate` returned exactly `['unsupported_roster_slots']` — no second reason. |
| 1 — comparison league | Same script on Lakeview `1312076055586050048` | `load_league OK … slots=[QB,RB,RB,WR,WR,WR,TE,FLEX,FLEX,SUPER_FLEX]` → `load_bundle REFUSED reason='unknown_starter_availability:1:1' body_bytes=114` — **byte-identical to the 17:57:29Z production response (114 bytes)**. See §6: Lakeview was *also* unavailable that day, for a different, transient reason. |
| 2 — design intent | `docs/plans/win-now/BUILD.md:78` "active K/DEF/IDP formats remain unsupported"; `HISTORICAL-VALIDATION.md:34` "FFv3 starts kickers and IDP players, which the current player model does not support"; `PROPOSAL.md:80` | The refusal is the specified behaviour; only its wording and cost are wrong. |
| 2 — public league facts | `curl api.sleeper.app/v1/league/1312140920132497408` (+ `/rosters`, `/users`, `/matchups/1`, `/state/nfl`) | 12 teams, `in_season`, 2026, `playoff_week_start` 15, `playoff_teams` 6, `league_average_match` 0, `divisions` 0, `playoff_seed_type` 0, `playoff_round_type` 0, `best_ball` 0, `start_week` 1, `trade_review_days` 0, `trade_deadline` 12; all rosters 0-0-0; week-1 matchups 6 pairs, 0 points; mattmurf77 = user `313560442465169408` owns roster 1. Scoring includes 12 `idp_*` and 9 kicker keys. |

## 3. Every `reason` the route can return, in evaluation order

`GET /api/league/season-projections` (`win_now_api.py:76-93`) → `service.load_bundle` (`win_now_service.py:212`) → `load_league` (`:90`) → `_forecast_batch` (`:183`) → `simulate_season`. `build_context` failures (`:288`) are swallowed at `win_now_api.py:85-90` — standings still return. Anything else propagates through `guarded` (`:51-64`).

| # | reason | Raised at | Trigger |
|---|---|---|---|
| 1 | `platform_unsupported` | `win_now_service.py:93-94` | actor platform ≠ sleeper |
| 2 | `source_unavailable` | `:79-82` (`_fetch`) | Sleeper fetch raised / non-JSON |
| 3 | `league_unavailable` | `:99-100` | meta not dict or no rosters |
| 4 | `season_not_active` | `:101-102` | `status` ≠ `in_season` |
| 5 | `best_ball_unsupported` | `:104-105` | `settings.best_ball` |
| 6 | `custom_start_week_unsupported` | `:106-107` | `start_week` ≠ 1 |
| 7 | `league_membership_unavailable` | `:108-110` | viewer owns ≠ 1 roster |
| 8 | `missing_scoring_settings` | `:111-112` | empty `scoring_settings` |
| 9 | `standings_not_final` | `:118-122` | W+L+T not a multiple of decisions/week, or rosters disagree on completed count |
| 10 | `postseason_in_progress_unsupported` | `:125-126` | completed ≥ regular-season weeks |
| 11 | `multiweek_playoffs_unsupported` | `:131-132` | `playoff_round_type` ≠ 0 |
| 12 | `ambiguous_roster_ownership` | `:138-139` | a player id on two rosters |
| 13 | `incomplete_schedule` | `:153-154`, `:157-158` | matchup rows ≠ team count, or null `matchup_id` |
| 14 | `live_week_unsupported` (msg A) | `:160-161` | nonzero points in the next week's matchups |
| 15 | `schedule_format_unsupported` | `:162-163` | a matchup_id with ≠ 2 rosters |
| 16 | forecast reasons: `missing_forecast_week:W`, `projection_fetch_failed:W`, `invalid_projection_response:W`, `projection_horizon_mismatch:W`, `invalid_game_date:W`, import errors | `:219-220` (first of `forecasts["reasons"]`), produced in `season_forecasts.py:212-299` | projection feed gaps |
| 17 | `game_start_cutoff_unavailable` | `:226-227` | feed carries no game date/kickoff at all |
| 18 | `live_week_unsupported` (msg B) | `:230-231`, `:242-243` | earliest game date/kickoff ≤ now (**fires for every league from 2026-09-09 00:00Z until week 1 settles**) |
| 19 | `stale_forecasts` | `:246-247` | snapshot older than 900 s or in the future |
| 20 | simulator `_validate` reasons (alphabetical first wins): `best_ball_unsupported`, `duplicate_player_ownership`, `forecast_season_mismatch`, `incomplete_or_doubleheader_schedule:W`, `invalid_schedule:W`, `missing_scoring_settings`, `playoffs_exceed_nfl_horizon`, `roster_size_out_of_bounds`, `simulation_count_out_of_bounds`, `unsupported_division_seeding`, `unsupported_live_or_completed_state`, `unsupported_playoff_byes`, `unsupported_playoff_format`, `unsupported_playoff_rounds`, `unsupported_playoff_seed_type`, `unsupported_playoff_start`, `unsupported_postseason_or_checkpoint`, **`unsupported_roster_slots`**, `unsupported_standings_rules`, `unsupported_team_count` | `:261-263` via `season_simulator.py:42-99` (slots at `:54-56`) | league shape |
| 21 | lineup-coverage reasons: `missing_starter_forecast:R:W` (`season_simulator.py:199-200`), `unknown_starter_availability:R:W` (`:201-203`), `incomplete_lineup_coverage:R:W` (`:206-207`), `unknown_contributor_availability:R:W` (`:212-213`), `unsupported_scoring:KEY` (`season_forecasts.py:310-311`), `duplicate_player_week` | `:261-263` via `projected_lineup_points` (`season_simulator.py:181-224`) | per-team, per-week forecast coverage |
| 22 | `model_unavailable` | `:263` fallback | simulator unsupported with no reasons (unreachable in practice) |

Job/decision routes add `feature_disabled`, `stale_forecast(s)`, `ranking_inputs_changed`, `league_inputs_changed`, `valuation_inputs_changed`, `championship_not_validated`, `trade_review_delay_unsupported`, `pick_ownership_unavailable`, `job_expired`, `generation_failed` (`win_now_api.py:74,136,141,145,149,154,157,189`; `win_now_service.py:294-295,367-368,501-502,508-509,536-547`). None is on the #422 path.

**FFV3 hits #20 `unsupported_roster_slots` and nothing earlier.** Checks 1–15 all pass on FFV3's public data (verified by the local run: `load_league OK`). Had the slot check not fired, FFV3 would next have failed #21 with `unsupported_scoring:fgm_0_19` (kicker coefficients survive `normalize_scoring_for_slots` because `K` *is* an active slot — `season_forecasts.py:51-64`) and `missing_starter_forecast:1:1` (four of roster 1's eleven starters — ids 11665, 2393, 10880, 7841 — are K/IDP with no QB/RB/WR/TE projection row). There is no path on which FFV3 is supportable without a new position model.

**Why Lakeview does not trip it:** its active slots are `QB RB RB WR WR WR TE FLEX FLEX SUPER_FLEX` — 10 slots, all in `SLOT_POSITIONS`; no `K`/`DEF` slot, so `normalize_scoring_for_slots` strips its kicker/defense coefficients (`:60-63`).

## 4. Why the message is opaque

`Unavailable.__init__` (`win_now_service.py:34-38`) derives `message` from the reason (`replace("_"," ").capitalize()`) whenever the raiser passes none. Every explicit message in the file belongs to a *transient* condition (`:94,:102,:126,:161,:231,:243,:295`); the *permanent format* refusals (`best_ball_unsupported`, `custom_start_week_unsupported`, `multiweek_playoffs_unsupported`, and all simulator reasons) get the auto text. Mobile shows `baseline.message` verbatim when present (`WinNowScreen.tsx:195`); web does the same (`web/js/win-now.js:231`). Both entry points (`TradesScreen.tsx:6755-6758`, `LeagueSummaryScreen.tsx:1517-1520`) advertise Win Now for every league when the flag is on, so an unsupported league is invited in and then handed four words.

## 5. What #420/#421 guaranteed — and did not

#420's PRD §1 (`../420-win-now-loading/prd.md`) fixed a `409 session_not_initialized` recovery gap and a mislabelled 15 s client timeout, and states explicitly that "the captured evidence does **not** establish that the 200 body contained available forecasts". It never claimed FFV3 projections were available. #422 is the next layer down, not a regression: the client now reliably reaches the server and reliably renders whatever the server says — and the server says "Unsupported roster slots".

## 6. Adjacent finding — Lakeview was unavailable too (out of #422 scope; needs an operator call)

The 17:57:29Z Lakeview response (114 bytes) is byte-identical to `unknown_starter_availability:1:1`, reproduced locally: Lakeview roster 1 starts Tucker Kraft, Malik Nabers and Breece Hall, all tagged `Questionable` in Sleeper's week-1 feed. `fetch_projection_snapshot` maps *any* injury tag to `availability=None` (`season_forecasts.py:273-276`, deliberate per the comment) and `projected_lineup_points` refuses the whole league when any team's *listed starter* is unknown (`season_simulator.py:201-203`). In-season, some starter somewhere is almost always Questionable, so this policy will keep Win Now off for offense-only leagues most weeks, and the phone will show the equally opaque "Unknown starter availability:1:1". Changing the availability policy is a model decision, not a fast-track bug; recommended as a separate item (see PRD §7). Separately, from 2026-09-09 00:00Z every league returns `live_week_unsupported` (#18) until week 1 settles — expected, and the format refusal proposed here is ordered *before* it so FFV3's message is stable.

## 7. Fix decision

**(b) legitimate refusal → make it honest, specific and cheap.** (a) is rejected: modelling K/IDP needs a new projection position set, IDP/kicker stat keys in `SUPPORTED_SCORING_KEYS`, slot eligibility for `DL/LB/DB/IDP_FLEX`, and re-validation — the win-now plan docs call this "a separate model change requiring tests and re-evaluation". (c) is rejected: nothing is cached; `load_bundle` recomputes from source every call (only *successful* projection snapshots are stored, `win_now_store.py:41-55`), and the local run reproduced the refusal with an empty store. Details in `prd.md`.

## 8. Scratch artefacts (not committed)

`scratchpad/{ffv3,lakeview}/x*.json` (league/rosters/users/matchups 1–2), `scratchpad/state.json`, `scratchpad/repro.py`, `scratchpad/cache/*.json` (17 weeks of Sleeper projections, `traded_picks`). Sleeper's public API only; no credentials, no production database.
