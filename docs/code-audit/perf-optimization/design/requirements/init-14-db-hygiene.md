# REQ — INIT-14: DB Hygiene

- **Initiative / Wave / Scope:** INIT-14 · Wave 1 (index) / Wave 2 (check_for_match, community-ELO cache, bulk upsert) · [B]
- **Source observations:** OBS-DB-01 (position index), OBS-DB-05 (check_for_match), OBS-DB-06 (community-ELO), OBS-DB-07 (upsert_league_members)
- **Peak RICE-P:** 3.2 (OBS-DB-01)

## Problem statement

Four related data-layer gaps collectively add unnecessary latency and write
amplification to the backend's hot paths: the `players.position` column is
unindexed, forcing full table scans on every positional board request;
`check_for_match` fetches and re-parses every like-row in Python on each trade
swipe; the community-ELO mean is recomputed in Python on every Trends request
with no server-side caching; and `upsert_league_members` performs N
select-then-write round-trips per session_init instead of a single bulk upsert.

## User stories

- As a **dynasty manager**, I want positional ranking boards and trio requests to
  be served quickly, so that navigating between positions does not stall on a
  full table scan.
- As a **dynasty manager**, I want trade match-checking to stay fast even after
  swiping on many trades in a deep league, so that liking a trade card does not
  add noticeable latency as my like history grows.
- As a **dynasty manager**, I want Trends (contrarian/consensus) scores to load
  quickly, so that I do not wait for redundant aggregation work on each visit.
- As an **operator**, I want league-member upserts to use a single bulk
  statement, so that session_init write load on Postgres is reduced and the DB
  round-trip count scales independently of league size.

---

## Wave 1 — Position index (target: quick win, ≤1 hour)

### Functional requirements (Wave 1)

- **FR-1** — Add `CREATE INDEX IF NOT EXISTS ix_players_position ON
  players(position)` to the `_hot_path_indexes` list in `_migrate_db()`
  (`database.py:714–723`), matching the existing idempotent `CREATE INDEX IF NOT
  EXISTS` pattern used for all other hot-path indexes in that block.
- **FR-2** — The new index must be created for both SQLite and Postgres dialects
  without branching (the `CREATE INDEX IF NOT EXISTS` syntax is valid on both).
- **FR-3** — `_migrate_db()` must remain idempotent: running it on a database
  where the index already exists must not raise an error.

### Acceptance criteria (Wave 1)

- [ ] **AC-1** — After `_migrate_db()` runs on a fresh SQLite database, an
  `EXPLAIN QUERY PLAN SELECT … FROM players WHERE position = 'QB'` shows a SEARCH
  using `ix_players_position` (not a full SCAN).
- [ ] **AC-2** — Running `_migrate_db()` twice on the same database does not
  raise an exception and leaves exactly one `ix_players_position` index.
- [ ] **AC-3** — The index is present on both SQLite (local dev) and Postgres
  (production) after a deploy that runs `_migrate_db()`.

---

## Wave 2 — check_for_match, community-ELO, bulk upsert (target: Wave 2, multi-day)

### Functional requirements (Wave 2)

**check_for_match (FR-4 – FR-6)**

- **FR-4** — Narrow the `SELECT` in `check_for_match` (`database.py:2720–2729`)
  to project only `give_player_ids, receive_player_ids` — dropping all other
  columns (`trade_id`, timestamps, etc.) — to reduce row width on the fetch.
- **FR-5** — Add a recency bound to the `check_for_match` query: restrict rows to
  those created within the last N days, using the same `since_days` parameter
  pattern already in `load_trade_decisions` (`database.py:1946,1960–1962`). The
  default value of N must be large enough (e.g., ≥90 days) to ensure a genuine
  mutual like is never silently missed for an active league season.
- **FR-6** — The Python set-comparison loop (`database.py:2731–2739`) may remain
  unchanged; FR-4/FR-5 reduce the input size, not the comparison logic.

**Community-ELO server cache (FR-7 – FR-9)**

