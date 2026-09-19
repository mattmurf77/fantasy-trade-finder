# G-425 build report — Team overhaul hero replaces the Draft cell (#425 + #426)

**Date:** 2026-09-08 · **Branch:** `feat/fb425-overhaul-hero-replaces-draft` (base `9be76a24`) · **Spec:** [prd.md](prd.md) · **Rulings:** [reconciliation-log.md](reconciliation-log.md) (Q1 ice via `HERO_TONE`; Q2 keep the mode-bar Draft chip; Q3 parity on the pushed page; Q4 Draft cell stays removed with the flag off)

**In plain words.** The Draft button is gone from the top row of the Acquire tab, and the Team overhaul card that used to sit five blocks lower is now one big full-width ice tile in the Draft button's old slot. Nothing else on the page moved. Draft is still reachable three other ways.

## 1. Code-walk — landing order, top to bottom

All line numbers are post-change, `mobile/src/screens/TradesScreen.tsx` unless noted. Both cohorts share one tree; only the row inside `modeBarWrap` differs (`showInlineHome`, `:960`).

### 1a. Inline-strip cohort (the reporter: `trades_home_inline` = strip)

| # | Block | Where | Note |
|---|---|---|---|
| 0 | main `ScrollView` | `ref={mainScrollRef}` `:6733` | everything below is scroll content |
| 1 | `trades.win-now` link | `:6756` | unchanged |
| 2 | **`OverhaulEntryCard` hero** | gate `:6768` → mount `:6769` | NEW position. Gate `(overhaulOn \|\| !!activeOverhaul) && leagueId` unchanged (`overhaulOn` `:764`, `activeOverhaul` `:770`); `onStart` tracks `overhaul_started {league_id, entry:'trades_home_card'}` `:6774`; `onResume` → `OverhaulPlan {overhaulId}` `:6779`. Mounted OUTSIDE `modeBarWrap` and independent of `finderMode` |
| 3 | `modeBarWrap` → `TradeHomeUtilityRow` **[Free agents \| Manual calc]** | conditional `:6807`, wrapper `:6809`, row `:6817` | the `onDraft` pass is gone (`:6820` comment marks the spot); `onTodaysTrade` / `onTrackRecord` flag-gated cells untouched |
| 4 | `OutlookBiasReceipt` / `trades.outlook-fallback` | `:6892` / `:6930` | untouched (T-1 gate `canvasHost !== 'flag'` at `:6930`) |
| 5 | prefs-changed strip · `TradingWithStrip` | `:7014` | untouched |
| 6 | `IdentityConfirmStrip` · `NewPartnersBanner` · `InviteLeaguematesBanner` | `:7026` · `:7039` · `:7050` | untouched |
| 7 | `TeamReviewEntryCard` | `:7069` | untouched; now the last entry before the builder — the old overhaul mount that followed it is deleted |
| 8 | merged builder `TradeBuildCanvas` | `:8008` | untouched |

Net: one fewer entry block, one fewer utility cell.

### 1b. Control cohort (mode bar)

Identical to 1a except block 3: `modeBarWrap` → `TradeFinderModeBar` (`:6845`) with its `onDraft` pass intact (`:6855`), so the control cohort's leading **Draft chip** (`TradeFinderModeBar.tsx:60` `DRAFT_CHIP`, `:130`) still renders — Q2 ruling. The hero (block 2) renders above the mode bar for this cohort too.

### 1c. Toast offset still clears the hero

`modeBarBottom` (`:638`) is set from the wrapper's `onLayout` `y + height` (`:6812`). The hero is a sibling ABOVE the wrapper inside the same scroll content, so the wrapper's `y` grows by the hero's height + the scroll `gap`; the Toast `topOffset = modeBarBottom + space.sm` (`:6638`) therefore clears both hero and row without any change.

### 1d. Flag-off / pushed page

`overhaul.enabled` off and no saved plan ⇒ gate `:6768` is false ⇒ no hero; the Draft cell does not return (its removal in `TradeHomeUtilityRow.tsx` is unconditional). The pushed `TradeDeck`+`resultsPush` page renders the same tree, so the hero appears there exactly where the card did (Q3 parity).

## 2. The hero's single colour constant

`mobile/src/components/OverhaulEntryCard.tsx:27`:

