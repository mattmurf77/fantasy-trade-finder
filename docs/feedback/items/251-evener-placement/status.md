# #251 — "Recommended to even it" placement

**Report (2026-08-05, screen TradeDeck, severity bug):** "Recommended to
even it should be right underneath the trade window itself. Above the
fairness summary."

**Status: built (2026-08-05, branch teardown-remediation).**

## Investigation — where the rows actually live

The screen field says TradeDeck, but the TradeDeck/featured-trade surface
itself renders **no** "Recommended to even it" block anywhere
(`FeaturedTradeWindow` → read-only `TradeCard` → `TradeValueBar`; the only
"even it" copy there is the value bar's collapsed "Why?" sentence). The
`EvenerRows` component mounts in exactly two places:

1. **`InLeagueCalculator`** (In-league mode — where the featured window's
   "Edit in calculator" hand-off lands): rendered **below** the
   `LeagueVerdict` fairness summary, i.e. trade sides → verdict → eveners.
   This matches the operator's complaint word for word ("trade window" =
   the give/receive builder, "fairness summary" = the verdict card).
2. **`ConsensusVerdictCard`** (open calculator, live mode): eveners render
   inside the verdict card, under the totals/adjustments.

## What shipped

Pure JSX reorder in `InLeagueCalculator.tsx` only: the `EvenerRows` block
moved above the `LeagueVerdict`/evaluating block, so the order is now
**trade window (You send / You receive) → Recommended to even it →
fairness summary**. Same render condition, same handler (`addEvener`),
no logic changes. `ConsensusVerdictCard` (live mode, a different surface
the operator didn't name) is untouched.

Note for triage: if the operator meant eveners should ALSO appear under the
featured-trade window on TradeDeck itself, that's a new feature (the
asset-ideas payload carries no `eveners`), not a reorder — flag it as a
follow-up item if the complaint recurs.

## Verification

- `cd mobile && npx tsc --noEmit` clean.
- testIDs unchanged (`calc.evener.<id>` / `calc.evener-add.<id>`).
