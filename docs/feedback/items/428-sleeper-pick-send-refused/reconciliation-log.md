
## Orchestrator rulings 2026-09-08 (Phase 1 exit)

1. New additive 422 `sleeper_pick_untradable` (with `picks[]`, `season_window`, `message == detail`) **approved**: an API contract addition, documented in api-reference/cross-client-invariants per the scope block; fielded build 154 already renders `detail`. Folding into `sleeper_pick_unmapped` rejected as misleading.
2. The exact pick sent at 17:03:52Z is not recoverable without the prod DB (blocked); the public-API evidence (draft complete 2026-08-26, 34 season-2026 rows still in `traded_picks`, sender's only acquired pick a spent 2026 4th) is sufficient for the mechanism. Operator is asked in the ship summary.
3. D-189 (narrowing D-089: when `/drafts` flakes and the cached #207 verdict says drafted, exclude the current season) **adopted** — live read still wins; allocate the id from origin/main at write time.
4. Optional mobile parity branch in SendInSleeperButton: **include** (small, owned by no other group).