```ts
const HERO_TONE = { fill: ice.base, press: ice.press, on: ice.on } as const;
```

Every colour in the file reads from it — `tile.backgroundColor` `:123`, `tilePressed` `:132`, `title`/`line`/`trail` `color` `:134-136`. The import line brings in `ice, space, radii, type, fonts` only — no `chalk`, `ink`, `semantic` or `flare`; no hex literal anywhere. `borderRadius: radii.md` `:124` (8); `minHeight: 64` `:125`; padding `space.md`/`space.lg`; no border, shadow, gradient or margin. Title is `type.heading` (`scale="display"` cap, `:86`/`:108`) — the largest type sanctioned on a control. TestIDs `overhaul.entry-card` `:77`/`:99`, `overhaul.entry-start` `:79`, `overhaul.entry-resume` `:101`; `accessibilityRole="button"` + labels "Start overhaul" / "Resume overhaul" `:83`/`:105`. `overhaulSummaryLine` export unchanged.

Ice count on the landing after the change: hero + Team review CTA (only while un-collapsed) + the builder's Find a Trade = 3 (≤ 3).

**Q1 (red) — for the operator.** A "big red button" needs a colour the design system does not have: `--neg` is Pass/error/destructive, flare may not sit on an action, and rule 9 forbids new hues. If the operator wants a true red, that is a design-system + ADR-005 amendment (new hero/alarm token in `design-system.md`, `chalkline.ts`, `web/style-guide.html`); after that, the switch is editing the one `HERO_TONE` object above.

## 3. Removed Draft cell and the three surviving Draft entries

Removed: `TradeHomeUtilityRow.tsx` — the `onDraft?` prop, the `trades.home-utility.draft` Pressable (flag glyph, 64pt) and the header comment; `TradesScreen.tsx` — the `onDraft` pass at the utility-row mount. `draftRoomOn` (`:825`) stays: the mode bar still reads it (`:6855`).

Surviving Draft Room entries (none touched):

1. **Mode-bar Draft chip** for the control cohort — `TradeFinderModeBar.tsx:60` (`DRAFT_CHIP`), `:130`; pass at `TradesScreen.tsx:6855`.
2. **Seasonal bottom tab** — `TabNav.tsx:626-627` (`DraftRoom` route), shown via `draft.tab` `:717`.
3. **League tab "Rookie draft" tile** — `LeagueScreen.tsx:696-700` under `draft.room` (`:104`).

Plus the `app/league/draft-room` deep link (`TabNav.tsx:65`), which resolves to the root-stack route.

## 4. Guard assertions and RED evidence — `mobile/tests/check-team-overhaul.js` §3

Method: commit the fix first, then for each sabotage edit the file → run the guard → `git checkout --` the file → confirm green. Baseline before and after every sabotage: `check-team-overhaul: 29 passed, 0 failed`. (First attempt was invalidated because the reverts ran before the fix was committed — redone against commit `9610e5ec`.)

