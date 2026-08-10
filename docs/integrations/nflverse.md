# nflverse/nfldata — NFL schedule CSV (bye-week derivation)

> Public, unauthenticated GitHub-hosted CSV. All data is public — nothing here needs redaction in logs. **Not currently reachable from any live server route** — this is the data source for the EVALUATED (not shipped) #169 bye-week μ multiplier; see [feedback/items/169-outlook-league-summary/bye-week-multiplier-2026-08-09.md](../feedback/items/169-outlook-league-summary/bye-week-multiplier-2026-08-09.md) for the ship/no-ship verdict.

## Table of Contents

- [What it is](#what-it-is)
- [Why nflverse instead of Sleeper](#why-nflverse-instead-of-sleeper)
- [Endpoint fetched](#endpoint-fetched)
- [Fetch triggers, cadence, and caching](#fetch-triggers-cadence-and-caching)
- [Derivation](#derivation)
- [Consumed fields](#consumed-fields)
- [Error modes](#error-modes)
- [Instrumentation guidance](#instrumentation-guidance)
- [Test seams](#test-seams)
- [Source](#source)

## What it is

[nflverse/nfldata](https://github.com/nflverse/nfldata) is a community-maintained, GitHub-hosted repository of NFL data feeds, published as flat CSV files under a [CC-BY license](https://github.com/nflverse/nfldata#license) — reuse is permitted with attribution. Fantasy Trade Finder reads `data/games.csv` (the full historical game-by-game schedule/results table, 1999–present) unauthenticated over plain HTTP GET from `raw.githubusercontent.com` — same trust boundary as the DynastyProcess CSVs FTF already fetches (see [dynastyprocess.md](dynastyprocess.md)), just a different upstream repo, hence its own doc.

**Attribution (required by CC-BY):** "Data by nflverse (https://github.com/nflverse/nfldata), CC-BY."

FTF does not consume `games.csv` for scores, odds, or any of its ~40 other columns — only `season`, `game_type`, `week`, `home_team`, `away_team`, to derive **bye weeks**: a team absent from every regular-season game in a given week is on bye that week. Nothing else in `games.csv` is read.

## Why nflverse instead of Sleeper

Verified 2026-08-09: Sleeper's `/v1/players/nfl` bulk dump (already fetched by FTF for the players cache — see `server._fetch_players_bulk`) does **not** carry a bye-week field. All 12,218 returned players, 53 distinct keys observed across the dump, zero bye-related keys. Byes must therefore be derived from a schedule rather than read off a player record. nflverse's `games.csv` is the source used here because it's already a trusted-shape public CSV (matching the DP precedent) rather than introducing a new API surface (auth, rate limits, ToS).

## Endpoint fetched

| File | URL constant | Module | Purpose |
|---|---|---|---|
| `data/games.csv` | `bye_weeks.NFLVERSE_GAMES_URL` | `backend/outlook/bye_weeks.py` | Full historical game-by-game schedule table. FTF reads only REG-season rows, only to derive `{season: {team_abbr: bye_week}}`. |

Plain GET request with `User-Agent: FantasyTradeFinder/1.0`, `timeout=15s` (`fetch_byes`).

## Fetch triggers, cadence, and caching

Mirrors the DynastyProcess crosswalk idiom (`espn_service.get_crosswalk`/`fetch_crosswalk`) almost exactly:

- Lazy fetch on first call to `bye_weeks.get_byes()` — nothing fetches eagerly at boot, and as of this writing **nothing in the live server calls `get_byes()` at all** (the only callers are `bye_multiplier.py`, the calibration backtest, and tests).
- **7-day in-memory TTL** on a successful fetch (`_BYE_CACHE_TTL_SECONDS`) — deliberately much longer than the DP crosswalk's 24h. NFL schedules (and therefore bye weeks) are **static** once the league office publishes them for a season; there is no "daily refresh" reason to re-pull, only a periodic safety re-pull in case the upstream file is corrected.
- Three-tier fallback on failure: (1) live fetch, (2) last-good in-memory copy if the live fetch fails, (3) a bundled snapshot fixture (`backend/tests/fixtures/nflverse_games_2022_2026.csv`, a season-filtered slice captured 2026-08-09 — NOT the full 25-year file) if there's no in-memory copy yet. A snapshot-served result retries hourly instead of waiting the full 7 days, same self-healing behavior as the DP crosswalk.
- `get_byes()` never raises. `fetch_byes()` (the raw fetch-and-parse) does, for callers/tests that want the failure directly.

## Derivation

`derive_byes(csv_text)` (pure function, no I/O):

1. Filter to `game_type == "REG"` rows only (drops PRE/POST — a team's postseason absence must never be read as a "bye").
2. For each `(season, week)`, collect the set of teams appearing in `home_team` or `away_team`.
3. A team's bye week is the **first** REG week in that season where it's absent from that set (each team has exactly one regular-season bye; "first" is defensive, not load-bearing).

**Team-code normalization:** nflverse's codes match Sleeper's player `team` field for every current franchise except the Rams — nflverse uses `"LA"`, Sleeper uses `"LAR"` (verified against a live `/v1/players/nfl` pull 2026-08-09; Washington is `"WAS"` in both, the Raiders are `"LV"` in both post-2020 relocation). `_TEAM_ALIASES = {"LA": "LAR"}` in `bye_weeks.py` is the single normalization point — the derived map is always keyed in Sleeper-style codes so `bye_multiplier.py` can join directly against `player_team` (itself sourced from Sleeper) with no further translation.

## Consumed fields

From `games.csv` (columns present in the live file: `game_id, season, game_type, week, gameday, weekday, gametime, away_team, away_score, home_team, home_score, location, result, total, overtime, old_game_id, gsis, nfl_detail_id, pfr, pff, espn, ftn, away_rest, home_rest, away_moneyline, home_moneyline, spread_line, away_spread_odds, home_spread_odds, total_line, under_odds, over_odds, div_game, roof, surface, temp, wind, away_qb_id, home_qb_id, away_qb_name, home_qb_name, away_coach, home_coach, referee, stadium_id, stadium` — 45 columns as of 2026-08-09) — FTF reads only:

| Column | Used for |
|---|---|
| `season` | Top-level key of the derived map |
| `game_type` | Filtered to `"REG"` — bye derivation is meaningless outside the regular season |
| `week` | The value being derived (which week a team is missing from) |
| `home_team` / `away_team` | The set of teams playing that week; a team's bye is the week it's in neither |

Scores, odds, weather, coaches, officiating, and every id/crosswalk column are present in the file but **not read**.

## Error modes

| Failure | Behavior |
|---|---|
| Fetch failure (network, timeout, non-2xx) | `fetch_byes()` raises; `get_byes()` catches it, logs `⚠️  nflverse schedule fetch failed (...) — keeping previous copy` / `... — using bundled snapshot`, and never raises to its caller. |
| Schema drift (column renamed/removed) | No explicit schema validation. A missing `week`/`season` row is skipped by `derive_byes` (defensive `try/except` on the `int(week)` cast); a renamed `home_team`/`away_team` column would silently produce an empty team set for every week, which surfaces as **every team missing from every week** — `test_bye_weeks.py::test_every_team_has_exactly_one_bye_per_season` would fail loudly against the committed fixture rather than degrading silently in production, since (per this doc) nothing in the live server currently depends on this data. |
| Stale data (upstream stops updating but keeps serving 200s) | Not detected — same posture as the DP crosswalk. Low risk here specifically: an NFL season's schedule doesn't change after publication, so "staleness" mostly matters for years not yet in the CSV (see below). |
| A season not yet published (e.g. requesting `team_bye_week("2027", ...)` before the NFL schedule is public) | `team_bye_week()` returns `None` (no `KeyError`) — callers must treat `None` as "unknown," not "no bye." |
| Live `games.csv` (2026-08-09, for reference) | 200 OK, ~2.1 MB, 7,548 data rows (1999–2026), header as listed above. |

## Instrumentation guidance

All data here is public (schedule/results, no PII, no secrets) — **log freely**, nothing to redact.

- `fetch_byes()` is wrapped in `observe_call("nflverse", "schedule")`, recording status, latency, `response_bytes`, and derived `seasons` count on success (row/season-count drop is the cheapest schema-drift signal, same rationale as the DP doc's row-count guidance).
- **This call site is not currently reachable from a live server request** — `observe_call` will only emit an `api_call` event when something actually invokes `bye_weeks.get_byes()`/`fetch_byes()`, which today means the calibration backtest script or a test with `_opener` injected (both pass `_opener` and are therefore `active=False` — no event write). If `bye_multiplier.py` is ever wired into `pipeline.py`, this becomes a genuine outbound egress chokepoint and should be added to the "What's captured" list in `docs/integrations/README.md` at that time.

## Test seams

| Param | Effect |
|---|---|
| `_opener` (kwarg on `fetch_byes`/`get_byes`/`team_bye_week`) | Injects a fake `urllib.request.urlopen`-shaped callable, same pattern as `espn_service.fetch_crosswalk`. Used by `backend/tests/test_bye_weeks.py`; no env-var seam exists because — unlike the DP crosswalk — nothing on the live request path calls this module, so there's no `FTF_TEST_MODE` startup dependency to satisfy. |
| `bye_weeks.reset_cache()` | Test-only: clears the in-memory cache so the next `get_byes()` call re-fetches instead of serving a prior test's cached result. |

## Source

- `backend/outlook/bye_weeks.py` — fetch, cache, fallback, derivation (`fetch_byes`, `get_byes`, `derive_byes`, `team_bye_week`)
- `backend/outlook/bye_multiplier.py` — the (unshipped) consumer: per-week starting-lineup value-fraction-on-bye → mu multiplier
- `backend/tests/fixtures/nflverse_games_2022_2026.csv` — committed offline fixture (season-filtered slice, captured 2026-08-09)
- `backend/tests/test_bye_weeks.py` — derivation correctness, cache/fallback behavior
- `docs/feedback/items/169-outlook-league-summary/bye-week-multiplier-2026-08-09.md` — full spec, backtest results, ship/no-ship verdict
- `docs/integrations/dynastyprocess.md` — the sibling doc this one's structure mirrors
