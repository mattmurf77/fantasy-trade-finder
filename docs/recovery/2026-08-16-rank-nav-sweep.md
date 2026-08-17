# Recovery ledger — rank-nav single-exit sweep (2026-08-16)

Per `docs/recovery/CLAUDE.md`: tip recorded BEFORE deletion; verification by CONTENT
against `origin/main` (this repo squash-merges, so ahead/behind counts are not evidence).

**Verification evidence:** squash commit `3a10751` ("Rank nav: one exit per surface … (#137)")
carries the branch's content — confirmed on `origin/main` by marker: `headerBackVisible: false`
present, `_openRankMenu` absent (0 occurrences), `MoreWaysButton` navigating to `RankHome`,
all 8 `rankSubScreenOptions` call sites on the 1-arg signature, plus
`mobile/tests/check-rank-nav-exit.js` and `docs/plans/rank-nav-single-exit/scope.md` present.

| Branch | Tip sha | Where its content lives now |
|---|---|---|
| `fix/rank-nav-single-control` | `8e00e2a` (pre-merge tip, PR #137) | `origin/main@3a10751` |

**Worktree removed:** the session scratchpad worktree at
`…/scratchpad/nav` (detached build tree; `mobile/node_modules` was a SYMLINK to the main
checkout's, never a real install — nothing to reclaim).

Also swept in the same pass: `…/scratchpad/fix-import` and `…/scratchpad/ledger`
(both already removed after PR #136 / the ship-record push).
