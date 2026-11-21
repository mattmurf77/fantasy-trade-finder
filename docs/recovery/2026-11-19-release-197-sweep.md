# Recovery ledger — release 197 sweep, 2026-11-19

Operator: "Make the cleanup" (2026-11-19). `origin/main` at capture: `c2a8778c` (merge of PR #706).

Captured before anything is deleted. The removals run only after this file is on `main`.

| Tip | Branch | Merged by | Worktree | Remote |
|---|---|---|---|---|
| `6f4319dc` | `docs/recovery-2026-11-17-sweep` | #704, merge `3d9c4dd7` | none to remove (see below) | `origin` branch to be deleted too |
| `9e04b493` | `feat/nav-continuity` | #705, merge `59422d6f` | `.claude/worktrees/nav-continuity` | `origin` branch to be deleted too |
| `26333f9b` | `docs/release-197-record` | #706, merge `c2a8778c` | `.claude/worktrees/release-197-record` | `origin` branch to be deleted too |
| `59422d6f` | none (detached HEAD) | none (build 197 source) | `.claude/worktrees/release-197` | none |

**Why it is safe:** every tip above is an ancestor of `origin/main` at capture (`git merge-base --is-ancestor <sha> origin/main`, checked one by one; the PRs were merged with merge commits, not squashed). Every worktree had a clean `git status --porcelain` (0 lines) at capture, so `git worktree remove` needs no `--force`; only ignored build folders (`node_modules`) go.

**The `recovery-sweep` worktree stays.** It was on `docs/recovery-2026-11-17-sweep`; it was switched to the branch carrying this file (`docs/recovery-2026-11-19-sweep`) so that no new worktree is made for each ledger. Only the old branch is deleted. This worktree and its current branch are ledgered when they are removed.

**Not in this sweep:** `fairness-formula` (`feat/fairness-formula` `1ac1b027` is not on `main`); `content-audit` and `context-audit` (unmerged, waiting on the operator's content decisions); every worktree registered under the old `Documents/Copied Claude` path (`git worktree prune` is not to be run); other sessions' branches (`claude/*`, `codex/*`); every branch with commits that are not on `main`; any worktree made for work started on or after 2026-11-19.

**Recover:** `git branch <name> <sha>`; for a detached checkout `git worktree add --detach <path> <sha>`.

**2026-11-21, sweep run (appended after this record reached `main` as `0f870e6c`, PR #707):** the three worktrees above were re-checked against their rows (head equal, ancestor of `origin/main`, `git status --porcelain` 0 lines) and removed with `git worktree remove` (no `--force`). The three named branches were deleted locally with `git branch -d` and on `origin` with `git push origin --delete`; `git ls-remote` shows none of them. Nothing else was deleted.
