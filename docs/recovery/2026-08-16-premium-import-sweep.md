# Recovery ledger — Premium Rankings Import v1 sweep (2026-08-16)

Per `docs/recovery/CLAUDE.md`: tips recorded BEFORE deletion; verification is by content
against `origin/main` (this repo squash-merges).

**Verification evidence:** `git diff 40f7a3a feat/premium-import-v1` is empty — the squash
commit `40f7a3a` ("Premium Rankings Import v1 … (#133)", merged 2026-08-16) carries the PR
head's exact tree. Both feeder branches are ancestors of that head via merge commits
`fdbfbf7` (backend) and `2883549` (mobile), plus conflict-resolution merge `2bc76e8`.

| Branch | Tip sha | Where its content lives now |
|---|---|---|
| `feat/premium-import-v1` (integration, PR #133 head) | `2bc76e8` | `origin/main@40f7a3a` (empty content diff) |
| `feat/premium-import-backend` | `627dcd0` | merged into integration via `fdbfbf7` |
| `feat/premium-import-mobile` | `8660b8c` | merged into integration via `2883549` |

**Worktrees removed in this sweep:**
- `/Users/teresadickens/Documents/Claude/Projects/ftf-premium-import-v1` (integration)
- `.claude/worktrees/agent-abf2d752f509e445b` (backend build agent)
- `.claude/worktrees/agent-a05f3298621325399` (mobile build agent — carried the only
  `mobile/node_modules`; the EAS build 112 archive was cut from it before removal)

Remote branch `feat/premium-import-v1` deleted after merge; the two agent branches were
never pushed.
