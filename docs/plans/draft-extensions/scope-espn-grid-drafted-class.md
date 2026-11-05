# Feature Scope — ESPN pick grid starts at the next class once the rookie draft is past (C5)

**Date:** 2026-10-28
**Entry point:** C5 from Product's pre-launch review, via head-eng 2026-10-27; scope (a) approved by head-eng 2026-10-28 (Product agreed the rule 2026-10-27)
**Builder:** draft-eng → eng-backend / eng-mobile worker
**Operator sign-off on waivers:** not needed (no waivers)

---

## 1. Analytics scope

- [ ] **(a) New events specced:** none.
- [x] **(b) Existing events cover it** — `pick_assignment_changed` (the grid's
  `user_events` audit trail) already records every assignment. This change
  moves which classes the grid shows, so there is no new question to measure.
- [ ] **(c) WAIVED:** n/a, (b) applies.

## 2. Schema & flag scope

- New/changed tables or columns: none. The rule reads the existing
  `leagues.draft_status` / `draft_status_confidence` columns and never writes
  them.
- New/changed feature flags: none. It rides the existing `picks.assign`.
- New env vars / `model_config` keys: none. Rollback is a code revert.
- **Scope (a) only.** The grid hides the spent class. The Draft Room's
  `_assignment_grid` and every priced `load_draft_picks(source=user)` reader
  (calculator, engine, Calibration) are unchanged. Those are follow-up (b).
- **Known gap: an existing grid shows 3 classes until setup is re-saved.**
  A grid seeded before the draft holds 2026–2029, so once the verdict reads
  drafted it shows 2027–2029. The 4th class (2030) is seeded the next time
  someone saves setup (`PickAssignmentScreen.tsx` setup path, which always
  sends `reseed: false`). `progress.total` counts the classes shown
  (`rounds × members × classes`, P2-1), so the progress line reads 48 of 48
  until then and 64 of 64 after, and the Draft Room offers "Edit the draft
  picks", not "Continue assigning". An automatic top-up is a named
  follow-up. The setup entry point stays reachable on a drafted grid because
  commit 2 moves the "change" link to the first visible tab (see §3).
- **Fielded builds** without commit 2 infer the league season from
  `seasons[0]`. On a drafted league they treat 2027 as current, so the 2027
  tab shows positions ("1.08") instead of round ordinals until users update.
  The "change" link still shows on that tab, so setup stays reachable there.
- **Seeder fix carried in this change.** `seed_pick_grid` re-inserts kept
  rows, which come back from the DB with their surrogate `id`, alongside new
  rows that have none. SQLAlchemy then refuses the bulk INSERT with "a value
  is required for bind parameter 'id'". That already failed on `origin/main`
  for any re-save that adds rows without `reseed` (more rounds, a new member).
  C5's re-save is exactly that case, so the seeder now drops `id` from every
  row before the replace. The DELETE has already freed every id, nothing
  reads `draft_picks.id` across reseeds, and the served grid doesn't include
  it.
- **Any positive drafted verdict moves the grid, at any confidence.**
  `draft_status.current_year_picks_visible` (through
  `_current_season_picks_visible`) returns False for any `drafted` status,
  whatever the confidence, so a drafted/LOW verdict would move the grid too.
  No writer produces drafted/LOW today: the detector writes `drafted` only at
  MEDIUM or HIGH (`backend/draft_status.py:284`, `:362`, `:365`, `:374`,
  `:430`, `:432`, `:436`), and LOW only comes with `unknown`. The predicate is
  shared and was left unchanged, not forked.
