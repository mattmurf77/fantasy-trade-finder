# Tick-notes worktree — recovery

2026-10-15. **Captured before removal.** A detached worktree used only to write the daily-tick finding and the Usage Trends week-5 notes straight to `main`. There was no branch.

| Tip SHA | Branch | Worktree |
|---|---|---|
| `dffff6ca` | — (detached) | `.claude/worktrees/tick-notes` |

**Content verified:** the tip equals `origin/main` at removal time (`git rev-parse HEAD` = `git rev-parse origin/main`), so it held nothing unique. The worktree held no uncommitted files.

Recovery: `git branch <name> dffff6ca`.
