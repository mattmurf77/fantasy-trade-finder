# #253 / #254 / #255 / #256 / #259 — TradesHome outlook & untouchables cleanup

**App:** v1.11.0 · **Screen:** `TradesHome` (`mobile/src/screens/TradesScreen.tsx`)
**Owner region:** the outlook/window area of TradesScreen + `components/OutlookSheet.tsx`,
`components/OutlookBiasReceipt.tsx`, and the DNA sheet that hosts the outlook editor
(`components/TradeDnaSheet.tsx`).
**Date:** 2026-08-08

One tester pass produced five reports that all land in the same strip of the
Acquire tab: the outlook receipt, the controls card, the lane pills and the
untouchables layer. They are fixed together because #254 and #255 are two
readings of the same duplication.

---

## 1. Background — where outlook lives today

Since **#246** (guided-first landing) `TradesHome` renders the deck directly with
`mode:'guided'`, so `finderMode` is always set on the tab's landing. That mount
carries:

| Surface | Source | What it shows |
|---|---|---|
| **Minimized bar** (`trades.outlook-receipt`) | `OutlookBiasReceipt` | "Leaning young + picks — you're Rebuilding · **Change**" → opens `TradeDnaSheet` |
| **Controls-card row** | `TradesScreen` inline | `TickLabel` "Outlook" + `cap(team_outlook)` + **Edit** → opens `OutlookSheet` |
| **Editor A** | `TradeDnaSheet` | outlook cards + Chasing/Shopping position rows + untouchables |
| **Editor B** | `OutlookSheet` | outlook rows + "Positions you want to acquire" / "…willing to trade away" |

Both bars state the same fact and both editors edit the same three
`league_preferences` fields (`team_outlook`, `acquire_positions`,
`trade_away_positions`). That is the whole of #254 and #255.

---

## 2. Items

### #253 (bug) — outlook order is weird

**Repro:** Acquire tab → tap **Change** on the minimized bar → the DNA sheet's
"My team is…" grid reads Rebuilding · Contending · All-in · Tanking.

**Root cause:** `TradeDnaSheet.OUTLOOK_CARDS` was authored in the order the #212
mock happened to draw it. No other surface agrees: `OutlookSheet.OUTLOOKS` and the
web `outlook-overlay` (`web/index.html`) are already
`championship → contender → rebuilder → jets`.

**Fix:** reorder `OUTLOOK_CARDS` to the canonical ladder
**All-in → Contending → Rebuilding → Tanking**, with a comment naming #253 so the
array is not reshuffled again. **Stored enum values are untouched** — this is a
presentation-order change only (`championship` / `contender` / `rebuilder` /
`jets` still round-trip through `POST /api/league/preferences`). `OutlookSheet` and
web get the same comment; no reorder needed there because they already comply.

**Verify:** grep proof that every list of the four outlooks reads championship,
contender, rebuilder, jets in source order.

---

### #254 (bug) — outlook listed twice

**Repro:** Acquire tab, any league with a directional outlook. The minimized bar
says "…you're Rebuilding"; ~200pt lower the controls card says "OUTLOOK /
Rebuilder / Edit".

**Root cause:** the controls-card row predates #231/#246. `OutlookBiasReceipt` was
added above it and nothing removed the older row.

**Fix:** the minimized bar is the one that belongs (it names the *bias*, not just
the label, and its Change reaches the full DNA editor). The controls-card outlook
row is suppressed **exactly when the bar is on screen**.

The bar is self-contained and can legitimately render `null` (flag
`trade.outlook_direction` off, or the resolved outlook is `not_sure`/absent). So
rather than deleting the row unconditionally — which would leave configurations
with *no* outlook surface — `OutlookBiasReceipt` exports its own visibility
predicate and `TradesScreen` gates the row on it:

```
outlookReceiptShown = !!finderMode && outlookReceiptCovers(directionOn, declared, inferred)
```

One table, two consumers, so the bar and the row can never both appear and can
never both vanish.

**Verify:** with `trade.outlook_direction` on and a declared outlook, exactly one
"Outlook" surface renders; with the flag off, exactly one (the row).

---

