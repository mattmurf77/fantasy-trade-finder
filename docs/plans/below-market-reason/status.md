# Status — below-market-reason

```project-status
{
  "status": "built-unmerged",
  "updated": "2026-09-02",
  "summary": "below market reason",
  "evidence": "Carried forward as the last documented disposition, not a fresh production audit. Prior index merge corrections take precedence over older pre-merge notes. Last documented index disposition: **built, unmerged** · 2026-09-02 **built, unmerged** · 2026-09-02 — One-line card reason when the give side's headliner is a player the user's OWN board prices below the market — `You rank {name} below the market — that gap is what this trade cashes in.` — because that gap is why the engine picked him (feedback #350 / Q-035, the operator's Davante Adams case). Knob `reason_below_market_frac` (default 0 = off, wire byte-identical — golden captured on `origin/main` @ `02d2eac2`, re-verified against `e16bb487`, the tip the branch is rebased on); rides the existing `TradeCard.reasons` field both clients already render, gated on `trade_math.human_explanations`. Presentation only: no deck output moves at any value (property-tested). [scope](scope.md) · [code-walk](code-walk.md) · [results](results.md) · harness `measure_below_market.py`. Arm A excludes it. Built on `claude/below-market-reason`; the lead ships.. Prior row preserved at ../../reviews/2026/2026-09-06-project-status-migration/plans-index.md."
}
```
