# Calibration Yes/No + live-deck filters worktrees — recovery

2026-10-15. **Captured before removal.** Two lead-session worktrees whose PRs squash-merged into `main`.

| Tip SHA | Branch | Worktree | PR |
|---|---|---|---|
| `81432938` | `feat/calibration-yes-no` | `~/Developer/ftf-calibration-yes-no` | #327 → `1549370b` |
| `1bf2235d` | `feat/deck-quality-filters` | `~/Developer/ftf-deck-quality-filters` | #328 → `71a02541` |

**Content verified:** for each branch, `git diff <branch> origin/main -- <every file the branch changed>` printed 0 lines (8 and 14 files). Neither worktree held uncommitted tracked files. The only untracked items were a `mobile/node_modules` symlink and a copied, gitignored `secrets.local.env`, both discarded.

Recovery: `git branch feat/calibration-yes-no 81432938` · `git branch feat/deck-quality-filters 1bf2235d`.
