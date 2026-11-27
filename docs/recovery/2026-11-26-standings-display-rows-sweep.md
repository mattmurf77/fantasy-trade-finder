# 2026-11-26: Standings display rows sweep

Deleted 2026-11-26 (local and `origin`). Reflog recovery expires about 90 days after that.

| Tip sha | Branch | Worktree | PR |
|---|---|---|---|
| `b560d28e` | `feat/standings-display-rows` | `.claude/worktrees/standings-display` | 740 |

Why deletion was safe: PR 740 was merged with a merge commit (`4f385af3`, pinned with
`--match-head-commit`), so the tip is an ancestor of `origin/main`
(`git merge-base --is-ancestor b560d28e origin/main`), and the tree at `4f385af3` is identical to
the branch tip (`git diff 4f385af3 b560d28e` is empty). Scope and evidence:
`docs/plans/standings-display-rows/`; decision D-285.

Worktree: `.claude/worktrees/standings-display` was created for this branch and reused for the
release record (`docs/release-202-record`, PR 742, which carries this file). It was removed after
that branch was pushed, with nothing uncommitted in tracked files; the only local content was the
ignored `mobile/node_modules`. `docs/release-202-record` itself stays on `origin` until PR 742
merges and is left for the next sweep.

Recovery: `git branch feat/standings-display-rows b560d28e`.