| Sabotage | RED line |
|---|---|
| S1 — old card mount left under Team review (two heroes) | `✗ 3a. exactly one <OverhaulEntryCard in TradesScreen` |
| S2 — hero moved back under `TeamReviewEntryCard` | `✗ 3a. hero ABOVE Team review` |
| S2b — hero mounted before `ref={mainScrollRef}` (outside the scroll) | `✗ 3a. hero INSIDE the main scroll` |
| S3 — gate reduced to `{leagueId ? (` | `✗ 3b. entry gated on the flag OR an active overhaul` |
| S4 — `onDraft` prop + `trades.home-utility.draft` cell re-added to the row | `✗ 3c. Draft cell removed from TradeHomeUtilityRow` |
| S4b — `onDraft=` re-added at the `<TradeHomeUtilityRow` mount | `✗ 3c. Draft cell removed from TradeHomeUtilityRow` |
| S5 — `const DRAFT_CHIP` renamed in `TradeFinderModeBar.tsx` | `✗ 3d. TradeFinderModeBar still declares DRAFT_CHIP` (first version of 3d matched the chip's *usage* too and stayed green — regex tightened to `const DRAFT_CHIP`, re-proven RED) |
| S5b — `onDraft=` dropped from the `<TradeFinderModeBar` mount | `✗ 3d. <TradeFinderModeBar mount still passes onDraft` |
| S6 — `fill: '#EF4444'` | `✗ 3e. hero colour/shape contract` (HERO_TONE.fill is not ice.base; contains a hex colour literal) |
| S6b — `import { …flare… }` + `fill: flare.base` | `✗ 3e. hero colour/shape contract` (references `flare`) |
| S6c — `borderRadius: 16` | `✗ 3e. hero colour/shape contract` (borderRadius not from radii.) |
| S6d — `minHeight: 40` | `✗ 3e. hero colour/shape contract` (no `minHeight: 64`) |
| S7 — `overhaul.entry-start` renamed | `✗ 8. every §9 testID family appears literally` |

Also run, all green after the change: every `mobile/tests/check-*.js` (98 files, 0 red — including `check-presentation-v2`, `check-receipts`, `check-finder-conditions-reachable`, `check-trades-banner-region`, `check-team-review`, `check-inline-home`, `check-calc-merged-layout`); `npx tsc --noEmit` exit 0; `bash scripts/testid-lint.sh` → `testid-lint OK`.

## 5. Operator TestFlight checklist (next build)

1. Acquire tab, FFV3 or Lakeview: the first block under the Win Now link is a full-width ice tile reading TEAM OVERHAUL / Start overhaul ›; the utility row below it has exactly two cells (Free agents, Manual calc). **Fail:** a Draft cell, or the tile anywhere else.
2. Scroll: Team review (collapsed "Team review · done" or the full card) is the only block between the pills/banners and the trade builder; no second overhaul card. **Fail:** two overhaul entries.
3. Tap the tile → Outlook step opens; back → Acquire, same league, tile unchanged. (Analytics: `overhaul_started entry=trades_home_card` in the admin feed.)
4. With a saved plan: the tile reads RESUME OVERHAUL with `<outlook> · <n sent · n accepted · n packages left>` on one line; tap → the plan screen.
5. Bottom tab Draft still opens the Draft Room; League tab → "Rookie draft" tile still opens it. **Fail:** either entry missing.

## 6. Docs updated (PRD list)

`docs/plans/team-overhaul/BUILD-CONTRACT.md` (§9 entry row, guard paragraph, and a pointer on the D9 row so the decision table does not contradict §9) · `docs/design/components.md` (new **Hero entry tile** row in the Cards table) · `mobile/src/components/CLAUDE.md` (`OverhaulEntryCard`, `TradeHomeUtilityRow` rows) · `docs/config-reference.md` (`trades_home_inline.strip` description) · `docs/plans/team-overhaul/mockups/entry-mock-evidence.md` (one superseded line). Not written here (orchestrator allocates ids): DECISIONS, TEST_LEDGER, CHANGELOG, `status.md` files.

## 7. DECISIONS entry text (for the orchestrator to id)

> **D-nnn · 2026-09-08 · Team overhaul hero is ice, not red; placement supersedes D9.** #426 asked for a "big red button". Chalkline has no red action fill: `--neg` is Pass/error/destructive, flare is informational-only and may not sit on an action, rule 9 forbids new hues. Ruling: the hero is ice — the only sanctioned bold action colour — and every colour in `OverhaulEntryCard.tsx` reads from one module constant `HERO_TONE` (`fill: ice.base`), pinned by `check-team-overhaul.js` §3e, so a future hero/alarm token (a design-system + ADR-005 amendment, operator's call — PRD Q1) is a one-object switch. Placement: the entry is a full-width tile directly above the utility row / mode bar (the removed Draft cell's slot), superseding D9's "directly below `TeamReviewEntryCard`"; the strip cohort's Draft cell is removed unconditionally (Q4), the control cohort's mode-bar Draft chip is kept (Q2), and the hero renders on the pushed results page wherever the card did (Q3, follow-up open).

## 8. Deviations from the PRD

- BUILD-CONTRACT D9 row (`:21`) got a one-clause pointer to §9 in addition to the two PRD-named edits — leaving it reading "directly below TeamReviewEntryCard" would have contradicted §9 in the same file.
- Guard 3d regex tightened from `\bDRAFT_CHIP\b` to `\bconst DRAFT_CHIP\b` after the sabotage showed the loose form was satisfied by the chip's usage alone.
- No other deviations. `TradeFinderModeBar.tsx`, `TeamReviewEntryCard.tsx`, the T-1 gate and the `OUTLOOK_FALLBACK_LABEL` region were not touched.
