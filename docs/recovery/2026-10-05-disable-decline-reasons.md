# Decline reasons disabled — branch recovery

2026-10-05. **Captured before any deletion.** Scope: the single branch that parked `feedback.decline_reasons` off ([D-195](../../living-memory/DECISIONS.md)).

[PR #310](https://github.com/mattmurf77/fantasy-trade-finder/pull/310) head `bf1e8e996744f9a03eb2d7d74920fd6e33c57d45` (branch `fix/disable-decline-reasons`) squash-merged as `85428813` on `main`. Content verification: `git rev-parse origin/main^{tree} bf1e8e99^{tree}` returned the same tree, and `git diff origin/fix/disable-decline-reasons origin/main` was empty.

## Captured targets

| Tip SHA | Branch / state | Location |
|---|---|---|
| `bf1e8e996744f9a03eb2d7d74920fd6e33c57d45` | `fix/disable-decline-reasons` | worktree `../ftf-disable-decline-reasons` (sibling of the main checkout) |

Recovery: `git branch <recovery-name> bf1e8e996744f9a03eb2d7d74920fd6e33c57d45` or `git fetch origin refs/pull/310/head`.

**Cleanup executed by this record:** worktree removed (it held only an untracked `mobile/node_modules` install, nothing unique), local and remote branch deleted, 2026-10-05. Reflog recovery expires about 90 days later.
