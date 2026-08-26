# 2026-08-26 — scratch probe worktree removed (feat/jon-360-362 rebase session)

| tip sha | ref | worktree path |
|---|---|---|
| 867c3baa | (detached — `origin/main`, no branch) | `<scratchpad>/wt-mainprobe` |

**Why safe:** the worktree was created detached at `origin/main` purely to run a
read-only engine probe (bisecting which upstream commit changed 1-for-1
admission for the #360 test fixture; culprit d42872f2). Zero commits were made;
the only checkouts were existing origin/main shas (d42872f2~1, d42872f2,
9dfcac96, ff153a0f), all reachable from `origin/main`. Content identity is by
construction — nothing existed there that is not on the remote.

**Recovery:** nothing to recover; `git worktree add --detach <path> origin/main`
recreates it exactly.

The session's other worktree (`<scratchpad>/wt-jon-360-362`, branch
`feat/jon-360-362`) is NOT removed — it holds the prepared, unpushed rebase and
is handed to the operator.
