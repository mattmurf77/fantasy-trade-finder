# Recovery ledger — release 188 sweep (2026-11-12)

Captured before deletion. Deleted after this file reached `main`. Reflog recovery expires about 2027-02-10.

| tip sha | branch | PR | merge commit | worktree | remote |
|---|---|---|---|---|---|
| `8ca71525` | `fix/free-agents-header-rank` | #671 | `517821a6` | `.claude/worktrees/fa-page` | `origin` branch deleted too |
| `4f972e2e` | `feat/usage-trends-period-toggle` | #672 | `f4f8d272` | `.claude/worktrees/usage-period` | `origin` branch deleted too |
| `fbc8cdc2` | `fix/founder-labels-any-label` | #673 | `9c1aa2a1` | `.claude/worktrees/founder-any-label` | `origin` branch deleted too |
| `968ddb02` | `feat/league-selector-pushed-pages` | #674 | `8d1bcefa` | `.claude/worktrees/selector-pages` | `origin` branch deleted too |
| `8d1bcefa` | (detached) | none | none | `.claude/worktrees/release-188` | build checkout for TestFlight 1.22.0 (188) |

**Why it is safe:** the four branches were stacked and merged in order with merge commits, not squashes. Each tip is an ancestor of `origin/main` = `8d1bcefa` (`git merge-base --is-ancestor <tip> origin/main` is true), and after each merge `origin/main`'s tree was identical to the merged head's tree. No worktree had a modified or untracked file; each held only ignored entries (`mobile/node_modules`, caches). Evidence: [TEST_LEDGER](../../living-memory/TEST_LEDGER.md) 2026-11-12 entries; PRs #671 to #674.

**Not in this sweep:** `.claude/worktrees/docs-188` (the branch carrying this ledger, `docs/release-188-ledger`; removed once it is on `main`, its tip is the head of its PR); `competent-driscoll-5fbebf` and `unruffled-ramanujan-e4e8f6` (other sessions' worktrees, left for their owners); the main checkout.

**Recover:** `git branch <name> <sha>`.
