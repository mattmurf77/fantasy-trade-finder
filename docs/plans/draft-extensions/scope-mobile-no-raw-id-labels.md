# Feature Scope — mobile: a team label is never a member id

**Date:** 2026-11-03
**Entry point:** direct ask: head-eng ("a raw user id must not be shown to leaguemates") via draft-eng, for the 2026-11-06 binary freeze
**Builder:** eng-mobile worker for draft-eng, branch `fix/mobile-no-raw-id-labels`
**Operator sign-off on waivers:** one waiver (§1 analytics), set by draft-eng's brief. Surfaced in the hand-off report.

Companion to #497 (`fix/pick-grid-name-fallback`, [scope](scope-pick-grid-name-fallback.md)), which stops the **server** storing or serving a user id as a team name. This change fixes the **client's** own fallbacks, which no server fix reaches. No backend change.

## The defect

When the server sent no name, three screens rendered the member id itself:

| Screen | Old expression | What a leaguemate saw |
|---|---|---|
| `PickAssignmentScreen` setup list | `m.display_name \|\| m.username \|\| m.user_id` | `espn:{SWID}`, `espn:<lid>.t7`, `acct_…` |
| `DraftRoomScreen` board owner cell | `slot.owner_username ?? slot.owner_user_id ?? 'Unassigned'` | the id, or a blank row (`??` lets `""` and `"  "` through) |
| `MockDraftScreen` `ownerNameOf` | MFL → `Team <fid>`; every other id returned raw | `espn:…`, `acct_…`, or `""` |

## The fix

One helper, `mobile/src/utils/teamLabel.ts`, called by all three sites. `teamLabel(names, userId, slot)` returns:

1. the first candidate that is a real name, trimmed. A blank, a whitespace-only string, a minted id (`espn:`, `mfl:`, `acct_`, also after a space, so a stored `Team espn:{…}` is caught), the member's own id and `Team <their id>` are not names;
2. else `Team <fid>` for an MFL id (unchanged convention, zero-padding kept);
3. else `Team <slot>`;
4. else `Unnamed team`.

