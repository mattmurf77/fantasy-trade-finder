# 2026-09-03c — ESPN sign-in-primary ship sweep (PR #276)

Ship: PR [#276](https://github.com/mattmurf77/fantasy-trade-finder/pull/276) squash → `main` @ `0059a8a0` ([D-179](../../living-memory/DECISIONS.md) + [G-069](../../living-memory/GOTCHAS.md)). CI on the merged head `38d5153e`: backend-tests · mobile-typecheck · maestro-testid-lint · web-structure, **all four success** (polled to `status == "completed"` per [G-062](../../living-memory/GOTCHAS.md), not a single optimistic read). Evidence: `living-memory/TEST_LEDGER.md` 2026-09-03d.

**Verification by content, with one expected difference.** `git diff origin/main 38d5153e` is **not** empty: it shows one `living-memory/TEST_LEDGER.md` region where **`main` is NEWER**, because `1d0152fc` (the other session's cron-scope ledger) replaced one bullet with two more detailed ones after this branch was pushed. The branch carries the older copy of *their* text and nothing of its own — confirmed by asserting every artifact of this change is present on `main`:

| Artifact | File on `main` |
|---|---|
| `espn-signin-btn` (the primary control) | `web/index.html` |
| `ENTRY_SESSION_LOST` ×9, `_handleEntrySessionLost` ×6 | `web/js/app.js` |
| G-069 entry + index row | `living-memory/GOTCHAS.md` |
| D-179 entry + index row | `living-memory/DECISIONS.md` |
| 2026-09-03d entries (+ TOC rows) | `CHANGELOG.md`, `TEST_LEDGER.md`, `HANDOFF.md` |
| §V3.1 scope + code-walk | `docs/plans/landing-platform-options/` |
| ESPN entry hierarchy row · layout note | `docs/design/components.md` · `docs/config-reference.md` |

| tip sha | branch | where it lived | why deletion is safe |
|---|---|---|---|
| `38d5153e` | `claude/espn-signin-primary` (local + `origin/`) | session worktree `compassionate-jones-ea8a0e` | every artifact above is on `main` @ `0059a8a0`; the only diff is a region where `main` is ahead (see above). Two commits: `04da90a0` (reorder) → `38d5153e` (G-069 guard). Rebased twice onto concurrent `main` moves; the pre-rebase tips `af7f0f62` and `48c41a18` are superseded by these and reachable in the reflog. |

Worktree `.claude/worktrees/compassionate-jones-ea8a0e` hosts the session that shipped this and cannot remove itself — remove from the main checkout (`git worktree remove .claude/worktrees/compassionate-jones-ea8a0e`; expect it clean).

Deleted: 2026-09-03, local + `origin/` (reflog recovery expires ~2026-12-02). Recovery: `git branch claude/espn-signin-primary 38d5153e`.
