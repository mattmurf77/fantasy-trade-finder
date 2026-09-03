# 2026-09-03b — Web landing platform entry ship sweep (PR #272)

Ship: PR [#272](https://github.com/mattmurf77/fantasy-trade-finder/pull/272) squash → `main` @ `ca5fac46` ([D-177](../../living-memory/DECISIONS.md)). Verification **by content**: `git diff origin/main 9fea43e0` is **empty** — every byte of the branch tip is on `main` (this repo squash-merges, so ancestry and `git branch -d` are not evidence). CI on the merged head: backend-tests · mobile-typecheck · maestro-testid-lint · web-structure, all pass. Evidence: `living-memory/TEST_LEDGER.md` 2026-09-03b.

| tip sha | branch | where it lived | why deletion is safe |
|---|---|---|---|
| `9fea43e0` | `claude/landing-page-espn-mfl-a5a85a` (local + `origin/`) | session worktree `compassionate-jones-ea8a0e` | `git diff origin/main 9fea43e0` empty — tree identical to `main` @ `ca5fac46` (the squash of this branch). Three commits: `8473fab2` (code) → `a9665fd1` (write-back) → `9fea43e0` (full-suite count). |
| `80b00290` | `claude/ledger-web-platform-entry-ship` (local + `origin/`) | same worktree | this file's own PR ([#275](https://github.com/mattmurf77/fantasy-trade-finder/pull/275), squash → `main` @ `709871d2`). `git diff origin/main 80b00290` empty at deletion. Recorded here after the fact — both branches were deleted in the same sweep and only the first row existed at that moment; the sha is preserved above and in the reflog. |

Worktree `.claude/worktrees/compassionate-jones-ea8a0e` hosts the session that shipped this and cannot remove itself — remove from the main checkout (`git worktree remove .claude/worktrees/compassionate-jones-ea8a0e`; expect it clean, everything is committed and pushed).

Deleted: 2026-09-03, both branches, local + `origin/` (reflog recovery expires ~2026-12-02). Recovery: `git branch <name> <sha>` with the shas above.
