# Values at the trade's date — DynastyProcess and KeepTradeCut history

> What was built so the Sleeper trade-universe study can price each traded player and pick with the market's value on the trade's date, what each source does and does not cover, and how the two should be used together. Research plan: `research-plan.md` in this folder (§2, §5.6, §5.7, decision 5). Written 2026-11-12.

## Contents

- [Summary](#summary)
- [What was built](#what-was-built)
- [Store design](#store-design)
- [DynastyProcess history](#dynastyprocess-history)
- [KeepTradeCut history](#keeptradecut-history)
- [Picks](#picks)
- [Using the two sources together](#using-the-two-sources-together)
- [Differences an analyst must not mistake for a finding](#differences-an-analyst-must-not-mistake-for-a-finding)
- [Runbook](#runbook)
- [Open questions for the operator](#open-questions-for-the-operator)

## Summary

- Production holds dated values only from 2026-07-10. The study needs 2024 onward.
- **DynastyProcess (DP):** the public `dynastyprocess/data` repository keeps the git history of its value files. The new tool reads it from a local clone and writes one board per commit day, roughly **weekly**, 1QB and superflex, with picks.
- **KeepTradeCut (KTC):** the operator states the agreement covers reading history from the site. Each player page carries a **daily** value series back to 2020 for 1QB and superflex. The new reader fetches the rankings page plus one page per listed entry, politely, and writes daily boards.
- Both land in one SQLite file, `data/sleeper-universe/values.sqlite` (git-ignored, never production), as `source = "dp"` and `source = "ktc"`.
- No real data has been read yet. Coverage numbers below are from the committed DP fixtures and two KTC sample pages; the real runs will tell the rest.

## What was built

| Piece | Where | Network |
|---|---|---|
| Store, DP history builder, lookups, coverage report, generic CSV loader | `backend/universe_values.py` | None (git may fetch blobs lazily from a blobless clone) |
| KTC reader: polite fetcher, page checkpoints, parser, ingest | `backend/ktc_history.py` | Only in `run_pull`, run by the operator |
| CLI | `scripts/universe_values.py` (`clone-dp`, `inspect-dp`, `build-dp`, `pull-ktc`, `ingest-ktc`, `load-csv`, `coverage`, `value-on`) | `clone-dp`, `pull-ktc` |
| Tests | `backend/tests/test_universe_values.py`, `backend/tests/test_ktc_history.py` (synthetic fixtures; a temporary git repository; a fake site) | None |

Neither module is imported by the Flask app. Standard library only.

## Store design

| Table | One row per | Columns |
|---|---|---|
| `value_boards` | source, format, board date | `source` (`dp`, `ktc`, optionally `ktc_vft` / `ktc_blend`), `format` (`1qb`, `sf`), `board_date`, `published_at` (UTC instant the board became public: DP commit time; KTC end of day), `commit_sha` (DP), `scrape_date` (DP), `header` (DP layout audit), `picks_file`, `player_rows`, `mapped_rows`, `pick_rows`, `collisions` |
| `values` | board, asset | `asset_key` (Sleeper player id or pick key), `asset_type`, `value`, `position`, `age` (DP only), `source_id` (DP `fp_id` / KTC `playerID`), `match_tier` |
| `unmapped` | board, source id | rows that did not map to a Sleeper id, keyed by the source's own id only (DP `fp_id`, else `name:<player>\|<pos>` when the DP row has no `fp_id`; KTC `playerID`) |
| `build_log` | build | what was built from what (clone HEAD, crosswalk revision, counts) |

**Lookup.** `ValueStore.value_on(when, asset_key, format, source=...)` returns the latest board at or before `when` that carries the asset, with `age_days` and `latest_board_date` (the newest board of that source at or before `when`; if it is newer than `board_date`, the asset had dropped off). A plain date matches boards dated that day or earlier; an ISO datetime matches only boards **published** by that instant, which is the strict no-look-ahead form to use with trade timestamps. `pick_value_on` is described under [Picks](#picks).

**Coverage report** (`coverage`): per source and format, boards per month, the longest gap between boards, the share of player rows mapped to Sleeper ids (overall and the worst board), the distinct unmapped ids with the highest-valued ones listed. Given `--lookups` (a CSV `asset_key,date`, which the crawler will supply for traded assets), it reports for each format the share with a value within `--max-age` days (default 14) per source, and how many have `dp+ktc`, only `dp`, only `ktc`, or `none`.

## DynastyProcess history

**Input.** A blobless clone of `github.com/dynastyprocess/data`. For every UTC day on which `files/values-players.csv` was committed (the day's last commit), from 2024-01-01 plus the last board before it, the builder reads at that commit:

- `files/values-players.csv` — players;
- `files/values.csv` `pos == "PICK"` rows — picks (the file the app already reads), else `files/values-picks.csv`;
- `files/db_playerids.csv` at the clone's HEAD — the crosswalk.

**Columns.** The 2026 layout is `player, pos, team, age, draft_year, ecr_1qb, ecr_2qb, ecr_pos, value_1qb, value_2qb, scrape_date, fp_id`. A board must carry `player, pos, value_1qb, value_2qb` and nothing outside those twelve; a narrower known layout is accepted and its header stored on the board. Anything else (a renamed or new column) fails the whole build and lists every offending commit and header, with nothing written. Run `inspect-dp` first: it lists each distinct header of the three files and the commit range each covers. If the real history has an older layout, the fix is a deliberate addition to `DP_KNOWN_COLUMNS` (or an alias), not a silent guess.

**Formats.** `value_1qb` -> `1qb`; `value_2qb` -> `sf`. DP publishes nothing else: no tight-end premium (the app's own note in `data_loader.py` measures DP's `sf` TE values about 25 % below their 1QB analogs), no league size, no PPR variants. Values are on a 0-10000 scale.

**Join to Sleeper ids.** `fp_id` -> `db_playerids.fantasypros_id` first, position-strict (ids beat names, #127); then the existing name tiers of `dp_values_history` (tier 1, then generational-suffix-stripped tier 2), also position-strict. A test proves the name tiers give exactly `dp_values_history.build_value_map`'s result on a committed board. Rows that do not map are stored in `unmapped`, never guessed.

**What the committed fixtures already show (no network).** The 24 boards in `backend/tests/fixtures/dp-values-history/` (2022-2025, autumn only) were each committed on a Friday, six days before their Thursday target: a **weekly** cadence. Board sizes run 324 to 647 valued rows. With the name tiers alone and the trimmed bundled crosswalk, the 2024 boards leave 6-17 rows unmatched (about 1-3 %), the 2025 boards 2-8. The `fp_id` tier should close part of that (for example "Ken Walker III", which no name rule bridges), if `fp_id` was populated in older files.

**What only a real clone will tell.** Whether the header changed between 2024 and today; whether `fp_id` and `age` were present throughout; whether `values.csv` carried PICK rows for the whole period or `values-picks.csv` must stand in; the real cadence through each offseason (the fixtures hold only September-December boards); the real mapping rate with the full crosswalk.

**Licence.** The repo's own docs record the source as CC-BY DynastyProcess with an attribution obligation (`backend/dp_values_history.py` docstring, `docs/integrations/dynastyprocess.md`). The licence text itself was not read here (no network); check `LICENSE` in the clone.

## KeepTradeCut history

**Pages read** (structure taken from two sample pages the main session fetched on 2026-11-12; no page content is committed):

- `https://keeptradecut.com/dynasty-rankings`: `<script type="application/json" id="ktc-players">`, 500 entries, `position` QB/RB/WR/TE plus 36 `RDP` pick entries (2027-2029, Early/Mid/Late, rounds 1-4). Each has `playerID`, `playerName`, `slug`, `mflid`. The reader parses it with the app's own regexes (`data_loader._KTC_PLAYERS_ELEMENT`, `_KTC_PLAYERS_LITERAL`) but keeps the `RDP` entries, which the app's `parse_ktc_players` drops.
- `https://keeptradecut.com/dynasty-rankings/players/<slug>`: `id="pd-oneqb"` and `id="pd-superflex"` (plus `pd-players`, the same 500 list again, not read). Each block holds `overallValue`, `overallRankHistory`, `positionalRankHistory`, `vftValueHistory`, `vftOverallRankHistory`, `vftPositionalRankHistory`, `blendValueHistory`, `blendOverallRankHistory`, `blendPositionalRankHistory`, adjacent-player lists, and `tep`/`tepp`/`teppp`. The sample page (a top quarterback) had 2,414 daily 1QB points from 2020-04-01 and 2,359 superflex points from 2020-05-26, about 1,047 days since 2024-01-01, largest gap 3 days.

**Which series is stored, and why.**

- `overallValue` is stored as `source = "ktc"`. It is the crowd-sourced keep/trade/cut value, the number the site shows by default (`var blendRatio = 0.0` on the page) and the same family the app's blend reads today.
- `vftValueHistory` ("Values from Trades", introduced in 2026 per the page's `vftLaunch2026` banner: "values powered by real trades, crowdsourcing, or both") and `blendValueHistory` (crowd and trade values mixed by the `blendRatio` slider) are kept in the page checkpoints and can be loaded as `ktc_vft` / `ktc_blend` (`ingest-ktc --series vft`), but are **not** the default. On the sample page they equal the crowd value exactly until 2021-07-26 and diverge after, so the pre-launch part is a back-fill computed later; and a value derived from trades may be derived from the very Sleeper trades this study analyses, which would make any "who paid more" finding circular.
- The `tep`/`tepp`/`teppp` objects on the player page hold only adjacent-player lists, no series. **There is no tight-end-premium history.** `sf` here is plain superflex, unlike the app's live `sf_tep` read (`superflexValues.tep.value`).

**Parsing details.** Days are `YYMMDD` (read as 20YY). A day listed twice keeps its last point (the sample page has 6-7 such days per format, mostly around 2021-07-26 and three in autumn 2026); the count is kept per page.

**Politeness and safety.** One process; one request every 3 s by default (`--interval`, floor 1 s), counted from the end of the previous answer; the app's browser headers plus `Accept-Encoding: gzip`; back-off and retry on 429, 5xx and network errors (30/60/120/240 s, `Retry-After` honoured); no retry on 404; a hard stop after 3 consecutive 403/429 answers, leaving the checkpoint. A page is done only when its gzip checkpoint is fully written (`pages/<slug>.json.gz`); a restart skips done pages and retries failed ones. Raw HTML is not kept (about 4 MB a page) unless `--keep-html`. The transport, clock and sleep are injectable; the tests use fakes.

**Join to Sleeper ids.** `playerID` -> `db_playerids.ktc_id`, then `mflid` -> `mfl_id`, then name + position through the same name tiers; never across positions. The crosswalk must be the full `db_playerids.csv` (the clone's), because the app's bundled snapshot has no `ktc_id` column. Unmapped entries are stored by KTC id only.

**Coverage limits to measure, not assume.**

- Only the **current** top 500 and current pick entries are listed. A player who has since fallen out of the top 500 (retired, cut, busted) is missing for the whole period, which biases against exactly the assets that lost value. Picks for drafts that already happened ("2025 Mid 1st" as valued in 2024, "2026 Early 2nd" as valued in 2025) are not listed either.
- `--extra FILE` takes extra slugs (or KTC ids already in the list) to fetch. A bare id with no slug cannot be turned into a URL and is reported as unresolved. The slug for a pick is `<year>-<early|mid|late>-<round><suffix>-<id>`; the ids are not guessable (2027 picks are 1702-1713, 2028 are 1882-1893, 2029 are 2126-2137).
- The coverage report against the crawler's traded players and dates says how many have a KTC value, how many only a DP one, and how many neither.

## Picks

**Pick keys** (shared by both sources and by the crawler's pick identity):

| Source label | Key |
|---|---|
| "2026 Pick 1.01" (DP, current draft year, 12-team slots) | `pick:2026:1:01` |
| "2027 Early 1st" (DP and KTC) | `pick:2027:1:early` |
| "2028 2nd" (DP, round only) | `pick:2028:2` |

DP's `values.csv` carries slots 1.01-5.12 for the current draft year and Early/Mid/Late plus round-only rungs, rounds 1-5, for future years (fixture `dp_values_picks_2026-08-06.csv`). KTC lists Early/Mid/Late, rounds 1-4, for the next three years; its numbered current-year picks appear only on a current-year pick page and are not read.

**Choosing the value for a traded pick** (`pick_value_on(when, season, round, format, slot=, bucket=, teams=)`, which falls back slot -> bucket -> round and reports the level used):

1. **The draft has happened by the trade's date:** the trade is of the drafted player (the crawler resolves the pick to its player), so price the player, not the pick.
2. **The draft order is set but the draft has not happened** (the crawler resolved the slot): pass `slot`. DP's slot curve is 12-team, so the slot key is used only when `teams == 12`; otherwise the slot becomes a bucket by thirds of the round (12 teams: 1-4 early, 5-8 mid, 9-12 late).
3. **Before the order is set:** pass `bucket` from the original team's standing at the trade's date (plan §5.7; the same input the app's live pick pricing uses). In the offseason before a draft, use the previous season's final standing; in season, the standing so far. Pass `bucket=None` when the standing is unknown and accept the round-only or Mid value.

Do not use the slot the pick *eventually* got for a trade made before the order was known: that is look-ahead.

## Using the two sources together

- **Primary:** KTC crowd value when a KTC point exists within 7 days of the trade (it is daily, so a gap that long means the asset was missing, not stale). **Fallback:** DP within 14 days. Report every result three ways: KTC-only rows, DP-only rows, and the combined "KTC, else DP" set, with the counts of each.
- **Never mix within one trade.** Price both sides of a trade with the same source, or the trade is excluded from that analysis. The two scales differ (below), so a mixed trade can show a "winner" that is just the scale difference.
- **Cross-check:** on trades both sources price, report the agreement on who received more value (sign agreement) and the rank correlation of the value differences. A finding that holds under one source but reverses under the other is reported as fragile.
- **Formats:** use `sf` for superflex/2QB leagues and `1qb` otherwise. Neither source has a tight-end-premium history; for TE-premium leagues report TE-involving trades separately.
- **Staleness:** keep `age_days` with every priced asset. Exclude, or report separately, assets priced from a board older than the threshold.

## Differences an analyst must not mistake for a finding

- **Scale.** KTC tops out at 9999 and its curve is fatter in the middle; DP tops out near 10000 with a steeper top. The app's own blend rank-normalises KTC onto DP's curve for this reason (`data_loader.py`, #145). Compare values only within a source, or rank-normalise per board before comparing across sources.
- **Cadence.** DP moves in weekly steps; KTC daily. Price moves around a trade date will look sharper in KTC.
- **Universe.** KTC's listed universe is today's top 500, so assets that collapsed are under-covered in KTC and present in DP. A "KTC says trades of declining players are rare" result is a coverage artefact.
- **Origin.** DP is derived from expert rankings (FantasyPros consensus); KTC crowd values from user keep/trade/cut votes. Their disagreements are real but expected.
- **No TE premium in either history.** TE value in a TE-premium league is understated by both.
- **Picks.** DP has slot values only for the current draft year and rounds 1-5; KTC has Early/Mid/Late for three future years, rounds 1-4. A pick that one source prices and the other cannot is a coverage difference, not a valuation one.
- **Values from Trades.** If anyone loads `ktc_vft`/`ktc_blend`, results may be circular (the values may come from these very trades) and the series before 2026 is a back-fill.

## Runbook

All paths relative to the repo root; nothing under `data/` is committed.

```bash
# DynastyProcess
python3 scripts/universe_values.py clone-dp --dest data/sleeper-universe/dp-data          # network
python3 scripts/universe_values.py inspect-dp --repo data/sleeper-universe/dp-data        # headers per commit range
python3 scripts/universe_values.py build-dp --repo data/sleeper-universe/dp-data          # git may fetch blobs lazily

# KeepTradeCut
python3 scripts/universe_values.py pull-ktc [--extra data/sleeper-universe/ktc-extra.txt]  # network, ~540 pages at 1 per 3 s
python3 scripts/universe_values.py ingest-ktc --repo data/sleeper-universe/dp-data

# Reading
python3 scripts/universe_values.py coverage [--lookups data/sleeper-universe/traded-assets.csv]
python3 scripts/universe_values.py value-on --date 2024-10-01 --asset <sleeper_id> --format sf --source ktc
```

A failed `build-dp` writes nothing and names the commits to look at. A `pull-ktc` hard stop exits 2; re-run later and it resumes. `ingest-ktc` and `build-dp` are full rebuilds of their source.

## Open questions for the operator

1. **KTC terms detail.** Does the agreement allow keeping the page-derived series indefinitely (decision 6 says no retention limit for the study's data), and is any attribution needed in published findings?
2. **Rate.** Is one request every 3 s acceptable to KeepTradeCut, and is there a preferred time of day or a contact to tell before the pull?
3. **Missing assets.** Can KeepTradeCut supply (or permit a bounded search for) the slugs of players who left the top 500 since 2024 and of the 2024-2026 draft picks, so the history is not biased toward today's survivors?
4. **Values from Trades.** Should the study ever use `vftValueHistory`, given it may be built from these trades and its pre-2026 part is a back-fill?
5. **TE premium.** Is there a TEP history anywhere under the agreement? Neither source has one.