- **Known gaps from release-lead's QA (2026-11-01).** Line numbers are on
  this branch after the main merge.
  - **(a) The "another season's row" guard can't fire from a route.**
    `_assignment_first_season` keeps `season` when the leagues row is for
    another season, but `_assignment_league` (`backend/server.py:23004`)
    takes `season` from that same row. And `leagues.season` is never
    refreshed after the first link: `upsert_espn_league` writes it on insert
    (`backend/database.py:15155`), and its re-link update refreshes
    `espn_season` (`:15178`) but not `season`. So after the 2027 rookie
    draft the row still says 2026 with a drafted verdict, and the grid keeps
    showing the spent 2027 class. This is a pre-existing seam. It needs a
    follow-up before the 2027 draft.
  - **(b) The ESPN heuristic can read drafted from waiver pickups.** ESPN's
    verdict is the rookies-on-rosters heuristic alone (`detect` →
    `_fall_back`, `backend/draft_status.py:469`). It reads drafted/MEDIUM
    once ≥ N rookies sit on ≥ N/2 teams (`:284`), and waiver pickups before
    an off-platform rookie draft can cross that bar. That hides the 2026
    class with no recourse in the app. It isn't live until May 2027; revisit
    before then.
  - **(c) "Hidden, not deleted" has two exceptions.** `seed_pick_grid`'s
    carry box is bounded (`backend/database.py:13200`–`:13207`):
    - lowering `rounds` on a drafted league deletes the hidden 2026 rows for
      the dropped rounds (the round bound, `:13207`, applies to carried
      rows too);
    - a re-save after a flip back to not-drafted drops the extra 2030 class,
      which is outside the season box (`:13200`, `:13205`) once
      `first_season` is 2026 again.
  - **(d) Pick-correction links dead-end for spent 2026 picks.**
    `openPickCorrection(..., 2026)` (`mobile/src/components/MemberEnteredMarker.tsx:69`)
    names a pick and season the grid no longer shows, so the screen falls
    back to the first tab, 2027 (`mobile/src/screens/PickAssignmentScreen.tsx:361`),
    and a PUT on that pick would get `404 pick_not_found`. The links come
    from the priced readers, which still surface 2026 picks, so this folds
    into follow-up (b), the priced-reads cleanup.
  - **(e) Old binaries show positions ("1.08") on 2027.** Cosmetic, and
    already listed above under "Fielded builds".

## 3. Evidence scope

- [x] **Structural guard:** new `mobile/tests/check-pick-assignment-season.js`
  (`npm run test:pick-assignment-season`). It pins (1) `PickAssignments`
  declares `current_season?: number`; (2) the screen's one `currentSeason`
  declaration reads `data.current_season` first; (3) the
  `pick-assignment.edit-order` link's gate is
  `season?.season === data.seasons[0]?.season` and does not reference
  `isFutureSeasonTab`; (4) that link's `Pressable` carries `hitSlop` (the
  44pt touch floor from the design review). It is labeled honestly (G-035):
  it proves the wiring is present, not runtime behavior.

  | Guard sabotage | Result |
  |---|---|
  | g1: revert `currentSeason` to `data.seasons[0]?.season ?? null` | red (1 of 8 checks) |
  | g2: restore the old `!isFutureSeasonTab` gate | red (2 of 8) |
  | g3: drop `current_season` from the type | red (1 of 8) |
  | g4: remove the edit-order `hitSlop` | red (1 of 8) |
  | restored (`cmp`-identical to the fixed copies) | green (8 of 8) |

