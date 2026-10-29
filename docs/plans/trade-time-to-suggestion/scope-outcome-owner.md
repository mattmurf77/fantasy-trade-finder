# Feature Scope — G3-e: `deck_outcomes.user_id` (an outcome's owner, for deletion and export)

**Date:** 2026-10-29
**Entry point:** direct ask. head-eng's routing of legal R28.22 and models-lead's addendum G (2026-10-29), item G3-e: "add a nullable, indexed `user_id` to `deck_outcomes`, written from the session user by the outcome write path (`_save_deck_outcome_safe`). Deletion and export ALSO match on it." No backfill. Target: release-lead's queue before the 200 ms flip, so every post-flip outcome carries its owner.
**Builder:** trades-eng. onboarding-eng reviews the `accounts.py` part. It is sequenced against #540 (the overhaul deletion fix, also in `accounts.py`): the two touch different hunks and merge cleanly in either order.
**Operator sign-off on waivers:** not needed. Analytics is answered (c) with its reason, and the evidence is answered in full.

**What it does:**
- `deck_outcomes` gains `user_id` (nullable `VARCHAR`), and an index on it (`ix_deck_outcomes_user`).
- `database.save_deck_outcome` writes `acting_user_id` into it. That is the session user that `server._save_deck_outcome_safe` resolves and checks against the request's verified session.
- `accounts._delete_user_data` and `accounts.export_user_data` match outcomes on it **as well as** on today's path (through the user's `deck_impressions` rows; with #523, also through their packs' contract ids). Neither path replaces the other.
- No backfill. Rows written before the column are NULL and stay reachable through rows and packs.

**Why, and the gap it closes (code walk, file:line on this branch):**
- Today an outcome reaches deletion and export only through its impression: deletion via `impression_id IN (the user's deck_impressions)` (`backend/accounts.py:793`), and export the same (`:1249`).
- So an outcome whose impression has neither a row nor a pack card is unreachable, and it would outlive deletion. That is the shape #535 logs: a deck with no rows and no pack (`backend/server.py:6638`).
- **The gap is latent on today's code, not live.** Every outcome write requires an owned `deck_impressions` row at write time:
  - `save_deck_outcome`'s insert selects `WHERE owner.exists()`, where `owner` is a `deck_impressions` row of that impression whose `user_id` is the acting user (`backend/database.py:7812`, `:7826`).
  - `_save_deck_outcome_safe` drops an id with no row and no pack upgrade as `unknown` (`backend/server.py:9973-9975`).
  - So a #535 deck's cards get no outcome today: the disposition is dropped and counted as an `unknown` reject.
- The column makes reachability a property of the outcome row itself. It no longer depends on how the deck's evidence was stored, or on what later prunes it. That covers:
  - #523's 90-day full-row prune (its pack keeps the card reachable today);
  - any future path that accepts an outcome on a pack-less deck's card;
  - an alias whose rows are gone.
- **The column is never another user's id.** The owner check is unchanged, so the id written is always the impression's owner, and matching on it can't delete or export another user's outcome.

**Deletion counts:** the owner-column delete runs **after** today's path (`backend/accounts.py:807`), under its own key, `deck_outcomes_by_owner_deleted`. So that count is exactly the outcomes only the new column reached: the measured size of the gap, 0 while it stays latent. `deck_outcomes_deleted` keeps its meaning.

