# Recovery ledger — projection model v5 and same-day follow-ups (2026-11-11)

Captured before deletion. Deleted after this file reached `main`. Reflog recovery expires about 2027-02-09.

| tip sha | branch | PR | merge commit | worktree | remote |
|---|---|---|---|---|---|
| `55077b46` | `feat/projection-model-v5` | #647 | `253136ac` | `.claude/worktrees/projection-model` | `origin` branch deleted too |
| `301cc8a5` | `docs/d227-d228-shipped` | #646 | `f6c1321e` | `.claude/worktrees/fit-copy-fix` | `origin` branch deleted too |
| `bdb741f8` | `fix/projection-team-changed` | #648 | `adead776` | none | `origin` branch deleted too |
| `df989650` | `fix/tf185-feedback` | #649 | `6891c195` | `.claude/worktrees/tf185-feedback` | `origin` branch deleted too |
| `0a6237a1` | `feat/projection-retry-incomplete` | #650 | `74cbbce8` | `.claude/worktrees/proj-rerun` | `origin` branch deleted too |

**Why it is safe:** all five merged into `main` with merge commits, not squashes, so each tip is an
ancestor of `origin/main`: `git merge-base --is-ancestor <tip> origin/main` is true for all five,
checked against `origin/main` = `74cbbce8`. The four worktrees had no modified or untracked tracked
files; each held only ignored entries (`mobile/node_modules`, caches). Evidence:
[TEST_LEDGER](../../living-memory/TEST_LEDGER.md) 2026-11-11 entries; PRs #646 to #650.

**Not in this sweep:** `.claude/worktrees/release-185` (the branch carrying this ledger),
`roster-tier-rank` (#651, open), `fit-rank-table`, `fast-deck-design` and `window-pieces-research`
(their documents are copied into this ledger's PR; the worktrees stay until that is on `main`).

**Recover:** `git branch <name> <sha>`.
