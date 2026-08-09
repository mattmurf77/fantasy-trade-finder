# DynastyProcess — consensus values CSV pipeline

> Public, unauthenticated GitHub-hosted CSVs that seed the trade engine's Elo baseline and (display-only) the Draft Room's per-slot pick prices. All data is public — nothing here needs redaction in logs.

## Table of Contents

- [What it is](#what-it-is)
- [Endpoints / files fetched](#endpoints--files-fetched)
- [Fetch triggers, cadence, and caching](#fetch-triggers-cadence-and-caching)
- [Consumed fields](#consumed-fields)
- [Error modes](#error-modes)
- [Related: KeepTradeCut blend](#related-keeptradecut-blend)
- [Instrumentation guidance](#instrumentation-guidance)
- [Test seams](#test-seams)
- [Source](#source)

## What it is

[DynastyProcess](https://github.com/dynastyprocess/data) publishes a community-consensus dynasty fantasy football values dataset as flat CSV files on GitHub (`raw.githubusercontent.com`), refreshed by their own pipeline roughly daily. Fantasy Trade Finder reads these files unauthenticated over plain HTTP GET — no API key, no rate-limit contract, no ToS beyond "be a polite client." This is the pipeline that seeds every player's starting Elo rating (`backend/data_loader.py`), which the trade engine then personalizes via user swipes.

## Endpoints / files fetched

| File | URL constant | Module | Purpose |
|---|---|---|---|
| `files/values-players.csv` | `data_loader.VALUES_URL` | `backend/data_loader.py` | Per-player consensus dynasty trade values (0–10000 scale), both 1QB and Superflex/2QB columns. **This is the pipeline that seeds Elo** — every ranking pool build reads it. |
| `files/values.csv` | `data_loader.PICK_VALUES_URL` | `backend/data_loader.py` | DynastyProcess's **combined** file — same player rows as `values-players.csv` PLUS `pos == "PICK"` rows: per-slot current-year pick prices (`"2026 Pick 1.01"` … `"2026 Pick 5.12"`) and future-year rungs (`"2027 Early 1st"`, `"2028 2nd"`, …). FTF reads it **only** for the PICK rows, via `load_pick_slot_values`. |
| `files/db_playerids.csv` | `espn_service.PLAYERIDS_URL` | `backend/espn_service.py` | **Third** DynastyProcess file, same repo — an ID crosswalk (`sleeper_id`, `espn_id`, `mfl_id`, `sportradar_id`, `yahoo_id`, `ktc_id`, `merge_name`/`name`) used to id-match players across platforms: ESPN roster imports (`map_rosters`), the Fleaflicker `sportradar_id` join, and the KTC blend's id-based matching (`get_crosswalk().by_ktc_id` / `.by_mfl_id`, see below). Not part of the values pipeline itself, but same source and same trust boundary — documented here rather than a fourth file. |

All three are plain GET requests with `User-Agent: FantasyTradeFinder/1.0`, `timeout=10`–`15`s.

**`values.csv` is display-only — not consumed by the trade engine.** As of this writing it prices individual draft slots on the Draft Room board's `order[].slot_value` (behind flag `picks.slot_values`) and nowhere else. `pick_values.GENERIC_PICK_SEEDS`, the tier ladder, the tier bands, and the trade engine all use FTF's own hand-tuned pick seeds, not DynastyProcess's slot curve — DP's current-year curve is steeper than FTF's shipped ladder, so adopting it in the engine would be a repricing decision, not a data plumb. `docs/plans/rookie-draft/plan.md` §0.5 records this boundary (bound KD-9) and an operator decision (O2) that **reverses** it for a future wave (M6b): market slot values are slated to enter the engine behind a #214-style user toggle in a dedicated calibration pass — but not from this code path today. Do not read "display-only" as "permanent"; read it as "not yet, and not here."

## Fetch triggers, cadence, and caching

**`values-players.csv` (player values → Elo seeds):**
- Fetched once per scoring format (`1qb_ppr`, `sf_tep`) inside `backend/server.py::_load_dp_maps`, called from `_build_universal_pools_locked` → `_ensure_universal_pools`.
- **No TTL on success** — once a format's universal pool is built, the fetch result is cached in-process (`dp_values_by_format` / `dp_elo_by_format` / `dp_pos_by_format`) until the process restarts or the player pipeline is explicitly invalidated (`POST /api/cron/players-refresh`, which walks disk → Sleeper cache → `sync_players` → DynastyProcess maps → universal pools → pool-generation bump).
- **On failure, a 60s retry backoff** (`_DP_FETCH_RETRY_SECONDS`) — a failed or empty fetch is never cached as a valid empty pool; the next access after the backoff retries.
- **Single-flight:** builds are serialized on `_pool_build_lock` so a refresh daemon tick and a concurrent request worker never both fan out their own fetch.
- The two scoring formats fetch concurrently via `ThreadPoolExecutor` inside `_load_dp_maps`.

**`values.csv` (pick slot prices — separate egress):**
- Fetched lazily on first Draft Room board render that needs slot values (`data_loader.load_pick_slot_values`), independent of the player-values fetch above.
- **24h in-memory TTL** (`_PICK_VALUES_TTL_SECONDS`), shared across both scoring formats from a single fetch. `reset_pick_values_cache()` exists for tests only.
- Fail-soft: any fetch/parse failure returns `{}` (cached for the TTL too, so a broken endpoint isn't re-hammered) and the Draft Room simply renders without the slot-value axis.

**`db_playerids.csv` (ID crosswalk):**
- Lazy 24h in-memory TTL (`espn_service._CROSSWALK_TTL_SECONDS`), first fetched on first `get_crosswalk()` call after boot (not eagerly at startup).
- Three-tier fallback on failure: (1) live fetch, (2) last good in-memory copy if the live fetch fails, (3) a bundled snapshot fixture (`backend/tests/fixtures/dp_playerids_snapshot_2026-07-11.csv`) if there's no in-memory copy yet. A snapshot-served crosswalk retries hourly instead of waiting the full 24h, so it self-heals quickly once the live fetch starts working again.
- `get_crosswalk()` never raises.

## Consumed fields

From `values-players.csv` (columns present in the live file: `player, pos, team, age, draft_year, ecr_1qb, ecr_2qb, ecr_pos, value_1qb, value_2qb, scrape_date, fp_id`) — FTF reads only:

| Column | Used for |
|---|---|
| `player` | Name join key → `normalise_name()` → `DP_TO_SLEEPER_NAME` reference table → Sleeper player id |
| `pos` | Filtered to `{QB, RB, WR, TE}`; also carried as `pos_map` so joins stay position-strict (#127 — two NFL players can share a normalised name, e.g. "Kenneth Walker" WR vs "Kenneth Walker III" RB) |
| `value_1qb` / `value_2qb` | The dynasty trade value (0–10000), selected by scoring format; mapped to seed Elo via the affine `seed_elo_for_value()` curve (see the module docstring in `data_loader.py` for the calibration) |

`team`, `age`, `draft_year`, `ecr_*`, `scrape_date`, `fp_id` are present in the file but **not read**.

From `values.csv`, only rows with `pos == "PICK"`: the `player` column doubles as the pick label (`"2026 Pick 1.01"`, `"2027 Early 1st"`) and `value_1qb`/`value_2qb` map through the same `seed_elo_for_value()` curve.

## Error modes

| Failure | Behavior |
|---|---|
| Fetch failure (network, timeout, non-2xx) — `values-players.csv` | Caught, logged (`⚠️ DynastyProcess fetch failed (...) — using flat Elo baseline`), returns `({}, {}, {})`. Callers treat an empty values map as fetch failure — nothing is cached, so the affected scoring format's pool build is skipped and retried after `_DP_FETCH_RETRY_SECONDS` rather than freezing an empty pool until process restart. |
| Fetch failure — `values.csv` (pick prices) | Caught, logged (`⚠️ DynastyProcess pick values unavailable (...) — draft board renders without slot values`), returns `{}`, cached for the 24h TTL. Draft Room omits the `slot_value` key entirely (never a null/zero placeholder). |
| Schema drift (column renamed/removed, `pos` values changed) | No explicit schema validation. A missing `value_1qb`/`value_2qb` column reads as `"0"` → `value = 0.0` → the player gets the value-0 floor Elo (1200) rather than an error. A renamed `player`/`pos` column would silently empty the pool for players under that column — no drift alarm exists beyond `backend/tests/test_dp_format_mapping.py` pinning the column mapping and a top-20 QB-share fingerprint against a checked-in snapshot. |
| Stale data (upstream stops updating, but keeps serving 200s) | Not detected. There is no explicit "data age" signal captured today — cache freshness is governed purely by FTF's own TTL/generation logic, not by any `scrape_date` check against the fetched CSV (see Instrumentation guidance below for a proposed fix). |
| Live `values-players.csv` (2026-08-09, for reference) | 200 OK, ~53 KB, 676 data rows, header `player,pos,team,age,draft_year,ecr_1qb,ecr_2qb,ecr_pos,value_1qb,value_2qb,scrape_date,fp_id` |
| Fetch failure — `db_playerids.csv` (crosswalk) | Caught, logged (`⚠️  DP crosswalk fetch failed (...) — keeping previous copy` / `... — using bundled snapshot`), never raises. Degrades id-based matching (ESPN/MFL/KTC joins fall back to name+position matching, which is already the fallback path for unmatched ids) rather than breaking any import or ranking flow. |
| Live `values.csv` (2026-08-09, for reference) | 200 OK, ~58 KB, 761 data rows, 85 of them `pos == "PICK"` |

## Related: KeepTradeCut blend

`data_loader.py` also blends a second, unauthenticated consensus source — KeepTradeCut's dynasty-rankings page HTML (`keeptradecut.com`, scraped once per 24h TTL, `_fetch_ktc_html` / `_ktc_consensus`) — into the DynastyProcess baseline before Elo seeding (`_apply_consensus_blend`, feedback #145/#148). DP remains the pool's spine (universe, crosswalk, value scale); KTC only contributes an ordering opinion (`ktc_blend_weight`) and a TE-premium multiplier for `sf_tep` (`tep_te_uplift`). It is fail-soft everywhere — any KTC problem leaves the maps DP-only. KTC is a **separate external call surface** from DynastyProcess (different host, different fetch/parse path, unsanctioned HTML scrape vs. a published CSV) and is out of scope for this document; see `docs/runbook.md` § "consensus seed blend" and `data_loader.py`'s module comments for the full design. It does not yet have its own `docs/integrations/` page.

## Instrumentation guidance

All data here is public (community consensus values, no PII, no secrets) — **log freely**, nothing to redact. Suggested fields for any structured logging added around this pipeline:

- **Status:** success / failure / empty-result, per file (`values-players.csv` vs `values.csv`) and per scoring format.
- **Latency:** wall-clock time of the `urllib.request.urlopen` call.
- **Row count:** parsed data rows (post-`VALID_POSITIONS` filter for player rows; `pos == "PICK"` count for pick rows) — a sudden drop is the cheapest schema-drift/stale-file signal available and isn't currently captured anywhere.
- **File age:** the `scrape_date` column (present on every row, currently unread) — comparing it against "now" would give a genuine staleness signal that the current TTL-only caching cannot detect (a dead upstream that still serves a stale-but-valid-shaped CSV would otherwise go unnoticed). Worth wiring into `_fetch_dynasty_process` if staleness monitoring becomes a priority.
- **Cache state:** hit vs. miss vs. retry-backoff-skipped, and (for `values.csv`) TTL age at read time.

Existing log lines already emitted (informal, not structured) follow the `print()` pattern seen throughout `data_loader.py`, e.g.:
```
✅ Loaded 676 player values from DynastyProcess (612 with value > 0)
⚠️  DynastyProcess fetch failed (<reason>) — using flat Elo baseline
✅ Loaded 85 DynastyProcess pick prices (display-only)
⚠️  DynastyProcess pick values unavailable (<reason>) — draft board renders without slot values
```
These already carry row counts; latency and file-age are the gaps.

## Test seams

| Env var | Effect |
|---|---|
| `FTF_DP_VALUES_FILE` | Serves `values-players.csv` from a local path instead of the live GitHub egress, through the identical parse path. **Mandatory** under `FTF_TEST_MODE=1` — the silent flat-Elo fallback would otherwise reshape the universal pool mid-test undetected. Missing file at the given path is a loud failure by design. |
| `FTF_DP_PICK_VALUES_FILE` | Same, for `values.csv`. A second, independent seam since it's a second live egress. **Mandatory** under `FTF_TEST_MODE=1`; `backend/server.py` startup-aborts without it (T-M6-01). |

See `docs/config-reference.md` for the full env var table.

## Source

- `backend/data_loader.py` — fetch, parse, Elo-seed mapping, KTC blend
- `backend/espn_service.py` — `db_playerids.csv` crosswalk fetch/cache/fallback (`get_crosswalk`, `fetch_crosswalk`, `PLAYERIDS_URL`)
- `backend/server.py` — `_load_dp_maps`, `_ensure_universal_pools`, `_build_universal_pools_locked`, `_DP_FETCH_RETRY_SECONDS`
- `docs/architecture.md` — data-flow diagram (External → `DP[DynastyProcess CSV]`)
- `docs/runbook.md` — "Consensus QB values" and "consensus seed blend" troubleshooting entries
- `docs/plans/rookie-draft/plan.md` §0.5 — the `values.csv` display-only bound (KD-9) and its reversal (O2)
