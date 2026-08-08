# #253/#254/#255/#256/#259 — status

**State:** BUILT, static verification only. Worktree branch
`agent/253-outlook-cleanup` (off `teardown-remediation`). Not merged, not
pushed. Runtime verification is owned by the batch QA round — this agent did
not boot the simulator, run Maestro, or start Flask (deliberate: parallel
agents contending one simulator has broken past runs).

**Ships live, no flag.** The changes are visibility/copy/ordering plus one
additive picker; every existing flag configuration keeps a working path (see
#254 below).

---

## What shipped

### #253 — outlook display order
`TradeDnaSheet.OUTLOOK_CARDS` reordered from Rebuilding · Contending · All-in ·
Tanking to the canonical **All-in → Contending → Rebuilding → Tanking** ladder.
`OutlookSheet.OUTLOOKS` and the web `outlook-overlay` already complied and were
only comment-pinned; `OutlookBiasReceipt.LEAN` (a lookup, not a rendered list)
was reordered to match so the four read the same way in every file.
**Stored enum values untouched** — `championship` / `contender` / `rebuilder` /
`jets` still round-trip through `POST /api/league/preferences`, and every
`dna.outlook.*` testID is unchanged.

### #254 + #255 — one outlook surface
`OutlookBiasReceipt` now exports its own visibility predicate
`outlookReceiptCovers(directionOn, declared, inferred)` and uses it internally;
`TradesScreen` computes `outlookReceiptShown` from it and gates the
controls-card "Outlook · Edit" row on `!outlookReceiptShown`.

Result per configuration — exactly one outlook surface in all of them:

| Configuration | Surface |
|---|---|
| Guided landing, `trade.outlook_direction` on, directional outlook | minimized bar only |
| `trade.outlook_direction` off | controls-card row only |
| Outlook `not_sure` / none resolved | controls-card row only |
| Classic home (`trades.finder_hub` off — no finder mode) | controls-card row only |

Because the row was the deck's only entry into `OutlookSheet`, this also
removes the second editor for the same record: on the landing `TradeDnaSheet`
(outlook + Chasing/Shopping + untouchables + #236 autosave) is the single
editor, and it is a strict superset of `OutlookSheet`'s outlook +
acquire/trade-away plays.

### #256 — label
Lane pill **"Window moves" → "Team-fit moves"**. Web filter button matches; the
web card chip reads `TEAM-FIT MOVE`. Recorded in
`docs/cross-client-invariants.md` beside the lane enum, which is unchanged
(`window` / `value`, `lane-chip--window` / `lane-chip--value`).
`docs/glossary.md` has no "window move" entry — nothing to update there.
Extension has no lane UI. Rejected "Win-now moves": the `window` lane is
win-now for a contender and youth+picks for a rebuilder, so it would be false
for half the users.

### #259 — untouchables addable from your roster
The #173 management layer (list + Remove) gains **"Add from your roster"**,
opening a roster picker as a third layer inside the same `TradeDnaSheet` Modal:
search + value-sorted rows (position dot, name, `POS · TEAM`) + per-row
Protect. Pool = the caller's own roster (`getLeagueRosters` filtered to
`owner_id === userId`) resolved through the layer's already-open
`['calc-values']` value pool; already-protected players are filtered out.
Writes go through the shipped `setAssetPref(leagueId, id, 'untouchable')` lane
and invalidate `['asset-prefs', leagueId]`, so the count, the list and the
deck's lock states all move together. The layer's how-to copy now leads with
the picker and keeps the long-press path as the secondary route.

---

## Deliberately NOT deleted (decisions, not oversights)

1. **The FB-47 "Target players" section** (`Target players` /
   `Trade away | Acquire` pills / `Add player` / SEND–GET chips). #255's wording
   ("trade away or acquire") also matches this section, but it is **player-level
   pinning** (`pinned_give_players` / `pinned_receive_players`), not the
   outlook's position-level plays. Nothing in the minimized bar or the DNA sheet
   can pin a player, so deleting it would remove a capability rather than a
   duplicate. **If the tester meant this section, it needs its own item** — the
   right fix there is probably "it belongs to Player mode, not the guided deck",
   which is a mode-scoping decision, not a de-dup.
2. **`OutlookSheet` stays mounted.** Two callers survive on this screen (the
   inferred-outlook confirm banner's Change and the `ux.outlook_inline_default`
   `trades.outlook-set-banner`), and it is still the outlook surface on the
   classic flag-off home. Only the controls-card route into it is gone.
3. **The inferred-outlook confirm banner stays** — it carries information
   neither bar has ("Your roster reads as Contender" + one-tap Confirm).
4. **The unrouted `TradeFinderHubScreen`'s own `OUTLOOK_CARDS`** was left in the
   old order. That screen is dead code awaiting the cleanup pass #246 already
   flagged; touching it would put a diff on a file nothing renders.

---

## Files touched

| File | Why |
|---|---|
| `mobile/src/components/TradeDnaSheet.tsx` | #253 card order; #259 roster picker layer (query, mutation, layer, styles) |
| `mobile/src/components/OutlookBiasReceipt.tsx` | #254 exported `outlookReceiptCovers` + internal use; #253 lookup order |
| `mobile/src/components/OutlookSheet.tsx` | #253 order comment-pin (list already complied) |
| `mobile/src/screens/TradesScreen.tsx` | #254/#255 row gate (`outlookReceiptShown`); #256 pill label |
| `web/index.html` | #256 lane filter button label |
| `web/js/app.js` | #256 lane card chip label |
| `docs/cross-client-invariants.md` | #256 display labels recorded beside the lane enum |
| `mobile/src/screens/CLAUDE.md` | new row documenting the cleanup |
| `mobile/src/components/CLAUDE.md` | `OutlookSheet` row + new testID tranche |
| `docs/feedback/items/253-outlook-cleanup/{prd,status}.md` | this |

No backend change, no schema change, no new route, no flag change.

## Verification performed

- `mobile/node_modules` is not present in this worktree; symlinked the main
  checkout's `mobile/node_modules`, ran `./node_modules/.bin/tsc --noEmit`, and
  removed the symlink. **Output: clean — zero diagnostics, exit 0.**
- Grep proofs:
  - outlook order: `championship` → `contender` → `rebuilder` → `jets` in
    source order in `TradeDnaSheet.tsx`, `OutlookSheet.tsx`,
    `OutlookBiasReceipt.tsx`.
  - `outlookReceiptCovers` has exactly two call sites (the receipt itself and
    `TradesScreen`'s `outlookReceiptShown`); the controls-card row is gated on
    `!outlookReceiptShown`.
  - **zero** occurrences of `Window moves` / `WINDOW MOVE` remain in
    `mobile/src`, `web`, `extension` (the only hit is the explanatory comment).
  - `Team-fit moves` present in the mobile pill + `web/index.html`;
    `TEAM-FIT MOVE` in `web/js/app.js`.
  - all six `#259` testIDs present.
- `mobile/.maestro` contains **no** flow referencing "Window moves" or the
  controls-card "Outlook" copy, so no existing flow is broken by these changes.

## QA checklist for the runtime round

Maestro flow list is in `prd.md` §4 (R1–R10). Manual spot checks to pair with it:

- [ ] **R1** Acquire tab (guided landing): the minimized bar renders and there
      is **no** second "OUTLOOK" TickLabel in the controls card.
- [ ] **R2** Bar → Change → DNA sheet: cards read All-in, Contending,
      Rebuilding, Tanking **in that order**.
- [ ] **R3** Pick Rebuilding → Done → reopen: still Rebuilding (the #236
      autosave still writes the right enum after the reorder).
- [ ] **R4** `trade.outlook_direction` **off**: the controls-card Outlook row is
      back and its Edit opens `OutlookSheet`. Same check for a `not_sure`
      outlook. **This is the regression that matters most** — the fix must not
      leave any configuration with zero outlook surfaces.
- [ ] **R5** Deck with lanes: pills read "Team-fit moves" / "Value moves";
      filtering and re-tap-to-clear behave as before.
- [ ] **R6/R7** DNA sheet → Manage → **Add from your roster**: only your own
      players, already-protected players absent, search filters, Protect adds,
      count increments, Done returns to the list, Remove still works.
- [ ] **R8** After adding, run Find a Trade: the protected player never appears
      on a give side.
- [ ] Sheet layering on a real device: DNA sheet → untouchables → roster picker
      → hardware/gesture back pops **one layer at a time** (roster → list →
      sheet). This is the one behavior static checks cannot cover.
- [ ] Roster picker in an ESPN/MFL-linked league (no Sleeper roster payload):
      confirm it renders the honest empty state rather than a spinner.
- [ ] **R9/R10** Classic flag-off home and the set-outlook banner still reach
      `OutlookSheet`.
- [ ] Web: lane filter button + card chip read the new label; filtering still
      works (the `data-lane="window"` value is unchanged).
