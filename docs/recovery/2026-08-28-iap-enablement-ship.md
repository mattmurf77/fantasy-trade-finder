# 2026-08-28 — IAP enablement ship: branch + worktree sweep

| tip sha | branch | worktree path |
|---|---|---|
| `1ad2fb53` | `claude/monetization-features-feedback-a6fe77` | `.claude/worktrees/monetization-features-feedback-a6fe77` |

**Why deletion is safe:** merged via squash PR
[#227](https://github.com/mattmurf77/fantasy-trade-finder/pull/227) →
`origin/main` `766d2261`; verified **by content**, not ancestry:
`git diff origin/main 1ad2fb53` is empty (0 files). The branch carried the
IAP enablement code half (runbook 6–7): the RevenueCat webhook delta
(alias reconciliation, TRANSFER, BILLING_ISSUE grace, tolerant SKU
mapping), `GET /api/paywall/config`, the mobile `react-native-purchases`
integration + `PaywallScreen`, ADR-016, and the living-memory write-back —
all dark behind `monetize.*`. Evidence: `living-memory/TEST_LEDGER.md`
2026-08-28d.

**Worktree note:** the worktree hosted the building session itself and
cannot remove itself mid-session; it was left clean (branch merged, no
uncommitted files beyond this write-back, which shipped via
`claude/iap-enablement-writeback`). Sweep it from the main checkout:
ledgered here, then `git worktree remove` + delete both branches.

Deletion date: 2026-08-28 (reflog recovery expires ~2026-11-26).

Recovery: `git branch claude/monetization-features-feedback-a6fe77 1ad2fb53`
