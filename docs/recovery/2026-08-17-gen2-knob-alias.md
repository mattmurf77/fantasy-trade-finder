# 2026-08-17 — gen-v2 G6 knob reconciliation sweep

Deletion date: 2026-08-17 (reflog recovery expires ~2026-11-15).

| tip sha | branch | worktree path |
|---|---|---|
| `92d2358` | `feat/gen2-knob-alias` | scratchpad `wt-alias` (session 5451272b) |

**Why deletion was safe:** the branch tip **is** `main`'s tip — pushed `ac71a67..92d2358`
before deletion, so the commit is permanently reachable from `main`, not merely merged.
Content is the G6 knob reconciliation (gen-v2 reads `pos_net_cap` / `pick_gap_frac` /
`pick_gap_min_value` instead of its own copies); full backend suite on that tip:
**3052 passed / 1 skipped / 0 failed**. Worktree removed cleanly, no `--force`, nothing
uncommitted discarded.

**Process note, recorded honestly:** the ledger entry was written *after* the branch and
worktree were removed, inverting this folder's capture-then-delete rule. No recovery risk
materialized (tip == `main` tip), but the ordering was wrong; noting it so the exception
is visible rather than silently normalized.

Recovery: `git branch feat/gen2-knob-alias 92d2358`
