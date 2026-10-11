# Buyer/Seller flare tags — branch and worktree recovery

2026-10-10. **Captured before any deletion.** Scope: the branch and worktree that built the flare Buyer/Seller tags and the uncapped Home ice emphasis ([D-204](../../living-memory/DECISIONS.md)).

[PR #322](https://github.com/mattmurf77/fantasy-trade-finder/pull/322) head `94ac8f250391054ca1d32b6d19cfc9bb6a4b007a` (branch `feat/band-badge-flare`) squash-merged as `41894bee` on `main`.

**Content verified:** `git diff --stat 94ac8f25 41894bee` is empty, so the merged tree is identical.

| Tip SHA | Branch | Worktree |
|---|---|---|
| `94ac8f250391054ca1d32b6d19cfc9bb6a4b007a` | `feat/band-badge-flare` (local + `origin`) | `../ftf-wt-band-flare` (detached at `41894bee` for the EAS build) |

Recovery: `git branch <recovery-name> 94ac8f250391054ca1d32b6d19cfc9bb6a4b007a`, or `git fetch origin refs/pull/322/head`.

**Cleanup executed by this record (2026-10-10):**
- local branch and remote `feat/band-badge-flare` deleted;
- worktree removed after its EAS upload (build 164).

Beyond tracked files the worktree held only `mobile/node_modules` and gitignored caches. Nothing uncommitted was discarded.
