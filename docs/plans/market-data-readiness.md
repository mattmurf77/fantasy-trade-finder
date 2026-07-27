# Market-Data Readiness — audit + minimal plumbing (2026-07-26)

**Operator directive (verbatim):** "I like the risers and fallers cards and the
concept of market driven rankings (plus risers and fallers). This feels like
something that can be app wide and league specific. I don't think either are
super big value adds for now, but just ensure that the data architecture
exists to build in the future."

This was an **audit + minimal-plumbing** pass, not a feature build. No UI, no
model, no aggregation endpoint. Scope: verify the data needed for future
app-wide and league-specific risers/fallers + market-driven rankings is being
recorded, and close only the recording gaps. Ties to
[PRD #43 — Own-Market from Observed Trades](../business/product/2026-07-20-prd-43-observed-market.md).

---

## 1. What already existed (audit findings)

### App-wide

- **`player_value_history`** — daily consensus (market) value snapshots, one
  row per universal-pool player per scoring format per UTC day
  (`player_id, scoring_format, consensus_elo, consensus_value, search_rank,
  adp, snapshot_date`; `uq_value_snapshot` upsert). Written by the dedicated
  `POST /api/cron/value-snapshot` route (unflagged — data retention by
  design, #57), which loops **both** formats (`SCORING_FORMATS`).
  **Gap found:** the route existed but `render.yaml` never provisioned a
  cron service for it — only `realtime/hourly/daily-tick` were scheduled, so
  daily cadence depended on out-of-band manual setup and a missed day is
  unrecoverable (the pool is rebuilt from the live DP CSV each boot).
  Retention: keep-forever (~1,369 rows/day ≈ 0.5M rows/yr; revisit with a
  downsample-to-weekly policy after year one — noted in the data dictionary).
- **`elo_history`** — per-user personal Elo snapshots
  (`user_id, league_id, player_id, scoring_format, elo, snapshot_at`).
  Since #164 (this branch), **every** board-mutating flow writes it:
  `/api/rank3` (trio swipes) plus `_record_trends_snapshot` on
  `/api/tiers/save`, `/api/rankings/reorder`, and `/api/anchor/save`.
  `trends_service.py` + `GET /api/trends/risers-fallers` already compute
  per-user risers/fallers from it. Complete for its purpose — no gap.

### League-specific

- **Per-user board movement in a league:** `elo_history.league_id` scopes
  each snapshot; `member_rankings` holds each leaguemate's latest board
  (replace-on-submit — current state only, no history; `elo_history` is the
  history). Aggregating leaguemates' `elo_history` per league is already
  possible → league-local "your league is rising on X" needs no new plumbing.
- **FTF-internal demand signals (exist, per league):** `trade_block`
  (counterparty on-the-block flags, FB-147), `trade_impressions` /
  `swipe_decisions` / `trade_decisions` (what users see/like/pass),
  `trade_matches` (mutual likes). Usable as secondary market signals.
- **Executed league trades:** **NOT captured anywhere** (confirmed by grep —
  the PRD #43 finding of 2026-07-20 still held). Sleeper's
  `/league/<id>/transactions/<week>` payloads were thrown away on every
  sync. This was the blocking gap for PRD #43's observed-market model and
  for any league-specific "what actually trades in your league" signal.

## 2. What this pass added (minimal, additive)

1. **`sleeper_trades` table + capture** (`backend/database.py`,
   `backend/sleeper_trades_service.py`): during `session_init`'s background
   daemon — the same best-effort, off-critical-path home as the trade-block
   and owned-pick syncs — sweep public v1
   `/league/<id>/transactions/<week>` for legs 1–18, keep `type="trade"` +
   `status="complete"`, store the **full raw payload** plus normalized
   projections (`week`, `traded_at`, `roster_ids`, `adds`, `drops`,
   `draft_picks`, `waiver_budget`). Idempotent on `transaction_id`
   (append-only skip, never upsert — first-captured raw wins). Flag
   `market.trade_capture` (ON in `config/features.json` — data must
   accumulate before anything can be built on it, the same "start logging
   now" logic as #57; the flag is the kill switch). Capture only: no
   scoring, no aggregation, no UI.
2. **Reliable daily consensus snapshots**: (a) `render.yaml` now provisions
   `value-snapshot-daily` (06:00 UTC → `POST /api/cron/value-snapshot`);
   (b) `POST /api/cron/hourly-tick` gained an idempotent, failure-isolated
   **fallback guard** — if today's UTC date is missing
   `player_value_history` rows for any scoring format
   (`database.value_snapshot_formats_for`), it writes the snapshot via the
   shared `server._write_daily_value_snapshots` (refactored out of the cron
   route; both callers share the `uq_value_snapshot` upsert so they can
   never duplicate). A fully missed day now requires both crons down ~24h.
3. **Read seams for later:** `database.load_sleeper_trades(league_id)`
   (newest first) and the existing `load_value_history` /
   `load_value_snapshot_baseline` accessors.

Tests: `backend/tests/test_market_data_readiness.py` (9) — parse filtering +
raw retention, capture idempotency (unit and end-to-end via an injected
opener), per-week fetch-failure tolerance, cron-route same-day idempotency,
hourly-tick guard writes-when-missing / skips-when-present /
never-blocks-the-tick.

## 3. How we'd build it later

**(a) App-wide risers/fallers cards.** Pure read over
`player_value_history`: for each `scoring_format`, join today's rows against
a baseline date via `load_value_snapshot_baseline(scoring_format, days=N)`
(already exists — FB4-61 uses it for the `/api/rankings` trend glyphs) and
rank by `consensus_value` delta (or `search_rank`/positional-rank delta for
scale-free ordering). Top-N up / down = the card content. One new read-only
endpoint (e.g. `GET /api/market/risers-fallers?window_days=30`) plus a
client card; no new writes, no schema change. The 30-day window is already
proven meaningful across the #145 KTC-blend transition (runbook: same affine
scale, no migration needed).

**(b) League-specific risers/fallers.** Two complementary signals, both
already recorded. *Board-driven:* aggregate leaguemates' `elo_history` rows
for a `league_id` (writers now cover every ranking flow, #164) — per player,
average the per-user Elo delta over the window across members with rows in
`member_rankings`; movement shared by ≥K members = a league riser/faller
("your league is warming up on X"). `load_community_elo_for_league` is the
existing current-state read; the history aggregation is one new query over
`elo_history (league_id, snapshot_at)`. *Trade-driven:* count each player's
appearances in `sleeper_trades.adds` (and `trade_block` flags /
`trade_impressions` likes) over the window for "most traded / most wanted in
your league". Both are read-only endpoints over existing tables.

**(c) Market-driven rankings (PRD #43).** The capture added here **is**
PRD #43's Phase-1 data foundation (backlog #26) minus the user-facing Trade
History feed. Phase 2 (`values.observed_market_derive`, dark): batch job
reads `sleeper_trades.raw` per format-comparable league (join
`leagues.default_scoring`), maps `adds`/`draft_picks` to the two packages,
and treats each completed trade as a balanced-value observation — nudge each
asset's observed value toward package parity over the trade graph, persist
to a new `observed_market_values` table (`asset_id, format_key,
observed_value, trade_count` as confidence), exactly the PRD sketch. Phase 3
(`values.observed_market_blend`): fold it into
`data_loader._apply_consensus_blend` as a third weighted source beside
DP + KTC via a new `model_config.observed_market_weight` (default 0 =
bit-for-bit unchanged), confidence-gated per asset so thin data keeps the
DP/KTC seed. Because the seed feeds `player_value_history` snapshots, the
app-wide risers/fallers of (a) automatically become market-driven the day
the blend ramps — no changes to (a) needed. Cross-league scale-up is #41,
explicitly out of scope until the single-league signal proves out.

## 4. Files

- `backend/database.py` — `sleeper_trades_table`, `record_sleeper_trades`,
  `load_sleeper_trades`, `value_snapshot_formats_for`
- `backend/sleeper_trades_service.py` — new capture module
- `backend/server.py` — `_write_daily_value_snapshots` refactor,
  hourly-tick fallback guard, session_init daemon capture hook
- `backend/feature_flags.py`, `config/features.json`,
  `backend/tests/fixtures/flags/release.json` — `market.trade_capture`
- `render.yaml` — `value-snapshot-daily` cron service
- `backend/tests/test_market_data_readiness.py` — coverage
- Docs: `data-dictionary.md`, `api-reference.md`, `config-reference.md`,
  `architecture.md`, `runbook.md`
