# Usage Trends — weekly data update

**Date:** 2026-10-10 · **Status:** built on `feat/usage-trends`. It ships with the feature and is held for the home-engagement redesign like the rest of the branch.
**Code:**
- [`backend/usage_trends_refresh.py`](../../../backend/usage_trends_refresh.py) — the writer.
- [`backend/usage_trends.py`](../../../backend/usage_trends.py) — normalization and math.
- `backend/database.py` — the `usage_*` tables and helpers.
- [`scripts/refresh_usage_trends.py`](../../../scripts/refresh_usage_trends.py) — the CLI.
- `backend/tests/test_usage_trends_refresh.py`.

**Before this,** `GET /api/usage-trends` fetched Sleeper on demand and held results only in memory. Every restart refetched, the first request after a deploy paid for it, and nothing survived the season.

**Now** a weekly job stores each completed week once. It re-checks the week for stat corrections for seven days, then freezes it. The route reads the store.

## 1. Sources

| What | Where | Used for |
|---|---|---|
| NFL calendar | `GET https://api.sleeper.app/v1/state/nfl` → `season`, `week` (the week **in progress**), `season_type` (`pre` / `regular` / `post` / `off`) | Which weeks are complete. Regular season: weeks `1 … week−1`. Post season: weeks 1–18. Pre/off season: nothing new |
| Weekly stats | `GET https://api.sleeper.app/stats/nfl/{season}/{week}?season_type=regular&position[]=QB&position[]=RB&position[]=WR&position[]=TE&position[]=FB` (≈700 KB JSON, one row per player-week; company `sportradar`) | Everything below. The five fields read are `stats.off_snp`, `stats.tm_off_snp`, `stats.rush_att`, `stats.rec_tgt` and `stats.gp`, plus `player_id`, `team` and `player.{position, first_name, last_name}` |

- **Accuracy.** Checked 2026-10-10 against your snap CSV and the Footballguys target export: identical on 1652/1656 snap and 1648/1652 target player-weeks.
- **Cost.** Both endpoints are public, with no key and no vendor contract. As with the projections feed, that is not a licence to redistribute.
- **QB and FB rows** are fetched only so team totals are complete. Only RB/WR/TE players are stored.

## 2. Data structure and location

