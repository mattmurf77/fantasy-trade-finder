# audit-p0-remediation — the nine launch blockers

**Status: shipped, 2026-08-11.** Eight of the nine P0 findings from the
[2026-08-09 mobile UX audit](../../business/product/2026-08-09-mobile-ux-audit/) were built and
merged on branch `p0-remediation-2026-08-10` (13 commits, off `origin/main @ ab9368f`).
Branch/worktree ledger: [`../../recovery/2026-08-11-p0-remediation-sweep.md`](../../recovery/2026-08-11-p0-remediation-sweep.md).
ADR-008 covers the wider remediation wave.

Two findings did not land as findings:

- **P0-4 was withdrawn** by the operator before the build — the Mock Draft "dead end" was a
  stale config comment, not a dead end. Resolution: audit
  [`06-resolutions.md`](../../business/product/2026-08-09-mobile-ux-audit/06-resolutions.md).
  There are no `*-p0-4.md` files, by design.
- **P0-9 landed as test *preparation***, not the 32-tap first-session redesign — a validation
  pass plus an operator runbook for the `trades_first_operator_test` experiment
  ([`prd-p0-8-9.md`](prd-p0-8-9.md) §5, summarized in [`../../runbook.md`](../../runbook.md)).
  The 32-tap question is still open.

**Deferred items from this build** are itemized in
[`living-memory/NEXT.md`](../../../living-memory/NEXT.md) § "2026-08-11 — P0 remediation status
+ deferrals" (0e–0k), each with the evaluation on the record. Read that before re-opening
anything here.

## Read order

[`hld.md`](hld.md) **first, and it wins.** It binds the seven per-finding plans into one
buildable branch and is the authority on batch composition, commit order, build-agent file
ownership, and the shared harness seam. The per-finding plans were written in parallel and
several make claims about shared files that don't survive reconciliation — §10 lists every one.

Then, per finding: `scope-p0-N.md` (feature scope) → `plan-p0-N.md` (the finding + approach) →
`prd-p0-N.md` (build contract) → `lld-p0-N.md` (implementation detail).

## Findings

| # | Finding | Files |
|---|---|---|
| P0-1 | The default ranking path never completes its own progression — write `ranking_method` at the point of use | [scope](scope-p0-1.md) · [plan](plan-p0-1.md) · [prd](prd-p0-1.md) · [lld](lld-p0-1.md) |
| P0-2 | A failed trade search is indistinguishable from never having searched | [scope](scope-p0-2.md) · [plan](plan-p0-2.md) · [prd](prd-p0-2.md) · [lld](lld-p0-2.md) |
| P0-3 | The invite loop is broken at both ends (deep-link join route + referred sign-in) | [scope](scope-p0-3.md) · [plan](plan-p0-3.md) · [prd](prd-p0-3.md) · [lld](lld-p0-3.md) |
| P0-4 | *Withdrawn before build* — see above | — |
| P0-5 | Apple account-only sign-in strands users with no league | [scope](scope-p0-5.md) · [plan](plan-p0-5.md) · [prd](prd-p0-5.md) · [lld](lld-p0-5.md) |
| P0-6 | Matched non-Sleeper users get no action and no reason — platform-generic send gate + copy-trade fallback | [scope](scope-p0-6.md) · [plan](plan-p0-6.md) · [prd](prd-p0-6.md) · [lld](lld-p0-6.md) |
| P0-7 | Analytics blindness — taxonomy, server send-leg, client instrumentation | [scope](scope-p0-7.md) · [plan](plan-p0-7.md) · [prd](prd-p0-7.md) · [lld](lld-p0-7.md) |
| P0-8 + P0-9 | Guided-tour sign-off gate, and first-session test prep | [scope](scope-p0-8-9.md) · [plan](plan-p0-8-9.md) · [prd](prd-p0-8-9.md) · [lld](lld-p0-8-9.md) |

The P1 tier of the same audit is [`../audit-p1-remediation/`](../audit-p1-remediation/).
