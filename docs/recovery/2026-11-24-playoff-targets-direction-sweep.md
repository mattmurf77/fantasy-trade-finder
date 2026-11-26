# Recovery ledger — Playoff targets and Improve pages sweep, 2026-11-24

Operator, asked which outstanding step to do: "Clean up old branches" (2026-11-24). `origin/main` at capture: `fa37a979`.

Captured before anything is deleted. The removals run only after this file is on `main`. Reflog recovery expires about 2027-02-22.

| Tip | Branch | Merged by | Worktree | Remote |
|---|---|---|---|---|
| `a08011ae` | `feat/playoff-targets` | #689, merge `1cfd1b72` | `.claude/worktrees/playoff-targets` | `origin` branch to be deleted too |
| `b3ba1aed` | `docs/playoff-pages-spec` | #690, merge `903318cc` | `.claude/worktrees/playoff-pages-spec` | `origin` branch to be deleted too |
| `94e036b9` | `feat/direction-pages` | #693, merge `e12f86a3` | `.claude/worktrees/direction-pages` | `origin` branch to be deleted too |
| `da392ecd` | `feat/direction-sheet` | #696, merge `83142801` | `.claude/worktrees/direction-sheet` | `origin` branch to be deleted too |
| `3a220408` | `feat/direction-flags-on` | #697, merge `061d61f9` | `.claude/worktrees/direction-flags-on` | `origin` branch to be deleted too |
| `995ccff7` | `research/playoff-targets-backtest` | #698, merge `edc3adab` | `.claude/worktrees/playoff-targets-backtest` | `origin` branch to be deleted too |
| `baf213e2` | `feat/playoff-targets-threshold-2` | #699, merge `01581adc` | `../Fleeced-wt-threshold` (sibling of the main checkout) | `origin` branch to be deleted too |
| `bcee82df` | `feat/playoff-targets-rerun` | #701, merge `3c941bb4` | `../Fleeced-wt-ptrerun` (sibling of the main checkout) | `origin` branch to be deleted too |
| `83142801` | none (detached HEAD) | none (build 195 source, the merge of #696) | `.claude/worktrees/build-195` | none |
| the commit that adds this file | `docs/recovery-2026-11-24-playoff-targets-sweep` | this file's PR | a temporary worktree in the session scratchpad | `origin` branch to be deleted too |

**Why it is safe:** every tip above is an ancestor of `origin/main` at capture (`git merge-base --is-ancestor <sha> origin/main`, checked one by one; the PRs were merged with merge commits, not squashed, so ancestry is the content check). Every worktree had a clean `git status --porcelain` (0 lines) at capture, so `git worktree remove` needs no `--force`; only ignored folders (`node_modules` in `build-195`) go. The last row's branch holds only this file, which is on `main` once its PR merges.

**Also deleted, not a git ref:** `ftf-research-cache/` beside the main checkout (578 MB, 527 files under `sleeper/`): public Sleeper API responses fetched for the Playoff targets backtest (#698) and the calibration research. Nothing in it is original work. Rebuild: `docs/plans/league-projections/playoff-targets/backtest/fetch_cache.py`.

**Not in this sweep:** `.claude/worktrees/daily-tick-fix-plan` (detached `f0ab507b`, clean; not confirmed as this session's); every `/private/tmp` and `codex/*` worktree (other sessions'; `git worktree prune` is not to be run); every branch with commits that are not on `main`.

**Recover:** `git branch <name> <sha>`; for a detached checkout `git worktree add --detach <path> <sha>`.
