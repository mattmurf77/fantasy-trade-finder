# 2026-08-27 — `claude/calc-merged-partner-summary` + its agent worktree

Ledgered **before** deletion, per [CLAUDE.md](CLAUDE.md).

## Refs

| tip sha | ref | note |
|---|---|---|
| `4e051c12` | `claude/calc-merged-partner-summary` (local + `origin/`) | the #384 partner team-shape regression fix; 2 commits |
| `61169c87` | `claude/lm-writeback-partner-summary` | living-memory write-back (CHANGELOG + HANDOFF) for the same work |
| — | worktree `.claude/worktrees/goofy-perlman-490e49` | the agent worktree both branches were authored in |

## Why deletion is safe — verified by content, not by ancestry

`claude/calc-merged-partner-summary` was squash-merged as PR
[#221](https://github.com/mattmurf77/fantasy-trade-finder/pull/221) → `main` `3119eece`.
This repo squash-merges, so ancestry checks prove nothing. Verified by **content** instead:

```
git diff --stat origin/main <branch>~1 -- \
  mobile/src/components/InLeagueCalculator.tsx \
  mobile/tests/check-calc-merged-layout.js \
  docs/feedback/items/384-calc-finder-merge/partner-summary-regression.md
```

→ **empty**: all three files byte-identical on `origin/main`. Cross-checked that
`git show origin/main:mobile/src/components/InLeagueCalculator.tsx` carries three
`PartnerSummaryLine` occurrences (the definition plus both layouts' mounts).

CI was green on all three checks (`backend-tests`, `mobile-typecheck`,
`maestro-testid-lint`) before the merge. Evidence record:
[docs/feedback/items/384-calc-finder-merge/partner-summary-regression.md](../feedback/items/384-calc-finder-merge/partner-summary-regression.md);
ledger entry in [living-memory/TEST_LEDGER.md](../../living-memory/TEST_LEDGER.md) 2026-08-27.

`claude/lm-writeback-partner-summary` is verified the same way once its own PR merges —
**do not delete it before that PR is on `main` and diffed by content.**

## Recovery

```
git branch claude/calc-merged-partner-summary 4e051c12
git branch claude/lm-writeback-partner-summary 61169c87
```

Reflog recovery expires ~90 days from **2026-08-27**.
