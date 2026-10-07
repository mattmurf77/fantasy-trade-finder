# 2026-09-30 — value-core integration scratch worktree

| tip sha | ref | worktree path |
|---|---|---|
| 3bb981ed | (detached HEAD, no branch) | `/private/tmp/claude-501/-Users-teresadickens-Documents-Claude-Projects-Fantasy-Trade-Finder/aa0e9ed2-669c-4123-ae01-aca8b59dc0f1/scratchpad/base-3bb981ed` |

**Why safe:** a clean, detached checkout of `3bb981ed`, which is on `origin/main` (`git merge-base --is-ancestor 3bb981ed origin/main`). It was used only for the flag-off identity comparison recorded in `living-memory/TEST_LEDGER.md` (2026-09-30). `git worktree remove` needed no `--force`, and nothing was discarded.

**Deleted:** 2026-09-30. **Recovery:** `git worktree add --detach <path> 3bb981ed`.

The package worktrees `value-core-wp1..wp5` (branches `feat/value-core-wp1..5`) are **kept**. They are merged into `feat/value-core-engine` but not yet into `origin/main`.
