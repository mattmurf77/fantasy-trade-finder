# 2026-08-14 — dropped-emitter taxonomy batch sweep

| tip sha | branch | worktree path |
|---|---|---|
| `7016850` | `claude/elegant-mccarthy-ef63f8` | `.claude/worktrees/elegant-mccarthy-ef63f8` |

- **Why safe:** merged via squash PR
  [#116](https://github.com/mattmurf77/fantasy-trade-finder/pull/116) → `main` @
  `4733f78`. Verified **by content**: `git diff origin/main
  claude/elegant-mccarthy-ef63f8` (post-merge fetch) is **empty** — every changed
  file (taxonomy, queries, QuickSetTiersScreen, addendum, invariants,
  living-memory) is byte-identical on `main`.
- Deleted 2026-08-14 (reflog recovery expires ~2026-11-12).
- Recovery: `git branch claude/elegant-mccarthy-ef63f8 7016850`
