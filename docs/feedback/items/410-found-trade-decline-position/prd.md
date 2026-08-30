# PRD — G-410: merged-canvas trade-card polish (#410 · #411 · #412 · #409-copy)

> Build spec for the group whose plan is [plan.md](plan.md). Four user-visible
> fixes on one surface (the `calc.canvas_results` browse session hosted by the
> merged calculator canvas on `TradesHome`) plus one client-only copy correction
> that rides the same build. **17 numbered requirements.**
>
> Branch: `claude/fb-410-412-trade-card-polish`, cut from `origin/main`
> `bd83fe94`, currently `11c8903c` (= `bd83fe94` + the FB-409 backend fix).
> Scope block: [scope.md](scope.md). Operator rulings and open-question
> resolutions: [reconciliation-log.md](reconciliation-log.md).
>
> **Every file:line in this document was re-verified against the working tree on
> 2026-08-30.** Where the plan's claim did not survive verification, this PRD
> says so and states the corrected fact — see §7.1 and §9.

## Table of contents

- [1. What ships](#1-what-ships)
- [2. Requirements — #410, the decline control](#2-requirements--410-the-decline-control)
- [3. Requirements — #411, player-name truncation](#3-requirements--411-player-name-truncation)
- [4. Requirements — #412, "More offers" placement](#4-requirements--412-more-offers-placement)
- [5. Requirement — #409 refusal copy](#5-requirement--409-refusal-copy)
- [6. Known limits](#6-known-limits)
- [7. Test plan (D-056)](#7-test-plan-d-056)
- [8. Code-walk proof outline](#8-code-walk-proof-outline)
- [9. Operator TestFlight checklist](#9-operator-testflight-checklist)
- [10. Success criteria](#10-success-criteria)
- [11. Out of scope](#11-out-of-scope)
- [12. Guardrails](#12-guardrails)
- [13. The D-169 entry, verbatim](#13-the-d-169-entry-verbatim)

---

## 1. What ships

| # | Report | Fix |
|---|---|---|
| **#410** | *"X button should replace the 'clear' button next to check box when a found trade is suggested."* | During a live browse session the action row's middle cell becomes the **decline ✕**; the pager ✕ is removed. Closes a real data-loss defect (R-6). |
| **#411** | *"Move the position tag to the second row… Pressure test whether the names stop getting truncated."* | Position chip moves to the meta line; the compact name drops one step on the Chalkline scale (16 → 13pt). |
| **#412** | *"Reversion from prior version.. move more offers underneath the add a player button"* | The shop entry moves from the pager row into the give column, under "Add player". |
| **#409 (copy)** | *"error when liking trades that a user isn't in this league"* | The `not_league_member` refusal line stops naming the partner. The server half already shipped (`11c8903c`); this is the client half. |

**One owner, one branch.** No backend, no schema, no API, no new flag, no new
analytics event. Rollback lever is the existing
`calc.canvas_results` / `calc.inline_home` / `calc.merged_layout` conjunction
(#410, #412) — #411 and #409-copy are unconditional and revert by revert.

---

## 2. Requirements — #410, the decline control

**Operator ruling (verbatim, 2026-08-30):** *"It does mean pass / Keep the x
button."* The operator was shown [D-157](../../../../living-memory/DECISIONS.md)
(the bare ✕ in this exact cell was replaced by the word "Clear" after tester
Segrave misread it as pass and wiped his canvas) and
[canvas-results-spec.md §4](../402-more-offers-shop/canvas-results-spec.md)'s
*"placement: with the pager, never inside the action row's 50/30/20 cells"*, and
chose the ✕ knowingly. **Do not re-open. Do not substitute a word.**

### R-1 — The middle cell forks on host-declared browse state

While the host declares a live browse session with an idea fronted, the action
row's middle cell is the **decline control**, routed through the host's existing
`handleBrowsePass` (`mobile/src/screens/TradesScreen.tsx:5750`) — the same
two-layer `trade_pass_overlay_*` machinery, the same
`commitReasonAdvance` → idea-splice, the same `/api/trades/pass-reason` writes.
**No parallel pass path, no new handler, no new endpoint, no new event.**

In every other state the cell is **Clear, byte-identical to today**
(`mobile/src/components/InLeagueCalculator.tsx:1301-1319`): empty canvas,
hand-built canvas with no session, flag off, the pushed Real-values page
(`mobile/src/screens/TradeCalculatorScreen.tsx:751`), `FeaturedTradeWindow`
(`mobile/src/components/FeaturedTradeWindow.tsx:82`), and the #270 experiment
mount.

### R-2 — The decline cell renders a bare ✕ glyph; the Clear cell keeps its word

- **Decline branch:** `<Icon name="x" size={16} color={semantic.neg} />`, centered
  — the identical glyph, size and color the pager ✕ uses today
  (`TradesScreen.tsx:7397`). `testID="calc.action.decline"`.
  `accessibilityRole="button"`, `accessibilityLabel="Pass on this trade idea"`
  (verbatim from `TradesScreen.tsx:7394`, so VoiceOver still carries the verb the
  glyph does not).
- **Clear branch:** unchanged — `testID="calc.action.clear"`, the word `Clear` in
  `styles.actionClearText` (`InLeagueCalculator.tsx:1318`, `:2067`),
  `accessibilityLabel="Clear the trade"`.
- **Two testIDs, two verbs.** `testid-lint` needs static literals: neither id may
  be built by a conditional expression, and `calc.action.clear` must survive
  verbatim (retained `.maestro/` flows reference it; the files are never run but
  the lint still reads them).
- **Chrome:** the decline cell keeps the Clear cell's neutral chrome
  (`styles.actionClear` + `styles.actionBtn`, **no** `styles.actionPrimary`), so
  ice stays rationed to `Find a Trade` and the ✓.

### R-3 — The 50/30/20 flex is byte-identical

`actionFind: { flex: 50 }` / `actionClear: { flex: 30 }` /
`actionSmall: { flex: 20 }` (`InLeagueCalculator.tsx:2049-2051`) are **not
edited**. The ✓ cell (`:1322-1352`) is **not edited**. This is the narrow reading
under which canvas-results-spec §4's stated rationale survives its placement
clause being overturned (see R-9 and §13).

### R-4 — Exactly one decline control is ever mounted

The pager ✕ block — `TradesScreen.tsx:7390-7401`, `testID="trades.canvas-results.pass"`
— is **removed**, along with the `browsePassBtn` style if it has no other
consumer. This mirrors `TradeCard`'s `reasonsAsOverlay` rule (exactly one
presentation is ever mounted). The pager's `‹ N / X ›`, its model-path Clear
(`:7369`) and the anchor receipt's Clear (`:7494`) are **unchanged**;
`handleBrowseClear` (`:5686`) is **unchanged**.

### R-5 — The fork arrives as an optional host prop, never a flag read

New optional prop, threaded `TradesScreen` → `TradeBuildCanvas` →
`InLeagueCalculator` in the same family as `onSidesChange` / `seededPrefill` /
`hideFormatChips`:

```ts
/** #410 — host-declared browse state. Absent/null ⇒ today's Clear cell,
 *  byte-identical for every pre-#410 host. The host owns the predicate
 *  (browseLive && sortedDeck.length > 0 && declineReasonProps); this
 *  component reads no flag — the two-host contract (check-canvas-results 4l). */
browseDecline?: { onPress: () => void } | null;
```

- `InLeagueCalculator.tsx` gains **zero** occurrences of `canvas_results` or
  `canvas-results` (the existing `4l` assertion, `check-canvas-results.js:270-271`,
  must stay green — see §7.1).
- `TradeBuildCanvas.tsx` passes it straight through
  (`mobile/src/components/TradeBuildCanvas.tsx:173-186`), adding no logic.
- Absent at `FeaturedTradeWindow.tsx:82` and `TradeCalculatorScreen.tsx:751`.

### R-6 — The browse-session data-loss defect is closed, not preserved

**This is a defect, not cosmetics.** Today, during a live browse session:

1. The action-row Clear calls `clear()` (`InLeagueCalculator.tsx:843-848`), which
   empties both sides.
2. The `onSidesChange` effect (`:386-392`) fires with `([], [])`.
3. `handleBrowseSidesChange` (`TradesScreen.tsx:5732-5738`) snapshots
   `{give: [], receive: []}` into the browsed idea's edit map under
   `browseSeededIdRef.current`.
4. The pager stays live over an empty canvas. Paging away and back re-seeds the
   **emptied** idea (`TradesScreen.tsx` seeding effect, pinned by
   `check-canvas-results.js` 5f) — the engine's original is gone. The only
   recoveries are ending the whole session or a fresh Find a Trade.

**Requirement:** when the decline branch is live, `clear()` and its
`track('calc_cleared', …)` (`:845`) are **unreachable from the action row**, so
step 1 cannot start. The build must not "fix" this by making the decline handler
also call `clear()`, and must not add a disabled-Clear fallback that still
reaches `clear()`.

Residual (accepted, stated): a user can still empty the canvas during a session
by tapping each row's remove ✕ — that is a deliberate per-asset edit and the edit
map capturing it is the #402 §3 feature working as designed. What R-6 removes is
the **single-tap, whole-canvas, silent** version of it.

### R-7 — Kill-switch parity with the control it replaces

The pager ✕ renders only when `declineReasonProps` is truthy
(`TradesScreen.tsx:7390`, gated on `feedback.decline_reasons`;
`handleBrowsePass` re-checks at `:5752`). The action-row decline branch inherits
that gate exactly: **`browseDecline` is passed as `null` when `declineReasonProps`
is undefined**, so under the kill switch the cell falls back to **Clear** rather
than degrading to a bare-pass path (the deleted fallback and its lying "Passed —
Undo" toast — `TradesScreen.tsx:5753-5762`). Under the kill switch the session
therefore has no decline control at all, which is exactly today's behavior.

### R-8 — The double warning haptic is resolved in place

`InLeagueCalculator.tsx:1311` fires `haptics.warning()` and then calls `clear()`,
which fires `haptics.warning()` again at `:844`. These are the exact lines R-1
rewrites, so the duplicate is removed inside the change's own footprint (not a
drive-by). The decline branch fires `haptics.selection()` once — matching
`handleBrowsePass`'s own `haptics.selection()` (`:5753`) — and must not fire a
second one; the handler already owns it.

### R-9 — A new decision entry amends D-157 and the canvas-results-spec contract

Two written artifacts become false and must be amended in the same commit:

1. **`living-memory/DECISIONS.md`** gains **D-169** (next id = max existing + 1;
   `D-168` at `living-memory/DECISIONS.md:1043` is the current max, verified
   2026-08-30). Insert adjacent to D-168 and add the matching row to the
   **Decision index** table at `living-memory/DECISIONS.md:438`. The exact text
   is in [§13](#13-the-d-169-entry-verbatim).
2. **`docs/feedback/items/402-more-offers-shop/canvas-results-spec.md` §4**, first
   bullet. Replace the parenthetical

   > `(placement: with the pager, never inside the action row's 50/30/20 cells — that row's proportions are D-157 and unchanged)`

   with

   > `(placement: the action row's middle cell during a live browse session — amended 2026-08-30 by D-169 on the operator's ruling; the row's 50/30/20 proportions are D-157 and remain unchanged, which is the part of this clause that was load-bearing. Before D-169 this control lived with the pager.)`

   Leave the rest of §4 verbatim — the reason-machinery, banked-pass/dismiss and
   server-write semantics are unchanged by #410 and are what R-1 reuses.

### R-10 — The D-157 tour beat n19 is re-checked and the finding recorded

D-157 requires n19 to be re-checked at build time. **It has been checked; the
finding is recorded here so the build agent does not re-derive it, and the build
agent's job is to confirm it still holds and change nothing.**

`mobile/src/components/analystScript.ts:549-558` — `n19` reads
*"Clear became this cross. It records why you passed; the check still accepts."*
with `target: 'trades.pass-btn'`.

- The **copy does not misdescribe the post-#410 UI.** After R-1 the calculator's
  middle cell literally becomes a cross that records why you passed, which is
  what the line says. No copy change is owed.
- The **target is already dark on this host, pre-existing.** `trades.pass-btn` is
  registered only by `TradeCard` (`mobile/src/components/TradeCard.tsx:274`,
  `:792`), and canvas-results-spec §2 retires the deck while a session exists —
  so n19's spotlight points at nothing on the merged path today, independently of
  #410. **Do not re-target it in this change** (the tour is Wave B and suppressed
  on this path; re-targeting is a tour-merge decision, not a polish one). Record
  the seam in the reconciliation log: if the tour is ever unsuppressed on the
  canvas-results host, `n19.target` becomes `calc.action.decline`.

---

## 3. Requirements — #411, player-name truncation

**Operator ruling (2026-08-30):** **tag move + shrink the name text.** Chosen
over the two-line option after being told the tag move alone leaves star names
truncated. Constraints, all absolute: the Chalkline **11pt floor**
(`docs/design/design-system.md:107` — *"Type floor: no text below 11px anywhere"*),
the position chip stays the specced Badges-&-chips construction with its
`docs/cross-client-invariants.md` colors, and **`numberOfLines` stays 1** — the
operator did **not** choose wrapping. Do not add it.

### 3.1 The width budget, re-verified

| Step | Source (verified 2026-08-30) | Width |
|---|---|---|
| ScrollView content, 375pt device | `TradesScreen.tsx:9215` — `scroll: { padding: space.lg }`, `space.lg = 16` | 375 − 32 = **343** |
| One column | `InLeagueCalculator.tsx:2033` gap `space.sm` (8) · `:2037` `column: {flex:1, flexBasis:0, minWidth:0}` | (343 − 8) / 2 = **167.5** |
| Card inner | `components/chalkline/Card.tsx:43-45,53` — `borderWidth: 1` ×2 + `body: { padding: space.lg }` ×2 | 167.5 − 34 = **133.5** |
| `info` (flex 1) | `TradeSide.tsx:205` `info: {flex:1}`; `rowCompact` gap `space.xs` (4) + the 32pt remove `Pressable` (`:206`, `:146-156`) | 133.5 − 36 = **97.5** |

97.5pt is the name's budget once the chip leaves line 1. The file's own comment
at `TradeSide.tsx:96-97` says "the ~97pt of info width a 375pt screen leaves" —
the chain and the comment agree.

### 3.2 Measured widths — method

Advance widths summed from **the shipped font binary**,
`mobile/node_modules/@expo-google-fonts/archivo/600SemiBold/Archivo_600SemiBold.ttf`
(`unitsPerEm` 1000), via `fontTools` `hmtx`. `type.title` and `type.bodySm` carry
no `letterSpacing`, so width = Σ advances × size / 1000. GPOS kern pairs are
**not** applied — Archivo's kerning for these strings is under 1% of total width
and omitting it makes every number slightly **wide**, i.e. conservative. Corpus
for the fit rates: `backend/tests/fixtures/player_pool_2026.json` (340 real
Active QB/RB/WR/TE intersected with DynastyProcess values), ranked by
`dp_value_1qb`.

### 3.3 The size decision

Chalkline's type scale is a closed 8-token table
(`docs/design/design-system.md:97-105`). Below `title` (16/22) there are exactly
two legal steps — `body` (Archivo 400, 14/21) and `body-sm` (Archivo 400, 13/18)
— plus `label` (11/14), which is **UPPER + `letterSpacing: 0.88` + `chalk.dim`**
and is therefore not a name style at all (rendering "CHRISTIAN MCCAFFREY" tracked
and dim is both a semantic misuse and *wider* than 13pt sentence case). 12pt is
off the scale entirely.

Names that fit in 97.5pt on one line, chip moved to the meta row:

| Name size | Top-100 by dynasty value | All 340 | On the Chalkline scale? |
|---|---|---|---|
| 16pt (`title`, today) | **32 / 100** | 142 / 340 | yes — today's token |
| 14pt (`body` metrics) | 64 / 100 | 241 / 340 | yes |
| **13pt (`body-sm` metrics) — CHOSEN** | **83 / 100** | **286 / 340** | **yes** |
| 12pt | 89 / 100 | 311 / 340 | **no — off-scale** |
| 11pt (floor) | 95 / 100 | 330 / 340 | only as `label`, which is uppercase/tracked/dim |

For reference, **today** (chip on line 1, name at 16pt in ~67pt of residual
width): **1 / 100** of the top-100 fits.

**Chosen: 13pt.** It is the largest on-scale step that clears a large majority
(83% of the top-100, 84% of the whole pool), it more than doubles the 16pt fit
rate, and it keeps 2pt of headroom above the absolute floor. The step from 13 →
12 buys 6 names at the cost of leaving the design system's scale; 12 → 11 buys 6
more at the cost of the floor's entire margin and of inventing a name style. Both
are refused.

### R-11 — The position chip moves to the meta line

`PositionChip position={p.pos} size="sm"` moves out of `compactTopLine`
(`TradeSide.tsx:85-90`) and becomes the **leading** child of `compactMetaLine`
(`:94-119`), before the `"<team> · <age> yrs"` / `"Draft capital"` text. The chip
is **moved, never dropped, resized or restyled** — it stays the Badges-&-chips
construction (`components/PositionChip.tsx:41-48`: transparent fill, 1px border in
the position hex, `radii.xs`, `type.label`) and its colors remain a
`docs/cross-client-invariants.md` data encoding. `size` stays `"sm"`.

`compactTopLine` collapses: line 1 becomes a plain `<Text>` holding the name
alone. Keep the `styles.compactTopLine` wrapper **only if** it still carries
layout; if it becomes a single-child `View` with no remaining purpose, delete the
style with it.

The non-compact branch (`TradeSide.tsx:79-83` fixed 44pt `chipCol`, `:92` plain
`<Text style={type.title}>`, `:139-147` trailing tier slot) is **byte-identical**.
The 44pt `chipCol` ↔ `PlayerPickerModal.chipCol` lockstep
(`mobile/tests/check-picker-chip-alignment.js`) is untouched.

### R-12 — The compact name renders at 13pt

`styles.compactName` (`TradeSide.tsx:210`) gains the size override, sourced from
tokens rather than magic numbers, and applied **after** `type.title` so the name
keeps Archivo 600 and `chalk.base`:

```ts
// #411 — one step down the Chalkline scale (16/22 → 13/18) so the compact
// name clears the 97.5pt info column on far more rows. Weight and color stay
// `type.title`'s: the name is still the row's primary identifier, just
// smaller. Sizes come from `type.bodySm`, never a literal — the 11pt floor
// (docs/design/design-system.md) is 2pt below this and is not approached.
compactName: {
  fontSize: type.bodySm.fontSize,
  lineHeight: type.bodySm.lineHeight,
  flexShrink: 1,
},
```

The mount stays `style={[type.title, styles.compactName]}` with
`numberOfLines={1}` (R-14). The `title` token's Dynamic-Type cap tier
(`typeMaxFontScale.title = 'body'`, ×2.0 —
`mobile/src/theme/chalkline.ts:175`) is unchanged.

**Row height falls by 4pt per asset row** (line 1: 22 → 18; the meta line stays
20pt, set by the tier badge — see R-13), which relieves rather than worsens the
#384 one-frame constraint.

### R-13 — The meta line gets an explicit shrink policy, and the tier badge goes `sm`

**This requirement exists because the chip move creates a new collision that the
plan did not measure.** Measured contents of the 97.5pt meta line
(same method as §3.2; badge widths include their `paddingHorizontal` and border):

| Element | Width |
|---|---|
| `PositionChip size="sm"` | QB 28.1 · RB 27.4 · WR 30.1 · TE 26.0 · **PICK 39.6** |
| meta text at 13pt Archivo 400 | `"LV · 25 yrs"` 60.2 · `"WAS · 24 yrs"` 74.2 · `"Draft capital"` 69.2 |
| `TierBadge` **md** (today's default) | `4+ 1sts` 63.5 · `1 1st` 47.4 · `FA` 30.3 |
| `TierBadge` **sm** | `4+ 1sts` 59.5 · `1 1st` 43.4 · `FA` 26.3 |

The meta text already ellipsizes hard today (74.2 + 4 + 63.5 = 141.7 against
97.5) — that is what `compactMetaText: { flexShrink: 1 }` (`TradeSide.tsx:211`)
is for. Adding the chip makes the **chip + badge alone** the binding constraint:
WR + md `4+ 1sts` = 30.1 + 4 + 4 + 63.5 = **101.6 > 97.5**. Neither the chip nor
the badge shrinks, the row does not wrap, and `Card` sets `overflow: 'hidden'`
(`chalkline/Card.tsx:47`) — so **the tier badge's right edge would be clipped**.
Losing the price is precisely the failure `compactMetaText`'s existing comment
says it exists to prevent.

**Requirement:**

1. `TierBadge` renders `size="sm"` **in the compact branch only**
   (`TradeSide.tsx:113`). This uses an existing prop; `TierBadge.tsx` is not
   edited, the label map and the tier hex border are untouched, and
   `docs/cross-client-invariants.md` governs those — not the badge's padding.
   The non-compact mount at `:141` keeps the default `md`.
2. `compactMetaText` gains `minWidth: 0` alongside `flexShrink: 1`, so it can
   actually reach zero and is always the element that yields.
3. The chip wrapper and the badge/value slot on the compact meta line get
   `flexShrink: 0` — the two **data encodings** are never the things that
   shrink or clip.

With `sm`, the worst realistic row (WR at `4+ 1sts`) is 30.1 + 8 + 59.5 = **97.6**
against 97.5 — a 0.1pt, sub-pixel overhang. The residual overflow cases are in
[§6](#6-known-limits).

### R-14 — `numberOfLines` stays 1; the stacked page is byte-identical

- The compact name keeps `numberOfLines={1}`. **No wrapping is added anywhere** —
  the operator did not choose it.
- The two `numberOfLines={compact ? 1 : undefined}` clamps (`TradeSide.tsx:61`
  team name, `:101` meta text) are unchanged, count and form.
- Every #411 edit lives inside a `compact ? … : …` branch or a `compact`-only
  style, so the flag-off / stacked-page render is byte-identical. This is what
  `check-calc-merged-layout.js` rule 16 exists to prove and it must stay green.
- The 32pt remove target and its `hitSlop={compact ? 12 : 6}` (`:151`) are
  unchanged. `MemberEnteredMarker` (`:121-128`) is unchanged and still
  unconditional.

---

## 4. Requirements — #412, "More offers" placement

Proceeds as the Planner proposed. The current pager placement was a QA agent's
design compensation built under the standing ship order — the code comment at
`TradesScreen.tsx:7336-7346` labels itself *"#402 QA B-C4 (operator-flagged
design call, built under the ship order)"* — **not** an operator ruling. No
prior ruling is overturned; no decision entry is owed for #412.

### R-15 — A presentational slot on `TradeSide`, under the give column's Add button

New optional prop on `TradeSide`:

```ts
/** #412 — host-supplied content rendered directly beneath "Add player",
 *  inside the same Card. Presentational only: TradeSide reads no flag and
 *  owns no handler. Absent ⇒ byte-identical for the receive column, the
 *  stacked page, FeaturedTradeWindow and the #270 experiment. */
belowAdd?: React.ReactNode;
```

Rendered immediately after the `<View ref={addRef}>` Add-button wrapper
(`TradeSide.tsx:165-168`), inside `styles.inner`'s `gap: space.sm`.

Threaded `TradesScreen` → `TradeBuildCanvas` → `InLeagueCalculator` → the
**give** `TradeSide` mount only (`InLeagueCalculator.tsx:1172-1189`), in the
`hideFormatChips` / `seededPrefill` / `onSidesChange` family. The receive mount
(`:1191-1224`) does not receive it — shop is a give-side verb (canvas-results
rev-3 §1).

Visual construction is carried over unchanged from the pager entry
(`TradesScreen.tsx:9563-9575` `browseMoreOffersBtn`): 1px `ink.line` border,
`radii.sm`, `space.sm` horizontal padding, `type.bodySm` + `fonts.uiSemi` +
`chalk.base`. Bordered chalk, not ice — it sits under a `variant="secondary"`
Button and reads correctly as the quieter sibling.

### R-16 — Handler, gate and analytics are unchanged; the pager copy is removed

- Handler: `openShopForCard(rawTopCard)` (`TradesScreen.tsx:3240`) — one give
  asset navigates, several open the "Shop which player?" chooser. **Unchanged.**
- Gate: `shopEnabled` (`:1538`) `&& browseLive && sortedDeck.length > 0 &&
  rawTopCard.give_players.length > 0`. **Unchanged** — resolution of the
  Planner's Q-2 is **browse-only**; see [reconciliation-log.md](reconciliation-log.md).
- `shop_opened` still fires **exactly once**, inside `openShopWindow`, at the
  navigate site (P-3). No new event, no changed properties, no changed `screen`
  value (`'Trades'`). `check-shop-deck.js` h4a/h4c/h4d/h5a/h5b stay green
  untouched.
- Argument: **`rawTopCard`** — the engine's original give side, not the edited
  canvas. Resolution of the Planner's Q-3; rationale and its accepted cost in
  [reconciliation-log.md](reconciliation-log.md) and [§6](#6-known-limits). The
  build adds a code comment at the slot's construction site mirroring
  `handleBrowsePass`'s original-vs-edited note (`TradesScreen.tsx:5744-5749`).
- The pager entry (`TradesScreen.tsx:7336-7368`) and its `browseMoreOffers*`
  styles are **removed**. One entry, one placement.
- The deck's own give-side chip (`TradeCard.tsx:444-464`,
  `testID="trade-card.keep-give"`) is **not touched** — it remains the flag-off
  entry, and `handleKeepSide` still routes through the same
  `openShopForCard` fork.
- `testID`: the entry keeps a static literal. Rename
  `trades.canvas-results.more-offers` → `calc.give.more-offers` (it no longer
  lives on the canvas-results pager and the id should not lie about its home),
  and register the rename with `mobile/scripts/testid-lint.sh`.

---

## 5. Requirement — #409 refusal copy

### R-17 — `not_league_member` stops naming the partner

`mobile/src/utils/queueCalcTrade.ts:43-44` currently renders the server's
`not_league_member` refusal as:

```ts
case 'not_league_member':
  return `@${name} isn't in this league.`;
```

That one server reason covers **three** causes and two of them are **caller-side**
(`backend/server.py:13139-13143`: *"caller is not a member of this league"*,
*"opponent is not a member of this league"*, *"cannot queue a trade with
yourself"*). The dominant one in production was the caller — which is why the
operator reported "a user isn't in this league" while the server was complaining
about the caller. The backend fix shipped in `11c8903c`; the string is still
capable of falsely blaming the partner and must stop.

**Replace with, exactly:**

```ts
case 'not_league_member':
  return "Couldn't queue that — one side isn't showing as a league member.";
```

- Client-only. **No `CalcQueueReason` enum split, no server contract change** —
  that is a cross-client change and is out of scope (§11).
- The file's header comment (`queueCalcTrade.ts:28-31`) currently states *"Every
  line names whose preference refused it and why"*. That principle now has one
  deliberate exception; the build **must** amend the comment to say so, e.g.:
  *"…with one exception: `not_league_member` is a single server reason covering
  three causes, two of them caller-side (backend/server.py:13139-13143), so the
  client cannot honestly name a side and deliberately does not (FB-409)."*
- `name` stays a parameter — every other branch still uses it. No signature change.
- No test currently asserts this string (verified by
  `git grep -n "isn't in this league" -- mobile`); a new one is added (§7.3).

---

## 6. Known limits

Stated rather than discovered. The operator asked for a pressure test; this is
the answer, including the parts that are not good news.

### 6.1 #411 — which of the operator's five names still ellipsize

Budget 97.5pt. Measured widths in points (method: §3.2).

| Name | chars | today (16pt, chip on line 1, ~67pt) | **13pt, chip moved (SHIPPING)** | 11pt (the absolute floor, not shipped) |
|---|---|---|---|---|
| Ja'Marr Chase | 13 | 106.8 — **truncates** | 86.8 — **fits** | 73.4 — fits |
| Bijan Robinson | 14 | 112.2 — **truncates** | 91.2 — **fits** | 77.2 — fits |
| Christian McCaffrey | 19 | 145.6 — **truncates** | 118.3 — **STILL TRUNCATES** | 100.1 — still truncates |
| Amon-Ra St. Brown | 17 | 144.8 — **truncates** | 117.6 — **STILL TRUNCATES** | 99.5 — still truncates |
| Marvin Harrison Jr. | 19 | 140.2 — **truncates** | 113.9 — **STILL TRUNCATES** | 96.4 — fits |

**Plainly: 2 of the operator's 5 pressure-test names are fixed. 3 of 5 still
ellipsize. That is fewer than half.**

Two further facts the operator should have:

- **"Christian McCaffrey" and "Amon-Ra St. Brown" cannot be made to fit on one
  line at any legal size.** At the 11pt Chalkline floor they still measure 100.1pt
  and 99.5pt against 97.5pt available. Single-line + 97.5pt + the type floor is an
  infeasible combination for names of that length. Fitting them would require
  wrapping (which the operator declined) or breaking the floor (which the design
  system forbids).
- **The fix is nonetheless large in aggregate.** Across the top 100 dynasty assets
  it moves fit-on-one-line from **1 / 100 today to 83 / 100**; across the full
  340-player pool, to 286 / 340. The five names the operator picked are, by
  construction, the long tail — they are the hardest five, not a random sample.

### 6.2 #411 — residual meta-line overflow

After R-13 (`TierBadge size="sm"`) the chip + badge pair still exceeds the 97.5pt
meta line in these combinations, where the badge's right edge is clipped by
`Card`'s `overflow: 'hidden'`:

| Row | chip + 2 gaps + sm badge | Overflow | Plausibility |
|---|---|---|---|
| WR at `4+ 1sts` | 30.1 + 8 + 59.5 = 97.6 | **0.1pt** | common — sub-pixel, not visible |
| PICK at `2 1sts` / `3 1sts` | 39.6 + 8 + 51.6 = 99.2 | 1.7pt | implausible — a single pick does not price at two firsts |
| PICK at `4+ 1sts` | 39.6 + 8 + 59.5 = 107.1 | 9.6pt | implausible, same reason |

Accepted. The realistic worst case is 0.1pt. The TestFlight checklist has an
explicit step (§9 step 11) to look at a top-tier player row and an early first,
because this is the one prediction here that a device could falsify.

### 6.3 #411 — Dynamic Type

`type.title` caps at the `body` tier, ×2.0 (`mobile/src/theme/chalkline.ts:175`),
and R-12 does not change that. At 200% text scaling a 13pt name renders at 26pt
and holds roughly 5–6 characters in 97.5pt — truncation returns for almost every
name. **The structural guards must therefore assert the structural change, never
"names do not truncate".**

### 6.4 #412 — the entry shops the original, not the edited give side

Under the give column the control *looks* like it shops what the column shows; it
shops `rawTopCard` (R-16). If the user removes the engine's give asset and adds
another, the entry's accessibility label still names the **original** player and
the shop window still searches for it. Accepted for consistency with the pass
signal (`TradesScreen.tsx:5744-5749`) and because changing it would make this a
behavior change rather than a move. Recorded here and in a code comment.

### 6.5 #410 — one cell, two meanings

The middle cell means "clear the canvas" in one state and "decline this idea" in
another, and the operator chose a bare glyph over a word knowing D-157's history.
Two things blunt it: the glyph itself changes (word → ✕) so the cell never looks
the same while meaning something different, and the decline opens a **confirmable,
dismissible reason overlay** — an accidental tap is recoverable by backing out,
unlike today's silent whole-canvas wipe (R-6). Checklist steps 2 and 5 test both
readings. **If a tester misreads it, that is D-169 material, not a bug** — the
decision entry records the reasoning so a reversal has something to reverse.

---

## 7. Test plan (D-056)

Maestro and the simulator are retired ([D-056](../../../../living-memory/DECISIONS.md)).
No flows, no `screens/` captures, no `qa/sim-runs` marker; `FTF_SKIP_SIM_GATE=1`
is the standing posture for `githooks/pre-push`.

**Baseline, measured 2026-08-30 on `11c8903c`:** `check-canvas-results`,
`check-calc-merged-layout`, `check-calc-merged-behavior`, `check-shop-deck` and
`check-any-partner` all pass. `check-any-partner.js` (A-1…A-15) must **stay green
with zero edits** — it is FB-406/FB-407 code from hours earlier, and A-10's
whitespace-normalized predicate pin and A-11b's textual-identity pin will fail on
a reformat of `InLeagueCalculator.tsx:1355-1362` or `:364/:370`. Run it explicitly.

**No new suite file.** Three existing suites are extended, which keeps CI's
`tests/check-*.js` glob and the `npm run` script list unchanged.

### 7.1 Corrections to the plan's re-spec list

The plan named seven assertions as becoming false. Re-verified against the tree,
**four** do; two survive unchanged and one is an addition rather than a re-spec.
Building to the plan's list unchanged would produce edits to green assertions.

| Plan's claim | Verified verdict |
|---|---|
| `check-canvas-results.js` §3 (`:169-175`) becomes false | **TRUE.** The id loop asserts `trades.canvas-results.pass` exists; R-4 deletes it. Re-spec. |
| `check-canvas-results.js` `:269` (rule `4l`) becomes false | **PARTLY.** The assertion is `!/canvas-results/.test(calcCode)` at `:270-271` and stays **green** under R-5 (the prop is `browseDecline`). Its **message** — *"the pass control lives with the pager"* — becomes false. Re-spec the message, keep the assertion, add the prop-shape assertion beside it. |
| `check-canvas-results.js` 12i (`:584-585`) becomes false | **TRUE.** Re-spec. |
| `check-canvas-results.js` 12i2 (`:587-591`) becomes false | **TRUE.** Re-spec. |
| `check-calc-merged-layout.js` rule 16 (`:261-270`) becomes false | **FALSE — it stays green.** It asserts exactly one bare `numberOfLines={1}` preceded by `styles.compactName`; R-12/R-14 keep both facts. **Extend** it, do not invert it. |
| `check-calc-merged-layout.js` rule 16b (`:271-272`) becomes false | **FALSE — it stays green.** The two `numberOfLines={compact ? 1 : undefined}` clamps are the team name and the meta text; neither is touched. Leave it alone. |
| `check-calc-merged-layout.js` rule 17 (`:273-275`) becomes false | **TRUE**, because R-13 adds `minWidth: 0` to `compactMetaText`. Re-spec. |
| `check-calc-merged-behavior.js` needs a re-spec | **NO — nothing there covers the action row's middle cell** (only `calc.action.confirm` at `:387`). These are **additions**. |
| `check-shop-deck.js` needs a re-spec | **NO.** It carries no `canvas-results` assertion (its two mentions at `:241`/`:245` are comments). It stays green **untouched**, which is itself the evidence that the deck chip did not move. |
| `check-canvas-results.js` 12i5 (`:601`) | **Stays green.** `count(/openShopForCard\(/g) === 3` holds: R-15 keeps the call in `TradesScreen`, inside the slot it hands down. |

### 7.2 Re-specs — what each assertion becomes, and why

**Never a deletion.** Every rule below keeps a rule in its place.

| Rule | Today | Becomes | Why |
|---|---|---|---|
| `check-canvas-results.js` **§3 id loop** (`:169-175`) | asserts `trades.canvas-results.pass` **exists** in `TradesScreen.tsx` | asserts it is **absent**, and that the pager's `pager` / `prev` / `next` ids still exist | R-4 moves the control; the pager itself is unchanged. The inversion is the *point*, and pinning the absence stops the old ✕ being re-added beside the new one. |
| `check-canvas-results.js` **§4 `4l`** (`:270-271`) | `!/canvas-results/.test(calcCode)`, messaged *"the pass control lives with the pager — the action row's 50/30/20 is untouched (D-157)"* | **same assertion**, re-messaged: *"InLeagueCalculator reads no canvas-results flag — the decline cell arrives as a PROP (D-169 amends the placement clause; the 50/30/20 is still untouched)"*, plus a new sibling asserting `browseDecline?:` is declared **optional** in `InLeagueCalculator.tsx` and `TradeBuildCanvas.tsx` | The one-flag-read rule survives verbatim; only the sentence it advertises was overturned. |
| `check-canvas-results.js` **12i** (`:584-585`) | `trades.canvas-results.more-offers` exists | the id is **gone** from `TradesScreen.tsx`, and `calc.give.more-offers` exists exactly once | R-15/R-16. |
| `check-canvas-results.js` **12i2** (`:587-591`) | the entry sits inside the pager block, before `<TradeBuildCanvas` | the entry sits **after** `<TradeBuildCanvas`'s open tag (it is a prop on it) and is **still gated** on `browseLive && sortedDeck.length > 0` and a non-empty `rawTopCard.give_players` | preserves the rule's real content — *absent with no session* — under the new home. |
| `check-calc-merged-layout.js` **17** (`:273-275`) | `/compactMetaText: \{ flexShrink: 1 \}/` | `/compactMetaText: \{[^}]*flexShrink: 1[^}]*minWidth: 0/` **plus** a new sibling asserting the compact chip wrapper and badge slot carry `flexShrink: 0` | R-13 makes the text the only element that yields; the *price* must never be the thing that shrinks. |

### 7.3 New assertions, each with its named sabotage

A sabotage is a **plausible wrong implementation**, not the textual negation of
the assertion's own regex. Self-satisfying mappings were re-audited before this
list was finalized; three candidates were rewritten and are noted.

| # | Assertion | Named sabotage (must go RED) |
|---|---|---|
| **T-1** | The middle cell has **two** branches; the decline branch mounts `calc.action.decline` and its `onPress` resolves to the **host prop's** handler (`browseDecline.onPress`) — no locally-defined pass function, no `track(` call, no other prop invoked inside that branch | **S-1 "local pass path":** rather than thread a prop, the builder defines a `passIdea()` inside `InLeagueCalculator` that emits its own analytics and calls back through an existing prop. Every id, glyph and flex is correct; the app now has two pass implementations and one of them writes events the taxonomy never classified. Also catches **S-1b "disabled instead of replaced"** (keep Clear, render it `disabled` during browse) — there is then no decline branch at all. |
| **T-2** | `clear` is referenced by **exactly one** JSX `onPress` in `InLeagueCalculator.tsx`, and that reference sits inside the `browseDecline ? … : …` **alternate** (asserted by AST identifier reference within the branch node, not by a text search) | **S-2 "helpful cleanup":** the decline branch calls `browseDecline.onPress()` **and then** `clear()` — the natural "tidy the canvas after passing" instinct. Reinstates the R-6 edit-map corruption verbatim while T-1, T-3, T-4 and every glyph/flex check still pass. This is the single most likely way R-6 gets un-fixed. |
| **T-3** | The middle cell is **two separate `Pressable`s** in the two branches, each carrying its own static string literal in `testID=` position — not one shared `Pressable` whose id, label, child and handler are all conditional | **S-3 "one cell, one Pressable":** collapse to a single `Pressable` with `testID={browseDecline ? 'calc.action.decline' : 'calc.action.clear'}` and conditional `onPress`/`disabled`/child. Genuinely tempting (it looks like less duplication), and it is the shape that produces S-1b and S-4 for free; it also breaks `testid-lint`'s static-literal contract and makes `calc.action.clear` ambiguous in the retained flows. |
| **T-4** | The decline branch's `disabled` prop is absent/false; `disabled={!anySide}` appears only on the Clear branch | **S-4 "shared disabled":** hoist `disabled={!anySide}` to the shared `Pressable`. Silently makes decline dead on an emptied canvas mid-session — the exact state R-6 leaves reachable via per-row removes. |
| **T-5** | `TradesScreen` passes `browseDecline` as `null`/undefined when `declineReasonProps` is falsy — the prop expression names `declineReasonProps` | **S-5 "kill-switch blindness":** gate `browseDecline` on `browseLive && sortedDeck.length > 0` only. Under `feedback.decline_reasons` off, the ✕ renders and `handleBrowsePass` early-returns at `:5752` — a dead control (R-7). |
| **T-6** | `handleBrowsePass` has exactly **one** caller in `TradesScreen.tsx` | **S-6 "belt and braces":** leave the pager ✕ in place beside the new cell. Two decline controls, and the ✕ the report asked to *replace* is still there. |
| **T-7** | `browseDecline` is declared optional (`browseDecline?:`) in both `InLeagueCalculator.tsx` and `TradeBuildCanvas.tsx`, and appears at **neither** `FeaturedTradeWindow.tsx:82` nor `TradeCalculatorScreen.tsx:751` | **S-7 "required prop":** declare it non-optional and default it in the destructure. `tsc` then forces the two other hosts to pass something, breaking byte-identity for the pushed page and the featured window. |
| **T-8** | `haptics.warning()` occurs at most once on any path from the middle cell — asserted as: the Clear branch's `onPress` body contains no `haptics.` call, since `clear()` owns it | **S-8 "leave the double":** keep `haptics.warning()` in the `onPress` *and* in `clear()`. R-8's target; a builder editing only the branch structure preserves it by default. |
| **T-9** | In `TradeSide.tsx`, `PositionChip` appears exactly twice — once in the non-compact `chipCol` and once inside `compactMetaLine`; **zero** occurrences inside `compactTopLine` / line 1 of the compact branch | **S-9 "belt-and-braces chip":** render the chip on both lines in compact mode (a natural "don't lose it" hedge). Line 1 is back to its 67pt budget and the whole of #411 is undone while every other assertion passes. |
| **T-10** | `compactName` sets `fontSize`/`lineHeight` from `type.bodySm.*` **member expressions**, not numeric literals, and no numeric literal `< 11` appears in `TradeSide.tsx`'s styles | **S-10 "just squeeze it":** `fontSize: 10`. Fits four more names and breaks the design-system floor. (Rewritten from an earlier draft that grepped for `13` — that version was self-satisfying: it would have passed on a hardcoded `13` too.) |
| **T-11** | `TierBadge` is rendered with `size="sm"` on the compact branch and **without** a `size` prop on the non-compact branch | **S-11 "global sm":** pass `size="sm"` at both mounts. The stacked page's badge shrinks — a flag-off visual change, exactly what rule 16's byte-identity charter forbids. |
| **T-12** | `TradeSide`'s `belowAdd` renders **after** the `<View ref={addRef}>` Add wrapper and **inside** the `Card`; `TradeSide.tsx` contains no `useFlag` / `features` import | **S-12 "slot above Add":** render `belowAdd` before the Add button. Reads as a second Add affordance and inverts the report's own words ("underneath the add a player button"). |
| **T-13** | `belowAdd` is passed at the **give** mount only — `InLeagueCalculator.tsx` contains exactly one `belowAdd=` and it is inside the `const give = (` region, before `const receive = (` | **S-13 "symmetric slot":** pass it to both columns. Produces a meaningless receive-side "More offers" (shop is a give-side verb) and double-mounts the entry. |
| **T-14** | `queueCalcTrade.ts`'s `not_league_member` branch contains **no** `${name}` interpolation and no `@` character | **S-14 "softened blame":** `` `@${name} may not be in this league.` `` — hedged wording that still names the partner for a caller-side cause. Catches the near-miss, which a "string changed" assertion would not. |
| **T-15** | The `queueCalcTrade.ts` header comment names FB-409 and the caller-side cause (a comment assertion, deliberately: the carve-out is the thing a future editor would otherwise "fix" back) | **S-15 "silent exception":** change the string, leave the comment claiming every line names whose preference refused it. The next editor reads the contract, sees `not_league_member` violating it, and restores `@name`. **Acknowledged as the weakest of the 15** — a documentation pin's sabotage is necessarily close to its own negation. It is kept because the failure it prevents (regression by a well-meaning future editor) is the one that actually happened to the *original* string's intent. |

### 7.4 Full gate

- `node mobile/tests/check-canvas-results.js` · `check-calc-merged-layout.js` ·
  `check-calc-merged-behavior.js` — extended, all green.
- `node mobile/tests/check-shop-deck.js` · `check-any-partner.js` ·
  `check-picker-chip-alignment.js` · `check-inline-home.js` ·
  `check-calc-tour.js` — green, **unedited**.
- `npx tsc --noEmit` (strict) in `mobile/`.
- `bash mobile/scripts/testid-lint.sh` — with `calc.action.decline` and the
  `calc.give.more-offers` rename registered.
- `pytest backend/tests` — untouched-proof; no backend file is in this change's
  footprint. (The FB-409 server fix already on the branch carries its own
  `backend/tests/test_calc_trade_queue.py` coverage.)
- Every sabotage in §7.3 run and proven RED **before** the corresponding
  assertion is accepted (the 2026-08-10 lesson).
- Evidence logged in `living-memory/TEST_LEDGER.md` per D-056.

---

## 8. Code-walk proof outline

Written to `docs/feedback/items/410-found-trade-decline-position/code-walk.md`
in the `406`/`407` house style — every step file:line-cited against the
post-change tree.

1. **The three action-row states** (empty canvas / hand-built canvas / live
   browse), traced through the new middle-cell branch including each branch's
   `disabled` predicate, `testID`, glyph-or-word, `accessibilityLabel` and
   haptic. Prove state A and state B are textually the pre-change Clear cell.
2. **The decline branch reaches the identical overlay path the pager ✕ reached**:
   `browseDecline.onPress` → `handleBrowsePass` (`TradesScreen.tsx:5750`) →
   `setBrowseReasonOpen(true)` + `handleReasonOverlayOpened` →
   `commitReasonAdvance` → idea splice. No new writes, no new events, and
   `dismissBrowseReasonOverlay`'s banked/unbanked contract untouched.
3. **R-6, the data-loss closure**: show `clear()` (`InLeagueCalculator.tsx:843`)
   and `track('calc_cleared')` (`:845`) are unreachable from the action row while
   `browseDecline` is non-null, therefore the `onSidesChange` effect (`:386-392`)
   cannot fire with `([], [])` from this control, therefore
   `handleBrowseSidesChange` (`TradesScreen.tsx:5732`) cannot write
   `{give: [], receive: []}` into `browseSession.edits[browseSeededIdRef.current]`,
   therefore the seeding effect (pinned by `check-canvas-results.js` 5f) still
   replays the engine's original on a page-back.
4. **R-7, kill-switch parity**: `declineReasonProps` (`TradesScreen.tsx:5541`)
   falsy ⇒ `browseDecline` null ⇒ the Clear cell, matching today's
   "no control at all" behavior.
5. **#411 is inside the `compact` branch only**: walk `TradeSide.tsx`'s compact
   and non-compact arms side by side and show the non-compact arm is unchanged
   line-for-line, so the flag-off stacked page is byte-identical.
6. **#412's slot is `undefined` at all four pre-existing mounts**:
   `FeaturedTradeWindow.tsx:82`, `TradeCalculatorScreen.tsx:751`,
   `InLeagueCalculator.tsx:1191` (receive), and `TradeBuildCanvas.tsx:173` when
   its host does not supply one.
7. **`shop_opened` still has one emitter**: cite `openShopWindow` and confirm the
   slot's `onPress` reaches `openShopForCard` without emitting.

---

## 9. Operator TestFlight checklist

Written to
`docs/feedback/items/410-found-trade-decline-position/testflight-checklist.md`.
**This is the only runtime evidence this change gets.** Screen · steps ·
expected. Covers all four fixes including #409's ✓ success, since the server fix
`11c8903c` ships in the same build.

| # | Screen | Steps | Expected |
|---|---|---|---|
| 1 | TradesHome (guided) | Open with an empty canvas | Action row: `Find a Trade` · **Clear, greyed** · ✓ greyed. **No pager. No ✕ anywhere on the page.** |
| 2 | TradesHome | Add one player to each side by hand (no Find a Trade) | Middle cell still reads **Clear** and is live. Tap it → both columns empty, one haptic, no pager appears. **This is the D-157 control and it must still work.** |
| 3 | TradesHome | With a give side on the canvas, tap **Find a Trade** (fair path) | Pager appears: `‹ 1 / N ›`. Anchor receipt above shows `Built around … · Change · Clear`. Middle cell is now a **✕**. **There is no ✕ in the pager row.** |
| 4 | TradesHome | Look at the pager row | `‹ N / X ›` and (model path only) `Clear`. **No "More offers" here** — it moved (step 13). |
| 5 | TradesHome | Tap the middle-cell **✕** | The two-layer decline-reason overlay opens, identical to the deck's. Pick a layer-1 tile, then a layer-2 option → the idea leaves the set, `X` decrements by one, the next idea seeds the canvas. |
| 6 | TradesHome | Tap ✕, then dismiss the overlay **without answering** (backdrop / swipe down) | The idea **stays**, `X` unchanged, canvas unchanged. |
| 7 | TradesHome | Tap ✕, bank a layer-1 tile, then dismiss without reaching layer 2 | The pass **stands**: idea leaves the set, `X` decrements. (Matches the deck exactly.) |
| 8 | TradesHome | **R-6 regression, the important one.** On idea 2 of N, edit the canvas (remove a player), page to idea 3 with `›`, then page back with `‹` | Idea 2 comes back **with your edit** — not blank, and not the engine's original. Then page forward and back again: still the edited version. **Nothing on this screen should ever leave you looking at an empty canvas with a live `2 / N` above it.** |
| 9 | TradesHome | With an idea fronted, tap **✓** | Queues. Toast confirms. Session stays on the idea, pager unchanged. **This is #409** — it must succeed, not say "isn't in this league". |
| 10 | TradesHome | Tap the receipt's **Clear** (fair) or the pager's **Clear** (model) | Session ends, canvas blank, pager gone, middle cell back to a greyed **Clear**. |
| 11 | TradesHome | **#411.** Load an idea containing a long name (Christian McCaffrey / Amon-Ra St. Brown / Marvin Harrison Jr.) **and** a draft pick, in both columns | Position tag is on the **second** row, left of team/age. Tier badge still **fully visible** at the right — check the pick row and the highest-tier player row especially. Name is on line 1 alone, one line, smaller than before. **Report every name still showing "…"** — §6.1 predicts those three do and Ja'Marr Chase / Bijan Robinson do not. |
| 12 | TradesHome | **#411 Dynamic Type.** Settings → Display & Brightness → Text Size, near max; reopen | Names may ellipsize again — expected (§6.3). Confirm nothing **overlaps**, the tier badge is not covered, and the row's remove ✕ is still tappable. |
| 13 | TradesHome | **#412.** While browsing an idea, look at the **give** column | **"More offers" sits directly under that column's "Add player" button**, inside the same card. Nothing similar under the receive column. |
| 14 | TradesHome | Tap **More offers** with exactly one give asset | The shop window opens directly on that player. Press Back → the browse session is **intact**: same idea, same `N / X`, same canvas edits. |
| 15 | TradesHome | Tap **More offers** with several give assets | The "Shop which player?" chooser opens; picking one navigates. Back returns to the session intact. |
| 16 | TradesHome | Clear the session (step 10), then look at the give column | **No "More offers" anywhere on the page.** |
| 17 | Trades (deck) | Switch to Team or Player mode, where the deck still renders | The deck card's own give-side "More offers" chip is **unchanged**, and the card's own ✕/✓ are unchanged. |
| 18 | Trade Calculator (pushed, "Calc") | Open the pushed Real-values page | Action row reads `Find a Trade` · **Clear** · ✓. **No ✕, no "More offers", no compact two-line rows** — this page is unchanged. |

---

## 10. Success criteria

Verifiable, and honest about what is not achieved.

1. **#410 placement.** During a live browse session with the decline machinery
   mounted, the decline control is the action row's middle cell and there is
   **exactly one** decline control on the page. In every other state the middle
   cell is Clear, byte-identical. (T-1, T-2, T-6; checklist 1–5.)
2. **#410 data loss.** The action row cannot write `{give: [], receive: []}` into
   a browsed idea's edit map. Paging away from an edited idea and back restores
   the **edit**; paging away from an untouched idea and back restores the
   **engine's original**. (T-1/S-1, T-2; checklist 8; code-walk step 3.)
3. **#410 proportions.** `actionFind`/`actionClear`/`actionSmall` are 50/30/20,
   unchanged, and the ✓ cell diff is empty.
4. **#410 ledger.** D-169 exists, is indexed, and the canvas-results-spec §4
   clause is amended — both in the same commit as the code. (R-9.)
5. **#411 structure.** The position chip renders on the compact meta line and
   nowhere on compact line 1; the compact name is `type.bodySm`-sized Archivo 600
   at `chalk.base`; `numberOfLines` is still 1; the stacked page is
   byte-identical. (T-9, T-10, T-11; rules 16/16b stay green; checklist 11, 18.)
6. **#411 outcome — stated as measured, not as "fixed".** On a 375pt device at
   default text size, one-line fit across the top 100 dynasty assets goes from
   **1/100 to 83/100**. **Of the operator's five pressure-test names, 2 of 5 fit
   (Ja'Marr Chase, Bijan Robinson) and 3 of 5 still ellipsize (Christian
   McCaffrey, Amon-Ra St. Brown, Marvin Harrison Jr.) — fewer than half.** Two of
   those three cannot fit on one line at any size at or above the 11pt Chalkline
   floor. This criterion is met by the numbers above being true on device, not by
   the names fitting. (Checklist 11 is the falsification test.)
7. **#411 price never clips.** The tier badge is fully visible on every row a
   tester can produce at default text size. (T-11, re-specced rule 17; checklist
   11.)
8. **#412 placement.** The shop entry renders inside the give column under "Add
   player" and nowhere else on this host; the pager copy is gone; the deck chip
   is untouched. (T-12, T-13, re-specced 12i/12i2; checklist 13–17.)
9. **#412 invariance.** `openShopForCard`, the browse gate and `shop_opened`
   (one emitter, `screen: 'Trades'`) are unchanged — `check-shop-deck.js` passes
   with **zero edits**.
10. **#409 copy.** No refusal line attributes `not_league_member` to the partner;
    the ✓ queue succeeds on device. (T-14, T-15; checklist 9.)
11. **No collateral.** `check-any-partner.js` passes **unedited**; `tsc --noEmit`
    clean; `testid-lint` clean; `pytest backend/tests` unchanged.

---

## 11. Out of scope

- **Splitting `CalcQueueReason`.** The server's three causes behind
  `not_league_member` stay one wire reason. Splitting it is a cross-client
  contract change (`backend/server.py:13060`, `13139-13143` + every client) and
  needs its own scope block.
- **Any backend change.** `backend/` is not in this change's footprint.
- **Wrapping the compact name.** Explicitly declined by the operator.
- **Restyling, resizing or dropping `PositionChip`**, and any change to
  `TierBadge.tsx` itself (only the `size` prop's *value at one call site* moves).
- **Re-targeting tour beat n19** or any other Wave-B tour work (R-10).
- **Restoring the deck under a browse session** — that reverses
  canvas-results-spec ruling 1, a live operator ruling.
- **Extending the shop entry to hand-built give sides** (Planner Q-2, resolved
  browse-only).
- **Shopping the edited give side** (Planner Q-3, resolved `rawTopCard`).
- **Widening the columns / reducing the page gutter.** Chalkline's page gutter is
  shared by every block on `TradesHome`; ≤16pt total win.
- **Abbreviating names** ("C. McCaffrey"). The calculator is where a user
  confirms *which* asset they are trading.
- **`docs/feedback/items/409-like-not-league-member/`** — that item's docs belong
  to the FB-409 owner and are not edited here.

---

## 12. Guardrails

1. **Fresh code underneath.** FB-406/FB-407 landed in this exact region hours
   earlier. Do **not** reformat `InLeagueCalculator.tsx:1355-1362` (the
   `calc.search-scope-note` predicate — A-10 pins it whitespace-normalized) or
   `:364`/`:370` (the `opponentChosenRef` / `partnerChosen` pair — A-11b pins
   their initializers as textually identical). Run `check-any-partner.js`
   explicitly and expect zero edits to it.
2. **`InLeagueCalculator` reads no flag.** Both new props are optional host props.
   A `useFlag('calc.canvas_results')` inside the component breaks the two-host
   contract and `4l`.
3. **Absent ⇒ byte-identical.** Every new prop defaults to today's behavior, and
   is asserted absent at `FeaturedTradeWindow.tsx:82`,
   `TradeCalculatorScreen.tsx:751` and the receive-side `TradeSide` mount.
4. **Two testIDs, two verbs.** `calc.action.clear` survives verbatim on the Clear
   branch; the decline branch gets `calc.action.decline`. Static literals only.
5. **Data encodings are not design choices.** Position hexes and tier
   labels/colors are `docs/cross-client-invariants.md`. They may be **moved**
   (R-11) and their padding preset may change (R-13, `size="sm"`), never their
   colors, labels or presence.
6. **The 11pt floor is absolute** (`docs/design/design-system.md:107`). 13pt is
   the shipping size and no literal below 11 may appear in `TradeSide.tsx`.
7. **No new analytics.** `calc_cleared` simply stops firing in one state — a
   reduction in emission, not a taxonomy change. Nothing is registered in
   `backend/analytics_taxonomy.py` or `analytics_queries.NON_INTENT_EVENTS`.
8. **Re-spec, never delete.** No assertion in any `check-*.js` is removed. Every
   rule this change falsifies is replaced by a rule that pins the new truth.
9. **Sabotages are plausible wrong builds**, not regex negations. §7.3 was
   re-audited for self-satisfaction; T-10's earlier draft is documented there as
   the example of what was rejected.
10. **Ledger before delete.** No branch or worktree is removed without a
    `docs/recovery/` entry per `docs/recovery/CLAUDE.md`.

---

## 13. The D-169 entry, verbatim

Insert into `living-memory/DECISIONS.md` adjacent to `D-168`
(`living-memory/DECISIONS.md:1043`), and add the matching row to the **Decision
index** table at `:438`. Text to add, exactly:

```markdown
## D-169 — The Merged Canvas Action Row's Middle Cell Becomes a Bare ✕ During a Browse Session; D-157's Misread Is Resolved by Making the Control Mean What Users Already Read It As

**Date:** 2026-08-30 (operator ruling, verbatim: *"It does mean pass / Keep the x button."*) · **Amends:** [D-157](DECISIONS.md) and `docs/feedback/items/402-more-offers-shop/canvas-results-spec.md` §4 · **Trigger:** feedback #410 · **Spec:** [docs/feedback/items/410-found-trade-decline-position/prd.md](../docs/feedback/items/410-found-trade-decline-position/prd.md)

**Context:** [D-157](DECISIONS.md) (2026-08-23) replaced a bare ✕ in this exact cell with the word "Clear" after tester Segrave (build 128) read the glyph as the deck's pass control and silently wiped the canvas he had just built. The #402 canvas-results operator session then wrote the placement into the spec as a contract clause: *"A ✕ control on the browsed idea (placement: with the pager, never inside the action row's 50/30/20 cells — that row's proportions are D-157 and unchanged)."* Feedback #410 asks for precisely the placement that clause forbids and precisely the glyph D-157 removed. The operator was shown both artifacts and ruled for the report.

**Decision:** During a live `calc.canvas_results` browse session with an idea fronted and the decline-reason machinery mounted, the merged calculator's action-row middle cell is the **decline control, rendered as a bare ✕** (`semantic.neg`, 16pt, `testID` `calc.action.decline`, `accessibilityLabel` "Pass on this trade idea"). In every other state — empty canvas, hand-built canvas, flag off, the pushed Real-values page, `FeaturedTradeWindow`, the #270 experiment, and under the `feedback.decline_reasons` kill switch — the cell remains the labeled **Clear** of D-157, byte-identical (`testID` `calc.action.clear`). The pager's ✕ is removed: exactly one decline control is ever mounted. The 50/30/20 proportions and the ✓ cell are untouched.

**Why this is not a straight reversal of D-157.** Segrave's misread was that the ✕ *meant pass when it actually cleared the canvas*. This decision makes the cell **mean pass** — it resolves the misread by making the control do what users already believed it did, rather than by teaching them it does something else. The operator's words are the ruling on that point: *"It does mean pass."* Two further facts made the ✕ safe here in a way it was not in D-157's world: the decline opens a **confirmable, dismissible two-layer reason overlay**, so a mistaken tap is backed out of rather than silently destructive; and the Clear it replaces was itself **actively corrupting browse state** — `clear()` emptied the canvas without ending the session and snapshotted `{[],[]}` into the browsed idea's edit map, so paging back restored a wiped idea instead of the engine's original (closed as PRD R-6). D-157's *principle* — do not put an unlabeled control where users will misread it — is honored by the ✕ now carrying the meaning users assign it, and by the accessibility label carrying the verb the glyph does not.

**The narrow reading that preserves the spec clause's rationale.** canvas-results-spec §4's stated reason for keeping the ✕ off the action row was *"that row's proportions are D-157 and unchanged"*. This change does not touch them: it swaps the middle cell's **content**, not its **flex**. Only the placement sentence is overturned; its rationale survives intact and is re-pinned by the structural guard.

**Alternatives considered:** *A word — "Pass" / "Decline" — instead of the glyph* (the plan's own recommendation, on D-157's authority): **rejected by the operator, knowingly, after being shown D-157 and the spec clause.** *Leave the ✕ on the pager and merely disable the action-row Clear during browse*: removes the corruption but not the report — decline stays far from ✓ at a smaller visual weight. *Add a fourth cell (Find / Clear / ✕ / ✓)*: changes the D-157 proportions outright, and the operator's word was "replace", not "add". *Make the action-row Clear end the session during browse*: duplicates `handleBrowseClear`, which the receipt and pager already own.

**Consequences:** The same cell means "clear the canvas" in one state and "decline this idea" in another — accepted, mitigated by the glyph changing with the meaning and by the reason overlay's confirmability. `calc_cleared` stops firing during a browse session (a reduction in emission on one state, not a taxonomy change). D-157's tour beat **n19** was re-checked as D-157 requires: its copy (*"Clear became this cross. It records why you passed"*) now describes the UI more literally than before and is **unchanged**; its `target: 'trades.pass-btn'` is registered only by `TradeCard`, which canvas-results retires on this host, so the spotlight was already dark on this path before #410 — re-targeting it to `calc.action.decline` is Wave-B tour work, deliberately not done here. `docs/feedback/items/402-more-offers-shop/canvas-results-spec.md` §4's first bullet is amended in the same commit. **If a future tester misreads the ✕ the way Segrave misread it, this entry — not D-157 — is what gets revisited.**

**Status:** Active.
```

Decision-index row to add at `living-memory/DECISIONS.md:438`'s table:

```markdown
| D-169 | The Merged Canvas Action Row's Middle Cell Becomes a Bare ✕ During a Browse Session | 2026-08-30 |
```
