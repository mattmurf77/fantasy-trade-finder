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
  sends `reseed: false`). `progress.total` still counts 4 classes, so the
  progress line reads 48 of 64 until then. An automatic top-up is a named
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
- **The shared predicate ignores confidence.**
  `draft_status.current_year_picks_visible` returns False for any `drafted`
  status, whatever the confidence. That's safe today because the detector
  only writes `drafted` at MEDIUM or HIGH (`backend/draft_status.py:284`,
  `:362`, `:365`, `:374`, `:430`, `:432`, `:436`). LOW only comes with
  `unknown`. The predicate is shared and was left unchanged.

## 3. Evidence scope

- [x] **Structural guard:** new `mobile/tests/check-pick-assignment-season.js`
  (`npm run test:pick-assignment-season`). It pins (1) `PickAssignments`
  declares `current_season?: number`; (2) the screen's one `currentSeason`
  declaration reads `data.current_season` first; (3) the
  `pick-assignment.edit-order` link's gate is
  `season?.season === data.seasons[0]?.season` and does not reference
  `isFutureSeasonTab`. It is labeled honestly (G-035): it proves the wiring
  is present, not runtime behavior.

  | Guard sabotage | Result |
  |---|---|
  | g1: revert `currentSeason` to `data.seasons[0]?.season ?? null` | red (1 of 7 checks) |
  | g2: restore the old `!isFutureSeasonTab` gate | red (2 of 7) |
  | g3: drop `current_season` from the type | red (1 of 7) |
  | restored (`cmp`-identical to the fixed copies) | green (7 of 7) |

- [x] **Unit tests:** new `backend/tests/test_pick_assignment_drafted_class.py`,
  13 cases. It uses the real routes and an in-memory SQLite DB, and sets the
  verdict with the real setter `set_league_draft_status`, the writer
  `_refresh_league_draft_status` persists through.

  | Test | Pins | Result |
  |---|---|---|
  | D1 `not_drafted`/high · D2 `unknown`/low · D3 never checked (NULL) · D3 `not_drafted`/low | GET seasons 2026–2029, `current_season == 2026`, whole payload equal to the pre-verdict payload | pass ×4 |
  | D3 no leagues row | same, via the session league | pass |
  | helper fail-safes | drafted moves only the verdict's own season; a DB error keeps `season` | pass |
  | D4 drafted, grid seeded 2026–2029 | GET shows 2027–2029, `current_season == 2026`, `progress.total` unchanged (64), 2027–2029 slots served exactly as before, 2026 rows still stored | pass |
  | D5 drafted, re-save order (no reseed) | seasons 2027–2030; 2027–2029 rows byte-identical (an edit included); all 16 2026 rows still exist verbatim (an edit included) | pass |
  | D5 pricing | 2030 rows: `pool_value == pick_pool_value(rnd, 4, fmt)` and `pick_value == compute_pick_value(rnd, 2030, 2026, teams)`, with a check that the decay really differs between years_out 4 and 3 | pass |
  | D6 drafted, fresh league | the order route seeds 2027–2030 only, priced with years_out = season − 2026 | pass |
  | D7 drafted | PUT on a 2026 pick returns `404 pick_not_found`, the row is unchanged and no event fires; PUT on a 2027 pick succeeds | pass |
  | D8 flip back to `not_drafted` after D5 | GET shows 2026–2030 and the edited 2026 slot reappears as stored | pass |
  | seeder kept + new rows | a non-drafted re-save from 2 rounds to 4 writes, and kept rows are unchanged | pass |

  **Sabotage** (one at a time, each restored and `cmp`-verified):

  | Step | Red | Green | Red tests |
  |---|---|---|---|
  | s1 `_assignment_first_season` always returns `season` | 7 | 6 | helper, D4, D5 ×2, D6, D7, D8 (every drafted-side test) |
  | s2 carry-box extension removed | 2 | 11 | D5 (2026 rows gone), D8 |
  | s3 PUT refusal removed | 1 | 12 | D7 |
  | s4 `current_season=first` into the seeder | 4 | 9 | D5 pricing (372.5 vs 316.6), D6 pricing (606.5 vs 515.6); also D5 rows and D8, because the carry range `[current_season, first)` goes empty |
  | s5 seeder `id` strip removed | 4 | 9 | D5 ×2, D8, seeder kept + new rows (the bulk INSERT error) |

  Existing tests touched: `test_espn_draft_order.py::test_espn_being_down_leaves_the_board_working`
  pinned the GET payload's exact key set and now includes the additive
  `current_season`. No other test asserted the always-current-season grid.
  `test_pick_assignment.py::test_w3_07` still asserts 2026–2029, because its
  verdict is NULL.
- [x] **Code-walk proof** (line numbers on `fix/espn-grid-drafted-class`):
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
     runs it, along with every `check-*.js` guard.
- [x] **Manual TestFlight checklist.** Run on an ESPN league whose 2026 rookie
  draft is done, after the backend deploy and a build that includes commit 2:
  1. League → Pick assignments: there is no 2026 tab, the first tab is 2027,
     and the tabs run 2027–2029.
  2. 2027 tab: slot labels read "1st", "2nd", …, never positions like "1.08".
  3. On the 2027 tab, tap the "N rounds · Linear/Snake order — change" link
     and save the order unchanged. A 2030 tab appears, and 2027–2029
     assignments are unchanged.
  4. Reassign one 2027 pick: it saves and the new owner shows.
  5. A league whose draft isn't done (or a Sleeper/MFL league) is unchanged.
  6. On a league whose draft isn't done, the "change" link shows only on the
     current-season (2026) tab and not on the 2027–2029 tabs.
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
