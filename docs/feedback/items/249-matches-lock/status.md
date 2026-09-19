# #249 — Remove the lock button from the Matches screen

**Report (2026-08-05, screen Matches, severity bug):** "Lock button not
needed on the mutual matches screen."

**Status: built (2026-08-05, branch teardown-remediation).**

## What the lock button was

The S3 PRD-02 **untouchable "visible twin"** (flags `ux.player_context_menu`
+ `trade.preference_lists`): a 28px lock toggle in the give-side player-row
`rightSlot` of `TradeCard`, added so the long-press accelerator was never
the sole path to marking a player untouchable ("never offered from your
roster in trade ideas", `POST setAssetPref`). On Matches it appeared on
every YOU SEND row of both segments.

## What shipped

UI-only removal, mechanism intact:

- `TradeCard.tsx`: new optional `hideLockButton` prop (default false —
  every other mount, including the Trades deck, renders exactly as before).
  When set, the lock slot and its share of the rightSlot render condition
  are skipped.
- `MatchesScreen.tsx`: passes `hideLockButton` on **both** mounts (mutual
  `variant="match"` list AND the awaiting `variant="swipe"` list — the
  operator named the screen, and a lock on only one segment would be
  inconsistent).

Untouchable toggling **remains reachable on Matches** via: the long-press
player context menu ("Mark untouchable" / "Remove untouchable" — built by
the screen's own `menuActionsFor`, independent of the button), the
screen-reader custom action on each give-side row, and the UNTOUCHABLE
badge still renders on marked players. The Trades deck lock and the hub's
untouchables manager are untouched.

## Verification

- `cd mobile && npx tsc --noEmit` clean.
