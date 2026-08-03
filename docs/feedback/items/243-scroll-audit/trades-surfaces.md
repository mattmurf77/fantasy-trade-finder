# #243 Scroll-Elimination Audit — Trades Surfaces

Observations only — no code changed. Method per the #218 hub density pass: nominal content height summed from styles vs a **658pt usable viewport** (iPhone 15/16-class 393×852 − 59 top inset − 52 TopBar − 49 tab bar − 34 bottom inset). Sheets are budgeted at their own maxHeight. Three sub-audits: deck surfaces, calculator surfaces, hub-regression + sheets.

## Shared building-block costs (cited once)

| Primitive | Height | Cite |
|---|---|---|
| Chalkline `Card` overhead (border + `space.lg` padding) | 34pt | chalkline/Card.tsx:41 |
| `TickLabel` | 14pt | chalkline/TickLabel.tsx |
| `Button` default / compact | 44 / 36pt | chalkline/Button.tsx:136-137 |
| `PlayerCard` compact row | 98pt | PlayerCard.tsx:354-413 |
| `StrengthBar` | 26pt | StrengthBar.tsx:63-71 |
| **`TradeValueBar`** | **≈240-248pt** | TradeValueBar.tsx:178-248 |
| `SuggestionCard` | 80pt | SuggestionCard.tsx |
| `TradeSide` card, 2 assets (+64pt per extra asset) | 228pt | TradeSide.tsx |

`TradeValueBar` is the single most expensive shared widget on every trade surface (label + heading + margin sentence + track + scale + end labels + a bordered verdict paragraph), and it appears **twice** in single-pin mode.

---

## A. TradesScreen deck modes

### State: classic empty (returning user, no deck)
Sum ≈ **863pt** (684pt before Explore) vs 658 → **overflows ~205pt**. Dominant cause: `deckWrap` sets an **unconditional `minHeight: 360`** (TradesScreen.tsx:4955) while the empty-state card content is only ~120pt — **~240pt of pure reserved dead space**. First-run skeleton state inherits the same floor.

### State: classic deck (1-for-1 card, minimal fields)
Chrome-above-card 308pt + card 532pt + disposition/hint/flag rows 138pt ≈ **994pt → overflows ~336pt**. The visible fold cuts off inside the TradeValueBar; the Like/Pass buttons sit ~300pt below the fold. Real 2-for-1 cards with fit lines are taller.

### State: single-pin featured-trade mode (#216/#209/#241) — worst offender
Minimal case (1 idea per group) ≈ **1497pt → overflows ~839pt (2.3 screens)**. Compounding causes:
1. `TradeFinderModeBar` (142pt) + `OutlookBiasReceipt` (48pt) are straight additions — nothing was subtracted for finder mode.
2. **The full Controls Card (286pt: outlook row + fairness row + two-column pin board) still renders above the featured window** — #241 removed the deck/Find button/progress strip but the card never shrank; its primary action is gone yet the editable chrome persists.
3. `FeaturedTradeWindow` = 512pt (full TradeCard incl. its own TradeValueBar; StrengthBar correctly suppressed).
4. `AssetIdeasPanel` = 333pt minimum stacks below both.

`AssetIdeasPanel` list rows are 63pt each (content overrides the styled minHeight:48) — the list is must-scroll by nature at 5+ rows; its own chrome (~52-124pt) is secondary to the 839pt of chrome above it.

### Modal sheets — not scroll-elimination targets
- Queue sheet: maxHeight 80% with an internal literal `maxHeight: 420` scroll cap (TradesScreen.tsx:5277) — reasonable for an unbounded list but inconsistent with the newer #242 size-to-content pattern.
- Team picker sheet: already the good pattern post-#242 (85%, flexGrow:0/flexShrink:1).

