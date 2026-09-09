
## Orchestrator rulings 2026-09-08 (Phase 1 exit)

1. New additive 422 `sleeper_pick_untradable` (with `picks[]`, `season_window`, `message == detail`) **approved**: an API contract addition, documented in api-reference/cross-client-invariants per the scope block; fielded build 154 already renders `detail`. Folding into `sleeper_pick_unmapped` rejected as misleading.
2. The exact pick sent at 17:03:52Z is not recoverable without the prod DB (blocked); the public-API evidence (draft complete 2026-08-26, 34 season-2026 rows still in `traded_picks`, sender's only acquired pick a spent 2026 4th) is sufficient for the mechanism. Operator is asked in the ship summary.
3. D-189 (narrowing D-089: when `/drafts` flakes and the cached #207 verdict says drafted, exclude the current season) **adopted** — live read still wins; allocate the id from origin/main at write time.
4. Optional mobile parity branch in SendInSleeperButton: **include** (small, owned by no other group).

## Phase 3 round 1 — 2026-09-08

QA-A FAIL (1 major to adjudicate, 3 minor); QA-B PASS (3 minor). Both suites 5890 passed / 1 skipped; RED-first 16/16 confirmed by both. Convergent finding: `completed_draft_seasons` skips startup-shaped completed drafts (A F-1 / B F-2), whereas the pre-fix sync excluded the current season for ANY completed draft.

**Rulings (Phase 4):** (1) restore shape-blind exclusion — any `complete` draft with season ≥ current excludes that season (a completed startup draft consumes the class too; the old behavior was the tested, safe one); PRD §3 amended, unit test updated, D-189 text amended. (2) B F-1: `check-send-button-platform.js` check 9 must match the `Alert.alert` arguments, not comment text. (3) A F-3: drop the dead `season_window: null` / "?–?" branches and the api-reference `null` note (window is always present when refusing). (4) A F-2 one-sentence D-189 note on confidence; A F-4 / B F-3 accepted as pre-existing or verbatim-spec copy.

## Round 1 resolution — 2026-09-08 (Phase 4, commit `c4f8a6f7`)

| Finding | Ruling | Change (commit `c4f8a6f7`) |
|---|---|---|
| A F-1 / B F-2 — startup-shaped completed draft not excluded | restore shape-blind exclusion | `backend/draft_status.py:165-187` `completed_draft_seasons` drops the `_is_rookie_shaped` skip: any `status == "complete"` draft with `season >= current_season` excludes that season. `backend/tests/test_sleeper_pick_tradability.py`: `test_completed_draft_seasons_reads_only_complete_current_or_later` now expects the startup entry to count; new `STARTUP_DONE` fixture (25 rounds, complete, 2026) + `test_completed_draft_seasons_is_shape_blind` and `test_sleeper_pick_window_post_startup_starts_next_class` (`(2027, 2029)`, 2026 untradable). `prd.md` §3 F1 and the D-189 text in `build-report.md` §4 amended |
| A F-2 — corroboration ignores confidence | one sentence in D-189 | D-189 text (`build-report.md` §4): any positive `drafted` counts regardless of confidence, bounded to one sync cycle |
| A F-3 — dead `season_window: null` / `?–?` branches | remove | `backend/server.py:18446` → `"season_window": list(window)`; `_sleeper_untradable_copy` (`:30403-30423`) takes a non-None `window` and unpacks it directly. `docs/api-reference.md` 422 row: `season_window` is always present (an unknown season abstains and never refuses). Abstain behavior (`sleeper_pick_tradable(season, None)` → True) and its tests unchanged |
| B F-1 — guard check 9 satisfied by a comment | assert on the `Alert.alert` arguments | `mobile/tests/check-send-button-platform.js` check 9 locates the `Alert.alert` CallExpression inside the branch and walks `arguments[1]` for an Identifier named `detail` — comments are not AST nodes. RED proof: with only the `detail \|\|` operand removed from the Alert, the guard prints `FAIL  sleeper button: sleeper_pick_untradable renders the server detail` (exit 1); restored → all checks pass |
| A F-4 (cached verdict not season-checked; `leagues.season` literal), B F-3 (far-side copy wording) | accepted as pre-existing / verbatim-spec | no change; A F-4 is a 2027 rollover item for NEXT.md |

Verification on `c4f8a6f7`: targeted suites (`test_owned_picks`, `test_sleeper_write_route`, `test_sleeper_write`, `test_sleeper_pick_tradability`, `test_pick_assignment`, `test_trade_send_validate`, `test_pick_horizon`) → 173 passed; `npx tsc --noEmit` → 0 errors; `node tests/check-send-button-platform.js` → all pass. Full-suite line recorded in status.md / TEST_LEDGER by the orchestrator.

## Phase 3 round 2 — 2026-09-08

QA-A PASS (0 defects, 1 wording note), QA-B PASS (0 defects, 3 observations). Both suites 5892 / 1 skipped; RED-first 18/18; guard check 9 RED with the operand removed. Startup-shaped draft exclusion verified end to end on scratch DBs by both. A F-1 wording ("rookie draft already ran" → shape-neutral) fixed in this commit. **Group ship-ready.**
