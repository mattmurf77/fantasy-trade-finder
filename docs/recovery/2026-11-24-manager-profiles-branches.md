# Recovery ledger: manager-profiles branches, 2026-11-24

The operator asked for this cleanup on 2026-11-24: "The outstanding item should be handled. Do that now." `origin/main` was at `cb260ca4` (merge of PR #716) when these tips were captured.

These tips were captured before anything was deleted. The remote branches are deleted only after this file is on `main`.

| Tip | Branch | Merged by | Worktree | Remote |
|---|---|---|---|---|
| `3d61127d` | `feat/manager-profiles` | #635, merge `9b14c47b` | none (the `unruffled-ramanujan-e4e8f6` worktree had already been removed outside the session) | the `origin` branch is to be deleted |
| `c6a18170` | `docs/manager-profiles-shipped` | #640, merge `37a65777` | none | the `origin` branch is to be deleted |

**Why it is safe:** both tips are ancestors of `origin/main` at capture. I checked each one with `git merge-base --is-ancestor <sha> origin/main`. Both PRs were merged with merge commits, not squashed. Neither branch has a local copy, so only the `origin` refs are deleted.

**Recovery:** run `git branch <name> <sha>`.
