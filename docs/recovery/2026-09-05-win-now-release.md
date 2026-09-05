# Win Now release recovery — 2026-09-05

Prepared before merging/deleting any release reference.

| Tip SHA | Branch | Worktree |
|---|---|---|
| `abb1af118d3fe39f32292e99cecc64cebff1d2f3` | `codex/win-now-20260904` | `/private/tmp/ftf-win-now-20260904` |

Cleanup date: **2026-09-05**. The committed branch tree was verified identical to PR #280 squash `c28ec6d802463e048d59a97967e9bb5bb9fdc6f9` using `git diff --quiet origin/main abb1af118d3fe39f32292e99cecc64cebff1d2f3` after fetch (exit 0). Before removal, the release executor publishes the final local documentation and checks it matches `origin/main`. Any `--force` removal discards only these already-published release notes and generated local test artifacts; no unpublished product work. Preserve the original checkout's unrelated changes. No private temporary DB/cache is part of the release.

Evidence: [release record](../business/ops/2026-09-05-win-now.md) and [PR #280](https://github.com/mattmurf77/fantasy-trade-finder/pull/280). The final release code passed all four CI gates and production smoke; runtime code in iOS build 147 matches that release.

Recovery: `git branch codex/win-now-20260904 abb1af118d3fe39f32292e99cecc64cebff1d2f3`.
