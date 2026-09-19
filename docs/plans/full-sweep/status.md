# Status — full-sweep

```project-status
{
  "status": "active",
  "updated": "2026-08-22",
  "summary": "full sweep",
  "evidence": "Carried forward as the last documented disposition, not a fresh production audit. Prior index merge corrections take precedence over older pre-merge notes. Last documented index disposition: **active** · 2026-08-22 **active** · 2026-08-22 — Score every leaguemate and rank the deck globally: [plan](plan.md) + [scope](scope.md). Both opponent loops in `backend/trade_service.py` stop at `global_target = max(30, max_per_opponent * 6)`, and because visit order is fixed the SAME five leaguemates are never scored on any refresh — measured at 5 of 13 and 7 of 13 absent across 6–11 refreshes by the 2026-08-22 trade-model second read §03 (that report is **not in the repo**; the plan carries its numbers). Flag `trade.full_sweep` skips the early exit in both loops; `_dedup_and_sort` already ranks the whole collected set, so no new ranking code. Adds the `exploration_base_per_opp` knob (default 5.0) in place of the hardcoded `server._EXPLORATION_BASE_PER_OPP`. Decision record: **D-154** — threads rejected (GIL), latency work deferred to a phase-2 plan, deck size stays the operator's `bakeoff_deck_limit` dial. Ships **dark**; graduation is the operator TestFlight checklist in [scope](scope.md) §3, UNRUN. Built on `claude/full-sweep-0822-a1c3`.. Prior row preserved at ../../reviews/2026/2026-09-06-project-status-migration/plans-index.md."
}
```
