# Architecture

High-level data flow and component boundaries. Update when modules are added, removed, or significantly re-wired.

## Data flow

```mermaid
flowchart LR
  subgraph External
    SL[Sleeper API]
    DP[DynastyProcess CSV]
    AN[Anthropic Claude API]
    EX[Expo Push]
    CR[Render Cron]
  end

  subgraph Backend [backend/ — Flask]
    DL[data_loader.py]
    DB[(SQLite<br/>trade_finder.db)]
    TC[tier_config.json]
    RS[ranking_service.py]
    TS[trade_service.py]
    TN[trade_narrative.py]
    SMG[smart_matchup_generator.py]
    TR[trends_service.py]
    WC[wrapped_collector.py]
    OG[og_image.py]
    FF[feature_flags.py]
    SRV[server.py<br/>routes + dispatcher]
  end

  subgraph Clients
    WEB[web/<br/>HTML+JS]
    MOB[mobile/<br/>React Native]
    EXT[extension/<br/>Chrome MV3]
  end

  SL -->|users, leagues, rosters, players| SRV
  DP -->|consensus values| DL
  DL -->|seed Elo| DB
  TC -->|tier bands| RS
  TC -->|tier bands via /api/tier-config| WEB
  SRV <--> DB
  RS <--> DB
  TS <--> DB
  TS --> TN
  TR <--> DB
  WC --> DB
  SMG -->|candidate pairs| AN
  AN -->|chosen pair| SMG
  SMG --> SRV
  SRV -->|push| EX
  CR -->|cron ticks| SRV
  FF --> SRV
  FF --> TS

  WEB <-->|/api/*| SRV
  MOB <-->|/api/*| SRV
  EXT <-->|/api/extension/*| SRV
```

## Components

### Backend (`backend/`)

| Module | Lines | Role |
|---|---|---|
| `server.py` | ~6.4k | Flask routes, session management, Sleeper passthrough, in-memory ring-buffer debug log (`/api/debug/log?n=100`), typed push dispatcher (`_send_typed_push`) with prefs/dedup/quiet-hours, cron tick handlers |
| `database.py` | ~5.2k | SQLAlchemy Core schema (22 tables), `_migrate_db()` idempotent ALTERs, `_MODEL_CONFIG_DEFAULTS` seeded via INSERT OR IGNORE; mirror/fuzzy match check (`check_for_match`) |
| `ranking_service.py` | ~860 | Elo math; pairwise + 3-player decomposition; `tier_bands_for` + `apply_tiers` read from `tier_config.json` |
| `trade_service.py` | ~2.1k | Cross-user mutual-gain trade discovery. Two paths: **v2 engine** (flag `trade_engine.v2` — single value space, marginal valuation, two-sided surplus gate, harmonic ranking) and the **legacy scorer** as flag-off fallback (mismatch/fairness weights, package diminishing returns, flag-gated QB/star/clogger taxes). The old `team_outlook_multiplier` and `positional_preference_multiplier` are **deleted**: outlook is now a now/future valuation *blend* (`trade.outlook_blend`, v2-only; legacy ignores outlook), and positional preferences are a *hard filter* on candidate packages in both paths |
| `trade_optimizer.py` | new | Tier 3 engine module (flag `trade_engine.v3`): exact per-pair package search + sweetener pass + 3-team cycle clearing (`trade.three_team`). Flag-selectable — off falls back to v2, then legacy |
| `trade_narrative.py` | ~100 | Deterministic template-based rationale strings for trade cards. No LLM. Used by `trade_service.generate_trades()` to fill `TradeCard.narrative` |
| `smart_matchup_generator.py` | ~530 | Claude-assisted matchup picker + algorithmic fallback. Includes `community_trio_signal` + `find_qc_trio` for QC checks |
| `data_loader.py` | ~280 | Pulls DynastyProcess CSV; maps consensus values → seed Elo (KTC curve) |
| `espn_service.py` | ~400 | ESPN league-linking adapter (flag `espn.link`): unofficial v3 API reads (browser-signature headers, injected `_opener`), payload parsing, and the DP `db_playerids` crosswalk (24h-TTL in-memory cache, snapshot fallback) that maps ESPN rosters → Sleeper player ids. Consumed by the `/api/espn/*` routes in `server.py`; live smoke CLI: `python3 -m backend.espn_service <league_id> [season]` |
| `trends_service.py` | ~420 | Risers/fallers, contrarian, consensus-gap; reads `elo_history` |
| `wrapped_collector.py` | ~70 | Exposes `record_event()` — dual-write into `user_events` + denormalized `users.last_*_at` |
| `og_image.py` | ~690 | Open Graph share images (1200×630 PNG) for tiers and trades |
| `feature_flags.py` | ~220 | Reads `config/features.json`; supports `FTF_FLAGS` env override; `/api/feature-flags/reload` re-reads at runtime |

