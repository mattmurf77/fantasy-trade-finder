# Runbook

Operational procedures. Add to this as you learn things.

---

## Local dev

```bash
pip install -r requirements.txt
python run.py            # Flask on :5000
```

Mobile:
```bash
cd mobile && npm install && npx expo start --tunnel
```

Extension: `chrome://extensions` → developer mode → Load unpacked → pick `extension/`.

Port conflicts: macOS AirPlay Receiver uses :5000. Free it: `lsof -ti:5000 | xargs kill -9`.

---

## Deploy (Render)

`render.yaml` drives the deploy. Push to GitHub `main` and Render auto-builds.

- **Backend:** Python service runs `run.py`.
- **DB:** Postgres via injected `DATABASE_URL`.
- **Static:** `web/` served by Flask.
- Set `ANTHROPIC_API_KEY` in Render dashboard if smart matchups should be enabled in prod.

---

## Database

- **Local:** SQLite at `data/trade_finder.db`. Back up by copying the file.
- **Prod:** Postgres via `DATABASE_URL`. Take a Render snapshot before destructive changes.
- **Schema source of truth:** `backend/database.py`.
- **Migrations:** No migration tool. `_migrate_db()` in `database.py` applies idempotent additive ALTERs and seeds `model_config` defaults via INSERT OR IGNORE on every startup. For destructive changes, write a one-off script and run it manually.

---

## Feature flags

- Edit `config/features.json` and commit/deploy, OR
- `POST /api/feature-flags/reload` to re-read without restart, OR
- Set `FTF_FLAGS` env var for process-level overrides.

---

## Trade engine flags + kill switch

The trade engine is selected by flags in `config/features.json` (reload via `POST /api/feature-flags/reload`, or override with `FTF_FLAGS`):

- `trade_engine.v3` — Tier 3 optimizer (`backend/trade_optimizer.py`)
- `trade_engine.v2` — Tier 1/2 scorer in `backend/trade_service.py`
- Tier 2 features toggle independently within v2: `trade.marginal_value`, `trade.outlook_blend`, `trade.likes_you`, `trade.fuzzy_match`, `trade.thompson_deck`, `trade.deck_diversity`
- `trade.three_team` — 3-team cycle cards (Tier 3)

**Kill-switch order** (bad cards / latency / errors after a trade-engine change):

1. `trade_engine.v3: false` → falls back to the v2 engine.
2. Still bad: `trade_engine.v2: false` → falls back to the legacy scorer (kept byte-for-byte unchanged).

No data migration either way; users just get the other engine's decks on next generate. See [ADR-002](adr/adr-002-trade-engine-v2-v3-rebuild.md) and [config-reference.md](config-reference.md).

**Offline validation scripts** (read-only, never write to the DB — run from repo root):

```bash
python3 -m backend.scripts.replay_trade_decisions   # regenerate historical decks legacy vs v2;
                                                    # reports precision@5, like recall, match@5,
                                                    # multi-player share, gen time
python3 -m backend.scripts.calibrate_elo_value      # Spearman check of elo_to_value(seed) vs
                                                    # dynasty_value(search_rank); PASS at ≥ 0.98,
                                                    # plus a grid/level-fit for elo_value_k
```

---

## Runtime tuning

`model_config` table is editable live (requires `X-Cron-Secret: $CRON_SECRET`):
```
curl -H "X-Cron-Secret: $CRON_SECRET" .../api/admin/config              # read all
curl -H "X-Cron-Secret: $CRON_SECRET" -X PUT .../api/admin/config/<key> # update one
```
See [config-reference.md](config-reference.md) for keys. All `/api/admin/*`
endpoints, `/api/debug/log`, and `/api/feature-flags/reload` share this auth.

---

## Debug log