**The index on prod (revised after release-lead's question, 2026-10-29):**
- `ix_deck_outcomes_user` is **never built at boot.** A plain `CREATE INDEX` on prod's `deck_outcomes` holds a SHARE lock that blocks every outcome write (likes, passes, views) for its whole scan.
- A fresh DB gets the index from the `Index` declaration (`create_all`). On an existing table, `scripts/create_outcome_owner_index.py` builds it off the boot path, the same pattern as #523's `ix_deck_impressions_served`:
  - Postgres: `CREATE INDEX CONCURRENTLY` with a 5 s `lock_timeout`, in autocommit;
  - an INVALID leftover of a failed build is dropped concurrently and rebuilt;
  - idempotent; `--check` reports without writing.
- It's run once after the deploy, by release-lead on the operator's word, since it's a prod write.
- **Until it runs, nothing breaks:** deletion's `DELETE … WHERE user_id IN (…)` and export's `SELECT` find the rows by a scan, inside the deletion transaction. It's slower, but only for the rare deletion or export.
- **The column itself** is added at boot by `_migrate_db`'s generic `migration_cols` loop, like every additive column before it (~20 on `deck_impressions`).
  - On Postgres, `ADD COLUMN` with no default and nullable is catalog-only: no rewrite and no scan. Its ACCESS EXCLUSIVE lock is held for milliseconds once granted.
  - The residual risk is the usual one: the `ALTER` waits behind a long open transaction on the table, and writes queue behind it meanwhile.
  - It isn't bounded with a `lock_timeout`, because a timed-out `ALTER` would leave the column missing. Then the outcome insert, which names `user_id`, would fail on every write until the next boot. Waiting is the lesser harm.

---

## 1. Analytics scope

- [x] **(c) WAIVED. No analytics needed.** It's a storage column for account rights; no user-visible behavior changes, and no event is added or changed. The new deletion count rides the deletion route's existing `counts` map (logged, and returned to the client that asked for the deletion).

## 2. Schema & flag scope

- **Columns:** `deck_outcomes.user_id` (nullable `VARCHAR`), with index `ix_deck_outcomes_user`.
  - The column is added by `_migrate_db`'s `migration_cols`. The index is never built at boot: it comes from the `Index` declaration on a fresh DB, and from `scripts/create_outcome_owner_index.py` on an existing one.
  - Documented in `docs/data-dictionary.md` § `deck_outcomes`.
- **Flags:** none. The column is written whenever an outcome is (flag `deck.signal_v2` gates outcomes as before), and the deletion and export match is unconditional. Like #523's account-rights fix (legal R28.22 d1), it goes live on merge, behind no switch.
- **Env vars / `model_config` keys:** none.
- **The entry-user purge:** `scripts/purge_entry_users.py`'s `DELETION_ONLY_KEYS` gains `("deck_outcomes_table", "user_id")`. `test_purge_entry_users.py`'s discovery guard requires every user-id column `delete_user_data` filters on to be listed there.

## 3. Evidence scope

- [x] **Unit tests:** `backend/tests/test_deck_outcome_owner.py`, 7 tests.
  1. The write stamps the acting user, and the unchanged owner check refuses a foreign writer.
  2. The same through `_save_deck_outcome_safe` under a verified session.
  3. Deletion: it reaches an outcome that only the column names (no row, no pack), including an account alias's. It keeps another user's outcomes and NULL legacy rows. Each count is right: `deck_outcomes_deleted` for today's path, `deck_outcomes_by_owner_deleted` for the outcomes only the column reached.
  4. Export: each owned outcome once (one reached both ways is not duplicated), in id order, with legacy NULL rows through the row path and nothing of another user's.
  5. Boot on a pre-G3-e table (`init_db`, twice): adds the column, **never the index**, and leaves the old row NULL (no backfill). A fresh DB gets the index from the declaration.
  6. The script on an existing table: `--check` reports `missing` and writes nothing; a run builds it on `user_id`; a second run leaves it valid.
  7. The script's Postgres build, pinned in source: `CONCURRENTLY`, autocommit, the 5 s `lock_timeout`, and the INVALID leftover dropped first. `_migrate_db` never names the index.
- [x] **Existing guard:** `test_purge_entry_users.py::test_discovery_covers_every_user_column_delete_user_data_filters_on` covers the new filter column.
- [x] **Sabotages: 16 of 16 mutations turn the suite red.** The suite is the new file plus `test_purge_entry_users.py` and `test_account_deletion_coverage.py`. The mutations:
  - a NULL owner written;
  - the deletion: no owner delete; the owner delete moved before the row path (the counts change);
  - the export: no owner match; no dedupe; no sort;
  - the migration: no column; the index built at boot; no metadata index;
  - the script: not `CONCURRENTLY`; not autocommit; no `lock_timeout`; the INVALID leftover not dropped; `--check` builds; the wrong column;
  - the purge key missing.
- [x] **Code-walk proof:** above ("Why, and the gap it closes").
- [x] **Manual TestFlight checklist:** not applicable. It's backend-only, with no client or user-visible change. The deletion and export routes' responses gain one count key and one column, additively.
- `testID`s: none.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | `DELETE /api/account` (outcomes also by `user_id`; the `deck_outcomes_by_owner_deleted` count) and `GET /api/account/export` (outcomes by `user_id` too) |
| `docs/data-dictionary.md` | updated | § `deck_outcomes`: the `user_id` row and `ix_deck_outcomes_user` |
| `living-memory/LLD.md` | n/a | no convention shift: an additive column through `migration_cols`, the existing pattern |
| `docs/architecture.md` / `living-memory/HLD.md` | n/a | no module wiring or data-flow change |
| `docs/cross-client-invariants.md` | n/a | no shared constant |
| `docs/glossary.md` | n/a | no new term |
| ADR / `DECISIONS.md` | n/a | head-eng's ruling (the routing note, G3-e), recorded there and in legal R28.22 |
| `docs/config-reference.md` | n/a | no flag, env var or `model_config` key |
| `scripts/README.md` | updated | § One-time index build (`create_outcome_owner_index.py`) |

## 5. Ship gate declaration

- **CI green:** `backend-tests`, `mobile-typecheck` and `maestro-testid-lint` on the pushed sha.
- **Evidence recorded:** the `living-memory/TEST_LEDGER.md` entry.
- **TestFlight verification:** none (backend-only).
- **Express lane:** no; full gates (an additive schema change).
- **Before the flip** (head-eng's target), so every post-flip outcome carries its owner.
- **Merge order (release-lead's QA P2-1):** after #427, or in the same deploy.
  - Without #427, every boot re-issues the `ALTER` (a DuplicateColumn error, but only after taking ACCESS EXCLUSIVE). It then waits, unbounded, behind any open transaction on `deck_outcomes`; QA measured a 17.9 s stall on outcome writes.
  - #427 skips an `ALTER` once the column exists, and fails a boot whose lock is busy while the old instance serves.
- **Known edges (QA P3s, accepted):**
  - Outcomes the old instance writes between `build.sh`'s `ALTER` and the traffic switch get a NULL `user_id`. They're reached through rows and packs, like every pre-G3-e row.
  - The script's Postgres path is pinned only in source (CI has no Postgres). QA ran it on PG 18: `CONCURRENTLY`, the 5 s timeout, and an INVALID index rebuilt.
- **After the deploy (release-lead, on the operator's word: a prod write):** run `python3 scripts/create_outcome_owner_index.py --check`, then `python3 scripts/create_outcome_owner_index.py` (expect `ix_deck_outcomes_user: valid`). It isn't a correctness gate, since deletion and export work by a scan until then.
