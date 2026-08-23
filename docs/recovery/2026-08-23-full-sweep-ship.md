# 2026-08-23 — trade-model reviews + full-sweep ship

| tip sha | branch | worktree |
|---|---|---|
| `32d9576` | `claude/trade-model-restrictiveness-7f3975` | `.claude/worktrees/trade-model-restrictiveness-7f3975` (live session home on 2026-08-23 — remove after that session ends) |
| `4ebb121` | `claude/full-sweep-0822-a1c3` | `.claude/worktrees/full-sweep-a1c3` (removed 2026-08-23) |

Merged via squash PRs [#181](https://github.com/mattmurf77/fantasy-trade-finder/pull/181) → `main` `23b8c80` and [#182](https://github.com/mattmurf77/fantasy-trade-finder/pull/182) → `main` `9dfcac9`. Verified **by content**, not ancestry: `git diff origin/main claude/full-sweep-0822-a1c3` is empty; `git diff origin/main claude/trade-model-restrictiveness-7f3975` names only files #182 later changed (the review branch's own content is on `main` — the three `docs/reviews/2026-08-22-*` reports, Q-030, G-058, CHANGELOG 2026-08-22m). Content markers on main: `trade.full_sweep` **true** in `config/features.json`, `full_sweep_budget_s` / `exploration_base_per_opp` in `trade_service._DEFAULT_CFG`, `backend/tests/test_full_sweep.py`, `docs/plans/full-sweep/`, D-154, TEST_LEDGER 2026-08-22j. CI green on both PRs (backend, typecheck, testid-lint; `FTF_SKIP_SIM_GATE=1` per D-056 standing posture).

Remote branches deleted 2026-08-23. Recovery: `git branch claude/trade-model-restrictiveness-7f3975 32d9576` · `git branch claude/full-sweep-0822-a1c3 4ebb121`
