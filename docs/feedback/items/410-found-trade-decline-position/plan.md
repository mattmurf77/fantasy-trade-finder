# Plan — G-410: merged-canvas trade-card polish (#410 · #411 · #412)

> Group canonical for three items filed by **mattmurf77 on 2026-08-30 against
> v1.16.12 (EAS build 140)**, screen `TradesHome`. All three land on the same
> surface — the merged calculator canvas hosting a `calc.canvas_results` browse
> session — and therefore on the same three files. **One owner.**
> Branch: `claude/fb-410-412-trade-card-polish`, cut from `origin/main` `bd83fe94`.
> This is the PLAN. The scope block and PRD are authored separately.

## Table of contents

- [0. Why these three are one group](#0-why-these-three-are-one-group)
- [1. The surface, as it exists today](#1-the-surface-as-it-exists-today)
- [2. #410 — decline position on found trades](#2-410--decline-position-on-found-trades)
- [3. #411 — player-name truncation](#3-411--player-name-truncation)
- [4. #412 — "More offers" location](#4-412--more-offers-location)
- [5. Prior-ruling conflicts the operator must see](#5-prior-ruling-conflicts-the-operator-must-see)
- [6. File ownership](#6-file-ownership)
- [7. Draft requirements (R-1 … R-9)](#7-draft-requirements-r-1--r-9)
- [8. Evidence sketch (D-056 compliant)](#8-evidence-sketch-d-056-compliant)
- [9. Risks](#9-risks)
- [10. Open questions for the operator](#10-open-questions-for-the-operator)

---

## 0. Why these three are one group

The surface changed **twice on 2026-08-29/30**, hours before these reports:

| Ship | PR / sha | What it did to this surface |
|---|---|---|
| v1.16.11 | #237 / `21989cda` | `calc.canvas_results` — found ideas are browsed **inside** the calculator canvas. The deck stops rendering on this host; a pager row above the canvas header carries ‹ ›, `N / X`, "More offers", a model-path Clear and the ✕. |
| v1.16.12 | #250 / `287aed09` | FB-407 (`opponentChosenRef` payload gate) + FB-406 ("Any league mate" row, `partnerAny`, `calc.search-scope-note`, `seededPrefill`) — all inside the same action-row / column region. |

All three reports name controls that live in exactly two components plus their
host screen. Splitting them across owners would produce three conflicting edits
to `InLeagueCalculator.tsx`'s action row and `TradesScreen.tsx`'s pager block.

---

## 1. The surface, as it exists today

Render order on the merged guided landing (`calc.inline_home` on, `canvasHost === 'flag'`):

```
trades.anchor-receipt          ← fair-anchored sessions only  (TradesScreen.tsx:7469)
  … "Built around X."   Change   Clear                        (:7486, :7503 → handleBrowseClear)
trades.canvas-results.pager    ← browseLive && sortedDeck.length > 0 (:7302)
  ‹  (:7304)   N / X (:7319)   ›  (:7320)   ───spacer───
  [More offers] (:7347)   Clear (model-origin only, :7369)   ✕ (:7390)
trades.build-canvas            ← TradeBuildCanvas (:7429)
  └─ InLeagueCalculator
       calc.trade-columns      ← two TradeSide columns  (InLeagueCalculator.tsx:1229)
       calc.action-row         ← Find a Trade 50 / Clear 30 / ✓ 20  (:1269)
       calc.search-scope-note  ← FB-406  (:1361)
```

Key handlers:

| Control | Handler | Effect |
|---|---|---|
| pager ✕ | `handleBrowsePass` — `TradesScreen.tsx:5750` | opens the two-layer decline-reason overlay; a completed pass splices the idea out via the browse-aware `commitReasonAdvance` |
| pager / receipt Clear | `handleBrowseClear` — `:5686` | `endBrowseSession()` — kills the session, restores the blank canvas |
| action-row Clear | `clear()` — `InLeagueCalculator.tsx:843` | `setGiveIds([]); setReceiveIds([])` + `calc_cleared` analytics. **Does not touch the session.** |
| action-row ✓ | `onLikeTrade` → `utils/queueCalcTrade` | queues whatever the canvas currently holds (D-152) |

---

## 2. #410 — decline position on found trades

> **Report:** *"X button should replace the 'clear' button next to check box when a
> found trade is suggested."*

### 2.1 State-by-state truth (the orchestrator asked for this explicitly)

| State | Pager row | Action row: Find a Trade | middle cell | ✓ cell | Where ✕ lives |
|---|---|---|---|---|---|
| **A — empty canvas, no session** | absent (`browseLive` false, `:7302`) | enabled | **Clear, DISABLED** (`disabled={!anySide}`, `InLeagueCalculator.tsx:1307`) | disabled (`!bothSides \|\| !opponent`, `:1331`) | **nowhere** |
| **B — hand-built trade on canvas, no session** | absent | enabled | **Clear, enabled** → empties both sides | enabled once both sides + a partner | **nowhere** — correct: a hand-built package has no engine suggestion to decline |
| **C — browsing a FOUND idea** | **present** | enabled ("Find a Trade" — relabel logic is page-level and does not reach this row) | **Clear, enabled** → empties the canvas, **session survives** | enabled | **pager row, `trades.canvas-results.pass` (`:7390`)** — small 44pt icon cell at the far right of a row that sits *above* the canvas |

### 2.2 Root cause — and it is worse than "the ✕ is in the wrong place"

In state C the action-row Clear is not merely redundant, it is **actively
destructive of browse state**:

1. `clear()` (`InLeagueCalculator.tsx:843-848`) empties both sides.
2. The `onSidesChange` effect (`:386-392`) fires with `([], [])`.
3. `handleBrowseSidesChange` (`TradesScreen.tsx:5732-5738`) snapshots
   `{give: [], receive: []}` **into the browsed idea's edit map**, keyed by
   `browseSeededIdRef.current`.
4. The pager stays live, still reading `3 / 12` over an empty canvas. Paging
   away and back re-seeds the **emptied** idea, not the engine's original. The
   only recoveries are the receipt/pager Clear (which discards the whole
   session) or a fresh Find a Trade.

So during a browse session the user is offered a prominent, ice-adjacent,
50/30/20-weighted control that silently corrupts the idea they are looking at,
while the action the moment actually calls for (accept ✓ / decline ✕) is split
across two rows at two visual weights.

Additionally, a fair-path session renders **two controls both labeled "Clear"**
at once (`trades.anchor-receipt.clear` at `:7494` and `calc.action.clear` at
`:1302`) that do different things; a model-path session renders
`trades.canvas-results.clear` (`:7369`) plus the action-row Clear, likewise.

### 2.3 Proposed change

**Fork the action row's middle cell on the browse state**, keeping the D-157
50/30/20 proportions byte-identical:

- **During a live browse session with an idea fronted** (`browseLive && sortedDeck.length > 0`),
  the middle cell renders the **decline control**: `handleBrowsePass` — the same
  handler the pager ✕ calls today, the same `trade_pass_overlay_*` machinery, no
  parallel pass path. It sits directly left of the ✓, so accept and decline are
  adjacent at the same weight, which is what the report asks for.
- **Everywhere else** (states A and B, flag-off, the pushed Real-values page,
  `FeaturedTradeWindow`, the #270 experiment) the cell is **Clear, byte-identical**.
- The pager's ✕ (`:7390-7401`) **is removed** — exactly one decline control is
  ever mounted, mirroring the `TradeCard` `reasonsAsOverlay` rule ("exactly one
  presentation is ever mounted").
- The browse-ending Clear stays where it already is: the anchor receipt (fair)
  and the pager (model). Nothing about `handleBrowseClear` changes.

**Label, not a bare glyph.** D-157 exists because a tester read a bare ✕ in this
exact cell as "close" and wiped his canvas. The cell is ~106pt on a 375pt screen
— D-157's own note says that holds a word at the Chalkline 11pt floor with room
to spare. Recommendation: render **"Pass"** (or "Decline") in `type.bodySm` /
`fonts.uiSemi` / `chalk.base` — the existing `actionClearText` construction —
optionally with the 16pt `x` glyph beside it. This satisfies the report's intent
(the decline action is next to the check) while *honoring* D-157's principle
rather than reverting it. **This is a copy call the operator should make** (see §10 Q-1).

**Ownership of the fork.** `InLeagueCalculator` must not read `calc.canvas_results`
— that would break the "one bare `const merged = useFlag(…)` read" rule and the
two-host contract. The fork arrives as an **optional host prop** in the same
family as `hideFormatChips` and `seededPrefill`:

```ts
/** #410 — host-declared browse state. Absent/false ⇒ today's Clear cell,
 *  byte-identical for every pre-#410 host. */
browseDecline?: { onPress: () => void } | null;
```

threaded `TradesScreen` → `TradeBuildCanvas` → `InLeagueCalculator`, exactly as
`onSidesChange` was.

### 2.4 Alternatives considered

| Alternative | Verdict |
|---|---|
| Add a 4th cell (Find / Clear / ✕ / ✓) | **Rejected** — changes the D-157 proportions outright, and at 4 cells nothing holds a word above the 11pt floor. The operator's own words are "replace", not "add". |
| Leave the ✕ on the pager, just disable the action-row Clear during browse | **Rejected as the whole fix** — it removes the corruption but not the reported complaint (decline is still far from ✓ at a smaller weight). Worth keeping as the **fallback** if the operator declines the swap. |
| Make the action-row Clear *end the session* during browse instead | **Rejected** — duplicates `handleBrowseClear`, and the receipt/pager already own that verb. Two controls, one verb, three placements is what got us here. |
| Move ✓ to the pager instead, so both live together above the canvas | **Rejected** — the ✓ is D-152 and the action row is the page's only primary (merged-view trim T-2). Moving it strands the primary. |

---

## 3. #411 — player-name truncation

> **Report:** *"Move the position tag to the second row, leaving just the name on
> the top row. Pressure test whether the names stop getting truncated now."*

### 3.1 The layout, and why it truncates

`TradeSide.tsx` `compact` mode (`compact={merged}` at both mounts,
`InLeagueCalculator.tsx:1183` and `:1204`) re-flows each asset row to two lines:

- **line 1** — `compactTopLine` (`TradeSide.tsx:85-90`): `PositionChip size="sm"` **+**
  the name at `type.title` with **`numberOfLines={1}`** and `flexShrink: 1`
  (`styles.compactName`, `:210`).
- **line 2** — `compactMetaLine` (`:94-119`): `"<NFL team> · <age> yrs"` at
  `type.bodySm` + the `TierBadge` (or a numeric value), `justifyContent: 'space-between'`.

The truncation is a **width budget**, not a bug in the clamp. On a 375pt device:

| Step | Source | Width |
|---|---|---|
| ScrollView content | `TradesScreen.tsx:9215` `scroll: { padding: space.lg }` | 375 − 32 = **343** |
| One column | `InLeagueCalculator.tsx:2033,2037` — `columns` gap `space.sm` (8), `column: {flex:1, flexBasis:0, minWidth:0}` | (343 − 8) / 2 = **167.5** |
| Card inner | `chalkline/Card.tsx:44,53` — 1pt border ×2 + `space.lg` (16) padding ×2 | 167.5 − 34 = **133.5** |
| `info` (flex 1) | `rowCompact` gap `space.xs` (4) + the 32pt remove `Pressable` (`:195-201`) | 133.5 − 36 = **~97.5** |

That 97.5 is corroborated by the file's own comment at `TradeSide.tsx:96-97`
("the ~97pt of info width a 375pt screen leaves"), so the chain is right.

Inside `compactTopLine` the chip takes its width first (`PositionChip.tsx:41-48`:
`paddingHorizontal 4` ×2 + `borderWidth 1` ×2 + `type.label` 11pt uppercase with
`letterSpacing 0.88`):

- `QB` / `RB` / `WR` / `TE` ≈ **26–28pt**
- `PICK` ≈ **43pt**

Minus the `space.xs` (4) gap, the **name gets ≈ 66–68pt** on a player row —
about **8 characters** at `type.title` (Archivo SemiBold 16pt, ~8.4pt average
advance for mixed-case Latin).

### 3.2 Quantified: what truncates now, and what still truncates after the move

Estimated rendered widths at 16pt SemiBold (device measurement owed — see §8):

| Name | chars | ≈ width | today (~67pt) | tag moved to row 2 (~97.5pt) | + `numberOfLines={2}` (~195pt) |
|---|---|---|---|---|---|
| Bo Nix | 6 | ~50 | fits | fits | fits |
| Puka Nacua | 10 | ~84 | **truncates** | fits | fits |
| CeeDee Lamb | 11 | ~92 | **truncates** | fits | fits |
| Nico Collins | 12 | ~101 | **truncates** | **borderline** | fits |
| Ja'Marr Chase | 13 | ~109 | **truncates** | **truncates** | fits |
| Jayden Daniels | 14 | ~118 | **truncates** | **truncates** | fits |
| Bijan Robinson | 14 | ~118 | **truncates** | **truncates** | fits |
| Amon-Ra St. Brown | 17 | ~143 | **truncates** | **truncates** | fits |
| Christian McCaffrey | 19 | ~160 | **truncates** | **truncates** | fits |
| Marvin Harrison Jr. | 19 | ~160 | **truncates** | **truncates** | fits |

**Answer to the operator's pressure test: no.** Moving the tag buys **+30pt
(+45%)** and fixes short names only. The median NFL full name is 13–16
characters and still ellipsizes. **The move alone does not deliver the ask.**

### 3.3 Proposed change — the move plus one more lever

1. **R-3 (the operator's ask):** move `PositionChip` out of `compactTopLine`
   into `compactMetaLine`, leading the meta row before the `"<team> · <age> yrs"`
   text. The name becomes the sole child of line 1. `compactTopLine` collapses
   to a plain `<Text>`; `compactName`'s `flexShrink` is no longer load-bearing
   but the clamp stays gated on `compact` (see the guard at
   `check-calc-merged-layout.js:264-269`, which asserts exactly one bare
   `numberOfLines={1}` and that it is the compact name — the guard must be
   re-keyed, not deleted).
2. **R-4 (what actually closes the complaint):** raise the compact name to
   **`numberOfLines={2}`**. Two lines of 97.5pt ≈ 195pt of name budget, which
   holds every name in the table above. This composes *only because* the tag
   moved — a wrapped name beside a chip reads as a layout accident; a wrapped
   name owning its own line reads as designed. Cost: the row grows by one
   `type.title` line-height (**22pt**, `theme/chalkline.ts:126`) when it wraps,
   and only when it wraps.

**Chalkline tokens that govern this** (`docs/design/design-system.md` +
`docs/design/components.md`): the name stays `type.title` (Archivo SemiBold 16 /
22) — **type is not shrunk**, per `TradeSide.tsx:40-43` and the 11pt floor. The
meta line stays `type.bodySm` (13/18, `chalk.dim`). `PositionChip` is the
standard Badges-&-chips construction (transparent fill, 1px border in the
position hex, radius `radii.xs`) — a **data encoding** under
`docs/cross-client-invariants.md`, so it is *moved*, never restyled or dropped.
The meta row keeps `space.xs` gaps and `justifyContent: 'space-between'` so the
`TierBadge` stays right-aligned; the chip enters at the row's **left**, which
preserves the "price is the right-hand thing on line 2" reading.

**Accepted limit, stated rather than discovered:** `type.title` caps at the
`body` Dynamic-Type tier (2.0×, `theme/chalkline.ts:175`). At 200% text scaling
a 16pt name renders at 32pt and even two wrapped lines hold ~11 characters —
truncation returns. The guard must therefore assert the **structural** change,
never "names never truncate".

### 3.4 Alternatives considered

| Alternative | Verdict |
|---|---|
| Move the tag only (stop at R-3) | **Insufficient** — §3.2 shows the median name still ellipsizes. Ship it only if the operator explicitly wants the minimal edit. |
| Also move the 32pt remove ✕ to line 2 (name gets the full 133.5pt) | **Held as a second lever.** Buys ~15–16 chars single-line — still fails McCaffrey/St. Brown/Harrison Jr. Strictly worse than R-4 and it demotes a destructive control's touch target. Reach for it only if the operator rejects wrapping. |
| Abbreviate to "C. McCaffrey" (`lastName` helpers exist at `MarketPulseStrip.tsx:40`, `MockDraftScreen.tsx:1228`, `TradeFinderHubScreen.tsx:107`) | **Rejected** — the calculator is the surface where a user confirms *which* asset they are trading. Abbreviating identity to win 40pt is the wrong trade on a decision screen. Reasonable on a 150pt strip; not here. |
| Drop the name to `type.body` (14pt) | **Rejected** — the name is the row's primary identifier; demoting it below the meta hierarchy to fit is a design-system deviation for a layout problem that R-4 solves without one. |
| Widen the columns (reduce `scroll` padding or the column gap) | **Rejected** — page-level padding is Chalkline's page gutter and is shared by every block on `TradesHome`. Total win would be ≤16pt. |

---

## 4. #412 — "More offers" location

> **Report:** *"Reversion from prior version.. move more offers underneath the add
> a player button"*

### 4.1 When it moved, and why

**It moved yesterday, in `21989cda` (v1.16.11 / PR #237).** Confirmed by
`git log -S"canvas-results.more-offers"` — that sha is the only commit that
introduces the string.

- **Before v1.16.11:** "More offers" was the deck `TradeCard`'s **give-side
  chip** (`TradeCard.tsx:444-464`, `testID trade-card.keep-give`), rendered with
  the give-side player tiles, inside the card, beneath that side's assets. Under
  `shopGiveEntry` (`TradesScreen.tsx:8028`) the label forks from
  `"Keep · more offers"` to `"More offers"` and the tap becomes the #402/#403
  shop-window push.
- **v1.16.11:** `canvas-results-spec.md` §2 ruled *"the deck does not render
  while a browse session exists"*. The deck card — and with it the give-side chip
  — disappeared from this host. The pager row inherited the entry as
  `trades.canvas-results.more-offers` (`TradesScreen.tsx:7347-7368`).

**So the operator is right: this is a reversion, and it was collateral, not a
design choice.** The code comment at `:7336-7346` labels it
*"#402 QA B-C4 (operator-flagged design call, built under the ship order)"* —
i.e. a QA agent **flagged it for the operator** and built a compensating
placement under the standing ship order. Searching `docs/` for `B-C4` returns
only `docs/feedback/items/402-more-offers-shop/testflight-checklist.md:206`, a
verification step. **There is no operator ruling placing "More offers" on the
pager row.** Moving it is therefore a low-conflict fix (unlike #410 — see §5).

### 4.2 Proposed change

Render the shop entry **inside the give column, directly beneath its "Add
player" button** (`TradeSide.tsx:166-168`, `addTestID="calc.league-give-add"`) —
which is the give-side position the pre-v1.16.11 card had, restored to the
layout that replaced the card.

Mechanics:

- New optional `TradeSide` prop — `belowAdd?: React.ReactNode` (or a narrower
  `moreOffers?: {label, onPress, a11yLabel}`) — rendered after the Add button
  inside the same `Card`. **Absent ⇒ byte-identical** for the receive column,
  the stacked page, `FeaturedTradeWindow` and the #270 experiment.
- Threaded `TradesScreen` → `TradeBuildCanvas` → `InLeagueCalculator` → the
  **give** `TradeSide` only, in the `hideFormatChips` / `seededPrefill` /
  `onSidesChange` family. `TradeSide` never reads a flag.
- The entry keeps the **bordered-chalk** construction it has today
  (`browseMoreOffersBtn`, `TradesScreen.tsx:9563-9575`: 1px `ink.line`,
  `radii.sm`, `space.sm` horizontal padding, `type.bodySm` `fonts.uiSemi`
  `chalk.base`) — ice stays rationed to the action row's primary and ✓. It sits
  under a `variant="secondary"` Button, so bordered chalk reads correctly as the
  quieter sibling.
- Handler and gate are **unchanged**: `openShopForCard` (`TradesScreen.tsx:3240`)
  — one give asset navigates, several open the "Shop which player?" chooser;
  `shop_opened` still fires exactly once inside `openShopWindow` (P-3). Gate
  stays `shopEnabled` (`:1538`) `&& browseLive && sortedDeck.length > 0 &&`
  give side non-empty.
- The pager copy (`:7347-7368`) and its `browseMoreOffers*` styles are **removed**
  — one entry, one placement, no duplicate.

**The semantic question the builder must answer explicitly.** Today the pager
entry shops `rawTopCard` — the **engine's original** give side, ignoring any
canvas edits (deliberate: `handleBrowsePass`'s comment at `:5744-5749` makes the
same original-vs-edited distinction for the pass signal). Sitting under the give
column's Add button, the control now *looks* like it shops what the column
shows. Recommendation: **keep `rawTopCard`** for consistency with the pass path
and note the divergence in a code comment; flag to the operator as Q-3.

### 4.3 Alternatives considered

| Alternative | Verdict |
|---|---|
| Restore the chip to `TradeCard` and let the deck render again | **Rejected** — reverses `canvas-results-spec.md` ruling 1 (the canvas *is* the results surface), a real operator ruling. |
| Leave it on the pager and just relabel | **Rejected** — the report is about location, explicitly. |
| Put it under the Add button and drop the browse gate (shop any hand-built give side) | **Not rejected — held as Q-2.** Coherent (a give side is a give side) and arguably better, but it is a scope expansion the report did not ask for. Default to the existing browse-only gate. |
| A give-column footer slot for the receive side too | **Rejected** — shop is a give-side verb (rev-3 §1); a receive-side entry has no meaning. |

---

## 5. Prior-ruling conflicts the operator must see

**#410 contradicts a written operator-session ruling and brushes a numbered decision.**

1. **`docs/feedback/items/402-more-offers-shop/canvas-results-spec.md` §4**,
   verbatim: *"A ✕ control on the browsed idea (**placement: with the pager,
   never inside the action row's 50/30/20 cells** — that row's proportions are
   D-157 and unchanged)."* The spec's own header calls itself "the contract".
   #410 asks for precisely the placement that clause forbids. `check-canvas-results.js:269`
   encodes it (*"The pass control lives with the pager — never in the D-157
   action row"*) and will fail until re-specced.
   - **Narrow reading that survives:** the clause's stated *reason* is the
     50/30/20 proportions, and the proposal **does not change them** — it swaps
     the middle cell's content, not its flex. Under that reading only the
     placement sentence is overturned, not its rationale.
2. **[D-157](../../../../living-memory/DECISIONS.md) (2026-08-23)** — *"The Action
   Row's ✕ Becomes a Labeled Clear Button"*. A tester (Segrave, build 128) read
   the bare ✕ in this cell as the deck's pass control and cleared his canvas
   mid-tour. D-157 replaced it with the word "Clear". #410 puts a decline
   control back in that cell.
   - **This is not a straight reversal, and the distinction matters:** Segrave's
     misread was that the ✕ *meant pass when it actually cleared*. #410 makes the
     cell mean pass — i.e. it resolves the misread by making the control do what
     users already believed it did. The D-157 **principle** (a word, not a bare
     glyph) is preserved by labeling the cell, which is why §2.3 recommends
     "Pass" over a bare ✕.
   - D-157's own tour copy is affected: beat **n19** reads *"Clear became this
     cross…"* and keys off this row. It must be re-checked at build time (D-157
     says so explicitly). The tour is Wave B and currently suppressed on this
     path, but the string still exists in `analystScript.ts`.

**#411 and #412 conflict with nothing.** #411 touches layout the #384 W6 comment
block owns but no ruling fixes. #412's current placement was a QA-agent
compensation, not an operator call (§4.1).

**The orchestrator must surface items 1 and 2 to the operator before build.**
The operator is free to overturn their own 2026-08-28 ruling — but silently
reversing a written contract clause and a numbered decision is exactly the
failure mode the ledger exists to prevent. Recommended ask: a one-line confirming
yes, plus the copy call in Q-1.

---

## 6. File ownership

**One owner for the whole group.** Every file below is touched by at least two of
the three items.

| File | #410 | #411 | #412 |
|---|---|---|---|
| `mobile/src/components/InLeagueCalculator.tsx` | action-row middle cell fork; new `browseDecline` prop | — | thread the give-column slot |
| `mobile/src/components/TradeSide.tsx` | — | `compactTopLine` / `compactMetaLine` re-flow; `numberOfLines` | new `belowAdd` slot |
| `mobile/src/components/TradeBuildCanvas.tsx` | thread `browseDecline` | — | thread the shop slot |
| `mobile/src/screens/TradesScreen.tsx` | delete pager ✕; pass `browseDecline` | — | delete pager "More offers" + its 3 styles; pass the slot |
| `mobile/tests/check-canvas-results.js` | re-spec §3 (pass placement, `:269`) and 12i/12i2 | — | re-spec 12i/12i2 |
| `mobile/tests/check-calc-merged-layout.js` | — | re-key rules 16/16b/17 (`:258-274`) | — |
| `mobile/tests/check-calc-merged-behavior.js` | assert the middle-cell fork is a **prop**, never a flag read | — | — |
| `mobile/src/components/CLAUDE.md` | rows for `InLeagueCalculator`, `TradeBuildCanvas` | row for `TradeSide` / the compact re-flow | rows for `TradeSide`, `TradeCard` |
| `mobile/src/screens/CLAUDE.md` | `TradesScreen` row (pager contents) | — | `TradesScreen` row |
| `docs/design/components.md` | — | if the compact calculator row earns a construction entry | — |
| `living-memory/DECISIONS.md` | **new D-### amending D-157 + canvas-results-spec §4** | — | — |
| `living-memory/CHANGELOG.md`, `TEST_LEDGER.md` | ship + evidence | ship + evidence | ship + evidence |

**No backend, no schema, no API, no new analytics event.** `calc_cleared`
(`InLeagueCalculator.tsx:845`) simply stops firing during browse because the
control is not a Clear there — a *reduction* in emission on one state, not a
taxonomy change. `trade_pass_overlay_*` and the `/api/trades/pass-reason` writes
are reused verbatim. **No feature flag is added:** all three ride the existing
`calc.canvas_results` / `calc.inline_home` / `calc.merged_layout` conjunction,
which remains the rollback lever.

---

## 7. Draft requirements (R-1 … R-9)

**#410**

- **R-1** — While a browse session is live with an idea fronted, the action
  row's **middle cell is the decline control**, routed through
  `handleBrowsePass` → the existing two-layer decline-reason machinery. No
  parallel pass path, no new endpoint, no new event.
- **R-2** — The cell renders a **word**, not a bare glyph (D-157's principle).
  In every other state — empty canvas, hand-built canvas, flag off, every
  non-`TradesScreen` host — the cell is **Clear, byte-identical**.
- **R-3** — The 50/30/20 flex values (`actionFind` 50 / `actionClear` 30 /
  `actionSmall` 20, `InLeagueCalculator.tsx:2049-2051`) are **unchanged**, and
  the ✓ cell is untouched.
- **R-4** — Exactly **one** decline control is mounted at a time: the pager ✕
  (`trades.canvas-results.pass`) is removed. The browse-ending Clear
  (`handleBrowseClear`) stays on the anchor receipt and the model-path pager,
  unchanged.
- **R-5** — The fork reaches `InLeagueCalculator` as an **optional host prop**.
  The component adds no flag read; absent ⇒ byte-identical.

**#411**

- **R-6** — In `compact` mode the position chip renders on the **meta line**;
  line 1 holds the name alone. The chip is moved, never dropped or restyled
  (data encoding, `docs/cross-client-invariants.md`); the `TierBadge` / numeric
  value stays right-aligned on the meta line.
- **R-7** — The compact name clamps at **two** lines. Type sizes are unchanged
  (`type.title` 16/22; the Chalkline 11pt floor holds), the 32pt remove target
  is unchanged, and the non-compact (stacked-page) branch is byte-identical.

**#412**

- **R-8** — The shop entry renders **inside the give column, directly beneath
  "Add player"**, and nowhere else on this host; the pager copy and its
  `browseMoreOffers*` styles are removed.
- **R-9** — Handler, gate and analytics are unchanged: `openShopForCard`,
  `shopEnabled && browseLive && sortedDeck.length > 0 &&` give-side non-empty,
  `shop_opened` fired exactly once at the navigate site. `TradeSide` receives a
  presentational slot and reads no flag; absent ⇒ byte-identical for the receive
  column and every other host.

---

## 8. Evidence sketch (D-056 compliant)

**Maestro and the simulator are retired ([D-056](../../../../living-memory/DECISIONS.md)).
No flows, no `screens/` captures, no `qa/sim-runs` marker — `FTF_SKIP_SIM_GATE=1`
is the standing posture.**

### 8.1 Structural assertions

`mobile/tests/check-canvas-results.js` — **re-spec, do not delete** (three
existing rules become false):

- **§3 / rule at `:269`** — invert: the pass control lives in the action row's
  middle cell during browse and **nowhere else**; assert `trades.canvas-results.pass`
  no longer exists in `TradesScreen.tsx`.
- **12i / 12i2 (`:584-591`)** — re-key: `trades.canvas-results.more-offers` is
  gone from the pager; the give-column entry exists and is threaded as a prop.
- **New** — exactly one decline control site in the tree; `handleBrowsePass` has
  exactly one caller.
- **New** — the middle-cell fork in `InLeagueCalculator.tsx` is driven by a prop,
  with **zero** occurrences of `canvas_results` in that file (the one-flag-read
  rule).
- **New** — `browseDecline` / the give-column slot are **optional** and absent at
  `FeaturedTradeWindow`, the pushed page and the #270 experiment mounts.

`mobile/tests/check-calc-merged-layout.js` — re-key rules **16 / 16b / 17**
(`:258-274`), which currently assert exactly one bare `numberOfLines={1}` and
that it is `compactName`. After R-7 the compact name is `{2}`; the guard must
assert (a) the clamp is still gated on `compact` so the stacked page cannot
inherit it, and (b) the chip now renders inside `compactMetaLine`, not
`compactTopLine`.

`mobile/tests/check-calc-merged-behavior.js` — add: the action-row middle cell's
`onPress` is the host-supplied decline handler when the prop is present and
`clear` otherwise; `disabled` semantics differ per branch (`!anySide` only
applies to the Clear branch).

`mobile/tests/check-shop-deck.js` — confirm the deck's own give-side chip
(`TradeCard.tsx:444-464`) is untouched; only the canvas host's entry moved.

`bash mobile/scripts/testid-lint.sh` — the retained flows reference
`calc.action.clear`; a renamed or conditional testID needs a lint entry. **Keep
`calc.action.clear` on the Clear branch** and give the decline branch its own id
(`calc.action.decline`) rather than reusing one id for two verbs.

`npx tsc --noEmit` (strict) · `pytest backend/tests` untouched-proof (no backend
files in §6).

### 8.2 Code-walk proof

`docs/feedback/items/410-found-trade-decline-position/code-walk.md`, in the
`406`/`407` house style, tracing with file:line:

1. All three states of §2.1 through the new middle-cell branch, including the
   disabled predicates.
2. That the decline branch reaches the **identical** overlay path the pager ✕
   reached — `handleBrowsePass` → `handleReasonOverlayOpened` →
   `commitReasonAdvance` → `removeBrowsedIdea` — with no new writes.
3. That `clear()` and `calc_cleared` are unreachable during a live browse
   session, closing the edit-map corruption in §2.2.
4. That #411's re-flow is inside the `compact` branch only, so flag-off /
   stacked-page rendering is byte-identical.
5. That #412's slot is `undefined` at all four pre-existing `TradeSide` /
   `InLeagueCalculator` mounts.

### 8.3 Operator TestFlight checklist

`docs/feedback/items/410-found-trade-decline-position/testflight-checklist.md`
— specific enough to catch a regression, since it is the only runtime evidence:

1. **Empty canvas.** TradesHome shows Find a Trade / **Clear (greyed)** / ✓
   (greyed). No pager, no ✕ anywhere.
2. **Hand-built trade** (add one player each side). Middle cell reads **Clear**
   and is live; tapping it empties both columns. **This must still work** — it is
   the D-157 control.
3. **Find a Trade with a give side** (fair path). Pager appears with ‹ `1 / N` ›.
   Middle cell now reads **the decline word**. Anchor receipt above still shows
   Change / Clear.
4. **Tap the decline cell.** The two-layer reason overlay opens exactly as the
   deck's does. Pick a layer-1 tile, then a layer-2 option → the idea leaves the
   set, `N` decrements by one, the next idea seeds the canvas.
5. **Dismiss the overlay without answering** → the idea stays, `N` unchanged.
6. **Tap ✓ on a browsed idea** → queues, toast, session stays on the idea.
7. **Receipt Clear** → session ends, canvas blank, middle cell back to a greyed
   **Clear**.
8. **Model path** (empty canvas → Find a Trade). Pager Clear present; middle cell
   is the decline word; both behave as in 3–7.
9. **#411 — name legibility.** Load an idea containing **Christian McCaffrey**
   (or any 17+ character name) plus a **draft pick**. Confirm: position tag is on
   the **second** row beside team/age, the tier badge is still right-aligned, the
   full name is readable across up to two lines, and the pick row's `PICK` chip
   did not push anything out of alignment. **Report any name still ellipsized** —
   that is the pressure test, and §3.2 predicts none at default text size.
10. **#411 — Dynamic Type.** Settings → larger text (~200%). Names may ellipsize
    again; confirm nothing **overlaps** and the remove ✕ stays tappable.
11. **#412 — placement.** While browsing, **"More offers" sits under the give
    column's "Add player" button**, not in the pager row. Tapping it with one
    give asset opens the shop window directly; with several, the "Shop which
    player?" chooser opens and its pick navigates. Back returns to the browse
    session **intact** (same idea, same `N / X`).
12. **#412 — absence.** With no browse session (blank canvas, or after Clear),
    there is no "More offers" anywhere on the page.
13. **Deck regression.** Switch to Team or Player mode (no canvas host): the
    deck's own give-side "More offers" chip and its ✕/✓ are unchanged.

### 8.4 Ledger

`living-memory/TEST_LEDGER.md` gets the suite names + pass counts and a line
naming the code-walk and the checklist as the mobile evidence, per D-056.
`living-memory/DECISIONS.md` gets a new D-### recording the §5 amendment.

---

## 9. Risks

| # | Risk | Mitigation |
|---|---|---|
| 1 | **The §5 rulings.** Building #410 without an operator confirmation silently reverses a written contract clause and brushes D-157. | Orchestrator surfaces §5 and gets a yes **before** build. Plan defaults to labeling the cell so D-157's principle survives. |
| 2 | **Muscle memory.** The same cell means "clear the canvas" in one state and "decline this idea" in another. A user who learned Clear taps it during browse and passes on an idea. | The label changes with the meaning (never a bare glyph). The decline opens a **reason overlay** — a confirmable, dismissible step — so an accidental tap is recoverable, unlike today's silent canvas wipe. Checklist steps 2 and 4 test both readings. |
| 3 | **Fresh code underneath.** FB-406/FB-407 landed in this exact region hours earlier (`opponentChosenRef`, `partnerChosen`, `partnerAny`, `seededPrefill`, `calc.search-scope-note` at `:1361`). | The scope-truth note's predicate is *"the exact complement of the FB-407 payload gate"* with a textually identical initializer — do **not** reformat those lines. `check-any-partner.js` (A-1…A-15) must stay green; run it explicitly. |
| 4 | **Prop sprawl.** `InLeagueCalculator` now takes `hideFormatChips`, `seededPrefill`, `onSidesChange`, `partnerLocked`, and gains two more. | Both new props are optional, default to today's behavior, and are asserted absent at the four pre-existing mounts. The alternative — a flag read inside the component — breaks the two-host contract. |
| 5 | **#411 row-height growth.** A wrapped name adds 22pt per row; two four-asset columns could push the action row out of frame, and "it fits in one frame with the calc section" is the #384 constraint the action row exists to satisfy. | Wrapping is per-row and only when needed. Checklist step 9 uses a long name **plus** a pick to exercise the worst case; if the frame breaks, fall back to R-6 only (tag moved, single line) and record why. |
| 6 | **#411 guard deletion.** `check-calc-merged-layout.js:264-269` is a *flag-off byte-identity* guard, not a style nit. | Re-key it, never delete it. The re-keyed rule must still prove the stacked page cannot inherit the clamp. |
| 7 | **#412 semantics.** Under the give column, "More offers" looks like it shops the edited canvas; it shops `rawTopCard`. | Q-3 to the operator; code comment either way, mirroring `handleBrowsePass`'s original-vs-edited note at `:5744-5749`. |
| 8 | **testID churn.** Renaming `calc.action.clear` breaks `testid-lint` and the retained flows. | Keep `calc.action.clear` on the Clear branch; add `calc.action.decline` for the new one. Two ids, two verbs. |
| 9 | **Double haptic (pre-existing).** `InLeagueCalculator.tsx:1309` calls `haptics.warning()` and `clear()` at `:844` calls it again. | These are the exact lines #410 rewrites; fix in place. Not a drive-by — it is inside the change's own footprint. |
| 10 | **Tour copy.** Beat **n19** ("Clear became this cross…") keys off this row (`analystScript.ts`). | The tour is Wave B and suppressed on this path, but grep the script and re-check the string at build time, as D-157 requires. |

---

## 10. Open questions for the operator

- **Q-1 (#410, copy).** The middle cell during browse: **"Pass"**, **"Decline"**,
  **"Not for me"**, or a bare ✕? Recommendation: a **word** — D-157 exists
  because a bare ✕ in this exact cell was misread. If the operator wants the
  literal ✕ from the report, that is their call to make knowingly.
- **Q-2 (#412, scope).** Should "More offers" under Add player render only while
  browsing a found idea (today's gate, and the default here), or also for a
  hand-built give side with no session? The latter is coherent but a scope
  expansion the report did not ask for.
- **Q-3 (#412, semantics).** Should the give-column entry shop the **engine's
  original** give side (today's `rawTopCard`, consistent with the pass signal) or
  the **canvas as currently edited**?
- **Q-4 (#411, depth).** R-7 (two-line name) is what makes "names stop getting
  truncated" true. If the operator wants the minimal edit (tag move only), §3.2
  is the honest answer about what that does and does not fix.
