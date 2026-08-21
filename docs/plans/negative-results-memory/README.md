# Negative-results memory

Persistent per-league memory of proposals that DIED — indexed by league-mate, trade
shape, and rejection reason — consulted by the trade engine as a **prior during
generation**, not just a filter after. The lesson from a rejected trade stops landing in
a log row and staying there; the next generation run starts from a different place.

**Status:** PLANNING ONLY — full gates, no build. Operator-assigned 2026-08-21 (dispatch
session, item 2 of the product-gap review). Planning stops at the doc suite for operator
review, after reconciliation with the sibling **Receipts** feature (item 1, planned in
session `trade-suggestions-review-69c9eb-f4` — the post-mortem half of the same loop:
Receipts grades what we suggested; this remembers what died so it isn't re-generated).

**Two layers** (PRD decides the v1 boundary):
1. **User-side memory** — what THIS user rejects (shape aversions, board misfits) → the
   engine respects it.
2. **League-mate tendency modeling** — inferred acceptance patterns of other managers
   from dismissals/declines → the engine anticipates the counterparty. Novel, riskier,
   and carries a privacy/fairness question (modeling league-mates who may not be app
   users) that the PRD surfaces for the operator rather than deciding.

**Design principle** (source: the operator's product-gap review, the "self-improving
trading loop" thread): *negative results are the most undervalued asset — keep every
failed hypothesis, in the context where it failed, and the system stops repeating them.*

## Doc map

| Doc | What | Status |
|---|---|---|
| [research-verification.md](research-verification.md) | Code-truth memo: every existing suppression/learning mechanism, with citations | in progress |
| [scope.md](scope.md) | Feature-gate scope block (docs/templates/feature-scope.md) | pending |
| [PLAN.md](PLAN.md) | Delivery plan | pending |
| [PRD.md](PRD.md) | Product requirements (dual-agent-doc-review) | pending |
| [HLD.md](HLD.md) | High-level design (dual-agent-doc-review) | pending |
| [LLD.md](LLD.md) | Low-level design (dual-agent-doc-review) | pending |
| reconciliation.md | The contract-level reconcile with Receipts (shared shape taxonomy, table ownership, pipeline touchpoints) | after both suites draft |

## Constraints of record (from dispatch + verified corrections)

- Branch: fresh from `origin/main` (`claude/vigilant-spence-8583f5`, verified 0/0 at fork).
- The fit-challenger is **merged to main** (PR #154) — its post-score filter stage and the
  bake-off arms are live surfaces this feature's generation hook must compose with.
- `taste_service` (F5) and deck fatigue (F3) already learn/suppress from swipes — the PRD
  carries a named section positioning this as NOT a third overlapping mechanism.
- **Counterfactual boundary:** the ghost holdout was disabled 2026-08-21T00:43Z (serving
  re-light). `is_ghost=1` "generated-but-never-shown" rows end there; any design that
  wants "rejected" vs "never saw" must respect that date.
- Reconciliation happens against Receipts' published contract (shared trade-shape
  taxonomy as a co-owned artifact; `receipts_`-prefixed tables theirs; reserved pipeline
  touchpoints), not against prose.
- One shared trade-shape taxonomy across the sibling features — never two. **Adopted
  2026-08-21: `docs/plans/shared/trade-shape-taxonomy.md` v1.0.0 (seed)** — authored by
  the Receipts session (lands in-repo with their merge), three-way co-owned, semver'd,
  code-cited. This plan uses its terms verbatim; the §2.1 partner-mirror convention and
  the §2.6 `user_value_basis` caveat (a pass on a personally-priced card is board-fit
  evidence, not market-value evidence) are load-bearing for the rejection-record design.
  Proposed v1.1.0 addition (additive minor, at reconciliation): an objection/rejection
  vocabulary section anchored on the shipped `trade_pass_reasons` layer-1/2 codes.
- **Third sibling (2026-08-21):** "Counterparty breaker" (session `trading-engine-eval-8ab7bc-31`)
  — an adversarial pass arguing the OTHER manager's rejection case from their present
  roster/window state. Boundary both PRDs draw identically: **breaker = deterministic
  present-state analysis; this feature = historical behavioral prior from observed
  rejections.** Potentially feeding each other later; separate mechanisms, separate
  owners now. Reconciliation is THREE-way (Receipts + breaker + this) before any suite
  reaches the operator.
