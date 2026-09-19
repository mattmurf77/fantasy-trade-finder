# Mobile App Inventory — Test Grounding (2026-08-09)

*Regenerates `app-inventory-2026-07-10.md` (4+ weeks stale) from the CURRENT source in `mobile/src/screens/`, `mobile/src/navigation/`, `mobile/src/components/` and `mobile/src/api/`. Machine-generated from source review; regenerate when screens/flows change materially. Superseded doc is kept for history — where the two disagree, THIS one wins.*

App identity: `app.json` name "DTF - Dynasty Trade Finder", scheme `dtf`, `userInterfaceStyle: "dark"` (dark-mode only). Backend: `https://fantasy-trade-finder.onrender.com` (Flask, Render free tier → cold-start 30–60s is a first-class UX concern). Companion doc: `capture-matrix-2026-08-09.md` (the screen×state capture matrix built on this inventory).

---

## 0. Delta vs 2026-07-10

**Screens ADDED to the inventory (13 product + 2 excluded):**

| Screen | Why it's new here |
|---|---|
| `QuickSetTiersScreen` | #104/#119/#122 — now the Rank tab's DEFAULT launch route for no-pref users |
| `QuickRankScreen` | #136 — within-tier ordering pass after Quick Set |
| `RookieRanksScreen` | rookie-draft M2 — consolidated cross-position rookie board (`ranks.rookie_subset`) |
| `LeagueSummaryScreen` | #142/#181 — power rankings; now the **League tab root** (`LeagueRankings`), also root-stack `LeagueSummary` |
| `FreeAgentsScreen` | #144 — FA finder with Sleeper claim sheet |
| `DraftRoomScreen` | rookie-draft M4 (`draft.room`) — dual-registered (root stack + seasonal Draft tab) |
| `MockDraftScreen` | draft-extensions W2 (`draft.mock`) |
| `PickAssignmentScreen` | draft-extensions W3 M-A (`picks.assign`) — ESPN-only |
| `RecordPicksScreen` | draft-extensions W3 M-D (`draft.manual_picks`) — ESPN-only |
| `EspnConnectScreen` | ESPN WebView cookie capture (`espn.webview_capture`) — **excluded**, live WebView |
| `TestStagesScreen` | operator QA (`testing.stage_users`) — **excluded**, non-product |
| `TradeFinderHubScreen` | present in the tree, **UNROUTED** — see §2.30 |

**Screens CHANGED materially since 2026-07-10:**

- **`LeagueScreen`** — demoted from tab root to the pushed `LeagueHome` sub-route; gained the low-activity progress module, "Works right now" example card, per-section zero-folds, ESPN re-sync + auth-expired refusal, and a Draft-picks section.
- **`TradesScreen`** — 6158 lines (was ~1.5k). Now the Acquire tab's *guided-first landing* with a `mode` route param (`guided`/`team`/`player`), a `TradeDeck` sibling route, mode-bar chip strip, pin board, single-pin featured window + asset ideas, TradeDnaSheet "full" edit sheet, suppression/adaptation/diff banners, deck-done summary.
- **`SignInScreen`** — Apple sign-in is now the PRIMARY entry (`auth.accounts`); Sleeper username is the fallback; `onboarding.landing` flips the layout.
- **`LeaguePickerScreen`** — gained ESPN/MFL/Fleaflicker link footers + sheets, auto-skip, and an auto-opening ESPN sheet.
- **`SettingsScreen`** — 1600 lines; two full layouts (`account.settings_v2` vs legacy), Account section (link/verify/export/delete), stud-tax + pick-pricing modes.
- **`RankHomeScreen`** — 3 primary cards + "More ways to rank" disclosure + rankings-import link (was 4 flat cards).
- **`RankScreen` (Trios)** — rookie-scope control, `ⓘ` twin button, unlock-payoff line, 6 instruction-copy states.
- **`TiersScreen`** — added the **All** position tab (fans out to 4 parallel saves), board search (`ux.board_search`), 8-rung tier ladder.
- **`MatchesScreen`** — added `LeagueProgressModule` + "Find a trade" CTA on the empty state, HelpSheet, 5s deferred dismiss.
- **`ManualRanksScreen`** — added rookie scope + board search.
- **Nav** — Rank tab may now be a real destination (`ux.rank_tab_destination`); tab bar is 4 or 5 tabs (`draft.tab`); Trades tab reads "Acquire" (`#245`); League tab is a stack; deep-link router v2 (`ux.deeplink_router_v2`).

**Screens REMOVED:** none. `PlaceholderScreen` still exists and is still unregistered.

**Flag surface:** 13 flag-gated surfaces in the 2026-07-10 doc → **~95 keys in `config/features.json`**, ~60 of which the mobile client reads. See §6.

---

## 1. Navigation map

### 1.1 Root stack (`RootNav.tsx`, `headerShown:false` default)

| Route | Component | Presentation | Back control |
|---|---|---|---|
| `SignIn` | SignInScreen | plain | — |
| `LeaguePicker` | LeaguePickerScreen | plain | — (params `{espnLink?}`) |
| `Main` | `<TabNav/>` + VerifyAccountBanner + PushPrimingModal + FeedbackFAB | plain | — |
| `Settings` | SettingsScreen | **modal**, header | `settings.close-btn` |
| `Profile` | ProfileScreen (`u/:username`) | plain, header | `profile.back-btn` |
| `FeedbackInbox` | FeedbackInboxScreen | **modal**, header | native |
| `LeagueSummary` | LeagueSummaryScreen | plain, header | `league-summary.back-btn` |
| `FreeAgents` | FreeAgentsScreen | plain, header | `free-agents.back-btn` |
| `DraftRoom` | DraftRoomScreen | plain, header | `draft-room.back-btn` |
| `MockDraft` | MockDraftScreen | plain, header | `mock-draft.back-btn` |
| `PickAssignment` | PickAssignmentScreen | plain, header | `pick-assignment.back-btn` |
| `RecordPicks` | RecordPicksScreen | plain, header | `record-picks.back-btn` |
| `TestStages` | TestStagesScreen | plain, header | `test-stages.back-btn` |
| `SleeperConnect` | SleeperConnectScreen | **modal**, header | native |
| `EspnConnect` | EspnConnectScreen | plain (NOT modal), header | `espn-connect.back-btn` |

**Initial route** (`RootNav.tsx:294`): `!user → SignIn`; `user && (!league || !hasToken) → LeaguePicker`; else `Main`. Boot gate renders a splash `ActivityIndicator` until `booted`.

`DraftRoom` / `MockDraft` / `PickAssignment` / `RecordPicks` / `EspnConnect` register **unconditionally** — their flags gate the ENTRY POINT, not the route, so a stale deep link lands on an honest unavailable state.

Container-level overlays outside the navigator: `<AnalystGuide/>` (guided tour) and the deep-link fallback `<Toast/>`.

### 1.2 Deep links

Two prefixes: `Linking.createURL('/')` (`dtf://…`) and `https://fantasy-trade-finder.onrender.com`.
- **Legacy map** (flag `ux.deeplink_router_v2` OFF): `SignIn→signin`, `LeaguePicker→leagues`, `Main→app`, `Settings→settings`, `Profile→u/:username`.
- **V2 map** (flag ON, `utils/deepLinks.getLinkingV2`): full nested table — tabs + pushed screens all URL-addressable, incl. `app/league/draft-room`, `app/league/pick-assignments`, `app/league/record-picks`, `app/league/summary`, `app/trades/finder`. Buffers intents until the container is ready; unroutable links fire the fallback toast. `NavigationContainer` reads `linking` once, so a mid-session flag flip applies next launch.
- Separate manual handler captures `?ref=<username>` → `useSession.setInvitedBy`.
- `routeNotificationTap` (flag `notif.tap_routing_v2`) routes push taps and passes `match_id` into Matches.

### 1.3 Tab navigator (`TabNav.tsx`)

4 or 5 tabs, hosted under a global `<TopBar/>`. Presence of the Draft tab is decided **once at mount** from `draft.tab`.

| # | Route | Label | Hosts | Tap behavior |
|---|---|---|---|---|
| 1 | `Rank` | Rank | `RankStackNav` | flag `ux.rank_tab_destination` OFF → intercepted, opens **RankMenu** sheet. ON → normal navigate; focused re-tap pops to root |
| 2 | `Trades` | **Acquire** | `TradesStackNav` | prefetch `['liked-trades']`; re-tap pops/scrolls (`ux.retap_active_tab`) |
| 3 | `Draft` | Draft | `DraftStackNav` | only when `draft.tab`; re-tap pops |
| 4 | `Matches` | Matches | `MatchesScreen` | prefetch `['matches','all']`; re-tap scrolls |
| 5 | `League` | League | `LeagueStackNav` | re-tap pops/scrolls |

**Rank stack** (`RankStackNav`): `RankHome`, `Trios` (=RankScreen), `Anchors` (=PickAnchorScreen), `Tiers`, `QuickSetTiers`, `QuickRank`, `ManualRanks`, `RookieRanks`, `Trends`. **Initial route** = `PREF_ROUTE[rankingMethodPref]` (`quickset→QuickSetTiers`, `trio→Trios`, `anchor→Anchors`, `tiers→Tiers`, `manual→ManualRanks`); with no pref, #244's completion-aware default: all four quick-tiers positions complete → `Trios`, else `QuickSetTiers` opened AT the next unset position. Every surface carries an always-on `stack.back-btn` falling back to `RankHome`; with `ux.rank_tab_destination` ON each also carries a `rank.more-ways` header control opening the RankMenu sheet. `QuickSetTiers` hides its back control when it is the stack root (#217).

