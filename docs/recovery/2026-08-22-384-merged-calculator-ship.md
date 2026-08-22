# 2026-08-22 — #384 merged calculator ship (E2E review → W5 → W6-A/W6-B → flip)

| tip sha | branch | worktree |
|---|---|---|
| `a12c8b7` (ship tip `304f55a`; `a12c8b7` = +1 docs commit re-landed as #173) | `claude/manual-calculator-e2e-review-39a467` | `.claude/worktrees/tweet-product-gap-review-266ff1` (this session's review worktree; removed after the EAS build it hosted finished) |
| `54e9e7e` | `docs/384-ship-writeback` (cherry-pick of `a12c8b7` onto main) | scratch `wt-docs` |
| `7399e18` | `feat/calc-finder-merge` (W0–W4 as originally built; superseded — every commit was carried forward on the review branch) | `.claude/worktrees/new-user-feedback-d4c47d` (**another session's worktree — sweep when idle**, not removed here) |

Merged via squash PR [#172](https://github.com/mattmurf77/fantasy-trade-finder/pull/172) → `main` `80dee42`, then docs-only PR [#173](https://github.com/mattmurf77/fantasy-trade-finder/pull/173) → `cc6c168`.
Verified by content on `origin/main`: `fair_packages_cap` in `backend/trade_service.py`, `"/api/trades/queue"` in `backend/server.py`, `calcTourDeckArrived` in `mobile/src/utils/calcTour.ts`, `"calc.merged_layout": true` in `config/features.json`; `git diff HEAD origin/main` was empty at `304f55a` vs `80dee42`. `feat/calc-finder-merge`'s content is a strict prefix of the review branch (it was reset onto it at session start and every later commit built on top). CI: testid-lint + typecheck green on `main` run 32585974208; backend job was still in progress at ledger time.
Remote branches deleted 2026-08-22. Recovery: `git branch claude/manual-calculator-e2e-review-39a467 a12c8b7` · `git branch docs/384-ship-writeback 54e9e7e` · `git branch feat/calc-finder-merge 7399e18`
