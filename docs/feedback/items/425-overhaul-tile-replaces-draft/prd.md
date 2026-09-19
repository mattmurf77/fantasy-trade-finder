# G-425 PRD — the Team overhaul hero takes the Draft button's slot (#425 + #426)

**Date:** 2026-09-08 · **Path:** polish, mobile · **Branch:** `claude/feedback-422-428` · **Evidence:** [investigation.md](investigation.md) · **Scope block:** [scope.md](scope.md)

**Decision in plain words.** On the Acquire landing the reporter sees a three-cell utility row whose first cell is a 64pt "Draft" button, and — five blocks lower — a full Team overhaul card. He wants one thing, not two, and he wants it big. So: the Draft cell leaves the row (the Draft Room keeps its seasonal bottom tab, the League tab tile and the deep link), the overhaul card leaves its spot under Team review, and a single full-width **Team overhaul** hero tile lands where the Draft button was — directly above the utility row. It is built in ice, the only action colour the design system allows; its fill is one constant so a true red is a one-line change if the operator adds that token.

## Requirements

**R-1 · Landing order.** Top of the main `ScrollView` (`TradesScreen.tsx:6754` onward), for the reporter's cohort:

| Before (build 154) | After |
|---|---|
| 1 `trades.win-now` link (`:6754`) | 1 `trades.win-now` link — unchanged |
| 2 `modeBarWrap` → `TradeHomeUtilityRow` **[Draft \| Free agents \| Manual calc]** (`:6783-6821`) | 2 **`OverhaulEntryCard` hero** (new mount, full width) |
| 3 outlook receipt / fallback (suppressed by T-1, `:6908`) | 3 `modeBarWrap` → `TradeHomeUtilityRow` **[Free agents \| Manual calc]** |
| 4 prefs-changed strip (transient) | 4–7 receipt/fallback · prefs strip · `TradingWithStrip` · banners — unchanged |
| 5 `TradingWithStrip` (`:6991`) | 8 `TeamReviewEntryCard` — unchanged, now the last block before the builder |
| 6 identity / partners / invite banners (`:7003-7045`) | 9 merged builder (`TradeBuildCanvas`, `:7910`) — unchanged |
| 7 `TeamReviewEntryCard` (`:7047`) | |
| 8 **`OverhaulEntryCard` card** (`:7058-7075`) | (removed here) |
| 9 merged builder (`:7910`) | |

Net: one fewer entry block and one fewer utility cell between the top of the page and the builder. The T-1 gate (`:6908`) and the merged calculator (`:6083-6098`, `:7910-8020`) are not touched.

**R-2 · Hero mount.** In `TradesScreen.tsx`, immediately **before** the `{finderMode || showInlineHome ? (<View style={styles.modeBarWrap}` conditional (`:6783`), outside it, mount `<OverhaulEntryCard …/>` with the **same props and the same gate** as today (`:7060-7075`): `{(overhaulOn || !!activeOverhaul) && leagueId ? ( … ) : null}`, `onStart` tracking `overhaul_started {league_id, entry:'trades_home_card'}` (`:7066`), `onResume` → `OverhaulPlan {overhaulId}`. Delete the mount at `:7058-7075`. Because the hero sits above `modeBarWrap`, the wrapper's `onLayout` y grows by the hero's height and the Toast `topOffset` (`:638`, `:6638`) keeps clearing both. The mount is independent of `finderMode`, exactly as the card is today (flag-off classic home keeps its entry).

**R-3 · Draft cell removed.** Delete the `onDraft` pass at `TradesScreen.tsx:6797-6801`, the `onDraft` prop (`TradeHomeUtilityRow.tsx:25`) and the Draft cell (`:74-88`); refresh the header comment (`:7-17`). `draftRoomOn` (`:825`) stays — the mode bar still reads it. **`TradeFinderModeBar.tsx` is not touched**: its Draft chip (`:49-60`, `:130`) is the control cohort's draft entry under the 2026-08-06 "permanent home" decision and is not the button the reporter sees (Q2).

