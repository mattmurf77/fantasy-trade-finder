# 2026-08-24 — knockout refine ship

| tip sha | branch | worktree |
|---|---|---|
| `f420a73` | `claude/knockout-refine-0823` | `.claude/worktrees/knockout-refine-0823` (removed 2026-08-24) |

Merged via squash PR [#194](https://github.com/mattmurf77/fantasy-trade-finder/pull/194) → `main`. Verified **by content**: `git diff origin/main claude/knockout-refine-0823` is empty post-merge. Content markers on main: `need_gate_dual_rescue`/`overpay_adjusted`/`pos_net_starter_relief`/`v3_shape_max_delta` in `trade_service._DEFAULT_CFG`, `backend/tests/test_knockout_refine.py`, `scripts/knockout_knob_sweep.py`, `docs/plans/knockout-refine/`, D-159, G-060, TEST_LEDGER 2026-08-24. CI green on #194 (`FTF_SKIP_SIM_GATE=1`, D-056 posture). Prod bundle applied post-deploy via admin API (source stamp `knockout-refine D-159 bundle`): filler 0.15 / gap 0 / shape 2 / overpay raw — all verified live 2026-08-24.

Remote branch deleted 2026-08-24. Recovery: `git branch claude/knockout-refine-0823 f420a73`
