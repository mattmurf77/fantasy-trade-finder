# #277 / #278 / #280 / #281 — Tier labels wherever players display (app-wide deep pass)

> Status: **in-progress** (built on worktree branch `teardown-remediation`,
> worktree `agent-a398ef6c79029326f`, from `origin/main` @ `ef9bbaa`; not
> merged/pushed by the build agent per instructions). 2026-08-09.

Operator follow-ups to #263 (calculator tier labels, validated PARTIALLY
fixed):

- **#280 (TradeCalculator):** "This is the value label I want persisted to
  the rest of the app wherever we present players."
- **#277 (TradesHome, bug):** values must persist to other screens — e.g.
  swapping a player on a found trade card. (This deep pass.)
- **#278 (LeagueRankings, bug):** league rankings/summary player rows still
  showed the numeric value.
- **#281 (LeagueHome, small):** league-summary chart had two keys after
  #260; keep only the below-graph key row and move it down a line.

## Rules applied (from the operator directive)

- Per-**asset** (player) numeric displays become **pick-tier labels**,
  reusing the #263 machinery only: server `tier` fields where the payload
  is server-built (canonical `RankingService.tier_for_elo` band-walk over
  the RAW Elo the value was priced from — **never** derived from the
  elo_to_value-transformed `value`), client `tierForElo`/`TIER_LABEL`
  (`mobile/src/utils/tierBands.ts`) where raw Elo is on hand, `TierBadge`
  (or the dense card's `TierChalkBadge` via PlayerCard `tier`) to render.
  No second value→tier mapping exists anywhere.
- Package/side **TOTALS and deltas stay numeric** — a sum of tiers is
  meaningless.
- **Draft picks stay numeric/labelled as-is** — a pick's own name ("2027
  1st") already reads as a rung on the same ladder.
- The #263 agent's scope-outs (EvenerRows, SuggestionCard) were **overruled
  by the operator** toward labels — converted below where a per-asset
  number existed.

## Enumeration — every mobile surface displaying a per-player numeric value

| Surface | File | Verdict |
|---|---|---|
| Calculator trade sides (all 3 modes) | `mobile/src/components/TradeSide.tsx` | already-label (#263); pick rows numeric by rule |
| Calculator picker primary column | `mobile/src/components/PlayerPickerModal.tsx` | already-label (#263); pick rows numeric by rule |
| Calculator picker secondary line (demo dual-board `you:`/`them:`) | `PlayerPickerModal.tsx` + `TradeCalculatorScreen.tsx` | **converted** — new `secondaryTierOf` prop; demo boards are raw-Elo scale so `tierForElo` applies; cross-tier arbitrage still shows as two different labels |
| Evener rows ("Recommended to even it" / "Trade options") | `mobile/src/components/EvenerRows.tsx` | **converted** (operator overrule of #263 scope-out) — player rows render `TierBadge` off new server `eveners[].tier`; PICK + PKG rows stay numeric by rule; old servers fall back numeric |
| Deck swap-suggestions sheet | `mobile/src/components/SwapSuggestSheet.tsx` | **converted** — same `CalcEvener.tier` rule as EvenerRows |
| Found-trade card swap sheet (#277's explicit ask) | `mobile/src/components/SwapPlayerSheet.tsx` | **converted** — rows render `TierBadge` off `CalcValueRow.tier` (#263 field, already served); suggested-section ± delta stays numeric (comparison figure); ±15% suggested-band math unchanged |
| Share-as-image card per-player rows | `mobile/src/components/ShareTradeImage.tsx` + both hosts | **converted** — `ShareAsset.tier` from the same maps the on-screen sides use; picks numeric; side TOTALS stay numeric |
| SuggestionCard (fair packages) | `mobile/src/components/SuggestionCard.tsx` | already-label/N-A — never displayed a per-player number (name + chip); package `you/them %` deltas stay |
| Found-trade deck card player rows | `mobile/src/components/TradeCard.tsx` | already-label/N-A — no per-player number (totals via TradeValueBar, which stays numeric) |
| AssetIdeasPanel / FeaturedTradeWindow | `components/AssetIdeasPanel.tsx`, `FeaturedTradeWindow.tsx` | left-numeric — the only numbers are per-IDEA package `diff` chips and give/receive totals (deltas/totals rule); no per-player value exists |
| League rankings/summary drill-in player rows (#278) | `mobile/src/screens/LeagueSummaryScreen.tsx` | **converted** — PlayerCard `tier` from new server `roster[].tier` (power-rankings); team totals, group sums, avg line, draft-capital pick values stay numeric |
| Tiers board dense tiles | `mobile/src/screens/TiersScreen.tsx` + `components/PlayerCard.tsx` | **converted** — the #54 right-cluster 0–10k numeric removed; the tile's zone `TierChalkBadge` IS the label; tier-header SUM stays numeric (total) |
| Overall Ranks rows | `mobile/src/screens/ManualRanksScreen.tsx` | **converted** — right cluster now posRank + `TierBadge` (client `tierForElo` over row Elo, active format); a11y says `tier <label>` |
| Rookie Ranks rows | `mobile/src/screens/RookieRanksScreen.tsx` | **converted** — numeric under the existing `TierBadge` removed; a11y `value N` → `tier <label>` |
| Free agents list rows | `mobile/src/screens/FreeAgentsScreen.tsx` | **converted** — PlayerCard `tier` from new server `free_agents[].tier`; drop-suggestion `(+delta)` stays numeric (delta rule) |
| FA claim sheet (header + drop candidates) | `FreeAgentsScreen.tsx` | **converted** — header + per-candidate `TierBadge` off new `tier` fields; FAAB $ figures stay (money, not player value) |
| Draft Room / Mock Draft undrafted rookie rows | `mobile/src/screens/DraftRoomScreen.tsx` (`UndraftedRowView`, shared with Mock) + `components/draft/DraftRows.tsx` | **converted** — the payload's `value` IS raw Elo (both bases), so client `tierForElo` renders a `TierBadge`; "No value" rows unchanged |
| Anchor confirmations ("Set to 1 1st · ≈ 1,234") | `components/AnchorSheet.tsx`, `screens/PickAnchorScreen.tsx` | **converted** — the "· ≈ N" numeric tail removed; the tier label already present IS the confirmation |
| PlayerCard dense `value` prop | `mobile/src/components/PlayerCard.tsx` | **removed** — prop deleted (all callers converted) so a numeric can't silently return |
| Calculator verdicts/summaries (ConsensusVerdictCard, VerdictPanel, InLeagueCalculator lineup + partner-shape lines, AdjustmentsDisclosure, one-sided demo read, text-share fallbacks) | various | left-numeric — all package/side totals, adjustments, or position-group sums (totals rule) |
| TradeValueBar / TradeMeter / StrengthBar | components | left-numeric — package delta / 0–1 meters, not per-player values |
| Market movers / Trends / Contrarian / Leaderboards / Profile contrarian | `MarketPulseStrip`, `TrendsScreen`, `ContrarianLeaderboard`, `LeaderboardsSection`, `ProfileScreen` | left-numeric — % changes, divergence scores, streaks, deltas: metrics, not player dynasty values |
| Matches / Portfolio / LeagueScreen / Rank (Trios) / QuickSet / QuickRank | screens | N/A — no per-player value displayed |

### Deferred to TradesScreen owner (file ownership constraint)

Another agent owns `mobile/src/screens/TradesScreen.tsx` and
`mobile/src/components/TradeDnaSheet.tsx` this wave — not edited here.

- `TradesScreen.tsx:4875-4886` — the FB-47 **target picker**
  (`PlayerPickerModal` mount) passes `ownerBoardValue={(p) => p.base}` but
  **no `tierOf`**, so target-picker rows still display the numeric
  `/api/trade/values` value. One-line fix for the owner: the screen already
  holds `valueById` (a `Map<string, CalcValueRow>` with `.tier`), so add
  `tierOf={(p) => (p.pos === 'PICK' ? null : valueById.get(p.id)?.tier ?? null)}`
  to that mount. Everything else on TradesScreen is plumbing, not display —
  the swap sheet itself was converted in `SwapPlayerSheet.tsx`.
- `TradeDnaSheet.tsx:305` — sorts by `.value` only; **no display change
  needed**.

## Backend (additive `tier` fields, #263 pattern — canonical band-walk)

| Route | Change |
|---|---|
| `POST /api/trade/evaluate` | `eveners[]` PLAYER rows gain `tier` (RAW seed Elo walk); PICK/PKG rows never carry it. `backend/server.py:_roster_eveners(tier_of=…)` |
| `GET /api/league/power-rankings` | every `roster[]` row gains `tier` (board Elo on `basis=personal`, seed otherwise; `null` when unpriceable). `backend/power_rankings.py` `tier_fn` |
| `GET /api/league/free-agents` | `free_agents[]`, `drop_suggestion`, `drop_candidates.players[]` gain `tier` (personal Elo, seed fallback — same Elo the value was priced from). `backend/free_agent_service.py` `tier_fn` + `board_elo` |

All three are pure-additive (key omitted when no `tier_fn` injected —
unit-test callers byte-identical). Docs: `docs/api-reference.md` rows
updated for all three routes.

## #281 — league-summary key dedupe (LeagueHome)

`mobile/src/screens/LeagueSummaryScreen.tsx`: the above-chart hint's
ticksOn branch ("Bar height = … Dashed line = … Arrows mark a 2+ rank
swing.") duplicated the below-graph key row (#248 tick swatch + #260 ▲▼N
entry). Removed — the hint now always states the ranking basis; the
below-graph key row (including ▲▼N) is the ONLY key and sits one bodySm
line-height (18) lower (`styles.legend` marginTop), per "keep the below
the graph ones, move them together a line down."

## Tests / gates

- `python3 -m pytest backend/tests -q` → **2059 passed, 1 skipped**
  (baseline 2053/1; +6 new: evener-tier, FA-row tier, drop-candidate tier,
  power-rankings tier ×3 following the #263 `test_values_endpoint_shape_and_etag`
  pattern — asserting equality with `RankingService.tier_for_elo` over the
  exact Elo the value was priced from).
- `cd mobile && npx tsc --noEmit` → clean.
- `mobile/tests/check-member-entered-marker.js` +
  `check-mock-mode-marker.js` → all pass (the D17 marker sits in rows whose
  price display changed).
- Maestro: no flow asserts a numeric player value (checked `.maestro/`);
  sim run deferred to the wave orchestrator with the merge.
