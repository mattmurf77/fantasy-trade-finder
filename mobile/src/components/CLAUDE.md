# mobile/src/components/

Stateless / lightly-stateful reusable UI — no data fetching, accept props. MAP, not a changelog. History: `git log -- <this file>`, `living-memory/CHANGELOG.md`. testID grammar/registry: `docs/plans/mobile-testing/lld.md` Appendix A (checked by `mobile/scripts/testid-lint.sh`).

| Component | Use |
|---|---|
| `PlayerCard` | Player tile: name, position, value. `denseSingleLine` (#299) — opt-in 32pt single-line variant of the `dense` row, used **only** by the League drill-in roster panel. Drops line 2 and renders the tier badge in the right cluster, left of `posRank`. **Incompatible with `statsSlot`** (there is no line 2 to hold it) and unsafe for any caller passing `onPress`: 32pt is below the 44pt touch minimum, and the League tiles being inert is what makes it legal there. Tiers board and FA list keep the 60pt two-line row. Pinned by `mobile/tests/check-league-drill-in.js` |
| `TradeCard` | Give/receive summary card; swipe-deck variant adds keep-side, edit-in-calc, remove-asset, hide-strength/hide-lock props, and `disposition` (#169: Pass/Like render inside the card beneath the player tiles — top deck card only, never peek/match/featured; vocabulary + ordering are `docs/cross-client-invariants.md` § Deck disposition) |
| `FeaturedTradeWindow` | Read-only featured-trade card for single-pin finder mode, back-chip history stack; exports `assetIdeaKey()` |
| `AssetIdeasPanel` | Grouped Upgrade/Lateral/Downgrade ideas for the pinned asset (flag `trade.asset_ideas`); tap loads into `FeaturedTradeWindow`. #317: with the pinned deck FINISHED (summary/exhausted card in the slot), a tile tap re-presents the featured window with that idea — the deck yields the slot only on the user's own gesture (host `pinIdeaResumed`, pinned by `check-single-pin-actions.js` 9a/9b); while the window is hidden the host nulls `featuredKey`, so no row is ever tagged "IN WINDOW"/inert against an off-screen window |
| `RookieScopeControl` | Shared All/Rookies toggle on every rank surface (flag `ranks.rookie_subset`); also exports `RookieScopeEmpty` |
| `TierBadge`, `TierBin` | Tier label + drop-zone bin |
| `PositionChip` | QB/RB/WR/TE chip with color |
| `StrengthBar` | Horizontal value/strength meter |
| `TradeValueBar` | Pick-denominated "Dynasty value swing" bar on every trade surface; verdict text behind a "Why?" disclosure |
| `TradeMeter` | Thin TRADE/GET score bar (0–1); not shown on Tiers tiles, fields still serialized |
| `TradeSide` | Calculator: one side of a built trade; marks owned picks with `MemberEnteredMarker` (flag `picks.assign_tradeable`) |
| `VerdictPanel` | Calculator: dual-board fairness verdict + gives/gets bars (demo mode) |
| `ConsensusVerdictCard` | Calculator: server-authoritative consensus verdict (live mode) |
| `InLeagueCalculator` | Calculator "In league" mode: real opponent/rosters, two-board verdict, eveners, lineup before/after, prefill. Fires `lineup_impact_unavailable` when the server omits `starter_impact` and both sides carry players; `platform` is read from the session league cache, **never** from the league id's shape |
| `SuggestionCard` | Calculator: tappable fair-package suggestion |
| `EvenerRows` | Calculator: one-tap balance rows from evaluate's `eveners`; also serves one-sided "Trade options" |
| `AdjustmentsDisclosure` | Calculator: collapsed "Value adjustments" itemization; "off" note under stud-tax `off` |
| `ShareTradeImage` | Calculator: captures a trade card to PNG for the share sheet; text fallback on failure |
| `PlayerPickerModal` | Calculator: search + position-filter picker, optional Suggested rows |
| `OutlookSheet` | Team-outlook sheet; reached from TradesScreen (hub no longer mounts it) |
| `OutlookBiasReceipt` | Deck bias summary (flag `trade.outlook_direction`); Change opens `TradeDnaSheet`. #315: optional host-composed `details` prop renders a dim 13pt second row (chasing/shopping · intent lane · untouchables count — never team scope or specific players, which are the #314 filters directly below); ≤2 rows total, empty ⇒ byte-identical single row. testIDs `trades.outlook-receipt`, `.change`, `.details`. Pinned by `mobile/tests/check-trades-banner-region.js` |
| `TradeDnaSheet` | Trade DNA editor as a sheet over the guided deck: outlook + Chasing/Shopping + untouchables, autosaves every tap |
| `SendInSleeperButton` | Flagged-beta trade send AND the single platform router for the send action. **Platform-generic gate (P0-6 + Send-in-MFL):** Sleeper leagues send (pre-send validates via `/api/trades/validate`); mfl with `trade.send_in_mfl` ON → `SendInMflButton`; espn with `espn.send` ON → `SendInEspnButton` (both live in release since 2026-08-12, D-026); mfl/espn flag-OFF / Fleaflicker get a stated reason + `Copy trade` — never null (structural test: `mobile/tests/check-send-button-platform.js`). The reason copy (`tradeText.NO_SEND_REASON`) names the platform and never claims "Sleeper-only" (#309 — it renders only in kill-switch/cold-flag/Fleaflicker states, where that claim is false; pinned by `check-trade-text.js` cases 15+29). Fails **open** to Sleeper on an uncached league id (#146 contract). Requires `surface` ∈ `deck\|match\|awaiting\|calculator` — it rides the `sleeper_send_*` events. testIDs: `trades.send-sleeper-btn`, `send-in-sleeper.unavailable`, `send-in-sleeper.copy` |
| `SendInMflButton` | Flagged (`trade.send_in_mfl`) MFL trade proposal via MFL's documented import API — mounted ONLY by `SendInSleeperButton`'s platform branch, never directly; same confirm/pre-flight UX; requires `surface` (P0-7 parity — carried, no MFL client events registered yet). Lazy auth (send-auth fix): up-front `GET /api/mfl/auth-link` — unlinked (and 409 `mfl_not_connected`/`mfl_auth_expired`) opens the in-flow `MflSignInSheet`, which resumes the send on success; only league-level `mfl_not_linked`/`mfl_franchise_unknown` still route to LeaguePicker. Asset arrays are mixed players + picks, passed verbatim — the server owns pick encoding and the never-drop-an-asset hard block. testID `trades.send-mfl-btn` |
| `SendInEspnButton` | Flagged (`espn.send` — OFF and absent from `config/features.json` until the auth probe clears, D-026: dark everywhere today) ESPN trade proposal via ESPN's undocumented write API — mounted ONLY by `SendInSleeperButton`'s platform branch, never directly; same confirm UX as the MFL twin; requires `surface`. Lazy auth (send-auth fix): up-front `GET /api/espn/link` — unlinked (and 409 `espn_not_connected`/`espn_auth_expired`) navigates in-flow to `EspnConnect` with `reason:'send'` (Sleeper-style tap-again loop via a focus re-check); only league-level `espn_not_linked`/`espn_team_unknown` still route to LeaguePicker. PLAYERS ONLY — the server hard-blocks any pick asset (422 `espn_pick_unsupported`) and any crosswalk miss (422 `espn_asset_unmapped`); nothing is silently dropped. testID `trades.send-espn-btn` |
| `MflSignInSheet` | Focused in-flow MFL sign-in sheet (send-auth lazy flow): username/password → `POST /api/mfl/auth-link` (stores the MFL cookie, verifies the session), then `onSignedIn` resumes the caller's action. No league list, no import step — `PlatformLinkSheet` keeps the full linking flow. Password transient, never persisted. testIDs `mfl-signin.username/password/submit/cancel/error` |
| `VerifyAccountBanner` | Dismissible "Verify your account" strip above the tab bar, unverified sessions only |
| `SteerSlider` | Settings: 5-dot "We steer ↔ You steer" ranking-method selector |
| `EspnLinkSheet` | Flag-gated (`espn.link`) link flow: ID/URL + cookie paste, or WebView sign-in (`espn.webview_capture`) → team match → summary |
| `PlatformLinkSheet` | Zero-auth link flow for MFL/Fleaflicker; MFL adds a sign-in path (flag `mfl.auth_link`) |
| `MemberEnteredMarker` | "Member-entered — not verified with ESPN" tag + correction link, `source:'user'` picks (flag `picks.assign_tradeable`) |
| `ProvenanceChip` | Deck-level "CONSENSUS VALUES"/"YOUR BOARD" chip (flag `onboarding.trades_first`) |
| `SkeletonTradeCard` | First-run deck placeholder while pregenerated cards stream in |
| `CoachMark` | One-time inline dismissible callout; never modal, never stacked |
| `IdentityConfirmStrip` | First-run "Trading as @user — not you?" strip |
| `QuickSetPromptCard` | Inline deck-slot prompt nudging to Quick Set (flag `onboarding.quickset_prompt`) |
| `AppleSaveMomentSheet` | Save-moment Apple sign-in ask modal (flag `onboarding.apple_save_moment`) |
| `Toast` | Transient notification; VoiceOver announce + Reduce Motion fallback; optional action slot (e.g. Undo). Optional `topOffset` (defaults to `space.xxl` = today's position) so a host screen can clear its own mode bar |
| `LinkSleeperSheet` | **Single owner** of the Sleeper-identity-link form (extracted from `SettingsScreen`, P0-5). Mounted by Settings and by the `LeaguePicker` companion state. Carries the 409 `merge_choice_required` alert — whose wrong branch deletes a ranking board — so it must never be reimplemented elsewhere. testID: `settings.link-sleeper-input` (kept verbatim through the move; `capture/settings.yaml` + the testID lint point at it) |
| `PlayerContextMenu` | Shared long-press sheet (flag `ux.player_context_menu`); caller-supplied command rows; also exports `LockGlyph` |
| `AnchorSheet` | Inline anchor-value sheet (flag `draft.rank_inline`): value a player in pick terms without leaving the host screen |
| `draft/DraftRows` | Shared Draft Room/Mock row pieces: styles, `BasisChip`, position/slot helpers, fallback copy |
| `draft/MockChrome` | `MockRail` mode marker + `DraftModeToggle` segmented control (flag `draft.mock`) |
| `draft/MockEntryPanel` | Mock-mode entry card: start/resume/recap + a muted card per refusal reason; exports `MOCK_MIN_TEAMS` |
| `draft/MockSetupSheet` | Mock draft setup sheet: rounds stepper, linear/snake toggle, no-published-order notice |
| `HelpSheet` | Lightweight help sheet (flag `ux.help_surface`); exports `InfoButton` |
| `RankImportSheet` | Paste-first rankings import (flag `ranks.import`): parse preview → match/review → apply |
| `SwapSuggestSheet` | Deck swap-suggestions sheet: one-tap replacements for one asset on the top card; marks owned picks |
| `TradeFinderModeBar` | Acquire tab's mode chip strip (Guided/Team/Player/Calc/Free agents, optional Draft chip under `draft.room`) |
| `LeagueProgressModule` | Card owning every league unlock: positions-ranked ring, ranked-members bar, unlock sentence with invite link. Fold line is dynamic (#308): `contrarianFoldLine(foldNeeded, foldFormat)` from the contrarian insufficient payload — in-format members + live remaining count, a DIFFERENT population from the any-format bar above it |
| `TradingWithStrip` | Inline-home (`trades_home_inline` strip/canvas) two-pill League / "Trading with" filter row; taps open the host's existing pickers directly. #314: mounts BELOW `OutlookBiasReceipt` (+ the prefs-changed nudge), outside `modeBarWrap`; a third "Players" pill is a documented seam HELD for an operator decision. testIDs `trades.trading-with-strip`, `.league`, `.team`. Pinned by `mobile/tests/check-trades-banner-region.js` |
| `LeagueProgressModule` | Card owning every league unlock: positions-ranked ring, ranked-members bar, unlock sentence with invite link |
| `MarketPulseStrip` | Compact top-riser/top-faller line (flag `market.movers`); opens a full Risers/Fallers sheet |
| `TopBar` | Global header: active-league cluster (opens switcher) + scoring-format tile + bell + settings gear |

## Sharp edges

- `MemberEnteredMarker` self-gates on the flag AND `source === 'user'` — render it unconditionally, never behind a ternary/`&&` (`mobile/tests/check-member-entered-marker.js`).
- `draft/MockChrome`'s `MockRail` must render outside the host's ScrollView and every conditional (`mobile/tests/check-mock-mode-marker.js`).
- iOS won't stack sibling Modals — a sheet needing a second layer nests it inside the same Modal (`TradeDnaSheet`'s untouchables layer) instead of opening a second Modal.
- Touchable containers with implicit `accessible={true}` swallow child testIDs on iOS — `PlayerPickerModal`/`SwapSuggestSheet` fold the marker text into the row's a11y label instead.
- `AnchorSheet` must never reach `/api/tiers/save` or the merged-band path — anchor lane only (`backend/tests/test_draft_extensions_w1.py`).
- Every new user-facing screen mounts `FeedbackFAB` by default; modals/sheets and onboarding flows are exceptions.
