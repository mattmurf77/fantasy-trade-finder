# #243 — Scroll audit: RANK tab surfaces

**Status: read-only audit, 2026-08-02. No code changed.**

Scope: `QuickSetTiersScreen`, `QuickRankScreen`, `RankHomeScreen`, `TiersScreen`,
`ManualRanksScreen`, `RankScreen` (Trios), `PickAnchorScreen`,
`RankImportSheet`, and the `RankMenu` sheet (`TabNav.tsx`). Method follows the
#218 hub density pass (`docs/feedback/items/218-hub-fit-to-screen/status.md`):
estimate nominal content height from the styles actually read (padding, gaps,
line heights, fixed heights, typical list-item counts), flag overflow, and
rank concrete reductions by estimated pt saved.

## Budget assumptions (read this before the per-screen sections)

- Device reference: iPhone 15/16-class, 393×852pt, top safe inset 59pt,
  bottom safe inset 34pt, tab bar 49pt — same constants #218 used.
- **The global `TopBar` (52pt) renders above every tab, including pushed
  Rank-stack screens** — confirmed in `TabNav.tsx`: `<TopBar /><Tab.Navigator>`
  sits outside the tab navigator entirely, so it mounts once for the whole
  authed app, not per tab-root.
- **Every Rank-stack sub-screen ALSO renders its own native stack header.**
  `RankStackNav` sets `screenOptions={{ headerShown:false }}` at the
  navigator level, but every individual `RankStack.Screen` (RankHome, Trios,
  Anchors, Tiers, QuickSetTiers, QuickRank, ManualRanks, Trends) overrides
  this via `subScreenOptions`/`rankSubScreenOptions`, both built on
  `chalklineHeader(title)` which sets `headerShown: true`. So a Rank-stack
  screen pays for **both** the 52pt global TopBar *and* a native stack
  header (~44pt, iOS compact non-large-title default) stacked directly
  underneath it. `components.md`'s own TopBar spec says "per-screen page
  identity moved into page content (in-page heading or the native stack
  header)" — implying the intent was *either/or*, not both. This double
  chrome is the single biggest fixed cost on every Rank-stack screen and is
  called out as its own finding below (see Top-10 #1 is the RankMenu bug;
  this double-header cost is folded into every per-screen budget instead of
  repeated per section).
