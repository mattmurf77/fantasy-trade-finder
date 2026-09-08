# QA round 1 — agent A — 2026-09-08

## Summary: PASS (0 findings, 3 non-blocking observations)

## Environment
- Worktree at build tip `d80e9ee9` ("G-425 (#425/#426): docs rows, guard 3d tightened…"), diff under test `9be76a24..d80e9ee9`; working tree clean before and after (every sabotage reverted with `git checkout --`).
- node v24.14.1; `mobile/node_modules` = populated symlink to the parent checkout's install.
- pytest: **not applicable** — the diff touches no backend file (`git diff --stat 9be76a24..d80e9ee9 -- backend config` is empty).
- No simulator, no Maestro (D-056). Flags read from source, not pinned at runtime: `overhaul.enabled` (`TradesScreen.tsx:764`), `draft.room` (`:825`), experiment `trades_home_inline` (`showInlineHome`, `:960`).

## Results

| Test | Verdict | Evidence |
|---|---|---|
| `cd mobile && npx tsc --noEmit` | PASS | exit 0 (24.9 s) |
| every `mobile/tests/check-*.js` (98 files) | PASS | 98 green, 0 red — includes `check-presentation-v2`, `check-receipts`, `check-finder-conditions-reachable`, `check-trades-banner-region`, `check-team-review`, `check-inline-home`, `check-calc-merged-layout` |
| `node tests/check-team-overhaul.js` | PASS | 29 passed, 0 failed (3a–3e, 8 all green) |
| `bash scripts/testid-lint.sh` | PASS | `testid-lint OK`, exit 0 |
| `pytest backend/tests` | N/A | no backend file in the diff |
| Sabotage matrix (14 sabotages incl. one extra) | PASS | every sabotage RED on the named assertion, revert → green; table below |
| R-1 landing order, both cohorts | PASS | code-walk §R-1 |
| R-2 Draft cell gone, three other Draft entries survive | PASS | code-walk §R-2 |
| R-3 hero visual contract (`HERO_TONE`, ice-only, `radii.md`, `minHeight: 64`, testIDs, a11y) | PASS | code-walk §R-3 |
| R-4 gate + `overhaul_started {entry:'trades_home_card'}` unchanged | PASS | code-walk §R-4 |
| R-5 Toast offset still clears the hero; ice count ≤ 3 | PASS | code-walk §R-5 |
| Hunt: `TradesScreen.tsx` L9837–9849 (`cap` / `OUTLOOK_FALLBACK_LABEL`) untouched | PASS | `git diff -U0` hunks are only `@@ -6759,0 +6760,23`, `@@ -6797,5 +6820,4`, `@@ -7058,18 +7079,0`; `cap()` at post `:9837-9839`, `OUTLOOK_FALLBACK_LABEL` at `:9849-9855` byte-identical |
| Hunt: T-1 gate untouched | PASS | `consolidateOn && !outlookReceiptShown && !firstRun && canvasHost !== 'flag'` at post `:6930`, outside every hunk; `check-finder-conditions-reachable` green |
| Hunt: utility row layout with two cells | PASS | code-walk §Hunts |
| Hunt: hero on the pushed "Trade ideas" page (Q3 parity) | PASS | code-walk §Hunts |
| Hunt: FeedbackFAB rule | PASS | `grep FeedbackFAB OverhaulEntryCard.tsx` → none; TradesScreen is a tab-stack screen covered by RootNav's global mount; guard §2 green |
| Hunt: `TradeFinderModeBar.tsx` / `TeamReviewEntryCard.tsx` untouched | PASS | `git diff --stat 9be76a24..d80e9ee9 -- <both>` empty; `DRAFT_CHIP` still declared `TradeFinderModeBar.tsx:60`, consumed `:130` |

### Sabotage matrix — `check-team-overhaul.js` §3 / §8

Method: `python3` script edits the file(s), runs `node tests/check-team-overhaul.js`, records every `✗` line, then `git checkout --` the four files; `git status --porcelain` empty at the end. Baseline before and after: exit 0.

