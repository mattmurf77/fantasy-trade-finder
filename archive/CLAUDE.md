# archive/ — Notes for Claude

**Frozen history. Nothing here is live code, live docs, or a live skill.** Do not read it
to answer "how does X work today" — use `docs/`, `backend/`, `mobile/`, `web/` at the repo
root. `/archive/` is in `.easignore`, so it never ships in the EAS build archive.

| Directory | Archived | What it is | Have a README? |
|---|---|---|---|
| [`skill-workspaces/`](skill-workspaces/README.md) | 2026-07-12, +2026-08-08 | Throwaway skill-eval workspaces, packaged `.skill` bundles, and five role skills retired for non-use | yes, both levels |
| [`root-cleanup-2026-07/`](root-cleanup-2026-07/README.md) | 2026-07-12 | One-off debug/analysis output that had accumulated in the repo root (trade dumps, DB check scripts, xlsx exports) | yes |
| [`cleanup-2026-07-19/`](cleanup-2026-07-19/MANIFEST.md) | 2026-07-19 | The phase-1 branch/worktree purge: an all-refs git bundle, the purge lists, `purge.sh`, and captured dirty worktree state | yes — `MANIFEST.md` |

## If you are looking for a deleted branch

`archive/cleanup-2026-07-19/all-refs-2026-07-19.bundle` is a snapshot of every ref as of
that date. **Everything after 2026-07-19 goes through the recovery ledger instead** —
`docs/recovery/`, per [`docs/recovery/CLAUDE.md`](../docs/recovery/CLAUDE.md). Capture the
tip sha first, delete second, never the reverse.

## Three traps

1. **Nested source/`docs/` trees are not FTF.** `skill-workspaces/project-reorganizer-workspace/` contains synthetic eval fixture projects (`flat-flask-api/`, `mixed-python-project/`, …) with their own `docs/` folders. They are test inputs, not this repo's history.
2. **`worktree-dirty-state/` holds patches, not branches.** `*.tracked.patch` + `*.untracked/` per worktree; branch content itself is in the bundle. Three genuinely unlanded fixes were already recovered and landed on 2026-07-19 — `MANIFEST.md` names them and their commits.
3. **Restoring a retired skill is a move, not a copy** — see [`skill-workspaces/retired-2026-08-08/README.md`](skill-workspaces/retired-2026-08-08/README.md) for the command and the re-verification step.

`purge.sh` (phase 2, the actual deletion) is still gated on a validated release and has
not run. `*.bundle` is gitignored — the 20 MB bundle lives on disk here only, so it does
not survive a fresh clone.