- [x] **Unit tests:** new `backend/tests/test_pick_assignment_drafted_class.py`,
  20 cases (13 C5 + 7 P2-1). It uses the real routes and an in-memory SQLite DB, and sets the
  verdict with the real setter `set_league_draft_status`, the writer
  `_refresh_league_draft_status` persists through.

  | Test | Pins | Result |
  |---|---|---|
  | D1 `not_drafted`/high · D2 `unknown`/low · D3 never checked (NULL) · D3 `not_drafted`/low | GET seasons 2026–2029, `current_season == 2026`, whole payload equal to the pre-verdict payload | pass ×4 |
  | D3 no leagues row | same, via the session league | pass |
  | helper fail-safes | drafted moves only the verdict's own season; a DB error keeps `season` | pass |
  | D4 drafted, grid seeded 2026–2029 | GET shows 2027–2029, `current_season == 2026`, progress 48 of 48 (P2-1; was 48 of 64), 2027–2029 slots served exactly as before, 2026 rows still stored | pass |
  | D5 drafted, re-save order (no reseed) | seasons 2027–2030; 2027–2029 rows byte-identical (an edit included); all 16 2026 rows still exist verbatim (an edit included) | pass |
  | D5 pricing | 2030 rows: `pool_value == pick_pool_value(rnd, 4, fmt)` and `pick_value == compute_pick_value(rnd, 2030, 2026, teams)`, with a check that the decay really differs between years_out 4 and 3 | pass |
  | D6 drafted, fresh league | the order route seeds 2027–2030 only, priced with years_out = season − 2026 | pass |
  | D7 drafted | PUT on a 2026 pick returns `404 pick_not_found`, the row is unchanged and no event fires; PUT on a 2027 pick succeeds | pass |
  | D8 flip back to `not_drafted` after D5 | GET shows 2026–2030 and the edited 2026 slot reappears as stored | pass |
  | seeder kept + new rows | a non-drafted re-save from 2 rounds to 4 writes, and kept rows are unchanged | pass |
  | P2-1 drafted, not re-saved | GET 2027–2029 reads 48 of 48; a 2027 PUT's progress reads 48 of 48 | pass (red before P2-1: 48 of 64) |
  | P2-1 drafted, re-saved | order response and GET read 64 of 64 | pass (green before too) |
  | P2-1 flip back with 2030 present | GET 2026–2030 reads 80 of 80 | pass (red before: 80 of 64) |
  | P2-1 new member, no re-seed ×2 | not drafted: 64 of 80; drafted: 48 of 60; `assigned < total` both | pass (drafted red before: 48 of 80) |
  | P2-1 unseeded ×2 (never checked, drafted) | `seeded` false, no seasons, 0 of 64 | pass (green before too) |

  **Sabotage** (one at a time, each restored and `cmp`-verified):

  | Step | Red | Green | Red tests |
  |---|---|---|---|
  | s1 `_assignment_first_season` always returns `season` | 7 | 6 | helper, D4, D5 ×2, D6, D7, D8 (every drafted-side test) |
  | s2 carry-box extension removed | 2 | 11 | D5 (2026 rows gone), D8 |
  | s3 PUT refusal removed | 1 | 12 | D7 |
  | s4 `current_season=first` into the seeder | 4 | 9 | D5 pricing (372.5 vs 316.6), D6 pricing (606.5 vs 515.6); also D5 rows and D8, because the carry range `[current_season, first)` goes empty |
  | s5 seeder `id` strip removed | 4 | 9 | D5 ×2, D8, seeder kept + new rows (the bulk INSERT error) |
  | s6 P2-1: `total` back to the fixed 4-class window | 4 | 16 | D4, P2-1 not re-saved, P2-1 flip back, P2-1 new member (drafted) |

  Existing tests touched: `test_espn_draft_order.py::test_espn_being_down_leaves_the_board_working`
  pinned the GET payload's exact key set and now includes the additive
  `current_season`. No other test asserted the always-current-season grid.
  `test_pick_assignment.py::test_w3_07` still asserts 2026–2029, because its
  verdict is NULL. P2-1 changed one C5 assert: D4 had pinned 48 of 64 and now
  pins 48 of 48. Every assert of `total` on a full 4-class grid (D1–D3, D5,
  `test_pick_assignment.py:589`) is unchanged and passes.