In-memory ring buffer (last ~200 entries; requires `X-Cron-Secret` — it leaks
usernames/user_ids/tracebacks, so it's operator-only):
```
curl -H "X-Cron-Secret: $CRON_SECRET" .../api/debug/log?n=100
```

> **Test users:** the `test_user_fp_*` username login bypass (`/api/sleeper/user`)
> is disabled in any non-SQLite (prod) environment. Seed test users only work
> against the local SQLite dev DB.

---

## Common failure modes

| Symptom | Likely cause | Fix |
|---|---|---|
| Smart matchup returns boring pairs | `ANTHROPIC_API_KEY` not set, or `smart_matchup_enabled=0` | Set the env var; flip the config |
| Tier colors disagree across clients | Drift in tier color tokens | See [cross-client-invariants](cross-client-invariants.md) |
| Trade Finder still locked after many ranks | Per-position threshold not met (10 each) | Rank more of the missing position |
| Empty deck only when `trade_engine.v3` is on (v2 returns cards) | v3 enforces lineup feasibility (`_STARTER_NEED` QB1/RB2/WR2/TE1) all-or-nothing: a roster that can't field a full lineup at every position makes *every* trade infeasible → zero v3 cards | Confirm the roster covers all four positions; a thin/incomplete roster (or a player-pool sync gap dropping a position) yields no v3 trades by design (TC-ENG-002) |
| Mobile can't reach backend | Not on tunnel; backend on different network | Run Expo with `--tunnel` |
| Push notifications not arriving | No `device_tokens` row, or pref bucket off, or quiet hours active | Check `notification_prefs`, `device_tokens`, and `notification_queue` for the user |
| Queued pushes never deliver | Cron ticks not firing | Verify Render cron schedule hits `/api/cron/*-tick` |
| Duplicate pushes for same event | `dedup_key` not set or differs across calls | Ensure `_send_typed_push` is given a stable `dedup_key` |
| "Action failed" on Matches Accept (feedback #8 → #35/#36 → #77) | Mobile builds ≤1.3.0 render Accept/Decline on **every** match tile — including already-decided ones (list shows all statuses, tiles never show decision state) — and surface any non-2xx as a generic "Action failed" toast. First tap 200s; every later tap on the same match hit the route's blanket `409 already_decided`. (The 2026-06-08 FB-01 fix removed the 500/KeyError class; the 409 was the residual case.) | Fixed 2026-07-09 server-side so old clients heal without an app update: re-sending the *same* decision → idempotent `200` (no second ELO signal); only a *conflicting* decision → 409. Current clients replaced Accept/Decline with Dismiss + Send in Sleeper (c079c91), so the route now mainly serves old builds + web |
| "Awaiting them" segment always empty on Matches (found via feedback #91) | `load_awaiting_trades` ordered `trade_matches` by a nonexistent `created_at` column (its timestamp is `matched_at`) → `AttributeError` for any user with ≥1 like, which the `/api/trades/awaiting` route's blanket `except` swallowed into `[]`. Silent because the route logs only a warning and the empty state looks legitimate | Fixed 2026-07-10 (`order_by matched_at`). Lesson: a bare-array endpoint that catch-alls to `[]` hides hard failures — check server logs for `get_awaiting_trades error` before trusting an empty segment |
| Suggested/default tiers absurd — dozens of "Elite" players, or stars defaulting to Depth/Bench (feedback #60/#69, "44 elite QBs") | Three stacked causes: (1) FB-76 — SF boards bucketed with 1qb_ppr thresholds (fixed 81a1934/b11a3d1, 1.3.0); (2) `apply_reorder` respread the whole board **linearly** from pool max→min, flattening the convex consensus value curve so any full Manual Ranks session pushed the top third of a position above the Elite floor; (3) `tier_config.json` bands were never calibrated to the consensus seed scale (`elo = 1200 + value/10000×600`) — DP values decay steeply, so Starter/Solid sat nearly empty and e.g. the consensus TE1 defaulted to "Depth" in SF | Fixed 2026-07-10: `apply_reorder` now permutes existing Elos (occupancy-invariant), and bands recalibrated per (format, position) to rank-count targets (Elite ≈ top 5). Guardrail: `backend/tests/test_tier_occupancy.py` pins per-position occupancy against a checked-in DP snapshot — if consensus drifts far, refresh the fixture and re-tune `tier_config.json` |
| League tab Pending/Accepted tiles disagree with the Matches list (feedback #91) | Tiles counted `trade_matches` rows split by disposition status (`pending`/`accepted`) and ignored per-user dismissal, while the Matches list shows all statuses minus dismissed — so one match could read as a "trade available" under both labels (e.g. a pending match you'd already accepted your side of + a dismissed accepted match) while the inbox showed one entry | Fixed 2026-07-10: tiles renamed to "Mutual matches" / "Awaiting them" and re-backed by `matches_mutual` / `matches_awaiting` in `/api/league/summary`, which mirror the Matches screen's segments exactly (see `test_league_summary_buckets.py`). Legacy keys still emitted for pre-1.4 builds |

---

## Cron schedule

External scheduler (Render cron) must hit:

| Endpoint | Recommended cadence |
|---|---|
| `POST /api/cron/realtime-tick` | every 1–5 min |
| `POST /api/cron/hourly-tick` | hourly (top of hour) |
| `POST /api/cron/daily-tick` | once daily |
| `POST /api/cron/value-snapshot` | once daily |

If these stop firing, queued pushes pile up in `notification_queue` and digests/re-engagement go silent.

**`value-snapshot` monitoring (#57):** the daily job upserts ~1,369 rows (≈684 `1qb_ppr` + 685 `sf_tep`); the response is `{"ok": true, "snapshot_date": "...", "1qb_ppr": N, "sf_tep": N}`. A day with no row written is value-history permanently lost (the universal pool is rebuilt from the live DP CSV each boot, so there is no backfill). If the job misses a day, that gap stays a gap — accept it; do **not** fabricate history. Verify it's firing by checking `player_value_history` has rows for today's UTC date. Idempotent, so re-running same-day is safe.

---

## Reset / wipe

```
POST /api/reset
```
Wipes the current user's `swipe_decisions`, `trade_decisions`, `member_rankings`.

---

## HTTP compression / encoding (OBS-API-02)

React Native's `fetch` auto-negotiates `Accept-Encoding: gzip, deflate, br` on every request. Cloudflare and Render both compress at the edge, so JSON responses are gzip-compressed in transit without any Flask-side configuration. The mobile app uses `/api/warm` (a lightweight ping) instead of fetching the full player payload on startup, so the largest payload (`/api/players`) is only fetched on first-run or after a 24-hour staleness. No additional Flask middleware is needed for current load; add `flask-compress` only if a new heavy endpoint is introduced that bypasses edge caching.
