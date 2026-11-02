# Feature Scope — Pick-assignment grid never stores a user id as a name

**Date:** 2026-10-27 (read-time guard added 2026-11-02, after release-lead's
QA P2)
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
- **Existing stored rows are healed at READ time, not repaired.** Rows
  written before this fix hold `Team <user_id>` (e.g. `Team espn:{1A2B…}`)
  or a whitespace-only name. The first version of this doc (and the PR
  body) said such a row keeps its string only "until the slot is reassigned
  or the grid reseeds". That was wrong. Nothing short of a reseed rewrites
  them, and a reseed costs the league its reassignments:
  - a PUT rewrites only `owner_username`;
  - `original_username` changes only on a reseed (`POST …/order` with
    `reseed: true`; without it `seed_pick_grid` keeps every row verbatim);
  - and a reseed drops every recorded reassignment.

  So every client-facing reader now goes through one helper,
  `database.pick_team_name`. A user-source name that is blank or equals
  `Team <that side's user id>` (`original_user_id` for `original_username`,
  `owner_user_id` for `owner_username`) is served as the writers' own
  fallback, `database.pick_slot_team_name`: `Team <original_roster_id>`, else
  `Unnamed team`. The PUT writer (`_assignment_owner_name`) calls the same
  fallback, so a healed read and a fresh write give the same label. Real
  names, a name that only starts with "Team " ("Team Rocket"), a correct
  `Team <slot>` and every platform row pass through. No stored row is
  written.
- **A stored-row backfill is optional, later.** QA wrote and tested one:
  two `UPDATE`s with the same predicate, and the same replacement wherever
  the row has a slot; the script re-runs them as an idempotency check. It is
  kept outside the repo at
  `/private/tmp/claude-501/-Users-teresadickens-ftf-worktrees-org-bringup/135a9db8-c179-41b9-87b1-9e387fd97f20/scratchpad/qa497/tools/backfill497.py`.
  It would be a prod write, so it needs the operator's word. The read-time
  guard makes it cosmetic: it would only make the stored strings match what
  is already served.

## 3. Evidence scope

