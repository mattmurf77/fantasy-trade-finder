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
| `SendInSleeperButton` | Flagged-beta ("Send in Sleeper"): propose a trade to Sleeper directly; routes to connect / deep-link fallback |
| `VerifyAccountBanner` | Account-auth P1: quiet dismissible "Verify your account" strip floated above the tab bar (mounted once in RootNav → Main). Renders null unless the session is unverified AND (a verified controller exists OR enforcement is on); routes to SleeperConnect |
| `SteerSlider` | Settings: "We steer ↔ You steer" 4-dot ranking-method selector (one dot per ranking flow, guided → manual) |
| `Toast` | Transient notification |
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

Full planned list: lld.md Appendix A (~90 IDs). Instrument the remainder only after spike S1 passes.
