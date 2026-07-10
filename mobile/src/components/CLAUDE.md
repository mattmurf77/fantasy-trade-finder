# mobile/src/components/

Stateless / lightly-stateful reusable UI. No data fetching here — accept props.

| Component | Use |
|---|---|
| `PlayerCard` | Player tile with name, position, value |
| `TradeCard` | Give/receive trade summary card |
| `TierBadge`, `TierBin` | Tier label + drop-zone bin |
| `PositionChip` | QB/RB/WR/TE chip with color |
| `StrengthBar` | Horizontal value/strength meter |
| `TradeSide` | Calculator: one side of a hand-built trade (players + add button) |
| `VerdictPanel` | Calculator: dual-board fairness verdict + gives/gets bars (demo mode) |
| `ConsensusVerdictCard` | Calculator: server-authoritative consensus verdict from /api/trade/evaluate (live mode) |
| `InLeagueCalculator` | Calculator "In league" mode: real opponent + rosters, two-board mutual-gain verdict (evaluate Mode B), carries Send in Sleeper |
| `SuggestionCard` | Calculator: tappable fair-package suggestion |
| `PlayerPickerModal` | Calculator: search + position-filter player picker |
| `OutlookSheet` | Bottom sheet for team outlook selection |
| `SendInSleeperButton` | Flagged-beta ("Send in Sleeper"): propose a trade to Sleeper directly; routes to connect / deep-link fallback |
| `SteerSlider` | Settings: "We steer ↔ You steer" 4-dot ranking-method selector (one dot per ranking flow, guided → manual) |
| `Toast` | Transient notification |
| `TopBar` | Screen header |
