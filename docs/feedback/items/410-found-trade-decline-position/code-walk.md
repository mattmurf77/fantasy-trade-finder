# FB-410 / 411 / 412 / 409-copy — Code-walk proof (8 steps, post-change state)

**Date:** 2026-08-30 · **Author:** mobile build agent · **State:** working tree on
`claude/fb-410-412-trade-card-polish` at base `966df00a` + this build (uncommitted —
line numbers cite the built tree the orchestrator is reviewing). Executes the PRD §8
outline; every step is file:line-cited at this state.

Maestro and the simulator are retired ([D-056](../../../../living-memory/DECISIONS.md)).
This document is what a sim capture used to be. Runtime proof is
[testflight-checklist.md](testflight-checklist.md).

Files: `calc` = `mobile/src/components/InLeagueCalculator.tsx` ·
`trades` = `mobile/src/screens/TradesScreen.tsx` ·
`canvas` = `mobile/src/components/TradeBuildCanvas.tsx` ·
`side` = `mobile/src/components/TradeSide.tsx` ·
`queue` = `mobile/src/utils/queueCalcTrade.ts` ·
`calcScreen` = `mobile/src/screens/TradeCalculatorScreen.tsx`.

---

## Step 1 — The three action-row states

The row is `calc:1291` (`testID="calc.action-row"`), three cells whose flex is
`actionFind: {flex: 50}` (`calc:2107`) / `actionClear: {flex: 30}` (`:2108`) /
`actionSmall: {flex: 20}` (`:2109`). **None of those three lines is edited** and the
✓ cell (`calc:1383-1409`) is untouched — the diff for both is empty. That is the whole
narrow reading under which D-169 amends canvas-results-spec §4's placement sentence
while leaving its stated rationale ("that row's proportions are D-157 and unchanged")
literally true.

The middle cell is now a fork on one host prop (`calc:1346`):

| State | `browseDecline` | Cell | testID | disabled | glyph/word | haptic |
|---|---|---|---|---|---|---|
| **A** empty canvas | null | Clear | `calc.action.clear` (`:1362`) | `!anySide` (`:1365`) → **true** | word `Clear` (`:1375`) | `clear()`'s own (`:861`) |
| **B** hand-built, no session | null | Clear | `calc.action.clear` | `!anySide` → false | word `Clear` | `clear()`'s own |
| **C** live browse session | `{onPress}` | Decline | `calc.action.decline` (`:1348`) | **absent** | `<Icon name="x" size={16} color={semantic.neg} />` (`:1357`) | none here — `handleBrowsePass` owns it (`trades:5755`) |

States A and B are **textually the pre-change Clear cell**, with one deletion inside
the change's own footprint: `onPress` was `() => { haptics.warning(); clear(); }` and
is now `onPress={clear}` (`calc:1368`). `clear` already fires `haptics.warning()` at
`calc:861`, so the pre-change form fired it **twice per tap**; R-8 resolves that on the
exact lines R-1 rewrites. Everything else on the branch — the `clearBtnRef` guide
target (`:1361`), the testID, `accessibilityLabel="Clear the trade"` (`:1364`),
`disabled={!anySide}`, the four style entries, the `numberOfLines={1}` label — is
carried over unchanged.

The decline branch takes the Clear cell's **neutral chrome**
(`styles.actionClear, styles.actionBtn` at `calc:1353`, no `styles.actionPrimary`), so
ice stays rationed to `Find a Trade` and the ✓. It carries `accessibilityLabel="Pass on
this trade idea"` (`calc:1350`) — verbatim from the pager ✕ it replaces — because the
glyph does not carry the verb.

**Two Pressables, not one.** `testid-lint` cross-checks literals; a single cell with
`testID={browseDecline ? … : …}` breaks that contract, makes `calc.action.clear`
ambiguous, and is the shape that hands the decline Clear's `disabled={!anySide}` for
free. Both ids are static string literals in `testID=` position.

## Step 2 — The decline branch reaches the identical overlay path the pager ✕ reached

`browseDecline.onPress` (`calc:1351`) is the object the host built at `trades:7412-7416`:
`{ onPress: handleBrowsePass }`. `handleBrowsePass` (`trades:5752`) is **unedited except
for two comments**; its body still runs `if (!rawTopCard) return` → `if
(!declineReasonProps) return` → `haptics.selection()` → `setBrowseReasonOpen(true)`
(`:5764`) → `handleReasonOverlayOpened()`.

From there nothing in the pass path is touched: the host-mounted `DeclineReasonPanel`
(the `4f`–`4k` block of `check-canvas-results.js`), `commitReasonAdvance`'s browse
splice, `dismissBrowseReasonOverlay`'s banked/unbanked contract, and the
`/api/trades/pass-reason` writes are all as shipped. **No new handler, no new endpoint,
no new event.** `check-canvas-results.js` 4b3 pins `handleBrowsePass` at exactly two
occurrences in `trades` — its definition and this one reference — so a second decline
control cannot be added beside it.

