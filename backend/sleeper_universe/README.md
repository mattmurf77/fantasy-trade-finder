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

Steps can run separately: `discover`, `pull` (also re-derives), `derive` (local only), `report`. Flags: `--seasons 2026` (any subset; a later, wider run adds to the same store and keeps lineage ids), `--hops`, `--cap`, `--limit`, `--rate` (max 10), `--max-429` (default 5, at most 20), `--refresh-incomplete` (re-pull league-seasons that were not `complete` when pulled), `--retry-failed` (requeue league-seasons dropped after failing), `--key-file`, `--data-dir` (tests use a temp dir).

Seed file rule: `id:<digits>` is a user id; `user:<name>` is a username; a bare line of 15 or more digits is a user id (Sleeper user ids are 18-19 digits); anything else, including a shorter all-digit line, is a username resolved through `/user/<name>`. `#` starts a comment.

A league-season that fails is retried on later runs, after everything that has not failed (so it cannot eat `--limit`), and dropped from the queue after 3 failures; a deleted league (`/league/<id>` answers null) is dropped at once. `--retry-failed` requeues them.

A store built by an older version is migrated on open (missing columns are added; see `store.MIGRATIONS`). Rows pulled before a column existed hold NULL there.

`report` exits 9 when the derived tables were written by an older `derive` (it says DERIVE NEEDED and still prints, with figures it cannot trust marked `not_derived` rather than counted as disagreements): run `derive` on the existing store, then `report` again; no re-pull is needed.

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

Identity stripping is an **allow-list per payload type** (`identity.py`); every other field is dropped and every user id becomes its keyed hash. Every kept value must have its field's shape, and no validator accepts free text: league, draft and transaction ids are 1-20 digits; player ids are 1-8 digits or a 2-3 letter team code; seasons are four digits; roster ids, weeks, rounds, slots and bracket fields are small integers; timestamps are epoch milliseconds; enums (status, season type, sport, transaction type and status, draft status and type, roster slots, positions) come from closed vocabularies, with anything else stored as `other` (transaction type: so a new type is counted without its text being kept) or dropped; league, roster and draft `settings` keep only known keys (lists in `identity.py`, taken from real payloads) with values below 1e9; scoring keys must be built from known scoring words and numbers (`pass_td`, `bonus_rec_te`, `pts_allow_14_20`). Every value discovery writes (`league_id`, `previous_league_id`, `status`, `season`) goes through the same validators. Dropped keys and values are counted in memory per kind. A user id and a draft id have the same shape, so a user id placed in an id field cannot be refused by shape: the leak scan catches it when the user is one the crawler hashed.

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
| `/user/...`, `/state/nfl` | nothing from `/user`; from `/state/nfl` only `season, week, season_type, leg, display_week, previous_season, league_season, season_start_date` (shape-checked, in `runs`) | — |

Tables (`store.py` has the schema): base, written per league-season by `pull`: `leagues` (format features: teams, roster slots, starters, bench, taxi, reserve, superflex, 2QB, IDP, tight-end premium, PPR, passing TD, median, playoff teams and start week, trade deadline, waiver type, FAAB and budget, best ball, league type, an `unusual_scoring` flag, raw scoring settings and settings JSON), `league_members`, `rosters` (as reported at pull time), `roster_weeks` (players, starters, per-player and per-starter points, played), `matchups` (the schedule), `transactions` (all types), `drafts`, `draft_picks`, `traded_picks`, `brackets`. Derived, rebuilt by `derive`: `trades`, `trade_assets` (one row per player, pick, FAAB amount or in-trade release), `trade_rosters`, `standings_weeks`, `outcomes`, `standings_checks`, `reconstruction_checks`. Bookkeeping: `runs` (when, parameters including seasons, request counts per endpoint, seconds, code version, NFL state, leak-scan result), `league_index` (discovery frontier, hop, lineage), `discovery_users` (keys only), `skipped_leagues` (league id, season, reason only), `pull_checkpoints`, `pull_failures`, `user_keys`.

Dynasty filter: `settings.type == 2`, not best ball, 8 to 16 teams, status `in_season`, `post_season` or `complete`. Skip reasons: `not_dynasty`, `best_ball`, `team_count`, `not_started`, `cap_reached` (revived by a later run with room), `not_found`.

