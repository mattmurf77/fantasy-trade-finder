# 2026-11-10 — Roster-first setup build branches

Deleted 2026-11-11 (reflog recovery expires about 2027-02-09).

| tip sha | branch | worktree |
|---|---|---|
| `1583e346` | `feat/roster-setup-backend` | `.claude/worktrees/agent-adda56057794d7bf3` (clean, no `--force`) |
| `1489dc68` | `feat/roster-setup-mobile` | `.claude/worktrees/agent-a6a184ac0c80e3aae` (clean apart from gitignored `mobile/node_modules`) |
| `29e7ad67` | `worktree-agent-adda56057794d7bf3` | agent scratch branch at the old `origin/main`, no commits of its own |
| `29e7ad67` | `worktree-agent-a6a184ac0c80e3aae` | agent scratch branch at the old `origin/main`, no commits of its own |
| `0cc85660` | `docs/roster-first-trade-setup` (local only) | design commits, cherry-picked onto `feat/roster-first-trade-setup` as `bb6c438c` + `7465682b` (decision IDs renumbered D-212/D-213) |

**Why it was safe:** #637 merged into `main` with a merge commit (`9c252819`, not a squash). `git merge-base --is-ancestor` confirms that `1583e346` and `1489dc68` are ancestors of `origin/main`. The design branch's content is on `main` in `docs/plans/roster-first-trade-setup/`, with the IDs renumbered. Evidence: [TEST_LEDGER](../../living-memory/TEST_LEDGER.md) 2026-11-10 roster-first setup entry, PR #637.

**Recover:** `git branch <name> <sha>`.