**R-4 · Hero tile spec** (`OverhaulEntryCard.tsx`, same file, same export, same props). Outer `View testID="overhaul.entry-card"` wrapping ONE full-width `Pressable` — the whole tile is the button:

| Property | Value |
|---|---|
| Fill / pressed / foreground | `HERO_TONE = { fill: ice.base, press: ice.press, on: ice.on }` — a single module-level constant; every colour in the tile reads from it, nothing else in the file names a colour. Switching to red = editing this one object (Q1). |
| Size | full width of the scroll content; `minHeight: 64` (matches the utility cells it replaces, `TradeHomeUtilityRow.tsx:150`); padding `space.md` vertical / `space.lg` horizontal; `borderRadius: radii.md` (8, rule 5); no border, no shadow, no gradient; no `marginBottom` (the scroll `gap: space.lg` spaces it). |
| Start state | title `Team overhaul` in `type.heading` (Barlow Condensed, uppercase — the largest sanctioned type on a control), colour `HERO_TONE.on`; one `type.bodySm` line `Plan 4–5 trades that push all in or blow it up.` in `HERO_TONE.on`; trailing `Start overhaul ›` in `fonts.uiBold`. Pressable `testID="overhaul.entry-start"`, `accessibilityRole="button"`, `accessibilityLabel="Start overhaul"`. |
| Resume state | title `Resume overhaul`; one line `<outlook label> · <overhaulSummaryLine(active)>` (`numberOfLines={1}`; "Outlook not set" when unset); trailing `Resume ›`. Pressable `testID="overhaul.entry-resume"`, label "Resume overhaul". The separate kicker, outlook pill and in-motion sentence go — the summary line carries the counts. `overhaulSummaryLine` export unchanged. |
| Copy semantics | "Team overhaul" / "Start overhaul" / "Resume overhaul" preserved verbatim; no emoji, no icon glyph required. |

