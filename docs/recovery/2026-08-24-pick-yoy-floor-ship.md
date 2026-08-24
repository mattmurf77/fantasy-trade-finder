# 2026-08-24 — pick YoY floor ship

| tip sha | branch | worktree |
|---|---|---|
| `292035c9` | `claude/pick-yoy-floor-0824` | `.claude/worktrees/pick-yoy-0824` (removed 2026-08-24) |

Merged via squash PR [#203](https://github.com/mattmurf77/fantasy-trade-finder/pull/203) → `main`. Verified by content: `git diff origin/main claude/pick-yoy-floor-0824` is empty post-merge. Content markers on main: `market_r1_yoy_floor` in `pick_values.py`/`trade_service._DEFAULT_CFG`/`_MODEL_CONFIG_DEFAULTS`, `backend/tests/test_pick_yoy_floor.py`, `docs/plans/pick-yoy-floor/`, D-161, Q-018 CLOSED, TEST_LEDGER 2026-08-24 pick-YoY entry. CI green on #203 (`FTF_SKIP_SIM_GATE=1`, D-056 posture). Default 1.0 = the operator's flat-YoY ruling — live at deploy, no knob flip required.

Remote branch deleted 2026-08-24. Recovery: `git branch claude/pick-yoy-floor-0824 292035c9`
