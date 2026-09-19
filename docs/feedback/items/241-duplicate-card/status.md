# #241 — Second trade card under the single-pin idea list

**Status: fixed (worktree branch `teardown-remediation`, pending merge) — 2026-08-02**

Operator (build 68, bug): "I don't know why we're presenting a second trade
card underneath the other options."

## Root cause (confirmed)

Exactly what was suspected: the #216 build swapped the single-pin surface to
`FeaturedTradeWindow` + the "More trades" list but left the OLD swipe deck
(`styles.deckWrap`: peek card, `SwipableTopCard`, disposition buttons, empty
states) rendering unconditionally further down `TradesScreen`. With a deck in
state (pinned during/after a generate) the top deck card appeared as a
mystery second trade card below the idea rows. It was not the featured card
rendering twice.

## Fix

Per the approved mock (`mockups/polish-lab-2026-08/asset-ideas-layout-v3.html`),
in single-pin mode the featured window + idea list IS the page:

- The deck block is skipped when the featured surface is shown (the same
  `!firstRun && singlePin` condition that mounts it).
- The Find-a-Trade button and the job progress strip hide under the same
  condition — with no deck to render into, a generate would build invisible
  cards (the ideas sweep is pin-driven, no button needed).
- Multi-pin / no-pin / classic / team / guided modes render the deck exactly
  as before (condition is false there). Unpinning (or adding a second pin)
  restores the deck and button with state intact.

## Files

- `mobile/src/screens/TradesScreen.tsx` — only file changed

testIDs unchanged; `trades.find-btn` / deck ids still render in every
non-single-pin mode (smoke flows use the classic no-pin surface).

## Verification

- `cd mobile && npx tsc --noEmit` — clean
