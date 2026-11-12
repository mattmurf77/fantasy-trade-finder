# Recovery ledger — release 187 sweep (2026-11-12)

Captured before deletion. Deleted after this file reached `main`. Reflog recovery expires about 2027-02-10.

## Branches merged by pull request

| tip sha | branch | PR | merge commit | worktree | remote |
|---|---|---|---|---|---|
| `bbe9f339` | `feat/roster-setup-tier-rank` | #651 | `8b5f076a` | `.claude/worktrees/roster-tier-rank` | `origin` branch deleted too |
| `64ceb006` | `docs/projection-v5-release` | #652 | `475c8de9` | `.claude/worktrees/release-185` | `origin` branch deleted too |
| `b7128237` | `feat/fit-block-rank-table` | #653 | `82169979` | `.claude/worktrees/fit-rank-table` | `origin` branch deleted too |
| `34e21e11` | `feat/fit-rank-table-all-positions` | #655 | `fa83f57b` | `.claude/worktrees/fit-rank-noise` | `origin` branch deleted too |
| `6a263079` | `plan/win-now-season-signal` | #656 | `c6b514fc` | `.claude/worktrees/win-now-plan` | `origin` branch deleted too |
| `6c703699` | `feat/projection-fa-fill` | #657 | `f804c2ae` | `.claude/worktrees/proj-fa-fill` | `origin` branch deleted too |
| `f6a588eb` | `feat/deck-rules-first` | #658 | `564ff857` | `.claude/worktrees/rules-first-deck` | `origin` branch deleted too |
| `8d585e3c` | `feat/projection-median-leagues` | #659 | `2f02145c` | `.claude/worktrees/median-leagues` | `origin` branch deleted too |
| `840ffa83` | `fix/pass-button-on-asking-card` | #660 | `6108b8c3` | `.claude/worktrees/pass-button` | `origin` branch deleted too |
| `e8fd4480` | `release/2026-11-12-train` | #663 | `4c2279b9` | `.claude/worktrees/train` | `origin` branch deleted too |
| `b3b893a4` | `feat/founder-label-review` | #664 | `679658b4` | `.claude/worktrees/founder-review` | `origin` branch deleted too |
| `7c7287a2` | `feat/founder-rule-waterfall` | #665 | `4b57aa91` | `.claude/worktrees/rule-waterfall` | `origin` branch deleted too |
| `c0ce570f` | `fix/platform-league-user-binding` | #666 | `5f1f7cb2` | `.claude/worktrees/link-binding` | `origin` branch deleted too |
| `c618c77f` | `feat/season-seller-labels` | #667 | `58e180f3` | `.claude/worktrees/seller-labels` | `origin` branch deleted too |
| `6b6484ce` | `feat/onboarding-test-profile` | #668 | `9f01fe40` (landed inside #669) | `.claude/worktrees/test-profile` | `origin` branch deleted too |
| `0b49ca38` | `feat/in-app-claims` | #669 | `12ac0f1d` | `.claude/worktrees/in-app-claims` | `origin` branch deleted too |

## Branches that reached `main` inside the 2026-11-12 train (#663), never pushed on their own

| tip sha | branch | worktree |
|---|---|---|
| `b0dd929d` | `fix/card-remove-position-ranks` | `.claude/worktrees/fit-no-ranks` |
| `61f8a6fe` | `feat/pick-value-projected-slot` | `.claude/worktrees/pick-draft-order` |
| `72cf9ef2` | `fix/untouchables-in-cards` | `.claude/worktrees/untouchable-hard` |

## Closed pull requests whose work shipped in the train (#663)

| tip sha | branch | PR | worktree | remote |
|---|---|---|---|---|
| `1aaca557` | `feat/partner-outlook-from-projection` | #661 (closed) | `.claude/worktrees/partner-outlook` | `origin` branch deleted too |
| `47389a0c` | `feat/season-signal-wi1` | #662 (closed) | `.claude/worktrees/win-now-build` | `origin` branch deleted too |

Each tip is a merge commit of `main` into the branch, made after the train had already taken the branch. Both parents of each tip are ancestors of `origin/main` (`eedf243f` and `2f02145c`; `6a8d64e0` and `2f02145c`), so the tip adds no commit of its own.

## Design and research branches (documents only)

| tip sha | branch | worktree | untracked file discarded |
|---|---|---|---|
| `8b5f076a` | `design/card-logic-grades` | `.claude/worktrees/card-logic-assess` | `docs/plans/card-logic-grades/assessment.md` and a `docs/plans/README.md` edit |
| `adead776` | `design/fast-deck-with-background-solve` | `.claude/worktrees/fast-deck-design` | `docs/plans/realtime-trade-engine/fast-deck-v2-design.md` |
| `8b5f076a` | `design/filler-muting` | `.claude/worktrees/filler-muting-design` | `docs/plans/filler-muting/design.md` |
| `adead776` | `research/window-asset-identification` | `.claude/worktrees/window-pieces-research` | `docs/research/window-asset-identification/README.md` |

These four worktrees needed `--force` because their documents were never committed on the branch. Each document was compared byte for byte with the copy on `origin/main` (`cmp`) and is identical, and the `README.md` row is on `main`. Nothing unique was discarded.

## Detached release checkouts

| tip sha | worktree | what it was |
|---|---|---|
| `82169979` | `.claude/worktrees/release-186` | build checkout for TestFlight 1.22.0 (186) |
| `12ac0f1d` | `.claude/worktrees/release-187` | build checkout for TestFlight 1.22.0 (187) |

**Why it is safe:** every tip in the first, second and fifth tables is an ancestor of `origin/main` = `12ac0f1d` (`git merge-base --is-ancestor <tip> origin/main` is true). This repo merged these with merge commits, not squashes. The third and fourth tables are explained above. Apart from the four design worktrees, no worktree had a modified or untracked tracked-area file; each held only ignored entries (`mobile/node_modules`, caches). Evidence: [TEST_LEDGER](../../living-memory/TEST_LEDGER.md) 2026-11-12 entries; PRs #651 to #669.

**Not in this sweep:** `.claude/worktrees/platform-forecasts` (the branch carrying this ledger; removed once it is on `main`, tip recorded in the PR); `competent-driscoll-5fbebf` and `unruffled-ramanujan-e4e8f6` (other sessions' worktrees holding nested untracked folders, including a local database; left for their owners); the main checkout.

**Recover:** `git branch <name> <sha>`.

**2026-11-12, after the sweep:** all 28 entries above were removed once this file was on `main` (#670, `0ae86582`). `.claude/worktrees/platform-forecasts` went with them: branch `feat/forecasts-espn-mfl`, tip `8879b9d7`, an ancestor of `origin/main`; `origin` branch deleted too.