| # | Sabotage applied | RED line (verbatim) |
|---|---|---|
| S1 | second `<OverhaulEntryCard …/>` block pasted after `TeamReviewEntryCard` (old mount left in place) | `✗ 3a. exactly one <OverhaulEntryCard in TradesScreen` |
| S2 | hero block moved from above `modeBarWrap` to after `TeamReviewEntryCard` | `✗ 3a. hero ABOVE Team review` |
| S2b | hero block moved before `<ScrollView ref={mainScrollRef}` (outside the scroll) | `✗ 3a. hero INSIDE the main scroll` |
| S2c (extra) | hero block moved below the wrapper, just above `TradingWithStrip` | `✗ 3a. hero ABOVE the utility row / mode bar wrapper` |
| S3 | gate `{(overhaulOn \|\| !!activeOverhaul) && leagueId ? (` → `{leagueId ? (` | `✗ 3b. entry gated on the flag OR an active overhaul` |
| S4 | `onDraft?` prop + destructure + `trades.home-utility.draft` Pressable re-added to `TradeHomeUtilityRow.tsx` | `✗ 3c. Draft cell removed from TradeHomeUtilityRow` |
| S4b | `onDraft={draftRoomOn ? … : undefined}` re-added at the `<TradeHomeUtilityRow` mount | `✗ 3c. Draft cell removed from TradeHomeUtilityRow` |
| S5 | `const DRAFT_CHIP …` line deleted and `[DRAFT_CHIP, ...baseChips]` → `baseChips` in `TradeFinderModeBar.tsx` | `✗ 3d. TradeFinderModeBar still declares DRAFT_CHIP` |
| S5b | `onDraft={…}` pass deleted from the `<TradeFinderModeBar` mount | `✗ 3d. <TradeFinderModeBar mount still passes onDraft` |
| S6 | `fill: ice.base` → `fill: '#EF4444'` | `✗ 3e. hero colour/shape contract` — detail: `HERO_TONE.fill is not ice.base; contains a hex colour literal` |
| S6b | `flare` added to the import, `fill: flare.base` | `✗ 3e. hero colour/shape contract` |
| S6c | `borderRadius: radii.md` → `borderRadius: 16` | `✗ 3e. hero colour/shape contract` |
| S6d | `minHeight: 64` → `minHeight: 40` | `✗ 3e. hero colour/shape contract` |
| S7 | `overhaul.entry-start` → `overhaul.entry-go` (both occurrences) | `✗ 8. every §9 testID family appears literally` |

No sabotage stayed green. Note S5 is a true removal (declaration and usage both gone), stricter than the build report's rename.

## Code-walk proofs (post-change line numbers, `mobile/src/screens/TradesScreen.tsx` unless noted)

### R-1 — landing order, top to bottom

Both cohorts render the same tree; only the child of `modeBarWrap` differs.

**Inline-strip cohort** (`showInlineHome` = `finderMode === 'guided' && homeInlineVariant !== 'control'`, `:960`):

| # | Block | Lines |
|---|---|---|
| 0 | `<ScrollView ref={mainScrollRef} contentContainerStyle={styles.scroll}>` | `:6732-6754` (`styles.scroll = { padding: space.lg, gap: space.lg, paddingBottom: 96 }`, `:9874`) |
| 1 | `trades.win-now` link | `:6755-6759` (unchanged) |
| 2 | **hero** — `{(overhaulOn \|\| !!activeOverhaul) && leagueId ? (<OverhaulEntryCard …/>) : null}` | gate `:6768`, mount `:6769-6781`, closes `:6782` — a direct child of the scroll content, **before** the wrapper conditional |
| 3 | `{finderMode \|\| showInlineHome ? (<View style={styles.modeBarWrap} onLayout=…>` → `<TradeHomeUtilityRow onFreeAgents onManualCalc onTodaysTrade? onTrackRecord?/>` | conditional `:6807`, wrapper `:6808-6814`, row `:6817-6843`; no `onDraft` (comment `:6820-6823`) |
| 4 | `OutlookBiasReceipt` / `trades.outlook-fallback` | `:6888-6900` / `:6930` (T-1 gate untouched) |
| 5 | prefs-changed strip · `TradingWithStrip` | `:6995` tick · `:7013-7020` |
| 6 | `IdentityConfirmStrip` · `NewPartnersBanner` · `InviteLeaguematesBanner` | `:7025` · `:7038` · `:7049` |
| 7 | `TeamReviewEntryCard` | `:7068-7078` — followed directly by the `#224` page-title comment at `:7080`; the old overhaul mount that sat here is gone (diff hunk `@@ -7058,18 +7079,0`) |
| 8 | merged builder | unchanged, below |