### Backend support files

- `backend/tier_config.json` — **single source of truth for Elo tier bands**, keyed by `(scoring_format, position, tier)` with `[min, max]` ranges. Read by `ranking_service.tier_bands_for` + `apply_tiers` on the server; served to the web SPA via `GET /api/tier-config` so the frontend buckets players the same way. Replaces the old `UNIFORM_TIER_ELO_BANDS` / `QB_TE_1QB_TIER_ELO_BANDS` class constants.
- `backend/scripts/` — one-off maintenance + offline validation scripts: `rescale_pick_values.py`, `replay_trade_decisions.py` (legacy-vs-v2 replay of historical decisions), `calibrate_elo_value.py` (Spearman check of `elo_to_value` vs the legacy `dynasty_value` curve).
- `backend/tests/` — pytest suite for non-trivial pure logic: `test_pick_value_scaling.py`, `test_roster_profile.py`, `test_trade_narrative.py`.

### Clients

| Client | Path | Stack | Talks to |
|---|---|---|---|
| Web SPA | `web/` | Vanilla HTML/CSS/JS | `/api/*` (same origin) |
| Mobile | `mobile/` | React Native + Expo | `/api/*` (network) |
| Extension | `extension/` | Chrome MV3 | `/api/extension/*` (bearer token) |

### Skills (development tooling)

- `feature-evaluator/` — Claude Code skill that reviews a feature area and emits an improvement report.
- `project-reorganizer/` — Claude Code skill that reorganizes a flat project into a conventional layout.

Both are exercised in `*-workspace/` sibling folders (throwaway eval output).

## Request lifecycle (typical ranking flow)

1. Client `GET /api/trio` → `server.py` calls `smart_matchup_generator.py`.
2. SMG fetches live Elo via `ranking_service.py`, builds ~10 candidates respecting tier engine settings (`tier_engine_enabled`, `tier_size`, mix-in rates), optionally consults Claude.
3. Returns `(player_a, player_b, player_c)`.
4. User orders best→worst; client `POST /api/rank3` with the ordering.
5. `server.py` decomposes into 3 pairwise updates → `swipe_decisions` rows + Elo updates → `member_rankings` snapshot + `elo_history` row per changed player.
6. `record_event('trio_swipe', …)` in `wrapped_collector.py` writes `user_events` and bumps `users.last_active_at` / `last_rank_at` / `events_count`.
7. Returns updated progress; client repaints the bar.

## Request lifecycle (trade card — v2 engine, flag `trade_engine.v2`)

1. Client `POST /api/trades/generate`; `server._run_trade_job` runs in a daemon thread, loads real league-mate rankings (`member_rankings`), the user's per-player comparison counts (`service.comparison_counts()` — Tier 1 confidence threading), outlook + positional prefs.
2. **Value space:** the user's Elos are shrunk toward consensus seed by comparison count (`w = n/(n+shrink_pseudocount)`), then mapped to dynasty-value units via `elo_to_value` (exponential). Opponents with no real rankings are NOT scored in divergence space (their Elos would be fabricated noise) — they get **consensus-basis** cards instead (`basis="consensus"`, fairness × tier multiplier only).
3. **Marginal valuation** (`trade.marginal_value`): each asset is valued over the receiving roster's per-position replacement level, plus a `bench_credit_rate` credit; **outlook blend** (`trade.outlook_blend`) tilts the user's values now↔future by age curve and α per outlook. Positional preferences act as a hard filter on packages.
4. **Mutual-gain gate + harmonic ranking:** packages are valued KTC-style in *each side's own* value space (`package_value_v2`), the side receiving more players pays `waiver_slot_cost` per extra slot, and a trade surfaces only when BOTH sides' surpluses clear `min_side_surplus(_marginal)`. Candidates rank by the harmonic mean of the two surpluses blended with range-overlap consensus fairness, kept in a bounded top-K heap. No QB/star/clogger taxes in this path.
5. **Likes-you injection** (`trade.likes_you`): cards whose mirror a league-mate already liked are flagged/synthesized and pinned to the top (cap 3).
6. **Thompson ordering** (`trade.thompson_deck`): per-shape Beta(1+likes, 2+passes) samples reorder the deck within a bounded (0.5, 1.5) multiplier; **diversification** (`trade.deck_diversity`) penalizes league-saturated targets and caps cards per target.
7. **Impressions logging:** the final served deck is written to `trade_impressions` (one row per card, true positions), once per job.
8. `trade_narrative.build_narrative()` fills `TradeCard.narrative`; cards served via `GET /api/trades` / job snapshots.

