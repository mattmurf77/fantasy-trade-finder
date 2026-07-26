# #186 — Keep one side, see other options · status

**State:** SHIPPED (2026-07-25, branch `teardown-remediation`, #156 finish batch).

**Feedback:** "If a user sees a player offered away or offered to receive
that they like but they don't love the other side, they should have a
button on both sides that gives the option to see other options for the
side they like."

## What shipped

Per-side **"Keep · more offers"** action on the swipe-deck trade card
(`mobile/src/components/TradeCard.tsx`, swipe variant only — match cards
unchanged). testIDs **`trade-card.keep-give`** / **`trade-card.keep-receive`**;
a11y labels spell out the semantics ("Keep the players you send and see
other returns" / "Keep the players you get and see other offers").

Deliberately a shortcut into the existing FB-47 targeting flow — nothing
new was invented:

- **Keep give side** → `useFinderTargets.setSide('give', card.give_players)`
  (replaces any prior give pins). With 2+ players, the #174 package toggle
  (default ON) sends `pinned_give_mode:'all'`, so the kept side stays
  together in every regenerated card.
- **Keep receive side** → `setSide('receive', card.receive_players)` —
  regenerated cards must return ≥1 of them (the existing pinned-receive
  semantics; the backend has no receive-side 'all' mode — noted honestly
  in the button copy by not promising the full side).
- Either action commits pending pass-undo state, resets the deck
  (`resetDeckForNewTargets`) and immediately kicks `generateTrades` — the
  mutation reads pins from the store (`useFinderTargets.getState()`), not
  the render closure, so the same-tick regenerate always sends the fresh
  lists. Analytics: `trade_keep_side_tapped {side}`.

Gating: rendered only when `trade.finder_targeting` is on (the pinning
machinery it rides on). The pinned side is visible + editable in the
normal targeting UI (chips / two-column board) afterward, so the user can
see and undo what got pinned.

## Where

`mobile/src/components/TradeCard.tsx` (`keepSlot`, props `onKeepSide`),
`mobile/src/screens/TradesScreen.tsx` (`handleKeepSide`, SwipableTopCard
pass-through), `mobile/src/state/useFinderTargets.ts` (`setSide`).

## Verification

`tsc --noEmit` clean; backend suite 1086 passed, 1 skipped (constraint
semantics covered by the #174 tests).