### #255 (polish/bug) — "the entire section with outlook plays to trade away or acquire feels redundant to the minimized bar"

**Repro:** same screen. The controls card's outlook row is the only entry into
`OutlookSheet`, whose body is "Positions you want to acquire" + "Positions you're
willing to trade away" — i.e. the outlook's *plays*. The minimized bar's Change
opens `TradeDnaSheet`, whose Chasing/Shopping rows write the same two fields.

**Root cause:** two editors for one record, reachable from two bars, on one screen.

**Fix:** absorbed by the #254 gate. Suppressing the row also removes the deck's
only route into `OutlookSheet`, leaving `TradeDnaSheet` as the single outlook +
position-preference editor on this screen. `TradeDnaSheet` is a strict superset
(outlook, Chasing, Shopping, **plus** untouchables and #236 autosave), so nothing
the sheet could do is lost.

**Deliberately NOT deleted** (recorded here so it is a decision, not an oversight):

1. **`OutlookSheet` itself stays mounted.** Two other callers survive on this
   screen — the inferred-outlook confirm banner's "Change" and the
   `ux.outlook_inline_default` "Set outlook" banner — and it remains the outlook
   surface in the flag-off classic home. It is no longer reachable from the
   controls card.
2. **The FB-47 "Target players" section stays** (`Target players` /
   `Trade away | Acquire` pills / `Add player` / the SEND/GET chips). Despite the
   shared "trade away or acquire" wording it is **player-level pinning**
   (`pinned_give_players` / `pinned_receive_players`), not the outlook's
   position-level plays. Nothing in the minimized bar or the DNA sheet can pin a
   player, so removing it would delete a capability rather than a duplicate.
3. **The inferred-outlook confirm banner stays** — it carries information neither
   bar has ("Your roster reads as Contender" + one-tap Confirm).

---

### #256 (polish) — "Window moves is a weird label"

**Repro:** Acquire tab → controls card → lane pills read `Window moves` /
`Value moves`.

**Root cause:** "window" is the engine's word. `docs/cross-client-invariants.md`
defines the lane enum as "`window` = the trade moves roster composition toward the
user's contend/rebuild window". A dynasty player never says "window move".

**The label:** **`Team-fit moves`** (web card chip: `TEAM-FIT MOVE`).

Rationale, and the options rejected:

| Candidate | Verdict |
|---|---|
| **Team-fit moves** | **Chosen.** Direction-neutral, plain English, and pairs grammatically with the existing "Value moves" — the pair reads "does this fit my team" vs "is this good value". |
| Win-now moves | Wrong. The `window` lane is win-now for a contender and youth/picks for a rebuilder; this label lies to half the users. |
| Plan moves / Direction moves | Vague; "plan" is not a term the app uses anywhere. |
| Fits my team | Reads well alone but breaks the pill pair's grammar next to "Value moves". |

**Scope:** presentation only. The `lane` enum values `window` / `value` and the
CSS class names `lane-chip--window` / `lane-chip--value` are unchanged — they are
cross-client invariants and the backend classifier keys on them.

**Locations:** `mobile/src/screens/TradesScreen.tsx` (pill row),
`web/index.html` (lane filter button), `web/js/app.js` (`renderTrades` card chip),
`docs/cross-client-invariants.md` (record the display label beside the enum).
`docs/glossary.md` has no "window move" entry — nothing to update there; the
invariants doc is where the enum is defined, so the label note goes there.
Extension: no lane UI, no occurrences.

---

### #259 (bug) — "Should be able to select players from your roster as untouchable in the untouchable section"

**Repro:** Acquire tab → minimized bar **Change** → DNA sheet → **Manage** next to
Untouchables. The layer lists what is already protected and offers Remove; adding
is only possible by long-pressing a give-side player on a trade card that happens
to contain them.

**Root cause (from `docs/feedback/items/173-untouchables-discoverability/`):** #173
built the *list + remove* half on purpose and left adding contextual — "no
duplicate player picker was built — adding stays contextual, per the 'reuse, don't
invent' rule". The gap that leaves: a player who is never offered in a trade idea
(because he is already untouchable, or simply never surfaces) can never be
protected, and the copy tells the user to go hunt for a card.

**Fix:** the untouchables layer gains an **Add from your roster** affordance that
opens a roster picker as a **third layer inside the same `Modal`** — the exact
construction #173/#246 already established for the untouchables layer itself.

- Pool: the signed-in user's own roster (`getLeagueRosters` → `owner_id === userId`)
  resolved through the **already-cached** `['calc-values', format]` value pool the
  layer uses today for names — no new endpoint, no new query key.
- Rows: position dot + name + `POS · TEAM`, value-sorted; players already
  untouchable are filtered out (they are in the list above).
- Search: a plain name filter, same construction as the board-search inputs.
- Add: `setAssetPref(leagueId, id, 'untouchable')` — the same mutation the deck's
  lock toggle uses — then invalidate `['asset-prefs', leagueId]` so the count, the
  list and the deck lock states all move together.
- Copy: the layer's how-to line changes from "hold a player on any trade card" to
  lead with the picker and keep the long-press path as the secondary route.

**Why not literally `PlayerPickerModal`:** it renders its own `<Modal>`, and this
layer lives *inside* an open `Modal` — the constraint this file already documents
("a sibling Modal wouldn't present over an open one on iOS"). It is also typed to
the calculator's `CalcPlayer`/`tradeCalcMock` shapes. The reused thing is the
pattern and the plumbing that matter: the in-Modal layer construction, the shared
`['calc-values']` pool, and the shipped `setAssetPref` write lane. No new API, no
new screen, no second untouchables store.

**New testIDs:**

- `untouchables.add-from-roster` — the "Add from your roster" button
- `untouchables.roster-back` — back to the untouchables list
- `untouchables.roster-search` — name filter
- `untouchables.roster-row.<player_id>` / `untouchables.roster-add.<player_id>`
- `untouchables.roster-empty` — honest empty/loading-resolved state

---

## 3. Non-goals

- No backend change. No new route, no schema change, no flag change.
- No change to stored outlook enum values or the `lane` enum.
- No change to `LeagueSummaryScreen`, `TradeCalculatorScreen`, `TrendsScreen`,
  `MarketPulseStrip`, `RankScreen` (other owners).
- The unrouted `TradeFinderHubScreen` is not touched; its `OUTLOOK_CARDS` copy is
  dead code pending the cleanup pass #246 already flagged.

---

## 4. Maestro regression flows (for the later runtime QA round)

Static verification only in this change — the batch QA round owns these.

| # | Flow | Assert |
|---|---|---|
| R1 | Sign in → Acquire tab | `trades.outlook-receipt` present; **no** second "Outlook" TickLabel in the controls card |
| R2 | Acquire tab → `trades.outlook-receipt.change` | DNA sheet opens; `dna.outlook.championship` is the **first** card, then `.contender`, `.rebuilder`, `.jets` |
| R3 | DNA sheet → tap `dna.outlook.rebuilder` → `dna.done` → reopen | Rebuilding still selected (autosave intact, order change did not break the write) |
| R4 | Flip `trade.outlook_direction` **off** → Acquire tab | receipt absent AND the controls-card Outlook row **present** (exactly one surface in both flag states) |
| R5 | Acquire tab, deck with lanes | pills read **"Team-fit moves"** / "Value moves"; tapping Team-fit filters and re-tapping clears |
| R6 | DNA sheet → `finder-hub.dna.untouchables` → `untouchables.add-from-roster` | roster list renders; only the user's own players; already-untouchable players absent |
| R7 | R6 → type in `untouchables.roster-search` → `untouchables.roster-add.<pid>` → `untouchables.roster-back` | player appears in the untouchables list; count increments; `finder-hub.untouchables.remove.<pid>` removes it |
| R8 | R7 → close DNA sheet → Find a Trade | the added player never appears on a give side |
| R9 | Classic home (`trades.finder_hub` off) | controls-card Outlook row + Edit → `OutlookSheet` still work (byte-identical path) |
| R10 | `trades.outlook-set-banner` (no outlook, `ux.outlook_inline_default` on) | "Set outlook" still opens `OutlookSheet` — the sheet's surviving entry points are unbroken |
