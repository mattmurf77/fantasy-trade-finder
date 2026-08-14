# Dynasty Year in Review — data-architect review (R1)

> **Role:** an-data-architect. **Date:** 2026-08-13.
> **Reviewing:** `docs/business/product/2026-08-13-dynasty-year-in-review-plan.md`
> **Verified against:** `origin/main` @ `60fccc7` (the plan cites `4a4b671`; nothing I
> cite changed between them — every line number below re-verified via
> `git show origin/main:<path>`).
> **Operator rulings YR-1…YR-7 are taken as binding.** Nothing here reopens them; §A4
> and §B2 exist specifically to make YR-1 and YR-6 *achievable*, because as sketched
> they are not.
> **Design only. No source file touched.**

## Contents

- [A. Specs](#a-specs)
  - [A1. `league_roster_history` — DDL](#a1-league_roster_history--ddl)
  - [A2. Pick-ownership history (C3)](#a2-pick-ownership-history-c3)
  - [A3. Board history (C5 + C6)](#a3-board-history-c5--c6)
  - [A4. Write path and idempotency](#a4-write-path-and-idempotency)
  - [A5. Volume and growth](#a5-volume-and-growth)
  - [A6. Query shape](#a6-query-shape)
  - [A7. Backfill](#a7-backfill)
  - [A8. Event taxonomy](#a8-event-taxonomy)
  - [A9. Doc updates required](#a9-doc-updates-required)
- [B. Disagreements and corrections](#b-disagreements-and-corrections)
- [C. Open questions for eng-architect](#c-open-questions-for-eng-architect)

---

## A. Specs

### A0. The one-paragraph version

The plan's capture half is right in principle and wrong in three mechanics that decide
whether it works: the weekly job **cannot** read rosters from memory or from
`league_members` (that data is client-supplied and only refreshed when a human opens the
app), it **cannot** be provisioned as a new Render cron (blueprint sync breaks), and its
proposed unique key **enforces nothing**. All three have exact precedents already in this
tree — `_fetch_league_rosters`, the `daily-tick` weekday-gated weekly pass, and
`uq_value_snapshot` — so the fix is smaller than the problem. The recap's read path is
cheap because YR-2 stores `team_value`; the join to `player_value_history` is only needed
for attribution, and it needs one index that does not exist yet.

---

### A1. `league_roster_history` — DDL

Follows `player_value_history_table` (`backend/database.py:995-1006`) as the direct
precedent: append-only, a **period key that is a bucket label rather than an instant**,
denormalised computed value alongside the input, one uniqueness constraint that the
writer upserts against.

```python
# ---------------------------------------------------------------------------
# league_roster_history — weekly roster snapshots (backlog #46 Wrapped, YR-1/2/6)
# ---------------------------------------------------------------------------
# player_value_history logs the MARKET side daily; this logs the OWNERSHIP side
# weekly. A team's value is roster x values — this is the half that was being
# overwritten (league_members.roster_data, :327, replaced on every sync).
#
# team_value is stored denormalised alongside the roster for the same reason
# player_value_history denormalises consensus_value (:1001): a later model change
# must not silently rewrite the shape of a season chart already shown to a user.
# The roster ids remain the input of record for attribution and recomputation.
# ---------------------------------------------------------------------------

league_roster_history_table = Table("league_roster_history", metadata,
    Column("id",                 Integer, primary_key=True, autoincrement=True),
    Column("league_id",          String,  nullable=False),
    # STABLE team identity, not owner identity: 'r:<roster_id>' when the platform
    # exposes one, else 'u:<owner_user_id>'. Keyed on the TEAM so a mid-season
    # ownership change does not split one team's season into two series, and so
    # orphan rosters (no owner_id at all) are representable — YR-6 requires both.
    Column("team_key",           String,  nullable=False),
    Column("roster_id",          Integer),           # platform roster/franchise id
    Column("owner_user_id",      String),            # NULL for orphan teams
    Column("scoring_format",     String,  nullable=False),   # '1qb_ppr' | 'sf_tep'
    # Bucket label, NOT an instant. '2026-W33' via now.isocalendar() —
    # same shape and derivation as deck_replenish_log.iso_week (:586, server.py:16244).
    # ISO week-numbering YEAR (isocalendar()[0]), never .year: 2026-12-31 is
    # 2027-W01 and a %Y-formatted key would sort and dedupe wrong at the boundary.
    Column("period_key",         String,  nullable=False),
    # 'week' today. Present from day one so a later daily / on-sync grain is a
    # write-path change, not a schema migration on a populated table.
    Column("period_kind",        String,  nullable=False),   # 'week' | 'day'
    # 'YYYY-MM-DD' UTC — the player_value_history JOIN KEY (see A6). Distinct from
    # snapshot_at so the join is a plain equality, never date arithmetic.
    Column("snapshot_date",      String,  nullable=False),
    Column("snapshot_at",        String,  nullable=False),   # ISO UTC instant of write
    Column("player_ids",         Text,    nullable=False),   # JSON array, SORTED
    Column("starter_ids",        Text),                      # JSON array | NULL
    Column("pick_ids",           Text),                      # JSON array of draft_picks.pick_id
    Column("pick_source",        String),   # 'platform'|'user'|'mixed'|NULL (ADR-010)
    # sha256(",".join(sorted(str(p) for p in player_ids))).hexdigest()[:16].
    # SORTED = set semantics, so a platform reordering the array is not a change.
    Column("roster_hash",        String,  nullable=False),
    Column("changed_from_prev",  Integer),   # 0|1|NULL(first row) — see note below
    Column("player_count",       Integer, nullable=False),
    # How many of player_count actually had a player_value_history row. The
    # universal pool is DP-seeded skill positions only (server.py:16810-16828), so
    # K/DEF and deep bench never price. Without this the chart cannot be honest.
    Column("valued_player_count",Integer, nullable=False),
    Column("team_value",         Float),    # sum of consensus_value over valued players
    Column("team_value_picks",   Float),    # pick portion, SEPARATE (different pipeline)
    Column("value_basis_date",   String),   # the pvh snapshot_date actually used
    Column("platform",           String),   # 'sleeper'|'espn'|'mfl'|NULL
    Column("source",             String,  nullable=False),  # 'weekly'|'sync'|'backfill'
    UniqueConstraint("league_id", "team_key", "scoring_format", "period_key",
                     name="uq_roster_snapshot"),
)

Index("ix_lrh_team_period",  league_roster_history_table.c.league_id,
                             league_roster_history_table.c.team_key,
                             league_roster_history_table.c.period_key)
Index("ix_lrh_league_period",league_roster_history_table.c.league_id,
                             league_roster_history_table.c.period_key)
Index("ix_lrh_owner_period", league_roster_history_table.c.owner_user_id,
                             league_roster_history_table.c.period_key)
```

**Why `scoring_format` is in the key rather than a stamp.** Exactly one format is written
today (`leagues.default_scoring`, `:253`), so this costs nothing now. It mirrors
`uq_value_snapshot` and it means a later "recompute this season under SF" backfill is an
insert, not a migration. The cost — a duplicated roster payload if both formats are ever
written — is bounded and its escape hatch (splitting roster and value into two tables) is
available at any time.

**Change detection, stated precisely — this is where the plan's sketch would break YR-2.**
`roster_hash` must **not** suppress the weekly write. The grid has to stay *dense*:
`team_value` moves every week even when the roster doesn't (consensus values move daily),
and YR-2's whole purpose is a stable season chart. A hash-suppressed series produces a
chart with holes in exactly the weeks nothing was traded. The hash's two real jobs are
(a) computing `changed_from_prev` at write time so "which weeks did this roster change" is
an index scan rather than a self-join, and (b) suppressing *extra* on-sync writes between
weekly rows if the YR-1 "free addition" is ever taken.

**JSON array vs a row-per-player child table.** Keep JSON. 240 rows/league-season vs
~6,100 normalized (25.6 players x 12 teams x 20 weeks — mean roster size measured at 25.6,
max 44, from the dev DB's `league_members`). The recap is a batch precompute, not a hot
path, so the set operations fold in Python at trivial cost; a child table buys a 25x row
multiplier and dialect-divergent `json_each`/`jsonb_array_elements` SQL in a codebase that
goes to real pains to keep the two dialects aligned. Precedent is unanimous:
`sleeper_trades.adds/drops` (`:368-369`), `trade_impressions.give_player_ids` (`:449`),
`league_members.roster_data` (`:327`) are all JSON-in-a-column read in Python. Using the
identical representation to `roster_data` also makes the on-sync writer a pure copy.
**Falsifiable trigger to revisit:** if the recap ever needs "who owned player X on date D"
as a *live* query rather than a precompute, normalize.

---

### A2. Pick-ownership history (C3)

**Do not build a second table.** Fold pick ownership into `league_roster_history` as
`pick_ids` (above). The plan offers "a thinner table or a periodic serialisation" and the
second option is right, but it should live on the row that already has the identical grain.

- Grain is identical: (league, team, period). A separate table with the same key is a join
  for nothing.
- `pick_id` is already a stable, self-describing string —
  `"{league_id}_{season}_{round}_{original_roster_id}"` (`database.py:731-733`). Season,
  round and original team are all recoverable from the id, so "pick flow / what your first
  became" is a set-difference across weeks, the same operation as the roster.
- Marginal row cost: zero.
- `team_value_picks` carries the value half, deliberately separate from `team_value`:
  `draft_picks.pool_value` (`:757`) is computed on a different pipeline than player
  consensus, and merging them makes "we changed pick valuation" indistinguishable from
  "the roster changed" on the chart.

**`pick_source` is load-bearing.** Since draft-extensions W3 / ADR-010, `draft_picks.source`
distinguishes platform-written rows (NULL or `'platform'`) from user-asserted ones
(`:766-770`). A recap must be able to decline to make pick-flow claims on a grid a
leaguemate typed in. Stamp `'platform'|'user'|'mixed'` per snapshot.

If per-pick value at snapshot time is ever needed, add a parallel `pick_values` JSON object
column — not a table.

---

### A3. Board history (C5 + C6)

**C5 and C6 are one build item, not two.** The plan treats C6 (leaguemates' valuations over
time) as a new capture problem created by YR-3 and C5 (personal Elo cadence) as a separate
P1 fix. They are the same table read from two angles: C5 is the FTF user's own series, C6 is
the other members' series. One table, one job, one write.

**But it is not `elo_history`, and it is not `member_rankings`.** Three facts:

1. `elo_history` (`:971-979`) already logs per-user valuations over time. The gap is
   **cadence**, not storage — exactly as the plan says for C5, and therefore also for C6.
2. `elo_history` writes **only players whose Elo changed** in a submission (`:965-966`;
   `server.py:6001-6010` builds `changed` before calling `record_elo_snapshot`). So it can
   never reconstruct a *complete* board at date D without folding forward from the first
   row ever written — and if that fold's start point is missing, every later date is wrong.
3. `elo_history` has **no uniqueness constraint of any kind**. A weekly append to it is not
   idempotent; a double run silently doubles every board and "value at week W" gets two
   answers. The plan's §5.4 "cheap fix: append a personal-Elo snapshot on the same trigger"
   is not safe as written.

Retrofitting a partial unique index onto `elo_history` would fix (3) but not (2), and it
adds a conflict path to the ranking-submit hot path. The volume math settles it: a complete
board is ~270 (player, elo) pairs (dev DB: 2,441 `member_rankings` rows across ~9 boards).
Row-per-player weekly at 100 leagues x 3 FTF users = **1.6M rows**; at 1,000 leagues, 16M.
That is 6,750x the roster table and it is a real constraint, not a rounding error.

**Spec: one JSON row per board per period.**

```python
# ---------------------------------------------------------------------------
# league_board_history — weekly COMPLETE board snapshots (C5 + C6, YR-3)
# ---------------------------------------------------------------------------
# elo_history (:971) stays as-is: the event-driven, per-player, CHANGED-ONLY log
# of "what moved when". This table answers the different question the recap asks —
# "what was this manager's whole board on date D" — which elo_history structurally
# cannot answer (it only ever wrote the deltas) and member_rankings (:379) cannot
# answer either (delete+insert on every submit, one point in time).
# NOT a fork of elo_history: different grain, different question, and the
# row-per-player alternative is 1.6M rows at 100 leagues.
# ---------------------------------------------------------------------------

league_board_history_table = Table("league_board_history", metadata,
    Column("id",             Integer, primary_key=True, autoincrement=True),
    Column("user_id",        String,  nullable=False),
    Column("league_id",      String,  nullable=False),
    Column("scoring_format", String,  nullable=False),
    Column("period_key",     String,  nullable=False),   # '2026-W33'
    Column("snapshot_date",  String,  nullable=False),   # 'YYYY-MM-DD' UTC
    Column("snapshot_at",    String,  nullable=False),   # ISO UTC
    Column("elos",           Text,    nullable=False),   # JSON {player_id: round(elo,1)}
    Column("player_count",   Integer, nullable=False),
    Column("board_updated_at", String),  # member_rankings.updated_at at capture —
                                         # distinguishes "re-ranked this week" from
                                         # "we re-snapshotted an unchanged board"
    Column("source",         String,  nullable=False),   # 'weekly' | 'backfill'
    UniqueConstraint("user_id", "league_id", "scoring_format", "period_key",
                     name="uq_board_snapshot"),
)
Index("ix_lbh_league_period", league_board_history_table.c.league_id,
                              league_board_history_table.c.period_key)
Index("ix_lbh_user_period",   league_board_history_table.c.user_id,
                              league_board_history_table.c.period_key)
```

The write reads `member_rankings` (`:379-387`) directly — no platform call, no
recomputation, and `load_member_rankings` already has the right index
(`ix_member_rankings_league_fmt_user`, `:2175-2176`). `board_updated_at` is what makes
"Your calls" honest: a board snapshotted five weeks running with the same
`board_updated_at` is one observation repeated, not five observations.

**Privacy note under YR-3.** This table stores one manager's valuations in a form another
manager's recap will read. YR-3 permits that *inside an authenticated league context*. The
storage design must not make the wider exposure easy by accident: any read accessor
(`load_board_history`) takes `league_id` **and** a caller identity, and asserts the caller
is a member of that league, exactly as `load_member_rankings` is scoped today. There is no
public-URL read path for this table — that is the half of D-P1-12 the YR-3 clarification
explicitly left standing.

---

### A4. Write path and idempotency

#### A4.1 The trigger: `daily-tick` with a weekday gate — not a new cron

**A new Render cron cannot be provisioned via `render.yaml`.** `docs/runbook.md:295` records
that a `value-snapshot-daily` blueprint cron was added and removed the same day because
"new blueprint cron = new billable resource needing approval" broke blueprint sync;
`runbook.md:586` restates it as a standing rule ("provision the dedicated cron by hand in
the Render dashboard, never via `render.yaml`"). `git show origin/main:render.yaml` has
exactly three cron services — realtime (`*/15`), hourly (`0 *`), daily (`30 13 * * *`) — and
no value-snapshot. See correction **B1**.

**The repo already has the exact weekly-job pattern, and it is better than a weekly cron.**
`_run_weekly_replenishment` (`server.py:16231-16245`) runs inside **`daily-tick`**
(`server.py:16676`), gated on `now.weekday() >= weekday_gate`, with the comment that says
precisely why: *">= (not ==) keeps the rest of the week eligible so one missed cron run
doesn't skip the week — the per-week marker still caps everything at once."* Idempotency
comes from `deck_replenish_log`'s `UniqueConstraint(user_id, league_id, iso_week)`
(`database.py:586-591`).

Adopt it verbatim:

```
POST /api/cron/roster-snapshot        # dedicated route, X-Cron-Secret
  -> _write_weekly_roster_snapshots(now)   # shared writer

daily-tick  (already provisioned, 13:30 UTC)
  -> if now.weekday() >= FTF_ROSTER_SNAPSHOT_WEEKDAY:   # default 1 = Tuesday
         _write_weekly_roster_snapshots(now)            # failure-isolated try/except
```

Properties this buys, mapped to the task's questions:

| Question | Answer |
|---|---|
| **Exactly one row per period?** | `uq_roster_snapshot (league_id, team_key, scoring_format, period_key)` + upsert. `period_key` is a *bucket label*, so a second run in the same ISO week overwrites rather than appends. |
| **Missed run?** | The `>=` gate re-attempts every subsequent day of the same ISO week. Losing a week requires `daily-tick` down for 6+ consecutive days. This is *stronger* than a true weekly cron, where one missed firing is a permanent hole — which is what YR-1 says must not happen. |
| **Double run?** | Free. Dialect-branched upsert, copied from `record_value_snapshots` (`:9376-9398`): `INSERT OR REPLACE` on SQLite, `pg_insert(...).on_conflict_do_update(constraint="uq_roster_snapshot", ...)` on Postgres. **The Postgres SET list must include `snapshot_at`, `snapshot_date`, `team_value`, `roster_hash`, `player_ids`** — otherwise a Thursday re-run leaves Tuesday's timestamp on Thursday's roster. |
| **Partial failure mid-league?** | One `engine.begin()` **per league**, never one transaction for the sweep. League 47 of 300 failing leaves 1–46 committed; 47's `period_key` is still absent so the next daily pass retries it inside the same week. Per-league counters logged in the shape of `log.info("value-snapshot: %s (%s)", counters, today)` (`server.py:16830`). |

The dedicated `POST /api/cron/roster-snapshot` route still earns its place for the reason
stated verbatim at `server.py:16761-16768` — a bug in daily-tick's push scan must not be
able to silently stop history collection — but it is **optional**, hand-provisioned in the
Render dashboard if wanted. **The daily-tick gate is the contract.** This directly satisfies
YR-1's "the weekly job is the contract and the thing that must not be allowed to miss."

#### A4.2 Where the roster data comes from — a server-side fetch, not memory

This is the correction that most changes the P0 estimate. See **B2**.

`upsert_league_members` (`database.py:5526`) has **exactly one production caller**:
`server.py:15276`, inside `session_init`. The rosters it writes are **client-supplied** —
`body["user_player_ids"]` and `body["opponent_rosters"]` (`server.py:14664-14670`,
`14686-14690`). The server never fetches them on that path. Therefore:

- A weekly job has no session and no client. Reading `league_members.roster_data` returns
  whatever the last human to open that league posted, which for a dormant league can be
  months stale — and stamping it with this week's `period_key` **fabricates a data point**.
  That is precisely what the runbook forbids for value-snapshot: *"If the job misses a day,
  that gap stays a gap — accept it; do not fabricate history"* (`runbook.md:295`).
- The weekly job must call **`_fetch_league_rosters(league_id)`** (`server.py:10564`) — the
  public, unauthenticated `GET /v1/league/<id>/rosters`, documented at
  `docs/integrations/sleeper.md:41` and `:181`, returning `roster_id`, `owner_id`,
  `players`, `starters`. **One call per league per week.** Against the 18 calls/league/sync
  the trade-capture sweep already makes (`sleeper.md:276`), this is noise.

Two things the server fetch fixes for free:

1. **It is the only way to satisfy YR-6.** `server.py:15229-15231` states outright that
   clients *"drop ownerless rosters from `opponent_rosters`"* — which is why
   `leagues.total_rosters` had to be added. `league_members` structurally cannot represent
   every team. `/rosters` returns every roster, orphans included.
2. **It is authoritative on team count.** Same comment: *"stale rows linger after a manager
   leaves."* A grid built from `league_members` would keep emitting rows for teams that no
   longer exist.

**Non-Sleeper leagues.** `_fetch_league_rosters` is Sleeper-only. ESPN/MFL leagues
(`leagues.platform`, `:259`) get **no row** for that period — a legible hole, never a
copy-forward. See **B11**: this contradicts §7's platform-agnostic growth claim and must be
scoped or struck.

**Sweep bounding.** If the sweep grows past what fits in the 120 s gunicorn timeout
(`render.yaml:16`, free plan, `--workers 1`), bound it exactly as §0b of hourly-tick does:
`_DRAFT_STATUS_SWEEP_BUDGET = 50` per tick, stalest-first, so it rotates rather than starves
(`server.py:12285`, `16471-16479`). Combined with the `>=` weekday gate this still completes
every league within the week. Prefer this over the `players-refresh` daemon-thread-plus-202
pattern (`server.py:16775-16791`) — budget rotation self-heals and needs no thread.

#### A4.3 On-sync writes (the YR-1 "free addition")

An on-sync write into the same table with the same `period_key` simply upserts: the grid
stays dense and one-row-per-period, and the last write in the week wins. That is the only
shape I would ship in P0. It does **not** deliver mid-week resolution — and it doesn't need
to, because `sleeper_trades` already carries day-exact trade timestamps (see **B10**). If
finer grain is later wanted, it is `period_kind='day'` with `period_key` = the date, which
is why that column is in the DDL from day one.

---

### A5. Volume and growth

Measured inputs, not estimates: dev DB `league_members.roster_data` averages **219 bytes**
(max 684); mean roster **25.6 players** (max 44); real leagues in the dev DB carry 11–12
members. `player_value_history` writes ~1,369 rows/day (`runbook.md:295`: ≈684 `1qb_ppr` +
685 `sf_tep`).

**`league_roster_history`, per row:** `player_ids` ~220 B + `starter_ids` ~80 B + `pick_ids`
~290 B (pick_id ≈ 30 chars x ~9 picks) + ~18 scalar columns ~150 B + row/index overhead
~150 B ≈ **~900 B, call it 1 KB**.

**Rows:** 12 teams x 20 weeks = **240 rows/league-season** — the plan's number is correct.

| Scale | `league_roster_history` | `league_board_history` | Combined |
|---|---|---|---|
| 10 leagues | 2,400 rows / ~2.4 MB | 600 rows / ~2.3 MB | ~5 MB |
| 100 leagues | 24,000 rows / ~24 MB | 6,000 rows / ~23 MB | ~47 MB |
| 1,000 leagues | 240,000 rows / ~240 MB | 60,000 rows / ~230 MB | **~470 MB** |

(`league_board_history` assumes 3 FTF users/league and ~270 (player, elo) pairs ≈ 3.8 KB of
JSON per row.)

**Plain verdict:**

- **Rosters at 10 and 100 leagues: a non-issue.** The plan is right and right for the right
  reason. Storage must not influence the cadence decision.
- **At 1,000 leagues it stops being free.** ~470 MB combined would make these the two
  largest tables in the database, on a **Basic-256mb** Render Postgres (`render.yaml:5`).
  For scale, `player_value_history` is the current largest at ~0.5M rows/yr — and the data
  dictionary already flags *"revisit with a downsample-to-weekly policy after year one"*
  (`data-dictionary.md:659`). Decide the roster-history retention policy **before** 1,000
  leagues, not after. Natural policy: keep the current season at weekly, downsample closed
  seasons to monthly plus the final week (drops ~75%). That is an ADR-sized call, not a
  build detail.
- **§9's "Storage cost — None" was written before YR-3 expanded scope** and must not be
  inherited by the C6 build. Row-per-player boards are 1.6M rows at 100 leagues; the
  JSON-per-board shape in A3 is what keeps the "None" verdict true. See **B14**.

**Does Postgres migration change any of this?** Structurally, no. Every type used
(`Integer`/`String`/`Float`/`Text`) maps cleanly and the repo already dialect-branches its
upserts. Three specifics:

1. `INSERT OR REPLACE` has no Postgres equivalent — `on_conflict_do_update` with an explicit
   SET list, and the SET list must be complete (A4.1).
2. Keeping the JSON columns out of SQL keeps their type portable `Text`. The moment a query
   reaches inside them, Postgres wants `jsonb` and SQLite wants `json_each`, and the two
   diverge. This is a second reason the read path stays in Python.
3. Row overhead is higher on Postgres (~24 B/tuple header plus per-index entries), so treat
   the table above as a floor, not a ceiling — call it ~1.2 KB/row on Postgres.

---

### A6. Query shape

**The headline chart needs no join at all.** That is the payoff of YR-2 and it should be
stated in the plan, because it is the difference between a cheap read path and an expensive
one:

```sql
SELECT period_key, snapshot_date, team_value, team_value_picks, valued_player_count
FROM   league_roster_history
WHERE  league_id = ? AND team_key = ? AND scoring_format = ?
ORDER  BY period_key
```

`ix_lrh_team_period` makes this an index range scan of ~20 rows. The league-median overlay
is `WHERE league_id = ? AND scoring_format = ?` on `ix_lrh_league_period` → 240 rows,
grouped in Python. Both are microseconds. **`player_value_history` is only needed for
attribution stats, never for the chart.**

**The attribution join, done wrong:** 240 roster rows x 25.6 players = 6,144 (player, date)
point lookups. Each one *is* index-supported — `uq_value_snapshot` is
`(player_id, scoring_format, snapshot_date)` (`:1003-1005`) and leads with `player_id` — but
6,144 round-trips through SQLAlchemy is seconds, not milliseconds.

**Done right — one query per league-season:**

```sql
SELECT player_id, snapshot_date, consensus_value
FROM   player_value_history
WHERE  scoring_format = ?
  AND  player_id     IN (:union of all ids seen in the season, ~200-300)
  AND  snapshot_date IN (:the ~20 snapshot_dates)
```

Selective on `player_id` first → uses `uq_value_snapshot`. ~5,000 rows, one scan, folded in
Python.

**The missing index.** The *other* natural recap query — "every player's value on these 20
dates," for league-wide superlatives — is `WHERE scoring_format = ? AND snapshot_date IN
(...)`, which has **no leading-column match** and full-scans a table the data dictionary
already projects at ~0.5M rows/yr. `player_value_history` has exactly one index, the
constraint. Add:

```python
("ix_pvh_format_date", "player_value_history", "scoring_format, snapshot_date")
```

to the idempotent `CREATE INDEX IF NOT EXISTS` list in `_migrate_db`
(`database.py:2160-2185` is the established home). Costs nothing today. See **B12**.

**Total read cost for one full user recap:** ~20 roster rows + ~5,000 pvh rows + ~20 board
rows + the league's `sleeper_trades` rows (dozens) = **under 6,000 rows across 3–4 queries,
comfortably under 200 ms.** Precompute is not needed for correctness. It will be needed for
a December traffic spike on a free-plan single-worker web service — a P3 decision, and the
natural shape is a `wrapped_cache` table keyed `(user_id, league_id, season)` holding the
assembled JSON, invalidated never (a closed season does not change).

**The single most likely production bug in this design.** `snapshot_date` on the roster row
must match a `player_value_history.snapshot_date` **exactly**. If pvh missed that day, the
join returns nothing and `team_value` computes as 0 — which renders as a roster wipe on the
chart, indistinguishable from a real one. Three defenses, all cheap, none in the plan:

1. Pin the weekly job's UTC weekday so `snapshot_date` is deterministic per `period_key`.
2. Resolve to the **nearest pvh `snapshot_date` ≤ target**, and record which one was used in
   `value_basis_date`. `load_value_snapshot_baseline` (`database.py:9425`) already
   establishes this "oldest prior-day snapshot in a window" idiom in this codebase.
3. Never write `team_value = 0` when the value lookup finds nothing — write `NULL`, and let
   the chart render a gap. A gap is honest; a zero is a lie that looks like data.

---

### A7. Backfill

**Tested against what Sleeper actually exposes**, per `docs/integrations/sleeper.md` and
`backend/sleeper_trades_service.py`.

**What exists.** `GET /v1/league/<id>/transactions/<week>`, weeks 1–18
(`sleeper_trades_service.py:36-40`, `sleeper.md:48`) — returns *all* transaction types; FTF
filters to `type == "trade" and status == "complete"` (`sleeper_trades_service.py:93`), but
the endpoint itself carries free-agent, waiver and commissioner rows too. Each entry has
`adds`/`drops` as `{player_id: roster_id}`, `roster_ids`, `draft_picks`, `leg`, and
`status_updated` (epoch ms). Plus `GET /v1/league/<id>/rosters` for the F8 anchor
(`sleeper.md:41`) and `GET /v1/league/<id>/drafts` for the draft list (`sleeper.md:44`).

**So the replay is real:** final roster − (adds after D) + (drops after D), per `roster_id`,
walking backwards. §2.3 is right that this is a genuine technique. It is imprecise on four
things that decide whether it works:

1. **Draft selections are not transactions.** Rookie and startup draft picks never appear in
   `/transactions/<week>`; they come from `/v1/draft/<draft_id>/picks`, reached via
   `/league/<id>/drafts`. A replay that ignores drafts loses every player acquired at the
   draft — for a startup league, that is the entire opening roster. Recoverable, but it is a
   **second source**, not "the transaction log," and P2 must budget it.
2. **Order by `status_updated`, never by `leg`.** Offseason moves all land on leg 1
   (`sleeper_trades_service.py:36-38`) with real millisecond timestamps. A leg-ordered
   replay scrambles the entire offseason into one bucket.
3. **A Sleeper dynasty league gets a new `league_id` every season** (chained via
   `previous_league_id`). Replay is bounded to one league_id = one season. Fine for a 2026
   recap; a second fetch chain for "what your 2025 first became."
4. **Gap corruption is per-player, not per-league.** The plan says *"a single gap corrupts
   every date before it"* — true for the affected player, false for the roster. One missed
   waiver claim poisons that player's ownership prior to that date and nothing else. That
   matters, because it means the fallback **degrades per-player rather than per-league** and
   is materially more useful than the plan claims.

**The framing I disagree with, and the fix.** "Correct by construction (weekly) vs. fragile
salvage (replay)" is the wrong axis. Replay produces **exact timestamps** — strictly finer
resolution than any weekly grid. The honest comparison is *guaranteed but coarse* vs.
*exact but conditional*. Which means the strongest design is **both**, and the second one is
nearly free: in P2, reconstruct week W from `final roster + transactions` and **diff it
against the stored snapshot**. Every disagreement localizes either a bad snapshot or a
transaction-log gap. That is the only way to state a confidence *number* instead of
asserting one, and it is a script, not a project. See **B9**.

**Confidence, stated numerically as asked:**

| Window | Confidence | Basis |
|---|---|---|
| In-season Sleeper dates, draft source included | **High, >95% of player-weeks** | All state transitions are transactions; timestamps are exact |
| In-season Sleeper dates, drafts omitted | **Low for startup leagues, high for established ones** | Startups acquire their whole roster at the draft |
| Pre-season / pre-first-transaction | **None** | No source exists. The plan says this and is right |
| Commissioner roster surgery | **Medium** | Sleeper logs `type: "commissioner"` for most, not all, commish moves |
| ESPN / MFL | **Unknown** — F4 correctly flags it | And §7 already leans on platform-agnostic reach as a growth argument. Reconcile before P3 |

**What FTF's own tables can backfill today, at zero API cost: nothing for rosters.**
`league_members` holds one row per member with a single `updated_at` — a point, not a
series. `sleeper_trades` is empty in the dev DB and gated behind `market.trade_capture`;
confirm it is actually enabled in prod before leaning on it (the plan does say "live behind
`market.trade_capture`" — credit given, but B10 depends on the flag being *on*).

---

### A8. Event taxonomy

#### A8.1 Instrumentation audit

| Event | Registered? | Fires? | Verdict |
|---|---|---|---|
| `wrapped_viewed` | Yes — `SERVER_FIRED_EVENTS` (`analytics_taxonomy.py:342`), taxonomy comment (`database.py:1065`), `data-dictionary.md:727` | **No.** `git grep wrapped_viewed origin/main` returns only those three registry/doc sites — zero `record_event` call sites | **Dark. Confirmed.** |
| Everything else recap-related | — | — | **Missing entirely** |

Two structural constraints determine the whole spec:

1. **`wrapped_viewed` is SERVER-fired, and that is now binding.**
   `_assert_namespaces_disjoint` (`analytics_taxonomy.py:838-849`) raises at import — the app
   fails to boot — if a name appears in both registries. A mobile client told to "fire
   `wrapped_viewed`" through `POST /api/events` would be **counted and dropped behind a
   200** (default-deny ingest, `analytics_taxonomy.py:14-17`). The plan's §11 handoff to me
   does not flag this. See **B13**.
   **Recommendation: keep it server-fired**, emitted from `GET /api/wrapped/<season>` on a
   successful assemble. It is genuinely server-authoritative (the recap was produced), it
   ships without an App Store release, and it matches the standing rollout rule that
   server-fired lands first.
2. **`INTENT_EVENTS` is derived by SUBTRACTION** — `(SERVER_FIRED | ALLOWED_CLIENT) −
   NON_INTENT_EVENTS` (`analytics_queries.py:180`). Every impression-, outcome-, or
   navigation-class recap event must be added to `NON_INTENT_EVENTS` **in the same commit**
   that registers it. This tree has four recorded instances of exactly that failure
   (`analytics_taxonomy.py:381-388`). December is the worst month to get it wrong: the recap
   *is* a seasonal DAU spike, so an inflated denominator would be indistinguishable from the
   thing being measured, permanently.

#### A8.2 Proposed events — nine, in rollout order

| # | Event | Client | Class | Trigger (exact) | Props |
|---|---|---|---|---|---|
| 1 | `wrapped_viewed` | **server** | **INTENT** | `GET /api/wrapped/<season>` returns a complete recap (200, not the insufficient-data shape) | `season`, `slide_count`, `tier1_count`, `has_roster_history`, `weeks_covered`, `teams_covered` |
| 2 | `wrapped_unavailable` | **server** | NON_INTENT | Same route, insufficient data | `season`, `reason` (`no_roster_history`\|`no_league`\|`season_incomplete`\|`no_board_history`), `weeks_covered` |
| 3 | `wrapped_slide_viewed` | client | NON_INTENT | A slide becomes the active card | `season`, `slide_key` (closed enum), `slide_index`, `tier` (1\|2\|3) |
| 4 | `wrapped_completed` | client | NON_INTENT | Last slide reached | `season`, `slides_seen`, `duration_ms` |
| 5 | `wrapped_abandoned` | client | NON_INTENT | Exit before the last slide | `season`, `slide_index`, `slide_key`, `duration_ms` |
| 6 | `wrapped_share_tapped` | client | **INTENT** | User taps share | `season`, `slide_key`, `surface` (`slide`\|`summary`) |
| 7 | `wrapped_shared` | client | **INTENT** | OS share sheet reports completion | `season`, `slide_key`, `channel` (or `unknown`) |
| 8 | `wrapped_league_section_viewed` | client | NON_INTENT | League-superlatives section renders | `season`, `teams_covered`, `ftf_users_in_league` |
| 9 | `wrapped_invite_tapped` | client | **INTENT** | "Your leaguemate's season is already here" CTA | `season`, `surface` |

**INTENT reasoning, in the house style:**

- **`wrapped_viewed` — INTENT.** The one number the whole December build exists to produce,
  and server-authoritative. It is also *rare* (once or a few times a year per user), so
  unlike an impression it cannot plausibly step-change DAU.
- **`wrapped_slide_viewed` — NON_INTENT.** The classic impression class, the exact peer of
  `deck_card_viewed` and `league_pos_candidates_viewed`. It fires 10–20x per recap open;
  admitting it to INTENT would make one open read as twenty intentful actions.
- **`wrapped_completed` — NON_INTENT.** An OUTCOME, the exact peer of `mock_completed`
  (`analytics_queries.py`, mock-draft block): the user is already counted by the open.
- **`wrapped_abandoned` — NON_INTENT.** A dismissal-class terminator, consistent with
  `quickset_abandoned` and `league_team_closed`, both already in the deny-list.
- **`wrapped_unavailable` — NON_INTENT.** A refusal shown *to* the user; peer of
  `mock_create_refused`.
- **`wrapped_league_section_viewed` — NON_INTENT.** An impression; peer of
  `invite_cta_shown`.
- **`wrapped_share_tapped` / `wrapped_shared` / `wrapped_invite_tapped` — INTENT.** Exact
  peers of `calc_trade_shared` and `invite_cta_tapped`, which the P1 reasoning block kept
  deliberately INTENT. These are the growth numbers the recap is being built for.

#### A8.3 PII rules (default-deny)

- **No player ids or names in props, ever.** `slide_key` is a closed enum
  (`team_value_trajectory`, `biggest_riser`, `trade_pnl`, `your_calls`,
  `one_that_got_away`, `board_divergence`, `pick_flow`, `age_curve`,
  `league_superlatives`, `season_record`, `playoff_run`). Recap slides are inherently about
  specific players and the temptation to log "biggest riser: 4034" is high. That belongs in
  the recap payload, not in `user_events.props` — building a shadow roster history in the
  event log when `league_roster_history` exists is exactly the fork this role exists to
  prevent.
- **No leaguemate identifiers.** `teams_covered` and `ftf_users_in_league` are counts. YR-3
  permits *in-app display* of a leaguemate's valuations to an authenticated leaguemate; it
  does not authorize putting another user's identity into an analytics row keyed to a
  different user.
- **`league_id` rides the envelope column, never props** — the standing rule stated for
  `trade_sent` (`analytics_taxonomy.py`, `trade_sent` block).
- **`season` is an integer, not a league name.**

#### A8.4 Registration-before-emitter — the exact order

1. **Tracking-plan addendum first:** `docs/business/analytics/2026-1X-XX-wrapped-addendum.md`,
   modeled on `2026-08-11-p0-7-addendum.md`. This is the precondition the module docstring
   demands (`analytics_taxonomy.py:16-18`).
2. **One commit, four registries, nothing else:**
   - the five client names → `ALLOWED_CLIENT_EVENTS`;
   - a `CLIENT_EVENT_PROPS` entry for **each of the five** — the import-time assert at
     `analytics_taxonomy.py:857-864` raises and the app will not boot if one is missing;
   - the two new server names (`wrapped_unavailable` + keeping `wrapped_viewed`) →
     `SERVER_FIRED_EVENTS`;
   - **all six NON_INTENT names → `NON_INTENT_EVENTS` in that same commit**, with the
     per-event reasoning written inline, in the established style.
3. **Then** emitters — server first (`wrapped_viewed`, `wrapped_unavailable` ship with the
   route, no App Store release), client second.
4. Record the seam date in the addendum.

#### A8.5 Two constraints the recap dashboard must respect

- **`record_event()` (`database.py:2819-2831`) accepts no `platform`, `screen`, `device_id`,
  `event_id`, `client_ts`, `experiments` or `country` argument.** Server-fired rows leave all
  of them NULL, forever. Given the NULL-`platform` incident this repo keeps citing: **do not
  spec a recap dashboard that segments `wrapped_viewed` by platform** — it will be NULL 100%
  of the time. Either accept server rows as platform-blind and get platform from the client
  `wrapped_slide_viewed` rows, or extend `record_event` (an analytics-platform change, out
  of scope for this feature).
- **Do not add any recap event to `_EVENT_TO_USER_COL`.** Precedent is explicit:
  `sleeper_send_succeeded` was deliberately kept out because bumping a `last_*_at` column
  changes notification gating (`analytics_taxonomy.py`, `sleeper_send_succeeded` block). A
  `last_wrapped_viewed_at` would silently alter re-engagement push eligibility in December —
  the worst possible month for that.

---

### A9. Doc updates required

Per the CLAUDE.md trigger table — flagged because a schema spec that skips them is
incomplete:

| Change | Doc |
|---|---|
| `league_roster_history`, `league_board_history`, `ix_pvh_format_date` in `backend/database.py` | **`docs/data-dictionary.md`** — new sections in the style of the `player_value_history` entry (`:644-661`), each with the constraint paragraph and a retention line |
| `POST /api/cron/roster-snapshot`, `GET /api/wrapped/<season>` | **`docs/api-reference.md`** |
| The daily-tick weekday gate + `FTF_ROSTER_SNAPSHOT_WEEKDAY` | **`docs/config-reference.md`** and **`docs/architecture.md`** (the cron table at `:230`) |
| Nine new events | **`docs/business/analytics/…-wrapped-addendum.md`** (new), plus the `user_events` taxonomy comment (`database.py:1060-1066`) and `data-dictionary.md:727` |
| Monitoring: "a week with no roster row is history lost" | **`docs/runbook.md`**, mirroring the value-snapshot monitoring paragraph at `:295` |
| **Correction, independent of this feature** | **`docs/architecture.md:230`** is factually wrong today — see B1 |

---

## B. Disagreements and corrections

**B1. §1 — "scheduled in `render.yaml` at 06:00 UTC" is false on `origin/main`.**
`git show origin/main:render.yaml` contains exactly three cron services —
`notif-realtime-tick`, `notif-hourly-tick`, `notif-daily-tick` — and no value-snapshot job.
`docs/runbook.md:295` records that the `value-snapshot-daily` blueprint cron *was* added on
2026-07-26 and **removed the same day** because it broke Render blueprint sync, and that
"the operative mechanism is the `hourly-tick` idempotent fallback guard." The plan cites
`docs/architecture.md:230`, which still asserts the cron exists — that line is stale and
contradicted by the runbook. **Why it matters:** the plan's P0 implicitly assumes a new
weekly Render cron can be provisioned the same way. It cannot (`runbook.md:586` states the
rule generally). A4.1 gives the mechanism that actually works. Fix `architecture.md:230`
regardless of this feature.

**B2. §5.2 — "No extra API calls. Sync already fetches rosters… data already in memory" is
false for the weekly path.** `upsert_league_members` (`database.py:5526`) has one production
caller, `server.py:15276`, inside `session_init`, and the rosters are **client-supplied**
(`server.py:14664-14670`, `14686-14690`). A weekly cron has no session and no client;
reading `league_members` stamps possibly-months-old data with this week's `period_key`,
which is fabrication — the exact thing `runbook.md:295` forbids. The weekly job needs
`_fetch_league_rosters` (`server.py:10564`), one Sleeper call per league per week. **This is
the largest single correction and it changes the P0 estimate.**

**B3. §5.1 — `UNIQUE (league_id, user_id, snapshot_at)` enforces nothing and cannot satisfy
YR-6.** Three defects: (a) `snapshot_at` is an *instant*, so two runs produce two rows —
compare `uq_value_snapshot`, which keys on the `"YYYY-MM-DD"` bucket precisely so the upsert
works (`database.py:1003-1005`); (b) `user_id` cannot key an orphan team, and orphan teams
are exactly what YR-6 demands; (c) the parenthetical "or `roster_id` for non-FTF teams" has
no source — `league_members` has no `roster_id` column at all (`database.py:321-333`), and a
polymorphic key column whose meaning varies by row is unjoinable. Spec: `team_key` +
`period_key`, sourced from the server-side `/rosters` fetch.

**B4. §5.1 — `roster_hash -- change detection` is underspecified in a way that would break
YR-2.** If the hash suppresses unchanged writes, the weekly series goes sparse. But
`team_value` moves every week even when the roster doesn't (consensus values move daily), so
the chart YR-2 exists to stabilize would have holes in precisely the quiet weeks. The grid
must be **dense**. The hash's jobs are `changed_from_prev` and suppressing *extra* on-sync
writes — never the weekly write.

**B5. §2.1 / §10 YR-3 consequence — C6 is not a new capture problem, and "append to
`elo_history`" is not a safe fix.** `elo_history` (`database.py:971-979`) already logs
per-user valuations over time; the gap is cadence, identical to C5. **But** `elo_history`
writes only *changed* players (`:965-966`), so it can never rebuild a complete board without
folding forward from row one; and it has **no uniqueness constraint whatsoever**, so §5.4's
proposed weekly append is not idempotent — a double run doubles every board silently. Row-
per-player weekly is also 1.6M rows at 100 leagues. **C5 and C6 collapse into one build item:
`league_board_history`, one JSON row per board per period (A3).**

**B6. §4.2 F7 — "age is a trap" understates it.** `players.age` (`database.py:657`) is not
merely "age at season end" — it is **overwritten on every Sleeper bulk sync** (24 h TTL) and
has no history at all. `players.birth_date` (`:658`) is the stable input and the plan is
right to say compute age per date. What it misses: birth_date is **not guaranteed present**
for prospects and camp bodies, so C10's roster age curve needs a coverage denominator the
same way `team_value` needs `valued_player_count`. Verify birth_date coverage now, not in
P2 — if Sleeper ever drops a birthdate we have no snapshot of it.

**B7. §4.1 C2 — `team_value` cannot be "the roster's value."**
`_write_daily_value_snapshots` (`server.py:16810-16828`) iterates the DP-seeded universal
pool only, so kickers, defenses and deep-bench camp bodies have **no `player_value_history`
row, ever**. Meanwhile `league_members` deliberately stores "the RAW client-sent ids"
including off-pool players (#151, `server.py:15258-15265`). So `team_value` is a sum over
pool-resident players and nothing else. Store `valued_player_count` beside `player_count`,
and write `NULL` rather than `0` when nothing prices — otherwise a coverage gap renders as a
roster wipe and nobody will be able to tell the two apart in December.

**B8. §2.3 — the transaction-log claim omits three mechanics that decide whether replay
works.** (i) Draft selections are **not transactions** — they need
`/v1/draft/<id>/picks`, reached via `/league/<id>/drafts` (`sleeper.md:44`); for a startup
league that is the entire opening roster. (ii) Offseason moves all land on `leg 1`
(`sleeper_trades_service.py:36-38`), so replay must order by `status_updated`, never `leg`.
(iii) A Sleeper dynasty league gets a **new `league_id` every season**, so replay is bounded
to one season per chain. Also, gap corruption is **per-player, not per-league** — which
makes the fallback more useful than the plan claims, not less.

**B9. §2.3 conclusion — the framing is on the wrong axis.** "Correct by construction" vs.
"fragile salvage" compares the wrong properties. Replay yields **exact timestamps** — finer
than any weekly grid. The real trade is *guaranteed but coarse* vs. *exact but conditional*.
**Recommendation: run the replay in P2 as a verifier**, diffing reconstructed week W against
the stored snapshot. It is a script, and it is the only way to publish a confidence number
in December rather than assert one.

**B10. §5.2 — the mid-season-trade argument is right about the problem and wrong about the
remedy.** Roster resolution is not the binding constraint on trade attribution:
`sleeper_trades` (`database.py:359-378`) already stores every completed trade with a
`status_updated`-derived `traded_at`. Overlaying trades on a weekly grid gives **day-exact**
attribution for trades with no daily snapshot at all. Weekly remains the right cadence — for
a stronger reason than the plan gives, which is worth having on the record when someone
later proposes going daily. **Residual gap:** waiver and free-agent adds are *not* captured
(`parse_trade_transactions` filters `type == "trade"`, `sleeper_trades_service.py:93`), so a
waiver pickup that spikes mid-week still mis-attributes. Whether that matters is a product
call, and it should be made explicitly rather than discovered.

**B11. §7 — "Platform-agnostic reach — serves ESPN and MFL leagues" is not supported by the
capture design.** `_fetch_league_rosters` is Sleeper-only; there is no ESPN or MFL weekly
roster fetcher and P0 does not scope one. Either scope per-platform fetchers into P0, or
strike the platform-agnostic growth claim until P2 verifies feasibility. Whichever: ESPN/MFL
leagues must record a **hole** for the period, never a copy-forward of the last known
roster.

**B12. Missing index on `player_value_history`.** The table has exactly one index — the
`uq_value_snapshot` constraint (`database.py:1003-1005`). Any recap query shaped "every
player's value on these 20 dates" (`WHERE scoring_format = ? AND snapshot_date IN (...)`)
has no leading-column match and full-scans a table the data dictionary already projects at
~0.5M rows/yr (`data-dictionary.md:659`). Add `ix_pvh_format_date (scoring_format,
snapshot_date)` to the idempotent list in `_migrate_db` (`database.py:2160-2185`). Free now,
a table scan later.

**B13. §11 — the handoff to me omits that `wrapped_viewed` is server-fired, which forbids
the client from firing it.** `_assert_namespaces_disjoint` (`analytics_taxonomy.py:838-849`)
raises at import if a name lands in both registries, and the ingest is default-deny behind a
200 (`analytics_taxonomy.py:14-17`). A mobile engineer told to "fire `wrapped_viewed`" would
ship a silently-dropped event with a success-shaped response — the fifth instance of a
failure this tree has already recorded four times. A8.1/A8.4 resolve it: keep it server-fired
from `GET /api/wrapped/<season>`.

**B14. §9 — "Storage cost: None" predates YR-3 and must not be inherited by the C6 build.**
It is correct for rosters (240 rows/league-season, ~240 KB) and it is the right instinct.
But YR-3 added C6 after that row was written, and C6 at row-per-player grain is **1.6M rows
at 100 leagues**. The verdict stays "None" only because A3 specs JSON-per-board. Note it, so
nobody quotes §9 at a reviewer who raises it.

**B15. §8 — "~1 week of work" for P0 is optimistic** once the server-side fetch, orphan-team
handling, `team_key` derivation, ESPN/MFL hole semantics, the pvh-gap defense, and the C6
table are included. Not strictly my lane — flagged for the eng-architect's estimate, since
the schedule argument ("before Week 1, ~Sept 10") is the plan's central urgency claim and it
should survive contact with the real scope.

---

## C. Open questions for eng-architect

1. **Weekly-job mechanism.** I spec the `daily-tick` weekday gate (`server.py:16231-16245`,
   `16676`) as the contract, with `POST /api/cron/roster-snapshot` optional and
   hand-provisioned. Do you accept that as the standing pattern for weekly work given
   `runbook.md:295`/`:586` forbid blueprint crons — or is the operational opacity of
   dashboard-provisioned crons the lesser evil?
2. **Sweep shape under the free-plan 120 s timeout** (`render.yaml:16`, `--workers 1`). A
   weekly sweep doing N Sleeper fetches inline breaks past roughly 30 leagues. I lean on the
   `_DRAFT_STATUS_SWEEP_BUDGET = 50` bounded stalest-first rotation (`server.py:12285`,
   `16471-16479`) over the `players-refresh` daemon-thread-plus-202 pattern
   (`server.py:16775-16791`) — rotation self-heals and needs no thread. Agree?
3. **Postgres storage ceiling.** At 1,000 leagues the two new tables total ~470 MB on
   `basic-256mb` (`render.yaml:5`). Does that fit, and is the retention/downsample policy an
   ADR rather than a build detail? `player_value_history` already carries a deferred
   downsample note (`data-dictionary.md:659`) — one policy could cover both.
4. **Client-supplied roster trust.** The recap will make league-visible comparative claims
   (YR-3) from data any client can POST (`server.py:14686-14690`). Does the server-side
   `/rosters` fetch I am speccing fully close this, or does league-comparative output from
   client-attested inputs warrant an ADR in its own right?
5. **Is `market.trade_capture` on in prod?** §2.1 lists `sleeper_trades` as live-behind-flag;
   the dev DB has 0 rows. My correction B10 — weekly cadence is sufficient because trades
   carry exact timestamps — depends on that flag actually being enabled.
6. **ESPN/MFL in P0.** Does P0 scope per-platform roster fetchers, or ship Sleeper-only and
   defer §7's platform-agnostic claim to P2?
7. **`period_kind` from day one?** One column, and it makes a later daily or on-sync grain a
   write-path change instead of a migration on a populated table. I say add it; cheap
   insurance, and reversible.
8. **`league_board_history` vs. retrofitting `elo_history`.** I chose a new table on volume
   grounds (A3) and I want that challenged explicitly, because "don't fork" is a guardrail I
   am deliberately trading against a 6,750x row multiplier. If you disagree, the alternative
   is `elo_history` + a nullable `period_key` + a **partial** unique index — which works on
   both dialects but adds a conflict path to the ranking-submit hot path, and requires a
   Postgres `ON CONFLICT` targeting the index expression rather than a constraint name.
