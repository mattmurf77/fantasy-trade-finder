# QA round 1 — agent B — 2026-09-08

## Summary: PASS (0 findings)

Independent static verification of G-425 (#425 + #426). Every mechanical gate is green, all 13 named sabotages go RED on the assertion that names them and return to green on revert, and the code-walk confirms every requirement R-1..R-7 of [prd.md](prd.md) at the build tip. Two non-blocking observations are recorded under "Observations" (a doc imprecision about which landing element is the third ice use; nothing in the diff is wrong).

## Environment

- Worktree: detached at build tip `d80e9ee9` ("G-425 (#425/#426): docs rows, guard 3d tightened…"); diff under test `git diff 9be76a24..d80e9ee9` (10 files: 4 mobile source/test, 6 docs; **no backend file, no `config/features.json`**). `git status` clean before and after every sabotage.
- node v24.14.1, `mobile/node_modules` populated symlink; Python 3.14.4 (not used — see pytest row).
- Flags as pinned in `config/features.json` at the tip: `overhaul.enabled` true (`:82`), `draft.room` true (`:213`), `draft.tab` true (`:228`), `trades.finder_hub` true (`:14`), `calc.inline_home` true (`:95`), `trades.team_review` true (`:80`), `trades.presentation_v2` false (`:246`), `receipts.screen` false (`:252`).
- No simulator, no Maestro, no captures (D-056).

## Results

| Test | Verdict | Evidence |
|---|---|---|
| `cd mobile && npx tsc --noEmit` | PASS | exit 0, no output |
| every `mobile/tests/check-*.js` (98 files) | PASS | 98 run, 0 failed; `check-team-overhaul: 29 passed, 0 failed` (3a–3e + 8 all ✓) |
| `bash scripts/testid-lint.sh` | PASS | `testid-lint OK`, exit 0 |
| `pytest backend/tests` | NOT APPLICABLE | `git diff --name-only 9be76a24..d80e9ee9 \| grep -c ^backend/` → 0; no backend file in the diff |
| Sabotage S1–S7 (13 edits) — guard §3a/3b/3c/3d/3e/8 proven RED then green | PASS | table in "RED summary" below; scripted apply → guard → `git checkout --` → guard; tree clean at the end |
| R-1 landing order, inline-strip cohort | PASS | code-walk §1a |
| R-1 landing order, control cohort | PASS | code-walk §1b |
| R-2 hero mount above `modeBarWrap`, inside the scroll, old mount gone | PASS | code-walk §1a rows 0/2/3; `git diff` hunk `@@ -7055,24 +7077,6` deletes the old mount; exactly one `<OverhaulEntryCard` (guard 3a) |
| R-3 Draft cell removed; `onDraft` prop + pass gone; three other Draft entries survive | PASS | code-walk §2 |
| R-4 hero spec: single `HERO_TONE`, ice-only, `radii.md`, `minHeight: 64`, no border/shadow/gradient, states, testIDs, a11y labels | PASS | code-walk §3 |
| R-5 colour ruling / ice count ≤ 3 | PASS (with observation O-1) | code-walk §3, ice enumeration |
| R-4/R-6 gate `(overhaulOn \|\| !!activeOverhaul) && leagueId` and `overhaul_started {entry:'trades_home_card'}` unchanged | PASS | code-walk §4 |
| R-6 flag off ⇒ no hero AND no Draft cell (removal unconditional) | PASS | code-walk §2, §4 |
| R-7 hero renders on the pushed "Trade ideas" page where the card did (Q3 parity) | PASS | code-walk §6 |
| Toast `topOffset` still clears the hero | PASS | code-walk §5 |
| Utility row layout with two cells (flex math) | PASS | code-walk §2 |
| No change near `TradesScreen.tsx` L9837–9849 (G-423 alias) or the T-1 gate | PASS | code-walk §7 — both regions byte-identical modulo line shift |
| `TradeFinderModeBar.tsx`, `TeamReviewEntryCard.tsx`, `InLeagueCalculator.tsx`, `TradeBuildCanvas.tsx`, backend, `features.json` untouched | PASS | `git diff --name-only` filtered for those names → none |
| FeedbackFAB rule (tab-stack screen; no local FAB) | PASS | code-walk §8 |
| Stale references to the removed testID outside tests | PASS | `git grep home-utility.draft -- docs mobile ':!mobile/tests' ':!docs/feedback/items/425*'` → 0 hits |

## Code-walk proofs (all line numbers at `d80e9ee9`)

### §1a — R-1, inline-strip cohort (the reporter), top of the main scroll to the builder

`showInlineHome = finderMode === 'guided' && homeInlineVariant !== 'control'` (`TradesScreen.tsx:960`). The whole page is one `return (` at `:6629`; there is no cohort- or push-dependent early return before the `ScrollView` (searched `:5900-6733` for `isResultsPushed` / `return (` — only `:6087`, `:6106` (the `canvasHost` derivation) and `:6629`).

| # | Block | Lines | Condition |
|---|---|---|---|
| 0 | `<ScrollView ref={mainScrollRef} contentContainerStyle={styles.scroll}>` | `:6732-6733`; `styles.scroll = { padding: space.lg, gap: space.lg, paddingBottom: 96 }` `:9874` | — |
| 1 | `trades.win-now` Pressable | `:6755-6759` | `winNowOn && seasonProjectionsOn && leagueId && !switching` |
| 2 | **`OverhaulEntryCard` hero** | gate `:6768`, mount `:6769-6781`, `) : null}` `:6782` | `(overhaulOn \|\| !!activeOverhaul) && leagueId`; **not** inside `modeBarWrap`, **not** dependent on `finderMode` |
| 3 | `modeBarWrap` host View (`onLayout` → `setModeBarBottom(y + height)`) | conditional `:6807`, View `:6808-6814` | `finderMode \|\| showInlineHome` |
| 3′ | └ `TradeHomeUtilityRow` **[Free agents \| Manual calc]** | `:6817-6843` | `finderMode ? (showInlineHome ? … )`; props passed: `onFreeAgents`, `onManualCalc`, `onTodaysTrade` (undefined — `presentationV2On` false), `onTrackRecord` (undefined — `receiptsOn` false); **no `onDraft`** (comment `:6820-6823` marks the removal) |
| 4 | `OutlookBiasReceipt` / `trades.outlook-fallback` | `:6892` / `:6930-6931` | T-1 gate `… && canvasHost !== 'flag'` at `:6930` — suppressed for this cohort (`canvasHost === 'flag'` via `:6089-6090`) |
| 5 | `TradingWithStrip` | `:7013-7020` | `showInlineHome` |
| 6 | `IdentityConfirmStrip` · `NewPartnersBanner` · `InviteLeaguematesBanner` | `:7025-7032` · `:7038-7044` · `:7049-7056` | first-run / conditional |
| 7 | `TeamReviewEntryCard` | `:7068-7078` | `teamReviewOn && leagueId` — **now the last entry block**: the next JSX after `:7078` is the `#224` classic page title (`:7085`, `!finderMode` only), then the sub-route pills; the old overhaul mount that sat here is deleted (diff hunk `@@ -7055,24 +7077,6`) |
| 8 | merged builder `TradeBuildCanvas` | `:8008` | `canvasHost === 'flag'` |

Hero-above-wrapper ordering is exact: the hero's closing `) : null}` is `:6782`; the next non-comment JSX is the `modeBarWrap` conditional at `:6807`. Net change vs build 154: one fewer entry block between the top and the builder, one fewer utility cell.

### §1b — R-1, control cohort (mode bar)

Identical tree; block 3′ is the other arm of the same ternary: `TradeFinderModeBar` at `:6845-6874` with its `onDraft` pass **intact** at `:6855-6859` (`draftRoomOn ? () => navigation?.navigate?.('DraftRoom') : undefined`). The hero (block 2) renders above the mode bar for this cohort too, since its gate (`:6768`) reads neither `showInlineHome` nor `homeInlineVariant`. `TradeFinderModeBar.tsx` is not in the diff; `const DRAFT_CHIP` `:60`, `onDraft?` prop `:86`, `withDraft = onDraft ? [DRAFT_CHIP, ...baseChips] : baseChips` `:130` are as before.

### §2 — R-3, Draft cell removed; row layout; the three surviving entries

`TradeHomeUtilityRow.tsx`: `Props` `:28-46` has `onFreeAgents`, `onManualCalc`, `onTodaysTrade?`, `onTrackRecord?` — **no `onDraft`**; destructure `:48-53` matches; the JSX `:54-122` renders Today (`:60-76`, only if `onTodaysTrade`), Free agents (`:77-89`), Manual calc (`:90-102`), Track record (`:106-120`, only if `onTrackRecord`). No `trades.home-utility.draft`, no `flag` glyph. `TradesScreen.tsx` mount `:6817-6843` passes no `onDraft`. `draftRoomOn` (`:825`) still exists and is still consumed by the mode-bar arm (`:6856`) — not dead.

Layout with two cells: `row = { flexDirection: 'row', gap: space.sm, marginBottom: space.md }` `:126`; `btn = { flex: 1, … minHeight: 64 }` `:127-139`; no fixed widths anywhere in the file. Two `flex: 1` children split the width equally with one 8pt gap; `btnManual` adds only `borderStyle: 'dashed'` `:140`. The row was already variable-count (2–5 cells by flags) before this change, so a two-cell render is a previously-exercised state. Not broken.

Surviving Draft Room entries (none in the diff): (1) mode-bar chip — `TradeFinderModeBar.tsx:60,130`, pass `TradesScreen.tsx:6855`; (2) seasonal bottom tab — `TabNav.tsx:626-627` (`DraftRoom` / `DraftRoomScreen`), gated `draft.tab` `:717`; (3) League tab "Rookie draft" tile — `LeagueScreen.tsx:696-703` (`league.draft-room-row`, `navigation.navigate('DraftRoom')`), gated `draft.room` `:104`. Deep link `app/league/draft-room` — `TabNav.tsx:65` comment names the root-stack route it resolves to.

### §3 — R-4/R-5, the hero tile

`OverhaulEntryCard.tsx`:
- Imports `:5`: `{ ice, space, radii, type, fonts }` only — no `chalk`, `ink`, `semantic`, `flare`. **`HERO_TONE`** `:27` = `{ fill: ice.base, press: ice.press, on: ice.on } as const`. Every colour in the file reads from it: `tile.backgroundColor: HERO_TONE.fill` `:123`, `tilePressed.backgroundColor: HERO_TONE.press` `:132`, `title/line/trail.color: HERO_TONE.on` `:134-136`. Zero `#` hex literals in the file (guard 3e regex, confirmed by reading). `ice` values resolve to `#56D9EC` / `#3FC2D6` / `#071013` (`chalkline.ts:43-47`).
- Shape `:122-131`: `borderRadius: radii.md` (= 8, `chalkline.ts:82`), `minHeight: 64`, `paddingVertical: space.md` (12), `paddingHorizontal: space.lg` (16), `flexDirection: 'row'`, `alignItems: 'center'`, `gap: space.md`. No `borderWidth`, no shadow/elevation, no gradient import, no `margin*` — the scroll's `gap: space.lg` (`TradesScreen.tsx:9874`) spaces it. The outer `View testID="overhaul.entry-card"` (`:77`, `:99`) carries no style; as a child of a column container it stretches to full content width (RN default `alignItems: 'stretch'`), and the Pressable inside it likewise — full-width tile, whole tile is the button.
- Start state `:75-95`: `Pressable testID="overhaul.entry-start"` `:79`, `accessibilityRole="button"` `:82`, `accessibilityLabel="Start overhaul"` `:83`; title `Team overhaul` `:86` in `styles.title = { ...type.heading, color: HERO_TONE.on }` — `type.heading` is `BarlowCondensed_600SemiBold` 22/26 `textTransform: 'uppercase'` (`chalkline.ts:107-114`), the token's `color: chalk.base` is overridden by the spread order; `ChalkText scale="display"` sets the Dynamic-Type cap tier only (no `variant`, so no `header` a11y role is injected inside the button — `Text.tsx:43-44`); line `Plan 4–5 trades that push all in or blow it up.` `:88` in `type.bodySm`; trailing `Start overhaul ›` `:91` in `fonts.uiBold`.
- Resume state `:97-116`: `overhaul.entry-resume` `:101`, label "Resume overhaul" `:105`; title `Resume overhaul` `:108`; one line `{outlook} · {overhaulSummaryLine(active)}` with `numberOfLines={1}` `:109-111`, `outlook` = `OUTLOOK_LABEL[...]` or `'Outlook not set'` `:97`; trailing `Resume ›` `:113`. The old kicker / outlook pill / in-motion sentence are gone; `inMotion` local removed. `overhaulSummaryLine` export `:35-60` byte-identical to the pre-change version (diff shows no hunk in that range).
- Ice enumeration on the landing (fills, i.e. `backgroundColor: ice.base`): (1) hero tile `OverhaulEntryCard.tsx:123`; (2) `TeamReviewEntryCard.tsx:158-161` CTA — un-collapsed state only (`:98` collapsed row uses `rowChevron` text colour `:172`, not a fill); (3) the builder's **Find a Trade is not an ice fill** — `InLeagueCalculator.tsx:2121 actionPrimary: { borderColor: ice.base }` + `:2122` ice text; `actionBtn` `:2110-2118` has no background. Conditional 3-pt ice ticks pre-exist in `InviteLeaguematesBanner.tsx:196-202` and `NewPartnersBanner.tsx:91-95` and `prefsChangedTick` `TradesScreen.tsx:10161`. **Net ice delta of this change: 0** — the old card's `cta { backgroundColor: ice.base }` fill is replaced 1:1 by the hero's fill. Steady-state landing (banners absent, review collapsed) = 1 ice fill + 1 ice border; worst case within R-5's ≤ 3 fills. See O-1.

### §4 — gate and analytics handler unchanged

Pre-change mount (from `git show 9be76a24:…TradesScreen.tsx`, the deleted hunk) and post-change mount `:6768-6782` are the same 15 lines moved: gate `(overhaulOn || !!activeOverhaul) && leagueId`; `onStart` → `try { track('overhaul_started', { league_id: leagueId, entry: 'trades_home_card' }) } catch {}` then `navigation.navigate('OverhaulOutlook')` (`:6772-6777`); `onResume={(overhaulId) => navigation.navigate('OverhaulPlan', { overhaulId })}` (`:6778-6780`). `overhaulOn = useFlag('overhaul.enabled')` `:764`; `activeOverhaul = activeOverhaulQ.data?.active ?? null` `:770`. Flag off + no saved plan ⇒ `false && …` ⇒ `null`; the Draft cell cannot return because no code path passes `onDraft` to the row and the row declares no such prop (R-6).

### §5 — Toast offset

`modeBarBottom` state `:638`; set from the wrapper's `onLayout` `y + height` `:6810-6813`; consumed by `<Toast topOffset={modeBarBottom > 0 ? modeBarBottom + space.sm : undefined}>` `:6638`. The hero is an earlier sibling of the wrapper inside the same content container, so the wrapper's layout `y` includes the hero's height plus one scroll `gap`; the Toast therefore clears hero and row with no code change. When the hero gate is false the `y` shrinks accordingly — same dynamic the wrapper already had for the Win Now link.

### §6 — R-7 pushed results page parity

`isResultsPushed = finderHubOn && !!resultsPushParam` `:955` is read at `:2390`, `:3601`, `:3858`, `:6087`, `:6106`, `:8121` — none forks the render tree before the `ScrollView`, and neither the hero gate (`:6768`) nor the `modeBarWrap` conditional (`:6807`) reads it. The pushed instance therefore renders the hero in the same slot; before the change the card rendered on the pushed page for the same reason. Parity holds (ruling Q3); the follow-up to suppress hero + utility row there remains open, as recorded.

### §7 — untouched regions

`git diff --numstat` for `TradesScreen.tsx`: 27 added / 23 removed across exactly three hunks (`@@ -6757,6 +6757,29`, `@@ -6794,11 +6817,10`, `@@ -7055,24 +7077,6`; net +4 lines). `diff` of pre `:9837-9849` vs post `:9841-9853` → identical (`OUTLOOK_FALLBACK_LABEL` now at `:9849`). `diff` of pre `:6900-6915` vs post `:6922-6937` → identical (T-1 gate now at `:6930`; also `:7599`, `:7801` shifted +4). Not touched per `--name-only`: `TradeFinderModeBar.tsx`, `TeamReviewEntryCard.tsx`, `InLeagueCalculator.tsx`, `TradeBuildCanvas.tsx`, anything under `backend/`, `config/features.json`.

### §8 — FeedbackFAB

`grep FeedbackFAB` over `TradesScreen.tsx`, `OverhaulEntryCard.tsx`, `TradeHomeUtilityRow.tsx` → none. TradesHome is a tab-stack screen covered by the single global mount `RootNav.tsx:624`. The hero is top-anchored, so it never sits under the bottom-right FAB and needs no `setPinnedBottomBarHeight`. Guard 2 (`no overhaul screen references FeedbackFAB`) green.

## RED summary — `check-team-overhaul.js` §3 / §8 sabotage proofs

Method: scripted (`sabotage.py` in the QA scratchpad): baseline green (29/0) → apply edit → run guard → record `✗` lines → `git checkout -- <4 files>` → assert clean → run guard → green. All 13 went RED on exactly the assertion the PRD names, 28/1 each time, and returned to 29/0.

| # | Sabotage applied | Edit | RED line |
|---|---|---|---|
| S1 | old mount re-added under `TeamReviewEntryCard` (two heroes) | +16 | `✗ 3a. exactly one <OverhaulEntryCard in TradesScreen` |
| S2 | hero mount moved back under `TeamReviewEntryCard` | +16/−15 | `✗ 3a. hero ABOVE Team review` |
| S2b | hero mount moved before `<ScrollView ref={mainScrollRef}` | +15/−15 | `✗ 3a. hero INSIDE the main scroll` |
| S3 | gate reduced to `{leagueId ? (` | 1 line | `✗ 3b. entry gated on the flag OR an active overhaul` |
| S4 | `onDraft?` prop + `trades.home-utility.draft` cell re-added to `TradeHomeUtilityRow.tsx` | +8 | `✗ 3c. Draft cell removed from TradeHomeUtilityRow` |
| S4b | `onDraft={…}` re-added at the `<TradeHomeUtilityRow` mount | +1 | `✗ 3c. Draft cell removed from TradeHomeUtilityRow` |
| S5 | `const DRAFT_CHIP` renamed (declaration + usage) in `TradeFinderModeBar.tsx` | 2 lines | `✗ 3d. TradeFinderModeBar still declares DRAFT_CHIP` |
| S5b | `onDraft={…}` dropped from the `<TradeFinderModeBar` mount | −5 | `✗ 3d. <TradeFinderModeBar mount still passes onDraft` |
| S6 | `fill: '#EF4444'` | 1 line | `✗ 3e. hero colour/shape contract` |
| S6b | `import { ice, flare, … }` + `fill: flare.base` | 2 lines | `✗ 3e. hero colour/shape contract` |
| S6c | `borderRadius: 16` | 1 line | `✗ 3e. hero colour/shape contract` |
| S6d | `minHeight: 40` | 1 line | `✗ 3e. hero colour/shape contract` |
| S7 | `testID="overhaul.entry-start"` → `overhaul.start-entry` | 1 line | `✗ 8. every §9 testID family appears literally` |

Guard-quality note (no action): the guard strips comments before matching (`strip` `:86`), so the `// G-425 … no onDraft` comment at the mount cannot satisfy or trip 3c; the 3b gate search is a 400-char window before the mount, which is wide enough for the 8-line comment block above it. S5 renamed both the declaration and its usage so the sabotage represents a real removal, not a typo that `tsc` would catch first.

## Findings

None.

## Observations (non-blocking; no code change requested)

- **O-1 — doc imprecision, not a defect.** `prd.md` R-5 and `build-report.md` §2 count "the builder's Find a Trade" as the third ice fill. In code it is an ice **border + ice text** (`InLeagueCalculator.tsx:2121-2122`), not a fill. The actual fills on the landing are the hero and the un-collapsed Team review CTA (plus pre-existing conditional 3-pt ticks in two banners). The requirement (≤ 3, ice only) is met with room to spare, and this change adds no ice — it moves one fill. Worth a one-word fix in the two docs when someone next touches them.
- **O-2 — Dynamic Type.** The title uses `scale="display"` (cap ×1.2) while the body line and trail use the default `body` tier (×2.0). At the largest OS text sizes the Start-state line wraps and the tile grows past 64pt (fine — `minHeight`, no `maxHeight`); the Resume line is `numberOfLines={1}` and truncates. Consistent with the pre-change card. Nothing to fix.

## TestFlight checklist (operator-run, next build)

1. **Acquire tab, FFV3 or Lakeview, operator account (inline-strip cohort):** the first block under the "Win Now · season gains…" link is a full-width ice tile — uppercase condensed **TEAM OVERHAUL**, one line "Plan 4–5 trades that push all in or blow it up.", trailing bold "Start overhaul ›". Directly below it the utility row shows **exactly two** cells: Free agents, Manual calc (Manual calc dashed border). **Fail:** a Draft cell anywhere in that row; the tile below the row; a three-cell row.
2. **Scroll the same page:** between the League / Trading-with pills (and any banners) and the trade builder there is only the Team review entry (collapsed "Team review · done" row or the full card). **Fail:** a second Team overhaul card or tile anywhere below the utility row.
3. **Tap the tile (Start state):** the tile darkens while pressed; release → the Outlook step of Team overhaul opens. Back → Acquire, same league, tile unchanged. Admin feed shows `overhaul_started` with `entry=trades_home_card` for that league. **Fail:** no navigation, wrong screen, or the event missing / carrying a different `entry`.
4. **With a saved overhaul in that league:** the tile reads **RESUME OVERHAUL** with a single line `<Push all in | Blow it up | Outlook not set> · <n sent · n accepted · n packages left>` (truncated with an ellipsis if long, never a second line), trailing "Resume ›". Tap → the plan screen for that overhaul. **Fail:** two lines, the old outlook pill, or navigation to the Outlook step instead of the plan.
5. **Control cohort (a non-allowlisted account, or the operator with the `trades_home_inline` assignment cleared):** the ice tile still renders above the mode chip strip, and the strip's **leading chip is Draft** and opens the Draft Room. **Fail:** the Draft chip missing, or the tile missing for this cohort.
6. **Flag off (`overhaul.enabled` → false via `POST /api/feature-flags/reload`, no saved plan in the league):** the tile is gone; the utility row is still two cells (Free agents, Manual calc) — the Draft cell does **not** come back. Restore the flag. **Fail:** a Draft cell reappearing, or the tile still showing with no saved plan.
7. **Draft Room still reachable three ways:** bottom-tab **Draft** (seasonal, `draft.tab`) opens it; League tab → "Rookie draft" tile opens it; control cohort's mode-bar Draft chip opens it (step 5). **Fail:** any of the three missing.
8. **Toast clearance:** trigger any toast on Acquire (e.g. switch leagues, or a like/pass on a suggestion) and confirm it appears **below** the utility row, not over the tile or the row. **Fail:** toast overlapping the tile.
9. **Pushed "Trade ideas" page:** run Find a Trade so the results deck pushes; confirm the tile and the two-cell utility row appear at the top of that page exactly as the old card and three-cell row did (parity, ruling Q3). **Fail:** the tile missing there, or a Draft cell present there.
