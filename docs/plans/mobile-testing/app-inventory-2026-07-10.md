# Mobile App Inventory — Test Grounding (2026-07-10)

*Exhaustive review of the mobile app (v1.5.3, branch `trade-engine-v2`) taken as the grounding snapshot for the mobile-testing doc suite in this folder. Machine-generated from source review; regenerate when screens/flows change materially.*

App identity: `app.json` name "DTF - Dynasty Trade Finder", scheme `dtf`, `userInterfaceStyle: "dark"` (dark-mode only, no light theme), version 1.5.3, `newArchEnabled: true`. Backend: `https://fantasy-trade-finder.onrender.com` (Flask, Render free tier → cold-start 30–60s is a first-class UX concern everywhere).

---

## 1. Navigation map

**Root stack** (`RootNav.tsx`, `createNativeStackNavigator`, `headerShown:false` default):
- Screens: `SignIn`, `LeaguePicker`, `Main`, `Settings` (modal, header shown), `Profile` (`u/:username`, header shown), `FeedbackInbox` (modal, header), `SleeperConnect` (modal, header "Connect Sleeper").
- **Initial route logic** (`RootNav.tsx:132`): `!user → SignIn`; `user && (!league || !hasToken) → LeaguePicker`; `user && league && hasToken → Main`.
- Boot gate: `RootNav` renders a splash `ActivityIndicator` until `booted` prop true (`App.tsx` sets `booted = bootstrap()+loadCachedFlags() done AND fonts settled`).
- Nav theme = React Navigation `DarkTheme` overridden with chalkline `ink.ink0` bg.
- `SignIn` callbacks: `onSignedIn → replace('LeaguePicker')`, `onDemoStarted → replace('Main')`. `LeaguePicker`: `onLeaguePicked → replace('Main')`, `onSignOut → signOut()+replace('SignIn')`.
- `Main` renders `<TabNav/> + <PushPrimingModal/> + <FeedbackFAB activeScreen={...}/>` (FAB floats over every authed screen; `activeScreen` tracked via `onStateChange`).

**Deep-link scheme handling**:
- Two prefixes (`RootNav.tsx:143`): `Linking.createURL('/')` (= `dtf://…`) and `https://fantasy-trade-finder.onrender.com`.
- React-navigation `linking.config.screens`: `SignIn→signin`, `LeaguePicker→leagues`, `Main→app`, `Settings→settings`, `Profile→u/:username`.
- Separate manual handler `utils/deepLinks.handleDeepLink` (wired in `App.tsx` for both cold-start `getInitialURL` and warm `url` events): captures `?ref=<username>` → `useSession.setInvitedBy` (forwarded on next `/api/session/init` as `invited_by`); routes `/u/<username>` → `navigationRef.navigate('Profile')`.

**Tab navigator** (`TabNav.tsx`, `createBottomTabNavigator`), 4 tabs in order, hosted under a global `<TopBar/>`:
1. **Rank** — hosts `RankStackNav`. Tab tap is **intercepted** (`e.preventDefault()`) to open the **RankMenu** action sheet instead of navigating; icon carries a chevron-down to signal fan-out.
2. **Trades** — hosts `TradesStackNav`. Tab tap prefetches `['liked-trades', leagueId]`.
3. **Matches** — `MatchesScreen` directly. Tab tap prefetches `['matches','all']`.
4. **League** — `LeagueScreen` directly.

