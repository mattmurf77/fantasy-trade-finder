# Usage Trends — branch and worktree recovery

2026-10-10. **Captured before any deletion.** Scope: the branch and worktree that built Usage Trends ([D-203](../../living-memory/DECISIONS.md), [scope](../plans/usage-trends/scope.md)).

[PR #321](https://github.com/mattmurf77/fantasy-trade-finder/pull/321) head `a69459017e275467cfca02269d9697b1fb7326ee` (branch `feat/usage-trends`) squash-merged as `35c6838c` on `main`.

**Content verified:** `git diff --stat a6945901 35c6838c` is empty, so the merged tree is identical.

| Tip SHA | Branch | Worktree |
|---|---|---|
| `a69459017e275467cfca02269d9697b1fb7326ee` | `feat/usage-trends` (local + `origin`) | `.claude/worktrees/usage-trends` (detached at `35c6838c` for the EAS build) |

Recovery: `git branch <recovery-name> a69459017e275467cfca02269d9697b1fb7326ee`, or `git fetch origin refs/pull/321/head`.

**Cleanup executed by this record (2026-10-10):**
- local branch and remote `feat/usage-trends` deleted;
- worktree removed after its EAS upload.

Beyond tracked files the worktree held only gitignored caches (`__pycache__`, `.pytest_cache`), a local test `data/` SQLite DB, and `mobile/node_modules`. Nothing uncommitted was discarded.
