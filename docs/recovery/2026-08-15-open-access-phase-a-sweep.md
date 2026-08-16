# Recovery ledger — open-access Phase A sweep (2026-08-15)

Session: open-access Phase A (ratification → gates → fixes → flip → ship record).
All three feature branches squash-merged to `main`; verification is **by content**:
each branch's entire diff is its merged PR's diff, and the ship-record commit
(`1a9efcd`) carried the post-merge renumber. Evidence: PR links below + the
TEST_LEDGER 2026-08-15 Phase A entry.

| Branch | Tip sha | Merged as | Content evidence | Worktree swept |
|---|---|---|---|---|
| `fix/likes-you-user-gain-floor` | `8e608c3` (full: 8e608c320e2d4d205c092cfb35943cdcc2991ef5) | PR #131 → `73c78fc` | squash diff == branch diff; reviewer re-ran tests on merged tree | scratchpad `likesyou-floor` |
| `fix/s5-1-regen-diff` | `f6bfb5d` (full: f6bfb5d74b8f0205998a20dea6ad200c95fac8c1) | PR #132 → `c2e44b5` | squash diff == branch diff; check suite re-run 32/32 by reviewer | `~/Documents/Claude/Projects/ftf-s51-regen-diff` (~2.8 GB incl. node_modules/Pods — the sweep this ledger exists for) |
| `feat/open-access-phase-a` | `ef8b53d` (full: ef8b53ddd8692c047089ae7f61f6ad3b46d03410) | PR #129 → `0d8d7bb` | squash diff == branch diff; fixture pin test re-run 76/76 by reviewer | scratchpad `phase-a` |
| `docs/phase-a-ship-record` | `1a9efcd` | pushed directly to `main` (same commit) | branch tip IS the main commit | scratchpad `docs-sync` |

Sim evidence copied out before sweep: `qa/sim-runs/2026-08-15-s43-gate/`,
`qa/sim-runs/2026-08-15-s51-fix/` (gitignored, per-machine).