**R-5 · Colour ruling.** Ice, not flare, not `semantic.neg`: `design-system.md:20` and `:66` forbid flare on any actionable control; `:73` and `components.md:25` make `--neg` the Pass/error/destructive colour; `:23` forbids new hues. Ice count on the landing after the change ≤3 (hero, Team review CTA while un-collapsed, the builder's Find a Trade). A true red action tile requires a design-system addition — Q1.

**R-6 · Flag behaviour.** `overhaul.enabled` off and no active overhaul ⇒ no hero (gate unchanged). The Draft cell does **not** return: its removal is unconditional, so a kill-switch flip never re-lays-out the utility row. Flag-off landing = today's landing minus the Draft cell and minus the card — strictly less content, never a new element.

**R-7 · Pushed results page.** Parity with today: the hero renders on the `TradeDeck`+`resultsPush` page exactly where the card does now (neither reads `isResultsPushed`, `:955`). Q3 records the follow-up.

## Files and ownership (all G-425)

`mobile/src/components/OverhaulEntryCard.tsx` (hero rewrite) · `mobile/src/screens/TradesScreen.tsx` entry region only (`:6783-6821` utility-row pass, new mount before `:6783`, delete `:7058-7075`) · `mobile/src/components/TradeHomeUtilityRow.tsx` (prop + cell removal) · `mobile/tests/check-team-overhaul.js` (§3 rewrite, header item 3) · docs: `docs/plans/team-overhaul/BUILD-CONTRACT.md` §9 entry row + guard paragraph, `docs/design/components.md` (new "Hero entry tile" row), `mobile/src/components/CLAUDE.md:79,:90`, `docs/config-reference.md:417` (strip description), `living-memory/DECISIONS.md` (colour ruling), `TEST_LEDGER.md`, `CHANGELOG.md`, this folder's `status.md` + `426-*/status.md`. **Not touched:** `TradeFinderModeBar.tsx`, `TeamReviewEntryCard.tsx` (G-423), `InLeagueCalculator.tsx`, `TradeBuildCanvas.tsx`, any backend file, `config/features.json`.

## Regression guards — `check-team-overhaul.js` §3 (named sabotages)

| # | Assertion | Sabotage it catches |
|---|---|---|
| 3a | exactly ONE `<OverhaulEntryCard` in TradesScreen; its index is **less than** `<TeamReviewEntryCard`'s and less than the first `styles.modeBarWrap`, and greater than `ref={mainScrollRef}` | old mount left in place (two heroes); hero put back under Team review; hero mounted outside the scroll |
| 3b | unchanged: nearest `{cond ? (` before the mount names `overhaulOn`/`overhaul.enabled` **and** `activeOverhaul` | ungated hero |
| 3c | `TradeHomeUtilityRow.tsx` contains neither `trades.home-utility.draft` nor `onDraft`; the `<TradeHomeUtilityRow` mount slice (to its `/>`) in TradesScreen has no `onDraft` | Draft cell re-added |
| 3d | `TradeFinderModeBar.tsx` still declares `DRAFT_CHIP` and the `<TradeFinderModeBar` mount still passes `onDraft` | over-reach into the control cohort's chip |
| 3e | `OverhaulEntryCard.tsx` declares `HERO_TONE` once with `fill: ice.base`; does not import `flare`; no `#`-hex literal; every `borderRadius` reads `radii.`; a `minHeight: 64` is present | hardcoded red / flare fill / radius > 8 / tile shrunk |
| 8 | unchanged: the three entry testIDs appear literally | id rename loses the hook |

Existing landing guards named in investigation §3 must stay green; the builder runs `npm run test:team-overhaul test:presentation-v2 test:receipts test:finder-conditions test:trades-banner-region test:team-review test:inline-home test:calc-merged-layout`, `tsc --noEmit`, `testid-lint.sh`.

## Not changed

Overhaul screens and API; `overhaul_started` event and its `entry` value; the mode bar and its Draft chip; the seasonal Draft tab, League-tab tile and deep link; `TeamReviewEntryCard` (collapse/complete behaviour, G-423's fix); `TradingWithStrip`; T-1 and the merged calculator; Win Now link; first-run chrome rules; `draft.room` / `draft.tab` flags.

## TestFlight checklist (operator, next build)

1. Acquire tab, FFV3 or Lakeview: the first block under the Win Now link is a full-width ice tile reading TEAM OVERHAUL / Start overhaul ›; the utility row below it has exactly two cells (Free agents, Manual calc). Fail: a Draft cell, or the tile anywhere else.
2. Scroll: Team review (collapsed "Team review · done" or full card) is the only block between the pills/banners and the trade builder; no second overhaul card. Fail: two overhaul entries.
3. Tap the tile → Outlook step opens; back → Acquire, same league, tile unchanged. (Analytics: `overhaul_started entry=trades_home_card` in the admin feed.)
4. With a saved plan: the tile reads RESUME OVERHAUL with `<outlook> · <n sent · n accepted · n packages left>` on one line; tap → the plan screen.
5. Bottom tab Draft still opens the Draft Room; League tab → "Rookie draft" tile still opens it. Fail: either entry missing.

## Open questions (for the operator)

- **Q1 — red.** "Big red button" needs a colour the design system does not have: red is the Pass/error/destructive colour and flare may not sit on an action. Options: (a) accept the ice hero as specced; (b) add a new hero/alarm accent token (design-system + ADR-005 amendment + `chalkline.ts` + `web/style-guide.html`), after which the switch is the one-line `HERO_TONE` edit. Default until answered: (a).
- **Q2 — control cohort's Draft chip.** Every non-allowlisted user sees the mode bar, whose leading chip is Draft (2026-08-06 "permanent home"). Keep it (default; the strip is already scrolled and the chip is 36pt, not "content") or remove it too?
- **Q3 — pushed "Trade ideas" page.** Today both the utility row and the entry card render on the pushed results page; the hero inherits that. Suppress hero + utility row there in a follow-up? Default: parity now, follow-up later.
- **Q4 — Draft cell when overhaul is off.** Specced as permanently removed (R-6). Confirm, or should the cell return whenever the hero is absent?
