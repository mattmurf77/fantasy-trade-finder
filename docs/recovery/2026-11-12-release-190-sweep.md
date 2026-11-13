# Recovery ledger — release 190 sweep (2026-11-12)

Captured before deletion. Deleted after this file reached `main`. Reflog recovery expires about 2027-02-10.

| tip sha | branch | PR | merge commit | worktree | remote |
|---|---|---|---|---|---|
| `6420c262` | `plan/sleeper-trade-universe` | #676 | `82581177` | `.claude/worktrees/trade-universe` | `origin` branch deleted too |
| `247c41e7` | `fix/projection-drop-fa-fill-line` | #677 | `ce6a9567` | `.claude/worktrees/proj-fa-line` | `origin` branch deleted too |
| `004d50da` | `feat/league-rankings-playoff-tile` | #678 | `52b9ce30` | `.claude/worktrees/rankings-tile` | `origin` branch deleted too |
| `fc57b05f` | `research/playoff-odds-calibration` | #679 | `53711036` | `.claude/worktrees/odds-calibration` | `origin` branch deleted too |
| `b0727aaf` | `feat/standings-single-table` | #680 | `ac877b73` | `.claude/worktrees/standings-table` | `origin` branch deleted too |
| `26d752a2` | `fix/team-review-current-data` | #681 | `c68090d4` | `.claude/worktrees/team-review-fixes` | `origin` branch deleted too |
| `01184485` | `feat/projected-pick-rank` | #682 | `4a8cd70d` | `.claude/worktrees/pick-rank` | `origin` branch deleted too |
| `c68090d4` | (detached) | none | none | `.claude/worktrees/release-189` | build checkout for TestFlight 1.22.0 (189, from `ac877b73`) and (190, from `c68090d4`) |

**Why it is safe:** all seven branches were merged with merge commits, not squashes. Each tip is an ancestor of `origin/main` = `4a8cd70d` (`git merge-base --is-ancestor <tip> origin/main` is true for every row, checked 2026-11-13 01:15 UTC), each worktree was clean (`git status --porcelain` empty), and each local branch pointed at the tip listed. The detached build checkout sits on a commit that is itself on `main`. Test evidence for each change is its own entry in [`living-memory/TEST_LEDGER.md`](../../living-memory/TEST_LEDGER.md).

**Not in this sweep:** `.claude/worktrees/docs-190` (the branch carrying this ledger, `docs/release-190-ledger`; removed once it is on `main`, its tip is the head of its PR); `competent-driscoll-5fbebf` and `unruffled-ramanujan-e4e8f6` (other sessions' worktrees); and seven worktrees whose work is not on `main`: `navigation-map`, `expanded-row`, `maxpf-explore`, `personal-tendencies`, `universe-crawler`, `universe-values`, `universe-run`.

**Recover:** `git branch <name> <sha>`.
