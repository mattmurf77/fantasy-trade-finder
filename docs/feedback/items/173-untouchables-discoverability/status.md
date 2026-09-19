# #173 — Untouchables flag discoverability · status

**State:** SHIPPED (2026-07-25, branch `teardown-remediation`, #156 finish batch).

**Feedback:** tester asked for an "untouchables flag", unsure if it exists.

## What already existed (the discoverability gap)

The feature has existed since FB-95 (`asset_prefs`, flag
`trade.preference_lists` — **ON** in prod):

- **Backend:** `GET/POST /api/league/asset-prefs`
  (`{untouchables:[], targets:[]}`; `list:'untouchable'|'target'|'none'`).
  Untouchable players are dropped from the give pool at the source in
  every generator, so they are never offered from the user's roster.
- **Mobile — marking:** long-press a give-side player on any trade card
  (Trades deck), or — with `ux.player_context_menu` on — the shared
  player context menu and the visible lock toggle in the give-side row.
- **Mobile — visibility:** UNTOUCHABLE badge on marked give-side card
  rows; count in the hub's Trade DNA panel.

The gap: nothing LISTED your untouchables or let you remove one without
re-finding the player on a card — hence the tester not knowing it exists.

## What shipped (hub surfaces only — this agent's ownership)

- The hub Trade DNA panel's **Untouchables count row is now a button**
  (testID `finder-hub.dna.untouchables`, "Manage" affordance, gated on
  `trade.preference_lists`) opening a management sheet:
  - lists each untouchable by name + position (ids resolved through the
    universal value pool, same source as the swap sheet; unresolvable ids
    degrade to "Player <id>");
  - per-row **Remove** (`finder-hub.untouchables.remove.<player_id>`,
    `POST asset-prefs list:'none'`, invalidates `['asset-prefs', league]`
    so the deck's lock states update too);
  - how-to-add copy pointing at the existing card long-press path (no
    duplicate player picker was built — adding stays contextual, per the
    "reuse, don't invent" rule).
- The count itself renders correctly (it already did — `assetPrefsQuery`
  → `untouchables.length`; verified unchanged).

## Where

`mobile/src/screens/TradeFinderHubScreen.tsx` (row + sheet + remove
mutation). No backend change.

## Verification

`tsc --noEmit` clean; backend suite 1086 passed, 1 skipped.