Steps 3 and 4 are the labels the server writes (#497, `database.pick_slot_team_name`). No other copy is added.

### The slot, per screen

| Screen | Slot source | Why |
|---|---|---|
| Draft Room | `slot` of an order row whose `original_user_id` is the owner (`ownSlotByUser`) | `slot` is the ORIGINAL owner's slot, so a traded row's `slot` belongs to the team that traded it away. The owner's own slot is read off a row they originally hold. No such row → `Unnamed team`. |
| PickAssignment setup | `assignmentSlots(settings.order + member ids, grid rows)` | `GET /api/league/members` carries no roster or slot number (`backend/server.py:26906`). So: a real name, then the seeded grid's server-healed name (`teamNameOf`), then `Team <slot>`. A member already on the grid keeps their `original_roster_id`. Everyone else gets the next free integer, walking the server's round-1 order (`settings.order`: the stored order, else the server's user-id-sorted default). This is `seed_pick_grid`'s own rule (`backend/database.py:13117-13133`), duplicated deliberately. Labels are distinct by construction, including a newcomer joining a seeded grid, which a plain list index would not guarantee. They come from server data only, so a label never moves with a drag. |
| Mock Draft | `slot` of a row the owner holds that was **not** traded to them (`ownSlotOf`) | In the mock payload `original_user_id` always equals `owner_user_id` (`backend/mock_draft_service.py:1392-1395`), so the Draft Room rule cannot be used here. A non-traded row's `slot` is that team's own position (`owner_of`: `order[slot-1]`). |

### D-16 (Mock Draft's Sleeper path)

The `ownerNameOf` comment cited D-16 for leaving non-MFL ids alone, because "a Sleeper roster id is a number the user has at least seen before". D-16 is the #289 batch-plan decision ([batch-plan.md](../../feedback/items/289-mfl-draft-room-ids/batch-plan.md), [LLD §5](../../feedback/items/290-mock-draft-engine/lld-delta.md)). It is not `living-memory/DECISIONS.md` D-016, which is an unrelated model-gate decision.

**Finding: the value is a Sleeper USER id, not a roster or slot number.** The mock's owners are `str(m.user_id)` of the session league members plus the caller (`backend/server.py:23636-23658`, `_mock_owner_ids`). `order[].owner_user_id` is that owner (`mock_draft_service.py:1392`). On Sleeper that is a long numeric account id the user has never seen. As briefed, this change **does not override D-16**: an all-digit id with no real name still renders the id (`MockDraftScreen.tsx:1208`). The guard pins this as the single raw-id return, so widening it goes red. Every other id shape (`espn:`, `acct_`, a blank, an unknown shape) now goes through the helper. Whether the Sleeper path should also become `Team <slot>` is draft-eng's / D-16's owner's call.

## 1. Analytics scope

- [ ] (a) New events specced — no
- [ ] (b) Existing events cover it — no
- [x] **(c) WAIVED — no analytics needed because:** a label-copy fix. No new surface, interaction or decision point to measure, and the brief sets analytics to none.

## 2. Schema & flag scope

- New/changed tables or columns: none
- New/changed feature flags: none. The three surfaces keep their existing gates (`picks.assign`, `draft.tab`, `draft.mock`)
- New env vars / `model_config` keys: none

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-no-raw-id-labels.js` (`npm run test:no-raw-id-labels`). 32 checks, all PASS:
  - §1 the helper: zero runtime imports, transpiled and **executed**:
    - a real name trimmed;
    - blank or whitespace → `Team <slot>`, or `Unnamed team` with no slot;
    - an ESPN / acct_ / MFL id never returned across an id × name × slot matrix;
    - MFL `Team 0003`;
    - `assignmentSlots` distinct, seeded and unseeded.
  - §2–§4 each call site's own expression, cut out of the screen and **executed**:
    - PickAssignment's `setupMembers` memo: distinct labels with no id, seeded and unseeded;
    - the Draft Room owner cell plus `ownSlotByUser`: own slot rather than the traded row's, and `Unassigned` only with no owner;
    - MockDraft's `ownerNameOf` and `ownSlotOf`.
  - Plus the negative pins: no `|| m.user_id`, no `?? slot.owner_user_id`, and the one D-16 raw-id return.
  - §5 single source: `'Unnamed team'` and the MFL regex live only in the helper.
- [x] **Existing guard updated:** `check-mock-lifecycle.js` §5 lifts `ownerNameOf` as before, now handing it the helper (the MFL regex moved there). All its D-16 cases are unchanged; one case's description now says "Sleeper USER id" instead of "roster id".
- [x] **Unit tests:** there is no JS unit-test harness in `mobile/`. The helper's unit cases run inside the guard (§1). Backend: none, as there is no backend change.
- [x] **Sabotage** (each call site reverted to its old fallback, guard run, file restored, `git diff --exit-code` clean):

  | Sabotage | `check-no-raw-id-labels` | `check-mock-lifecycle` |
  |---|---|---|
  | S1 PickAssignment: old `\|\| m.user_id` map | red: 2a, 2b | green (doesn't read the screen) |
  | S2 Draft Room: old `?? owner_user_id ?? 'Unassigned'` | red: 3a, 3b, 3d | green (doesn't read the screen) |
  | S3 MockDraft: old `ownerNameOf` | red: 4b, 4c, 4e, 5b | red: D-16 ladder |
  | S4 MockDraft: D-16 carve-out widened to every id | red: 4c, 4e | red: ladder, `mfl:`, padding |
  | S5 helper returns the user id instead of `Unnamed team` | red: 1f, 1h, 3d, 4e | green |

- [x] **Code-walk proof:**
  1. Helper — `mobile/src/utils/teamLabel.ts:23-31` (`realName`): trims each candidate, skips blank, `MINTED_ID_RE` (`:15`), own id and `Team <id>` (`:28`). `:37-48` (`teamLabel`): name → `Team <fid>` (`:44-45`, regex `:18`) → `Team <slot>` / `Unnamed team` (`:46-47`). Every return is a passed-in name or one of the two shapes.
  2. PickAssignment — `PickAssignmentScreen.tsx:415-431`: the members from `GET /api/league/members?include_self=1` (`:293-305`) are labelled by `teamLabel([display_name, username, teamNameOf(user_id)], user_id, slots.get(user_id))`. `slots` is `assignmentSlots([...settings.order, ...member ids], every season's slots)` (`:418-421`). `:662` passes `setupMembers ?? teams` to `SetupView`, whose drag rows render `item.name` (`:1135-1138`). The slot number column is still `idx + 1`, the drag position. The team label beside it never changes with a drag.
  3. Draft Room — `DraftRoomScreen.tsx:1198-1209`: `ownSlotByUser` maps `original_user_id → slot`, first row wins. `:1243-1249`: an owner id or a non-blank name → `teamLabel([owner_username], owner_user_id, ownSlotByUser.get(owner_user_id))`; neither → `Unassigned`, as before.
  4. Mock Draft — `MockDraftScreen.tsx:509-521` (clock card + ticker) and `:1069-1083` (recap rail) build the owner-name maps through `ownerNameOf(name, id, ownSlotOf(order, id))`. `:1202-1210`: an all-digit id with no real name → the id (D-16, kept); everything else → `teamLabel`. `:1214-1216`: `ownSlotOf` is the slot of a non-traded row the owner holds.
- [x] **Manual TestFlight checklist** (run by the operator on the 11-06 binary):
  1. **Pick setup, ESPN league with ≥2 nameless members** (an ESPN team whose owner has no display name, or an Apple-first `acct_` member): League → Draft picks → the setup step (an unseeded board, or "Edit draft order and rounds" on a seeded one). Expected:
     - every row shows a name or `Team <n>`;
     - no row contains `espn:`, `{`, `acct_`, or is blank;
     - the nameless members show **different** numbers;
     - long-press-drag a nameless row: its `Team <n>` does not change as it moves.
  2. **Draft Room, same league with picks assigned:** Draft tab → the Board. Expected:
     - every owner cell is a name or `Team <n>` / `Unnamed team`, with no `espn:` / `acct_` / blank;
     - a row with no owner still reads `Unassigned`;
     - a traded pick shows the NEW owner's label, followed by "from …".
  3. **Mock draft, same league:** start a mock. Check the on-the-clock line ("· X's pick 1.03"), the ticker's who-column, and the recap rail once it is finished. Expected: no `espn:` / `acct_` / blank owner anywhere, and a nameless owner reads `Team <their round-1 slot>`.
  4. **Regression, Sleeper and MFL mocks:** start a mock in a Sleeper league and in an MFL league. Expected:
     - Sleeper owners show the same names as on the 1.13.x build;
     - an MFL franchise with no member row still reads `Team 0003`-style, zero-padded.
- [ ] **WAIVED because:** n/a
- `testID`s added/renamed: none. `testid-lint OK`.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` (any route added/renamed/removed/contract-changed) | n/a | No route or payload change. The client only reads fields it already read. |
| `living-memory/LLD.md` (schema/route/invariant *conventions* shifted) | n/a | No schema, route or server invariant moved. The client label rule is recorded in `mobile/src/utils/CLAUDE.md`. Living-memory is out of this worker's scope; draft-eng owns the write-back. |
| `docs/architecture.md` (module wiring / data flow changed) | n/a | No backend module or data flow changed. One mobile util added. |
| `living-memory/HLD.md` (architecture genuinely shifted: new module, client, major flow) | n/a | No architecture shift. |
| `docs/cross-client-invariants.md` (shared constants/enums/colors) | n/a | `Team <slot>` / `Unnamed team` are the server's existing labels (#497 documents them in `api-reference.md`). Web and extension do not render these three surfaces. |
| `docs/glossary.md` (new domain term) | n/a | No new term. |
| ADR or `DECISIONS.md` entry (non-obvious choice made) | n/a | No decision taken here. The D-16 Sleeper question is raised for its owner, not decided. The PickAssignment slot rule is recorded in this scope and in `utils/CLAUDE.md`. |

Mobile maps kept in step: `mobile/src/utils/README.md` (row + node-testable list), `mobile/src/utils/CLAUDE.md` (entry), `mobile/tests/README.md` (Draft & mock row), and `docs/plans/README.md` (this folder's row).

## 5. Ship gate declaration

- **CI green** (local, 2026-11-03):
  - `npx tsc --noEmit`: clean;
  - all 136 `tests/check-*.js`, looped as `ci.yml` does: exit 0;
  - `bash scripts/testid-lint.sh`: OK.
- **Evidence recorded:** this scope. The `living-memory/TEST_LEDGER.md` entry is for draft-eng to write; this worker does not write living-memory.
- **TestFlight verification:** §3's four steps, by the operator, on the 11-06 binary.
- Express lane declared by the operator? no

## 6. Known gaps

1. **Server-supplied names elsewhere on the same screens are rendered as sent:**
   - the Draft Room's "from …" (`original_username ?? '—'`) and Your picks' "from …";
   - the PickAssignment grid and its owner picker (`teams`, from `original_username`).

   None of these falls back to an id client-side. #497 heals them server-side for ESPN-asserted rows. Out of this brief's scope.
2. **The Draft Room fallback's number can differ from the grid's.** The client fallback uses the order row's `slot` (the draft position, as briefed). #497's server label uses `original_roster_id`, and after a reorder the two can differ. It shows only when the server sent no usable name: a pre-#497 server, or a platform row with no name.
3. **An unseeded setup label can renumber at save.** On an unseeded board a nameless member's `Team <n>` is their position in the server's order. If the user drags them and saves, the seeder mints `original_roster_id` from the SAVED order (`backend/server.py:23231-23232`), so the board can then read a different `Team <n>`. Keeping labels fixed during the drag was the brief's requirement.
4. **D-16's Sleeper raw-id path is kept** (see above). A nameless Sleeper mock owner still shows a Sleeper user id. That is rare in practice: Sleeper members always carry a username.
5. **Count drift, noted, not fixed:**
   - `mobile/tests/README.md` says 88 guards while 136 exist;
   - `mobile/CLAUDE.md` says 84;
   - this folder's row in `docs/plans/README.md` said 22 with 23 files on main. It is set to 24 here, but #497 and #510 each add a scope file here without bumping it.