- **Content budget for Rank-stack pushed screens** (RankHome, Trios,
  Anchors, Tiers, QuickSetTiers, QuickRank, ManualRanks):
  852 − 59 (top inset) − 52 (TopBar) − 44 (native header) − 49 (tab bar) −
  34 (bottom inset) = **614pt**. This is an estimate (exact native header
  height wasn't measured at runtime) — treat it as a ±20pt band, not a
  precise cutoff.
- Sheets (`RankMenu`, `RankImportSheet`) aren't tab-hosted; budget them
  against the audit brief's "~85% height" guidance, ≈724pt.
- Unbounded lists (Tiers board, Overall Ranks board) are expected to scroll
  once populated — the question for those two is only "does the chrome
  above the list fit, leaving the list a healthy majority of the screen."

---

## RankMenu sheet (`TabNav.tsx`) — CRITICAL, not a density issue

**Verdict: broken, not just tight.** No `maxHeight` on the sheet at all, and
no `ScrollView` wrapping its rows — it's a plain `<View style={styles.sheet}>`
with `position:'absolute', bottom:0` and every row (`Pressable`) listed
directly inside it:

```
sheet: {
  position: 'absolute',
  left: 0, right: 0, bottom: 0,
  ...
  padding: space.lg,
  paddingBottom: space.xxl,
  gap: space.sm,
  ...shadowSheet,
},
```

Collapsed nominal state (3 primary rows, disclosure closed): handle(12) +
heading "Rank"(26) + sheetSub(26) + 3× primary item row (padding
32+itemLabelRow 14+itemLabel 22+itemSub-2-lines 36+border1 ≈105 each = 315)
+ moreHeader(44) + Cancel button(56) + vertical sheet padding(48) + 7 inter-row
gaps×8(56) ≈ **583pt** — fits inside the 852pt screen with room to spare, so
collapsed it looks fine.

Tap "More ways to rank" (`rankmenu.more-toggle`) and it renders the 3
`MORE_METHODS` rows too — each a shorter variant of the same `item` style
(padding32 + title22 + 2-line sub36 + border1 ≈ 91pt) × 3 = 273pt, plus 3
more 8pt gaps = 24pt. **New total ≈ 880pt — taller than the 852pt screen
itself**, with no `maxHeight`, no `overflow:hidden`, and no scroll
mechanism anywhere in the component. Because the sheet is bottom-anchored
and grows upward with its content, the top ~28pt of content (the "Rank"
heading and the start of `sheetSub`) renders above y=0 — off the physical
top edge of the device. There's no way to scroll up to it; it's simply
gone. This is verifiable from the source alone (no `maxHeight`, no
`ScrollView` present) — high confidence, no runtime check needed.

Contrast with `RankImportSheet`, which does this correctly:
`sheet: { ..., maxHeight: '88%', ... }` plus its review step wraps rows in
`<FlatList style={styles.list} ...>` inside that capped sheet. `RankMenu` is
the one outlier among the Rank surfaces.

**Fix (structural, not density):** give `styles.sheet` a `maxHeight` (mirror
`RankImportSheet`'s `'88%'`) and wrap the row list in a `ScrollView` (or a
`FlatList`) so expanding the disclosure scrolls the sheet instead of growing
it past the screen. Trivial, low-risk change; this is the highest-priority
item in this whole audit because it's the only *broken* (not just
sub-optimal) surface in scope.

---

## QuickSetTiersScreen (Rank tab default / guided walk)

**Verdict: chrome fits comfortably; the FlatList's missing `style` prop is a
separate structural risk that undermines "does it scroll when it needs to."**

### Budget math (typical step, 12 chips)

Fixed chrome above the grid:

| Block | pt |
|---|---|
| `formatRow` (marginTop 8 + FormatToggle 38) | 46 |
| `switcher` (marginTop 8 + row 46) | 54 |
| `stepHeader` (padding 20 + title row ~20 + hint, 2 lines ~36 + xs margin 4) | 80 |
| `search` (height 40 + marginBottom 8) | 48 |
| **Chrome subtotal** | **228** |

Grid content at 12 chips (3/row → 4 rows × 48pt chip + 3× xs(4) row gaps):
**204pt**. Footer (Back/Skip/Save) is `position:'absolute', bottom:0` — it
always overlays the bottom ~64pt of the screen regardless of scroll
position, so it can never itself be "below the fold" (good — this screen
does NOT have the worst-offense pattern the audit brief warns about).

