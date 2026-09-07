# Team overhaul v1 release — branch recovery

2026-09-07. **Captured before any deletion.** Scope: the single build branch for the team-overhaul v1 release. The Fleeced checkout on `codex/team-overhaul-discovery` (uncommitted organization branch + the original handoff packet) was read only and is preserved untouched.

Release [PR #288](https://github.com/mattmurf77/fantasy-trade-finder/pull/288) head `4203d0593ef31c8dc05acdf7f8a468a700397270` (branch `claude/team-overhaul-scoping-ea1c72`) squash-merged as `a8ef182e` on `main`. Content verification: `git diff --stat origin/main 4203d059` is empty (complete-tree equality across the squash boundary). Hosted CI passed all four jobs on the PR merge refs (runs 34090353672, 34091694362); iOS 1.17.2 (151), EAS build `2e13ce3d`, was built from `c190f52a`, whose tree differs from `4203d059` only by the docs-only ledger commit — no mobile or config file differs. Local full backend suite on `d23a3b81`: 5810 passed / 1 skipped.

## Captured targets

| Tip SHA | Branch / state | Location |
|---|---|---|
| `4203d0593ef31c8dc05acdf7f8a468a700397270` | `claude/team-overhaul-scoping-ea1c72` | worktree `.claude/worktrees/open-feedback-summary-b43796` (the session's own tree; detached to `origin/main` after merge) |

Full tip: `4203d0593ef31c8dc05acdf7f8a468a700397270` (PR #288 head). Recovery: `git branch <recovery-name> 4203d0593ef31c8dc05acdf7f8a468a700397270` or `git fetch origin refs/pull/288/head`.

**Cleanup executed by this record:** remote and local branch deleted after the equality check above. The worktree directory is the running session's checkout and is left detached at `origin/main` for the operator's next sweep (`git worktree remove` from the main checkout); it holds no unique content.
