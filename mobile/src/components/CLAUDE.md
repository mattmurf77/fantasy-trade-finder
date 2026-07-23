# mobile/src/components/

Stateless / lightly-stateful reusable UI. No data fetching here — accept props.

| Component | Use |
|---|---|
| `PlayerCard` | Player tile with name, position, value |
| `TradeCard` | Give/receive trade summary card |
| `TierBadge`, `TierBin` | Tier label + drop-zone bin |
| `PositionChip` | QB/RB/WR/TE chip with color |
| `StrengthBar` | Horizontal value/strength meter |
| `TradeMeter` | Thin TRADE (tradeability) / GET (acquirability) bar, 0–1 score from `/api/rankings` — removed from Tiers tiles in 1.5.4 #100; kept available (payload fields still serialized) |
| `TradeSide` | Calculator: one side of a hand-built trade (players + add button) |
| `VerdictPanel` | Calculator: dual-board fairness verdict + gives/gets bars (demo mode) |
| `ConsensusVerdictCard` | Calculator: server-authoritative consensus verdict from /api/trade/evaluate (live mode) |
| `InLeagueCalculator` | Calculator "In league" mode: real opponent + rosters, two-board mutual-gain verdict (evaluate Mode B), carries Send in Sleeper |
| `SuggestionCard` | Calculator: tappable fair-package suggestion |
| `PlayerPickerModal` | Calculator: search + position-filter player picker |
| `OutlookSheet` | Bottom sheet for team outlook selection |
| `SendInSleeperButton` | Flagged-beta ("Send in Sleeper"): propose a trade to Sleeper directly; routes to connect / deep-link fallback. Self-gates to Sleeper leagues (#146): renders null when its `leagueId` is an imported ESPN league (platform check against `useSession.leagues`) — mounts never need their own gate |
| `VerifyAccountBanner` | Account-auth P1: quiet dismissible "Verify your account" strip floated above the tab bar (mounted once in RootNav → Main). Renders null unless the session is unverified AND (a verified controller exists OR enforcement is on); routes to SleeperConnect |
| `SteerSlider` | Settings: "We steer ↔ You steer" 5-dot ranking-method selector (one dot per ranking flow, guided → manual; Quick set leads since #119) |
| `EspnLinkSheet` | Flag-gated (`espn.link`) ESPN league link flow (feedback #115): league ID/URL input (+ manual espn_s2/SWID paste for private leagues) → "which team is yours?" → import summary (match rate, skipped players, read-only expectations). Opened from LeaguePicker's "Link an ESPN league" footer |
| `PlatformLinkSheet` | Zero-auth platform-aware link flow for MFL (`mfl.link`) + Fleaflicker (`fleaflicker.link`): `platform` prop; league URL/ID input (MFL adds a season year; Fleaflicker adds an optional find-by-email lookup) → "which team is yours?" → import summary. Same three steps as EspnLinkSheet, no cookie paste. Opened from LeaguePicker's per-platform footer buttons |
| `ProvenanceChip` | Onboarding item 4 (flag `onboarding.trades_first`): deck-level tick-label chip — "CONSENSUS VALUES" → "YOUR BOARD" once `ob.quicksetCompletedPositions` is non-empty (flare = informational highlight). `onPress` inert until item 7 wires the Quick Set tap-through |
| `SkeletonTradeCard` | Onboarding item 4: static (shimmer-free) first-run deck placeholder with a one-line status while pregenerated cards stream in |
| `CoachMark` | Onboarding guided layer (v2.1): one-time inline dismissible callout — never modal, never stacked; callers own shown-once persistence + `coach_mark_shown/dismissed` events |
| `IdentityConfirmStrip` | Onboarding item 4 (F5): first-run "Trading as @user — not you?" strip (avatar + ice action → sign-out confirm; X = session dismiss) |
| `QuickSetPromptCard` | Onboarding item 7 (flag `onboarding.quickset_prompt`): inline deck-slot prompt card ("These trades use consensus values.") — accept deep-links to onboarding-mode QuickSetTiers, dismiss = snooze (caller owns bookkeeping); explicit buttons, not swipeable (documented deviation) |
| `AppleSaveMomentSheet` | Onboarding item 8 (flag `onboarding.apple_save_moment`, ADR-006): save-moment Apple ask modal — honest cross-device framing only, official Apple button, "Not now" decline; bind flow mirrors Settings' handleLinkApple (conflict/linked/no-session outcomes) |
| `Toast` | Transient notification. Teardown S4 PRD-03: unflagged VoiceOver announce on show + Reduce Motion fade fallback; flag `ux.toast_v2` = warn/error hold ≥5s (holdMs 0 = sticky); optional `action` slot (label+callback, e.g. Undo — callers pass it only under `ux.swipe_undo`) |
| `PlayerContextMenu` | Teardown S3 PRD-02 (flag `ux.player_context_menu`): shared player long-press bottom sheet — header = player info, rows = per-surface commands (untouchable / swap) passed by the caller; also exports `LockGlyph` (untouchable visible-twin icon, local Svg pending Icon.tsx fold-in) |
| `HelpSheet` | Teardown S4 PRD-01 (flag `ux.help_surface`): lightweight help bottom sheet (2–3 sentences + "Read more" web link); exports `InfoButton` (ⓘ, 44pt effective target) |
| `TradeFinderModeBar` | Trade-Finding Hub (#156, flag `trades.finder_hub`): lateral quick-switch chip row (Guided · Team · Player · Calc) + "‹ Hub" back + mode title/hint, carried atop each focused trade-finder mode in `TradesScreen`. Presentational; host owns nav (guided/team/player switch in place via setParams, calc/hub navigate) |
| `TopBar` | Screen header |

## testID registry (UI-test harness — docs/plans/mobile-testing/lld.md Appendix A)

**Grammar:** `testID = <screen> "." <element> [ "." <qualifier> ]` — kebab-case segments; qualifier is a stable domain id (`player_id`, `league_id`, `user_id`, tier, position), **never a list index** (lists reorder; single exception: synthetic stable lists like demo partner chips). State is asserted via distinct IDs or visible copy, never encoded in an ID. Every element a Maestro flow references must carry one (`mobile/scripts/testid-lint.sh` cross-checks). **Adding a screen = adding its IDs** — part of the definition of done.

**Maintenance tax (pay in the same change):** element rename → update IDs + affected flows (~10–20 min); new screen → 1–2 flows + profile touch (~1–2 h); new feature flag → boundary case pair (~30 min).

**RN caveat:** containers with implicit `accessible={true}` (Touchables) swallow child IDs on iOS — fix with `accessible={false}` on the container. `DraggableFlatList` rows are the likeliest offender.

**Landed so far (S1 spike set, 2026-07-11):**
- SignIn: `signin.username-input` · `signin.continue-btn` · `signin.hint-btn` · `signin.demo-link` · `signin.error-text`
- Tab bar (`tabBarButtonTestID`): `tab.rank` · `tab.trades` · `tab.matches` · `tab.league`
- LeaguePicker: `leagues.row.<league_id>` (S1 part B surfaced the container-accessibility hazard live: the row Pressable swallows child Text from the tree — text-asserts fail while pixels render; id selectors are the fix)
- Verify banner (Main root): `main.verify-banner` · `main.verify-banner.verify` · `main.verify-banner.dismiss`
- SleeperConnect: `sleeperconnect.done` (post-capture success overlay)

**W1 smoke-set tranche (2026-07-12):**
- RankMenu: `rankmenu.quickset|trios|anchors|tiers|manual|trends` · RankHome: `rank-home.card.<quickset|trio|anchor|tiers|manual>` (quickset added by #119)
- Trios: `trios.card.a|b|c` (fixed trio slots — stable domain qualifier) · `trios.pos-tab.<pos>` · `trios.speed-toggle` · `trios.confirm-btn` · `trios.skip-btn`
- Trades: `trades.find-btn` · `trades.card-top` · `trades.like-btn` · `trades.pass-btn` · `trades.subnav.<trades|portfolio|calculator>` · `trades.progress-strip` · `trades.empty-text`
- Calculator: `calc.mode-tab.<league|live|demo>` · `calc.side-a-add` · `calc.side-b-add` · `calc.picker.search` · `calc.picker.row.<player_id>` · `calc.verdict` · `calc.clear-btn`
- Matches: `matches.segment.<mutual|awaiting>` · `matches.empty-text` · League: `league.hero` · Tiers (minimal): `tiers.list` · `tiers.pos-tab.<pos|all>` (`all` = the #132 cross-position All board) · `tiers.save-btn`
- Pass-through props added: chalkline `Button.testID`, `PlayerCard.testID`, `TradeSide.addTestID`
- OutlookSheet: `outlook.save-btn` (the sheet AUTO-OPENS on first Trades visit — flows dismiss it conditionally) · Picker: `calc.picker.done` (onPick adds without closing; Done closes — flows must tap it)

**ESPN league linking tranche (2026-07-12, flag `espn.link`):**
- LeaguePicker: `leagues.link-espn` · `leagues.link-mfl` · `leagues.link-fleaflicker` · EspnLinkSheet: `espn-link.input` · `espn-link.private-toggle` · `espn-link.s2-input` · `espn-link.swid-input` · `espn-link.continue` · `espn-link.team.<team_id>` · `espn-link.open` · `espn-link.error` · League tab: `league.espn-resync`
- PlatformLinkSheet (MFL/Fleaflicker): `platform-link.input` · `platform-link.year` (MFL) · `platform-link.email-toggle`/`platform-link.email`/`platform-link.email-lookup`/`platform-link.discovered.<league_id>` (Fleaflicker) · `platform-link.continue` · `platform-link.team.<team_id>` · `platform-link.open` · `platform-link.error` · Settings: `settings.link-platform`

**Apple entitlement tranche (2026-07-12, feedback #131):**
- SignIn: `signin.apple-btn` (Apple sign-in button)
- Settings: `settings.link-apple-btn` (Link Apple card button)
- TopBar: `topbar.settings` (Settings gear — shared chrome, sibling of reserved `topbar.bell`/`topbar.bell-badge`)

**Feedback batch tranche (2026-07-12, #130/#136):**
- Settings: `settings.close-btn` (modal header close Icon Button, #130) · `settings.link-espn` (flag `espn.link` CTA row → LeaguePicker with the ESPN sheet auto-opened, #130)
- Quick Rank (#136): `rankmenu.quickrank` (Rank action-sheet row) · `quick-rank.pos-tab.<pos>` · `quick-rank.chip.<player_id>` · `quick-rank.save-btn`

**Legacy-smoke repair tranche (2026-07-12, QA F-1..F-3):**
- FeedbackFAB: `feedback.fab` (floating capture button — its accessibilityLabel "Capture feedback" also text-matches in Maestro, so flows must use the id)
- FeedbackSheet: `feedback.severity.<bug|polish|idea>` · `feedback.note-input` · `feedback.save-btn`

**Free-agent finder tranche (2026-07-17, #143):**
- FreeAgentsScreen: `free-agents.pos-tab.<all|qb|rb|wr|te>` (filter pills) · `free-agents.list` (FlatList) · `free-agents.row.<player_id>` (dense PlayerCard) · `free-agents.empty-text` (no-league AND empty-list states)

**Quick-walk format + search tranche (2026-07-17, #137/#138):**
- QuickSetTiersScreen: `quick-set.format-toggle` (View hosting the SF/1QB FormatToggle — the segments themselves carry accessibilityLabel "<1QB PPR|SF TEP> scoring format", which is what Maestro text-matches) · `quick-set.search` (per-step name filter TextInput)
- QuickRankScreen: `quick-rank.format-toggle` · `quick-rank.search` (same pair, same semantics)

**Calculator suggestions tranche (2026-07-17, #78):**
- InLeagueCalculator: `calc.league-give-add` · `calc.league-receive-add` (TradeSide add buttons in the In-league mode; the picker/verdict IDs are shared with the calc screen)

**Onboarding trades-first tranche (2026-07-17, plan item 4, flags `onboarding.v2` + `onboarding.trades_first` / `onboarding.guided_layer`):**
- TradesScreen: `trades.provenance-chip` (deck-basis chip; disabled Pressable until item 7) · `trades.skeleton-card` (first-run streaming placeholder) · `trades.coach-mark.provenance` (guided-layer callout, tap dismisses) · `trades.identity-strip` (container) · `trades.identity-strip.switch` ("not you?" → sign-out confirm) · `trades.identity-strip.dismiss` (session hide)

**League rankings tranche (2026-07-17, #142/#144):**
- LeagueSummaryScreen: `league-summary.basis.<consensus|personal|redraft>` (basis chips — redraft is permanently disabled "(soon)") · `league-summary.team.<user_id>` (ranked team row → roster overlay) · `league-summary.roster-close` (overlay close Icon Button)
- LeagueScreen Explore rows: `league.rankings-row` (→ root-stack `LeagueSummary`) · `league.free-agents-row` (→ root-stack `FreeAgents`)

**League rankings bar-chart redesign tranche (2026-07-20, #169):**
- LeagueSummaryScreen: `league-summary.posfilter.<all|qb|rb|wr|te>` (chart position filter pills — single/multi select, reorders + rescales the stacked bars live) · `league-summary.roster-posfilter.<all|qb|rb|wr|te>` (drill-in overlay's own position filter). The team rows are now stacked bars but keep `league-summary.team.<user_id>`; basis + roster-close IDs unchanged

**Onboarding items 5–10 tranche (2026-07-17, flags `onboarding.*` per feature):**
- SignIn (item 5, `onboarding.landing`): `signin.apple-link` (quiet Apple re-entry text link) · `signin.error-demo-escape` (Sleeper-down "browse the sample league" escape)
- Trades (items 7/8/9/10): `trades.quickset-prompt` (+ `.accept` / `.dismiss`) · `trades.diff-banner` (post-Quick-Set regen receipt) · `trades.apple-sheet.<like|quickset_save|session2_banner>` (+ `trades.apple-sheet.signin` / `.decline`) · `trades.apple-session2-banner` (+ `.dismiss`) · `trades.share-liked` · `trades.trio-entry` (deck-exhausted CTA) · `trades.demo-bridge` · `trades.redraft-label`
- Rank stack (item 9, `onboarding.rank_routing`): `rank.more-ways` (QuickSetTiers header link → demoted RankHome chooser)

**Teardown Trades/engagement tranche (2026-07-19, W2B):**
- Trades: `trades.fairness-help` (flag `ux.help_surface`, ⓘ by the fairness toggle → HelpSheet) · `trades.outlook-set-banner` (flag `ux.outlook_inline_default`, no-inference set-outlook banner)
- Matches: `matches.go-to-trades` (flag `ux.empty_state_ctas`, both empty states) · `matches.matching-help` (flag `ux.help_surface`)
- Portfolio: `portfolio.open-settings` · FreeAgents: `free-agents.pick-league` (both flag `ux.empty_state_ctas`)
- Rank/Trios: `rank.unlock-payoff` (flag `ux.outlook_inline_default` pre-threshold caption) · `trios.info.<a|b|c>` (flag `ux.player_context_menu` ⓘ twins)
- Shared: `player-menu` (+ `player-menu.<action-key>`, keys `untouchable-add|untouchable-remove|swap`) · `help-sheet`

**Teardown growth/boards tranche (2026-07-19, W2D):**
- Board search (flag `ux.board_search`): `manual-ranks.search` · `tiers.search` (scroll-to + highlight inputs — the highlighted row reuses the active-drag ring, no ID of its own)
- League tab: `league.rookie-board-row` (flag `league.rookie_board_entry` → opens RookieDraftBoardSheet) · `league.whats-new` (flag `ux.whats_new`, CoachMark — tap dismisses)

**Teardown navigation tranche (2026-07-19, W2A):**
- TopBar bell sheet: `topbar.notif-row.<notification_id>` (tappable inbox row — only rendered with flag `notif.tap_routing_v2`; flag off the rows are inert Views with no ID)
- `rank.more-ways` note: with flag `ux.rank_tab_destination` on, the same ID appears in the header of EVERY rank surface (Trios/Anchors/Tiers/QuickSetTiers/QuickRank/ManualRanks/Trends) and opens the RankMenu sheet; flag off it remains QuickSetTiers-only → RankHome (unchanged)

Smoke flows: `mobile/.maestro/flows/smoke/01–11` (headers carry the TC ids). Full planned list: lld.md Appendix A (~90 IDs).

**Trade-Finding Hub tranche (2026-07-20, #156, flag `trades.finder_hub`):**
- TradeFinderHubScreen: `finder-hub.dna.edit` (opens OutlookSheet) · `finder-hub.card.<guided|team|player|calc>` (mode launcher cards) · `finder-hub.team-picker.<user_id>` (manager rows in the Specific Team sheet)
- TradeFinderModeBar (rendered in `TradesScreen` when opened as `TradeDeck` with a `mode` param): `trades.finder-mode.<guided|team|player|calc>` (quick-switch chips) · `trades.finder-mode.hub` (back to hub). The Trades/Portfolio/Calculator subnav is hidden in these launches

**League outlook-odds tranche (2026-07-23, #169, flag `outlook.odds` — DARK):**
- LeagueSummaryScreen: `league-summary.odds.section` (the gated playoff-picture container — present only when `outlook.odds` is on AND GET /api/league/outlook returns teams) · `league-summary.odds.beta-ribbon` (the load-bearing "Projected · preseason · beta" honesty label) · `league-summary.odds.source` (strength-source caption, e.g. "Preseason roster-value projection · 10,000 sims · top 6 make the playoffs") · `league-summary.odds.row.<roster_id>` (one team's projected playoff% / title% row, payload order). Flag off ⇒ none of these render and the endpoint is never called (it 404s while the modeling backend is dark). Basis toggle + dynasty-chart IDs unchanged.

**Guided avatar (The Analyst, flag `onboarding.guided_avatar`):** `analyst/` (six rn-svg pose components + `AnalystAvatar`; art source-of-truth = mockups/avatar-lab/analyst-poses.html) · `AnalystGuide.tsx` (RootNav-mounted overlay: scrim+cutout spotlight, bubble with in-bubble CTAs, ✕ skip / Skip-tour opt-out) · `analystScript.ts` (dialogue table = DATA; script doc: docs/plans/onboarding-conversion/guided-avatar-script.md). Guide testIDs: `guide.overlay` · `guide.bubble` · `guide.cta.<accept|dismiss>` · `guide.step-x` · `guide.skip-tour` · `guide.avatar.<pose>` · new targets `trades.card-body`
