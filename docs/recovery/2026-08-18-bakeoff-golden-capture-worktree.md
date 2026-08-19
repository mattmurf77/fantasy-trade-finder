# 2026-08-18 — bake-off arm-A golden-capture worktree (throwaway, detached)

Removed the read-only worktree used to capture arm A's goldens for
[three-model bake-off Phase 2](../plans/three-model-bakeoff/scope-phase2.md).

| tip sha | ref | worktree path |
|---|---|---|
| `92c31d5` | **detached HEAD — no branch created** | `…/scratchpad/wt-prewave` |

**Why deletion was safe.** `92c31d5` is an ordinary commit on `origin/main`
(`review: P0 remediation verified against main`, the parent of the G6 wave
`20b40db` on `--first-parent`), so nothing was unreachable. The worktree was
created detached, never committed to, and held exactly one added file — a copy
of `backend/tests/test_bakeoff_arm_a_golden.py` brought in from the working
branch to run its `__main__` capture mode. That file lives on
`feat/bakeoff-arm-a` (`bbc366b`); the captured output is inlined in it as
`_GOLDEN_JSON` / `_GOLDEN_IDEAS_JSON`. `git worktree remove` **did** need
`--force`, for that one untracked file and nothing else (`git status --short`
listed only it). What was discarded is a byte-for-byte copy of the committed
test file — re-verified immediately before removal: re-running the documented
capture procedure with the FINAL committed file reproduced both goldens
exactly.

**Deleted:** 2026-08-18. Reflog recovery expires ~90 days later, but is not
needed — the sha is on `main`.

**Recovery:** `git worktree add --detach <path> 92c31d5` (re-runs the capture;
procedure is in the test file's module docstring).
