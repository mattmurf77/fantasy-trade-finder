# FB-193 — "Listed as both chasing and shopping QB" — status

**Fixed 2026-07-27** (branch `teardown-remediation`).

**Root cause:** the Trade DNA panel (TradeFinderHubScreen) merged explicit prefs
(`acquire_positions`/`trade_away_positions`) with roster-profile recommendation
chips (`position_needs`/`position_surplus`) but only de-conflicted a
recommendation against the SAME side's explicit list. Explicitly shopping QB
while `analyze_roster_strengths` reported "thin at QB" (which shopping-your-QBs
naturally causes) rendered QB under Chasing (need chip) AND Shopping (explicit
chip). The backend analyzer itself cannot emit a position in both needs and
surplus (need threshold ≤ surplus threshold at every position, incl. the
superflex QB 2/2 boundary) — the merge was the whole bug; no backend change.

**Precedence rule** (now in `mobile/src/utils/dnaChips.ts`, a position appears
on at most ONE side): explicit prefs beat recommendations on both sides;
acquire beats shed (explicit∩explicit — "I want one" is the more actionable
instruction); need beats deep (rec∩rec, defensive only — analyzer can't emit
it; a starter shortfall is the more urgent signal).

**Tests:**
- `mobile/tests/check-dna-chips.js` (`npm run test:dna-chips`) — pins the
  invariant (exhaustive 16-combo sweep: sides disjoint, no position dropped)
  plus the operator repro, both tiebreaks, and chip ordering.
- `backend/tests/test_roster_profile.py::test_needs_and_surplus_mutually_exclusive`
  — pins the analyzer's exclusivity across 0..6 starters × all positions ×
  1QB/SF.
