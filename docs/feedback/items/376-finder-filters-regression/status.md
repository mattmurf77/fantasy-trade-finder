# FB-376 + FB-379 + FB-394 — finder filters / outlook & prefs regression (Group A canonical)
- **Status:** planned 2026-08-24 — PRD ready
- **Covered:** #376, #379, #394 (+#333 verified delivered on the merged calculator, `InLeagueCalculator.tsx:784-824` — no work; see prd.md §5)
- **Path:** fast-track bug (mobile-only); stayed fast-track — plan found no layout work
- Docs: [plan.md](plan.md) → [prd.md](prd.md) + [scope.md](scope.md) (analytics: existing `outlook_saved` covers it; no schema/API/flag changes)
- Batch plan: [346-quickset-tier-drop/plan.md](../346-quickset-tier-drop/plan.md)

History that matters: #376's first diagnosis (2026-08-20, in
[374-partners-copy-and-finder-conditions](../374-partners-copy-and-finder-conditions/status.md))
found the filters hidden by the `trades_home_inline` experiment's
`TradeHomeUtilityRow` swap; that fix merged. The #384 merged-calculator
rebuild (1.16.0→1.16.2) reshaped TradesHome again, and #394 (2026-08-24,
1.16.2) reports outlook & preferences still/again completely missing —
operator calls it the most critical bug. #379 rules the top-tab placement
out: filters belong inside the Find-a-Trade page, minimized by default.
Check #360/#361 ("positions I'm NOT looking for") as a candidate rider on
this surface — flagged in the batch plan, not committed.