**Tier 3** (`trade_engine.v3`, flag-selectable): `backend/trade_optimizer.py` replaces step 4's enumeration with an exact per-pair package search, adds a sweetener pass for near-miss-fair trades, and (behind `trade.three_team`) 3-team cycle clearing. Off → v2.

**Legacy path** (`trade_engine.v2` off — kill-switch fallback, byte-for-byte unchanged): mismatch (user-Elo gap) and fairness weighted `0.70 / 0.30`, fixed package diminishing weights (`package_value`), flag-gated QB/star/clogger taxes, filters by `min_mismatch_score`, `max_value_ratio`, `trade_elo_gap_max`. Outlook is ignored; positional preferences are the same hard filter.

## Request lifecycle (trade match)

1. Either user `POST /api/trades/swipe` with `like`.
2. `server.py` checks for a mirrored existing like from the other side (`database.check_for_match`). With flag `trade.fuzzy_match`, a near-mirror also matches: Jaccard ≥ `fuzzy_match_tau` (0.8) per side, and only low-value players (`search_rank ≥ 120`) may differ.
3. If found: insert `trade_matches` row (status `pending`), insert two `notifications` rows, dispatch typed push for both users.
4. Either user `POST /api/trades/matches/<id>/disposition` with `accept` or `decline`. Updates `user_a_decision` / `user_b_decision`; rolls `status` → `accepted` / `declined` once both have decided (or any user declines).
5. Counterparties receive `trade_accepted` / `trade_declined` notifications + push.

## Push dispatcher

`_send_typed_push(user_id, kind, title, body, data, dedup_key)` is the single entry point.

1. Resolve `kind` → bucket via `get_pref_bucket()`. If the user's `notification_prefs` toggle for that bucket is off → drop.
2. Check `notification_events_log` for `(user_id, kind, dedup_key)`. If duplicate → drop.
3. If `quiet_hours_enabled = 1` and now is in the user's quiet window → insert into `notification_queue` with `deliver_after = next 8am local` and return.
4. Otherwise: send via Expo to all `device_tokens` for the user; append a row to `notification_events_log`.

## Cron ticks

External scheduler (Render cron) hits four endpoints:

| Endpoint | Cadence | What it does |
|---|---|---|
| `POST /api/cron/realtime-tick` | every 1–5 min | Drain `notification_queue` rows whose `deliver_after` has passed |
| `POST /api/cron/hourly-tick` | hourly | Bundle drain + quiet-hours summary push at user's local 8am |
| `POST /api/cron/daily-tick` | once daily | Weekly digests + re-engagement scans (`winback_dormant`-style kinds) |
| `POST /api/cron/value-snapshot` | once daily | Upsert consensus value of every universal-pool player into `player_value_history` (#57). Kept separate from `daily-tick` so a push-scan failure can't stop history collection. |

## Event recording

`record_event(user_id, event_type, props=…)` in `wrapped_collector.py` does a dual-write:

1. Append to `user_events` (full structured row with device/source/session/league context).
2. Update the matching `users.last_*_at` denormalized column, plus `events_count`, `last_device_type`, `last_os_version`, `last_app_version`.

Hot-read endpoints (inactivity scans, "last login" lookups) read the denormalized `users.*` columns. Analytical reads scan `user_events` via the `(user_id, occurred_at)` or `(event_type, occurred_at)` indexes.

## Tier bands flow

1. `backend/tier_config.json` is the single source of truth.
2. Server boots → `ranking_service` loads it via `_load_tier_config()`.
3. `apply_tiers` spreads Elos linearly inside each `[min, max]` band per `(scoring_format, position, tier)`.
4. Web SPA `GET /api/tier-config` → buckets players client-side using the same `[min, max]` ranges (top-down walk). This guarantees server and web tier assignments match.
5. Mobile + extension use their own `tierBands` constants — keep in sync with this file (see [cross-client-invariants.md](cross-client-invariants.md)).
