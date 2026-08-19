# 2026-08-18 — navdoc-refresh branch + worktree sweep

| tip sha | ref |
|---|---|
| `38a989c` | `docs/navdoc-refresh-2026-08-18` (local + origin) — worktree `wt-navdocs` (session scratchpad) |

**Why safe:** shipped via PR [#138](https://github.com/mattmurf77/fantasy-trade-finder/pull/138)
(workspace-wide CLAUDE.md/README.md navigation refresh + completion of the D-056
Maestro/simulator retirement), squash-merged to `main` as `686c429`.

Verified **by content**, not by ahead-count — this repo squash-merges, so a
`git branch -d` refusal is not evidence: `git diff 38a989c origin/main` is
**empty**, i.e. every byte of the branch is absorbed in `main` @ `686c429`.

CI green on the exact merged sha — `backend-tests` (8m48s), `mobile-typecheck`
(50s, which also globs `mobile/tests/check-*.js`), `maestro-testid-lint` (8s).
GitHub reported the PR `MERGED` at 2026-08-19T00:36:13Z and deleted the remote
branch. All 81 changed markdown files passed a relative-link check with zero
breaks, before and after the rebase onto `60cbe11`.

**Scope note:** docs plus `.claude/skills/**`, `githooks/pre-push`, and the
`.github/workflows/ci.yml` header comment. No application source changed, so
there is no deploy behaviour to probe — the Render auto-deploy off this merge is
a no-op rebuild. Two changes take effect for humans/agents rather than users:
`githooks/pre-push` is now a documented no-op (its gate was already bypassed
permanently via `FTF_SKIP_SIM_GATE=1`), and the swept skills change what future
sessions are instructed to do.

**Deleted:** 2026-08-18 (reflog recovery expires ~2026-11-16).

**Recovery:** `git branch docs/navdoc-refresh-2026-08-18 38a989c`