The pager ✕ block and its `browsePassBtn` style are **deleted** (`trades:7309-7357` is
now pager chevrons, the `N / X` TickLabel, the spacer and the model-path Clear only).
`§3-bis` of the guard pins `trades.canvas-results.pass` as absent.

## Step 3 — R-6, the data-loss closure

This is the defect, not the cosmetics. Pre-change, during a live session:

1. the action row's Clear called `clear()` (`calc:860-865`), which does
   `setGiveIds([])` + `setReceiveIds([])`;
2. the `onSidesChange` effect (`calc:400-409`) fired with `([], [])` at `:408`;
3. `handleBrowseSidesChange` (`trades:5732`) read `browseSeededIdRef.current` (`:5733`)
   and wrote `{give: [], receive: []}` into `browseSession.edits` under that key;
4. the seeding effect (`trades:5813-5824`, pinned by guard `5f`) replays
   `edited ? edited.give : rawTopCard.give_player_ids` (`:5820`) — so paging away and
   back re-seeded the **emptied** idea. The engine's original was gone.

Post-change, in state C the Clear branch is **not mounted**: `clear` is not referenced
anywhere inside the `browseDecline` consequent. Step 1 therefore cannot start from this
control, so step 2 cannot fire with `([], [])` from it, so step 3 cannot write the
empty snapshot, so step 4 still replays the engine's original.

Two guards hold this, both AST-based rather than textual (`check-canvas-results.js`
`4m2`/`4m2b`): `clear` is **not** referenced inside the fork's `whenTrue` node, and
**is** referenced inside its `whenFalse` node. `4m2c` additionally pins
`onPress={clear}` at exactly two occurrences in the file — the action row's Clear branch
and the stacked-only ghost `Clear trade` button (`calc:1558`, itself gated `merged ?
null : …` and therefore unreachable on any host that can host a browse session).

`track('calc_cleared', …)` (`calc:862`) simply stops firing in state C. That is a
**reduction in emission on one state**, not a taxonomy change: nothing is registered or
reclassified.

Residual, accepted and stated: a user can still empty the canvas mid-session by tapping
each row's remove ✕ (`side:173-186`). That is a deliberate per-asset edit and the edit
map capturing it is #402 §3 working as designed. What R-6 removes is the **single-tap,
whole-canvas, silent** version.

## Step 4 — R-7, kill-switch parity

`declineReasonProps` (`trades:5541`) is `undefined` whenever `declineReasonsOn`
(`feedback.decline_reasons`) is false. The prop expression at `trades:7412-7416` is

```
browseDecline={
  browseLive && sortedDeck.length > 0 && declineReasonProps
    ? { onPress: handleBrowsePass }
    : null
}
```

so under the kill switch it is **null** → the cell is Clear → the session has **no
decline control at all**, which is exactly today's behavior (the pager ✕ was wrapped in
`{declineReasonProps ? (` for the same reason). Gating on `browseLive && sortedDeck`
alone would render a ✕ that `handleBrowsePass` early-returns out of at `trades:5754` —
a dead control. Pinned whitespace-normalized by re-specced `4b2`.

## Step 5 — #411 lives inside the `compact` branch only

Walked arm by arm in `side`:

| Concern | non-compact (stacked page, flag off) | compact (column mode) |
|---|---|---|
| chip | `styles.chipCol` 44pt slot, `<PositionChip size="sm">` (`side:83-86`) — **unchanged**, and the 44pt ↔ `PlayerPickerModal.chipCol` lockstep (`check-picker-chip-alignment.js`) is untouched | moved to the meta line's `compactChipSlot` (`side:106-108`) |
| name | `<Text style={type.title}>` (`side:100`) — **unchanged** | `[type.title, styles.compactName]`, `numberOfLines={1}` (`side:96`) |
| name size | `type.title` 16/22 | `compactName` overrides `fontSize: type.bodySm.fontSize` / `lineHeight: type.bodySm.lineHeight` (`side:245-249`) → 13/18, applied **after** `type.title` so Archivo 600 + `chalk.base` survive |
| meta text | `numberOfLines={compact ? 1 : undefined}` (`side:119`) — **unchanged, count and form** | + `compactMetaText` (`side:250`) |
| price | trailing `styles.tierSlot`, `<TierBadge tier={t} />` default `md` (`side:165-168`) — **unchanged** | `compactPriceSlot`, `<TierBadge tier={t} size="sm" />` (`side:135-141`) |

Every #411 edit is inside a `compact ? … : …` branch or a `compact`-only style, so the
flag-off stacked render is byte-identical — which is what
`check-calc-merged-layout.js` rule **16** (one bare `numberOfLines={1}`, preceded by
`styles.compactName`) and **16b** (two `compact ? 1 : undefined` clamps) prove. Both
stayed **green with no edit**, as the PRD's §7.1 correction predicted.

