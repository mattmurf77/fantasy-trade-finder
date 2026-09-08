
## Orchestrator rulings 2026-09-08 (Phase 1 exit)

1. New additive 422 `sleeper_pick_untradable` (with `picks[]`, `season_window`, `message == detail`) **approved**: an API contract addition, documented in api-reference/cross-client-invariants per the scope block; fielded build 154 already renders `detail`. Folding into `sleeper_pick_unmapped` rejected as misleading.
2. The exact pick sent at 17:03:52Z is not recoverable without the prod DB (blocked); the public-API evidence (draft complete 2026-08-26, 34 season-2026 rows still in `traded_picks`, sender's only acquired pick a spent 2026 4th) is sufficient for the mechanism. Operator is asked in the ship summary.
3. D-189 (narrowing D-089: when `/drafts` flakes and the cached #207 verdict says drafted, exclude the current season) **adopted** — live read still wins; allocate the id from origin/main at write time.
4. Optional mobile parity branch in SendInSleeperButton: **include** (small, owned by no other group).

## Phase 3 round 1 — 2026-09-08

QA-A FAIL (1 major to adjudicate, 3 minor); QA-B PASS (3 minor). Both suites 5890 passed / 1 skipped; RED-first 16/16 confirmed by both. Convergent finding: `completed_draft_seasons` skips startup-shaped completed drafts (A F-1 / B F-2), whereas the pre-fix sync excluded the current season for ANY completed draft.

**Rulings (Phase 4):** (1) restore shape-blind exclusion — any `complete` draft with season ≥ current excludes that season (a completed startup draft consumes the class too; the old behavior was the tested, safe one); PRD §3 amended, unit test updated, D-189 text amended. (2) B F-1: `check-send-button-platform.js` check 9 must match the `Alert.alert` arguments, not comment text. (3) A F-3: drop the dead `season_window: null` / "?–?" branches and the api-reference `null` note (window is always present when refusing). (4) A F-2 one-sentence D-189 note on confidence; A F-4 / B F-3 accepted as pre-existing or verbatim-spec copy.
