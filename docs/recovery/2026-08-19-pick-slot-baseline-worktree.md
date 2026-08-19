# 2026-08-19 — throwaway baseline worktree removed (pick-slot-labels session)

| tip sha | branch | worktree path |
|---|---|---|
| `7462c23` | **none — detached HEAD** | `…/9a7e628e-…/scratchpad/wt-base` |

**What it was.** A pristine, detached checkout of `origin/main` created for one purpose: to
re-measure the pytest baseline rather than assume the number quoted in the task brief. It ran
`pytest backend/tests -q` once (**3480 passed, 1 skipped**, recorded in
[TEST_LEDGER 2026-08-19g](../../living-memory/TEST_LEDGER.md)) and was never edited.

**Why deletion was safe — verified by content, not by ahead-count.** It carried no branch and no
commits: `HEAD` was `7462c23`, which *is* `origin/main`, so there is nothing on it that is not on
`origin/main` by identity. `git worktree remove` needed `--force`; the only untracked files were
pytest's `__pycache__` / scratch DB artifacts, and **no source file was modified** — `git status`
in it was clean of tracked changes throughout.

**Deleted:** 2026-08-19. **Recovery:** none needed (`7462c23` is `origin/main`); if a checkout is
wanted again, `git worktree add --detach <path> 7462c23`.

**Procedural note, recorded rather than hidden:** the removal happened *after* the session's commit
rather than before, so this entry was written retroactively. It is the "capture, then delete" order
inverted. Harmless here only because the ref was a detached pointer at `origin/main` with zero work
on it — which is exactly the case the rule is not protecting against, but the rule has no exception
and the deviation belongs on the record.

**Not deleted, and still live:** `feat/pick-slot-labels` at `268fa16`, in
`…/9a7e628e-…/scratchpad/wt-pickslot`. Unpushed and unmerged — it holds this session's work
([D-090](../../living-memory/DECISIONS.md)) and must not be swept until that lands.
