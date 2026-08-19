# 2026-08-18 — matchmaking/bake-off session sweep

Deletion date: 2026-08-18 (reflog recovery expires ~2026-11-16).

## Feature branches (all squash-merged to `main`)

| tip sha | branch | merged in | worktree |
|---|---|---|---|
| `defd036` | `feat/engine-pick-and-diversity` | `60cbe11` | scratchpad `wt-engine-fix` |
| `b6dfbb5` | `feat/unpin-overrides` | `e8ae476` | scratchpad `wt-unpin` |
| `c15a6a8` | `feat/bakeoff-arm-a` | `3760f12` | scratchpad `wt-phase2` |
| `7454fbd` | `feat/tier-bounded-pins` | `9d24da3` | scratchpad `wt-ship-tb` source |
| `09b9bbb` | `feat/bakeoff-runner` | `7c2d615` | scratchpad `wt-phase3` |

## Ship branches (tips are `main` commits; zero unique content)

| tip sha | branch | worktree |
|---|---|---|
| `60cbe11` | `ship/engine-fixes` | scratchpad `wt-merge-eng` |
| `e8ae476` | `ship/phase0` | scratchpad `wt-ship-p0` |
| `3760f12` | `ship/g049` | scratchpad `wt-g049` |
| `9d24da3` | `ship/tier-bounded` | scratchpad `wt-ship-tb` |
| `7c2d615` | `ship/phase3` | scratchpad `wt-ship-p3` |

Detached worktrees removed with no branch and no unique commits (nothing owed):
`wt-next`, `wt-peerdocs`, `wt-dryrun`, `wt-ver`, `wt-led`, `wt-led2`.

**Why deletion was safe — verified by content, not ancestry** (this repo squash-merges, so
`git branch -d` refusals and ahead-counts prove nothing). Each feature branch's identifying
addition was confirmed present on `origin/main` @ `7c2d615`: `rank_div_min_frac` (6 hits,
`trade_service.py`), `pin_exclude_comparisons` (1, `database.py`), `MODEL_A_PROFILE` (2,
`bakeoff_profiles.py`), `pin_tier_bounded` (4, `database.py`), `fairness_threshold` (15,
`bakeoff_runner.py`). Functional corroboration: the merged-state suite grew monotonically
across the sequence — 3173 → 3224 → 3280 → 3314 → **3363 passed / 1 skipped / 0 failed** —
each merge carrying its own new tests.

**Method note, recorded because it nearly caused a wrong call:** a first pass compared whole
files (`git diff origin/main <branch> -- <file>`) and reported five branches as DIFFERING.
That was the check being wrong, not the merges — `main` had moved under concurrent sessions,
so the diff was surfacing *main's newer content* as though it were missing branch content.
On a repo with several sessions pushing daily, verify a branch landed by confirming its
**additions are present on main**, never by whole-file equality.

Sim gate waived by the operator 2026-08-17 for this line of work; every push used
`FTF_SKIP_SIM_GATE=1`. Detail in `living-memory/TEST_LEDGER.md`.

Not touched (other sessions' work): `feat/sweep-followups-2026-08-18`,
`docs/session-memory-writeback`, `feat/sleeper-reachability-probe`, `feat/trade-relevance-p0`,
and their worktrees.

Recovery: `git branch <name> <sha>` for any row above.
