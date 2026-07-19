# Workspace cleanup 2026-07-19 — archive manifest

Two-phase cleanup (operator decision 2026-07-19): **phase 1 = archive (this
directory), phase 2 = deletion via `purge.sh --release-validated`, only after
the next release is pushed to main, deployed on Render, and validated.**

## What was found (survey summary)

- 55 auxiliary worktrees under `.claude/worktrees/`, ~162 local branches,
  39 stale remote branches, 9 stashes, 1 open PR (#91).
- Nearly all branches were **squash-merged via PRs** (verified against the full
  GitHub PR history), so `git branch --no-merged` overstated unfinished work.
- Three worktrees held genuinely unlanded fixes; all three were recovered,
  adapted, tested, and committed to `trade-engine-v2` on 2026-07-19:
  - `vigilant-wozniak-382289` → consensus consolidation raw-loss gate
    (`consolidation_raw_loss_frac`, deck-eval 2026-07-17) — commit bc3ccd7
  - `magical-hofstadter-40cf12` → universal-pool DP fetch retry backoff
    (empty fetch no longer cached; test adapted to post-#127
    `load_consensus_maps` API) — commit 5075e70
  - `cranky-hofstadter-251429` → `/api/session/init` 400 `missing_user_id`
    fail-fast for tokened calls (S2 drill) — commit a343333
  - Full backend suite after landing: **875 passed**.

## Archive contents

| Item | What it preserves |
|---|---|
| `all-refs-2026-07-19.bundle` | Every ref (all branches, tags, remotes) + complete history. Verified. **Not committed to git** (20 MB); lives on disk here. Restore any ref: `git fetch archive/cleanup-2026-07-19/all-refs-2026-07-19.bundle <ref>:<ref>` |
| `archive/stash-{0..8}` git tags | The 9 stash commits — recoverable even after `git stash clear` (`git stash apply archive/stash-N`) |
| `worktree-dirty-state/` | Per-worktree uncommitted tracked diffs (`*.tracked.patch`) and untracked files (`*.untracked/`), node_modules excluded. The all-deletions junk state of `agent-a6f676d19f96310cd` (138 deleted-file entries, branch content intact in git) was deliberately skipped |
| `purge-*.txt` | Exact deletion lists consumed by `purge.sh` |

## Disposition

**Keep (excluded from purge):** `trade-engine-v2`, `main`,
`chalkline-primitives` (unfinished Chalkline primitive gap-fill, local only),
`audit/perf-optimization` (perf-audit docs artifact, pushed),
`claude/stoic-mccarthy-e56da9` until PR #91 is closed.

**Open PR #91** (Depth tier purple #a855f7): superseded — the color already
landed via 0edc7de + PR #98. Close it manually, then delete its branch.

**Everything else** (worktrees, local branches, remote branches, stashes, root
QA screenshots): obsolete — squash-merged, duplicate tips, or abandoned
(e.g. the `loving-wright` DTF/SwiftUI rebuild). Delete in phase 2.

**Untouched by cleanup:** `staged-work/` (17 staged competitor features
awaiting 1-by-1 validation), `feedback-workspace/` (scratch, gitignored),
uncommitted `mobile/App.tsx` onboarding work owned by a concurrent session.

## Phase 2

```bash
./archive/cleanup-2026-07-19/purge.sh --release-validated
```
