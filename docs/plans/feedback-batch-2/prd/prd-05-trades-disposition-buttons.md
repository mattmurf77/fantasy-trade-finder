# PRD FB-05 — TradesHome ✓/✗ disposition buttons

**Feedback:** #34 · **Surface:** mobile · **Priority:** P1

## Requirement
On the Trades (Find-a-Trade) screen, add an explicit **✓ (accept/like)** and
**✗ (decline/pass)** button pair beneath the trade card as an alternative to the
swipe gesture — same outcome as swiping the card right/left.

## User story
As a manager browsing suggested trades, I can tap a ✓ or ✗ button under the card
to like or pass on a trade, instead of having to swipe — useful when swiping is
awkward or unclear.

## Acceptance criteria
- [ ] A ✓ and ✗ button pair renders under the top trade card on TradesScreen.
- [ ] Tapping ✓ performs the exact same action as a right-swipe (like/accept);
      tapping ✗ performs the same as a left-swipe (pass/decline) — same API call,
      same deck advance, same haptics/animation as the swipe path.
- [ ] Buttons are disabled/hidden when there's no card to act on (empty deck /
      loading) and during an in-flight disposition.
- [ ] Works with the existing fairness toggle + streaming deck; advancing to the
      next card behaves identically to swiping.
- [ ] `cd mobile && npx tsc --noEmit` clean.

## Implementation notes
- **Owns only** `mobile/src/screens/TradesScreen.tsx` (and may reuse existing
  swipe-handler functions there — wire the buttons to the SAME handlers the
  swipe gesture calls; do not duplicate the disposition logic).
- Match the app's button styling; place under the card without disturbing the
  swipe deck layout.