- [ ] **Structural guard:** none. No mobile change.
- [x] **Unit tests:** new `backend/tests/test_pick_assignment_names.py`, 16
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

  T5-T9 (the read-time guard) seed a 1-round grid, then write the pre-fix
  shapes straight into `draft_picks` (`_write_legacy`): SWID's rows named
  `Team espn:{1A2B3C4D-SWID}` on both sides, the acct member's rows `"   "`
  on both sides, and four traded rows (two carrying a pre-fix owner name,
  two a pre-fix original name).

  | Test | Pins | Result |
  |---|---|---|
  | T5 `test_t5_get_heals_pre_fix_names_on_both_sides` | GET: all 16 slots serve `Team <slot>` / the real name on both sides, no id, no blank; the stored rows still hold the pre-fix strings (no write) | pass |
  | T6 `test_t6_put_responses_are_healed` | PUT 409 `current` row healed on both sides; PUT 200 `slot` serves the new owner's name and the healed original, while the stored `original_username` keeps the id (a PUT does not repair it) | pass |
  | T7 `test_t7_draft_room_grid_is_healed` | `GET /api/draft/board` (ESPN): every `order[]` row healed on both sides | pass |
  | T8a `test_t8a_calculator_pick_labels_and_names_are_healed` | `picks.assign_tradeable` on: `/api/league/picks` labels read `(from Team <slot>)`, and its raw `original_username` / `owner_username` are healed | pass |
  | T8b `test_t8b_generated_suggestion_pick_labels_are_healed` | the engine's pick assets (`_owned_pick_assets`, the trade-card name) | pass |
  | T8c `test_t8c_matches_pick_labels_are_healed` | the Matches overlay (`_pick_labels_by_id`) | pass |
  | T8d `test_t8d_calibration_pick_labels_are_healed` | Calibration's catalog (`blind_grading._league_inputs`) | pass |
  | T9 `test_t9_good_stored_names_pass_through` ×3 (real name, "Team Rocket", the correct `Team <slot>`) | served verbatim. The fallback is swapped for a sentinel, so a pass-through and a heal that yields the same string can't be confused | pass |

  **Sabotage:**

  | Step | Red | Green | Red tests |
  |---|---|---|---|
  | Fix 1 reverted alone (`_assignment_members` back to `… or f"Team {uid}"`) | 5 | 1 | T1, T2 ×2, T3 ×2 (T2/T3 also go red because the old dict maps every member, including whitespace names) |
  | Fix 1 restored, fix 2 reverted alone (PUT back to `names.get(owner, f"Team {owner}")`) | 4 | 2 | T2 ×2, T3 ×2 |
  | Both restored | 0 | 6 | none |

  Read-time guard sabotage (2026-11-02): each reader's guard removed alone
  (back to the raw stored field), run against `test_pick_assignment_names`
  + `test_pick_assignment` + `test_pick_assignment_tradeable` (89 tests),
  then restored (`git diff --exit-code` clean):

  | Guard removed | Red | Red tests |
  |---|---|---|
  | `_assignment_slots` original side | 5 | T5, T6, T9 ×3 (T9's sentinel check sees the whitespace rows unhealed) |
  | `_assignment_slots` owner side | 2 | T5, T6 |
  | `_assignment_grid` owner side | 1 | T7 |
  | `_assignment_grid` original side | 1 | T7 |
  | `_owned_pick_label` | 3 | T8a, T8b, T8c |
  | `_pick_labels_by_id` (drop the `source` / `original_user_id` keys) | 1 | T8c |
  | `/api/league/picks` raw name fields | 1 | T8a |
  | `blind_grading._league_inputs` | 1 | T8d |
  | predicate over-broad (`startswith("Team ")`) | 2 | T9 team-rocket, T9 team-slot |
  | predicate without the `Team <uid>` clause | 7 | T5, T6, T7, T8a-d |
  | all restored | 0 | none |

  Area suites (2026-11-02, after the main merge): `test_pick_assignment_names`
  16, `test_pick_assignment` 36, `test_pick_assignment_tradeable` 37,
  `test_draft_board` 67, `test_mock_pick_ownership` 16,
  `test_pick_labels_in_matches` 16, `test_pick_slot_labels` 28,
  `test_seed_ui_test_db` 76: **292 passed**. No existing test asserted the
  old `Team <uid>` fallback. Their `Team u1`-style strings are stored
  usernames, not fallbacks.
- [x] **Code-walk proof** (steps 1-7: line numbers on
  `fix/pick-grid-name-fallback` at `28da8395`, before the main merge):
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
     `pick_assignments_route` → `_assignment_slots` (`:21900`) served the
     stored strings unchanged (`:21926` `original_username`, `:21928`
     `owner_username`, assembled at `:22184`). Step 8 adds the read-time
     guard there.
  6. `mobile/src/api/pickAssignment.ts:78` / `:80` type them as
     `original_username: string` / `owner_username: string`.
  7. `mobile/src/screens/PickAssignmentScreen.tsx:1324` renders
     `{slot.owner_username}` verbatim (and `:1328` renders
     `from {slot.original_username}`). The owner picker's team names
     (`:389`) and the optimistic PUT row (`:465`, via `teamNameOf` `:401`)
     come from the same server `original_username`, so the optimistic guess
     (`Team <slot>`) now matches what the PUT stores.

  The read-time guard (line numbers after the main merge):

  8. `backend/database.py:13344` `pick_team_name(row, side, rows)` returns
     the stored `<side>_username` unless the row is user-source and the name
     is blank or equals `Team <row's <side>_user_id>`. Then it returns
     `pick_slot_team_name` (`:13330`): `Team <original_roster_id>` of the
     row itself for the original side, or of any row in `rows` the owner
     originally owns for the owner side, else `Unnamed team`.
  9. The PUT writer's fallback is the same function:
     `backend/server.py:22763` `_assignment_owner_name` →
     `pick_slot_team_name(rows, owner)`.
  10. Readers that go through the guard:
      - `_assignment_slots` `backend/server.py:22815` / `:22817`, which
        serves the GET, the PUT 200 `slot` and 409 `current`, and the
        `POST …/order` payload;
      - `_assignment_grid` `:23009` / `:23011`, which serves the ESPN Draft
        Room's `order[]` (the mock draft reads only its owner ids);
      - `_owned_pick_label` `:18775`, the "(from …)" suffix on every
        owned-pick label (trade-card pick assets, eveners, power rankings,
        `/api/league/picks`);
      - `_pick_labels_by_id` `:18845` / `:18861`, the Matches overlay, which
        now selects `source` + `original_user_id`;
      - `get_league_picks` `:18732` / `:18733`, the raw name fields it
        spreads;
      - Calibration: `backend/blind_grading.py:492`, in `_league_inputs`.
        The module never imports `backend.server`, which is why the helper
        lives in `database.py`.
- [ ] **Manual TestFlight checklist:** not needed. The client renders the
  server string verbatim, and pytest pins the stored value.
- [ ] **WAIVED:** n/a.
- `testID`s added/renamed: none.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` (any route added/renamed/removed/contract-changed) | updated | § Pick assignment: one paragraph above the routes table says the served `original_username` / `owner_username` are never a user id, and that pre-fix rows are healed at read time. No route added; `owner_username` is still a string. |
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

## 6. Known gaps

1. **The mobile setup step can still show an id or a blank row.** It labels
   members `m.display_name || m.username || m.user_id`
   (`mobile/src/screens/PickAssignmentScreen.tsx:642`), so a nameless member
   shows their id, and a whitespace-only name shows a blank row. It reads
   member names, not stored pick names, so the server guard can't reach it.
   The fix is a binary change, not in this PR.
2. **P3: "Unnamed team" stays after the member gets a slot.** A slot PUT to a
   member added after seeding stores `Unnamed team`. A later reseed (#510)
   gives that member `Team 7` on their own rows, but the reassigned slot
   keeps `Unnamed team`: it isn't blank and isn't `Team <user id>`, so the
   guard passes it through. Only reachable through the API, since the app
   only offers seeded members.
3. **Readers left unguarded on purpose** (none serves an asserted row's
   stored name to a client):
   - `backend/accounts.py:1375` exports the user's own `assigned_by` rows
     verbatim. That's a data export, and each row already carries the raw
     `owner_user_id` / `original_user_id`.
   - `backend/overhaul_service.py:230` (`holder_username`) and
     `backend/overhaul_api.py:472` read platform rows only
     (`overhaul_api.py:141`).
   - `backend/win_now_service.py:350` reads platform rows only (`:337`).
   - `backend/eval/value_core_bench.py:253` and
     `backend/eval/fit_scorecard_test.py:56` are offline eval tools.
