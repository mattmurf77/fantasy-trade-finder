# 2026-08-14 — roster-history branch + worktree sweep

| tip sha | ref |
|---|---|
| `1564d37` | `feat/roster-history` (local + origin) — worktree `.claude/worktrees/roster-history` |
| `633fe20` | `tmp-ship` (worktree-local only; fast-forwarded into `main`, deleted immediately) |

**Why safe:** merged via squash PR [#120](https://github.com/mattmurf77/fantasy-trade-finder/pull/120)
→ `main` @ `81dd6d2`. **Verified by content, not ancestry:**
`git diff origin/main feat/roster-history` was empty immediately after the merge
(byte-identical trees). PR CI green (backend-tests on 3.12 incl. the full suite,
mobile-typecheck, testid-lint). The `tmp-ship` living-memory commit fast-forwarded
to `main` @ `633fe20`. Post-deploy, Writer C swept 11/12 prod leagues live
(TEST_LEDGER 2026-08-14 entry).

**Worktree removal note:** `mobile/node_modules` in the worktree was a symlink to
the primary checkout's (for tsc/tests) — removal discards only that link.

**Deleted:** 2026-08-14 (reflog recovery expires ~2026-11-12).

**Recovery:** `git branch feat/roster-history 1564d37`
