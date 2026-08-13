# Recovery ledger — feedback #300 sweep, 2026-08-12

> Capture-then-delete, per [`CLAUDE.md`](CLAUDE.md). Tip shas recorded **before**
> removal; every branch verified **by content** against `origin/main` (this repo
> squash-merges, so ahead/behind counts are not evidence).

---

## Branches swept

| Branch | Tip sha | Landed as | Verified |
|---|---|---|---|
| `build-300-backend` | `6fd7ed6` | PR #112 → `5139b45` | content on main |
| `build-300-mobile` | `9512c2d` | PR #112 → `5139b45` | content on main |
| `integration-300` | `d207b03` | PR #112 → `5139b45` | content on main |
| `analytics-300` | `0b64871` | PR #112 → `5139b45` | content on main |

`analytics-300` was the branch actually merged — it was cut from `integration-300`,
which already carried both build halves plus the flag flip and version bump, so a
single PR carried the whole feature.

## Worktrees removed

`.claude/worktrees/build-300-backend` · `build-300-mobile` · `integration-300` ·
`analytics-300`

## Incident recorded during this work

The backend agent ran `git stash -u` on a **clean** worktree; git saved nothing, so
its `git stash pop` took a **pre-existing, unrelated stash** (`stash@{0}`,
`teardown-remediation` WIP) and landed it with conflict markers across ~32 files.
Its recovery attempts (`rm -rf`, `git clean -fd`) were **blocked by the permission
classifier**, correctly.

**Verified afterwards, independently:** all 10 stashes still present including
`stash@{0}` (a conflicted pop does not drop the stash, which is why it survived);
tracked tree matched HEAD; zero conflict markers; branch content exactly the 9
intended files. **No data was lost.** The 24 untracked leftovers were the stash's
`-u` component — duplicates of content still in `stash@{0}` — and were removed only
after the operator explicitly directed it.

**Lesson:** never `git stash` to "check the baseline". A clean tree stashes nothing,
and the pop then reaches for someone else's work.

## Where the work landed

- **`5139b45`** (PR #112) — #300 backend + mobile + analytics, flags ON, v1.13.1.
- **TestFlight build 106**, v1.13.1, submitted and operator-confirmed.
