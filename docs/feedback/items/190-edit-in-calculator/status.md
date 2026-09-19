# #190 — Edit suggested trade in the calculator · status

**State:** SHIPPED (2026-07-25, branch `teardown-remediation`, #156 finish batch).

**Feedback:** "When a user wants to edit a suggested trade, it should
bring them to a replica experience as the manual calculator with the
suggested players... presented from the teams involved."

## What shipped

**"Edit in calculator"** action on the swipe-deck trade card (testID
`trade-card.edit-in-calc`, hint-tier row below the two sides; swipe
variant only). Tapping navigates to the existing `TradeCalculator` route
with a new `prefill` route param:

```
navigation.navigate('TradeCalculator', {
  prefill: { opponentUserId, giveIds, receiveIds }  // from the card
})
```

`TradeCalculatorScreen` (no prefill path existed; minimal route-param
support added, no restructuring):

- lands in **In-league mode** (`mode:'league'`) when `prefill` is present
  — the dual-board replica experience against the card's actual opponent;
- the persisted draft's stored mode no longer yanks a prefilled launch
  back to live/demo (guarded restore); list drafts still restore for
  manual visits;
- a NEW prefill arriving on an already-mounted screen re-asserts league
  mode, and a `key` on `InLeagueCalculator` remounts it with the new
  package (navigate() to a mounted route only swaps params).

`InLeagueCalculator` (another agent's file — touched at the agreed
"trivially accept params" level, ~10 lines): three optional props
(`initialOpponentId` / `initialGiveIds` / `initialReceiveIds`) used as
useState initializers, plus a first-run guard (prev-opponent ref) on the
opponent-change effect so the mount run no longer wipes the prefilled
receive side — that mount run was always a no-op before prefill existed,
so existing behavior is unchanged. Everything downstream (evaluate Mode B,
suggestions, Send in Sleeper) is untouched and works on the prefilled
package.

The existing swap-sheet in-place edit on the deck card **stays** — this
is the full-editor path beside it.

Analytics: `trade_edit_in_calculator_tapped`.

## Where

`mobile/src/components/TradeCard.tsx` (`onEditInCalculator` prop + row),
`mobile/src/screens/TradesScreen.tsx` (`handleEditInCalculator`),
`mobile/src/screens/TradeCalculatorScreen.tsx` (prefill param),
`mobile/src/components/InLeagueCalculator.tsx` (initial-value props).

## Verification

`tsc --noEmit` clean; backend suite 1086 passed, 1 skipped (no backend
change in this item).