Cleaning flags on `trades.flags_json` (flag, never delete): `reversed_within_day`, `orphan_side` (a side's roster had no owner at pull), `during_draft` / `during_startup_draft` (10+ rounds), `low_trade_league` (< 3 trades in the league-season), `unusual_scoring`, `recon_below_target` (the league-season's weekly replay matched < 98%). Lopsided outliers need values the store does not hold (plan §5.6) and are not flagged.

## Rosters at a trade

`reconstruct.rosters_for_trade(conn, league_id, transaction_id)`. Every completed transaction row changes rosters through its `adds` / `drops`, whatever its `type` (trade, waiver, free agent, commissioner, or a type not seen before); failed or pending rows never do. Lineup moves (starter, bench, taxi, IR) are not transactions and change nothing; real matchup `players` lists include taxi and IR players (99.9% of current taxi and reserve players are in the weekly snapshots). Draft picks add their player to the picking roster (the pick's `roster_id`; crediting by `picked_by` matched worse); Sleeper's pick objects carry no time, so every pick of a completed draft is timed at the draft's end (spreading picks over the draft by pick number matched worse).

**When a snapshot is taken.** A week's matchup `players` list is the roster at a moment inside the week, not at the end of the leg. On the pilot (352 league-seasons) replaying by leg matched 69.9% of roster-weeks; replaying by timestamp to one instant per week matched up to 94.7%, best from **Sunday 13:00 US Eastern** of the NFL week (the main kickoff) and flat to about 17:00. That is the rule (`reconstruct.SnapshotClock`): NFL week 1's Thursday is the Thursday after Labor Day, and the UTC hour moves when US daylight time ends in November. Every boundary is an instant and every transaction is placed by its timestamp (`status_updated`; `created` matched worse, 92.5%); legs are not used. Rows with an empty `players` list are not snapshots (no lineup set, or a week past the league's season): they are dropped and counted (`empty_snapshot_rows_not_compared`).

Optional per-player lock: with `--nfl-schedule <nflverse games CSV> --player-teams <JSON>` on `derive` / `pull` / `run`, each player's instant is his own team's kickoff that week (a Monday-night player can still move on Sunday afternoon). On the 2026 pilot seasons, with teams known for 76% of player-weeks (from a current-team list, a proxy), it matched 96.2% against 94.75% for the fixed rule. Without those inputs the fixed rule is used; `meta.snapshot_rule` and the report say which.

**Ceiling and residual** (pilot, fixed rule): 94.7% in season, below the 98% target. Fitting one instant per league-week, which is circular and only an upper bound, reaches 95.7%, so the residual is not one timing per week. What is left is per player: moves made up to three days after the player's game that the snapshot still reflects, consistent with a matchup row being re-saved later (for example on a stat correction), and moves before the instant that it does not reflect. The data has no timestamps for those re-saves. The report gives the mismatching players by cause, per season.

- `in_season`: latest snapshot of the same season whose instant is before the trade, plus that season's moves after the instant and before the trade.
- `forward`: previous season in the store (or a startup league): the previous season's **final `/rosters`** (the frozen end-of-season roster: 93.8% against week 1 on the pilot, against 83.0% for its last snapshot plus later moves), then this season's moves and completed drafts before the trade.
- `backward`: previous season not in the store: the first snapshot of the season, undoing every move up to its instant dated at or after the trade, and every draft pick not finished before it. **Extra uncertainty:** a roster change before week 1 that left no transaction or pick (a commissioner edit, a reset) is invisible to it.

When forward and backward are both possible both run; `trade_rosters.alt_agrees` and the report give the agreement rate. The verifier replays each snapshot to the next snapshot's instant (`in_season`), and the offseason both ways when the prior season is present (`offseason_forward`, `offseason_backward`), and attributes each mismatching player to `no_add_event`, `no_drop_event`, `wrong_roster` or `other`. The report still counts transactions whose leg goes backwards in time order (`leg_time_inversions`).

## Standings, schedule and as-of inputs

`custom_points` (a commissioner's score override) is the week's score when present; the original is kept in `matchups.points_original`. `standings.py` states its rules: regular season = played weeks before `playoff_week_start`; head-to-head by `matchup_id`; median leagues also count a result against the weekly median (H2H, median and combined stored apart); rank = combined win percentage, then points for, then roster id; `division_rank` stored; games back of the roster ranked `playoff_teams`. A week is **played** when `/state/nfl` says it is over and someone scored. The derived final record is checked against `/rosters` (`standings_checks`), with records (`record_matched`) and points (`points_matched`) judged apart: a stat correction moves Sleeper's points without any bug here and never a record. `outcomes` gives the inferred seed, bracket results, losers-bracket place, final finish and champion.

`standings.standing_for_trade` gives each side's record, points for, rank, games back and weeks left as of the trade (previous season's final finish for an offseason trade, or `prior_season_not_in_store`). `asof.outlook_inputs` adds, per side, the reconstructed roster with each player's points and starts so far, opponents already played with results, and the remaining regular-season opponents with their record at that date. Nothing from the trade's own week or later is returned (pinned by a test that changes every later value).

## Leak scan

Runs at the end of every `discover` / `pull` / `run`, after the run's own record is written (so it sees everything the run wrote; its own result, file names and counts, is the one write after it), and in `report`. It reads every file in the data folder except exactly two operator files at its top level, `seeds.txt` and `hmac.key`; gzip data is recognised by its magic bytes whatever the name (`.tmp` files too); the SQLite file is read as raw bytes (schema, column names and free pages included; the store runs with `secure_delete`, so deleted rows are zeroed) and cell by cell (text, integer and real cells; JSON cells parsed). It fails on:

- (a) a dropped field name (`username`, `display_name`, `team_name`, `name`, `avatar`, `metadata`, `p_nick_*`, ...) as a JSON key or a column;
- (b) a raw user id: every digit run of 12-20 digits whole, and every 15-20 digit window inside any longer run (an id glued to neighbouring digits in a SQLite record is still found), HMAC'd and looked up in `user_keys`, so raw ids are never kept to check against; during a run the raw ids seen are also held in memory and matched directly;
- (c) during a run, a name value seen in a name field (held in memory with the field it came from, never written). Every decoded SQLite cell, every string and key of a raw file, every line of any other file and the SQLite schema are checked against every name; a name hits when its word sequence appears (inside longer strings too), or, for a first word of 6+ characters, glued inside a longer word. The SQLite file's raw bytes (free pages, overflow) are checked only for ASCII names of at least 11 word characters: binary pages read as text match short names by chance (a live run failed on a player named "J.J." meeting two one-letter words). The threshold: with a noise byte matching a given word character at a conservative 1/36, the expected chance matches over a pull are 3e9 bytes x 1e5 names x 36^-c, below 0.01 for c >= 11. The store runs with `secure_delete`, so its own deleted rows are zeroed; the raw pass is for pages freed by other writers. Names left out of it are counted (`names_excluded_from_raw_bytes_pass`). A name made only of words the store legitimately holds as values (numbers, player-id or team-code shapes, 1-2 character tokens, and every fixed word the crawler writes, from the schema and its own code) cannot be told apart from data ("2025", "J.J.", "QB 1"): it is skipped and counted (`ambiguous_names_skipped`). Every hit reports where it is (`file:table.column`, a raw file's key path with only the crawler's own keys shown, `file@pageN`, `file:lineN`, `file:schema`), the name's source field (e.g. `draft.picks.first_name`) and its shape (words, characters), never the name. NFL player names from draft-pick metadata stay canaries: they prove pick metadata is not stored, and with the rules above they force no weaker check;
- (d) any number cell of 1e15 or more (nothing the store keeps as a number is that large; an id stored as a number is caught even after a REAL lost its low digits).

Not detectable by value, by design: an id in another encoding (hex, base64), an id of a user the crawler never saw, a name glued inside a word when its first word is under 6 characters. `report` mode cannot check name values or raw ids of users never hashed (both exist only in a run's memory) and says so in its output (`not_checked`). Output names files and counts only.

## Code map

`client.py` (HTTP), `identity.py` (key, allow-lists), `discover.py`, `pull.py`, `normalise.py`, `store.py`, `derive.py`, `reconstruct.py`, `standings.py`, `asof.py`, `report.py`, `cli.py`. Entry point `scripts/sleeper_universe.py`. Tests: `backend/tests/test_sleeper_universe_*.py` on the synthetic world in `backend/tests/support/sleeper_universe_world.py`.