**Trades stack** (`TradesStackNav`): `TradesHome` (=TradesScreen, `initialParams {mode:'guided'}` when `trades.finder_hub`), `TradeDeck` (same component, registered only when `trades.finder_hub`), `Portfolio`, `TradeCalculator`.

**League stack** (`LeagueStackNav`): `LeagueRankings` (=LeagueSummaryScreen, tab ROOT) → `LeagueHome` (=LeagueScreen, pushed).

**Draft stack** (`DraftStackNav`): `DraftRoom` (=DraftRoomScreen, `initialParams {inTabs:true}`).

**RankMenu action sheet** (bottom Modal in `TabNav.tsx`): 3 primary rows (`rankmenu.quickset` / `.trios` / `.tiers`) + a "More ways to rank" disclosure (`rankmenu.more-toggle`) revealing `.anchors` / `.manual` / `.trends`. Each row prefetches the destination query then dispatches `CommonActions.navigate('Rank',{screen})`.

---

## 2. Per-screen inventory

Legend for **States**: each named state is a distinct capturable render. Data column lists the API function → backend path.

### 2.1 SignInScreen — root `SignIn`
- **Purpose:** Apple sign-in (primary), Sleeper username / league-URL (fallback), or demo session.
- **States:** `idle--apple` (Apple button + divider + username field) · `idle--no-apple` (primary "Connect →") · `idle--landing` (`onboarding.landing`: username-first, Apple demoted to a text link) · `idle--hint` (Keychain last-username row) · `idle--smart-start` (placeholder/hint change under `landing.smart_start_cta`) · `reauth-notice` · `focused` · `busy` · `busy--apple` · `busy--demo` · `error--generic` · `error--notfound` · `error--unavailable` · `error--smart-start-invalid` · `error--unsupported-platform` (ESPN/MFL URL) · `error--owner-unresolved` · `demo-escape` (landing + unavailable + `landing.try_before_sync`) · `submit-disabled` · guided-tour bubbles s0.1/s0.2/s0_err_*.
- **Data:** `appleSignIn` → `POST /api/auth/apple` · `signIn` → `POST /api/extension/auth` · `resolveSmartStart` → `POST /api/league/parse-url` · `getLeagues` → `GET /api/sleeper/leagues/{userId}` · `getLeagueRosters` → `GET /api/sleeper/rosters/{id}` · `getLeagueUsers` → `GET /api/sleeper/league_users/{id}` · `startDemoSession` → `POST /api/session/demo` · `track` → `POST /api/events`.
- **Flags:** `auth.accounts`, `onboarding.landing`, `landing.smart_start_cta`, `landing.try_before_sync`.
- **testIDs:** `signin.reauth-notice` `signin.apple-btn` `signin.hint-btn` `signin.username-input` `signin.error-text` `signin.error-demo-escape` `signin.continue-btn` `signin.demo-link` `signin.apple-link`.
- **Traps:** keyboard; guided bubble auto-opens ~600ms after mount and can spotlight the field; native Apple sheet is un-drivable; hint row appears async (layout shift).

### 2.2 LeaguePickerScreen — root `LeaguePicker`
- **Purpose:** pick a league (Sleeper + imported ESPN/MFL/Fleaflicker), then 2-phase session init.
- **States:** `loading` · `slow-load` (>4s "Waking up server") · `error` · `empty` · `populated` · `row-busy` · `link-footer` (any of espn/mfl/fleaflicker flags) · `espn-sheet-open` · `platform-sheet-open` · `auto-skip` (single league + `onboarding.league_autoskip`, effectively invisible) · guided-tour S1 bubble (≥2 leagues).
- **Data:** `getLeagues` → `GET /api/sleeper/leagues/{userId}` · `getEspnLeagues` → `GET /api/espn/leagues` · `getPlatformLeagues` → `GET /api/mfl|fleaflicker/leagues` · `buildSessionInitBody` → `GET /api/sleeper/rosters/{id}` + `GET /api/sleeper/league_users/{id}` + `GET /api/sleeper/players/warm` · `submitSessionInit` → `POST /api/session/init` (detached) · `maybePregenTrades` → `POST /api/trades/generate` · child `RankChipBadge` → `GET /api/league/rank-chip`.
- **Flags:** `espn.link`, `mfl.link`, `fleaflicker.link`, `onboarding.league_autoskip`, `onboarding.trades_first` (indirect).
- **testIDs:** `leagues.row.<league_id>` (templated) · `leagues.link-espn` `leagues.link-mfl` `leagues.link-fleaflicker`.
- **Traps:** ESPN sheet AUTO-OPENS on `{espnLink:true}` with an 800ms fallback timer; 4s slow-load timer; auto-skip can navigate away before interaction; two-phase optimistic nav.

### 2.3 RankHomeScreen — Rank stack `RankHome`
- **Purpose:** build-your-board chooser (Quick set / Trios / Tiers primary; Anchors / Overall / Trends behind a disclosure).
- **States:** `populated` (only steady state — no query) · `populated--more-expanded` · `import-link` (`ranks.import`) · `rookie-section` (`ranks.rookie_subset`) · `import-sheet-open` (paste step / review step) · `toast--imported`.
- **Data:** `setRankingMethod` → `POST /api/ranking-method` (fire-and-forget) · sheet: `POST /api/rankings/import-match`, `POST /api/rankings/import-apply`.
- **Flags:** `ranks.import`, `ranks.rookie_subset`.
- **testIDs:** `rank-home.card.{quickset|trio|tiers|anchor|manual|trends}` · `rank-home.import` `rank-home.more-toggle` `rank-home.rookie-ranks` · sheet: `rank-import.paste` `rank-import.match` `rank-import.apply` `rank-import.row.<n>`.
- **Traps:** More-ways rows + Rookies section are below the fold and behind the toggle; import sheet is a multiline keyboard paste flow; apply auto-navigates to `ManualRanks`.

### 2.4 RankScreen (Trios) — Rank stack `Trios`
- **Purpose:** 3-up tap-order head-to-head ranking loop.
- **States:** `loading` (3 skeletons) · `error` · `scope-empty` (rookie thin pool, checked BEFORE loading/error) · `populated` · `partial-selection` (1 or 2 ranked; instruction copy changes) · `all-ranked` (Confirm visible) · `submitting` · `speed-mode-on` · `streak-chip` · `progress-locked` (per-position `n/threshold`) · `progress-unlocked` (counters hidden + unlock banner, 2 copy variants) · `unlock-payoff` (`ux.outlook_inline_default`) · `info-sheet-open` · `toast--streak` / `--qc-compliment` / `--save-failed` / `--format-switch-failed`.
- **Data:** `getNextTrio` → `GET /api/trio?position=…[&scope=rookie]` · `getProgress` → `GET /api/rankings/progress` · `getStreak` → `GET /api/me/streak` · `submitTrioRanking` → `POST /api/rank3` · `setFormat` → `POST /api/scoring/switch` · `track` → `POST /api/events`. (`/api/trio/skip` is NOT called — Skip is a client refetch.)
- **Flags:** `swipe.qc_compliments`, `swipe.gesture_audit`, `ux.outlook_inline_default`, `ux.player_context_menu`, `visual.chalkline_cleanup`, `ranks.rookie_subset`.
- **testIDs:** `trios.card.{a|b|c}` `trios.info.{a|b|c}` `trios.pos-tab.{qb|rb|wr|te}` `trios.confirm-btn` `trios.skip-btn` `trios.speed-toggle` `rank.unlock-payoff` · scope: `trios.scope*`.
- **Traps:** speed mode persists in AsyncStorage (`ftf.trios.speedMode`) and auto-submits on the 2nd tap — leaks between runs; long-press (400/500ms) opens the info sheet only under `swipe.gesture_audit`; cards silently no-op while submitting; below-fold speed tile/Confirm/Skip/banner.

### 2.5 TiersScreen — Rank stack `Tiers`
- **Purpose:** 8-rung tier board with drag, multi-select, per-position or merged **All** view.
- **States:** `loading` · `error` · `scope-empty` · `populated` · `populated--all-tab` · `multi-select` (0 selected) · `multi-select--active` (action bar + `TierTargetChips`) · `expanded` (full-screen board; header/format/scope/copy chrome UNMOUNTED) · `sticky-header` · `search-focused` / `search-highlight` (`ux.board_search`) · `copy-in-flight` · `saving` · `unassigned-hidden` (pool empty) vs `unassigned-shown` · `alert--copy-confirm` · `alert--reset-confirm` · toasts (saved / save-failed / copied / copy-failed / reset / reset-failed / drag-reject / format-switch-failed) · `refreshing` (`ux.touch_polish`).
- **Data:** `getRankings` → `GET /api/rankings[?position=…][&scope=rookie]` · `getTiersStatus` → `GET /api/tiers/status` · `getRisersAndFallers` → `GET /api/trends/risers-fallers?window_days=30&top_n=50` · `saveTiers` → `POST /api/tiers/save` (All view = up to 4 parallel POSTs) · `copyTiersFromFormat` → `POST /api/tiers/copy-from-format` · `setFormat` → `POST /api/scoring/switch`.
- **Flags:** `ux.touch_polish`, `ux.board_search`, `visual.chalkline_cleanup`, `ranks.rookie_subset`.
- **testIDs:** `tiers.list` `tiers.save-btn` `tiers.search` `tiers.pos-tab.{qb|rb|wr|te|all}` · scope: `tiers.scope*`. **Player rows, tier headers, multi-select chips, expand/copy/action-bar buttons carry NO testIDs** — text/a11y-label only.
- **Traps:** drag = 220ms long-press + 18px activation (prefer multi-select + `TierTargetChips` or the a11y `tier:<tier>` custom actions); two native Alerts; guarded drop into Unassigned looks like a no-op; keyboard search SCROLLS, does not filter; expanded mode removes chrome from the tree.