Three tables live in the app database: Postgres in production via `DATABASE_URL`, SQLite at `data/trade_finder.db` locally. They are created automatically at boot (`metadata.create_all`), so there is no migration step. Full column docs: [data dictionary](../../data-dictionary.md#usage-trends-weekly-store).

**`usage_week_loads`.** One row per stored week. A week counts only once this row exists.

| Column | Type | Meaning |
|---|---|---|
| `season`, `week` | int | Unique together |
| `source` | text | `sleeper_stats` |
| `first_fetched_at` | ISO UTC | First successful load. Starts the 7-day correction window |
| `fetched_at` | ISO UTC | Last fetch, changed or not |
| `changed_at` | ISO UTC | Last time the numbers actually changed (a stat correction) |
| `content_hash` | sha256 | Of the normalized week; unchanged content is not rewritten |
| `team_count`, `player_count` | int | Sanity readout (26–32 teams in a normal week) |

**`usage_team_weeks`.** One row per team per week. A team with no row in a loaded week was on bye.

| Column | Type | Calculation |
|---|---|---|
| `season`, `week`, `team` | int, int, text | Unique together. Sleeper team abbreviation |
| `snaps` | int | Team offensive plays: the max `tm_off_snp` over the team's rows (Sleeper repeats it on each) |
| `carries` | int | Sum of `rush_att` over the team's QB/RB/WR/TE/FB rows. **QB scrambles count** |
| `targets` | int | Sum of `rec_tgt` over the same rows |

**`usage_player_weeks`.** One row per RB/WR/TE per week.

| Column | Type | Calculation |
|---|---|---|
| `season`, `week`, `player_id` | int, int, text | Unique together. Sleeper `player_id`, the app's canonical id |
| `name`, `position`, `team` | text | `first_name last_name`, RB/WR/TE, and **his team that week** (trades move him) |
| `played` | 0/1 | 1 when `gp` > 0 or `off_snp` > 0. Inactive players still get a feed row carrying only `gms_active`; they store 0 |
| `snaps`, `carries`, `targets` | int | `off_snp`, `rush_att`, `rec_tgt` |

- **Size.** About 600 player rows (inactive players included) and 32 team rows per week, roughly 11,000 rows a season. Seasons are kept, which lets later features (season views, longer windows) read history without refetching.
- **Counts only.** No shares, averages or signals are stored. They are computed when read (§4), so changing a spike rule never requires rewriting data.

## 3. The update job

`refresh_usage_weeks(fetch_json, now=…, weeks=None, force=False, dry_run=False)` is the **only writer**. It is idempotent, so its three callers can overlap safely; a lock stops two in-app runs at once.

1. Read the NFL state to get the completed weeks.
2. **Plan** the run:
   - every completed week not yet stored (this is the backfill);
   - plus, for corrections, any stored week first loaded **under 7 days ago** whose last fetch was **20+ hours ago**.

   Older weeks are frozen.
3. For each planned week: fetch, then **normalize** (`usage_trends.normalize_week`, the calculations in §2), then **sanity-check**. A week with fewer than **24 teams** means the feed isn't finished; it is skipped and not stored. Then **hash**:
   - **changed:** replace the week whole, deleting and inserting in one transaction, and stamp `changed_at`;
   - **same:** only move `fetched_at`.
4. Return a summary: `{season, planned, stored, changed, unchanged, skipped{week: reason}, error?}`. A bad week never stops the others, and a half-written week can't exist.

**Schedule.**
- **Steady state** is the existing daily cron tick (13:30 UTC; `render.yaml` `notif-daily-tick`). It runs this step only while `usage_trends.enabled` is on; off, the tick's response is byte-identical to today. Most days the run costs one state call.
- **New week:** the first tick after Sleeper rolls `week` forward (Tue/Wed after Monday Night Football) loads the just-finished week.
- **Corrections:** that week is re-checked about once a day for its first 7 days, which catches stat corrections (usually in by Thursday), then frozen.
- **Network load:** about 5 stats fetches a week. Every user shares them.
- **No new Render service**, which follows the roster-snapshot and receipts precedent.

**Manual levers.**

| Command | What it does |
|---|---|
| `python3 scripts/refresh_usage_trends.py --remote` | Runs the job **on production** (`POST /api/cron/usage-trends-refresh`, `CRON_SECRET` from `secrets.local.env`). Works with the feature flag off, so the store can be **backfilled before launch** |
| `… --remote --weeks 3,4 --force` | Re-fetches those weeks now (a known stat correction) |
| `python3 scripts/refresh_usage_trends.py [--dry-run] [--weeks 1-4 --force]` | Runs against the **local** DB |
| `python3 scripts/refresh_usage_trends.py --status` | What the local DB holds, week by week |
| Production read | `SELECT season, week, team_count, player_count, fetched_at, changed_at FROM usage_week_loads ORDER BY season, week;` |

## 4. Calculations at read time (`GET /api/usage-trends`)

1. **Window.** The last 4 completed weeks.
   - If **all** of them are in the store, they are read from it.
   - Otherwise the whole window is fetched live, the old path. A window never mixes stored and live weeks.
   - The computed result is cached 6 hours, and a job run that stored new numbers clears that cache.
2. **Per player, per metric** (snaps, carries, targets), over the window:
   - **status per week:**
     - `played`;
     - `out` (his team played, he didn't);
     - `bye` (his team has no row that week).
   - **share** = player count ÷ team count that week, as a % to 1 decimal.
   - **average** = mean count over **played** weeks only (byes and missed games are left out).
   - **average share** = total played-week count ÷ total team count over those same weeks.
   - **Version B total** = sum of played-week counts.
3. **Signal (one per metric):**
   - **spike:** a played week whose share beats BOTH his earlier-weeks average share AND his previous game by 15 percentage points (snaps), 10 (carries) or 8 (targets), with at least 20 / 6 / 4 that week;
   - **return:** the newest week played after missed games;
   - **new role:** the first game of the window, with real volume;
   - **out:** missed the newest week;
   - **rising / falling:** share slope of 5 points a week or more over 3+ games.
4. **Order:**
   1. newest-week spikes and returns (biggest share jump first);
   2. a newest-week return or new role;
   3. older spikes (most recent first);
   4. rising;
   5. everyone else by average share.
5. **Trim:** players under 10% average snap share with no spike/return/new/rising signal are left out.

All of this lives in `usage_trends.compute_normalized`. It takes the same input whether the weeks came from the store or the live feed, and a test pins that the two paths give identical output on the real 2026 data.

## 5. Failure modes

| Case | What happens |
|---|---|
| Sleeper down during the job | Week reported `fetch_failed` (or `error: state_unavailable`); nothing written; the next tick retries |
| Feed not finished (Monday night stats lag) | `< 24 teams` → `incomplete`, skipped; next tick retries |
| Store behind (job off, new deploy) | Route falls back to the live fetch for that window, same numbers |
| Stat correction after day 7 | Not picked up automatically. Run `--remote --weeks N --force` |
| Bad data stored | Re-fetch with `--force`; the week is replaced whole |