- [x] **Code-walk proof** (line numbers on `fix/espn-grid-drafted-class` at
  `95fe8190`, before the main merge; the merge shifted `server.py` and
  `database.py` down by 500–650 lines):
  1. Verdict. `backend/server.py:23935` `_refresh_league_draft_status` →
     `_detect_league_draft_status` (`:23834`) → `draft_status.detect`
     (`backend/draft_status.py:453`). For ESPN that is the rookies-on-rosters
     heuristic alone, which tops out at `drafted`/MEDIUM (`:284`). The
     verdict is persisted by `set_league_draft_status`
     (`backend/server.py:23963` → `backend/database.py:11867`).
  2. Read. `backend/server.py:22385` `_assignment_first_season` reads
     `get_league_draft_context` (`backend/database.py:11887`). It returns
     `season + 1` (`:22405`) only when the row's season matches and
     `_current_season_picks_visible` (`:13848` → `draft_status.py:236`) is
     False. Every other path, including an exception, returns `season`.
  3. GET. `pick_assignments_route` (`:22414`) passes the result as
     `first_season` (`:22454`) to `_assignment_slots` (`:22131`), which drops
     rows with `season < first_season` (`:22146`). `seasons[]` is built from
     those slots. `current_season` is added at `:22456`.
  4. PUT. `pick_assignment_put_route` (`:22481`) computes `first` (`:22533`)
     and returns `404 pick_not_found` for a prior row of an earlier season
     (`:22534`), before `assign_draft_pick`. The 409 lookup (`:22548`) and
     the success payload (`:22566`) use the same `first_season`.
  5. Order. `pick_assignments_order_route` (`:22575`) computes `first`
     (`:22656`) and passes `first_season=first` (`:22661`) with
     `current_season=int(season)` unchanged. The payload's slots use the
     same filter (`:22669`).
  6. Seeder. `backend/database.py:12533` `seed_pick_grid`. `first`
     (`:12615`) drives `seasons` (`:12616`). Pricing stays on
     `current_season`: `years_out = season - current_season` (`:12622`),
     `compute_pick_value(rnd, season, current_season, teams)` (`:12650`) and
     `pick_pool_value(rnd, years_out, fmt)` (`:12651`). The carry box adds
     `[current_season, first)` (`:12666`), so spent rows survive the
     `replace_draft_picks` (`:12684`). The `id` strip is at `:12683`.
  7. Mobile. `mobile/src/api/pickAssignment.ts:125` types `current_season`.
     `mobile/src/screens/PickAssignmentScreen.tsx:664` reads it first, so
     `isFutureSeasonTab` (`:665`) and `slotDisplayLabel` (`:207`) treat 2027
     as a future class and render "1st"/"2nd". The default tab is the first
     visible season (`:377`). The "change" link (`:703`–`:706`) gates on the
     first visible tab, so it opens setup (`:627`), whose save sends
     `reseed: false` (`:544`) and seeds 2030 on a drafted league.
  8. `npx tsc --noEmit` was not run locally: there is no `mobile/node_modules`
     in this worktree or the main checkout (G-022). CI's `mobile-typecheck`
     runs it, along with every `check-*.js` guard. Run 2026-11-01 after the
     main merge, with `node_modules` linked: `tsc --noEmit` clean, all 136
     `check-*.js` suites green, `testid-lint.sh` OK.
