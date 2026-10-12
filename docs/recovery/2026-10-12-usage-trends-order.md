# Usage Trends order toggle — branch and worktree recovery

2026-10-12. **Captured before any deletion.** Scope: the branch and worktree that built the Usage Trends order toggle ([D-205](../../living-memory/DECISIONS.md), [scope](../plans/usage-trends/scope-order-toggle.md)).

[PR #323](https://github.com/mattmurf77/fantasy-trade-finder/pull/323) head `87062f7211e222147493cdff860559a66fba4ddd` (branch `feat/usage-trends-order`) squash-merged as `fc0f6149` on `main`.

**Content verified:** `git diff --stat 87062f72 fc0f6149` is empty, so the merged tree is identical.

| Tip SHA | Branch | Worktree |
|---|---|---|
| `87062f7211e222147493cdff860559a66fba4ddd` | `feat/usage-trends-order` (local + `origin`) | `.claude/worktrees/usage-trends-order` (detached at `fc0f6149` for the EAS build) |

Recovery: `git branch <recovery-name> 87062f7211e222147493cdff860559a66fba4ddd`, or `git fetch origin refs/pull/323/head`.

**Cleanup executed by this record (2026-10-12):**
- local branch and remote `feat/usage-trends-order` deleted;
- worktree removed after its EAS upload.

Beyond tracked files the worktree held only gitignored `mobile/node_modules` (a fresh `npm ci`) and Python caches. Nothing uncommitted was discarded.
