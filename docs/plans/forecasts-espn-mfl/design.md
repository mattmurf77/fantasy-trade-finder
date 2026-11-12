# Rest-of-season forecasts for ESPN and MFL leagues — design

> Research + design only. Nothing here is built. Written 2026-11-11 on branch
> `feat/forecasts-espn-mfl` (cut from `origin/main` `fa83f57b`), designed on top of
> the open median-leagues PR #659 (`feat/projection-median-leagues`).
> Scope block: [scope.md](scope.md).

## Contents

1. [The ask](#1-the-ask)
2. [What exists today (verified)](#2-what-exists-today-verified)
3. [Dependency map](#3-dependency-map)
4. [Auth and scheduling reality](#4-auth-and-scheduling-reality)
5. [Recommended design](#5-recommended-design)
6. [Accuracy and evaluation](#6-accuracy-and-evaluation)
7. [Build plan](#7-build-plan)
8. [Open decisions for the operator](#8-open-decisions-for-the-operator)
9. [What could not be determined](#9-what-could-not-be-determined)

---

## 1. The ask

Operator, verbatim: "No. Add the MFL standings read to pull max PF and build rest of
season projections for both platforms." Earlier: "Can we just default to reverse order
of standings for ESPN leagues and max PF for MFL leagues? MFL has the stat and reverse
order of standings is the obvious assumption for ESPN with no good alternative."

Goal: the rest-of-season forecast (projected standings, playoff odds, projected
non-playoff draft order) runs for ESPN and MFL leagues, so next year's first-round
picks can be priced by projected slot on every platform. Draft-order rule:
**ESPN = reverse standings; MFL = lowest max PF ("potential points") first among
non-playoff teams; Sleeper unchanged (lowest max PF).** The rule is a per-league
setting with platform defaults, not hard-wired to platform.

## 2. What exists today (verified)

File names differ from the brief: the package is `provider.py`, `core.py`,
`simulation.py` (not `simulate.py`), `joint.py`, `batch.py`, `store.py`, `service.py`,
`api.py`, `scoring.py`, `timing.py`, `recommendation.py`. There is no
`season_points.py`; scoring keys live in `backend/season_forecasts.py`.

- **The whole forecast is dark.** `config/features.json:2-3`: `league.projections`
  and `league.projections_provider_approved` are both `false`.
- **Sleeper-only in four places:** `batch._bootstrap_connected` filters to
  `platform == "sleeper"` (`batch.py:127-129`); registration only on Sleeper
  session-init (`server.py:30307-30313`); `api.py:73-74` refuses a POST and
  `api.py:101-103` blanks the latest view with `sleeper_only`; `service._viewer_identity`
  requires a Sleeper binding (`service.py:26-33`) and `service.py:98` calls the one
  Sleeper `provider.capture`.
- **`provider.capture` (`provider.py:215-658`) is one 440-line function** that mixes
  Sleeper reads and reconciliation (215-333) with platform-free lineup building,
  free-agent fill and coverage (334-609), then reads traded picks (610-615) and
  re-reads the league to detect change (616-620).
- **Player projections are Sleeper stat lines**, not points. `SleeperExperimentalFeed`
  (`provider.py:52-192`) pulls `api.sleeper.app/projections/nfl/{season}/{week}`, and
  each row is scored with the league's `scoring_settings` keyed in **Sleeper's stat
  vocabulary** (`scoring.best_available`, `scoring.py:100-152`; key sets in
  `season_forecasts.py:21-48`). A missing key makes a player "partial", never zero
  (contract `sleeper_best_available_v1`, `config/league_projections.json`).
  So any ESPN/MFL league's scoring must be **translated into Sleeper stat keys**.
- **No team-defense slot.** `core.SLOTS` (`core.py:11-18`) has QB RB WR TE K FLEX
  SUPER_FLEX REC_FLEX WRRB_FLEX DL LB DB IDP_FLEX — **no `DEF`**. Any league that
  starts a team defense is refused `unsupported_lineup` (`provider.py:254-256`),
  Sleeper included. ESPN's default lineup starts a D/ST and a K.
- **The simulator hard-codes both orders:** standings sort is
  (record, PF, PA, lottery) (`simulation.py:257`) and non-playoff draft order is
  lowest simulated Max PF (`simulation.py:262`). Playoff-team draft positions are not
  projected (warning at `simulation.py:325`).
- **Max PF:** Sleeper's official season-to-date `ppts` is the floor
  (`provider.py:320-331`); weekly Max PF history is empty (`maxpf_history: []`,
  `provider.py:332`); remaining weeks are simulated jointly with the actual score by
  `joint.py`'s mean-preserving positive-gap construction (`simulation.py:164-231`).
- **PR #659 (median, not on main)** adds `core.league_format`, `core.median_outcomes`,
  reads `league_average_match` live at capture, books a second result per week in both
  the capture reconciliation and the simulator, a descriptive `leagues.median_game`
  column, and an operator `retry_unsupported` dispatch option. This design reuses
  `median_outcomes` for ESPN's "top-half win bonus" and `retry_unsupported` for the
  re-run after DEF support lands.
- **ESPN** (`backend/espn_service.py`): `fetch_league` (150) always requests
  `view=mTeam&view=mRoster&view=mSettings`; `parse_league` (510-563) keeps
  W/L/T/PF/playoffSeed/rankCalculatedFinal and `playoffTeamCount` only.
  `derive_espn_draft_order` (570-669) is the existing final-standings rule.
  No schedule, weekly scores, lineup slots, scoring rules, IR slot or tiebreak rule
  is parsed today, and **no ESPN read runs in the background** (`docs/integrations/espn.md`
  §5: "No polling, no webhooks, no background job hits ESPN").
- **MFL** (`backend/mfl_service.py`): reads `league`, `rosters`, `futureDraftPicks`,
  `players`, `rules`, `draftResults`, `pendingTrades`, `myleagues`. **No standings,
  schedule, weekly results or projections.** `_fetch_one` (308) cannot pass extra
  query params (`W=`), so a small `export_url` extension is needed. MFL **is** already
  read in the background: the hourly tick's draft-status sweep (≤50 leagues/tick,
  `docs/integrations/mfl.md` §5).
- **Player identity:** the DynastyProcess `db_playerids.csv` crosswalk
  (`espn_service.py:677-832`): ESPN → `by_espn_id`, MFL → `by_mfl_sleeper`, plus a
  position-strict name fallback. Team defenses are not in it (ESPN D/ST ids are
  negative; MFL defenses are `Def` rows with a team code like `KCC`); the import
  report treats K/DST as "out of pool", never crosswalk failures (`espn.md` §3.2).
  IDP coverage in the DP file was not measured in this repo.
- **Seat binding** for platform leagues lives on the single `leagues` row: the importer's
  `user_id` plus `espn_my_team_id` / `platform_my_team` (`database.py:591-650`,
  `upsert_espn_league` 17055). One linking user per league row.
- **Recorded fixtures:** `espn_league_snapshot_2026-07-11.json` and
  `espn_league_11896_standings_2026-08-08.json` are trimmed (no `scheduleSettings`
  beyond `playoffTeamCount`, no `rosterSettings`, no `scoringSettings`, no schedule);
  `mfl_league_snapshot_2026-07-17.json` has `league`, `rosters`, `futureDraftPicks`,
  `players` only. **Every new field this design reads is documented-only, not
  fixture-verified.**

## 3. Dependency map

"Sleeper source" cites `backend/league_projections/provider.py` unless noted. Status:
**have** = already read by us; **have-unparsed** = in a response we already fetch,
not parsed; **new** = new request; **n/a** = not available from the platform.
ESPN views are on `lm-api-reads.fantasy.espn.com/.../leagues/{id}`; MFL types are
`https://{host}/{year}/export?TYPE=…&L={id}&JSON=1`. Field names marked † come from
community libraries (cwendt94/espn-api, dynastyprocess/ffscrapr) or MFL's API page,
not from our fixtures.

| Input | Sleeper source (read at) | ESPN source | MFL source | Status ESPN / MFL |
|---|---|---|---|---|
| League size | `total_rosters` + rosters (226-227, 257-259) | `settings.size`, `teams[]` (`parse_league` 556) | `league.franchises.count` / `franchise[]` | have / have |
| Playoff team count | `settings.playoff_teams` (260) | `settings.scheduleSettings.playoffTeamCount` (parsed 561) | `TYPE=playoffBrackets` / `playoffBracket` (owners-only on private) — the `league` export has no documented playoff count | have / **new**; absent until the commissioner builds the bracket |
| Playoff byes | derived 2^k − p (268) | same derivation | same derivation | derived |
| Regular-season length | `settings.playoff_week_start − 1` (248) | `scheduleSettings.matchupPeriodCount` † + `matchupPeriods` † (map period → NFL weeks) | `league.lastRegularSeasonWeek` † (name unverified) | have-unparsed / have-unparsed |
| Start week | `settings.start_week` (243) | `matchupPeriods["1"]` † | `league.startWeek` † | have-unparsed |
| Current week | `/state/nfl` (219, 246-249) | `status.currentMatchupPeriod`, `scoringPeriodId` (seen in fixture) + Sleeper `/state/nfl` | Sleeper `/state/nfl` | have |
| Schedule (who plays whom, remaining weeks) | `/league/{id}/matchups/{w}` (298-300, `_games` 202) | `view=mMatchupScore` † → `schedule[]` `{matchupPeriodId, home.teamId, away.teamId}` | `TYPE=schedule` → `weeklySchedule[].matchup[].franchise[]` `{id, isHome}` † | **new** / **new** |
| Completed weekly scores | matchups `points` (272-295) | `schedule[].home/away.totalPoints`, `winner` † | `TYPE=schedule` `score`, `result` †, and `TYPE=weeklyResults&W=n` | **new** / **new** |
| Official standings (reconciliation target) | roster `settings.wins/losses/ties/fpts/fpts_against` (324-328) | `teams[].record.overall.{wins,losses,ties,pointsFor,pointsAgainst}` (parsed except PA) | `TYPE=leagueStandings` `h2hw h2hl h2ht pf pa` † (owners-only on private) | have / **new** |
| Rosters | `/league/{id}/rosters` (221, 301) | `teams[].roster.entries[]` (parsed) | `TYPE=rosters` (parsed) | have / have |
| IR / taxi / reserve | roster `reserve`, `taxi` (301-302, 394) | roster entry `lineupSlotId == 21` (IR) †; ESPN has no taxi | roster player `status`: `ROSTER` / `INJURED_RESERVE` / `TAXI_SQUAD` (`ROSTER` seen in fixture) | have-unparsed / have-unparsed |
| Lineup slots (incl. flex, superflex, IDP) | `roster_positions` (254-256) | `settings.rosterSettings.lineupSlotCounts` † (slot-id map: 0 QB, 2 RB, 4 WR, 6 TE, 23 FLEX, 7 OP, 16 D/ST, 17 K, 20 bench, 21 IR, IDP 8-15) | `league.starters.position[] {name, limit}` (parsed for QB only), `starters.count`, `starters.idp_starters` † | have-unparsed / have-unparsed; **MFL ranges ("1-2") need a rule** (§5.3) |
| Scoring settings | `scoring_settings` in Sleeper keys (306, `season_forecasts.py:51`) | `settings.scoringSettings.scoringItems[] {statId, points, pointsOverrides}` † | `TYPE=rules` `positionRules[] {positions, rule[] {event, points, range}}` (only `CC` parsed today) | have-unparsed / have-unparsed; **translation to Sleeper keys is new code** |
| Tiebreak / seeding rule | fixed: record, PF, PA, lottery (`simulation.py:257`) | `scheduleSettings.playoffSeedingRule` †: `TOTAL_POINTS_SCORED` / `H2H_RECORD` / `INTRA_DIVISION_RECORD` | `league.standingsSort` † (name unverified) | have-unparsed / have-unparsed |
| Divisions | refused (241-242) | `scheduleSettings.divisions[]` † | `league.divisions` † | have-unparsed |
| Median / extra games | `league_average_match` (PR #659) | `scoringSettings.scoringEnhancementType == "WIN_BONUS_TOP_HALF"` † | no documented median setting; caught by reconciliation | have-unparsed / n/a |
| Home-team bonus / other score adjustments | `custom_points` refused (277-278) | `scoringSettings.homeTeamBonus` † | caught by reconciliation | have-unparsed / n/a |
| Best ball | refused (241) | n/a on ESPN | `league.bestLineup == "Yes"` † | — / have-unparsed |
| Max PF, season to date | roster `ppts` (320-331) | **not exposed** | `leagueStandings.pp` † | n/a / **new** |
| Max PF, per completed week | not available (`maxpf_history []`, 332) | n/a | `weeklyResults` player `shouldStart` † + `score`: per-week optimum = Σ score where shouldStart | n/a / **new** |
| Locked current-week starters / player actuals | matchup `starters`, `players_points` (375-436) | `mBoxscore` / `rosterForCurrentScoringPeriod` † | `weeklyResults` / `liveScoring` † | **out of launch scope** (§5.6) |
| Traded-pick ownership | `/league/{id}/traded_picks` (610-615) | **n/a on ESPN** — FTF's own pick-assignment grid (`draft_picks`, `/api/league/pick-assignments`) | `futureDraftPicks` (stored as `leagues.platform_future_picks`, refreshed on the draft-status cadence) | FTF table / have |
| Draft-order rule | hard-coded lowest Max PF (`simulation.py:262`) | default reverse standings; existing final rule `derive_espn_draft_order` | default lowest `pp` among non-playoff teams | new setting (`leagues.draft_order_rule`) |
| Player identity → Sleeper id | native | DP crosswalk `by_espn_id` + name/pos fallback (`espn_service.py:835`) | DP `by_mfl_sleeper` (`map_franchises`, `mfl_service.py:806`) | have; **D/ST and Def need a team-code table** |
| Player positions / NFL team | `/players/nfl` (305) | same Sleeper metadata after crosswalk | same | have (Sleeper) |
| Player projections | Sleeper projections feed (109) | same Sleeper feed after crosswalk (recommended); ESPN's own league-scored projections exist but future-week availability is unknown | same Sleeper feed (recommended); `projectedScores` (FantasySharks, league-scored, `W` defaults to upcoming week, owners-only) | have (Sleeper) |
| Bye weeks / kickoff times | Sleeper `/schedule/nfl/regular/{season}` + `/scores/...` (101-106, `timing.py`) | same (NFL-wide, platform-free) | same | have |
| Free agents for the fill | Sleeper feed rows not on any league roster (68-94, 345-364) | same feed minus crosswalked ESPN rosters | same feed minus crosswalked MFL rosters | have, with the conservative rule in §5.4 |
| Team names | `/league/{id}/users` (312-316) | `teams[].name` (parsed) | `franchise.name` via `_clean_text` | have |
| Change detection during capture | `_league_revision` re-read (195-199, 616-620) | re-read mTeam/mRoster/mSettings | re-read `rosters` + `league` | new code, existing requests |

## 4. Auth and scheduling reality

### 4.1 ESPN

- **Public leagues:** readable with no credential. A background read works.
- **Private leagues: readable by a server cron today, but only because the server
  holds the cookie.** `espn_credentials` (`database.py:2972`) keeps one row per FTF user:
  `swid` plaintext, `espn_s2` Fernet-encrypted (`SLEEPER_TOKEN_KEY`), an
  `expires_hint_at` guess of about a year, and `verified_at`. Real expiry is discovered
  by a 401/403. `_espn_standings_read` (`server.py:24794`) already decrypts and replays
  this cookie server-side, but only inside a user request.
- **What the forecast would change:** the first **background** ESPN read. The
  integration doc states no background job hits ESPN today, so this is a new egress
  pattern and needs an operator yes (decision 1).
- **The forward risk:** the device-side platform-auth programme (PRD
  `docs/plans/device-side-platform-auth-prd-2026-08-12.md`, goal G1: "eliminate
  server-side custody of Sleeper and ESPN credentials"; S0 shipped 2026-08-13, S3+
  not built) would remove the stored cookie. **Once G1 lands, private ESPN leagues can
  no longer be forecast in the background.** The fallback, specified now but built only
  when G1 is scheduled: the device fetches the same two ESPN views and posts the raw
  JSON for one capture (option E in that PRD is rejected for *persisting* or relaying
  credentials, not for relaying league data). Until then, a cron with the stored
  cookie is the design.
- **When a read is refused:** 401/403 → run fails `espn_auth_required`
  (state `failed`, not retried that week), the last success stays on record as stale,
  and the view says the ESPN sign-in needs renewing. The next re-link or
  `/api/espn/import` makes the target due immediately (§5.7). No credential is deleted
  by the forecast. Only the propose route's existing dead-cookie cleanup deletes.
- **Polling budget:** ESPN publishes no rate limit (unofficial API). Two ESPN requests
  per capture: the existing three views plus `mMatchupScore` in **one** request, and
  the same request again for change detection. One capture per league per week plus
  operator retries. This is lighter than the existing link/import traffic.
- **Privacy:** log league id, platform, season, HTTP status, `EspnError.kind`,
  latency and refusal reason. Never log the cookie, SWID, owner SWIDs, member display
  names or raw bodies. Snapshots store team names and Sleeper player ids, as Sleeper
  snapshots already do, and are retained for 7 days (`retention_days`).

### 4.2 MFL

- **Public leagues:** all needed exports are public. A background read works.
- **Private leagues:** `leagueStandings`, `schedule`, `weeklyResults`,
  `playoffBrackets`, `projectedScores` and `futureDraftPicks` are "Private league,
  owners only" per MFL's API page. The cron uses the importer's stored `MFL_USER_ID`
  cookie (`mfl_credentials`, Fernet, one row per user, lifetime undocumented). A
  key-less deployment keeps the cookie only in the session (`_mfl_cookie_for`,
  `server.py:42413`), so a background read cannot use it, and the run fails
  `mfl_auth_required`.
- **MFL is the sanctioned API** and is already read in the background (the hourly
  draft-status sweep). The forecast adds a second background reader. The device-auth
  programme's MFL goal (G2) concerns the password, which is never stored, so it does
  not threaten the stored cookie.
- **Politeness:** keep `_REQUEST_SPACING_SECONDS = 1.0` between exports and always send
  `MFL_USER_AGENT` (an empty UA has returned empty bodies, `mfl.md` §2). Requests per
  capture: `league`, `rules`, `rosters`, `leagueStandings&ALL=1`, `schedule`,
  `playoffBrackets` (+ one `playoffBracket`), then `weeklyResults&W=n` for each
  completed week not already cached (≤17 the first time, about 1 a week after that),
  plus `rosters` and `league` again for change detection. That is about 9 requests
  (≈10 s) in steady state and ≤26 (≈30 s) the first time. `players` is not needed:
  positions come from Sleeper metadata after the crosswalk, and Def rows use the team
  table. Completed weeks' `weeklyResults` are cached on the target, so a week is read
  once and re-read only if reconciliation fails. MFL registration (higher limits) is
  still not done. Not needed at one capture per league per week.
- **Refusals:** 401/403 → `mfl_auth_required` as for ESPN. Any `MflError` other than
  auth → `incomplete_projections`, retried at the next weekly slot or by an operator
  retry. An empty body (the UA symptom) is a parse failure, never "no games".
- **Privacy:** as `mfl.md` §6. League id, franchise ids, host, export type, status and
  latency are safe. Never log the cookie or the username.

### 4.3 Scheduling and fairness

- The forecast stays on the existing weekly slot (Tuesday 09:30 ET,
  `config/league_projections.json`), dispatched from the 15-minute realtime tick
  (`server.py:32300-32303`), `batch_limit` 4, one worker thread (`service.py:15-23`).
- **Head-of-line problem (verified in code):** `dispatch` selects the oldest due targets
  (`batch.py:175-177`). When `store.create` refuses with `another_run_pending` because
  the same account already has a run queued, the target's lease is cleared but
  `next_due_at` is left alone (`batch.py:198-200`). An account with many due targets
  therefore keeps the front of every tick's batch. Adding ESPN/MFL targets to such an
  account makes it worse.
- **Fix, in the shared plumbing item:** select up to `4 × batch_limit` due rows, keep the
  first due target **per user** (ordered by `next_due_at`, `created_at`), and take
  `batch_limit` of those. A refused `another_run_pending` row is then never chosen
  twice in one tick and cannot block other users. Also cap **one MFL capture per tick**
  so a 30-second first capture cannot crowd out a tick. Captures are already serial on
  the single worker.

## 5. Recommended design

### 5.1 Shape: a neutral league-facts contract, one adapter per platform

Split `provider.capture` in two:

1. **`adapters/<platform>.read_facts(target, fetchers, cfg) -> LeagueFacts`.** Platform
   reads, refusals and reconciliation only. One module per platform:
   `adapters/sleeper.py` (moved from `provider.py:215-333` and `610-620`), `espn.py`,
   `mfl.py`.
2. **`assemble.build_snapshot(facts, feed, metadata, cfg) -> snapshot`.** The existing
   platform-free lineup, free-agent, Max PF lane and coverage code
   (`provider.py:334-609`, moved, not rewritten). It returns exactly today's snapshot
   shape plus the new keys below.

`core.py`, `joint.py` and `simulation.py` never branch on platform. They read only the
snapshot.

**`LeagueFacts` (the contract).** All points are Decimal strings and all player ids are
Sleeper ids.

| Key | Meaning |
|---|---|
| `platform` | `sleeper` / `espn` / `mfl` |
| `league_id`, `season`, `league_name`, `viewer_roster_id` | as today |
| `teams[]` | `roster_id` (int; MFL `"0001"` → 1, ESPN team id as is), `native_team_id`, `name`, `wins/losses/ties`, `points_for`, `points_against`, `maxpf` (string or **null** when the platform does not publish it), `actual_history[]`, `maxpf_history[]` (MFL only; empty elsewhere), `roster {players, reserve, taxi}`, `unmapped[]` (native ids the crosswalk could not place, with native position) |
| `slots` | `core.SLOTS` vocabulary, with `DEF` added (§5.3) |
| `scoring` | coefficients in Sleeper stat keys; `scoring_translation {mapped, unmapped_rules[], source_hash}` |
| `completed_weeks`, `future_weeks[]`, `games {week: [(a, b), …]}` | as today |
| `playoff_spots`, `playoff_byes` | as today |
| `league_format` | PR #659's `{median_game, games_per_week}` |
| `seeding_rule` | `record_pf_pa` (Sleeper and ESPN `TOTAL_POINTS_SCORED`) or `record_h2h_pf` (ESPN `H2H_RECORD`, MFL H2H-first sorts) |
| `draft_order_rule` | `maxpf_lowest_first` or `reverse_standings` (§5.2) |
| `pick_ownership[]` | `{season, round, original_roster_id, owner_roster_id}` |
| `revision` | digest re-checked at the end of capture |
| `coverage` | per-platform contract id (`espn_capture_v1`, `mfl_capture_v1`), crosswalk report, endpoint hashes |

**Model version.** Keep one model id, `projected-lineup-universal-sd-v6`. The math does
not fork. Bumping `VERSION` would re-run every Sleeper baseline through
`_expire_other_model_baselines` (`batch.py:72-85`) for no change. Each result gains
`platform`, `draft_order_rule`, `seeding_rule` and the adapter's contract id. A change
to one adapter bumps only its contract id. A target is re-run on contract change by the
same last-attempt check that `_expire_other_model_baselines` already does, keyed on
`(VERSION, contract)`.

### 5.2 Draft order is a per-league setting

- **New column `leagues.draft_order_rule TEXT NULL`**: `maxpf_lowest_first` |
  `reverse_standings` | NULL. NULL means the platform default: Sleeper → maxpf, ESPN →
  reverse standings, MFL → maxpf. It is read at capture and copied into the snapshot,
  so a saved forecast keeps the rule it was made with. It is not keyed by platform, so
  a Sleeper league that drafts by reverse standings can be set to that. At launch it is
  set only by the operator (a CRON_SECRET route, or SQL). No user UI (decision 4).
- **`maxpf_lowest_first`** (today, `simulation.py:262`): non-playoff teams sorted by
  simulated season Max PF ascending, exact ties by the seeded lottery
  (`random_exact_ties`). For MFL the season-to-date floor is `leagueStandings.pp`.
- **`reverse_standings`**: non-playoff teams pick first in the order of the existing
  ESPN final-standings rule (`derive_espn_draft_order`, `espn_service.py:666-667`),
  applied to each simulated world. Key, ascending: (win % with a tie as half a win,
  points for, −final regular-season standing position, lottery). The standing position
  is the simulated seeding order from the same world, so it plays the role of ESPN's
  `playoffSeed`. A test pins that in a zero-variance world the simulator's order equals
  `derive_espn_draft_order` on the same final records.
- **Playoff teams** stay an unordered late block (picks n − p + 1 … n), as today. The
  real ESPN rule orders them by playoff finish (`rankCalculatedFinal`), and the forecast
  does not simulate the bracket (decision 3). Pick pricing reads the block for those
  picks.
- **Seeding** (who makes the playoffs) is a separate per-league fact:
  `record_pf_pa` is today's sort. `record_h2h_pf` is new: within a group tied on
  record, order by head-to-head win % among the tied teams over the simulated season,
  then PF, then the lottery. It is about 25 lines in the per-world standings step.
  The H2H matrix is accumulated alongside `records`.
- **Max PF where the platform has none (ESPN).** `maxpf` null → the simulator skips the
  Max PF accumulation and reports `maxpf_mean`/quantiles as null. A league whose
  `draft_order_rule` is `maxpf_lowest_first` but has no official Max PF is refused
  `maxpf_rule_without_platform_maxpf`. ESPN cannot be switched to the max PF rule.

### 5.3 Shared model extension: team defense (`DEF`)

- Add `"DEF": {"DEF"}` to `core.SLOTS` and admit Sleeper's `DEF` position (Sleeper
  team-defense player ids are team codes such as `BUF`).
- Map ESPN D/ST (negative ids; `proTeamId`) and MFL `Def` rows (team codes such as
  `KCC`, `SFO`, `GBP`, seen in the MFL fixture) to Sleeper team codes with one fixed
  32-team table. A test pins all 32 for both platforms.
- Team-defense scoring is largely threshold-based (`pts_allow_0`, `pts_allow_1_6`, …).
  Best-available scoring already treats a key the projection does not supply as
  missing, which makes the player partial, not zero. A DEF projected with sacks,
  interceptions and fumble recoveries only is therefore partial and understated. This
  is surfaced in coverage (`partial_player_weeks`). It is not corrected by inventing
  bucket probabilities.
- Effect on Sleeper: leagues refused only for a DEF slot become admissible. Results for
  already-admitted leagues are unchanged. Re-run them with PR #659's
  `retry_unsupported`.

### 5.4 Platform adapters

**Common rules (both adapters):**

- **Refusals:** `unsupported_divisions`, `unsupported_median_setting` (if the shape is
  unknown), `unsupported_multiweek_matchups`, `unsupported_seeding_rule`,
  `nonstandard_start_week`, `unsupported_lineup` (a slot outside `SLOTS`),
  `standings_unreconciled` (§6.1), `playoff_teams_unknown`, `live_week_not_supported`
  (§5.6), `espn_auth_required` / `mfl_auth_required`,
  `crosswalk_coverage_insufficient`.
- **Crosswalk:** every rostered native id → Sleeper id via the DP file; D/ST and Def via
  the team table. An unmapped rostered player is recorded in `teams[].unmapped` and
  treated exactly like an unpriced Sleeper player (excluded from the pool, so the
  free-agent fill can take the slot). **Refuse the league
  (`crosswalk_coverage_insufficient`) if any team has an unmapped player at a
  starter-eligible position** among the top `len(slots)` of that team's roster by
  consensus value. A missing star would silently become a waiver-wire stand-in. Bench
  depth misses only lower coverage.
- **Free agents:** a Sleeper projection row is a free agent only if its Sleeper id has
  a reverse crosswalk entry to this platform **and** that native id is on no roster in
  the league. A rostered player the crosswalk missed must never be offered as a free
  agent to someone else.
- **Viewer seat:** from the `leagues` row (`user_id` and `espn_my_team_id` /
  `platform_my_team`). The target's user must be that row's `user_id`. The team must
  still exist. For a private ESPN read, the stored SWID must be one of that team's
  `owner_swids`, or the run fails `league_membership_changed`.
  `service._viewer_identity` stays Sleeper-only.

**ESPN adapter (`espn_capture_v1`):**

- One request: the existing three views plus `mMatchupScore`. This needs an optional
  `views` argument on `espn_service.fetch_league`. The default stays unchanged.
- Regular season = `matchupPeriodCount`. Refuse if any regular-season matchup period
  spans more than one NFL week (`matchupPeriods`), or if the league's
  `currentMatchupPeriod` and Sleeper's NFL week disagree.
- Completed weeks: `schedule[]` entries with `playoffTierType == "NONE"` †; per-team
  totals and `winner`; points against from the opponent's total. With
  `WIN_BONUS_TOP_HALF`, add `median_outcomes` results.
- Refuse `homeTeamBonus ≠ 0`, divisions > 1, and `playoffSeedingRule` other than
  `TOTAL_POINTS_SCORED` / `H2H_RECORD`.
- Slots from `lineupSlotCounts` via a fixed slot-id table (bench 20 and IR 21
  excluded). IR = roster entries with `lineupSlotId == 21`. No taxi.
- Scoring: `scoringItems` statId → Sleeper key table. `pointsOverrides` by slot map to
  Sleeper's position bonuses where one exists (for example a TE reception override
  becomes `bonus_rec_te`). Anything else lands in `unmapped_rules` and makes affected
  players partial.
- Pick ownership: FTF's pick-assignment grid for this league (users enter ESPN pick
  trades in-app). With no grid, every team owns its own pick, flagged
  `pick_ownership_source: "assumed_original"`.
- `maxpf` null; draft rule default `reverse_standings`.

**MFL adapter (`mfl_capture_v1`):**

- Host from `leagues.platform_host`; season from `platform_season`; the cookie from the
  importer's `mfl_credentials` row.
- `league`: start week, last regular-season week, `starters`, divisions, `bestLineup`,
  `standingsSort` (exact names verified on the first recorded capture; until then the
  adapter refuses on any missing field rather than defaulting).
- **Lineup ranges:** MFL allows "QB 1-2" with a total starter count. Translate
  "1 QB + one more QB-or-flex" as a `SUPER_FLEX`, and refuse any other range shape
  (`unsupported_lineup_range`) until seen in a real league.
- Standings: `leagueStandings&ALL=1` → `h2hw/h2hl/h2ht/pf/pa/pp`. **`pp` is the official
  Max PF floor.**
- Completed weeks: `schedule` (pairs + scores) and `weeklyResults&W=n` (per-player
  `score`, `status`, `shouldStart`). The weekly Max PF history is the sum of `score` over
  players with `shouldStart` set. If the history sums to `pp` for every team, it becomes
  `maxpf_history` (the first platform to have one). Otherwise history stays empty, with
  the same warning Sleeper uses.
- Playoff spots from `playoffBrackets` / `playoffBracket` (the regular-season bracket's
  team count). **No bracket yet → refuse `playoff_teams_unknown`** (decision 6).
- IR from roster `status == INJURED_RESERVE`, taxi from `TAXI_SQUAD`.
- Scoring: `rules` `positionRules` event codes → Sleeper keys (passing/rushing/receiving
  yards and TDs, receptions with per-position points, INT, fumbles lost, 2-pt, kicking,
  team defense). Range rules (a points value for a band such as "0-9") are threshold
  bonuses and go to `unmapped_rules`. Position-specific reception points become Sleeper
  position bonuses.
- Pick ownership from `platform_future_picks` (`parse_future_picks`): `originalPickFor`
  → `owner`.
- Draft rule default `maxpf_lowest_first` on simulated season `pp`.

### 5.5 How MFL Max PF is simulated for the remaining weeks

The existing construction can be reused unchanged:

- The floor is the observed season-to-date total: `team.maxpf = pp`.
- For each future week, `assemble` computes the hindsight-optimal lineup from the
  eligible roster and projections (`optimize(..., hindsight=True)`, `provider.py:517`).
- `joint.prepare` samples that week's Max PF as actual plus a non-negative gap with the
  same SD and correlation config (`simulation.py:177-231`).

`ir_maxpf` must match MFL's own definition of potential points. Whether MFL counts IR
or taxi players is unknown. Decide it from data: on the first recorded league, check
whether any `INJURED_RESERVE` player ever has `shouldStart` set. Record the answer as
the MFL adapter's fixed `ir_maxpf` (an adapter fact that overrides the app config for
MFL), with a test.

### 5.6 Live weeks

The Sleeper adapter supports a partly played current week (locked starters, completed
actuals). ESPN and MFL at launch do not. The adapter requires that no game of the
current NFL week has kicked off. The Tuesday batch always satisfies this. Mid-week runs
(operator retries) fail `live_week_not_supported` and keep the last success. Locked
lineups (ESPN `mBoxscore`, MFL `weeklyResults`/`liveScoring`) are a later item.

### 5.7 Storage, registration, flags

- **Schema:** `leagues.draft_order_rule` (TEXT, NULL) plus its `_migrate_db` entry.
  Completed-week MFL `weeklyResults` caching goes in a new nullable
  `league_projection_targets.platform_cache_json` (TEXT): per week, the reconciled team
  totals and per-week optimum, plus a hash. Nothing else. Snapshots and results keep
  using `league_projection_runs`.
- **Registration:** `batch.register` is called after a successful ESPN link/import
  (`/api/espn/link` with a team, `/api/espn/import`) and MFL link/import
  (`/api/mfl/link` with a franchise, `/api/mfl/import`, `/api/mfl/auth-import`), for the
  league row's `user_id` only. `_bootstrap_connected` drops its Sleeper-only filter and
  instead checks the per-platform flag. A re-link or import of a target whose last
  attempt failed `espn_auth_required` / `mfl_auth_required` sets `next_due_at = now`.
- **Fetchers:** `service._run` receives a fetcher bundle (`sleeper`, `espn`, `mfl`)
  instead of one `fetch_json`. ESPN and MFL go through `espn_service.fetch_league` /
  `mfl_service._fetch_one` with their injectable `_opener`, so every adapter test is
  offline.
- **Flags (default off):** `league.projections_espn`, `league.projections_mfl`. Both
  also require `league.projections` and `league.projections_provider_approved`. Off →
  no registration, no dispatch, and `api.py` keeps today's `sleeper_only` answer for
  that platform. The deploy-free rollback is flipping the platform flag. Queued runs then
  fail `new_projection_provider_approval_pending`-style at admission, so `admit()` in
  `service.py:67-79` gains the platform-flag check.
- **API:** routes unchanged. `api.py:73` and `101-103` check the per-platform flag
  instead of `!= "sleeper"`. The result gains `platform`, `draft_order_rule`,
  `seeding_rule` and `league_format`. `docs/api-reference.md` documents them.

## 6. Accuracy and evaluation

### 6.1 Offline (no live calls)

- **Golden refactor check:** every existing `test_league_projection_*` passes, and the
  Sleeper snapshot digests for their fixtures are byte-identical before and after the
  adapter split.
- **Reconstruction must match exactly** (as done for Sleeper at `provider.py:326-328`):
  - **ESPN:** W/L/T, PF and PA rebuilt from `schedule[]` (plus the median result when
    configured) equal `record.overall` for every team.
  - **MFL:** W/L/T, PF and PA rebuilt from `schedule` equal `leagueStandings`
    `h2hw/h2hl/h2ht/pf/pa`. The per-week Σ(shouldStart score) equals `pp`.

  Any mismatch refuses the league (`standings_unreconciled`). This is the safety net for
  every rule the adapter does not model.
- **Scoring-translation agreement:** for each completed week, score Sleeper's actual
  stat lines (`api.sleeper.app/stats/nfl/regular/{season}/{week}`, a new public read,
  path unverified) with the translated coefficients. Compare with the platform's own
  recorded player score (ESPN `appliedTotal` / box score †, MFL `weeklyResults`
  `score`). Report the share of player-weeks that agree within 0.01 and the worst
  rules. This measures translation error with no projection noise. Below an agreed bar
  (decision 2's follow-up) the league runs as `estimated`, not refused.
- **Draft-rule parity:** in a zero-variance world, the simulated `reverse_standings`
  order equals `derive_espn_draft_order` on the same records.
- **Fixtures:** none of the new reads have recorded fixtures. Builders write synthetic
  fixtures to the documented shapes first. Then one recorded cassette per platform
  (below) replaces them as the authority. Shapes that differ are fixed in the adapter,
  not the fixture.

### 6.2 Needs one consenting real league per platform

- **ESPN:** one league (public is simplest; a private one needs the operator's own
  stored credential) with schedule, scoring and roster settings, recorded once by an
  operator-run script (standard library only, writes a cassette, logs nothing
  secret, reviewed before running, like `scripts/espn_pair_check.py`).
- **MFL:** the operator's MFL league (NEXT.md names "Dependables" 62846) recorded the
  same way, with the stored cookie if private.
- From each: verify every † field name, run the three reconciliations, measure
  crosswalk coverage and scoring agreement, and answer the MFL IR question (§5.5).

### 6.3 Known accuracy gaps

- **Projection source mismatch.** Sleeper's projections are scored with translated
  rules. Unmapped rules (MFL range bonuses, ESPN slot overrides with no Sleeper key,
  distance-banded kicking) make players partial. Team-defense threshold scoring is
  understated (§5.3).
- **Missing positions.** No IDP-heavy validation exists. DP crosswalk coverage for IDP
  and K is unmeasured. Unmapped bench players lower coverage silently. Unmapped likely
  starters refuse.
- **Playoff-team pick order** is not projected (block only).
- **No live-week support** for ESPN/MFL at launch.
- **The SD (25.0) is uncalibrated** on every platform (`simulation.py:321`), so cross-
  platform comparisons of forecast quality are not evidence until calibration exists.
- **ESPN top-half median semantics at exact ties** are unverified. Reconciliation
  refuses any mismatch.

## 7. Build plan

Sizes: **S** ≤ 1 builder-day, **M** 2–3, **L** 4–5. "Sabotage" = the change that must
turn the named test red.

**Shared first (one builder, in order; ESPN and MFL start after A–D merge):**

| # | Item | Files | Tests / sabotage | Size |
|---|---|---|---|---|
| A | Split capture: `adapters/sleeper.read_facts` + `assemble.build_snapshot`; `LeagueFacts` contract; Sleeper byte-identical | `league_projections/provider.py` → `adapters/sleeper.py`, `assemble.py`; `service.py` | all `test_league_projection_*` green; new `test_league_projection_contract.py` pins the facts schema and Sleeper snapshot digests. Sabotage: reorder one `assemble` field / drop a coverage key → digest test red | M–L |
| B | Draft-order + seeding rules: `leagues.draft_order_rule`, snapshot keys, `reverse_standings`, `record_h2h_pf`, null-Max-PF path | `database.py`, `simulation.py`, `assemble.py`, `adapters/sleeper.py` | `test_league_projection_draft_rules.py`: Sleeper default byte-identical; zero-variance parity with `derive_espn_draft_order`; H2H tie case; null Max PF refused under maxpf rule. Sabotage: swap PF direction in the reverse key → parity red | M |
| C | `DEF` slot + 32-team ESPN/MFL→Sleeper defense table | `core.py`, `assemble.py`, new `league_projections/teams.py` | `test_league_projection_def_slot.py`: a Sleeper DEF league admitted and partial-scored; all 32 codes both platforms. Sabotage: drop one code → table test red | S–M |
| D | Platform plumbing: per-platform flags, fetcher bundle, adapter registry, seat resolution, registration hooks on ESPN/MFL link/import, fair dispatch, auth-failure re-due | `feature_flags.py`, `config/features.json`, `tests/fixtures/flags/release.json`, `batch.py`, `service.py`, `api.py`, `server.py` (registration lines only) | `test_league_projection_platforms.py`: flags off = today's `sleeper_only`; one-per-user dispatch (an account with 6 due targets cannot starve another user). Sabotage: remove the per-user de-dup → starvation test red | M |

**Then in parallel:**

| # | Item (ESPN builder) | Files | Tests / sabotage | Size |
|---|---|---|---|---|
| E1 | ESPN reads + refusal ladder + reconciliation; `fetch_league(views=…)` | `espn_service.py`, `adapters/espn.py` | `test_league_projection_espn.py` on synthetic fixtures: each refusal; W/L/T/PF/PA rebuild; median top-half. Sabotage: drop the median booking → reconciliation red | M |
| E2 | ESPN scoring statId map + slot-id map + agreement check | `adapters/espn_scoring.py` | table tests per stat; agreement report. Sabotage: wrong rec-yard coefficient → agreement test red | M |
| E3 | Recorded ESPN cassette + tighten † fields | fixtures, `scripts/record_espn_forecast_fixture.py` | the recorded league reconciles exactly | S (+ operator run) |

| # | Item (MFL builder) | Files | Tests / sabotage | Size |
|---|---|---|---|---|
| M1 | MFL reads (`leagueStandings`, `schedule`, `weeklyResults`, `playoffBrackets`), `export_url` params, spacing, week cache | `mfl_service.py`, `adapters/mfl.py`, `database.py` (`platform_cache_json`) | `test_league_projection_mfl.py`: refusals; standings rebuild; `pp` = Σ shouldStart; empty-body = failure. Sabotage: treat an empty body as no games → test red | M |
| M2 | MFL rules → Sleeper keys, lineup ranges | `adapters/mfl_scoring.py` | event-code table tests; range rule → unmapped. Sabotage: map a range rule as linear → test red | L |
| M3 | Max PF floor + history wiring, MFL `ir_maxpf` fact | `adapters/mfl.py`, `assemble.py` | Max PF floor = `pp`; history used only when it reconciles | S |
| M4 | Recorded MFL cassette + † fields | fixtures, `scripts/record_mfl_forecast_fixture.py` | the recorded league reconciles exactly | S (+ operator run) |

**Last (either builder):** docs rows in [scope.md](scope.md) §4, `docs/integrations/{espn,mfl}.md`
(new reads, background reader, safe-to-log), `docs/config-reference.md` (two flags),
`docs/data-dictionary.md` (two columns), TEST_LEDGER, then CI. Size S.

**Total:** shared ≈ 7–10 builder-days; ESPN ≈ 5; MFL ≈ 7–8. With two builders after the
shared items, about 3 weeks of calendar time, plus operator turnaround on the recordings.

**Blocks on the operator:** decisions 1–6 before A–D finish (2, 3 and 4 shape item B);
one consenting ESPN league and one MFL league for E3/M4; and, for private leagues, the
recordings must run where the operator's stored credentials are, which means a
production-side or operator-laptop run. Agents have no credential access.

## 8. Open decisions for the operator

Each is answerable yes/no. Only decisions that change the build are listed.

1. **May the server read ESPN and MFL leagues once a week in the background, using the
   sign-in the user already gave us for private leagues?** Recommend **yes**. It is the
   only way to keep a forecast current without the user opening the app, and the
   credential is already stored and used server-side. (If no: private leagues forecast
   only while the user is in the app, a different build.)
2. **Use Sleeper's player projections, scored with each league's own rules translated
   into Sleeper terms, for ESPN and MFL leagues?** Recommend **yes**. They cover every
   remaining week and reuse the tested lineup and free-agent machinery, while ESPN's and
   MFL's own projections are not known to go past next week.
3. **Leave playoff teams' picks as an unordered "late picks" block for now, rather than
   simulating the playoff bracket?** Recommend **yes**. Bracket simulation adds a week of
   work and only reorders the last few first-round picks, which are priced close together.
4. **Store the draft-order rule per league (defaults: ESPN reverse standings, MFL and
   Sleeper max PF) with no in-app setting for users yet?** Recommend **yes**. This is the
   smallest build, and any league can still be switched by the operator.
5. **Add team-defense (D/ST) lineup support for all platforms as part of this work?**
   Recommend **yes**. Most ESPN leagues start a D/ST, so without it nearly every ESPN
   league is refused. It also unlocks Sleeper leagues refused today for the same reason.
6. **For an MFL league whose commissioner has not set up the playoff bracket yet, show
   no forecast rather than guess the number of playoff teams?** Recommend **yes**.
   Guessing the playoff count moves every projected pick. The forecast appears once the
   bracket exists.

## 9. What could not be determined

- Every † field name. In particular, the MFL `league` export's `lastRegularSeasonWeek`,
  `standingsSort`, `divisions`, `h2h` and `startWeek`, and ESPN's `playoffTierType`,
  `scoringEnhancementType` and `matchupPeriods`. Nothing in the repo's fixtures
  carries them.
- Whether MFL potential points (`pp`) counts IR or taxi players. Whether MFL has a
  "versus median" option. MFL cookie lifetime.
- Whether ESPN or MFL publish projections beyond the upcoming week (decision 2 makes
  this non-blocking).
- DP crosswalk coverage for K and IDP. The MFL/ESPN share of linked leagues that start
  a D/ST, use divisions, or use H2H seeding (no production access in this session).
- Whether ESPN binds `espn_s2` to the SWID (open risk R1, `espn.md` §2.5). It does not
  block the forecast (the read uses the user's own pair), but it bounds the
  team-owner check in §5.4.
- Whether the users table marks platform-signed-in (`acct_*`) users as verified for
  `connected_targets()` (`outlook_calibration.py:667`). Item D must check this.
- The Sleeper actual-stats endpoint path for the agreement check.
