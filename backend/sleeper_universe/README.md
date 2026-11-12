# Sleeper trade universe crawler

> Research tool. Builds a local dataset of completed Sleeper trades, the rosters they happened between, the standings and schedule at the time, and the leagues' formats, from Sleeper's public REST v1 API. The Flask app never imports it. No production database is involved. Plan: `docs/plans/sleeper-trade-universe/` (`research-plan.md` lives on its own branch; `scope.md` is in this repo).

## Contents

- [Run it](#run-it)
- [The key](#the-key)
- [What it calls](#what-it-calls)
- [What is stored](#what-is-stored)
- [Rosters at a trade](#rosters-at-a-trade)
- [Standings, schedule and as-of inputs](#standings-schedule-and-as-of-inputs)
- [Leak scan](#leak-scan)
- [Code map](#code-map)

## Run it

From the repo root, with the backend's Python (3.12, standard library only):

```bash
# 1. Seeds: one Sleeper username or user id per line ('#' comments allowed).
#    Kept in the git-ignored data folder; never in the repo, a test or a log.
$EDITOR data/sleeper-universe/seeds.txt

# Pilot: about 150 league lineages across 2024-2026 (one league over three
# seasons counts once), about 21,000 requests, about 1.5 hours at 4 a second
python3 scripts/sleeper_universe.py run --cap 150

# Full pull (defaults: seasons 2024 2025 2026, 2 hops, 3,000 lineages, 4 requests a second)
python3 scripts/sleeper_universe.py run

# Resume after a stop, a 429 hard stop or a kill: run the same command again.
# Completed league-seasons are skipped; an interrupted one is redone whole.
python3 scripts/sleeper_universe.py run

# Report (aggregates only, plus the leak scan; exit 4 if the scan fails)
python3 scripts/sleeper_universe.py report          # or --json
```

Steps can run separately: `discover`, `pull` (also re-derives), `derive` (local only), `report`. Flags: `--seasons 2026` (any subset; a later, wider run adds to the same store and keeps lineage ids), `--hops`, `--cap`, `--limit`, `--rate` (max 10), `--max-429` (default 5), `--refresh-incomplete` (re-pull league-seasons that were not `complete` when pulled), `--data-dir` (tests use a temp dir).

Exit codes: 0 ok; 1 other error; 3 stopped on 429s; 4 leak scan failed; 5 blocked (a 403 or a Cloudflare block page); 6 a 200 whose body is not JSON; 7 circuit breaker (12 failed responses in a row, i.e. two requests' full retry cycles, or three failed league-seasons in a row); 8 another crawler process holds the machine-wide lock. Every stop keeps the checkpoints; re-run to resume.

Request budget: about 44 per league-season (league, rosters, users, 18 transaction legs, 18 matchup weeks, drafts plus one call per draft, traded picks, two brackets), plus `/state/nfl` once per run, plus discovery (1 call per season listed per new user, 1 rosters call per expanded league, 1 per predecessor league walked; estimated at about 8 per lineage until the pilot measures it). The pilot, `--cap 150` over three seasons: 150 x 3 x 44 = 19,800 pull requests plus about 1,200 for discovery, about 21,000 in all. A `run` prints its planned budget at the start and the pull plan (league-seasons queued x 44) before pulling.

One process only: `discover`, `pull` and `run` take an exclusive lock on `/tmp/ftf-sleeper-universe-crawler.lock`, machine-wide whatever the data folder, and refuse to start (exit 8) while another crawler holds it.

## The key

Owners are stored only as `HMAC-SHA256(key, "user:" + user_id)` (first 32 hex characters). The key comes from env `SLEEPER_UNIVERSE_HMAC_KEY`, else the key file `~/.config/ftf-sleeper-universe/hmac.key` (`--key-file` overrides), created on first run (directory 0700, file 0600). The key is never kept in the data folder, so a copy of the data does not carry it. The crawler refuses, rather than repairs: a key file readable by group or others; a key file inside the data folder, or an `hmac.key` left there; an env key that is set but empty, shorter than 32 characters or with fewer than 12 distinct characters; an env key and a key file that both exist and differ. The store records a fingerprint of the key and refuses a pull with a different one; `--allow-new-key` accepts the new key and records its fingerprint (owner keys made before that point no longer link).

**Losing the key breaks linkage across pulls**: the same manager pulled again under a new key gets a different owner key, and nothing can join the two. Back the key up somewhere private. Anyone holding the key and a candidate Sleeper user id can test whether that user is in the data; keep it as private as the data.

**The dataset is pseudonymous, not anonymous.** It keeps league ids and roster ids, so anyone holding the data can look any owner up through Sleeper's public API (`/league/<id>/rosters` names the owner of each roster). The keyed hash keeps identity out of the store itself; it does not make the data safe to share. Treat the data folder as personal data.

## What it calls

Public Sleeper REST v1 only, through one throttled client (token bucket, default 4 requests a second, hard maximum 10; retry with back-off on 429 / 5xx / network errors; `Retry-After` honoured; hard stop after 5 consecutive 429s; User-Agent `FTF-Research-Crawler/1.0`). Calls: `/state/nfl`, `/user/<username>`, `/user/<id>/leagues/nfl/<season>`, `/league/<id>`, `/league/<id>/rosters`, `/league/<id>/users`, `/league/<id>/transactions/<leg>` (legs 1-18), `/league/<id>/matchups/<week>` (weeks 1-18), `/league/<id>/drafts`, `/draft/<id>/picks`, `/league/<id>/traded_picks`, `/league/<id>/winners_bracket`, `/league/<id>/losers_bracket`.

**Answers that are not a list.** Every list endpoint must answer with a JSON list; a dict or an empty body is a failed request (retried, then the league-season fails and is not checkpointed). JSON `null` is accepted as "none of that thing" only where it can be legitimate: brackets (Sleeper answers `null` when a league has no bracket, e.g. playoffs off, `playoff_week_start` 0; seen live 2026-11-12) and, because the captures do not rule it out, transactions, matchups, drafts, draft picks and traded picks. Each accepted `null` is counted per endpoint in `runs.summary_json` and in the report (`null_answers_accepted_as_none_by_endpoint`), so a real hole stays visible. `null` on rosters or users is a failure. Three failed league-seasons in a row of the same rejected shape stop the run with a message saying the code's assumption is probably wrong.

**No playoffs** (`playoff_week_start` 0 or missing, no bracket): every played week is regular season; `outcomes` records no playoff result (seed, made-playoffs and champion are null, not "no") and the final finish is the final regular-season rank, with `finish_basis = regular_season_rank`; weeks remaining count the scheduled weeks still to play.

## What is stored

Data folder `data/sleeper-universe/` (git-ignored, mode 0700): `universe.sqlite` (0600), `raw/<season>/<league_id>.json.gz` (0600, one per league-season, written AFTER identity stripping), and the operator's `seeds.txt`. The key is elsewhere (see above). Kept indefinitely (operator decision 6, 2026-11-12).

Identity stripping is an **allow-list per payload type** (`identity.py`); every other field is dropped, every kept value must have the expected shape (an id or enum token, a number, a list of those), and every user id becomes its keyed hash.

| Payload | Kept | Dropped (examples) |
|---|---|---|
| `/league/<id>` | `league_id, previous_league_id, season, season_type, sport, status, total_rosters, draft_id, bracket_id, loser_bracket_id, roster_positions`, numeric `scoring_settings`, numeric `settings` | `name, avatar, metadata`, message ids, `company_id`, `shard` |
| `/rosters` | `roster_id, league_id`, `owner_id` → `owner_key`, `co_owners` → `co_owner_keys`, `players, starters, reserve, taxi, keepers`, numeric `settings` (record, points, `ppts`, `division`, FAAB used) | `metadata` (team name, record string, player nicknames `p_nick_*`), `player_map` |
| `/users` | `user_id` → `user_key`, `is_owner`. **Never stored raw** | `username, display_name, avatar, metadata` (team name), everything else |
| `/transactions/<leg>` | `transaction_id, type, status, leg, roster_ids, consenter_ids` (roster ids), `adds, drops` (player → roster), `draft_picks` (season, round, roster ids), `waiver_budget` (sender, receiver, amount), `settings.seq / waiver_bid`, `created, status_updated`, `creator` → `creator_key`, `metadata.notes` → `notes_code` (`outbid`, `roster_full`, `already_played`, `processed`, `other`) | the notes text, `player_map`, anything else |
| `/matchups/<week>` | `roster_id, matchup_id, points, custom_points, players, starters, starters_points, players_points` | anything else |
| `/drafts` | `draft_id, league_id, season, season_type, status, type, start_time, last_picked`, numeric `settings`, `slot_to_roster_id`, `draft_order` with user-id keys → user keys | `metadata` (draft name, description), `creators` |
| `/draft/<id>/picks` | `draft_id, pick_no, round, draft_slot, roster_id, player_id, is_keeper`, `picked_by` → `picked_by_key`, `metadata.position` | the rest of `metadata` (player names, team, news) |
| `/traded_picks` | `season, round, roster_id, owner_id, previous_owner_id` (all roster ids) | anything else |
| brackets | `r, m, t1, t2, w, l, p, t1_from, t2_from` | anything else |
| `/user/...`, `/state/nfl` | nothing from `/user`; from `/state/nfl` only `season, week, season_type, leg, display_week, previous_season, league_season, season_start_date` (in `runs`) | — |

Tables (`store.py` has the schema): base, written per league-season by `pull`: `leagues` (format features: teams, roster slots, starters, bench, taxi, reserve, superflex, 2QB, IDP, tight-end premium, PPR, passing TD, median, playoff teams and start week, trade deadline, waiver type, FAAB and budget, best ball, league type, an `unusual_scoring` flag, raw scoring settings and settings JSON), `league_members`, `rosters` (as reported at pull time), `roster_weeks` (players, starters, per-player and per-starter points, played), `matchups` (the schedule), `transactions` (all types), `drafts`, `draft_picks`, `traded_picks`, `brackets`. Derived, rebuilt by `derive`: `trades`, `trade_assets` (one row per player, pick, FAAB amount or in-trade release), `trade_rosters`, `standings_weeks`, `outcomes`, `standings_checks`, `reconstruction_checks`. Bookkeeping: `runs` (when, parameters including seasons, request counts per endpoint, seconds, code version, NFL state, leak-scan result), `league_index` (discovery frontier, hop, lineage), `discovery_users` (keys only), `skipped_leagues` (league id, season, reason only), `pull_checkpoints`, `pull_failures`, `user_keys`.

Dynasty filter: `settings.type == 2`, not best ball, 8 to 16 teams, status `in_season`, `post_season` or `complete`. Skip reasons: `not_dynasty`, `best_ball`, `team_count`, `not_started`, `cap_reached` (revived by a later run with room), `not_found`.

Cleaning flags on `trades.flags_json` (flag, never delete): `reversed_within_day`, `orphan_side` (a side's roster had no owner at pull), `during_draft` / `during_startup_draft` (10+ rounds), `low_trade_league` (< 3 trades in the league-season), `unusual_scoring`, `recon_below_target` (the league-season's weekly replay matched < 98%). Lopsided outliers need values the store does not hold (plan §5.6) and are not flagged.

## Rosters at a trade

`reconstruct.rosters_for_trade(conn, league_id, transaction_id)`. Every completed transaction row changes rosters through its `adds` / `drops`, whatever its `type` (trade, waiver, free agent, commissioner, or a type not seen before); failed or pending rows never do. Lineup moves (starter, bench, taxi, IR) are not transactions and change nothing. Draft picks add their player to the picking roster; Sleeper's pick objects carry no time, so every pick of a completed draft is timed at the draft's end (`last_picked`). Events are ordered by timestamp, never by an assumed leg.

- `in_season`: latest played snapshot of the same season before the trade's leg, plus that season's later moves before the trade.
- `forward`: previous season in the store (or a startup league): its last snapshot plus its later moves, then this season's moves and completed drafts before the trade.
- `backward`: previous season not in the store: the first played snapshot of the season, undoing every move up to that week dated at or after the trade, and every draft not finished before it. **Extra uncertainty:** a roster change before week 1 that left no transaction or pick (a commissioner edit, a reset) is invisible to it.

When forward and backward are both possible both run; `trade_rosters.alt_agrees` and the report give the agreement rate. The verifier replays every full week onto the next snapshot (and the offseason both ways when the prior season is present) and attributes each mismatching player to `no_add_event`, `no_drop_event`, `wrong_roster` or `other`, per season.

## Standings, schedule and as-of inputs

`standings.py` states its rules: regular season = played weeks before `playoff_week_start`; head-to-head by `matchup_id`; median leagues also count a result against the weekly median (H2H, median and combined stored apart); rank = combined win percentage, then points for, then roster id; `division_rank` stored; games back of the roster ranked `playoff_teams`. A week is **played** when `/state/nfl` says it is over and someone scored. The derived final record is checked against `/rosters` (`standings_checks`). `outcomes` gives the inferred seed, bracket results, losers-bracket place, final finish and champion.

`standings.standing_for_trade` gives each side's record, points for, rank, games back and weeks left as of the trade (previous season's final finish for an offseason trade, or `prior_season_not_in_store`). `asof.outlook_inputs` adds, per side, the reconstructed roster with each player's points and starts so far, opponents already played with results, and the remaining regular-season opponents with their record at that date. Nothing from the trade's own week or later is returned (pinned by a test that changes every later value).

## Leak scan

Runs at the end of every `discover` / `pull` / `run` and in `report`. It reads every file in the data folder except `seeds.txt` and `hmac.key` (decompressing `.gz`; the SQLite file both as raw bytes and cell by cell) and fails on: (a) a dropped field name (`username`, `display_name`, `team_name`, `name`, `avatar`, `metadata`, `p_nick_*`, ...) as a JSON key or a column; (b) a raw user id, found by HMAC-ing every 15-20 digit run and looking the result up in `user_keys`, so raw ids are never kept to check against (during a run the raw ids seen are also held in memory and matched directly); (c) during a run, the name values seen (held in memory, never written) matched exactly against every stored string (4+ characters, excluding the store's own vocabulary). Its output names files and counts only.

## Code map

`client.py` (HTTP), `identity.py` (key, allow-lists), `discover.py`, `pull.py`, `normalise.py`, `store.py`, `derive.py`, `reconstruct.py`, `standings.py`, `asof.py`, `report.py`, `cli.py`. Entry point `scripts/sleeper_universe.py`. Tests: `backend/tests/test_sleeper_universe_*.py` on the synthetic world in `backend/tests/support/sleeper_universe_world.py`.