- [x] **Manual TestFlight checklist.** Run on an ESPN league whose 2026 rookie
  draft is done, after the backend deploy and a build that includes commit 2.
  - **Precondition for steps 1–4.** Before the run, release-lead confirms
    `leagues.draft_status = 'drafted'` for the test league with a read-only
    prod read, which needs the operator's word first. If the row isn't
    `drafted`, the grid is unchanged by design and steps 1–4 prove nothing.
  - **Steps 3–4, S2 and S4 are real writes** to the league's shared grid.
    Leaguemates will see them.
  - **Steps 1–4 also check two progress readouts:** the grid's progress line,
    and the Draft Room's assignment row (`draft-room.assign-progress`), which
    must read "Edit the draft picks", not "Continue assigning". The figures
    assume P2-1 (commit B) ships and no member has joined since the grid was
    seeded: the two numbers are equal, rounds × teams × the classes shown
    (the 4-team test league reads 48 of 48 for 3 classes, 64 of 64 for 4).
    Without P2-1 they read one class short (48 of 64), and the Draft Room
    says "Continue assigning".

  1. League → Pick assignments: there is no 2026 tab, the first tab is 2027,
     and the tabs run 2027–2029. Progress reads 3 classes, both numbers
     equal (e.g. 144 of 144 for 4 rounds × 12 teams). Draft Room row: "Edit
     the draft picks".
  2. 2027 tab: slot labels read "1st", "2nd", …, never positions like "1.08".
     Progress and the Draft Room row are as in step 1.
  3. On the 2027 tab, tap the "N rounds · Linear/Snake order — change" link
     and save the order unchanged. A 2030 tab appears, and 2027–2029
     assignments are unchanged. Progress reads 4 classes, both numbers equal
     (e.g. 192 of 192). Draft Room row: "Edit the draft picks".
  4. Reassign one 2027 pick: it saves and the new owner shows. Progress
     numbers stay equal (only the "· N traded" count may move). Draft Room
     row: "Edit the draft picks".
  5. *Not runnable in November* (there's no ESPN league whose 2026 rookie
     draft is still ahead); covered by D1–D3 and the guard. A league whose
     draft isn't done (or a Sleeper/MFL league) is unchanged.
  6. *Not runnable in November,* for the same reason; covered by D1–D3 and
     guard check 3. On a league whose draft isn't done, the "change" link
     shows only on the current-season (2026) tab and not on the 2027–2029
     tabs.

  **Seeder fix (the PR's separate QA item).** Run after step 3, so the raise
  doesn't also seed 2030 and blur step 3.
  - S1. Before saving, note one traded or reassigned pick (season, round,
    original team, owner), e.g. the step 4 pick.
  - S2. Open the "change" link, raise rounds by one (4 → 5) and save. It
    saves without an error, and round 5 appears on every visible tab
    (2027–2030). The hidden 2026 class gets no round 5, since it isn't
    generated.
  - S3. The S1 pick and every other existing assignment are unchanged.
  - S4. Restore rounds 5 → 4 and save. This deletes round 5 on every
    visible class, including any round-5 reassignment made in between. Lowering rounds
    also deletes hidden 2026 rows for any dropped round the class had, as in
    §2 (c). Here 2026 never had a round 5, so no 2026 row goes; a drop below
    the original 4 would delete them.
- [ ] **WAIVED:** n/a.
- `testID`s added/renamed: none. `pick-assignment.edit-order` is unchanged;
  only its gate moved.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` (any route added/renamed/removed/contract-changed) | updated | The three `/api/league/pick-assignments` rows. GET: `seasons[]` starts at season + 1 once the rookie draft reads drafted, and the additive `current_season`. PUT: a pick of the drafted class → `404 pick_not_found`. Order: seeds from season + 1 when drafted, pricing stays relative to the league season, and spent-class rows are kept. |
| `living-memory/LLD.md` (schema/route/invariant *conventions* shifted) | n/a | No convention shift. It reuses the shared `current_year_picks_visible` fail-safe. |
| `docs/architecture.md` (module wiring / data flow changed) | n/a | No wiring change. One helper inside the existing pick-assignment block. |
| `living-memory/HLD.md` (architecture genuinely shifted: new module, client, major flow) | n/a | No architecture change. |
| `docs/cross-client-invariants.md` (shared constants/enums/colors) | n/a | No shared constant or enum. `current_season` is a plain int. |
| `docs/glossary.md` (new domain term) | n/a | No new term. |
| ADR or `DECISIONS.md` entry (non-obvious choice made) | n/a | Head-eng's C5 approval records the decision. living-memory belongs to release-lead. |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` (which also runs the
  `check-*.js` suites) + `maestro-testid-lint`, all passing on the pushed sha.
- **Evidence recorded:** release-lead writes the `living-memory/TEST_LEDGER.md`
  entry at merge (living-memory is release-lead's).
- **TestFlight verification:** required. The operator runs the §3 checklist,
  and the outcome is logged in TEST_LEDGER.
- Before ship, release-lead may take a read-only prod read of ESPN rows'
  `draft_status` / `draft_status_confidence` to see how many grids flip.
- Express lane declared by the operator? No.
