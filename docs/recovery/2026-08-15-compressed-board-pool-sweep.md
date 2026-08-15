# Recovery ledger — compressed-board pool fixes (worktree `loving-shtern-12e4b1`)

**Date:** 2026-08-15
**Procedure:** [docs/recovery/CLAUDE.md](CLAUDE.md) — capture, then delete, never the reverse.

## Captured tips (recorded BEFORE any deletion)

| Branch | Tip sha | Fate |
|---|---|---|
| `claude/loving-shtern-12e4b1` | `c7ee5b027302fac3f2a3f70253a5055017696385` | work squash-merged as PR #122 → `main` @ `19d4174`; spent after the squash (see [G-046](../../living-memory/GOTCHAS.md)) |
| `claude/compressed-board-ship-record` | `bec25bbf1f08e9a1083a448e4c2a4892e55239cb` | ship record + deck-size correction squash-merged as PR #124 → `main` @ `f8b51be` |
| `claude/ci-gotchas` | (this branch, unmerged at time of writing) | G-046 / G-047 |

Worktree path: `.claude/worktrees/loving-shtern-12e4b1`

## Verification — BY CONTENT, not by ahead-count

This repo squash-merges, so `git branch -d` refusals and ahead/behind counts are
**not** evidence. Both branches were verified by content against `origin/main`:

```
git diff --stat origin/main origin/claude/loving-shtern-12e4b1      # engine + tests + docs
git diff --stat origin/main origin/claude/compressed-board-ship-record
```

Evidence that the shipped behaviour is actually on `main` and live, independent
of git bookkeeping:

- `git show origin/main:config/features.json` → both flags `true`
- `git show origin/main:docs/config-reference.md | grep "stop-when-reached threshold"` → present (the correction)
- prod `GET /api/feature-flags` → `trade.pool_calibration: true`, `trade.divergence_fallback: true` (2026-08-15T18:21:21Z)
- post-deploy deck read against prod boards: all four boarded FFV3 members produce cards

## Notes

PR #123 was opened from `claude/loving-shtern-12e4b1` after PR #122 had already
squash-merged it, and was born `CONFLICTING`. Closed as superseded and replaced
by PR #124 from a branch cut fresh off `main`. Root cause and the general rule
are recorded as [G-046](../../living-memory/GOTCHAS.md).
