# PRD FB4-59 — Single-format gate error on TradesHome

**Feedback #59 (TradesHome, polish):** "I'm assuming that trading unlocks for all leagues once you go
through the initial gate. I would like to add an error if a user has only set ppr or only set
superflex. The error should tell them exactly that and give them two options: copy f[rom the other
format] …"

## Context to discover FIRST
- The app supports two scoring formats: `1qb_ppr` and `sf_tep` (see `mobile/src/shared/types.ts`
  `ScoringFormat`, and the Tiers "Copy tier list from <other format>" flow in `TiersScreen.tsx`
  which already calls `copyTiersFromFormat(from, to)` from `mobile/src/api/league.ts`).
- Trading requires the user to have established rankings/tiers for the league's format. The feedback:
  a user who has set up only ONE format hits Trades for a league in the OTHER format and gets nothing
  useful. We should detect that and explain it, offering a fast fix.

## Requirement
On the Trades home, when the user is trying to trade in a format they have NOT set up (only the other
format is set), show a clear, friendly error/empty-state that:
1. States exactly the problem — e.g. "You've set up your **SF TEP** rankings but not **1QB PPR**, which
   this league uses."
2. Offers two actions:
   - **Copy from <the format they DID set>** → calls the existing `copyTiersFromFormat(setFormat,
     neededFormat)` path (reuse the confirm + mutation pattern already in `TiersScreen.tsx`), then
     refreshes so trading unlocks.
   - **Set up <needed format> manually** → routes the user to the ranking flow (Rank/Tiers) for the
     needed format.

## User story
I open Trades for my PPR league but I only ranked Superflex. Instead of an empty/broken screen, I see
"You haven't set up 1QB PPR yet" with a "Copy from SF TEP" button — one tap and I'm trading.

## Acceptance criteria
- [ ] Detects the "only one format configured, viewing the other" state using existing session/league
      data (`mobile/src/state/useSession.ts` `activeFormat`, and whatever flag marks a format as
      established — check tiers-status / rankings emptiness; do NOT add a backend route).
- [ ] Renders a dedicated message naming BOTH the format the league needs and the one the user has.
- [ ] "Copy from <other format>" reuses `copyTiersFromFormat` + the existing confirm Alert + cache
      invalidation pattern; on success the Trades content loads (gate cleared).
- [ ] "Set up manually" navigates to the ranking entry for the needed format.
- [ ] When both formats are set (normal case) nothing changes — no regression to TradesHome.
- [ ] tsc clean.

## Implementation notes — OWNERSHIP
- Owns the **TradesHome / trades-gate path only**: `mobile/src/screens/TradesScreen.tsx` (and, if a
  separate gate/empty-state component exists, that). MAY READ but must NOT edit `TiersScreen.tsx`
  (Agent T owns it) — copy the `copyTiersFromFormat` usage pattern, don't share edits.
- If the precise "is this format established?" signal is unclear, READ `mobile/src/api/rankings.ts`
  (`getTiersStatus`) and `mobile/src/api/league.ts`; pick the existing signal that best indicates an
  unconfigured format. Keep the detection conservative — only show the error when you're confident a
  format is genuinely unset, never on a transient loading state.
