# Feature Scope — Pick-assignment grid never stores a user id as a name

**Date:** 2026-10-27
**Entry point:** direct ask from head-eng, 2026-10-27, found during #452's QA
**Builder:** draft-eng → eng-backend worker
**Operator sign-off on waivers:** not needed (no waivers)

---

## 1. Analytics scope

- [ ] **(a) New events specced:** none.
- [x] **(b) Existing events cover it** — `pick_assignment_changed` (the grid's
  `user_events` audit trail) already records every assignment. This change
  alters only the stored display string, so there is no new question to
  measure.
- [ ] **(c) WAIVED:** n/a, (b) applies.

## 2. Schema & flag scope

- New/changed tables or columns: none.
- New/changed feature flags: none. The fix rides the existing `picks.assign`.
- New env vars / `model_config` keys: none. Rollback is a code revert.
- **Existing stored rows are NOT repaired.** Rows already written with
  `Team <user_id>` keep that string until the slot is reassigned or the grid
  reseeds. Only a `POST …/order` with `reseed: true` rewrites them: without it
  `seed_pick_grid` preserves every existing row verbatim
  (`backend/database.py`, the `prior is not None and not reseed` branch). A
  data repair would be a prod write and is out of scope (noted for
  release-lead).

## 3. Evidence scope

- [ ] **Structural guard:** none. No mobile change.
- [x] **Unit tests:** new `backend/tests/test_pick_assignment_names.py`, 6
  cases. It uses the real routes, an in-memory SQLite DB and production-shape
  members: the caller `acct_caller` ("Dana"), `u_named` (display_name only,
  "Riley"), `espn:{1A2B3C4D-SWID}` (username None, display_name `"   "`),
  `acct_testnameless` (username `""`, display_name None).

  | Test | Pins | Result |
  |---|---|---|
  | T1 `test_t1_seeded_grid_never_names_a_team_by_user_id` | seeding via `POST …/order`: no stored or served `owner_username` / `original_username` holds a member id, `espn:`, `acct_` or the SWID; nameless members' rows read `Team <original_roster_id>` | pass |
  | T2 `test_t2_put_to_nameless_member_stores_their_slot_label` ×2 (SWID, acct) | PUT to a nameless member with slots stores `Team <their slot>` | pass |
  | T3 `test_t3_put_to_slotless_nameless_member_stores_unnamed_team` ×2 (`espn:{9F8E7D6C-LATE}`, `acct_latecomer`) | PUT to a nameless member added after seeding stores `Unnamed team` | pass |
  | T4 `test_t4_named_members_keep_their_real_names` | named members keep `username` / `display_name` on the seeder and PUT paths | pass |

  **Sabotage:**

  | Step | Red | Green | Red tests |
  |---|---|---|---|
  | Fix 1 reverted alone (`_assignment_members` back to `… or f"Team {uid}"`) | 5 | 1 | T1, T2 ×2, T3 ×2 (T2/T3 also go red because the old dict maps every member, including whitespace names) |
  | Fix 1 restored, fix 2 reverted alone (PUT back to `names.get(owner, f"Team {owner}")`) | 4 | 2 | T2 ×2, T3 ×2 |
  | Both restored | 0 | 6 | none |

  Area suites (`test_pick_assignment_names`, `test_pick_assignment`,
  `test_pick_assignment_tradeable`, `test_draft_board`,
  `test_espn_draft_order`, `test_mock_pick_ownership`): **204 passed**
  (6 + 36 + 37 + 67 + 42 + 16). No existing test asserted the old
  `Team <uid>` fallback. Their `Team u1`-style strings are stored usernames,
  not fallbacks.
- [x] **Code-walk proof** (line numbers on `fix/pick-grid-name-fallback`):
  1. `backend/server.py:21828` `_assignment_members` adds a member to
     `names` only when `username` → `display_name` is non-blank
     (`:21853-21855`). A nameless member is absent from the dict.
  2. `backend/server.py:22298` `pick_assignments_order_route` reads
     `member_ids, names` (`:22339`) and passes `user_id_to_name=names` to
     `seed_pick_grid` (`:22376-22378`).
  3. `backend/database.py:12626` / `:12629` `seed_pick_grid` writes
     `owner_username` / `original_username` as
     `user_id_to_name.get(uid, f"Team {orig_rid}")`. That fallback now fires
     for a nameless member, and `orig_rid` is the league-local slot label.
     Rows persist through `replace_draft_picks` (`:12660`).
  4. PUT: `backend/server.py:22210` `pick_assignment_put_route` already
     loads `prior` (`:22256`, full `draft_picks` rows, so they carry
     `original_user_id` / `original_roster_id`) and stores
     `_assignment_owner_name(names, prior, owner)` (`:22263`). The helper
     (`:21860-21874`) returns the real name, else `Team <slot>`, else
     `Unnamed team`, and never the id.
  5. `GET /api/league/pick-assignments`: `backend/server.py:22150`
     `pick_assignments_route` → `_assignment_slots` (`:21900`) serves the
     stored strings unchanged (`:21926` `original_username`, `:21928`
     `owner_username`, assembled at `:22184`).
  6. `mobile/src/api/pickAssignment.ts:78` / `:80` type them as
     `original_username: string` / `owner_username: string`.
  7. `mobile/src/screens/PickAssignmentScreen.tsx:1324` renders
     `{slot.owner_username}` verbatim (and `:1328` renders
     `from {slot.original_username}`). The owner picker's team names
     (`:389`) and the optimistic PUT row (`:465`, via `teamNameOf` `:401`)
     come from the same server `original_username`, so the optimistic guess
     (`Team <slot>`) now matches what the PUT stores.
- [ ] **Manual TestFlight checklist:** not needed. The client renders the
  server string verbatim, and pytest pins the stored value.
- [ ] **WAIVED:** n/a.
- `testID`s added/renamed: none.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` (any route added/renamed/removed/contract-changed) | n/a | No route or contract change. `owner_username` is still a string. |
| `living-memory/LLD.md` (schema/route/invariant *conventions* shifted) | n/a | No convention shift. The fix follows the existing #289 "drop empty names" rule. |
| `docs/architecture.md` (module wiring / data flow changed) | n/a | No wiring or data-flow change. |
| `living-memory/HLD.md` (architecture genuinely shifted: new module, client, major flow) | n/a | No architecture change. |
| `docs/cross-client-invariants.md` (shared constants/enums/colors) | n/a | No shared constant or enum. |
| `docs/glossary.md` (new domain term) | n/a | No new term. |
| ADR or `DECISIONS.md` entry (non-obvious choice made) | n/a | No new choice. Open PR #452's data-dictionary text already describes the writers' fallback as `Team <slot>`, and this fix makes the assignment writers match it. |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` + `maestro-testid-lint`,
  all passing on the pushed sha.
- **Evidence recorded:** the `living-memory/TEST_LEDGER.md` entry is written
  by release-lead at merge (living-memory is release-lead's).
- **TestFlight verification:** none (no checklist in §3).
- Express lane declared by the operator? No.