### Top suggestions (deck surfaces)
| Fix | Saves | Class |
|---|---|---|
| Collapse the Controls Card to a one-liner ("Pinned: <player> · Edit", tap-to-expand) in single-pin mode | ~230-250pt | structural — **biggest single lever in the audit** |
| Make `deckWrap` `minHeight:360` conditional on an actual deck rendering | ~240pt (empty state) | free space |
| Collapse `TradeValueBar`'s verdict paragraph behind a "Why?" disclosure | ~68pt × 2 instances in single-pin mode | structural |
| Step `TradeValueBar` winner line `type.heading`→`type.title` (it's a mid-card element, not a page title) | ~4pt/instance | density |
| Screen padding lg→md + scroll gap lg→sm (the #218 precedent) | ~48-64pt | free space |
| Drop the doubled `marginBottom:12` on TradeFinderModeBar/OutlookBiasReceipt (stacks on the scroll gap) | 24pt | free space |
| Fold "Edit in calculator" + "Bad trade?" rows into one overflow affordance (classic deck) | ~66pt | structural |
| Cap AssetIdeasPanel groups at 2 rows + "Show N more" | bounded worst case | structural |

---

## B. Calculator surfaces

All three calculator modes render inline in the 658pt budget (single ScrollView; no sheets in the audited files). All overflow heavily — this screen is a data-entry tool, so fit-to-screen is not the goal, but the common scroll can be materially shortened:

| Mode | Nominal (typical 2-for-2) | Overflow |
|---|---|---|
| Live (ConsensusVerdictCard 425pt) | ≈1419pt | +761pt |
| Demo (VerdictPanel 252pt) | ≈1206pt | +548pt |
| In-league, collapsed partner (LeagueVerdict 444pt) | ≈1398pt | +740pt |

- **`LeagueVerdict` (InLeagueCalculator.tsx:791-896) is the tallest single element in the whole audit — 444pt, 67% of the viewport.** It's also a bespoke local re-implementation of ConsensusVerdictCard (real code duplication; the two already disagree on gap tokens — LeagueVerdict uses scattered marginTops with no `gap`).
- **Bug-shaped find (highest-leverage for larger leagues):** the full opponent-chip picker's per-team `summaryLine` (InLeagueCalculator.tsx:920-925) has **no `numberOfLines` cap**, so chips sprawl to ~full-row width → a 12-team league renders ~1 chip/row ≈ **564pt** for the picker alone (+520pt vs the collapsed row). Fix: `numberOfLines={1}` + ellipsize, matching the sibling `partnerCollapsedText`.
- Worst case (4 assets/side + 4 suggestions + add-ons + eveners) exceeds **2400pt** (3.5 viewports). A "Show N more fair packages" cap (1-2 visible SuggestionCards, 80pt each) bounds the suggestion section's 366pt worst case.
- `AdjustmentsDisclosure` is the **positive precedent**: collapsed by default, null without data — the pattern the TradeValueBar verdict paragraph and suggestions should follow.
- Trims: TradeValueBar verdict-box padding md→sm (8pt); verdict-internal gaps md→sm where numeric rows adjoin (~12-16pt/card); screen `paddingBottom` 48 may be over-provisioned post-#223 (check → 24pt); system-wide Card padding lg→md would save ~40-48pt/screen but is a design-system decision, not a per-file fix.
- Consistency notes: EvenerRows nests inside the Card in live mode but renders as a sibling after it in league mode; VerdictPanel (demo) vs ConsensusVerdictCard (live) are 252 vs 425pt for the same conceptual job.

---

## C. Hub regression + Trades sheets

### TradeFinderHubScreen — no regression; #218 doc is stale
The DNA panel was fully rewritten by #212/#236 after the #218 measurement. Recomputed: DNA panel ~88-142pt (mid-state ~112pt vs the doc's 135pt); hub total mid-state **468pt → 190pt spare** (160pt with untouchables). The redesign is *more* efficient than what #218 documented. **Action item: update docs/feedback/items/218-hub-fit-to-screen/status.md** — its spacing table cites deleted styles (dnaGroupLabel 64pt column etc.). No further trimming warranted.

### OutlookSheet — the one sheet with real waste
- Internal ScrollView capped at a magic `maxHeight: 420` (OutlookSheet.tsx:228) while content is ~538pt → unnecessary internal scroll. But naively deleting the cap yields ~746pt vs a 732.8pt safe budget (the sheet reserves **no bottom safe-area inset** and uses 90% maxHeight vs the app's 85% convention) — the fix must pair the #242 size-to-content pattern with the trims below.
- Trims: submit button's `marginTop: space.md` stacks on the parent gap (12pt free); posHeader marginTop lg→md (24pt); outlookRow padding md→sm (32pt, tap target preserved by minHeight:44); add `SafeAreaView edges={['bottom']}` (safety).

### Other sheets/pickers
- PlayerPickerModal: correctly built (bottom inset reserved); 176pt fixed chrome is all necessary UI; list is must-scroll by nature (~9-10 rows fit before scrolling).
- "Untouchables" and "team picker" are inline anonymous Modals in TradeFinderHubScreen (already sized-to-content post-#242); calculator team-switching is an inline chip row, not a sheet — excluded.

---

## Chalkline violations noticed in passing (not scroll items)

- **TradeValueBar.tsx:223,227 — `fontSize: 9`** on scale labels: below the documented 11px floor. The only literal floor violation on these surfaces, present in every TradeValueBar instance.
- AssetIdeasPanel.tsx:268 — inTag text overridden to fontSize 10 (below floor); :257 diffText 12/16 is an off-scale literal; :255-256 hardcoded rgba variants of semantic.pos/neg (token drift risk).
- OutlookSheet 90% maxHeight vs the 85% convention; no bottom safe-area handling.
- TradeFinderHubScreen: three ad-hoc 11-12px font literals (untChipText, outCardBias, dnaHint) — at/above floor but scale drift.
- FeaturedTradeWindow backChipText mixes tokens (bodySm metrics + title fontFamily).

## Top 10 (impact × ease) — Trades surfaces overall

1. Single-pin mode: collapse the Controls Card to a pinned-summary one-liner (~240pt, the hero state of the app's newest flow)
2. Conditional `deckWrap` minHeight (~240pt in empty/first-run states)
3. InLeagueCalculator opponent picker: `numberOfLines={1}` on summaryLine (bounds a ~520pt sprawl; one-line fix)
4. TradeValueBar: collapse verdict paragraph behind a disclosure (~68pt × every instance, app-wide)
5. Screen padding/gap lg→md/sm on TradesScreen + calculator (the #218 precedent; ~48-64pt each)
6. TradeValueBar fontSize:9 → 11px floor fix (violation, trivial)
7. OutlookSheet: #242 size-to-content pattern + the three free-space trims (+ bottom inset safety)
8. Suggestions/add-ons: cap visible SuggestionCards at 1-2 + "Show more" (bounds 366pt worst case)
9. Doubled marginBottom on TradeFinderModeBar/OutlookBiasReceipt (24pt, trivial)
10. Update stale #218 status doc (hygiene; the audit's reference standard should describe the shipped UI)
