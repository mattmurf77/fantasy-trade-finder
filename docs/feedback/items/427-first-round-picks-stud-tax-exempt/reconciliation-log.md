
## Orchestrator rulings 2026-09-08 (Phase 1 exit)

- Rule adopted as specced: first-round picks (generic `generic_pick_1_*` and owned round-1 ids) contribute face value on the multi-asset side; taxable subset keeps today's formula and cap; gen-v2's `consolidated_value` changes in step. Knob `stud_tax_exempt_first_round = 1.0` (≤0 byte-identical).
- (a) band width: informational; the report's example (two mid firsts vs a `firsts_2`-floor player) lands even; noted in the ship summary. (b) crown credit for ≥6000 players stays — it is the elite-player premium, not the pick tax; surfaced as a candidate follow-up. (c) heavy mode unchanged — confirmed.

## Orchestrator ruling 2026-09-08 (Phase 2 exit)

- Deviation 1 accepted: `trade_optimizer.py`, `trade_gen_fit.py`, `trade_breaker.py`, `trade_policy.py` are the PRD R-3 call sites; no other batch group owns them. Owned-paths list amended accordingly. Deviations 2–3 accepted (actual value pinned; knob-0 identity proven by the grid test + goldens at the pin).