- **FR-7** — Add a server-side in-process cache keyed by `(league_id,
  scoring_format)` for the assembled community-ELO map returned by
  `load_community_elo_for_league` (`database.py:4200–4216`). The cache TTL must
  be short (≤5 min), mirroring the existing 5-min leaderboard cache pattern at
  `database.py:1126–1127`.
- **FR-8** — The community-ELO cache must be **invalidated** whenever
  `upsert_member_rankings` (`database.py:2528`) is called for the same
  `(league_id, scoring_format)` key, so that a leaguemate's new ranking is
  reflected within the next cache cycle.
- **FR-9** — Both Trends endpoints that independently call
  `load_community_elo_for_league` (`trends_service.py:99–113` and `:224–238`)
  must benefit from the same cache without code duplication; the cache must live
  in the data layer (inside or adjacent to `load_community_elo_for_league`), not
  in each Trends endpoint.

**upsert_league_members bulk write (FR-10 – FR-12)**

- **FR-10** — Replace the per-member select-then-insert/update loop in
  `upsert_league_members` (`database.py:1990–2025`) with a single dialect-aware
  bulk upsert keyed on the `uq_league_member` unique constraint
  (`database.py:138` — `(league_id, user_id)`).
- **FR-11** — The bulk upsert must use the same dialect-branch pattern already
  established at `database.py:749–759`: `INSERT … ON CONFLICT (league_id,
  user_id) DO UPDATE` for Postgres; `INSERT OR REPLACE` (or `INSERT … ON
  CONFLICT DO UPDATE`) for SQLite.
- **FR-12** — The bulk upsert must preserve "newest snapshot wins" semantics:
  the `ON CONFLICT DO UPDATE` clause must update **all** mutable columns
  (including `updated_at`) so a re-insert of the same `(league_id, user_id)`
  with new data always overwrites the old record.

### Acceptance criteria (Wave 2)

- [ ] **AC-4** — Given a user with 200 liked trades in a league, when a trade
  swipe like is submitted, then `check_for_match` issues a single SQL SELECT that
  projects only `give_player_ids, receive_player_ids` and is bounded to N days
  (verifiable via SQL query log or a test with a mocked DB).
- [ ] **AC-5** — Given a user with likes older than N days that do not have a
  recent mirror, when `check_for_match` runs, then those old rows are excluded
  from the Python comparison loop without changing the match result for rows
  within the recency window.
- [ ] **AC-6** — Given a match that exists and was created within N days, when
  `check_for_match` runs, then the match is still detected correctly (no false
  negative from the recency bound).
- [ ] **AC-7** — Given two consecutive calls to the same Trends endpoint for the
  same `(league_id, scoring_format)` within the 5-min TTL, when inspecting DB
  query logs, then `load_member_rankings` is called at most once (the second
  call is served from the in-process cache).
- [ ] **AC-8** — Given a leaguemate submits a new ranking (triggering
  `upsert_member_rankings`), when the next Trends call is made after the
  invalidation, then the community-ELO map is reloaded from DB (cache miss), not
  served stale.
- [ ] **AC-9** — Given a 12-member league on Postgres, when `upsert_league_members`
  is called, then exactly **1 SQL statement** (the bulk upsert) is executed, not
  24 (12 selects + 12 writes), verifiable via DB query count in a test.
- [ ] **AC-10** — Given `upsert_league_members` is called twice in succession for
  the same league with updated member data, when the second call completes, then
  the `updated_at` field reflects the second call's timestamp (newest-wins
  semantics preserved).
- [ ] **AC-11** — Given a Postgres deployment, when `upsert_league_members` runs,
  then no `UniqueViolation` exception is raised when a member already exists in
  the table.

---

## Related components

- `backend/database.py:714–723` — `_hot_path_indexes` block (Wave 1 touch point)
- `backend/database.py:202–223` — `players` table schema (confirms no existing
  position index)