`MemberEnteredMarker` (`side:151-157`) is still unconditional. The 32pt remove target
and its `hitSlop={compact ? 12 : 6}` (`side:177`) are unchanged. `TierBadge.tsx` and
`PositionChip.tsx` are not edited at all: only the `size` prop's **value at one call
site** moves, and the tier/position hexes remain `docs/cross-client-invariants.md` data
encodings.

**The shrink policy (R-13).** Measured on 97.5pt of `info` width, a WR chip (30.1) +
two 4pt gaps + an `md` `4+ 1sts` badge (63.5) = **101.6 > 97.5**, and `Card` sets
`overflow: 'hidden'` — the price would be clipped, the exact failure
`compactMetaText`'s own comment says it exists to prevent. So: `size="sm"` drops the
badge to 59.5 (worst realistic row **97.6**, a 0.1pt sub-pixel overhang);
`compactMetaText` gains `minWidth: 0` so it can actually reach zero and is always the
element that yields; and the chip and price slots carry `flexShrink: 0` so the two data
encodings are never what shrinks.

## Step 6 — #412's slot is `undefined` at all four pre-existing mounts

`belowAdd` is rendered at `side:198`, **after** the `<View ref={addRef}>` Add wrapper
(`side:192-194`) and **inside** the `Card` (`side:61` → `:200`), spaced by
`styles.inner`'s `gap: space.sm` (`side:205`). `side` imports no flag module.

| Mount | `belowAdd` / `giveBelowAdd` |
|---|---|
| `calc:1213-1246` — the **receive** `TradeSide` | not passed (`check-canvas-results.js` 12i2c pins exactly ONE `belowAdd=` in the file, 12i2d pins it inside the `const give = (` region at `calc:1189`, before `const receive = (` at `:1213`) |
| `calcScreen:751` — the pushed Real-values page | not passed; `giveBelowAdd` is optional (`calc:143`) so it arrives `undefined` |
| `FeaturedTradeWindow.tsx:82` | mounts `TradeBuildCanvas`/`InLeagueCalculator` without it — same |
| `canvas:193-194` when its host supplies none (the #270 experiment path) | threaded verbatim as `undefined` |

The give mount gets it at `calc:1205`. `canvas:109/112` declare both new props
**optional**, and `canvas:146-147/193-194` pass them straight through with no logic —
`check-canvas-results.js` `4l2` pins the optionality in both files and `4l3` pins
`browseDecline`'s absence from `FeaturedTradeWindow.tsx` and `calcScreen`.

## Step 7 — `shop_opened` still has one emitter

The slot's `onPress` (`trades:7441-7444`) is `haptics.selection()` → `openShopForCard(rawTopCard)`
— textually the pager entry's handler. `openShopForCard` is the one entry fork
(navigate vs the "Shop which player?" chooser) and **emits nothing itself**
(`check-canvas-results.js` 12i3); `shop_opened` fires once, inside `openShopWindow`, at
the navigate site (P-3, `check-shop-deck.js` h4a/h4c/h4d). `12i5` still counts exactly
three `openShopForCard(` occurrences — definition, deck chip, browse entry — which is
what proves the move did not add a caller. `check-shop-deck.js` passes **with zero
edits**, which is itself the evidence that the deck's own give-side chip
(`TradeCard.tsx:444-464`, `trade-card.keep-give`) did not move.

The argument is **`rawTopCard`** — the engine's original give side, not the edited
canvas. Same rule the pass signal follows (`trades:5744-5751`), stated again in a
comment at the slot's construction site. Accepted cost: after a mid-session give-side
swap the entry's label still names the engine's player (PRD §6.4).

## Step 8 — #409, the client half

`queue:50-51` is now

```ts
case 'not_league_member':
  return "Couldn't queue that — one side isn't showing as a league member.";
```

No `${name}`, no `@`. The server raises this one reason for **three** causes and two of
them are caller-side (`backend/server.py:13139-13143`), so the client cannot honestly
name a side. `name` stays a parameter — every other branch still uses it — and the
signature is unchanged. No `CalcQueueReason` split, no server change: the backend half
already shipped as `11c8903c` and `backend/` is not in this change's footprint
(`pytest backend/tests/test_calc_trade_queue.py` → **33 passed**, unchanged).

The file header's contract (`queue:26-36`) previously read *"Every line names whose
preference refused it and why"*, which this case now violates. It carries the carve-out
explicitly (`queue:31-36`), with the cause and the `backend/server.py:13139-13143`
citation — pinned by `check-calc-merged-behavior.js` 18k, because an undocumented
exception to a stated contract is a regression waiting on the next reader.
