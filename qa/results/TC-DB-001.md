# TC-DB-001 — Schema integrity, migration idempotency, SQLite↔Postgres parity, live-data quality

| Field | Value |
|---|---|
| **Status** | PASS (24/24 checks, Postgres plane included) |
| **Date executed** | 2026-06-11 |
| **Layer** | db |
| **Component(s)** | `database.py::init_db/_migrate_db`, dialect-branched upserts (`upsert_league`, `upsert_league_members`, `upsert_member_rankings`, `add_skip`); live `data/trade_finder.db` |
| **Requirement / doc ref** | CLAUDE.md "swappable to Postgres via DATABASE_URL"; docs/data-dictionary.md; recon prod-parity gap |
| **Engine path & flags** | n/a (data layer); fresh schema built on both dialects |

### Objective
Close the prod-cutover gap: prove the app's schema and dialect-branched writes
behave identically on SQLite (dev) and Postgres (Render prod), that migrations
are safely re-runnable, and that live data is internally consistent.

### Scope
- **In scope:** fresh-init schema parity (table set + per-table columns) SQLite
  vs Postgres; `_migrate_db()` idempotency (re-run, no schema change, no error)
  on both; dialect upsert smoke incl. the F-1 second-member league upsert;
  live-DB orphan classification, enum domains, timestamp format, boolean
  storage, duplicate guards.
- **Out of scope:** index *name* parity (SQLAlchemy auto-names differ by
  dialect — column coverage is what matters), query-plan/perf parity, data
  migration of an existing SQLite DB into Postgres (separate cutover runbook).

### Preconditions / Setup
- Local Postgres (Postgres.app) reachable; `psycopg2-binary` (declared in
  requirements.txt) installed into the env. Throwaway DB `ftf_qa_parity`
  created fresh and dropped after. Live DB read-only; SQLite plane uses a fresh
  empty file so the schema reflects the code's `CREATE`, not existing data.

### Inputs / Steps
Automated: [qa/db/tc_db_001.py](../db/tc_db_001.py) + probe
[qa/db/_dialect_probe.py](../db/_dialect_probe.py). The probe runs per-dialect
in a subprocess (so `database.py` binds its engine to the right `DATABASE_URL`):
init → schema snapshot → re-run `_migrate_db()` → upsert smoke battery → emit
JSON. The orchestrator compares the two snapshots and audits the live DB.

### Expected Result
Identical 24-table schema with matching columns on both dialects; migrations
idempotent; all dialect upserts succeed with the documented row semantics
(leagues = 1 row/league, league_members no-dup, member_rankings replace-snapshot,
skips idempotent); F-1 second-member upsert does not raise on either dialect;
live data clean (benign orphans only, enums in-domain, ISO timestamps, 0/1
booleans, no dup members).

### Actual Result
**24/24 PASS.** Schema parity exact (24 tables, all columns). Migrations
idempotent on SQLite and Postgres. **F-1 fix confirmed cross-dialect** — the
second-member league upsert succeeds and leaves exactly one `leagues` row on
both SQLite and Postgres. Live audit clean: 41 orphan rows / 20 distinct users,
**0 with rankings, 0 in trade_matches** (confirmed benign — never-logged-in
leaguemates). Evidence: `qa/db/scratch/TC-DB-001-run.json`.

### Outcome
**PASS** — the SQLite→Postgres swap is safe at the schema + write-path level;
the recon "moderate prod-parity risk" is downgraded to low. Migrations re-run
cleanly on redeploy.

### Findings requiring attention
| ID | Severity | Finding | Evidence | Suggested action |
|---|---|---|---|---|
| F-1 | **P3 (resolved-adjacent)** | The 41 orphaned `league_members` rows (recon "HIGH, fix before scale") are **benign by design** — leaguemates who appear in a roster snapshot but have never logged in (no `users` row, no rankings, never in `trade_matches`). Not a data-integrity defect. | live audit: 0 ranked, 0 in matches | Downgrade the recon item. Optionally add one line to docs/data-dictionary.md `league_members` noting `user_id` may reference a not-yet-onboarded member. |

### Observations & feedback (no change required)
- **Postgres parity is real, not theoretical now** — every dialect-branched
  write path (`INSERT OR REPLACE`/`ON CONFLICT`, the `on_conflict_do_update`
  league fix) was exercised on an actual Postgres server and matched SQLite.
  The `qa/db/_dialect_probe.py` is reusable as a pre-cutover gate.
- **Migrations are additive + idempotent** (try/except `ADD COLUMN`,
  `CREATE INDEX IF NOT EXISTS`, `INSERT OR IGNORE`/`ON CONFLICT` seeds) — safe to
  re-run on every boot, which is exactly how Render redeploys invoke them. No
  version table, but for additive-only migrations that's an acceptable tradeoff
  (noted for when a destructive migration is ever needed).
- **data-dictionary.md is in sync** — all 24 tables documented (the recon
  "22/23 tables" was a skim miscount; no drift).
- `psycopg2-binary` was missing from the local env despite being in
  requirements.txt — worth a one-line dev-setup note so contributors can run the
  Postgres plane locally.
