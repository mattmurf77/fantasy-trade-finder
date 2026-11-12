# Feature Scope — per-user binding for linked ESPN / MFL leagues

**Date:** 2026-11-11
**Entry point:** direct ask (operator: "fix the ESPN overwrite bug"; MFL found to share the defect)
**Builder:** link-binding builder agent, branch `fix/platform-league-user-binding`
**Operator sign-off on waivers:** needed for §1 (c) and §3 TestFlight (see below)

Design and reasoning: [design.md](design.md).

---

## 1. Analytics scope

- [ ] (a) New events specced — none.
- [ ] (b) Existing events cover it — n/a.
- [x] **(c) WAIVED — no analytics needed because:** a correctness fix to stored identity;
      no new user action or surface. The damage is measured once with the read-only
      aggregate query in [design.md §7](design.md#7-counting-the-damage-read-only-postgres),
      and the boot backfill prints its own counts (`[backfill] platform_league_bindings: {…}`).

## 2. Schema & flag scope

- New table **`platform_league_bindings`** (PK `user_id, league_id`; `platform`, `team_id`,
  `source`, `created_at`, `updated_at`; index `ix_plb_league`). Additive: created by
  `metadata.create_all` on both dialects, no `migration_cols` row (new table). Idempotent
  evidence-gated backfill from `_migrate_db` every boot (`backfill_platform_league_bindings`).
  No column dropped or rewritten; `leagues.espn_my_team_id` / `platform_my_team` become
  legacy (still written, read only by the backfill). → `docs/data-dictionary.md` updated.
  User-keyed: deleted + exported with the account (`accounts._ADDITIONAL_PRIVATE_TABLES`).
- New/changed feature flags: **none.** Not flag-gated on purpose: the fix replaces a
  corrupting write; a flag-off path would keep corrupting. Rollback lever = revert the
  deploy (old code reads the still-written legacy columns; the new table is ignored).
- New env vars / `model_config` keys: none.

## 3. Evidence scope

- [x] **Unit tests:** `backend/tests/test_platform_league_binding.py` (36 tests): two-user
      ESPN/MFL reproductions in both link orders, re-link, re-sync by either user, the MFL
      sign-in import path, one user relinking, two accounts on one team, unbound users
      failing closed, cookie re-sync not un-verifying, sends using the SENDER's team and
      cookie in both orders, counterparty by real id, the overhaul's fresh rosters,
      credential disconnect + account deletion isolation, backfill (intact / overwritten /
      partial / SWID conflict / idempotent / race / untouched rows / via `_migrate_db`),
      Postgres DDL + upsert compile, Sleeper snapshot untouched, no platform FA moves, and
      two seam tests. 23 red on `main`, all green with the fix; 13 named sabotages each red.
- Existing tests changed (they seeded the binding as a raw `leagues` column, i.e. encoded
  the old storage model): `test_espn_draft_order.py` (fixture runs the backfill),
  `test_roster_history.py` (seeds `u1`'s binding), `test_draft_board.py` (stubs the two
  accessors like it stubs `get_platform_league`), `test_calibration_linked_capture_real_arms.py`
  (seeds ME's binding beside the raw row). No assertion changed.
- [x] **Code-walk proof:** design.md §4–§5 lists every writer and reader with the change.
- [x] **Manual TestFlight checklist** (runtime proof matters: two real accounts):
  1. Accounts A and B on two devices, one ESPN league (public is fine), A owns team 1, B team 2.
  2. A links the league, picks team 1. B links it, picks team 2.
  3. On A: the league is still in the picker; My Team shows team 1's roster; Find a Trade
     cards give team-1 players. On B: the same for team 2.
  4. On A, pull to refresh / re-sync the league: still team 1. Same on B.
  5. On A, open a trade with B's team (B appears under B's name) and send it (ESPN send
     flag permitting): the ESPN offer comes from team 1. Repeat from B.
  6. Repeat 1–4 for an MFL league (franchise ids).
  7. A deletes their account: B's league, team and sends are unchanged.
  8. A user whose league vanished before this release opens the picker: the league is
     listed after re-linking it, with their own team.
- `testID`s: none (backend only).

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route added/renamed and no response shape changed; `/api/*/import`, sends and MFL respond/pending return the existing `*_not_linked` 404 for a caller without a binding (same code, same copy) |
| `living-memory/LLD.md` | not written (builder may not touch living-memory) | convention: "my team" in a platform league = `get_platform_binding`; text handed to the operator |
| `docs/architecture.md` | updated | linked-platform data flow: per-user binding |
| `living-memory/HLD.md` | n/a | no new module or client |
| `docs/cross-client-invariants.md` | n/a | the client contract (`mine` = member whose id is me) is unchanged |
| `docs/glossary.md` | updated | "Platform league binding"; "Synthetic member id" corrected |
| `docs/data-dictionary.md` | updated | new table; `leagues` legacy columns; `league_members` labels |
| `docs/integrations/espn.md`, `mfl.md` | updated | binding sections; MFL "single-linker" limitation removed |
| `docs/runbook.md` | updated | count query pointer, repairing a lost binding |
| ADR or `DECISIONS.md` entry | text handed to the operator | D-entry text in the build report |

## 5. Ship gate declaration

- **CI green:** `backend-tests` (full suite run locally, see TEST_LEDGER text in the report);
  no mobile change, so `mobile-typecheck` / testid-lint unaffected.
- **Evidence recorded:** TEST_LEDGER entry to be written by the merging session.
- **TestFlight verification:** §3 checklist, operator.
- Express lane declared by the operator? no.
