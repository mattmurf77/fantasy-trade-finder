# 2026-08-18 — golden-capture worktree removed (tier-bounded pins)

A throwaway **detached** worktree of pristine `origin/main`, created solely to
capture `backend/tests/fixtures/pin_tier_bounded_golden.json` against the
pre-change tree (and to measure the baseline `pytest backend/tests` result) for
`feat/tier-bounded-pins`. No branch, no commits, nothing authored in it.

| tip sha | ref | worktree path |
|---|---|---|
| `9a20ca8` | detached at `origin/main` (no branch created) | `…/5451272b-…/scratchpad/wt-main` |

**Why deletion was safe:** the tip *is* `origin/main` — nothing to verify by
content, since the sha is the remote head itself. The only files ever added were
two untracked scratch scripts (`_capture.py`, a verbatim copy of the new test
module's fixture builder), both deleted before removal; their output is committed
as the golden fixture on `feat/tier-bounded-pins`. `git worktree remove --force`
was used, and there was nothing uncommitted left to discard at that point.

**Procedure note (correction, per this folder's append-only rule):** the ledger
entry was written *after* the removal, not before. Recorded rather than papered
over. The capture-then-delete rule is unharmed in substance — a detached
worktree at a public remote ref cannot lose work — but the order was wrong.

**Recovery:** `git worktree add --detach <path> 9a20ca8`

**Deleted:** 2026-08-18.
