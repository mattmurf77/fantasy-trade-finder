# 2026-08-23 — session docs/CI branches (W8 ship write-back · onboarding-tour-merge plan · fixture-mirror fix)

| tip sha | branch | merged as |
|---|---|---|
| `915601d` | `docs/384-w8-ledger` | squash PR [#180](https://github.com/mattmurf77/fantasy-trade-finder/pull/180) → `3208b0e` |
| `b65f07f` | `docs/onboarding-tour-merge` | squash PR [#184](https://github.com/mattmurf77/fantasy-trade-finder/pull/184) → `000a9d8` |
| `d187411` | `fix/release-flags-mirror` | squash PR [#185](https://github.com/mattmurf77/fantasy-trade-finder/pull/185) → `16f0e0a` |

All three are single-commit branches off `origin/main`; verification is by squash diff — each PR's
diff equals the branch's only commit, and the content is on `main` (`docs/plans/onboarding-tour-merge/`,
TEST_LEDGER `2026-08-23a`, `trade.full_sweep: true` in the three flag fixtures). Remote branches
deleted 2026-08-23. Recovery: `git branch docs/384-w8-ledger 915601d` ·
`git branch docs/onboarding-tour-merge b65f07f` · `git branch fix/release-flags-mirror d187411`.

The branch carrying THIS file (`docs/recovery-sweep-0823`, scratch worktree `wt-docs2`) is itself
docs-only and single-commit; after its squash-merge it is recoverable from its own PR's diff.
Deleted same day, worktree removed.

Same pattern, same day: `docs/segrave-v2` (scratch worktree `wt-docs3`) — single-commit,
docs-only (notes v2 + plan §2b + this paragraph); after its squash-merge it is recoverable from
its own PR's diff. Deleted same day, worktree removed.

Same pattern, same day: `docs/segrave-128-d157` (scratch worktree `wt-docs4`) — docs-only
(D-157; plan §2b item 12 reopened as a build-128 defect with the loading-race cause; this
paragraph). Its earlier form `docs/segrave-128-d155` was deleted UNMERGED when its PR #189 hit the
D-155 collision with the ram-mascot PR #186 — content re-landed here renumbered, nothing lost.
Recoverable from its own PR's squash diff. Deleted same day, worktree removed.

Same pattern: `docs/d158-inline-home` (scratch worktree `wt-docs5`) — docs-only (D-158; plan §3b
Wave B0 spec; CHANGELOG + NEXT refresh; this paragraph). Recoverable from its own PR's squash
diff. Deleted same day, worktree removed.
