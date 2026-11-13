# Recovery ledger — release 191 sweep (2026-11-12)

Captured before deletion. Deleted after this file reached `main`. Reflog recovery expires about 2027-02-10.

| tip sha | branch | PR | merge commit | worktree | remote |
|---|---|---|---|---|---|
| `7161cd7e` | `docs/max-pf-trade-away-exploration` | none (merged into `feat/max-pf-moves`) | `90d8837c` via #684 | `.claude/worktrees/maxpf-explore` | `origin` branch deleted too |
| `a1af32e1` | `feat/max-pf-moves-app` | none (fast-forwarded into `feat/max-pf-moves`) | `90d8837c` via #684 | `.claude/worktrees/maxpf-moves-app` | `origin` branch deleted too |
| `4304f3a0` | `feat/max-pf-moves` | #684 | `90d8837c` | `.claude/worktrees/maxpf-moves` | `origin` branch deleted too |
| `145c6bfc` | `research/max-pf-moves-backtest` | merged into `docs/release-191-ledger` (this PR) | this PR's merge commit | `.claude/worktrees/maxpf-backtest` | `origin` branch deleted too |
| `90d8837c` | (detached) | none | none | `.claude/worktrees/release-191` | build checkout for TestFlight 1.22.0 (191) |

**Why it is safe:** the first three tips are ancestors of `origin/main` = `90d8837c` (`git merge-base --is-ancestor <tip> origin/main` true, checked 2026-11-13 04:45 UTC); #684 was merged with a merge commit, not a squash. `145c6bfc` is an ancestor of this ledger branch's own tip and reaches `main` with it; the sweep re-checks that before deleting. Every worktree was clean and every local branch pointed at the tip listed. The detached build checkout sits on a commit that is on `main`.

**Not in this sweep:** `.claude/worktrees/docs-191` (the branch carrying this ledger, removed once it is on `main`); `competent-driscoll-5fbebf` and `unruffled-ramanujan-e4e8f6` (other sessions' worktrees); and worktrees whose work is not on `main`: `navigation-map`, `expanded-row`, `personal-tendencies`, `universe-crawler`, `universe-values`, `universe-run` (the checkout the full Sleeper pull is running from; do not remove while it runs).

**Recover:** `git branch <name> <sha>`.
