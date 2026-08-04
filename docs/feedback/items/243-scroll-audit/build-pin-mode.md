# #243 — Pin-Mode Collapsed Controls (V1) — Build Notes

Implements the operator-approved design "Pin-mode collapsed controls V1" from
`mockups/polish-lab-2026-08/pin-mode-collapsed-controls.html` (frames B1/B2) —
the #1-ranked lever in the #243 scroll audit (`trades-surfaces.md` §A,
single-pin state).

## What changed

`mobile/src/screens/TradesScreen.tsx` only (plus the screens CLAUDE.md registry
row and this doc):

- **Collapsed by default (B1):** in single-pin featured-trade mode
  (`!firstRun && singlePin` — the same condition #241 uses to suppress the
  deck/Find button/progress strip), the full Controls Card (outlook row +
  fairness row + two-column pin board, ~286pt) no longer renders. In its place:
  a single one-line row — position dot + "Pinned: **\<player name\>**" + an ice
  "Edit" text button — in a thin card shell (`pinSummaryCard`: ink-1 surface,
  hairline `ink.line` border, `radii.md`, `minHeight: 44` tap target,
  `space.md`/`space.xs` padding). Chalkline tokens throughout; the chalkline
  `Card` primitive itself isn't used for the shell because its fixed `space.lg`
  body padding would defeat the collapse.
- **Edit expands in place (B2):** tapping Edit sets `pinEditOpen` and renders
  the exact existing full `<Card>` — outlook row, fairness toggle, lane pills,
  two-column TRADE AWAY / TRADE FOR pin board, all controls and testIDs
  unchanged — with one added header row inside the card: `TickLabel`
  "Editing pin" + an ice "Done" text button that collapses back to the
  one-liner. The header row renders only in single-pin mode.
- **State reset:** `pinEditOpen` starts `false` and a `useEffect` keyed on
  `pinKey` (the same reset trigger as the #216 featured-window state) resets it
  to collapsed on entering the mode, pin change, or unpin.
- **Zero changes outside the single-pin branch:** classic deck, first-run,
  multi-pin, and team mode all fail the `!firstRun && singlePin` collapse
  condition and render the full Controls Card exactly as before; the "Editing
  pin"/Done header condition also fails there, so those modes are
  byte-identical in render output.

## New testIDs

| testID | Element |
|---|---|
| `trades.pin-summary` | collapsed one-line pin summary row |
| `trades.pin-summary.edit` | ice "Edit" text button (expands) |
| `trades.pin-summary.done` | ice "Done" text button in the expanded card header (collapses) |

## Before / after (audit's nominal math, minimal 1-idea case)

| | Before | After (collapsed default) |
|---|---|---|
| Controls chrome | ~286pt Controls Card | ~44pt pin-summary row |
| Cumulative before Featured Trade Window | ~476pt | ~234pt |
| Page total vs 658pt viewport | ~1497pt (overflow ~839pt) | ~1255pt (overflow ~597pt) |

Saves ~242pt — in line with the audit's cited "~230–250pt, biggest single
lever." The featured trade (the mode's hero content) now starts rendering
above the fold instead of ~476pt down. Expanded state costs what today's card
costs (plus the ~26pt header row) — intentional; only the default state is
being made cheap. The audit's other single-pin levers (verdict-paragraph
disclosure, AssetIdeasPanel row cap, padding/gap trims) remain open items.

## Verification

- `cd mobile && npx tsc --noEmit` — clean (exit 0).
- Code inspection: collapse branch and Done header are both gated on
  `!firstRun && singlePin`; no other mode's JSX path changed. Existing
  testIDs (`trades.find-btn`, `trades.board.*`, `trades.progress-strip`,
  fairness/outlook controls) untouched inside the expanded card.
- Simulator QA (pin one player → collapsed row shows; Edit → full card with
  Done; Done → collapsed; unpin/re-pin → collapsed again) still to be run in
  the main session as part of the #243 batch QA.
