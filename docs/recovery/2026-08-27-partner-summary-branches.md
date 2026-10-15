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

---

## Correction — 2026-08-27, same day

The table above records `claude/lm-writeback-partner-summary` at **`61169c87`**. That was its
tip when the entry was written; the recovery-ledger commit itself then landed on the same
branch, so the sha it was actually **deleted at is `aee848a5`**. Per this folder's append-only
rule the original line stands and this corrects it.

Nothing was lost — both commits are on `main` via the squash of PR
[#222](https://github.com/mattmurf77/fantasy-trade-finder/pull/222) (`69dc0cae`), verified by
content (`git diff --stat origin/main <branch> -- living-memory/CHANGELOG.md
living-memory/HANDOFF.md docs/recovery/2026-08-27-partner-summary-branches.md` → empty) before
deletion. But recovering from `61169c87` would restore the branch one commit short.

**Corrected recovery:**

```
git branch claude/lm-writeback-partner-summary aee848a5
```

Both branches were deleted (local + `origin/`) on **2026-08-27** after the content
verification above. `claude/calc-merged-partner-summary` at `4e051c12` is unchanged and
correct as recorded.

### Worktree still live

`.claude/worktrees/goofy-perlman-490e49` was **not** removed — the session doing the cleanup
was running inside it. Its branches are gone and its work is fully on `main`, so it holds
nothing unrecovered. Sweep it from the main checkout with:

```
git worktree remove .claude/worktrees/goofy-perlman-490e49
```

A `--force` refusal means uncommitted files — inspect before discarding.
