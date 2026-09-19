# audit-p1-remediation — the P1 tier

**Status: shipped, 2026-08-12.** The P1 findings from the
[2026-08-09 mobile UX audit](../../business/product/2026-08-09-mobile-ux-audit/), planned
2026-08-11 and shipped the next day. See the `CHANGELOG.md` entry "P1 audit remediation:
tier-board exposure closed, share loop wired, invite promoted, anchors unlockable".

Two outcomes worth knowing before you read the docs:

- **P1-3 (email capture) was built and then reverted in full** — flag, policy, docs and
  living-memory. The sequencing was backwards: plaintext PII with indefinite retention, no
  removal path and no legal review, for addresses no email infrastructure exists to use. Its
  plan/PRD/LLD/scope are kept as the reasoning trail, **not as a spec to build from.**
- **`growth.tier_board_share` ships OFF as its resting state** (D-P1-12) — sharing rankings is
  not a product surface. The P1-1/P1-2 work closed a live exposure on those routes; it did not
  open a feature.

## Read order

1. **[`DECISIONS-p1.md`](DECISIONS-p1.md) — read first, and it wins.** Operator decisions made
   during the 2026-08-11 planning round, binding on any later build. Where a decision
   contradicts a plan, HLD, LLD or PRD written before it, that section is superseded. Superseded
   entries are struck through in place rather than deleted, so the trail survives.
   `D-P1-08` (simulator gate retired) and `D-P1-12` are the two most often cited elsewhere.
2. **[`HLD-p1.md`](HLD-p1.md)** — the round-level reconciliation across findings.
3. Per finding: `scope-p1-N.md` → `plan-p1-N.md` → `PRD-p1-N.md` → `LLD-p1-N.md`.

## Findings

| # | Audit ref | Finding | Files |
|---|---|---|---|
| P1-1 + P1-2 | — | Share artifacts carry no link, and two complete landings have zero callers | [scope](scope-p1-1-2.md) · [plan](plan-p1-1-2.md) · [PRD](PRD-p1-1-2.md) · [LLD](LLD-p1-1-2.md) |
| P1-3 | A-12 | Email capture at the Apple bind point — **built, then reverted** | [scope](scope-p1-3.md) · [plan](plan-p1-3.md) · [PRD](PRD-p1-3.md) · [LLD](LLD-p1-3.md) |
| P1-5 | A-14 | Invite is buried, duplicated, and unmeasured | [scope](scope-p1-5.md) · [plan](plan-p1-5.md) · [PRD](PRD-p1-5.md) · [LLD](LLD-p1-5.md) |
| P1-7 | A-16 | Pick Anchors can never unlock, and its labels contradict the tier ladder | [scope](scope-p1-7.md) · [plan](plan-p1-7.md) · [PRD](PRD-p1-7.md) · [LLD](LLD-p1-7.md) |
| P1-9 | A-18 | Quality-gated `trade_found` push | [scope](scope-p1-9.md) · [plan](plan-p1-9.md) · [PRD](PRD-p1-9.md) · [LLD](LLD-p1-9.md) |
| P1-10 | A-19 | Sleeper Connect in-flow analytics | [scope](scope-p1-10.md) · [plan](plan-p1-10.md) · [PRD](PRD-p1-10.md) · [LLD](LLD-p1-10.md) |
| P1-11 | A-20 | "Acquire" → "Trades": presentation-only vocabulary correction (naming half only) | [scope](scope-p1-11.md) · [plan](plan-p1-11.md) — no PRD/LLD; presentation-only |

P1-4, P1-6 and P1-8 have no files here — they were not carried into this round; the decision
for each is in [`DECISIONS-p1.md`](DECISIONS-p1.md).

Related: [`../audit-p0-remediation/`](../audit-p0-remediation/) (the launch-blocker tier),
ADR-008 (the remediation wave), and D-043 / D-041 / D-042 in
[`living-memory/DECISIONS.md`](../../../living-memory/DECISIONS.md) for the P1-7 rulings.
