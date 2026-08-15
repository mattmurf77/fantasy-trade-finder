# 2026-08-14 — trade-relevance P0 build worktrees swept

Two auxiliary build worktrees, used to parallelize Phase P0 across agents
working on disjoint regions of `server.py`/`database.py`. Both were merged into
the surviving branch, which is **pushed**.

| tip sha | branch | worktree path |
|---|---|---|
| `ef20d91` | `feat/trade-relevance-p0-join` | `…/744e007c-…/scratchpad/p0-join` |
| `7c89c09` | `feat/trade-relevance-p0-agg` | `…/744e007c-…/scratchpad/p0-agg` |

- **Why safe:** both tips are **ancestors of `origin/feat/trade-relevance-p0`**
  @ `b47046b` — verified with
  `git merge-base --is-ancestor <branch> origin/feat/trade-relevance-p0`
  (exit 0 for both) after the two merge commits `4a8f2ce` (join) and `f6ee573`
  (agg). Their content is therefore on the remote, not merely on this disk.
  **Note the difference from the usual sweep entry in this folder:** the
  surviving branch is *not* `main` — P0 is unmerged by design (the pass-ledger
  refactor owes a ≥3-day soak before any flag flips). So the safety claim here
  is "contained in a pushed branch", and these tips must NOT be re-swept
  against `main` until that branch merges.
- The surviving worktree `…/scratchpad/p0-build` (branch
  `feat/trade-relevance-p0`) is **kept** for tomorrow's session and is itself
  session scratch — if the scratchpad is cleaned, re-check out the branch from
  `origin`; nothing is lost.
- Removed 2026-08-14 (reflog recovery expires ~2026-11-12).
- Recovery:
  `git branch feat/trade-relevance-p0-join ef20d91`
  `git branch feat/trade-relevance-p0-agg 7c89c09`