**Control cohort** (`homeInlineVariant === 'control'`): identical except block 3's child is `<TradeFinderModeBar … onDraft={draftRoomOn ? () => navigate('DraftRoom') : undefined} …/>` (`:6845-6868`, `onDraft` at `:6855-6859`). The hero (block 2) is outside the `finderMode || showInlineHome` conditional and outside `modeBarWrap`, so it renders for this cohort in the same slot. Guard 3a pins: exactly one mount, index > `ref={mainScrollRef}`, < first `styles.modeBarWrap`, < `<TeamReviewEntryCard`.

Conditions under which the hero does **not** render: `overhaulOn` false AND `activeOverhaul` null (gate `:6768`); or no `leagueId`; `OverhaulEntryCard.tsx:73` also returns null on a falsy `leagueId`. `finderMode` plays no part, so the flag-off classic home (`!finderMode`) keeps its entry, as before.

### R-2 — Draft cell removed; the three other Draft entries survive

- `TradeHomeUtilityRow.tsx:28-46` Props: `onFreeAgents`, `onManualCalc`, `onTodaysTrade?`, `onTrackRecord?` — no `onDraft`. Destructure `:48-53` matches. Cells rendered: Today (`:60-76`, only with `onTodaysTrade`), Free agents (`:77-89`), Manual calc (`:90-102`), Track record (`:106-120`, only with `onTrackRecord`). No `trades.home-utility.draft` anywhere in the file. `Icon`/`chalk` imports (`:3-4`) are still consumed by the remaining cells.
- Mount `:6817-6843` passes no `onDraft`; `draftRoomOn` (`:825`) is still read by the mode-bar pass at `:6856`, so it is not dead.
- Survivors: (a) mode-bar chip — `TradeFinderModeBar.tsx:60` `DRAFT_CHIP`, `:130` `onDraft ? [DRAFT_CHIP, ...baseChips] : baseChips`, host pass `:6855-6859`; (b) seasonal Draft tab — `TabNav.tsx:620-635` `DraftStackNav` → `DraftRoomScreen` with `initialParams {inTabs:true}`; (c) League tab tile — `LeagueScreen.tsx:696-703` `showDraftRoom` → "Rookie draft" → `navigate('DraftRoom')`; plus the root-stack route `RootNav.tsx:907-908` (`src/utils/deepLinks.ts` untouched). None of these files is in the diff.

### R-3 — hero visual contract (`mobile/src/components/OverhaulEntryCard.tsx`)

