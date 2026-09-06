# Status — pick-yoy-floor

```project-status
{
  "status": "active",
  "updated": "2026-08-24",
  "summary": "pick yoy floor",
  "evidence": "Carried forward as the last documented disposition, not a fresh production audit. Prior index merge corrections take precedence over older pre-merge notes. Last documented index disposition: **active** · 2026-08-24 **active** · 2026-08-24 — One clamp re-asserting [D-079](../../../living-memory/DECISIONS.md)'s flat-firsts ruling under D-146's `market_slots` pricing, as **D-161**: [plan](plan.md) · [scope](scope.md). Since market pricing became unconditional an owned pick rides DynastyProcess's curve, which carries DP's OWN year discount — so a 2027 1st served at 1,751 and a 2028 1st at 1,459 against a 2,184.6 current-year mid, exactly the Q-018 risk, and a tester was shown A.J. Brown + depth for Isaiah Likely + three future firsts. Operator re-ruling 2026-08-24: *\"The ideal solution is the D-079 ruling.\"* The fix is one `max()` at step 2 of `pick_values.priced_pool_value`, for **round 1 only** and only past the current draft class (read out of DP's own per-slot grid, not a new clock), behind `model_config` knob **`market_r1_yoy_floor`** (default 1.0; **0 = pure market, byte-identical, deploy-free revert**). Rounds 2–4, the per-slot step 1, `tier_ladder` and the stored-ladder fallback are all untouched. Evidence: `backend/tests/test_pick_yoy_floor.py` (8 sabotage-proven tests, monkeypatched market map, no network). Built on `claude/pick-yoy-floor-0824`.. Prior row preserved at ../../reviews/2026/2026-09-06-project-status-migration/plans-index.md."
}
```
