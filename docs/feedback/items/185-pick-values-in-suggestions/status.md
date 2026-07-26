# #185 — Pick values missing in suggestions — status

**Status: fixed** · 2026-07-25 · branch `teardown-remediation` worktree

Operator report (BUG, P1): "Pick values seem to be missing. I was just shown three trade suggestions in a row: Cam Ward for a 29 1st, Ward for a 29 2nd, Ward for a 29 3rd. All three were shown as fair value with no diff in value."

## Root cause (exact)

The v2/v3 trade engine prices assets through **Elo maps**, not through `dynasty_value`:

- consensus/fairness/value-bar: `seed_value(pid) = elo_to_value(seed_elo.get(pid, 1500.0))` — `trade_service._generate_trades_v2._vs` (~line 2090) and `trade_optimizer._sv` (line ~295); `_consensus_packages`/`_fairness_v3` consume it for `give_value`/`receive_value` and the fairness gate.
- user board: `user_value` built only from `user_elo` keys; opponent board: `opp_elo.get(pid, 1500.0)`.

The #170 owned-pick injection (`server._owned_pick_assets` + inline block in `_run_trade_job`) added PICK pseudo-players to `trade_service._players`, `players_dict` and member rosters, and set `pick_value` so **`dynasty_value`** would reproduce `pool_value` — but `dynasty_value`'s PICK branch (trade_service.py ~line 358) only serves the LEGACY engine path. None of the v2/v3 Elo maps (`seed_map = service._seed`, `elo_map_rt`, `member.elo_ratings`) ever learned the pick ids, so **every pick fell through the `.get(pid, 1500.0)` default**: Elo 1500 ≈ value 1000 for a 2029 1st (true value 1300.1), 2nd (502.8) and 3rd (249.7) alike. Identical values ⇒ identical fairness (ratio 1.0 vs a ~1000-value player like Ward) ⇒ three "fair" cards with no diff — the exact symptom.

Two-scale reminder: `draft_picks` rows carry `pick_value` (legacy 0–100 round-tier, pick-share ratios only) AND `pool_value` (engine value space). The engine must always see the `pool_value` scale.

## Fix

`backend/server.py` (pick-injection region):

- New `_pick_asset_elos(pick_assets)` — engine-space Elo per injected pick: `1200 + 6·pick_value` = `value_to_elo(pool_value)` (inverse of the dynasty_value bridge).
- Injection block extracted to `_inject_owned_picks(...)` which now, after the roster/player injection, **primes every map the engine reads**: a job-local copy of `seed_map` (never pollutes the session's `service._seed`), the user's `elo_map_rt` (consensus for picks — they aren't matchup-rankable, so divergence is zero by construction), and each member's `elo_ratings`. Fairness, `give_value`/`receive_value`, both boards' surplus math and the #108 raw-board gate all price picks at `pool_value` now.
- `dynasty_value`'s PICK branch is **unchanged** (still serves the legacy path and direct pick pricing, e.g. `test_owned_picks` round-trips); the calculator's #158 path (`/api/trade/evaluate` `league_pick_vals`) was already correct and is untouched.

Docs: `docs/cross-client-invariants.md` (#185 corollary under the owned-pick `pool_value` invariant), `docs/data-dictionary.md` (`pick_value` row), docstring corrections in `_owned_pick_assets` / `dynasty_value`.

## Tests

`backend/tests/test_pick_values_in_suggestions.py` (5) — verified failing pre-fix via `git stash` (4 fail / 1 documents the bug), all pass post-fix:

- `test_pick_asset_elos_reproduce_pool_value` — bridge round-trip.
- `test_inject_owned_picks_primes_all_boards` — seed copy + user + opponent boards all priced; original `service._seed` dict untouched.
- `test_player_vs_1st_2nd_3rd_differ_materially` — the operator symptom in engine value space: receive values ≈1300/503/250 (gaps >300/>100), 1st fair vs a Ward-priced player, 3rd gated unfair.
- `test_unprimed_seed_reproduces_the_bug` — documents the pre-fix failure mode (all three identical).
- `test_generated_cards_price_picks_on_pool_scale` — end-to-end `generate_trades` (consensus opponent, the operator's scenario): pick-return cards carry pool-scale `receive_value`, never the flat 1500-Elo default.

Full backend suite: **1105 passed, 1 skipped**.