- Import `:5` — `{ ice, space, radii, type, fonts }` only; `ink`, `chalk`, `semantic`, `flare` no longer imported. `:27` `const HERO_TONE = { fill: ice.base, press: ice.press, on: ice.on } as const` is the only colour source: `tile.backgroundColor: HERO_TONE.fill` `:123`, `tilePressed: HERO_TONE.press` `:132`, `title`/`line`/`trail` `color: HERO_TONE.on` `:134-136`. No `#` hex literal in the file (guard 3e; ice hex values live in `theme/chalkline.ts:43-47`).
- Shape `:122-131`: `borderRadius: radii.md` (= 8, `chalkline.ts:82`), `minHeight: 64` (= utility cell `TradeHomeUtilityRow.tsx:138`), `paddingVertical: space.md`, `paddingHorizontal: space.lg`, row layout, `gap: space.md`; no `borderWidth`, `shadow*`, `elevation`, gradient or `margin*` (the scroll's `gap: space.lg`, `:9874`, spaces it).
- Start state `:75-95`: outer `<View testID="overhaul.entry-card">` `:77` wrapping one `Pressable testID="overhaul.entry-start"` `:79`, `accessibilityRole="button"` `:82`, `accessibilityLabel="Start overhaul"` `:83`; title `Team overhaul` in `type.heading` (`BarlowCondensed_600SemiBold`, 22/26, uppercase — `chalkline.ts:107-114`, `fonts.displaySemi` `:87`) with `scale="display"` `:86`; one `type.bodySm` line `:87-89`; trailing `Start overhaul ›` in `fonts.uiBold` `:91`/`:136`.
- Resume state `:97-116`: `overhaul.entry-card` `:99`, `Pressable testID="overhaul.entry-resume"` `:101`, label `"Resume overhaul"` `:105`, `onPress → onResume(active.overhaul_id)` `:103`; title `Resume overhaul` `:108`; one line `{outlook} · {overhaulSummaryLine(active)}` with `numberOfLines={1}` `:109-111`, `outlook` = label or `'Outlook not set'` `:97`; trailing `Resume ›` `:113`. Kicker, pill and in-motion sentence removed; `LIVE_ATTEMPT_STATES` import still used by `overhaulSummaryLine` `:38`, whose export is unchanged `:35-60`.

### R-4 — gate and analytics unchanged

Post `:6768-6781` vs pre `:7060-7075` (from `git show 9be76a24:…`): gate `(overhaulOn || !!activeOverhaul) && leagueId`, props `leagueId`, `active={activeOverhaul}`, `onStart` → `track('overhaul_started', { league_id: leagueId, entry: 'trades_home_card' })` inside try/catch `:6773-6776` then `navigate('OverhaulOutlook')` `:6777`, `onResume` → `navigate('OverhaulPlan', { overhaulId })` `:6779-6780` — token-for-token identical apart from indentation. `overhaulOn = useFlag('overhaul.enabled')` `:764`; the `['overhaul', leagueId]` query is `enabled: !!leagueId && overhaulOn` `:768`; `activeOverhaul` `:770`.

### R-5 — Toast offset; ice count

- `modeBarBottom` state `:638`; set from the wrapper's `onLayout` `y + height` `:6810-6813`; consumed by `topOffset={modeBarBottom > 0 ? modeBarBottom + space.sm : undefined}` `:6638`. The hero is a sibling above the wrapper inside the same `contentContainerStyle` column, so the wrapper's `y` (relative to the scroll content) grows by hero height + `gap`; the offset therefore clears both. When the hero is absent nothing changes from today.
- Ice-**filled** elements on the strip cohort's landing (`backgroundColor: ice.base`): (1) hero `OverhaulEntryCard.tsx:123`; (2) `TeamReviewEntryCard.tsx:159` CTA, only while un-collapsed. The builder's Find a Trade is ice-**outlined** (`InLeagueCalculator.tsx:2121-2122` border + text) — PRD counts it as the third. Steady-state count = 3 (≤ 3). Other ice on the page is text/border/2–3 px ticks (`trades.win-now` `:6757`, `prefsChangedTick` `:10161`, `fairnessThumbOn` `:9963` inside the builder) or a conditional pre-existing banner (`InviteLeaguematesBanner.tsx:199`, `NewPartnersBanner.tsx:94`). Net delta of this change is zero ice fills: the removed card's CTA was already `backgroundColor: ice.base` (pre `:131`).

### Hunts

- **Utility row at two cells:** `row: { flexDirection: 'row', gap: space.sm }` `:126`, every cell `btn: { flex: 1, … }` `:127-139`; no fixed widths or `flexBasis`, so two cells split the width 50/50 (and 3–4 with the flag-gated cells). No orphaned Draft-specific style remains. Layout intact.
- **Pushed "Trade ideas" page (Q3):** `isResultsPushed` `:955` is referenced at `:2390, :3601, :3858, :6087, :6106, :8121` only — none in the entry region `:6755-7078`. Neither the hero nor the utility row reads it, so parity with the card holds (both render on the pushed page).
- **Hero inside the scroll, not fixed chrome:** the mount's nearest enclosing JSX parent is the `ScrollView` at `:6732` (no intervening `<View`/`Fragment` between `:6754` and `:6768` other than the closed `trades.win-now` conditional).
- **`tsc` type surface:** `TradeHomeUtilityRow`'s Props drop `onDraft`; `tsc --noEmit` exit 0 proves no other caller passes it.

## Findings

None.

### Observations (non-blocking, no action required for this group)

- O-1: `docs/config-reference.md`, `components.md`, `mobile/src/components/CLAUDE.md`, BUILD-CONTRACT §9/D9 rows are in the diff; DECISIONS / TEST_LEDGER / CHANGELOG / the two `status.md` files are deliberately deferred to the orchestrator (build report §7) — still pending at this sha.
- O-2: PRD R-5 counts the builder's Find a Trade as an "ice" element; it is ice-outlined, not ice-filled. Either way the ≤ 3 budget holds and the change adds no ice fill relative to the removed card.
- O-3: Guard 3e's hex check `/#[0-9a-fA-F]{3,8}\b/` would also flag a `#` in a comment; `strip()` is not applied to `entry` for this test. Harmless today (no such comment), noted only so a future comment mentioning "#EF4444" is not mistaken for a defect.

## TestFlight checklist (operator-run)

1. **Acquire tab, inline-strip cohort (FFV3 or Lakeview), `overhaul.enabled` on, no saved plan** → below the Win Now link the first block is a full-width ice tile reading TEAM OVERHAUL (condensed uppercase) / "Plan 4–5 trades that push all in or blow it up." / "Start overhaul ›" → directly beneath it the utility row shows exactly two cells, Free agents and Manual calc (Today / Track record only if those flags are on). **Fail:** a Draft cell in the row, or the tile anywhere other than directly above the row.
2. **Same screen, scroll down** → Team review (collapsed "Team review · done" row or the full card) is the last block before the trade builder; no second overhaul card anywhere. **Fail:** two overhaul entries, or a card under Team review.
3. **Tap the tile** → the Overhaul outlook screen opens; back → Acquire, same league, tile unchanged. Admin feed shows `overhaul_started` with `entry=trades_home_card`. **Fail:** no navigation, or a different `entry` value.
4. **With a saved plan (start one, pick an outlook, return)** → the tile reads RESUME OVERHAUL with one line `<Push all in | Blow it up | Outlook not set> · <summary>` (e.g. "Setup in progress", or "n sent · n accepted · n packages left") truncated to one line, trailing "Resume ›"; tap → the plan screen for that overhaul. **Fail:** two-line summary, missing outlook, or the Start state showing while a plan exists.
5. **Control cohort (non-allowlisted account)** → the tile sits above the mode-bar chip strip; the strip's leading chip is still Draft (with `draft.room` on) and opens the Draft Room. **Fail:** Draft chip missing.
6. **Flag off (`overhaul.enabled` off, no saved plan)** → no tile; the utility row still has no Draft cell (two cells). **Fail:** a Draft cell returning, or the tile rendering.
7. **Draft still reachable** → bottom Draft tab (seasonal, `draft.tab` on) opens the Draft Room; League tab → "Rookie draft" tile opens it. **Fail:** either entry missing.
8. **Toast check** → trigger any toast on the landing (e.g. change a preference) → it appears below the utility row, not over the tile. **Fail:** toast overlapping the tile or the row.
9. **Pushed "Trade ideas" page (calc.results_push on)** → the tile and the utility row appear on that page exactly as the old card did (parity, PRD Q3). **Fail:** a layout difference between the landing and the pushed page beyond what existed before.
