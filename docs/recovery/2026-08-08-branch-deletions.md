# Branch deletion record — 2026-08-08

Deleted after content-level verification that everything on them exists on
`origin/main` (or was deliberately superseded). Evidence and per-branch basis:
[docs/reviews/2026-08-08-branch-triage.md](../reviews/2026-08-08-branch-triage.md).

Recovery: `git branch <name> <sha>` restores any of these while the commits remain
reachable (reflog retention, ~90 days from deletion date; after a `git gc` past that
window they may be unrecoverable).

## Group 1 — non-worktree DELETE branches (15), deleted 2026-08-08

| Tip sha | Branch |
|---|---|
| `4982dee` | `web/feedback-batch-2026-04-29` |
| `d9e775e` | `feat/mobile-parity-2026-04` |
| `412ccb4` | `feat/mobile-parity-plan` |
| `65bb39a` | `fix/tiers-rework` |
| `90e665f` | `mobile/tiers-multi-select` |
| `2dd347d` | `fix/trios-hide-unlock-promo-when-unlocked` |
| `dda9c5d` | `claude/hungry-allen-8615ed` |
| `dca5b54` | `claude/leaderboards-phase4-5` |
| `7107617` | `claude/stoic-mccarthy-e56da9` |
| `e5b51c4` | `claude/sentry-phase3` |
| `f084fff` | `feat/in-app-feedback-capture` |
| `8026b7f` | `feat/feedback-liked-trades-waiting` |
| `ec30f60` | `feat/feedback-backend-sync` |
| `468df39` | `feat/feedback-backend-sync-plan` |
| `241f223` | `feat/wave2-init07` |

## Merged-branch deletions (verified by merge itself)

| Tip sha | Branch | Note |
|---|---|---|
| `35deb70` | `process/feature-gates-ci-2026-08-08` (6 commits) | Squash-merged via PR #100 (`4b60440`, CI green); branch deleted post-merge |
| `4a381f7` | `context-slim-2026-08-08` (7 commits) | Squash-merged via PR #101 (`e907c93`, CI green); worktree removed + branch deleted post-merge |

## Group 2 — worktree-pinned DELETE branches (29), NOT yet deleted

Pending `git worktree remove` first; when executed, append their tip shas here
(or in a new dated file) before deletion. List and worktree paths in the triage doc.

## Untracked (not deleted): stale Maestro screenshots (2026-08-09)

24 PNGs under `mobile/.maestro/screenshots/` (5.7 MB, one-off 2026-07-12 debug
session) removed from tracking via `git rm --cached` on branch
`screen-library-2026-08-09`; dir is now gitignored. Files remain on disk in any
checkout that had them; historical blobs remain in git history. Replacement:
the `screens/` library (see `screens/CLAUDE.md`).
| `dc91a91` | `screen-library-2026-08-09` (20 commits) | Squash-merged via PR #106 (`6b8270b`, CI green); worktree ~/ftf-worktrees/screens-wt removed + branch deleted 2026-08-10 |