### 2.6 QuickSetTiersScreen — Rank stack `QuickSetTiers`
- **Purpose:** guided per-position tier walk (8 rungs, top→FA). Rank tab's default launch route for no-pref users.
- **States:** `loading` · `error` · `scope-empty` · `step-populated` (3-col chip grid) · `step--selection` · `empty--search-miss` · `empty--all-placed` · `saving` · `cta--continue-no-picks` · `cta--continue-finish` · `cta--save-n` · `skip-hidden` (0 selected) · `back-disabled` (tier 0) · `alert--tiers-set` (finish → Not now / Quick rank) · `onboarding-return` (no prompt; navigates to Trades) · `guide-coach-mark` · toasts.
- **Data:** `getRankings` → `GET /api/rankings?position=…[&scope=rookie]` · `saveTiers` → `POST /api/tiers/save` (per step) · `track` → `POST /api/events` · `setFormat` → `POST /api/scoring/switch`.
- **Flags:** `visual.chalkline_cleanup`, `ranks.rookie_subset`, `onboarding.guided_avatar`+`onboarding.v2`, `ux.touch_polish`.
- **testIDs:** `quick-set.chip.<player_id>` `quick-set.save-btn` `quick-set.search` `quick-set.format-toggle` `quick-set.pos-tab.{QB|RB|WR|TE}` (**uppercase**) · scope: `quick-set.scope*`.
- **Traps:** the walk ALWAYS terminates in a native Alert; every successful save auto-advances the step; silent demotion (#161) mutates unselected players; save with 0 selected is a client-side skip; keyboard search inside a `KeyboardAvoidingView` over an absolute footer.

### 2.7 QuickRankScreen — Rank stack `QuickRank`
- **Purpose:** within-tier click-order ordering pass offered after Quick Set.
- **States:** `loading` · `error` · `scope-empty` · `empty--no-walkable-tiers` (fresh accounts land here; ghost Done only) · `step-populated` · `step--clicked` (numeric rank badges) · `empty--search-miss` · `saving` · `back-disabled` · footer label variants (`Save <TIER>` / `… & finish`).
- **Data:** `getRankings` → `GET /api/rankings?position=…` · `reorderRankings(…, 'quickrank')` → `POST /api/rankings/reorder` · `setFormat` → `POST /api/scoring/switch`.
- **Flags:** `visual.chalkline_cleanup`, `ranks.rookie_subset`, `ux.touch_polish`.
- **testIDs:** `quick-rank.chip.<player_id>` `quick-rank.save-btn` `quick-rank.search` `quick-rank.format-toggle` `quick-rank.pos-tab.{QB|RB|WR|TE}` · scope: `quick-rank.scope*`.
- **Traps:** the step list is data-derived (only tiers with ≥2 members); no finish Alert (just `goBack`); auto-advance per save.

### 2.8 PickAnchorScreen — Rank stack `Anchors`
- **Purpose:** value one player at a time in draft-pick terms.
- **States:** `loading` · `scope-empty` (3 reason copies) · `error` (Retry) · `empty--no-players` (no Retry) · `question` (player card + 8 rungs + Skip) · `busy` · `save-error` · `consequence-line` · `hint-line` · `done-card` (4 copy variants) · progress-line suffix variants (`· Rookies`, `· <POS>`, `· SF TEP`/`· 1QB PPR`).
- **Data:** `getAnchorPool` → `GET /api/rankings[?scope=rookie]` (staleTime **Infinity**) · `saveAnchor` → `POST /api/anchor/save`. Unmount invalidates rankings/progress/trio/tiers-status/trends.
- **Flags:** `ranks.rookie_subset`.
- **testIDs:** `anchors.scope-{all|qb|rb|wr|te}` (position pills) · `anchors.scope*` (rookie control). **⚠ Collision:** `anchors.scope-all` is emitted by BOTH the rookie "All players" segment and the ALL position pill when the flag is on. The 8 rung buttons, Skip, Start over and Retry have no testIDs.
- **Traps:** resume set persists in AsyncStorage `ftf_anchor_done_v1_<fmt>` — a "done card" can appear on a fresh launch unless storage is cleared; two-phase first paint.

### 2.9 ManualRanksScreen ("Overall Ranks") — Rank stack `ManualRanks`
- **Purpose:** editable full drag/tap rank board with jump-to-rank.
- **States:** `loading` · `scope-empty` · `error` · `empty--filter` · `populated` · `row--dragging` · `row--editing` (numeric TextInput) · `row--highlighted` (search hit) · save pill `pending`/`saving`/`saved`(1.5s)/`error` · `search-focused` (`ux.board_search`) · `refreshing` (`ux.touch_polish`).
- **Data:** `getRankings(null)` → `GET /api/rankings` · `reorderRankings` → `POST /api/rankings/reorder`.
- **Flags:** `ux.touch_polish`, `ux.board_search`, `ranks.rookie_subset`.
- **testIDs:** `manual-ranks.search` · `manual-ranks.scope*`. **No testIDs on rows, drag handles, position filter, rank-edit input, or Try again.** (Note: the 2026-07-10 LLD Appendix A predicted the prefix `ranks.` — source shipped `manual-ranks.`.)
- **Traps:** 600ms save debounce → mutation → 1500ms "saved" auto-clear (screenshot timing); saves silently skipped when <2 ids; keyboard number-pad commits on blur (no return key).

### 2.10 RookieRanksScreen — Rank stack `RookieRanks`
- **Purpose:** consolidated cross-position rookie drag board (`?scope=rookie` view filter). Never touches the tiers-save path.
- **States:** `flag-off` ("Rookie rankings aren't available yet.") · `loading` · `scope-empty` · `error` · `empty--filter` · `populated` · `row--dragging` · save pill (same 5 statuses) · `back-to-draft-row` (only when `returnTo==='DraftRoom'`) · `toast--format-switch-failed`.
- **Data:** `getRankings(null,{scope:'rookie'})` → `GET /api/rankings?scope=rookie` · `reorderRankings(…, 'rookie_ranks')` → `POST /api/rankings/reorder` · `setFormat` → `POST /api/scoring/switch`.
- **Flags:** `ranks.rookie_subset` (hard gate), `ux.toast_v2`, `a11y.reduce_motion`.
- **testIDs:** `rookie-ranks.list` `rookie-ranks.row.<pid>` `rookie-ranks.drag-handle.<pid>` `rookie-ranks.filter.{all|qb|rb|wr|te}` `rookie-ranks.save-status` `rookie-ranks.back-to-draft` `rookie-ranks.scope-empty*`.
- **Traps:** drag-only (no jump-to-rank); 600ms debounce; route params change the layout.

### 2.11 TrendsScreen — Rank stack `Trends`
- **Purpose:** 30-day risers/fallers + league consensus-gap easiest sells/buys.
- **States:** per-section (risers / fallers / consensus-gap) each independently: `loading` · `error` · `empty--no-history` · `empty--none-in-window` · `empty--no-league` (gap section, shown immediately) · `empty--no-baseline` · `empty--no-gaps` · `populated`. Plus `gap-block-empty--filter` (nested), 5 position tabs, `refreshing`.
- **Data:** `getRisersAndFallers` → `GET /api/trends/risers-fallers?window_days=30&top_n=10` · `getContrarianGap` → `GET /api/trends/consensus-gap?league_id=…&top_n=5` (enabled only with a league).
- **Flags:** none.
- **testIDs:** **NONE anywhere on this screen** — text/role selection only.
- **Traps:** everything below the fold; 60s staleTime means repeat visits skip the loading state.

### 2.12 TradesScreen — Trades stack `TradesHome` / `TradeDeck`
- **Purpose:** the swipe-deck trade browser and the Acquire tab's guided-first landing. Route params: `mode` (`guided`/`team`/`player`), `opponentUserId`, `opponentName`, `editDna`.
- **Mode semantics** (`trades.finder_hub` ON): `guided` = landing (mode bar / inline-home variants, `OutlookBiasReceipt`, canvas experiment); `team` = deck scoped to one opponent; `player` = two-column TRADE AWAY / TRADE FOR pin board replacing the direction toggle. Any mode set hides the classic title and the Trades/Portfolio/Calculator subnav and enables the consolidated (sheet) layout.
- **States (40 distinct renders):** `switching-overlay` · `slow-switch-overlay` (4s) · `format-gate` · `mode-bar` (+`--hint` when deck empty) · `inline-home--strip` / `--canvas` · `outlook-bias-receipt` · `prefs-changed-strip` · `identity-confirm-strip` · `new-partners-banner` · `invite-leaguemates-banner` · `classic-title+subnav` · `pin-summary-collapsed` · `controls-card-full` · `controls-consolidated` · `find-btn--find` / `--find-more` / `--disabled` · `progress-strip` (running job) · `featured-window` (+`--history-back`) · `asset-ideas-panel` (+`--loading`) · `trade-build-canvas` · `inferred-outlook-banner` · `outlook-set-banner` · `demo-bridge` · `redraft-label` · `provenance-chip` · `diff-banner` (8s auto-dismiss) · `apple-session2-banner` · `coach-mark-provenance` · `board-refresh-note` · `suppression-note` · `quickset-prompt-card` · `adaptation-moment` · `card-top` (+ peek, + swipe-nudge, + Queue/Queued, + Send-in-Sleeper, + disposition-disabled) · `skeleton` (first run) · `generating` · `deck-summary` · `exhausted--classic` · `empty--cold` · `queue-footer` · `toast*`.
- **Data:** `generateTrades` → `POST /api/trades/generate` · `getTradeStatus` → `GET /api/trades/status` · `swipeTrade` → `POST /api/trades/swipe` · `flagBadTrade` → `POST /api/trades/flag` · `getLikedTrades` → `GET /api/trades/liked` · `undoDeckSuppression` → `POST /api/trades/suppressions/undo` · `fetchAssetIdeas` → `POST /api/trades/asset-ideas` · `getLeaguePreferences`/`saveLeaguePreferences` → `GET|POST /api/league/preferences` · `getAssetPrefs`/`setAssetPref` → `GET|POST /api/league/asset-prefs` · `getLeagueCoverage` → `GET /api/league/coverage` · `getNewPartners` → `GET /api/league/activity` · `copyTiersFromFormat` → `POST /api/tiers/copy-from-format` · `getLeagueRosters` → `GET /api/sleeper/rosters/{id}` · `getLeagueUsers` → `GET /api/sleeper/league_users/{id}` · `getTradeValues` → `GET /api/trade/values` · `evaluateTradeInLeague` → `POST /api/trade/evaluate` · `getProgress` → `GET /api/rankings/progress` · `track` → `POST /api/events`.
- **Flags (25 + 7 onboarding):** `trades.finder_hub` `trades.queue_2k` `trades.new_partners_alerts` `trades.edit_full_sheet` `trades.intent_modes` `trades.sheet_targeting` `trades.player_offers_calc` `trades_home_inline.strip` `trades_home_inline.canvas` `trade.preference_lists` `trade.finder_targeting` `trade.asset_ideas` `trade.outlook_direction` `deck.signal_v2` `deck.replenishment` `deck.fatigue` `deck.session_rerank` `deck.first_session` `ux.swipe_undo` `ux.player_context_menu` `ux.retap_active_tab` `ux.outlook_inline_default` `ux.help_surface` `growth.share_landing` `draft.room` · onboarding: `.trades_first` `.guided_layer` `.quickset_prompt` `.apple_save_moment` `.share_sheet` `.rank_routing` `.demo_bridge`.
- **testIDs:** `trades.card-top` `trades.like-btn` `trades.pass-btn` `trades.find-btn` `trades.progress-strip` `trades.empty-text` `trades.deck-summary(+.see-liked|.done)` `trades.pin-summary(+.edit|.clear|.done)` `trades.board.add-away` `trades.board.add-for` `trades.board.{away|for}.<pid>` `trades.package-toggle` `trades.subnav.{trades|portfolio|calculator}` `trades.prefs-changed-strip` `trades.fairness-help` `trades.demo-bridge` `trades.redraft-label` `trades.diff-banner` `trades.apple-session2-banner(+.dismiss)` `trades.coach-mark.provenance` `trades.outlook-set-banner` `trades.board-refresh-note` `trades.suppression-note(+.undo|.dismiss)` `trades.adaptation-moment(+.dismiss)` `trades.share-liked` `trades.trio-entry` `trades.explore.free-agents` `trades.team-picker.<user_id>`.
- **Traps:** swipe needs |Δx|>120 **and** |velocity|>200 (slow synthetic drags snap back — use the buttons or a11y `like`/`pass`); 3 native Alerts; `OutlookSheet` FORCE-OPENS when prefs load with no outlook (unless firstRun / `ux.outlook_inline_default` / consolidated); `TradeDnaSheet` auto-opens from `editDna`; `AppleSaveMomentSheet` on a 700ms timer; poll loop 800→4000ms ±10% jitter; ScrollView disabled while generating; module-level once-per-session latches survive remounts; `firstRun` latches at mount.

### 2.13 TradeCalculatorScreen — Trades stack `TradeCalculator`
- **Purpose:** manual trade builder — In league / Real values / Demo league. Optional `prefill` route param.
- **States:** `mode-tabs` (2 or 3) · `league-mode` (delegates to `InLeagueCalculator`; format chips/TradeSides/pickers all unmounted) · `live-header` · `values-loading` · `values-error` (Retry / switch to demo) · `demo-header` · `sides-empty` · `sides-filled` · `verdict--live` (+`--stale`) · `evaluating` · `verdict--demo` · `one-sided-read` · `addon-suggestions` (4 header variants) · `package-suggestions` (4 variants) · `no-suggestions` · `actions-row` · `picker-open` · `toast--cleared-undo` (`ux.swipe_undo`).
- **Data:** `getTradeValues` → `GET /api/trade/values?scoring_format=…` · `evaluateTrade` → `POST /api/trade/evaluate` · chunked `evaluateTrades` for suggestions · `track` → `POST /api/events`. Draft persisted `ftf:tradecalc:v1`.
- **Flags:** `ux.swipe_undo`, `growth.share_landing`.
- **testIDs:** `calc.mode-tab.{league|live|demo}` `calc.verdict` `calc.clear-btn` `calc.find-a-trade` `calc.side-a-add` `calc.side-b-add` · picker: `calc.picker.search` `calc.picker.done` `calc.picker.row.<pid>` · `calc.share-image`.
- **Traps:** 250ms debounce before evaluate, suggestions ~2 round-trips later; async draft hydration can flip mode after first paint; native share sheet.

### 2.14 MatchesScreen — tab `Matches`
- **Purpose:** cross-league mutual matches + awaiting-them inbox. Route params `segment`, `at`.
- **States:** `skeleton` (3 tiles) · `error` · `empty--mutual-all` · `empty--mutual-filtered` · `empty--awaiting` (+`--with-cta` under `ux.empty_state_ctas`) · `populated--mutual` · `populated--awaiting` · `progress-module` (`matches.progress-module`) · `hold-hint` (`trade.preference_lists`) · `filter-chips` · `refreshing` · `optimistically-emptied` · toasts (dismissed+Undo, dismiss-failed, untouchable added/removed/failed).
- **Data:** `getAllMatches` → `GET /api/trades/matches/all` · `getAwaitingTrades` → `GET /api/trades/awaiting` (lazy) · `dismissMatch` → `POST /api/trades/matches/{id}/dismiss` · `getAssetPrefs`/`setAssetPref` → `GET|POST /api/league/asset-prefs` · `getLeagueSummary` → `GET /api/league/summary` · `getLeagueCoverage` → `GET /api/league/coverage` · `track` → `POST /api/events`.
- **Flags:** `ux.swipe_undo`, `ux.player_context_menu`, `ux.retap_active_tab`, `ux.empty_state_ctas`, `ux.help_surface`, `visual.chalkline_cleanup`, `trade.preference_lists`.
- **testIDs:** `matches.segment.{mutual|awaiting}` `matches.empty-text` `matches.go-to-trades` (reused by BOTH empty states) `matches.progress-module` `matches.matching-help`.
- **Traps:** dismiss holds the POST for 5000ms and flushes on unmount; long-press only for the context menu; pull-to-refresh does NOT work on the empty states (use the Refresh button); route `segment` needs a fresh `at` to re-apply.

### 2.15 LeagueSummaryScreen — tab root `LeagueRankings` + root `LeagueSummary`
- **Purpose:** league power rankings — per-team stacked bar chart + ranked list + drill-in roster.
- **States:** `no-league` · `loading` · `error` (+`--verification-required`) · `empty` · `populated` · `basis--consensus` / `--personal` / `--redraft-disabled` · `boards-identical` (ticks/deltas/legend keys all hidden, #248) · `overlay-on` (ghost ticks + Δ chips ≥2) · `filtered-suppression` (#208) · `subset--all|starters|bench` (control only mounts when `starters_available`) · `posfilter--*` (+`picks` pill) · `hint-line` (6 permutations) · `focused` (drill-in: card controls UNMOUNT, `roster-` prefixed set replaces them) · `roster-panel` · `draft-capital-section` · `odds--loading|null|populated` (`outlook.odds`) · `refreshing` · `league-home-row` (tab root only).
- **Data:** `getPowerRankings(…, 'consensus')` and `(…, 'personal')` → `GET /api/league/power-rankings?league_id=…&basis=…` (always both, in parallel) · `getOutlook` → `GET /api/league/outlook?league_id=…&basis=…` (only under `outlook.odds`).
- **Flags:** `ux.retap_active_tab`, `outlook.odds`, `picks.assign_tradeable` (child), `ux.touch_polish`.
- **testIDs:** `league-summary.league-home` `.basis.{consensus|personal|redraft}` `.subset.<k>` `.roster-subset.<k>` `.posfilter.<k>` `.roster-posfilter.<k>` `.bar.<user_id>` `.team.<user_id>` `.tick.<user_id>` `.delta.<user_id>` `.focus-caption` `.filter-caption` `.roster-close` `.back-all-teams` `.refresh` `.updated-at` `.avg-line` `.roster-picks` `.odds.section` `.odds.beta-ribbon` `.odds.source` `.odds.row.<roster_id>`.
- **Traps:** both routes can be mounted simultaneously (duplicate testIDs); `subset.*`/`posfilter.*` do NOT exist while focused; bars are narrow flex columns with tight hitSlop; the Redraft chip is a permanent no-op; `selectedId` survives basis/filter changes.

### 2.16 LeagueScreen — League stack `LeagueHome` (pushed)
- **Purpose:** classic league home — identity, matches roll-up, explore tiles, coverage, activity, contrarian, leaderboards.
- **States:** `no-league` · `first-paint-pending` (em-dashes everywhere) · `refreshing` · `low-activity` (action row + `LeagueProgressModule` + "Works right now" example card) · `populated` · per-section zero-folds (`matches-hidden`, `joined-chip-hidden`, `coverage-hidden`, `contrarian+leaderboards-hidden`) · `explore--draft-room-tile` / `--rookie-board-tile` / `--two-tiles` · `espn-badge` · `espn-resyncing` · `espn-resync-success` · `espn-resync-failed` · `espn-auth-expired` (+ Sign in button under `espn.webview_capture`) · `draft-picks-row` (`picks.assign` && ESPN) · `members-overlay` · `whats-new-coach-mark` · `market-pulse-strip` · `rookie-board-sheet`. **No error state exists** — failed queries render as zeros/dashes.
- **Data:** `getLeagueSummary` → `GET /api/league/summary` · `getLeagueCoverage` → `GET /api/league/coverage` · `getLeagueMembers` → `GET /api/league/members` · `getLeagueMemberUnlockStates` → `GET /api/league/member-unlock-states` · `getActivityFeed` → `GET /api/league/activity` · `getContrarianLeaderboard` → `GET /api/league/contrarian` · `getPickAssignments` → `GET /api/league/pick-assignments` · `getProgress` → `GET /api/rankings/progress` · `getTiersStatus` → `GET /api/tiers/status` · `importEspnLeague` → `POST /api/espn/import` · children → `GET /api/league/rank-chip`, `GET /api/market/movers`, `GET /api/leaderboard`, `GET /api/rookies`.
- **Flags:** `league.rookie_board_entry`, `draft.room`, `picks.assign`, `espn.webview_capture`, `league.activity_feed`, `league.unlock_badges_per_member`, `ux.whats_new`, `market.movers`, `growth.share_landing`.
- **testIDs:** `league.hero` `league.whats-new` `league.action.rank` `league.action.find` `league.rankings-row` `league.free-agents-row` `league.draft-room-row` `league.rookie-board-row` `league.draft-picks-row` `league.progress-module` `league.progress-invite` `league.works-now` `league.espn-resync` `league.espn-resync-signin` `league.rank-chip.<id>` `league.market-pulse(+.see-all)`. **No testIDs on the Matches tiles, joined chip, member rows, overlay close, or Coverage card.**
- **Traps:** `Share.share()` from the invite link; pull-to-refresh fires 6–8 parallel requests; nearly every section can be absent; only reachable by pushing from `LeagueRankings` (`league-summary.league-home`, itself hidden while a team is focused).

### 2.17 FreeAgentsScreen — root `FreeAgents`
- **Purpose:** FA finder by the caller's board values, with drop suggestions and a Sleeper claim-prep sheet.
- **States:** `no-league` (+`--with-cta` under `ux.empty_state_ctas`) · `loading` · `error--rosters-unavailable` (503, server copy verbatim) · `error--generic` · `populated` · `consensus-only-banner` · `empty--all` · `empty--position` · `refreshing` · claim sheet: `sheet-open` · `sheet--faab` · `sheet--over-budget` (CTA disabled) · `sheet--priority-waivers` · `sheet--no-waivers-info` · `sheet--open-slots` · `sheet--drop-list` · `sheet--no-candidates` · `sheet--untouchables-excluded` · `alert--espn|mfl|fleaflicker|local` refusal.
- **Data:** `getFreeAgents` → `GET /api/league/free-agents?league_id=…[&position=…]` (one request + cache entry PER position tab; no `placeholderData` ⇒ full-screen spinner on every first tab switch). No submit endpoint — `Linking.openURL('https://sleeper.com/leagues/<id>/players')`.
- **Flags:** `ux.empty_state_ctas`, `visual.chalkline_cleanup`, `ux.touch_polish`.
- **testIDs:** `free-agents.list` `free-agents.empty-text` (**ambiguous** — no-league AND no-results) `free-agents.pos-tab.{all|qb|rb|wr|te}` `free-agents.row.<pid>` `free-agents.add.<pid>` `free-agents.pick-league` · sheet: `fa-claim.sheet` `fa-claim.bid` `fa-claim.drop.<cid>` `fa-claim.open-sleeper`.
- **Traps:** native Alert on every non-Sleeper Add; number-pad keyboard inside an 85%-height sheet with no KeyboardAvoidingView; `resolveAddPlatform` treats any NON-NUMERIC league id (and any demo session) as `local` ⇒ refusal Alert, not the sheet.

### 2.18 PortfolioScreen — Trades stack `Portfolio`
- **Purpose:** cross-league exposure (which players owned across leagues).
- **States:** `gate--single-league` (+`--with-cta` under `ux.empty_state_ctas`) · `loading` · `error` (no retry, no pull-to-refresh — dead end) · `empty` · `populated` · `refreshing` · row chips `pool` vs `tiered`.
- **Data:** `getPortfolio(leagueIds)` → `GET /api/portfolio?league_ids=<csv>` (enabled only with ≥2 leagues).
- **Flags:** `ux.empty_state_ctas`.
- **testIDs:** `portfolio.open-settings` only.
- **Traps:** each row has a HORIZONTAL ScrollView of league chips (off-screen sideways, not just below fold).

### 2.19 ProfileScreen — root `Profile` (`u/:username`)
- **Purpose:** read-only public profile.
- **States:** `flag-off` · `missing-username` · `loading` · `error--404` · `error--other` · `populated` (+ optional tiers snapshot section, optional contrarian-takes section, avatar-image vs initial fallback).
- **Data:** `getPublicProfile` → `GET /api/profile/{username}` (skipAuth).
- **Flags:** `profiles.public_pages`.
- **testIDs:** **NONE.**
- **Traps:** deep-link only (needs `route.params.username`); 60s staleTime.

### 2.20 SettingsScreen — root `Settings` (modal)
- **Purpose:** leagues, ranking pref, trade-value modes, notifications, account/data rights, about, testing, sign out.
- **States:** `loading-gate` (whole tree absent until `/api/notifications/prefs` resolves) · `layout--v2` vs `layout--legacy` (`account.settings_v2` reorders every section) · `league-rows` (hidden when ≤1 league) / `row--active|busy|dimmed` · `connect-card--idle|typed|busy` · `platform-link-rows` · `steer-slider` · `stud-tax--market|heavy|off` (+busy) · `pick-pricing` (`trade.slot_pricing`) · `guided-tour-toggle` · `notif-denied-banner` (`notif.denial_recovery`) · `notif-toggles` · `quiet-hours` · `account--demo` · `account--identities` · `account--link-apple` (+busy) · `account--none` · `account--account-only-link` · `verification-row` (5 label variants) · `sleeper--connected|expired|not-connected|absent|disconnecting` · `public-profile-toggle` · `export--idle|exporting` · `delete--idle|deleting` · `testing-section` · `about-section` · `alert--merge-conflict` (3 buttons) · `alert--verify` · `alert--disconnect` · `alert--delete` (nested two-step) · toasts (many).
- **Data:** `getNotifPrefs`/`updateNotifPrefs` → `GET|PUT /api/notifications/prefs` · `getAccount` → `GET /api/account` · `deleteAccount` → `DELETE /api/account` · `appleSignIn` → `POST /api/auth/apple` · `linkSleeperUsername` → `POST /api/account/link-sleeper` · `getSleeperLinkStatus`/`unlinkSleeper` → `GET|DELETE /api/sleeper/link` · `getProfileVisibility`/`setProfileVisibility` → `GET|PUT /api/profile/visibility` · `exportAccountData` → `GET /api/account/export` · `getStudTaxMode`/`setStudTaxMode` → `GET|PUT /api/settings/stud-tax` · `getPickPricingMode`/`setPickPricingMode` → `GET|PUT /api/settings/pick-pricing` · `setRankingMethod` → `POST /api/ranking-method` · `switchLeague` → rosters+users+`POST /api/session/init` · `connectLeague` → `POST /api/league/parse-url`.
- **Flags:** `account.settings_v2`, `account.data_export`, `account.sleeper_disconnect`, `profiles.user_toggle`, `notif.denial_recovery`, `ux.help_surface`, `trade.slot_pricing`, `auth.accounts`, `espn.link`, `mfl.link`, `fleaflicker.link`, `testing.stage_users`, `onboarding.guided_avatar`.
- **testIDs:** `settings.link-espn` `settings.link-platform` `settings.stud-tax.<k>` `settings.pick-pricing.<k>` `settings.guided-tour-toggle` `settings.notif-denied-banner` `settings.test-stages` `settings.sleeper-disconnect` `settings.export-data` `settings.link-apple-btn` `settings.link-sleeper-input`. **The notification switches, quiet-hours switch, public-profile toggle, Test feedback / Verify / Delete / Sign out / Privacy / Terms / Help rows have NO testIDs.**
- **Traps:** very long scroll and the section ORDER flips with the layout flag; native Alerts on every destructive path incl. a nested delete confirm; system Share sheet on export; several rows only appear after their query resolves (absence ≠ flag-off).

### 2.21 FeedbackInboxScreen — root `FeedbackInbox` (modal)
- **Purpose:** tester inbox for locally captured feedback.
- **States:** `empty` · `populated` · `retry-sync-visible` · `retrying` · `row--responded` · `row--synced|pending|failed` · `row--status` (6 variants) · `row--delete-btn` (only under `ux.touch_polish`) · `alert--clear` · `alert--delete`.
- **Data:** `getMyFeedback` → `GET /api/feedback/mine` · `submitFeedback` → `POST /api/feedback` (sequential retry).
- **Flags:** `ux.touch_polish`.
- **testIDs:** `feedback-inbox.delete.<id>` only.
- **Traps:** hydrate + status refresh on mount can remove rows shortly after render; delete is long-press-only unless the flag is on; system Share sheet.

### 2.22 DraftRoomScreen — root `DraftRoom` **and** Draft-tab `DraftRoom`
- **Purpose:** read-only rookie draft room over one `/api/draft/board` payload. FTF never writes a pick.
- **States (Real mode):** `no-league` · `loading` · `error--schema` (no retry) · `error--generic` (retry) · `status-bar` (`Not started`/`Drafting now`/`Complete`/`Unavailable`) · `as-of--stale` · `as-of--degraded` (4 codes) · `rank-rookies-row` · `notice.<code>` (`order_not_set`, `startup_draft`, `platform_unsupported`, `class_not_loaded`, `mfl_reconnect`, `picks_not_assigned`) · `last-year-toggle` · `assign-progress-row` · `record-picks-row` · `unavailable--with-notice` / `--no-notice` · `your-picks-chips` · `board--picks-only` / `--round-ownership` / `--board` · `undrafted--consensus|my-board` · `coverage-nudge` · `undrafted-empty` · `deep-link-cta` + D9 note · `live-polling`.
- **States (Mock entry mode, `draft.mock` + `mode==='mock'`):** mode toggle + `MockRail` pinned; body is ONLY `MockEntryPanel` — `mock-entry.loading` · `.error` · `.card` (no-mock / active / complete) · `.blocked.{cpu_model_unvalidated|class_not_loaded|startup_draft|league_too_small|live|complete}` · `mock-setup-sheet`.
- **Data:** `getDraftBoard` → `GET /api/draft/board?league_id=…&basis=consensus|my_board` · `getPickAssignments` → `GET /api/league/pick-assignments` · `getMockDraft` → `GET /api/mock-draft` · `createMockDraft` → `POST /api/mock-draft` · `setAssetPref` → `POST /api/league/asset-prefs` · AnchorSheet → `POST /api/anchor/save`.
- **Flags:** `draft.live_poll`, `draft.rank_inline`, `ranks.rookie_subset`, `draft.mock`, `picks.assign`, `draft.manual_picks`. (Entry gated by `draft.room` / `draft.tab` elsewhere.)
- **testIDs:** `draft-room.scroll` `.state` `.as-of` `.refresh` `.empty-text` `.error-text` `.rank-rookies` `.assign-progress` `.assign-picks` `.last-year-toggle` `.record-picks` `.unavailable-text` `.basis.consensus` `.basis.my-board` `.coverage-nudge` `.undrafted-empty` `.deep-link` `.notice.<code>` `.order-row.<r>-<slot>` `.pick-row.<n>` `.undrafted-row.<pid>` `.action.{set-value|rank-rookies|add-target}` · mock: `mock.rail` `mock-entry.*` `mock-setup.*`.
- **Traps:** row menu is LONG-PRESS only (a11y action `menu` is the alternative) and rows are inert without `draft.rank_inline`; polling `refetchInterval` 15s gated on `draft.live_poll` && focused && app-active && `state==='live'`; a successful `createMock` AUTO-NAVIGATES to MockDraft; no pull-to-refresh in Mock mode.

### 2.23 MockDraftScreen — root `MockDraft`
- **Purpose:** FTF-native mock draft session — the only surface where a pick can be made; must prove at every scroll position that it is a simulation.
- **States:** `rail` (ALWAYS, outside the ScrollView, pinned by `mobile/tests/check-mock-mode-marker.js`) · `no-league` · `loading` · `error--schema|generic` (both retry) · `empty.<reason>` (`no_active_mock`/`class_not_loaded`/`cpu_model_unvalidated`/`unknown`) · `recap` (+ per-round sections + "Your draft") · `on-the-clock--you` / `--cpu` (persona label) · `pick-ticker` (2 TickLabel variants, 3 row tints) · `your-picks-chips` · `undrafted--consensus|my-board` (+ my-board-only CPU note) · `undrafted-empty` · `row-selected` · `confirm-bar` (+ pending) · `end-btn` (header-right, active only) · `alert--end-mock`.
- **Data:** `getMockDraft` → `GET /api/mock-draft?league_id=…&basis=…` · `pickInMockDraft` → `POST /api/mock-draft/pick` · `abandonMockDraft` → `POST /api/mock-draft/abandon` · `setAssetPref` → asset-pref write · AnchorSheet → `POST /api/anchor/save`.
- **Flags:** `draft.rank_inline` only (route is unconditional).
- **testIDs:** `mock-draft.rail` `.scroll` `.empty-text` `.error-text` `.empty.<reason>` `.recap` `.recap-row.<n>` `.on-the-clock` `.ticker-row.<n>` `.basis.*` `.undrafted-row.<pid>` `.undrafted-empty` `.confirm` `.confirm.cancel` `.confirm.draft` `.end` `.action.*`.
- **Traps:** native 3-button `Alert` on End; two-step pick (select row → confirm bar); header-right button only exists while active; `staleTime: Infinity`, no polling, no pull-to-refresh; zero `track()` calls by design.

### 2.24 PickAssignmentScreen — root `PickAssignment` — **ESPN-only**
- **Purpose:** ESPN pick-ownership grid. Ownership only; there is never a value input (D13).
- **States:** `unavailable` (flag off) · `no-league` · `loading` · `error--feature-disabled|generic` (+ retry) · **setup view** (`!seeded` or re-opened): `setup--loading-members` · `rounds-stepper` (+ min/max dimmed) · `order-type--linear|snake` · `espn-derived-note` · `order-list` (drag) · `setup-save` · `setup-cancel` · **grid view**: `progress` · `provenance-tag` · `open-questions` · `edit-order-link` (hidden on future seasons) · `traded-empty` / `traded-summary` (+ `traded-toggle`) · `season-tabs` (4) · `round--collapsed|expanded` · slot variants `pristine|deviation|contested|orphaned|highlighted|member-entered` · `confirm-season` / `season-confirmed` · `owner-sheet` · `conflict-sheet` (CAS 409) · toasts (3 success, 7 warn).
- **Data:** `getPickAssignments` → `GET /api/league/pick-assignments?league_id=…` · `getLeagueMembers(…, {includeSelf:true})` → `GET /api/league/members` · `assignPick` → `PUT /api/league/pick-assignments/<pick_id>` · `seedPickGrid` → `POST /api/league/pick-assignments/order`. Local: AsyncStorage `ftf_pick_board_confirmed_v1`.
- **Flags:** `picks.assign`.
- **testIDs:** `pick-assignment.{unavailable|no-league|loading|error|retry|setup|rounds-stepper|rounds-minus|rounds-value|rounds-plus|order-type|order-type.linear|order-type.snake|espn-derived-note|order-list|setup-save|setup-cancel|screen|progress|provenance|open-questions|edit-order|traded-empty|traded-summary|traded-toggle|season-tabs|owner-sheet|conflict-sheet|conflict-current|conflict-provenance|conflict.keep-theirs|conflict.use-mine|season-confirmed}` · templated `.order-row.<uid>` `.traded-row.<pick_id>` `.season-tab.<season>` `.round-toggle.<round>` `.slot.<pick_id>` `.confirm-season.<season>` `.owner-option.<uid>`.
- **Traps:** setup is drag-ONLY (180ms long-press + 18px activation; no a11y reorder action); `focusPickId` auto-selects the season tab AND auto-expands the round; owner sheet auto-closes on tap with the save in the background; season-tab tap resets every accordion.

### 2.25 RecordPicksScreen — root `RecordPicks` — **ESPN-only**
- **Purpose:** live offline pick recording during a real off-platform rookie draft. Only writer of `recorded_picks`.
- **States:** `no-league` · `unavailable` (flag off — note the no-league check runs FIRST) · `loading` · `error` (retry) · `not-assigned` (dead end, no CTA) · `progress` · `on-the-clock` · `team-picker-expanded` · `done-card` · `order-row--cursor|recorded|sending|unrecorded` · `undo-btn` · `undrafted-list` (hidden in the done state) · `undrafted-empty` · toasts.
- **Data:** `getDraftBoard` → `GET /api/draft/board?league_id=…&basis=consensus` (staleTime 5s, `refetchInterval` 15s) · `recordPick` → offline AsyncStorage queue (`ftf.recpicks.queue.v1`) flushing to `POST /api/league/recorded-picks` · `voidRecordedPick` → `POST /api/league/recorded-picks/void`.
- **Flags:** `draft.manual_picks`.
- **testIDs:** `record-picks.{scroll|no-league|unavailable|error|not-assigned|progress|on-the-clock|change-team}` · templated `.team.<uid>` `.order-row.<n>` `.undo.<n>` `.undrafted-row.<pid>`.
- **Traps:** **unconditional 15s polling** (no focus/app-active/state gate, unlike the Draft Room); cursor auto-advances after each record; nested Pressables (undo inside the row); `recordPick` never throws — " · sending…" can persist forever offline.

### 2.26 SleeperConnectScreen — root `SleeperConnect` (modal) — **EXCLUDED**
- Live `sleeper.com/login` WebView; injected JS polls `localStorage['token']` every 800ms. States: `browsing` · `error` · `linking` · `done--verified` · `done--not-verified`. Data: `linkSleeperToken` → `POST /api/sleeper/link`. testID: `sleeperconnect.done`.
- **Exclusion reason:** real third-party auth, content outside the RN a11y tree, un-mockable. **Success overlay auto-dismisses after 1200ms.**

### 2.27 EspnConnectScreen — root `EspnConnect` — **EXCLUDED (with a caveat)**
- Live `espn.com/login` WebView + Disney SSO + emailed OTP; reads `espn_s2`/`SWID` from the native cookie store. States: `base` · `wedge-hint` (10s timer) · `otp-hint` · `warm-up-reload` · capture (no overlay — just `goBack`) · abandon. testIDs: `espn-connect.{banner|reload|wedge-hint|otp-hint|webview}`.
- **Exclusion reason:** requires real credentials + an out-of-band code; clears cookies on every mount; auto-navigates back on capture.
- **⚠ Caveat / capturable remainder:** the SHEET AROUND it — `EspnLinkSheet` — IS capturable and worth matrix rows for its `input` / `team` / `done` steps, the my-leagues list, manual entry, and the private-league s2+SWID fields. Only the pushed WebView screen itself is excluded. Note `EspnLinkSheet` HIDES its own Modal while the WebView is pushed, so the sheet visibly disappears mid-flow by design.

### 2.28 TestStagesScreen — root `TestStages` — **EXCLUDED (non-product)**
- Operator QA: capture league templates, spawn a synthetic `qa_*` adoption-stage user, device factory reset. testIDs `test-stages.*`. **Exclusion reason:** operator tool, gated on `testing.stage_users` + a server allowlist, and spawning MUTATES global session state (destructive to any concurrent capture run).

### 2.29 PlaceholderScreen — **EXCLUDED (non-product)**
- Static title + note stub. Not registered in any navigator. One state, no data, no testIDs.

### 2.30 TradeFinderHubScreen — **UNROUTED DEAD CODE (verified)**
- `screens/CLAUDE.md:18` claims it is unrouted since the guided-first landing (#246). **Verified against source:** `grep -rn "TradeFinderHubScreen" mobile/` returns only (a) the file itself, (b) `TabNav.tsx:36` — a COMMENT, the import is commented out, (c) `TabNav.tsx:400` comment, (d) the CLAUDE.md line. **No navigator registers it; nothing imports the component. Unreachable at runtime.**
- It is a real 1196-line screen (DNA panel collapsed/expanded, 4 mode launcher cards, FA row, team-picker + untouchables Modals, testIDs `finder-hub.*` / `dna.*`), but it is **not capturable** and gets zero matrix rows. Its DNA editor moved to `TradeDnaSheet`; its FA link is superseded by the mode-bar chip.
- **Recommendation for the orchestrator:** the file should be deleted in a cleanup pass, or, if it is to be kept, revived behind a route — carrying 1196 lines of unreachable UI is a standing trap for anyone grepping testIDs (`dna.*` testIDs exist in BOTH this file and `TradeDnaSheet`).

---

## 3. Modal / sheet / overlay surfaces

| Surface | Mounted by | Flag | States | testIDs |
|---|---|---|---|---|
| `RankMenu` (in `TabNav.tsx`) | TabNav (global) | `ux.rank_tab_destination` decides the tab-tap path | collapsed · more-expanded | `rankmenu.{quickset,trios,tiers,anchors,manual,trends}`, `rankmenu.more-toggle`, `rank.more-ways` |
| `OutlookSheet` | TradesScreen (`!consolidateOn`) | shaped by `ux.outlook_inline_default`, `trade.outlook_direction` | populated · submitting · error | `outlook.save-btn` only |
| `TradeDnaSheet` | TradesScreen, DraftRoomScreen | `trade.preference_lists` (untouchables); shaped by `trades.edit_full_sheet`, `.intent_modes`, `.sheet_targeting` | DNA editor · untouchables-roster sub-view · error | `dna.done` `dna.league-picker` `dna.team-target.*` `dna.targets.*` `dna.fine.*` `dna.outlook.<k>` `dna.chase.<t>` `dna.shop.<t>` `dna.intent.<t>` `untouchables.*` |
| `SwapPlayerSheet` | TradesScreen, FreeAgentsScreen | — | loading · empty · populated | **none** |
| `SwapSuggestSheet` | TradesScreen | — | empty · populated | `trade-card.swap-suggest-sheet`, `trade-card.swap-option.<id>` |
| `PlayerPickerModal` | TradeCalculator, InLeagueCalculator, TradesScreen | — | search-empty · results | `calc.picker.search` `calc.picker.done` `calc.picker.row.<pid>` |
| `PlayerContextMenu` | Trades, Matches, DraftRoom, MockDraft, TradeCard | `ux.player_context_menu` | populated (host-supplied rows) | `player-menu`, `player-menu.<key>` |
| `LeagueSwitcherSheet` | TopBar (global), League, Trades, TradeDnaSheet | — | empty · populated · row-busy · error | `league.switcher.add-league` only |
| TopBar **notification bell sheet** | TopBar | `notif.tap_routing_v2` (flag OFF makes rows inert Views) | empty ("all caught up") · populated + unread dots + Clear all | `topbar.notif-row.<id>`; the bell button itself has NO testID (a11y label only) |
| TopBar **format tile / settings** | TopBar | — | inline | `topbar.league` `topbar.format` `topbar.settings` |
| `PushPrimingModal` | RootNav (global) | `ux.prompt_arbiter` | single layout | **none** — label-text only |
| `AppleSaveMomentSheet` | TradesScreen | `ux.prompt_arbiter` (defers while another surface holds the slot) | idle · busy · note/error | `trades.apple-sheet.<trigger>`, `.signin`, `.decline` |
| `FeedbackFAB` | RootNav (global) + offset helpers on 10 screens | `ux.touch_polish` (offset) | badge / no badge | `feedback.fab` |
| `FeedbackSheet` | FeedbackFAB | `ux.sheet_guard` | severity · note · guard-confirm | `feedback.severity.<v>` `feedback.note-input` `feedback.save-btn` |
| `HelpSheet` | Trades, Matches, RankScreen | `ux.help_surface` | populated | `help-sheet` + caller-supplied rows |
| `AnchorSheet` | DraftRoom, MockDraft | `draft.rank_inline` (entry) | rungs · error · result | `anchor-sheet` `.rung.<k>` `.error` `.result` `.done` |
| `RankImportSheet` | RankHomeScreen | `ranks.import` | paste · review (+ per-row resolution) · error | `rank-import.paste` `.match` `.apply` `.row.<n>` |
| `RookieDraftBoardSheet` | LeagueScreen | `league.rookie_board_entry` | loading · error · empty · populated + filter chips | **none** |
| `EspnLinkSheet` | LeaguePicker, QuickRank, QuickSetTiers, Settings, RootNav | `espn.link`, `espn.webview_capture`, `espn.league_picker`, `ux.sheet_guard` | input (my-leagues / empty / busy / manual / private s2+SWID) · team · done | `espn-link.*` (13 literal + 2 templated) |
| `PlatformLinkSheet` | LeaguePickerScreen | `mfl.auth_link`, `ux.sheet_guard` | input · team · done · auth-pick · auth-done | `platform-link.*` (13 literal + 3 templated) |
| `MarketPulseStrip` + movers sheet | LeagueScreen | `market.movers` | **returns null on loading/error/thin data alike** · populated · sheet | `league.market-pulse` `.see-all` `market-movers.sheet` |
| `draft/MockSetupSheet` | DraftRoomScreen | `draft.mock` | default · order-notice · error | `mock-setup-sheet` + 9 |
| `draft/MockEntryPanel` | DraftRoomScreen | `draft.mock` | loading · error · card (3 variants) · 6 blocked variants | `mock-entry.*` |
| `AnalystGuide` | RootNav (container level) | driven by `useGuide`; steps gated by `onboarding.guided_avatar` + `onboarding.v2` | null · talk-step (tap-catcher swallows taps) · action-step · spotlight · auto-advance (2400ms) | `guide.overlay` `.tap-catcher` `.bubble` `.step-x` `.dismiss-tour` `.avatar.<pose>` `.cta.<action>` |
| `CoachMark` | LeagueScreen, TradesScreen | `ux.whats_new` / inline | shown · dismissed | testID is a prop (`league.whats-new`, `trades.coach-mark.provenance`) |
| `Toast` | RootNav + ~14 screens | `ux.toast_v2` (warn/error hold ≥5s) | default / success / warn / error | **none** |
| `ShareTradeImage` | TradeCalculator, InLeagueCalculator | — | off-screen capture; text fallback | `calc.share-image` |
| Members overlay | LeagueScreen (inline Modal) | `league.unlock_badges_per_member` (extra chips) | populated · pending (`…`) · empty (no copy) | **none** |
| Claim sheet | FreeAgentsScreen (inline Modal) | — | see §2.17 | `fa-claim.*` |
| Owner / conflict sheets | PickAssignmentScreen (inline Modals) | `picks.assign` | see §2.24 | `pick-assignment.owner-sheet`, `.conflict-sheet` |
| Team-picker / queue sheets | TradesScreen (inline Modals) | `trades.queue_2k` (queue) | populated | `trades.team-picker.<uid>` |

**Cross-cutting sheet rules:**
- **iOS cannot stack sibling RN Modals.** Documented at `TradeDnaSheet.tsx:292` (which is why it uses an in-sheet roster view instead of `PlayerPickerModal`). Real nesting risk remains in `SwapSuggestSheet → SwapPlayerSheet/PlayerPickerModal` and `PlayerContextMenu → SwapPlayerSheet`.
- **`ux.sheet_guard`** adds a native discard-confirm Alert to `FeedbackSheet`, `EspnLinkSheet`, `PlatformLinkSheet`.
- **`ux.prompt_arbiter`** makes `PushPrimingModal` and `AppleSaveMomentSheet` defer while another surface owns the interrupt slot — they may not appear when a naive flow expects them.
- Surfaces with **zero testIDs** (text-only selection): `SwapPlayerSheet`, `RookieDraftBoardSheet`, `PushPrimingModal`, `Toast`, the TopBar bell button, the members overlay.

---

## 4. testID screen-dir vocabulary (as-built)

The LLD Appendix A grammar (`<screen>.<element>[.<qualifier>]`) still holds. The **as-built** `<screen>` vocabulary, superseding the 2026-07-10 list:

```
signin  leagues  rank-home  trios  tiers  quick-set  quick-rank  anchors
manual-ranks  rookie-ranks  trends  trades  calc  inleague  matches
league  league-summary  free-agents  portfolio  profile  settings
feedback  feedback-inbox  sleeperconnect  espn-connect  draft-room
mock-draft  pick-assignment  record-picks  test-stages
```
Shared chrome / sheet prefixes:
```
tab  topbar  rankmenu  rank  stack  header  push  fab  guide
dna  outlook  untouchables  help-sheet  anchor-sheet  player-menu
rank-import  espn-link  platform-link  mock-entry  mock-setup  mock
market-movers  fa-claim  trade-card
```
**Drifts from the 2026-07-10 registry:** `ranks.*` shipped as `manual-ranks.*`; `sleeper-connect` shipped as `sleeperconnect`; `Trades` gained `trades.board.*` / `trades.pin-summary.*` / banner IDs; `header.back` shipped as `stack.back-btn` (tab stacks) and `<screen>.back-btn` (root stack).

Dynamic-ID allowlist (`mobile/scripts/testid-lint-allow.txt`): `tab.*`, `rankmenu.*`, `rank-home.card.*`, `trios.card.*`, `trios.scope*`, `tiers.scope*`, `tiers.pos-tab.*`, `quick-set.scope*`, `leagues.row.*`, `calc.mode-tab.*`, `calc.picker.row.*`, `calc.side-*`, `rookie-ranks.filter.*`, `feedback.severity.*`, `draft-room.notice.*`, `draft-room.undrafted-row*`. **Many templated IDs shipped since are NOT in the allowlist** (e.g. `pick-assignment.slot.*`, `league-summary.bar.*`, `record-picks.order-row.*`, `mock-draft.undrafted-row.*`) — a lint sweep is owed.

---

## 5. Fixture profiles (`backend/tests/fixtures/profiles/`)

| Profile | Shape | Powers |
|---|---|---|
| `standard` | 12-team SF TEP, unlocked in BOTH formats, 4-position rankings + 30d history, seeded-suggested tiers, 1 ranked + 1 unranked opponent, 2 mutual + 1 awaiting match, activity_seed 3, feedback_reply_seed 1 | the bulk of populated states |
| `fresh` | 1 league (10-team 1QB PPR), locked, ZERO rankings/tiers/history, no matches. Extra user `qa_no_leagues` with an empty league list | first-run, empty, locked, empty-picker |
| `near-unlock` | threshold−1 trios per position in `sf_tep` only, still locked, 7d history | unlock banner, push priming |
| `two-leagues` | 12-team SF TEP + 10-team 1QB PPR, unlocked in both formats | league switcher, `/matches/all`, Portfolio gate pass |
| `single-format` | league resolves `sf_tep`, user ranked+unlocked only in `1qb_ppr` | FormatGate |

**All five profiles seed SLEEPER leagues with NUMERIC ids and no draft data.** Consequences for capture:
- **No ESPN profile exists.** `PickAssignmentScreen`, `RecordPicksScreen`, LeagueScreen's ESPN badge / re-sync / auth-expired / Draft-picks section, and `EspnLinkSheet`'s team step are all unreachable from the current fixture set without a new profile or a `/__test__` override.
- **No draft-board seed exists.** `DraftRoomScreen` and `MockDraftScreen` will render notice/unavailable/refusal states, not populated boards.
- `FreeAgentsScreen`'s claim sheet requires a numeric Sleeper league id — satisfied by all five profiles, but a demo session is treated as `local` and gets the refusal Alert.
- `anchors: null` in every profile ⇒ `PickAnchorScreen` always opens at the start of the queue (good), but the client-side AsyncStorage resume key can still poison a run.
- Every profile's `flag_overrides` pins only the 13 legacy keys; the ~50 newer keys come from `flags_base: release`, so any capture depending on a newer flag must pin it explicitly via `FTF_FLAGS`.

---

## 6. Feature flags read by the mobile client

`config/features.json` carries ~95 keys. Grouped by what the client actually reads:

- **Landing / auth:** `auth.accounts` `onboarding.landing` `landing.smart_start_cta` `landing.try_before_sync` `account.settings_v2` `account.data_export` `account.sleeper_disconnect` `profiles.user_toggle` `profiles.public_pages`
- **Onboarding (all AND-gated by the `onboarding.v2` master):** `.trades_first` `.league_autoskip` `.quickset_prompt` `.apple_save_moment` `.share_sheet` `.rank_routing` `.demo_bridge` `.guided_layer` `.guided_avatar`
- **Rank surfaces:** `ranks.import` `ranks.rookie_subset` `swipe.qc_compliments` `swipe.gesture_audit` `ux.board_search`
- **Trades / deck:** `trades.finder_hub` `trades.queue_2k` `trades.new_partners_alerts` `trades.edit_full_sheet` `trades.intent_modes` `trades.sheet_targeting` `trades.player_offers_calc` `trades_home_inline.strip` `trades_home_inline.canvas` `trade.preference_lists` `trade.finder_targeting` `trade.asset_ideas` `trade.outlook_direction` `trade.send_in_sleeper` `trade.slot_pricing` `trade_math.human_explanations` `deck.signal_v2` `deck.replenishment` `deck.fatigue` `deck.session_rerank` `deck.first_session`
- **League:** `league.activity_feed` `league.unlock_badges_per_member` `league.rookie_board_entry` `market.movers` `outlook.odds`
- **Draft:** `draft.room` `draft.tab` `draft.live_poll` `draft.mock` `draft.rank_inline` `draft.manual_picks` `picks.assign` `picks.assign_tradeable`
- **Platform linking:** `espn.link` `espn.webview_capture` `espn.league_picker` `mfl.link` `mfl.auth_link` `fleaflicker.link`
- **UX / teardown remediation:** `ux.sheet_guard` `ux.rank_tab_destination` `ux.retap_active_tab` `ux.deeplink_router_v2` `ux.player_context_menu` `ux.swipe_undo` `ux.toast_v2` `ux.prompt_arbiter` `ux.empty_state_ctas` `ux.help_surface` `ux.touch_polish` `ux.whats_new` `ux.outlook_inline_default` `visual.chalkline_cleanup` `a11y.text_scaling` `a11y.reduce_motion`
- **Notifications / analytics:** `notif.tz_sync` `notif.tap_routing_v2` `notif.denial_recovery` `analytics.client_events` (gates `track()` entirely) `experiments.engine`
- **Operator:** `testing.stage_users`

`state/useFeatureFlags.ts` hard-codes only THREE local defaults (`espn.link`, `auth.accounts`, `ranks.import`) — **every other key is server-supplied**, so a capture run must pin what it depends on.

---

## 7. Test-relevant hazards (updated)

- **Dark-mode only** (`userInterfaceStyle: "dark"`) — baselines must be dark.
- **Sentry active in builds** unless `FTF_ENV=test` nulls the DSN.
- **Gestures likely to flake:** `SwipableTopCard` (Δx>120 AND |v|>200); `DraggableFlatList` on Tiers (220ms/18px), ManualRanks (220ms/18px or 5px), RookieRanks (220ms/18px), PickAssignment setup (180ms/18px). Prefer chevrons, multi-select, jump-to-rank, a11y custom actions, or the disposition buttons.
- **Native Alerts** now appear on: Tiers (copy, reset), QuickSetTiers (finish), Trades (3), Settings (4 incl. a nested delete), FreeAgents (4 platform refusals), MockDraft (end), FeedbackInbox (2), TestStages (2), EspnLinkSheet, PlatformLinkSheet.
- **Auto-opening surfaces** that can appear over any capture: `PushPrimingModal`, `AnalystGuide` (auto-advance 2400ms + tap-catcher), `OutlookSheet` (force-open when prefs have no outlook), `TradeDnaSheet` (`editDna` param), `AppleSaveMomentSheet` (700ms), `EspnLinkSheet` (`{espnLink:true}` + 800ms fallback), `Toast` (timer-driven), `FeedbackFAB` (always mounted, occludes bottom-right).
- **Timers/debounces:** calculator evaluate 250ms · ManualRanks/RookieRanks save 600ms + 1500ms saved-pill · Matches dismiss 5000ms deferred POST · trade poll 800→4000ms ±10% · undo toasts 5000ms · diff banner 8000ms · slow-load/slow-switch 4000ms · guide auto-advance 2400ms · SleeperConnect auto-dismiss 1200ms · EspnConnect wedge 10 000ms.
- **Polling:** DraftRoom 15s (four-condition gate) · RecordPicks 15s (**ungated**) · trade job status (self-scheduling).
- **Persisted client state that leaks between runs:** `ftf.trios.speedMode` · `ftf:trades:fairness_on` · `ftf:tradecalc:v1` · `ftf_anchor_done_v1_<fmt>` · `ftf_pick_board_confirmed_v1` · `ftf.recpicks.queue.v1` · `ftf_rank_method_pref` · `ftf_inapp_feedback_v1` · `ftf_active_format` · onboarding state. Erase the simulator data volume between cells (`sim-run.sh` already does unless `--keep-data`).
- **Module-level once-per-session latches in TradesScreen** (`quicksetPromptShownThisSession`, `appleAskShownThisSession`, `adaptationMomentShownThisSession`, `guideS55/S7ShownThisSession`, `identityStripDismissedThisSession`) survive remounts — those states need a fresh app launch, not a re-navigation.
- **First-mount-only contracts:** Rank stack `initialRouteName`/`initialParams` (#244), `initialTab`, `showDraftTab`, `firstRun`, `NavigationContainer.linking`. A mid-session flag flip does NOT apply — relaunch.
- **Ambiguous/colliding testIDs:** `anchors.scope-all` (rookie segment vs ALL pill) · `free-agents.empty-text` (no-league vs no-results) · `matches.go-to-trades` (two empty states) · `rankmenu.*` (collapsed and expanded lists both render) · `league-summary.*` (both route registrations can be mounted at once).
- **Screens with no testIDs at all:** `TrendsScreen`, `ProfileScreen`.