Chrome(228) + grid(204) = 432pt vs the 614pt budget minus the 64pt the
footer permanently occupies (550pt usable) → **fits, ~118pt spare** at 12
chips. At a low-chip step (top tiers, "4+ 1sts") it's even more spare. At a
high-chip step (e.g. FA/waivers with 25-35 remaining players ≈ 9-12 rows)
the grid alone runs 430-580pt, which **does** exceed the 550pt usable
budget — expected, and fine in principle, since a variable-length player
pool is an unbounded list by nature (per the audit brief's own carve-out).

### Structural risk: the grid `<FlatList>` has no `style` prop

```
<FlatList
  data={visiblePlayers}
  keyExtractor={(p) => p.id}
  renderItem={renderChip}
  numColumns={3}
  columnWrapperStyle={styles.gridRow}
  contentContainerStyle={styles.grid}
  keyboardShouldPersistTaps="handled"
  ListEmptyComponent={...}
/>
```

No `style={{ flex: 1 }}` (or explicit height) anywhere. Compare to
`TiersScreen`'s and `ManualRanksScreen`'s drag lists, which both pass
`containerStyle={styles.listContainer}` = `{ flex: 1 }` to
`DraggableFlatList`. Standard RN flexbox: a child with `flexGrow: 0`
(the default) inside a `flex:1` column parent does not get any of the
parent's leftover space — it renders at its own natural content height.
At high chip counts (the FA/waivers step above), that means the grid's
*true* rendered height can exceed the physical screen, and — because
neither `SafeAreaView` nor `KeyboardAvoidingView` above it is a scroll
container — the overflow isn't reachable by any gesture. The pinned footer
still shows (it's absolutely positioned), but chip rows past the bottom
edge become untappable, i.e. **some players may be impossible to select at
a busy step**. This is a static-analysis read, not confirmed against a
running build — recommend a quick simulator check on the FA/waivers step
for a position with a deep pool before treating it as fact, but it's
worth fixing regardless: add `style={{ flex: 1 }}` to give the grid its
own bounded, correctly-scrolling region. `QuickRankScreen` has the
identical pattern (see below) — same fix, same file-shape.

### Ranked suggestions

1. **(c, structural, do first)** Add `style={{ flex: 1 }}` to the grid
   `FlatList`. Not a density change — a correctness fix that makes "does it
   scroll when it needs to" actually true. No pt estimate (this doesn't
   shrink content, it restores reachability).
2. **(b, density)** Trim `stepHint` from 2 sentences to 1 ("Tap every
   {position} for {tier}; each chip shows their current tier.") — saves
   ~18pt (2 lines → 1) at typical widths.
3. **(a, free space)** `stepHeader` padding 12/8 → 8/4 (mirrors #218's
   literal-value trims) — saves ~8pt.
4. **(a, free space)** Drop `switcher`'s `marginTop: space.sm` (formatRow
   already separates it) — saves ~8pt.

---

## QuickRankScreen (Quick rank follow-on)

Same chrome shape as QuickSetTiers minus the footer's Skip-hide state (Skip
always renders here). Chrome subtotal ≈ **226pt** (stepHint text is
similarly long — "Tap players best-first — each tap sets the next rank.
Anyone you don't tap slots in below your last pick, in their current
order." — 2 lines). Same math, same verdict: **fits at typical tier sizes,
same missing-`style` risk on its grid `<FlatList>`** (identical code
shape — no `style` prop).

### Ranked suggestions

1. **(c, structural, do first)** Same `style={{ flex: 1 }}` fix as
   QuickSetTiers — identical pattern, same file.
2. **(b, density)** Trim `stepHint` to one sentence — saves ~18pt.
3. **(a, free space)** Same `stepHeader`/`switcher` trims as QuickSetTiers —
   ~16pt combined.

---

## RankHomeScreen (chooser)

**Verdict: overflows by ~35-40pt in the nominal state** (3 primary cards +
collapsed disclosure — the state most users see, since "More ways to rank"
is collapsed by default).

### Budget math

`ScrollView contentContainerStyle={{ padding: lg(16), gap: md(12) }}`:

| Block | pt |
|---|---|
| Screen padding (top+bottom) | 32 |
| `headingRow` (heading, 1 line) | 26 |
| `callout` (padding 24 + icon/2-line text 38) | 62 |
| Quick set card (featured, has `subRow`) | 173 |
| Head-to-heads card | 116 |
| Tiers board card | 116 |
| `moreHeader` (collapsed) | 52 |
| `mixNote` (2 lines, centered) | 36 |
| Inter-block gaps (6 × 12) | 72 |
| **Total** | **≈ 685** |

(Slightly higher than my first-pass estimate of 653 once the gap count is
walked precisely — either way it clears the 614pt budget by ~40-70pt, i.e.
a small persistent scroll, the same flavor of complaint that drove #218.)

### Ranked suggestions

1. **(a, free space)** Screen padding `lg`(16)→`md`(12): −8pt. Inter-card
   gap `md`(12)→`sm`(8) across 6 gaps: −24pt. Callout padding `md`(12)→
   literal `10` (#218 precedent): −4pt. **Subtotal ≈ −36pt.**
2. **(b, density)** Shorten the two non-featured cards' `body` copy so it
   wraps to 1 line instead of 2 (currently ~110-130 char sentences at
   `bodySm` 13/18 in a ~361pt column reliably wrap twice) — e.g. "Put three
   players in order — your board sharpens with every answer." −19pt ×2
   cards = **−38pt**.
3. **(b, density)** Shorten the Quick set card's `subRow` lead-in text
   similarly (1 line instead of 2) — **−18pt**.
4. **(c, structural)** Fold `mixNote` ("Every method writes to the same
   board...") into the `moreHeader` row as a trailing caption, or drop it
   under the disclosure (it's evergreen orientation copy, not per-card
   info) — reclaims the whole always-visible block: **−48pt** (36pt text +
   12pt gap).

Total addressable ≈ **120pt**, which would take the nominal state from
~685pt to ~565pt — comfortably under the 614pt budget with margin for
Dynamic Type growth, matching the #218 hub's own before/after magnitude.

---

## RankScreen (Trios / head-to-heads)

**Verdict: overflows significantly (~120pt) in the nominal state** (no
streak chip, no unlock-payoff copy, no Confirm button shown pre-selection,
no unlocked banner) — this is the biggest single overflow in the audit, and
it already ships as a scrolling `ScrollView`, so users already pay this
cost today.

### Budget math

| Block | pt |
|---|---|
| Screen padding (top+bottom) | 32 |
| `modeHint` (1 line, negative margin) | 14 |
| `FormatToggle` | 38 |
| Position `switcher` (minHeight 48 + border) | 50 |
| `progressWrap` (track + 1 progress line) | 28 |
| `instruction` (1 line + padding 16) | 37 |
| **3 stacked `PlayerCard`s** (classic variant, ~104pt each + 2×12 gaps) | **≈ 324** |
| `speedTile` (marginTop 16 + padding 24 + 2 lines) | 80 |
| `actions` row (marginTop 16 + button ~44) | 60 |
| Inter-block gaps (7 × 12) | 84 |
| **Total** | **≈ 747** |

vs the 614pt budget → **overflow ≈ 133pt**. The three `PlayerCard`s stacked
vertically are **43% of total content height** and by far the dominant
line item — everything else on the screen is comparatively cheap.

### Ranked suggestions (ordered by estimated savings)

1. **(c, structural, biggest lever)** The three cards render as a full
   vertical stack (`cards: { gap: space.md }`, no `flexDirection: 'row'`,
   default column) even though the interaction (tap to rank 1/2/3, all
   three visible at once) doesn't require full-width cards. A horizontal
   3-up row (each card ~1/3 width) would collapse this block from ~324pt to
   roughly one card's height (~110-130pt) — **potential savings ~180-200pt**,
   the single largest lever in this entire audit. Caveat: this needs a
   narrower card treatment (name truncation, badge wrapping at ~110pt
   width) — it's a real design pass, not a pure prop change, and readability
   at 1/3 width needs a mock before committing.
2. **(c, structural, lower-risk alternative to #1)** Short of a full
   horizontal reflow, pass the existing `compact` prop to `TrioPlayerCard`
   → `PlayerCard` (`padding: space.md` instead of `space.lg`, and drops the
   years-experience meta segment). This is a prop that already exists and
   is used elsewhere (`PlayerCard.tsx` `cardCompact: { padding: space.md }`)
   — near-zero engineering risk. Estimated **−24 to −30pt** across the 3
   cards (8-10pt padding trim each). Note `dense` mode (the Tiers board's
   60pt row) is NOT a drop-in option here without extra work — its layout
   doesn't render the rank-number badge Trios needs (`ranked && rankBadge`
   only exists on the classic branch), so reusing it would need new
   plumbing, not just a prop flip.
3. **(a, free space)** `scroll` padding `lg`(16)→`md`(12): −8pt. Gaps
   `md`(12)→`sm`(8) across 7 gaps: −28pt. `speedTile`/`actions` margins
   `lg`(16)→`md`(12): −8pt combined. **Subtotal ≈ −44pt.**

Even the padding/gap trims (#3, ≈44pt) plus the compact-prop win (#2,
≈27pt) only recover ~71pt against a 133pt overflow — the horizontal reflow
(#1) is the only lever big enough to make this screen actually fit without
scrolling; short of that, Trios stays a legitimately-scrolling screen (which
is defensible — it's showing 3 full player identities at once by design —
but it's the surface most worth a real design pass if "no scroll on Rank
surfaces" is a hard goal).

---

## TiersScreen (Tiers board) — unbounded list, chrome-only matters

**Verdict: fits, healthy margin.** This is the "40-player board must scroll"
case the audit brief carves out — the question is only whether the chrome
above the (correctly scrollable, `DraggableFlatList` with `containerStyle:
{flex:1}`) board eats too much of the screen.

### Budget math (collapsed, `ux.board_search` off — its default)

| Block | pt |
|---|---|
| `headerRow` (padding 16 + title/actions row ~38) | 54 |
| `formatRow` (marginBottom 8 + FormatToggle 38) | 46 |
| `switcher` (row 46) | 46 |
| `copyBtn` (marginTop 8 + minHeight 44) | 52 |
| `boardBar` (padding 8 + hint 2-line 36) | 52 |
| **Chrome subtotal** | **250** |

614 − 250 = **364pt for the list** (~5.7 tile rows at 60pt+4pt gap before
any scrolling) — a healthy majority of the screen. The existing `#81`
expand/collapse control (hides header/formatRow/copyBtn) already improves
this to ~528pt of list room when toggled — a good existing pattern, not a
new suggestion.

### Ranked suggestions (low priority — already fits)

1. **(a, free space)** `headerRow`/`formatRow` vertical padding trims
   (#218-style, `sm`(8)→literal 6) — **−12 to 16pt**, grows visible rows
   marginally. Not urgent.
2. **(c, structural, optional)** `copyBtn` ("Copy tier list from...") is a
   full-width secondary button for an infrequent power-user action (switch
   formats and copy the other format's tiers). Demoting it to an icon
   button in `headerActions` (mirroring the `#81` expand toggle's slot)
   would free **~52pt** of always-visible chrome. Only worth doing if the
   list room ever needs to grow further — not needed today given the 364pt
   margin.

---

## ManualRanksScreen (Overall Ranks) — unbounded list, chrome-only matters

**Verdict: fits, generous margin.**

| Block | pt |
|---|---|
| `headerRow` (padding 16 + title 26) | 42 |
| `hint` (2 lines + padding 8) | 44 |
| `filterRow` (marginBottom 8 + row 46) | 54 |
| **Chrome subtotal** | **140** |

614 − 140 = **474pt for the list** (~7+ rows before scrolling) — the most
headroom of any surface in this audit. No action needed; noting a couple of
trivial trims for completeness only:

1. **(a, free space)** `hint` could drop to 1 line ("Drag to re-rank; tap
   the rank number to jump.") — **−18pt**. Optional, screen already fits
   with wide margin.

---

## PickAnchorScreen (Pick Anchors wizard)

**Verdict: fits, generous margin.** `ScrollView` content (scope pills +
progress line + player card + question + 2 button rows + skip + hint) sums
to **≈414pt** against the 614pt budget — ~200pt spare. No suggestions
warranted; lowest priority in this audit.

---

## RankImportSheet ("Bring your rankings")

### Paste step

Sheet `maxHeight: '88%'` (≈750pt budget, correctly capped, unlike RankMenu).
Nominal content (handle + heading + 3-line intro copy + 170pt paste box +
row-count line + honesty box + Match/Cancel buttons) sums to **≈530pt** —
fits comfortably, no action needed.

### Review step — flag, don't fix here

The results `<FlatList style={styles.list} ...>` where `list: { flexGrow:
0 }` is an **explicit, deliberate** style (unlike QuickSet's *missing*
style) — someone chose not to let this list flex. Inside a `maxHeight: 88%`
sheet with no other scroll container, a large import (30-50+ pasted rows)
would render the full row list at its natural height and rely on the
sheet's `maxHeight` to cap it — but nothing sets `overflow: 'hidden'`
explicitly either, so the actual clipping behavior at high row counts is
genuinely uncertain from source alone and worth a runtime check with a
50+-row paste. If it does clip, rows past the cutoff (including the Apply
footer) become unreachable — the exact "hides the Save button below the
fold" failure mode the audit brief calls out as the worst offense, just on
a sheet instead of a full screen.

**Suggestion (c, structural):** change `list: { flexGrow: 0 }` to
`{ flex: 1 }` so the row list gets its own bounded, internally-scrolling
region within the capped sheet, leaving the header/footer always visible.
Low effort, addresses a real (if import-size-dependent) risk.

---

## Top 10, ranked by impact × ease

| # | Surface | Fix | Type | Est. impact | Effort |
|---|---|---|---|---|---|
| 1 | `RankMenu` sheet (TabNav.tsx) | Add `maxHeight` + wrap rows in a `ScrollView` (mirror `RankImportSheet`) | Structural / correctness | **Critical** — top content unreachable today when disclosure is open (≈880pt content vs 852pt screen, no scroll at all) | Low |
| 2 | QuickSetTiers + QuickRank grid `FlatList` | Add `style={{flex:1}}` to both screens' grids | Structural / correctness | High — restores reachability of chip rows past the fold at busy steps (both are the app's default entry surfaces) | Low |
| 3 | `RankScreen` (Trios) | Reflow the 3 stacked `PlayerCard`s to a horizontal 3-up row | Structural | High — ~180-200pt, the single largest recoverable block in the audit | Medium-high (needs a mock) |
| 4 | `RankHomeScreen` | Padding/gap trims + shorten 3 card-body strings to 1 line + fold `mixNote` into the disclosure header | Free space + density + structural | Medium — ~120pt, takes the chooser from a small persistent scroll to comfortably fitting | Low |
| 5 | `RankImportSheet` review step | `list: {flexGrow:0}` → `{flex:1}` | Structural | Medium (import-size-dependent) — protects large pastes from clipping | Low |
| 6 | `RankScreen` (Trios) | Pass the existing `compact` prop to the 3 trio cards | Density | Medium — ~24-30pt, near-zero engineering risk, works alongside or instead of #3 | Very low |
| 7 | QuickSetTiers + QuickRank | Trim `stepHint` to 1 sentence + tighten `stepHeader` padding | Density + free space | Low-medium — ~25-35pt each, more headroom before typical (8-15 chip) steps need to scroll | Low |
| 8 | `RankHomeScreen` | (part of #4, called out separately) fold `mixNote` under the disclosure toggle | Structural | Low-medium — ~48pt on its own | Low |
| 9 | `TiersScreen` | Header/format-row padding trims (#218-style) | Free space | Low — already fits (364pt list margin); marginal row-count gain | Low |
| 10 | `TiersScreen` | Demote "Copy tier list from..." to an icon button (mirrors the `#81` expand toggle's slot) | Structural | Low — ~52pt, optional; only worth it if list room needs to grow further | Low |

Not included above because they already fit with wide margin and need no
action: `ManualRanksScreen` (474pt spare), `PickAnchorScreen` (~200pt
spare), `RankImportSheet` paste step (~220pt spare).
