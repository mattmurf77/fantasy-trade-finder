# SQLAlchemy pin — branch recovery

2026-10-05. **Captured before any deletion.** Scope: the single branch that capped `sqlalchemy` below 2.1 ([G-073](../../living-memory/GOTCHAS.md)).

[PR #311](https://github.com/mattmurf77/fantasy-trade-finder/pull/311) head `672f898a4fc801c319bc606f4a7738da25a9fdbf` (branch `fix/pin-sqlalchemy-2-0`) squash-merged as `e30a8f47` on `main`. Content verification: `git diff origin/fix/pin-sqlalchemy-2-0 origin/main` was empty.

| Tip SHA | Branch / state | Location |
|---|---|---|
| `672f898a4fc801c319bc606f4a7738da25a9fdbf` | `fix/pin-sqlalchemy-2-0` | worktree `../ftf-pin-sqlalchemy` (sibling of the main checkout) |

Recovery: `git branch <recovery-name> 672f898a4fc801c319bc606f4a7738da25a9fdbf` or `git fetch origin refs/pull/311/head`.

**Cleanup executed by this record:** worktree removed (nothing uncommitted), local and remote branch deleted, 2026-10-05.
