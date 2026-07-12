# #127 — Kenneth Walker listed as a WR (duplicate, wrong position) — status

**State:** built + regression-tested (2026-07-12, branch `trade-engine-v2`). Awaiting QA/ship.

## Root cause

Two different NFL players normalise to the same name: Kenneth Walker (veteran
WR, Sleeper id `4634`) and Kenneth Walker III (RB, Sleeper id `8151`).
`DP_TO_SLEEPER_NAME` maps the suffixed DynastyProcess name onto the shared key
`"kenneth walker"`, and `build_universal_pool`'s DP↔Sleeper join was
**name-only** — so BOTH Sleeper players matched the single DP row and entered
the universal pool with the RB's value. The phantom WR then surfaced on the
QuickSet/Tiers WR tab. Verified against the real cache + live DP CSV: the
name-only join also admitted phantom Josh Johnson (RB + WR namesakes of the
QB) and Antonio Williams (RB namesake of the WR).

## Fix

Never name-match across positions:

- `backend/data_loader.py` — `_fetch_dynasty_process` now also returns a
  `{normalised name: DP position}` map; new public `load_consensus_maps`
  returns all three maps from ONE fetch; `seed_elo_for_players` takes an
  optional `pos_map` and treats a position-mismatched name hit as unmatched.
- `backend/server.py` — `build_universal_pool` takes `dp_pos` and requires the
  Sleeper player's position to equal the DP row's; `_ensure_universal_pools`
  threads the per-format pos maps (`dp_pos_by_format`); demo seeding passes
  the pos map too. (Also halves the DP CSV fetches per format — one
  `load_consensus_maps` call replaces separate values+elo fetches.)
- `backend/scripts/replay_trade_decisions.py`, `backend/scripts/calibrate_elo_value.py`
  — same position-strict rule in their pool joins (they replicate the
  membership rule).

## Verification

- Real-data before/after: pool went 619 → 615 real players; the 4 dropped rows
  are exactly the wrong-position namesakes (KW WR 4634, Josh Johnson RB/WR,
  Antonio Williams RB). Exactly one Kenneth Walker remains, at RB, id 8151.
  Zero single-match players have a DP-vs-Sleeper position disagreement, so no
  legitimate player is dropped.
- Regression tests: `backend/tests/test_dp_crosswalk_position.py` (4 tests —
  the Walker case pinned; general cross-position rule; pos_map surface;
  `seed_elo_for_players` strictness). Full suite: 556 passed.

## Known limitation (spawned as a follow-up task)

Same-name **same-position** collisions still all match one DP row (live
example: three Sleeper "Kyle Williams" WRs inherit the NE rookie's value).
Proper fix: resolve DP rows to a specific `sleeper_id` via the DP
`db_playerids` crosswalk `espn_service.py` already fetches. Out of scope here.
