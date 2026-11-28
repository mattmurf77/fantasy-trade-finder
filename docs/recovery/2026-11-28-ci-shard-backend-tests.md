# 2026-11-28: ci/shard-backend-tests branch and worktree

Deleted 2026-11-28 (local and `origin`). Reflog recovery expires about 90 days after that.

| Tip sha | Branch | Worktree |
|---|---|---|
| `64cf4641` | `ci/shard-backend-tests` | `.claude/worktrees/ci-shard-backend-tests` |

Why deletion was safe: merged via PR 739 as a true merge commit (`cb248ccf`, parents `f0085c06`
and `64cf4641`), so the tip is an ancestor of `origin/main` and both branch commits (`9dcf6f61`,
`64cf4641`) stay reachable from `main`. Checked by content against `origin/main` at `464ac175`:
`.github/scripts/ci_shard.py`, `.github/backend-test-durations.json` and
`backend/tests/test_ci_shard.py` are byte-identical to the tip; `.github/workflows/ci.yml`,
`.github/CLAUDE.md` and `backend/tests/CLAUDE.md` differ only by the later skip-by-area change
(PR 735), which kept the 8-shard matrix, the `backend-tests` gate and the `concurrency` block.
The worktree had no uncommitted files; `git worktree remove` needed no `--force`.

Recovery: `git branch ci/shard-backend-tests 64cf4641`.
