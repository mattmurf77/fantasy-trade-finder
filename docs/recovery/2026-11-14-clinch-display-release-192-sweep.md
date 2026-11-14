# Recovery ledger — clinch-display / release-192 sweep (2026-11-14)

Captured before deletion. **The sweep itself is NOT yet run:** nothing below has been deleted; delete only after this file reaches `main`. Reflog recovery expires about 2027-02-12.

| tip sha | branch | PR | merge commit | worktree | remote |
|---|---|---|---|---|---|
| `5329015c` | `feat/playoff-odds-clinch-display` | #687 | `11f774fb` | `.claude/worktrees/clinch-display` | `origin` branch to be deleted too |
| `11f774fb` | none (detached HEAD) | none (build 192 source) | `11f774fb` (is `origin/main` at capture) | `.claude/worktrees/release-192` | none |

**Why it is safe:** `5329015c` is an ancestor of `11f774fb` (#687 was merged with a merge commit; checked with `git merge-base --is-ancestor 5329015c 11f774fb`; by content, `git diff 5329015c 11f774fb` is empty, the merge's second parent is `5329015c`), and `11f774fb` is `origin/main` at capture. `release-192` is a detached checkout of that same commit, used only to build 1.22.0 (192) (TEST_LEDGER 2026-11-14 release entry). The sweep re-checks `git merge-base --is-ancestor <tip> origin/main` and a clean worktree (`git status --short` empty, untracked files inspected) for every row before deleting.

**Not in this sweep:** `.claude/worktrees/maxpf-most-likely` (the branch carrying this ledger; ledgered with its own entry once merged); other sessions' worktrees; and worktrees whose work is not on `main`.

**Recover:** `git branch <name> <sha>` (for `release-192`: `git worktree add --detach <path> 11f774fb`).
