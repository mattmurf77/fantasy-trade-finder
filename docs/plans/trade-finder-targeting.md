# Trade Finder Targeting (FB-47)

*Source: feedback id 47 (operator, 2026-06-10). Decisions locked 2026-06-10.*

**Goal:** let a user start from intent — "I want to acquire X" / "I want to move X" (player or position) — and have the engine search all league rosters, rank counterparties by positional strength, and prioritize offers accordingly. Must work even when no league-mate has joined (consensus-basis path).

## Operator decisions (locked)

1. **Acquire scope: both** position-level ("I want a WR") and player-level ("what does Jefferson cost?").
2. **Placement:** configuration settings within the existing Find a Trade page — extend the controls that already exist (web's pinned-give player picker, mobile's acquire/trade-away position chips in OutlookSheet). No new tab.
3. **Presentation: lead with cards.** Partner fit shows as a badge/line on cards and shapes deck order; no partner-first list view.

## Architecture decision

**One engine, new parameters — not a separate feature.** The finder flow parameterizes the existing v2 pipeline (same gates, package math, dedupe, impressions, matching), so finder cards are automatically telemetered (`trade_impressions`) and finder likes can convert to real matches later via mirror detection. Rationale recorded in chat 2026-06-10; consistent with ADR-002.

What already exists and is reused:
- `pinned_give_players` (engine + API + web picker UI)
- `acquire_positions` / `trade_away_positions` prefs (engine hard filter + both clients)
- Consensus-basis cards for unranked opponents (`_generate_consensus_for_pair`)
- Per-roster positional profiles (`analyze_roster_strengths`) computed for every opponent each run
- Marginal (over-replacement) valuation on the divergence path (`trade.marginal_value`)

## Phase A — engine (backend)

1. **`pinned_receive_players`** — symmetric to pinned-give: when set, every card's receive side must include at least one pinned player. Threads through `generate_trades` → `_generate_for_pair_v2` + `_generate_consensus_for_pair`. Pinned flows bypass the job cache exactly like pinned-give.
2. **Counterparty fit score** — per opponent, from the existing profiles:
   - Acquiring at position P → opponents with surplus/elite depth at P score high.
   - Selling at position P → opponents thinnest at P score high.
   - Fit ∈ [0,1]; stored on cards as `partner_fit`, serialized to clients.
   - Scoring: multiplier on consensus-card composite (`fit_consensus_weight`), tiebreak-level blend on divergence cards (`fit_divergence_weight` — small; real divergence signal must dominate).
   - Opponent visit order: best-fit first (helps the time budget spend itself on promising rosters).
3. ~~Need-aware consensus cards~~ — **deferred**: the partner-fit multiplier (A2) already carries the counterparty-need signal onto consensus composites, and the consensus generator's position filters cover the user side. Revisit only if telemetry shows consensus-card like-rates lagging.
4. Flag: `trade.finder_targeting` (off = byte-identical legacy behavior). Config keys in `_DEFAULT_CFG` + `model_config` seed.

## Phase B — API

- `POST /api/trades/generate` accepts `pinned_receive_players` (list) alongside `pinned_give_players`.
- Card dicts gain `partner_fit` (0–1, omitted when flag off).
- Docs: api-reference.md, config-reference.md.

## Phase C — clients

- **Web:** the existing pin picker gains a direction toggle (Trade away / Acquire); acquire mode lists *league-mates'* players (search across rosters). Cards show a small partner-fit line ("They're 4-deep at WR").
- **Mobile:** Find a Trade controls gain the same direction toggle + player picker (positions already covered by OutlookSheet chips). `TradeCard` component renders the fit line.

## Validation

- Unit: pinned-receive reachability (cards always include the pinned player on receive side); fit ranking math (surplus → high fit for acquire, thin → high fit for sell); flag-off parity snapshot.
- Live: `GET /api/admin/engine-metrics` — compare like-rate of finder-flow cards (impressions written with the served deck) vs organic.

## Status

- [x] Decisions locked
- [x] Phase A (2026-06-10 — A3 deferred, see above; tests in `test_finder_targeting.py`)
- [x] Phase B (2026-06-10 — `pinned_receive_players` honored behind the flag; `partner_fit` serialized; pinned jobs bypass cache)
- [ ] Phase C (web)
- [ ] Phase C (mobile)
