# Recovery ledger — Max PF follow-ups sweep (2026-11-13)

Captured before deletion. Deleted after this file reached `main`. Reflog recovery expires about 2027-02-11.

| tip sha | branch | PR | merge commit | worktree | remote |
|---|---|---|---|---|---|
| `4e821a41` | `feat/forecast-retry-missing-moves` | #686 | `cdaf10fe` | `.claude/worktrees/moves-rerun` | `origin` branch deleted too |
| `d723b064` | `feat/max-pf-moves-show-all` | none (stacked under `feat/playoff-odds-clinch-display`) | this PR's merge commit | `.claude/worktrees/maxpf-v1-1` | `origin` branch deleted too |
| `447540d1` | `research/score-spread-study` | none (merged into `feat/playoff-odds-clinch-display`) | this PR's merge commit | `.claude/worktrees/score-spread` | `origin` branch deleted too |

**Why it is safe:** `4e821a41` is an ancestor of `origin/main` = `cdaf10fe` (#686 was merged with a merge commit). `d723b064` and `447540d1` are ancestors of this PR's branch tip and reach `main` with it; the sweep re-checks `git merge-base --is-ancestor <tip> origin/main` and a clean worktree for every row before deleting.

**Not in this sweep:** `.claude/worktrees/clinch-display` (the branch carrying this ledger; ledgered with its own release entry once merged); `competent-driscoll-5fbebf` and `unruffled-ramanujan-e4e8f6` (other sessions' worktrees); and worktrees whose work is not on `main`: `navigation-map`, `expanded-row`, `personal-tendencies`, `universe-crawler`, `universe-values`, `universe-run` (the full Sleeper pull runs from it).

**Recover:** `git branch <name> <sha>`.