- `backend/database.py:3504–3512` — `load_players(position=...)` hot reader
- `backend/database.py:3556–3570` — `load_rookies` positional filter
- `backend/database.py:2700–2739` — `check_for_match` (Wave 2 narrow)
- `backend/database.py:1946,1960–1962` — `since_days` pattern reference
- `backend/database.py:4200–4216` — `load_community_elo_for_league`
- `backend/database.py:2528` — `upsert_member_rankings` (cache invalidation hook)
- `backend/database.py:1126–1127` — existing 5-min leaderboard cache (reference
  pattern for community-ELO cache)
- `backend/trends_service.py:99–113` — first Trends mean-computation block
- `backend/trends_service.py:224–238` — second (duplicate) Trends mean-computation
  block
- `backend/database.py:1990–2025` — `upsert_league_members` N+1 loop (Wave 2)
- `backend/database.py:138` — `uq_league_member` unique constraint
- `backend/database.py:749–759` — existing dialect-branch upsert pattern
  (reference for FR-11)

## Prerequisite components / dependencies

- **Wave 1** (position index): none. Additive, idempotent, both dialects.
- **Wave 2** (check_for_match recency bound): none, but the recency window N
  must be reviewed against the longest realistic time between two users mutually
  liking the same trade (suggest ≥90 days as default).
- **Wave 2** (community-ELO cache): none beyond confirming the invalidation hook
  in `upsert_member_rankings` (`database.py:2528`) is the sole write path for
  member rankings.
- **Wave 2** (bulk upsert): none. The `uq_league_member` unique constraint
  (`database.py:138`) is already present on both dialects.

## Non-functional requirements & invariants

- **No ELO math invariant:** the position index is additive; it changes query
  plan, not data. The check_for_match narrowing changes which rows are compared
  but not the comparison logic. Neither touches ELO computation, K-factors, or
  tier bands.
- **Community-ELO score parity:** the SQL `AVG(elo) GROUP BY player_id` approach
  (OBS-DB-06 Option A, deferred in favor of Option B server-cache) is **not**
  implemented here; the Python mean computation is preserved. The server cache
  only reduces how often it runs. Verify that the cached mean matches the live
  mean (no NULL/zero handling divergence). Trends contrarian/consensus scores
  must not shift between a cached and a non-cached Trends request for the same
  data.
- **Bulk upsert "newest snapshot wins":** the `ON CONFLICT DO UPDATE` clause in
  FR-11 must include all mutable columns. An incomplete SET clause (updating only
  some columns) would be a regression.
- **Both dialects:** all Wave 1 and Wave 2 changes must work on SQLite (local
  dev / `data/trade_finder.db`) and Postgres (`DATABASE_URL` production). No
  dialect-specific SQL may be introduced without a corresponding branch or a
  syntax verified as supported on both.
- **Idempotent migrations:** all schema changes (index creation) must use `IF NOT
  EXISTS` or equivalent guards in `_migrate_db()`, consistent with the existing
  pattern.
- **Rollback (Wave 1):** dropping `ix_players_position` fully restores the prior
  query plan with no data loss.
- **Rollback (Wave 2):** reverting check_for_match restores the unbounded scan;
  reverting the cache removes the TTL layer; reverting the bulk upsert restores
  the N+1 loop. Each is independently revertible.

## Out of scope

- The composite `players(position, search_rank)` index (OBS-DB-01 Option B).
  Deferred; only warranted if an `EXPLAIN` shows a filesort on the positional
  sort.
- Introducing a normalized match-key column on `trade_decisions` (OBS-DB-05
  Option B). Schema change + backfill required; higher effort and higher risk of
  match-semantics divergence. Deferred.
- Pushing community-ELO aggregation into SQL `AVG(…) GROUP BY player_id`
  (OBS-DB-06 Option A). Higher effort than the TTL cache; deferred unless the
  cache alone proves insufficient.
- Indexing `league_members.league_id` as a standalone column (noted in OBS-DB-01
  as the weaker gap; the composite unique index already covers the prefix lookup
  on SQLite).
- Compacting `swipe_decisions` / `elo_history` history (mentioned in OBS-DB-03
  context; a separate maintenance concern outside this initiative).