**Rank stack** (`RankStackNav`, `headerShown:false` except sub-screens): routes `RankHome`, `Trios` (=`RankScreen`), `Anchors` (=`PickAnchorScreen`), `Tiers`, `ManualRanks`, `Trends`. **Initial route** = `PREF_ROUTE[rankingMethodPref]` (trio→Trios, anchor→Anchors, tiers→Tiers, manual→ManualRanks) or `RankHome` when pref null. `initialRouteName` honored only on first mount (mid-session pref change applies next launch; the chooser routes immediately via `navigation.replace`). Sub-screens (Anchors/Tiers/ManualRanks/Trends) get a chalkline header + custom always-on `HeaderBack` control (fallback route `Trios`) — replaces unreliable native back (#51/#52).

**Trades stack** (`TradesStackNav`): `TradesHome` (=`TradesScreen`), `Portfolio` (header "Portfolio"), `TradeCalculator` (header "Calculator", `HeaderBack` fallback `TradesHome`).

**RankMenu action sheet** (bottom Modal): 5 rows — Trios, Pick Anchors, Tiers, Overall Ranks, Trends — each with subtitle; tap prefetches the destination query (Trios→`['trio','QB']`, Tiers→`['rankings','QB']`+`['tiers-status']`, ManualRanks→`['rankings','all']`, Anchors→`['anchor-pool',fmt]`; Trends not prefetched) then dispatches `CommonActions.navigate('Rank',{screen})`. Cancel button + backdrop dismiss.

---

## 2. Per-screen feature inventory

### SignInScreen
- Purpose: Sleeper username login via `POST /api/extension/auth`.
- Interactive: username `TextInput` (autoCapitalize none, returnKey "go", submit-on-enter); "Continue as @hint" pressable (prefilled from Keychain `getLastUsername`); "Connect →" primary button; conditional "Try the app on a sample league →" demo link (flag `landing.try_before_sync`).
- Data: `signIn` → `setUser` + `setLastUsername`(Keychain) + prefetch `getLeagues`→`setLeagues`. Smart-start path (flag `landing.smart_start_cta`): `resolveSmartStart` accepts league URL; Sleeper URL → resolves a roster owner via `getLeagueRosters`+`getLeagueUsers`; ESPN/MFL → soft error. Demo: `startDemoSession`.
- States: idle / busy (spinner in button) / demoBusy / error text / focused-border / hint-prefill first-run.
- Flags: `landing.smart_start_cta` (input placeholder + field hint changes), `landing.try_before_sync`.

### LeaguePickerScreen
- Purpose: pick a Sleeper league → 2-phase session init.
- Interactive: league row Pressables (`FlatList`), pull-to-refresh (`RefreshControl`), "Sign out" ghost button, "Try again" on error.
- Data: `getLeagues(user.user_id)`; on pick: **INIT-08 two-phase** — phase 1 `buildSessionInitBody` (blocking, ~2-3s), `setLeague` + navigate, phase 2 `submitSessionInit` detached (~5-10s, warns to console on fail).
- States: loading (with **slowLoad after 4s** → "Waking up server…30s" copy), error+retry, empty ("No 2026 NFL leagues found"), list. Per-row busy spinner while selecting; all rows disabled during a select.

### RankHomeScreen (Build-your-board chooser)
- Purpose: first-run Rank chooser; describes 4 flows guided→manual.
- Interactive: 4 method cards (Trios "easiest" featured / Anchors / Tiers / Manual), each with a HandsOnMeter (1–4 segments); "WE STEER↔YOU STEER" axis; mix note.
- On choose: `haptics.selection()`, `setRankingMethodPref(pref)` (persist), `setRankingMethod(pref)` POST fire-and-forget, `navigation.replace(route)`.
- States: static (no data fetch). No loading/error.

### RankScreen (Trios)
- Purpose: 3-player head-to-head swipe-ranking loop.
- Interactive: tap cards in preference order (tapping ranked card undoes it + later ranks); **"I AM SPEED" toggle** (auto-rank 3rd + auto-submit after 2 picks, persisted `ftf.trios.speedMode`); Confirm button (manual mode, 3 ranked); Skip button (ephemeral refetch, no player removal); position segmented switcher QB/RB/WR/TE (per-position count `count/threshold`); `FormatToggle` (SF/1QB); streak chip (tap→League tab); long-press card → info sheet (**flag `swipe.gesture_audit`**).
- Data: `getNextTrio(position)` (`['trio',position]`, staleTime 0, refetchOnMount always); `getProgress` (`['progress',leagueId,activeFormat]`); `getStreak`; `submitTrioRanking` mutation (local-merges progress cache; invalidates on threshold cross; sets streak; QC-compliment toast when `is_qc_trio` + correct order, **flag `swipe.qc_compliments`**).
- States: loading (3 skeleton cards), error+retry, unlock progress bar (per-position segmented), "Trade Finder unlocked" banner when `progress.unlocked`. Toasts: streak, save-fail rollback (clears selection + refetch trio), QC compliment. Haptics throughout.
- NOTE: swipe-gesture-to-rank was REMOVED (FB-72) — tap-only now.

### TiersScreen (Positional Tiers)
- Purpose: drag players into tier bins (Elite/Starter/Solid/Depth/Bench + Unassigned).
- Interactive: single **`DraggableFlatList`** (long-press 220ms to drag, `activationDistance:18`, `dragItemOverflow`, patched lib); per-tile chevron up/down (single tier step, #90); **multi-select mode** (Select toggle → tap chips → bulk Up/Down rank, Tier up/Tier down, quick `TierTargetChips`, Done); `FormatToggle`; position switcher; "Copy tier list from {otherFormat}" (destructive Alert confirm); "Reset to suggested" (destructive Alert → clear-only save); "Anchors" button → PickAnchor; **expand/collapse full-screen board (#81)**; Save button (per-position); sticky tier header overlay on scroll (viewability-driven, #67).
- Data: `getRankings(position)` (`['rankings',activeFormat,position]`), `getTiersStatus`, `getRisersAndFallers(30,50)` (for TileStats "You 30d"); `saveTiers`/`copyTiersFromFormat`/reset mutations; renders `TileStats`, `TradeMeter` (tradeability/acquirability), `TierBadge`, `TierStickyHeader`, `TierTargetChips`.
- States: loading spinner, error+retry, dirty-guard (unsaved edits survive background refetch), saving spinner. Toasts on save/copy/reset/drag-reject ("Tiered players can't move to Unassigned"). Haptics on every move.

### PickAnchorScreen (Anchors wizard)
- Purpose: value one player at a time in draft-pick terms → `POST /api/anchor/save`.
- Interactive: 8 anchor buttons (4/3/2/1 firsts, 1 2nd/3rd/4th, No value); "Skip — not sure"; "Start over" (when all done).
- Data: `getRankings(null)` snapshot (`['anchor-pool',fmt]`, **staleTime Infinity** so queue doesn't reshuffle mid-run); `saveAnchor` mutation; per-format resume via AsyncStorage `ftf_anchor_done_v1_<fmt>`. On unmount (if saved anything) invalidates rankings/progress/trio/tiers-status/trends.
- States: loading, error/empty ("No players to anchor"), current-player card w/ tier badge, "All anchored" done card, last-placed consequence line. Filters out generic PICK rows.

### ManualRanksScreen (Overall Ranks)
- Purpose: single editable overall rank board (drag + jump-to-rank).
- Interactive: `DraggableFlatList` (long-press 220ms, `activationDistance:5`); tap rank number → inline `TextInput` jump-to-rank (number-pad); position filter ALL/QB/RB/WR/TE (client-side).
- Data: `getRankings(null)` (`['rankings',activeFormat,'all']`); `reorderRankings` **debounced 600ms** (coalesces drags into one call; skips if <2 ids). Save-status indicator pill: pending/saving/saved(1.5s fade)/error.
- States: loading, error+retry, empty ("No rankings yet"). Haptics on drag/jump.

### TrendsScreen
- Purpose: risers/fallers (30d ELO movers) + easiest sells/buys (consensus gap).
- Interactive: position filter ALL/QB/RB/WR/TE; pull-to-refresh; per-section "Try again".
- Data: `getRisersAndFallers(30,10)` (`['trends','risers-fallers',30,10]`); `getContrarianGap(leagueId,5)` (`['trends','consensus-gap',leagueId,5]`, **enabled only w/ leagueId**). Renders `TrendBar`, `PositionChip`.
- States: per-section loading/error/empty (no-history / no-league / no-baseline / no-gaps). Explainer text (FB-94: "ranks are your own").

### TradesScreen (swipe deck)
- Purpose: streaming trade-finder swipe deck + controls.
- Interactive: **Tinder swipe** (`SwipableTopCard`, reanimated Pan, threshold 120px + velocity 200, rotate) — right=like, left=pass; **Check/X disposition buttons** (same as swipe); **"Bad trade?" flag** (feedback #85); **"Find a Trade"/"Find more trades"** button (streaming job); **Trade-fairness toggle** (custom slider, ON=balanced/0.75, OFF=mismatch-sort/0.5, persisted `ftf:trades:fairness_on`); **Outlook Edit** (`OutlookSheet`); `LeaguePill`→`LeagueSwitcherSheet`; subnav pills Trades/Portfolio(≥2 leagues)/Calculator; **Queue** button + queue footer bar + queue bottom-sheet + "Send All" (flag `trades.queue_2k`); **player swap** affordance (feedback #86 → `SwapPlayerSheet`, re-prices via evaluate Mode B); **untouchable** long-press on give-side (flag `trade.preference_lists`); **FB-47 targeting** direction toggle Trade away/Acquire + player picker + chips (flag `trade.finder_targeting`); `SendInSleeperButton`; "Hide" (dismiss running job).
- Data: `generateTrades`/`getTradeStatus` (self-scheduling poll, 800ms→4000ms backoff+jitter, MAX_POLL_FAILURES 4); `swipeTrade`(optimistic advance + rollback rewind), `flagBadTrade`, `getLikedTrades`; `getLeaguePreferences`, `getNewPartners`(flag), `getLeagueCoverage`, `getAssetPrefs`/`setAssetPref`, `getTradeValues`/`getLeagueRosters`/`getLeagueUsers`(swap+targeting), `copyTiersFromFormat`(gate), `getProgress`(gate), `evaluateTradeInLeague`(reprice).
- States: switching overlay (with 4s slowSwitch copy), **FormatGate** (single-format), running-job progress strip + Meter, deck peek (next card behind), banners (`NewPartnersBanner`, `InviteLeaguematesBanner` cold-start), empty states ("Hit Find a Trade" / "That's all for now" / no-fair-trades toast). Haptics on all actions.

### TradeCalculatorScreen
- Purpose: manual trade builder, 3 modes.
- Interactive: mode tabs — **In league** (only if `hasLeague`), **Real values** (live), **Demo league**; format chips 1QB/SF (live); partner chips (demo); Side A/B `TradeSide` add/remove via `PlayerPickerModal`; Share trade; Clear trade; suggestion/add-on cards (tap-to-apply).
- Data: live → `getTradeValues` + `evaluateTrade` (**debounced 250ms**, no auth); demo → local `tradeCalcMath` over `tradeCalcMock`; league → delegates to `InLeagueCalculator`. Draft persisted `ftf:tradecalc:v1`.
- States: live loading/error+retry+"switch to demo"; `ConsensusVerdictCard` (live) / `VerdictPanel` (demo dual-board) / `LeagueVerdict` (in-league); one-sided value readout; no-suggestions text.

### MatchesScreen
- Purpose: cross-league mutual matches + awaiting-them inbox.
- Interactive: segment toggle Mutual/Awaiting; league filter chip row (horizontal scroll, All + per-league + extras); pull-to-refresh; Dismiss (mutual, optimistic + rollback); untouchable long-press (flag `trade.preference_lists`); `SendInSleeperButton` via TradeCard `showSend`. Deep-linked from League tiles via `route.params.segment/at`.
- Data: `getAllMatches` (`['matches','all']`), `getAwaitingTrades` (`['awaiting-trades']`, lazy on segment), `dismissMatch`, `getAssetPrefs` (useQueries per league).
- States: skeleton (3 tiles), error, empty (per-segment/per-filter), toasts. Renders `TradeCardComp` variant match/swipe.

### LeagueScreen
- Purpose: league home dashboard.
- Interactive: hero card → `LeagueSwitcherSheet`; joined chip → members Modal overlay; Matches tiles → Matches tab (segment deep-link); "Switch league" button; pull-to-refresh (refetches all).
- Data: `getLeagueSummary`, `getLeagueCoverage`, `getLeagueMembers`, `getLeagueMemberUnlockStates`(flag `league.unlock_badges_per_member`), `getActivityFeed`(flag `league.activity_feed`), `getContrarianLeaderboard`. Renders `ActivityFeed`, `ContrarianLeaderboard`, `LeaderboardsSection`.
- States: no-league fallback, per-section pending skeletons ("—"), coverage Meter, member overlay w/ unlock/join chips.

### PortfolioScreen
- Purpose: cross-league exposure (which players owned across leagues).
- Interactive: pull-to-refresh; horizontal tier-chip strips per player.
- Data: `getPortfolio(leagueIds)` (`['portfolio', ids]`, **enabled only ≥2 leagues**, FB-48 season-scoped).
- States: gate ("Connect a second league"), loading, error, empty ("No exposure yet"), list. Tier chips show "Pool" (backend doesn't emit per-league tier).

### ProfileScreen
- Purpose: read-only public profile (`/u/<username>` deep link).
- Interactive: none (pure display, ScrollView).
- Data: `getPublicProfile` (`['public-profile',username]`, **flag `profiles.public_pages`**, no auth; retry skips 404/400).
- States: flag-off ("coming soon"), missing-username, loading, 404 "Profile not found", error, content (hero avatar, ranks-by-position, tiers snapshot, contrarian takes higher/lower).

### SleeperConnectScreen
- Purpose: WebView Sleeper login to capture JWT for Send-in-Sleeper.
- Interactive: in-app `WebView` (Sleeper's own login page); injected JS polls `localStorage['token']` every 800ms, posts token out once.
- Data: `linkSleeperToken(token)` → `navigation.goBack()`.
- States: browsing / linking (overlay "Connecting…") / error ("Couldn't connect — try again"). **Hazard: real external WebView, network + Sleeper auth dependent.**

### FeedbackInboxScreen
- Purpose: review/share captured feedback (Settings→Test feedback).
- Interactive: Retry sync (when unsynced>0), Share (markdown to OS share sheet), Clear (Alert confirm), long-press row → Delete (Alert).
- Data: `useFeedback` store (AsyncStorage `ftf_inapp_feedback_v1`) + `getMyFeedback` for operator statuses; hides `closed` notes.
- States: empty, per-row sync badge (Synced/Pending/Failed) + operator status line + "unread" dot when operator responded.

### PlaceholderScreen
- Purpose: stub for unfinished routes (props title/note). Not registered in current nav. Static.

---

## 3. Cross-cutting flows

**(a) First-run onboarding**: `SignIn` (`signIn`→`setUser`, prefetch leagues) → `replace('LeaguePicker')` → pick league (2-phase `buildSessionInitBody`→`setLeague`→`replace('Main')`, `submitSessionInit` detached) → Rank tab opens at `RankHome` chooser (pref null) → user picks method → `setRankingMethodPref` persists + `navigation.replace(route)`; next launch RankStack opens straight to that route. Demo path: `startDemoSession`→`replace('Main')`, skips picker. `useLeagueFormatDefault` (mounted in RootNav) applies league's detected format after league set.

**(b) 3-player matchup ranking**: `RankScreen` `getNextTrio(position)` → tap-order selection → `submitTrioRanking` → local progress merge + `['trio']` invalidate → next trio. Speed mode auto-submits after 2 picks. Backend selects trios (QC trios flagged via `is_qc_trio`+`qc_expected_order`). **Randomness: trio contents are server-chosen — non-deterministic across runs.**

**(c) Trade finder w/ targeting (FB-47)**: flag `trade.finder_targeting` reveals direction toggle + `PlayerPickerModal` (Trade away=own roster, Acquire=leaguemate rosters w/ @owner badges). Selected → `pinnedGive`/`pinnedReceive` chips (session-local, cleared on league switch) → `generateTrades({pinned_give_players, pinned_receive_players})`. Position-level targeting lives in `OutlookSheet`. `TierTargetChips`/`SteerSlider` are NOT part of finder targeting (SteerSlider=Settings ranking-method; TierTargetChips=Tiers multi-select).

**(d) Trades swipe deck + untouchable + queue**: `SwipableTopCard` (reanimated) or Check/X → `advance('like'|'pass')` → `swipeTrade` (optimistic, rollback-rewind on error). Untouchable: long-press give-side player → `setAssetPref(...,'untouchable')` (flag `trade.preference_lists`). Queue: `handleQueue`→`useTradeQueue.enqueue` (AsyncStorage `ftf_trade_queue_<user_id>`) → footer bar → "Send All" `sendAll` opens each `sleeper_url` with 500ms stagger via `Linking.openURL` (flag `trades.queue_2k`).

**(e) Manual calculator all modes**: mode tabs. Live: `getTradeValues`+`evaluateTrade` (debounced 250ms, public). Demo: local math over mock. League: `InLeagueCalculator` (`getLeagueRosters`+`getLeagueCoverage`+`getTradeValues`, opponent picker w/ unranked dot, `evaluateTradeInLeague` Mode B debounced 250ms → `LeagueVerdict` two-board mutual-gain, carries `SendInSleeperButton`). **TradeMeter is NOT in the calculator** — it's a Tiers tile bar (tradeability/acquirability from `/api/rankings`).

**(f) Send-in-Sleeper state machine**: `SendInSleeperButton` (flag `trade.send_in_sleeper`, else null). States idle/checking/sending/sent. `onPress`: if no league/opponent→`openInSleeper` deep-link; else `getSleeperLinkStatus`→ if connected `confirmSend`→`proposeTradeToSleeper`; if not→Alert→`goConnect`→`SleeperConnect` webview. On screen `focus` return (`awaitingLinkRef`), re-checks link status and Alerts result. Error codes branched: `sleeper_not_linked/expired`→reconnect, `sleeper_rejected`, `sleeper_unconfigured/feature_disabled`, `roster_not_found`. Token stored server-side via `linkSleeperToken`; session token via `useSession`/SecureStore `ftf.sessionToken`.

**(g) Pick anchor wizard**: reached from RankMenu, RankHome, or Tiers "Anchors" button. `getRankings(null)` snapshot (staleTime Infinity) → per-player 8-button pick → `saveAnchor` → resume set persisted `ftf_anchor_done_v1_<fmt>` → on unmount invalidate downstream caches.

**(h) Feedback FAB/sheet/inbox**: `FeedbackFAB` (mounted in RootNav over all authed screens, pre-fills `activeScreen`) → `FeedbackSheet` (severity bug/polish/idea, screen input, note; `useFeedback.add`→AsyncStorage + background POST `/api/feedback`) → `FeedbackInboxScreen` (Settings→Test feedback; retry sync, share markdown, clear, delete; operator statuses via `/api/feedback/mine`). All TestFlight-era, meant to be removed at public release.

**(i) Push priming + notifications**: `usePushNotifications` (mounted RootNav, gated on `progress.unlocked===true` via `pushEnabled`). Permission deferred: if `undetermined` → `usePushPriming.request(handler)` → `PushPrimingModal` ("Enable notifications"/"Maybe later") → on accept `requestPermissionsAsync`+`getExpoPushTokenAsync`+`registerDeviceForPush`. Foreground/tap listeners always wired post-signin; taps route by `data.type` (matchKinds→Matches, leagueKinds→League, rankKinds→Rank). In-app feed → `useNotifications` (in-memory, cap 50) → `TopBar` bell badge + sheet. Notification prefs in `SettingsScreen`.

---

## 4. API endpoint inventory

**client.ts** `apiBaseUrl` resolution: `Constants.expoConfig.extra.apiBaseUrl` → `manifest2.extra.apiBaseUrl` → hardcoded `https://fantasy-trade-finder.onrender.com`. Attaches `X-Session-Token` (SecureStore `ftf.sessionToken`) unless `skipAuth`, plus `X-Device/X-OS-Version/X-App-Version/X-User-TZ`. **Timeouts**: default 15s, slow-POST 30s for `/api/session/init` & `/api/trades/generate`. **Retry**: GET-only, statuses 502/503/504, MAX_RETRIES 2, backoff 400ms→1200ms ±20% jitter; NO_RETRY paths: `/api/session/init`, `/api/trades/generate`, `/api/rank3`, `/api/tiers`, `/api/trades/swipe`. 401 → clears token only if the sent token still matches stored (FB-45 guard). Timeout error message "Server is waking up — please retry."

**auth.ts**: `POST /api/extension/auth` (skipAuth), `POST /api/session/init` (slow), `GET /api/session/ping`, `POST /api/session/demo` (skipAuth), `POST /api/league/parse-url` (skipAuth), `GET /api/profile/:username` (skipAuth).

**sleeper.ts** (all via FTF backend proxy, NOT direct): `GET /api/sleeper/leagues/:userId`, `GET /api/sleeper/rosters/:leagueId`, `GET /api/sleeper/league_users/:leagueId`, `GET /api/sleeper/players/warm` (warmed-once-per-launch guard).

**league.ts**: `GET/POST /api/league/preferences`, `GET/POST /api/league/asset-prefs`, `GET /api/league/coverage`, `GET /api/league/summary`, `GET /api/league/members`, `GET /api/league/format-stats`, `POST /api/tiers/copy-from-format` (X-Scoring-Format header), `GET /api/league/member-unlock-states`, `GET /api/league/activity`, `GET /api/league/contrarian`, `GET /api/portfolio`, `POST /api/league/parse-url`. `getNewPartners` derives client-side from activity feed.

**rankings.ts**: `POST /api/scoring/switch`, `GET /api/me/streak`, `GET /api/trio`, `POST /api/rank3`, `POST /api/trio/skip` (unused by UI), `GET /api/rankings/progress`, `GET /api/rankings`, `POST /api/rankings/reorder`, `POST /api/tiers/save`, `POST /api/anchor/save`, `GET /api/tier-config`, `GET /api/tiers/status`, `POST /api/tiers/dismiss`, `POST /api/ranking-method`, `GET /api/rookies`, `GET /api/trends/risers-fallers`, `GET /api/trends/consensus-gap`. Active format mirror in AsyncStorage `ftf_active_format`; per-call `X-Scoring-Format` header.

**trades.ts**: `POST /api/trades/generate` (slow, job), `GET /api/trades/status`, `GET /api/trades`, `POST /api/trades/swipe`, `POST /api/trades/flag`, `GET /api/trades/matches/all`, `GET /api/trades/matches`, `POST /api/trades/matches/:id/disposition`, `POST /api/trades/matches/:id/dismiss`, `GET /api/trades/liked`, `GET /api/trades/awaiting`. Backend returns bare arrays; adapters normalize.

**calc.ts** (public for live mode): `GET /api/trade/values?scoring_format=` (skipAuth), `POST /api/trade/evaluate` (skipAuth for live Mode A; **authed** for in-league Mode B w/ `league_id`+`opponent_user_id`).

**sendInSleeper.ts**: `GET /api/sleeper/link`, `POST /api/sleeper/link`, `DELETE /api/sleeper/link`, `POST /api/trades/propose`. **Requires Sleeper write token.**

**flags.ts**: `GET /api/feature-flags`. **notifications.ts**: `GET /api/notifications`, `POST /api/notifications/read`, `POST /api/notifications/read-all`, `POST /api/notifications/register-device`, `GET/PUT /api/notifications/prefs`. **leaderboard.ts**: `GET /api/leaderboard`. **feedback.ts**: `POST /api/feedback`, `GET /api/feedback/mine`.

**All Sleeper access is proxied through the FTF backend — no direct `api.sleeper.com`/CDN calls anywhere in the client** (only the SleeperConnect WebView touches sleeper.com).

---

## 5. State & persistence

**useSession** (zustand): `{user, league, leagues, hasToken, activeFormat: '1qb_ppr'|'sf_tep'|null, formatExplicit, switching, isDemo, invitedBy, rankingMethodPref: 'trio'|'anchor'|'tiers'|'manual'|null}`. Persistence: AsyncStorage `sleeper_user`, `sleeper_league`, `sleeper_leagues`, `ftf_rank_method_pref`; session token in **SecureStore** `ftf.sessionToken`; last username SecureStore `ftf.lastUsername`. `bootstrap()` hydrates locally (no network). `revalidateSession` (FB-45) re-mints server session on boot + foreground (throttled 60s). `switchLeague` re-runs `initLeagueSession` + invalidates portfolio/matches/awaiting/rankings/progress/streak/tiers-status caches.

**react-query persistence** (`App.tsx`): `PersistQueryClientProvider` + AsyncStorage persister, maxAge 30min, dehydrates only `{rankings, progress, matches, tiers-status, liked-trades}`. Defaults: staleTime 30s, gcTime 30min, retry 1, refetchOnReconnect true, refetchOnWindowFocus false (bridged to AppState via focusManager). Active-format mirror: AsyncStorage `ftf_active_format`.

**Feature flags** (`useFeatureFlags`): source `GET /api/feature-flags`; cached AsyncStorage `feature_flags_v1`; `loadCachedFlags` (boot, local) + `revalidateFlags` (detached). **13 flag-gated surfaces**: `landing.smart_start_cta`, `landing.try_before_sync`, `league.activity_feed`, `league.unlock_badges_per_member`, `profiles.public_pages`, `swipe.gesture_audit`, `swipe.qc_compliments`, `trade.finder_targeting`, `trade.preference_lists`, `trade.send_in_sleeper`, `trade_math.human_explanations`, `trades.new_partners_alerts`, `trades.queue_2k`.

**Trade queue** (`useTradeQueue`): AsyncStorage `ftf_trade_queue_<user_id>`, per-user. **Other stores**: `useFeedback` (AsyncStorage `ftf_inapp_feedback_v1`), `useNotifications` (in-memory, cap 50), `usePushPriming` (ephemeral). Screen-local persisted prefs: `ftf.trios.speedMode`, `ftf:trades:fairness_on`, `ftf:tradecalc:v1`, `ftf_anchor_done_v1_<fmt>`.

---

## 6. Test-relevant hazards

- **Dark-mode only**: `userInterfaceStyle: "dark"` — snapshot baselines must be dark.
- **`__DEV__` paths**: Sentry "no DSN" info log dev-only; `tracesSampleRate` 1.0 dev / 0.2 prod. No dev-only UI branches found.
- **Sentry ACTIVE in builds** (DSN in `app.json` extra; wraps App root, nav integration, spans around trio.submit/tiers.save/rankings.reorder). Test runs send events unless disabled/tagged.
- **Animations/gestures likely to flake**:
  - `SwipableTopCard` — reanimated Pan; swipe needs 120px displacement AND velocity >200 (slow programmatic swipes fail — prefer Check/X buttons in automation).
  - `DraggableFlatList` (Tiers `activationDistance:18` + long-press 220ms, patched lib; ManualRanks `activationDistance:5` + 220ms) — drag automation fragile; prefer chevron/jump-to-rank/multi-select alternatives.
  - Reanimated 4 + worklets; gesture-handler root.
- **Timers/debounces**: calculator evaluate 250ms (both modes), ManualRanks save 600ms, trade-status poll 800→4000ms + jitter (deck streams in asynchronously — assert with waits, not fixed timing). SignIn/LeaguePicker/Trades **4s slowLoad/slowSwitch** copy switch.
- **Cold-start dependency**: Render free tier 30–60s; warm ping on boot; player-cache warm gating on `/api/session/init`. Generous timeouts needed against prod-like backends; local Flask avoids this.
- **Nondeterminism**: trio contents server-chosen; trade deck order depends on backend job + fairness re-sort; `Math.random()` only in retry/poll jitter + notification id fallback (not UI-visible).
- **OTA/updates**: EAS projectId configured; no `updates` block — no auto-OTA surprises.
- **WebView** (`SleeperConnectScreen`): live `sleeper.com/login` + injected JS polling — external, real auth, unmockable; exclude from simulator automation.
- **Push**: `Device.isDevice` guard — simulators can't get real APNs (note: `xcrun simctl push` can inject payloads); permission prompt deferred behind unlock; priming modal only on `undetermined`.
- **Orphans**: `RookieDraftBoardSheet` + `getRookies` exist but are wired to no screen — no test surface. `TradeMeter` IS wired (TiersScreen tiles).

---

## 7. Feature list for test-case enumeration

Legend fixtures: **L**=league fixture, **O**=opponent-with-rankings fixture, **W**=Sleeper write token, **P**=push permission, **F**=feature flag.

1. Sign in with Sleeper username → `/api/extension/auth` (SignIn)
2. "Continue as @hint" prefill from Keychain (SignIn)
3. Smart-start league-URL sign-in (SignIn) — F `landing.smart_start_cta`
4. ESPN/MFL "coming soon" soft error (SignIn) — F
5. Try demo / sample league (SignIn) — F `landing.try_before_sync`
6. League picker list + pull-to-refresh (LeaguePicker) — L
7. Pick league → 2-phase session init + optimistic nav (LeaguePicker) — L
8. Cold-start "waking up server" copy after 4s (LeaguePicker/Trades) — L
9. Sign out (LeaguePicker/Settings)
10. Build-your-board chooser method pick + persist pref (RankHome)
11. Rank tab action-sheet fan-out menu (TabNav)
12. Trios tap-order ranking + submit (RankScreen) — L
13. "I AM SPEED" auto-submit toggle, persisted (RankScreen)
14. Skip trio (ephemeral refetch) (RankScreen)
15. Position switcher + per-position unlock progress (RankScreen)
16. SF/1QB FormatToggle (RankScreen/Tiers) — L
17. Streak chip → League tab (RankScreen)
18. QC-compliment toast (RankScreen) — F `swipe.qc_compliments`
19. Long-press player info sheet (RankScreen) — F `swipe.gesture_audit`
20. Trade Finder unlock banner + gating (RankScreen) — L
21. Tiers drag-to-bin reorder (TiersScreen) — L
22. Per-tile chevron tier step (TiersScreen) — L
23. Multi-select bulk move (rank/tier/quick-to-tier) (TiersScreen) — L
24. Copy tiers from other format (destructive) (TiersScreen) — L
25. Reset tiers to suggested (destructive) (TiersScreen) — L
26. Expand/collapse full-screen board (TiersScreen)
27. Sticky tier header on scroll (TiersScreen)
28. Save tiers (TiersScreen) — L
29. TileStats You/Consensus + TradeMeter bars (TiersScreen) — L,O
30. Pick Anchor wizard 8-button valuation + save (PickAnchor) — L
31. Anchor resume/skip/start-over (PickAnchor)
32. Overall Ranks drag reorder (ManualRanks) — L
33. Jump-to-rank number edit (ManualRanks) — L
34. Position filter ALL/QB/RB/WR/TE (ManualRanks/Trends)
35. Debounced save + status pill (ManualRanks) — L
36. Trends risers/fallers 30d (Trends) — L
37. Trends easiest sells/buys consensus gap (Trends) — L,O
38. Find a Trade streaming job + progress strip (Trades) — L
39. Swipe like/pass gesture (Trades) — L
40. Check/X disposition buttons (Trades) — L
41. Trade-fairness toggle persisted (Trades) — L
42. Bad-trade flag (Trades) — L
43. Player-swap sheet + reprice (Trades) — L,O
44. Untouchable long-press mark/unmark (Trades/Matches) — L, F `trade.preference_lists`
45. FB-47 finder targeting toggle + picker + chips (Trades) — L, F `trade.finder_targeting`
46. Human-readable trade reasons (TradeCard) — F `trade_math.human_explanations`
47. Outlook sheet edit (Trades) — L
48. League switcher pill/sheet (Trades/League) — L
49. New-partners banner (Trades) — L, F `trades.new_partners_alerts`
50. Invite-leaguemates cold-start banner (Trades) — L
51. FormatGate single-format copy/manual (Trades) — L
52. Trade queue enqueue/dequeue + footer + Send All (Trades) — L, F `trades.queue_2k`
53. Send in Sleeper propose flow + link check (Trades/InLeague/Matches) — L,O,W, F `trade.send_in_sleeper`
54. Sleeper WebView token capture (SleeperConnect) — W
55. Calculator Real-values mode + debounced evaluate (TradeCalc)
56. Calculator Demo-league dual-board mode (TradeCalc)
57. Calculator In-league Mode B two-board verdict (TradeCalc/InLeagueCalculator) — L,O
58. Calculator player picker + suggestions/add-ons (TradeCalc)
59. Calculator share/clear + draft persistence (TradeCalc)
60. Matches mutual segment + dismiss (Matches) — L,O
61. Matches awaiting-them segment (Matches) — L,O
62. Matches league filter chips + pull-to-refresh (Matches) — L
63. Matches deep-link from League tiles (Matches/League) — L
64. League summary hero + team/joined chips (League) — L
65. League members overlay + unlock chips (League) — L, F `league.unlock_badges_per_member`
66. League activity feed (League) — L, F `league.activity_feed`
67. Contrarian ranks leaderboard (League) — L,O
68. Coverage meter (League) — L
69. Leaderboards section (League) — L
70. Portfolio cross-league exposure + gate (Portfolio) — L (2+)
71. Public profile deep link `/u/<user>` (Profile) — F `profiles.public_pages`
72. Connect another Sleeper league (Settings) — L
73. Switch league (Settings) — L
74. Ranking-method SteerSlider (Settings)
75. Notification prefs toggles + quiet hours (Settings)
76. Notifications bell badge + sheet (TopBar) — P
77. Push priming modal enable/later (PushPrimingModal) — P
78. Push tap-routing to tab by type (usePushNotifications) — P
79. Feedback FAB → capture sheet (FeedbackFAB/Sheet)
80. Feedback inbox retry/share/clear/delete + operator status (FeedbackInbox)
81. `?ref=` referral capture on deep link (deepLinks)
82. Session revalidate on foreground/boot (useSession/FB-45) — L
