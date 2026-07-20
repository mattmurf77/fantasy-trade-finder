# Data Dictionary

Source of truth: `backend/database.py`. Keep this file in sync when adding/changing tables or columns. DB: SQLite at `data/trade_finder.db` (overridable via `DATABASE_URL`). All tables defined as SQLAlchemy Core (`metadata`).

---

## `users`

Sleeper user identities + denormalized hot-read activity columns.

| Column | Type | Notes |
|---|---|---|
| `sleeper_user_id` | str PK | The app's **working key** (historical column name). Usually Sleeper's stable user ID; account-only users (P2.6) use the synthetic `acct_<account_id>`; demo sessions `demo_user_*` |
| `username` | str | Sleeper handle (empty for account-only users) |
| `display_name` | str | |
| `avatar` | str | Sleeper avatar hash |
| `created_at` | str | ISO timestamp |
| `ranking_method` | str | `null` / `'trio'` / `'manual'` / `'tiers'` |
| `tiers_saved` | JSON text | Per-format: `{"1qb_ppr": ["RB","WR"], "sf_tep": []}` |
| `tier_overrides` | JSON text | Per-format: `{"1qb_ppr": {pid: elo}, "sf_tep": {pid: elo}}`. Values are raw Elo — tier keys are never stored, so neither the 2026-07-11 pick-value tier-ladder migration nor the 2026-07-12 8-tier revision (#117) needed **any data pass**: existing overrides re-bucket through the new `tier_config.json` band walk on read. |
| `invited_by` | str | Referrer's Sleeper username |
| `unlocked_formats` | JSON text | Formats the user has unlocked Trade Finder in |
| `anchor_scale` | JSON text | Per-format pick-value scale (1.5.4 #111): `{"1qb_ppr": 3, "sf_tep": 2}` — "a top-tier asset is worth N firsts" (N ∈ 2/3/4). Absent key = default 4 since the #117 re-derivation (2026-07-12; = the plain `m × base` anchor math). Stored values keep their semantics across the re-derivation — only the neutral point moved. Read/written by `load_anchor_scale` / `save_anchor_scale` via `/api/anchor/scale`. |
| `last_active_at` | str | denormalized from `user_events` for hot reads |
| `last_login_at` | str | |
| `last_rank_at` | str | |
| `last_match_seen_at` | str | |
| `last_trade_proposed_at` | str | |
| `last_push_sent_at` | str | |
| `signup_at` | str | |
| `events_count` | int | |
| `last_device_type`, `last_os_version`, `last_app_version` | str | most recent client snapshot |
| `verified_at` | str | ISO — when this user record was last proven controlled (account-auth plan P1/P2) |
| `verified_via` | str | `'sleeper'` / `'apple'` / `'google'` — the proof source; NULL = never verified (username-only) |
| `profile_public` | int | Public-profile opt-in (teardown 06-04, flag `profiles.user_toggle`): 1 = user opted into `/u/<username>` exposure; NULL/0 = private. Checked by the public profile routes IN ADDITION to the global `profiles.public_pages` flag; managed via GET/PUT `/api/profile/visibility` |

---

## `leagues`

One row **per league** (PK is `sleeper_league_id` alone), owned by the first
member to import it. `upsert_league` keys on the PK: the initial import
INSERTs the owner's row; every later member of that league only refreshes
`name` / `updated_at` (it does **not** INSERT — doing so raised
`UNIQUE constraint failed: leagues.sleeper_league_id`). Per-member rosters
are **not** stored here — see `league_members` for the authoritative
per-`(league, user)` roster.

| Column | Type | Notes |
|---|---|---|
| `sleeper_league_id` | str PK | |
| `user_id` | str, not null | Importer-owner (first member to import the league); not overwritten by later members |
| `name` | str | |
| `season` | str | |
| `roster_data` | JSON text | Importer-owner's player IDs at import time; write-once, not read back |
| `opponent_data` | JSON text | `[{user_id, username, player_ids}]` — importer-owner's snapshot; write-once, not read back |
| `default_scoring` | str | `'1qb_ppr'` / `'sf_tep'` (null → `'1qb_ppr'`) |
| `total_rosters` | int | Sleeper's `total_rosters` (TRUE team count incl. ownerless rosters; FB #41). Written by session_init's meta fetch; null for local leagues / pre-migration rows |
| `platform` | str | League source: NULL reads as `'sleeper'`; `'espn'` (flag `espn.link`), `'mfl'` (flag `mfl.link`), `'fleaflicker'` (flag `fleaflicker.link`). For every non-Sleeper platform the PK column holds the **platform-native** league id — the plans chose a platform column over magic-prefix ids ([ESPN §2](plans/espn-league-linking-plan-2026-07-11.md) / [multi-platform](plans/multi-platform-linking-plan-2026-07-17.md)) |
| `espn_season` | int | ESPN `seasonId` used at import — the re-sync key (`/api/espn/import`). NULL for non-ESPN rows |
| `espn_auth` | str | `'public'` / `'cookie'` — how the ESPN league was read; `'cookie'` re-syncs decrypt the importer's `espn_credentials` row |
| `espn_my_team_id` | int | The linking user's ESPN team id — binds their `league_members` row to their real FTF `user_id` across re-syncs |
| `platform_season` | int | Season/year at import for MFL/Fleaflicker (`mfl`/`fleaflicker`) — the re-sync key. NULL for ESPN/Sleeper rows (ESPN uses `espn_season`) |
| `platform_host` | str | MFL's per-league `wwwNN.myfantasyleague.com` host (the wwwNN gotcha) — reused on re-sync so no re-resolve is needed. NULL for Fleaflicker/ESPN/Sleeper |
| `platform_auth` | str | `'public'` / `'cookie'` for MFL/Fleaflicker (Phase 1 is public-only → always `'public'`) |
| `platform_my_team` | str | The linking user's franchise/team key (MFL franchise id `"0001"`, Fleaflicker team id) — binds their `league_members` row across re-syncs (generic analog of `espn_my_team_id`; **string**, since these ids aren't numeric integers) |
| `platform_future_picks` | text (JSON) | MFL/Fleaflicker `futureDraftPicks` stored **raw** at import (`[{franchise_id,year,round,original_owner}]`) for the pick-inclusive-trades follow-up. **Not read by the trade engine today** — additive storage only |
| `created_at`, `updated_at` | str | |

---

## `swipe_decisions`

Atomic interaction log — every pairwise comparison. Insert-only.

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `user_id` | str | |
| `winner_player_id` | str | |
| `loser_player_id` | str | |
| `decision_type` | str | `'rank'` (3-player matchup decomposed) or `'trade'` |
| `k_factor` | float | default 32.0 |
| `scoring_format` | str | `'1qb_ppr'` / `'sf_tep'` (null = legacy `'1qb_ppr'`) |
| `created_at` | str | |

A 3-player ranking A>B>C writes 3 rows with `decision_type='rank'`. Trade swipes write rows with `decision_type='trade'` and a smaller `k_factor`.

Indexes: `ix_swipe_dec_user_format` on `(user_id, scoring_format)` — `load_swipe_decisions` is read on every `session_init` (one query per format).

---

## `trade_decisions`

High-level trade card decisions — audit trail.

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `user_id` | str | |
| `league_id` | str | |
| `trade_id` | str | |
| `give_player_ids` | JSON text | array |
| `receive_player_ids` | JSON text | array |
| `decision` | str | `'like'` / `'pass'` |
| `created_at` | str | |

Indexes: `ix_trade_dec_user_league_decision` on `(user_id, league_id, decision)` — `check_for_match` fires on every "like" swipe filtering on these three columns.

---

## `league_members`

Members of every league `session_init` has seen. Uniqueness enforced via `(league_id, user_id)`.

For ESPN-imported leagues (`espn.link`), rows are written by `replace_espn_league_members` (delete-then-insert snapshot): the linking user's team carries their real FTF `user_id`; every other team gets a synthetic `espn:{SWID}` (fallback `espn:{league_id}.t{team_id}`) id. Synthetic ids must never reach push/notification paths (same class as unlinked Sleeper members). `roster_data` always holds **Sleeper** player ids — ESPN ids are crosswalked at import (`backend/espn_service.py`).

MFL (`mfl.link`) and Fleaflicker (`fleaflicker.link`) leagues reuse the **same writer** (`replace_espn_league_members`, which is platform-agnostic) and the same snapshot rule, with synthetic counterparty ids `mfl:{league_id}.f{franchise_id}` / `flea:{league_id}.t{team_id}`. Rosters are crosswalked to Sleeper ids via `mfl_id` / `sportradar_id` respectively (`backend/mfl_service.py`, `backend/fleaflicker_service.py`, shared crosswalk in `espn_service`). League rows are written by the generic `upsert_platform_league`; loaded by `load_platform_leagues_for_user(user_id, platform)`.

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `league_id` | str | |
| `user_id` | str | Real FTF id, or a synthetic id for imported-league counterparties (`espn:` / `mfl:` / `flea:`) |
| `username`, `display_name` | str | |
| `roster_data` | JSON text | |
| `updated_at` | str | |

---

## `trade_block`

FB-147 — snapshot of a league's Sleeper trade block: one row per asset a manager currently flags "on the block" in the Sleeper app. Source is Sleeper's **public GraphQL** `league_players` query (`settings.otb` = flagging roster_id, `settings.otb_added_at` = epoch ms — undocumented but unauthenticated; see `backend/trade_block_service.py`). Synced by `session_init`'s background daemon (flag `sleeper.trade_block`) and replaced atomically per league (delete + insert, `member_rankings`-style). Sleeper never clears stale `otb` flags after a player moves, so a flag is stored only when the flagging roster still owns the player (validated against v1 rosters at sync). Pick pseudo-ids (`"<roster>,<season>,<round>"`) are skipped — documented follow-up.

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `league_id` | str | |
| `player_id` | str | Sleeper player id (players only; no picks in v1) |
| `user_id` | str | Sleeper user who owns + flagged the player |
| `roster_id` | int | flagging roster (raw `otb` value) |
| `flagged_at` | str, nullable | ISO UTC from `otb_added_at`; NULL on legacy leagues that predate the timestamp |
| `synced_at` | str | ISO UTC of the snapshot |

Constraint: `uq_trade_block` on `(league_id, player_id)`. Written via `replace_trade_block`; read via `load_trade_block` — the documented **trade-engine hook** (weighting is owned by the trade-logic thread; serving-side, `server.trade_card_to_dict` stamps `on_block: true` on involved card players through a 5-min TTL cache).

---

## `member_rankings`

Latest Elo per (user, league, player). Replaced atomically (delete + insert) on submit.

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `user_id` | str | |
| `league_id` | str | |
| `player_id` | str | |
| `elo` | float | |
| `scoring_format` | str | `'1qb_ppr'` / `'sf_tep'` (null = legacy) |
| `updated_at` | str | |

Indexes: `ix_member_rankings_league_fmt_user` on `(league_id, scoring_format, user_id)` — `load_member_rankings` filters by `(league_id, scoring_format)` on every `/api/trades/generate`; trailing `user_id` covers per-user replace.

---

## `trade_matches`

Created when both users like mirrored trades. Lifecycle: `pending → accepted | declined`.

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `league_id` | str | |
| `user_a_id`, `user_b_id` | str | A swiped first |
| `user_a_give`, `user_a_receive` | JSON text | from A's perspective |
| `status` | str | `pending` / `accepted` / `declined` (default `pending`). Pre-2026-05 rows could be `active`; `_migrate_db()` flips any remaining `active` → `pending` once. |
| `user_a_decision`, `user_b_decision` | str | `accept` / `decline` / null |
| `user_a_decided_at`, `user_b_decided_at` | str | |
| `user_a_dismissed`, `user_b_dismissed` | int | 0/1/null — per-user inbox archive. Set by `dismiss_match`; `load_matches` hides the match from that user only. ELO-neutral (distinct from a decline). |
| `matched_at` | str | |

Indexes: `ix_trade_matches_user_a_league`, `ix_trade_matches_user_b_league` for cross-league `/api/trades/matches/all` scans.

---

## `trade_impressions`

Every trade card **shown** to a user — one row per card per completed generation job (not per `/status` poll). The implicit-negative side of the acceptance-model training data (Tier 2 work item 2.4); explicit decisions live in `trade_decisions`, and joining the two on `(user_id, league_id, give/receive sets)` labels each impression. Written by `log_trade_impressions()` from `server._run_trade_job`, after deck ordering, so `position_in_deck` records true served positions. Demo league excluded.

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | autoincrement |
| `user_id` | str | user the deck was generated for |
| `league_id` | str | |
| `target_user_id` | str | counterparty on the card |
| `give_player_ids` | JSON text | array, user's give side |
| `receive_player_ids` | JSON text | array, user's receive side |
| `basis` | str | `'divergence'` / `'consensus'` — how the card was generated |
| `likes_you` | int | 0/1 — counterparty had pre-liked the mirror trade |
| `mismatch_score` | float | |
| `fairness_score` | float | |
| `composite_score` | float | |
| `position_in_deck` | int | 0 = top card as served |
| `shown_at` | str | ISO timestamp |

Indexes: `ix_trade_impressions_user_league` on `(user_id, league_id)` — training queries scan one user-league at a time.

---

## `players`

Canonical player reference, synced from Sleeper bulk payload (skill positions, Active or prospects). Re-synced if empty or `last_synced` > 24h.

| Column | Type | Notes |
|---|---|---|
| `player_id` | str PK | |
| `full_name`, `first_name`, `last_name` | str | |
| `position` | str | QB / RB / WR / TE |
| `team` | str | abbr or null (FA) |
| `age`, `birth_date` | int / str | |
| `years_exp` | int | 0=rookie, null=prospect |
| `depth_chart_position`, `depth_chart_order` | str / int | |
| `status`, `injury_status`, `injury_body_part` | str | |
| `height`, `weight`, `college` | str | |
| `search_rank` | int | Sleeper's internal rank proxy |
| `adp` | float | |
| `last_synced` | str | |

Indexes: `ix_players_position` on `position` — `load_players(position=...)` and `load_rookies` filter by position on every positional ranking board request and trio generation (shipped Wave 1, PR #66 / INIT-14a).

---

## `league_preferences`

Per-(user, league) team-building outlook. Unique on `(user_id, league_id)`.

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `user_id`, `league_id` | str | |
| `team_outlook` | str | `championship` / `contender` / `rebuilder` / `jets` / `not_sure` |
| `acquire_positions` | JSON text | e.g. `["WR","TE"]` |
| `trade_away_positions` | JSON text | e.g. `["QB"]` |
| `updated_at` | str | |

---

## `draft_picks`

Dynasty pick assets across upcoming seasons. `pick_id = "{league}_{season}_{round}_{original_roster_id}"`.

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `pick_id` | str, unique | |
| `league_id` | str | |
| `season`, `round` | int | |
| `owner_user_id`, `owner_username` | str | current owner |
| `original_roster_id`, `original_user_id`, `original_username` | str | |
| `is_traded` | int | 1 if ownership changed |
| `pick_value` | float | `compute_pick_value()` output at sync time, on the **0–100 round-tier scale** (mid-1st ≈ 67.5), NOT the 0–10000 player value space. The v2 engine bridges it via `elo_to_value(1200 + 6·pick_value)` in `trade_service.dynasty_value` so a league pick prices like its universal-pool generic-pick twin. |
| `synced_at` | str | |

---

## `notifications`

In-app inbox. Types: `trade_match`, `trade_accepted`, `trade_declined`.

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `user_id` | str | |
| `type` | str | |
| `title`, `body` | str | |
| `metadata_json` | JSON text | type-specific context (default `"{}"`) |
| `is_read` | int | 0=unread, 1=read |
| `created_at` | str | |

---

## `user_player_skips`

"I don't know this player" / dismiss decisions. Composite PK `(user_id, player_id, scoring_format)`. Filtered out of future trios. No Elo update.

| Column | Type | Notes |
|---|---|---|
| `user_id` | str PK | |
| `player_id` | str PK | |
| `scoring_format` | str PK | |
| `skipped_at` | str | |

---

## `elo_history`

Append-only Elo snapshots powering the Trends tab. Written on every `save_ranking_swipes` call, only for players whose Elo actually changed.

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `user_id` | str | |
| `league_id` | str, nullable | null for global rankings |
| `player_id` | str | |
| `scoring_format` | str | `'1qb_ppr'` / `'sf_tep'` |
| `elo` | float | |
| `snapshot_at` | str | ISO UTC |

Compaction (snapshots >90 days) is a future maintenance task — not done in v1.

Indexes: `ix_elo_history_user_fmt_at` on `(user_id, scoring_format, snapshot_at)` — `/api/trends/risers-fallers` scans per (user, format) ordered by snapshot.

---

## `asset_preferences`

Per-player trade preferences, per league (backlog #2). Where `league_preferences` expresses intent at position granularity, this expresses it per player.

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `user_id` | str | |
| `league_id` | str | |
| `player_id` | str | Sleeper player id |
| `list_type` | str | `'untouchable'` (never suggest giving away) \| `'target'` (bias toward acquiring) |
| `created_at` | str | ISO UTC |

Constraint: `uq_asset_pref` on `(user_id, league_id, player_id)` — a player holds at most one tag per league; `set_asset_preference` deletes any prior tag before inserting (single membership), so setting `target` on an existing untouchable moves it. Read via `load_asset_preferences` → `{"untouchables": [...], "targets": [...]}`; written via `set_asset_preference(..., list_type)` where `list_type=None` removes. Add/remove history for the #65 label stream is captured in `user_events` (`asset_pref_added`/`asset_pref_removed`), not here.

---

## `player_value_history`

Daily **consensus** value snapshots (backlog #57 / player profiles #17). `elo_history` logs each user's *personal* Elo; this table logs the market side — one row per universal-pool player per scoring format per day, written by `POST /api/cron/value-snapshot`. The DynastyProcess-seeded universal pool is rebuilt from the live CSV on every boot, so yesterday's consensus numbers are otherwise unrecoverable; this is pure retention so value-history charts, the movers digest (#33), and Wrapped (#46) have history to draw on.

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `player_id` | str | Sleeper player id (or pick pseudo-id) |
| `scoring_format` | str | `'1qb_ppr'` / `'sf_tep'` |
| `consensus_elo` | float | seed Elo at snapshot time. Since #145 (2026-07-17) the seed is the **blended** DP+KTC consensus (`data_loader._apply_consensus_blend`); no schema or scale change and **no migration** — a blend shifts individual players slightly on the *same* affine value scale (unlike the #117 scale change below), so pre- and post-blend rows are directly comparable and the 30d trend baselines stay meaningful. See runbook → "KTC consensus blend". |
| `consensus_value` | float, nullable | `elo_to_value(consensus_elo)`, stored denormalised so later `elo_value_*` config changes don't rewrite recorded history |
| `search_rank` | int, nullable | Sleeper rank proxy, if known |
| `adp` | float, nullable | ADP, if known |
| `snapshot_date` | str | `"YYYY-MM-DD"` UTC |

Constraint: `uq_value_snapshot` on `(player_id, scoring_format, snapshot_date)` — the daily upsert (INSERT OR REPLACE / ON CONFLICT DO UPDATE) is idempotent, so a same-day cron retry overwrites rather than duplicating. Written via `record_value_snapshots`; read via `load_value_history` / `load_value_extremes` / `load_value_snapshot_baseline` (FB4-61: oldest prior-day snapshot in the trailing 30d window — the baseline for the consensus positional-rank trend on `/api/rankings`). Retention: keep-forever in v1 (~700 players × 2 formats × 365 ≈ 0.5M rows/yr; revisit with a downsample-to-weekly policy after year one).

**2026-07-12 (#117) scale migration:** rows written before the consensus seed recalibration stored old-scale (`elo = 1200 + dp/10000 × 600`) values; `database._migrate_db` rescaled them in place to the new value-affine scale (closed-form, invertible), guarded by the one-time `model_config` marker row `value_history_seed_scale = 2.0`. See docs/runbook.md → "8-tier ladder + consensus seed recalibration".

---

## `model_config`

Runtime-tunable constants. Edited via `/api/admin/config`. Defaults seeded on first run via `INSERT OR IGNORE` (manual overrides survive redeploys).

| Column | Type | Notes |
|---|---|---|
| `key` | str PK | snake_case |
| `value` | float | |
| `description` | str | human-readable explanation |

See [config-reference.md](config-reference.md) for the seeded defaults.

---

## `wrapped_events` — **FROZEN (analytics P0 cutover)**

Legacy event stream that powered the "Fantasy Trade Wrapped" recap. `event_type` ∈ `swipe | trade_match | trade_accepted | trade_declined | tier_save | ranking_reorder | league_sync`.

**Zero writes since the analytics P0 cutover** ([ADR-007](adr/adr-007-first-party-analytics-experimentation.md), LLD §6.4): all five writers now route through `record_event()` into `user_events` (`league_sync` renamed to the live `league_synced`; `tier_save` also joined `_RANK_STREAK_EVENTS`, so tier saves now advance the ranking streak). The cutover instant lives in `model_config` key `analytics.wrapped_cutover_at` (epoch seconds; read via `get_wrapped_cutover_iso()`). Retained read-only for pre-cutover history: `load_league_activity()` unions `wrapped_events.created_at < cutover` with `user_events.occurred_at >= cutover` (zero overlap by construction). Do not add writers.

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `user_id`, `league_id` | str | |
| `season` | int | default 2026 |
| `event_type` | str | |
| `payload_json` | JSON text | opaque |
| `created_at` | str | |

---

## `user_events`

Append-only log of meaningful user actions. Hot reads use the denormalized `users.last_*_at` columns instead — see `record_event()` for the dual-write.

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `user_id` | str, indexed | |
| `event_type` | str | see taxonomy below |
| `occurred_at` | str | ISO UTC |
| `league_id`, `session_id` | str | |
| `device_type` | str | `iphone` / `ipad` / `macos` / `web` / `extension` |
| `os_version`, `app_version` | str | |
| `source` | str | `mobile` / `web` / `api` / `cron` |
| `props` | JSON text | event-specific extras |
| `event_id` | str, unique (nullable) | client-generated UUID — idempotent retries / dedup ([tracking plan v2 §S1](business/analytics/2026-07-17-tracking-plan-v2.md)) |
| `device_id` | str, indexed | stable per-install anon id (`dev_` + UUID) — pre-signin attribution |
| `platform` | str | `ios` / `web` / `extension` / `server` |
| `screen` | str | screen/view the event fired from |
| `client_ts` | str | client wall-clock ISO; `occurred_at` stays server receive time |
| `experiments` | JSON text | `{exp_key: variant}` snapshot of active assignments at event time |
| `country` | str | ISO-3166 alpha-2, stamped at ingest from a CDN geo header (`CF-IPCountry` / `X-Country-Code`) only — never derived from or stored with raw IP; NULL when no header (bare Render today) |

Indexes: `(user_id, occurred_at)`, `(event_type, occurred_at)`, **full** unique `event_id` (`ix_user_events_event_id` — NULLS-DISTINCT on both dialects, so unlimited server-fired NULL rows coexist; conflict-ignore inserts must target it *without* `index_where`), `(device_id, occurred_at)` (`ix_user_events_device_occurred` — replaced the single-column `ix_user_events_device_id`, dropped at the analytics P0 migration).

The envelope columns (`event_id` … `experiments`) are nullable and only populated by `POST /api/events` (client batches, `insert_client_events()`); server-fired `record_event()` rows leave them NULL. Pre-auth client events store `user_id = 'device:<device_id>'` — resolve through `identity_links`.

**event_type taxonomy** (registry: `backend/analytics_taxonomy.py` — client and server namespaces are disjoint, asserted at import):
- Session: `signup`, `login`, `logout`, `app_open`
- Ranking: `trio_swipe`, `tier_save` (streak event since the P0 cutover; `props.via` ∈ `tiers`/`quickset`), `ranking_complete_first_time`, `ranking_method_changed`, `ranking_reorder`, `anchor_answered`, `quickset_completed` (`position, players_placed, duration_ms, skipped`), `quickrank_completed` (`position, players_ranked, duration_ms, skipped`), `swipe` (cutover twin of the legacy wrapped writer: `count, scoring_format`)
- Trade: `match_viewed`, `match_swiped`, `trade_proposed`, `counter_sent`, `trade_accepted`, `trade_declined`, `trade_ratified`, `trade_match` (cutover twin: `match_id, partner_id, give, receive`), `trades_generated` (`count, gen_ms, engine_version, lanes`), `calc_trade_evaluated` (`verdict, asset_count, mode` — WAT north-star input; fires for pre-auth `device:` identities too)
- Engagement: `push_sent`, `push_opened`, `notif_pref_changed`, `league_synced`, `wrapped_viewed`, `feedback_submitted`, `asset_pref_added`, `asset_pref_removed`
- Client-fired (via `POST /api/events` only, allowlisted in `ALLOWED_CLIENT_EVENTS` in `backend/analytics_taxonomy.py`): see [cross-client-invariants.md](cross-client-invariants.md) — the allowlist is a cross-client contract.

---

## `identity_links`

Stitches pre-auth `device:<device_id>` `user_events` rows to the signed-in identity ([tracking plan v2 §S1](business/analytics/2026-07-17-tracking-plan-v2.md)). Written idempotently by `link_identity()` on every successful sign-in that carries a `device_id` (body or `X-Device-Id` header): `/api/extension/auth`, `/api/auth/apple`, `/api/auth/google`, `/api/session/demo`.

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `device_id` | str | `dev_` + UUID per install |
| `sleeper_user_id` | str | user-keyed identity (demo ids and synthetic `acct_…` working keys land here too); null when unknown |
| `account_id` | str | `acct_…` anchor when the sign-in was provider-backed; null otherwise |
| `linked_at` | str | ISO UTC |

Indexes (analytics P0, LLD §3.2): `(device_id, linked_at)` (`ix_identity_links_device_linked` — new name on purpose: `CREATE INDEX IF NOT EXISTS` would silently no-op on the old single-column name; that old `ix_identity_links_device` is dropped by the migration) and `sleeper_user_id` (`ix_identity_links_user`). Code-enforced CHECK in `link_identity()`: at least one of `sleeper_user_id`/`account_id` non-null.

---

## `device_tokens`

Expo push tokens. Composite uniqueness via `device_token` PK + indexed `user_id`. Re-signing in on the same device refreshes `last_seen_at`.

| Column | Type | Notes |
|---|---|---|
| `user_id` | str, indexed | |
| `device_token` | str PK | |
| `platform` | str | `ios` / `android` |
| `created_at`, `last_seen_at` | str | |

---

## `sleeper_credentials`

⚠️ Flagged-beta ("Send in Sleeper", `trade.send_in_sleeper`). Encrypted Sleeper write tokens — one row per FTF `user_id`. Written by `upsert_sleeper_credential`; read/deleted by `get_sleeper_credential` / `delete_sleeper_credential`. Crypto lives in `backend/sleeper_write.py` (Fernet, `SLEEPER_TOKEN_KEY`); this table never holds plaintext.

| Column | Type | Notes |
|---|---|---|
| `user_id` | str PK | FTF user_id (one Sleeper link per user) |
| `sleeper_user_id` | str | Linked Sleeper account (from the JWT `user_id` claim) |
| `token_encrypted` | text | **Fernet ciphertext** of the Sleeper JWT — never plaintext, never logged |
| `expires_at` | str | ISO UTC of the JWT `exp` (365-day token); drives proactive reconnect |
| `created_at`, `updated_at` | str | |

Interim home; folds into the auth epic's `linked_sources` when that lands.

---

## `espn_credentials`

ESPN league linking (`espn.link`, [plan](plans/espn-league-linking-plan-2026-07-11.md)). Encrypted ESPN session cookies for private-league reads — one row per FTF `user_id`. Written by `upsert_espn_credential`; read/deleted by `get_espn_credential` / `delete_espn_credential`. Crypto reuses `backend/sleeper_write.py`'s Fernet helpers (same `SLEEPER_TOKEN_KEY` — one credential-encryption key per deployment).

| Column | Type | Notes |
|---|---|---|
| `user_id` | str PK | FTF user_id (one ESPN cookie pair per user) |
| `swid` | str | Braced GUID — doubles as the user's ESPN member id in league payloads; plaintext |
| `espn_s2_encrypted` | text | **Fernet ciphertext** of the `espn_s2` cookie — never plaintext, never logged |
| `expires_hint_at` | str | ISO UTC guess (~1yr community consensus; undocumented). NULL = unknown — 401s drive reconnect |
| `created_at`, `updated_at` | str | |

Interim home; folds into the auth epic's `linked_sources` when that lands.

---

## `accounts`

Identity-anchor layer above the app's working key (`sleeper_user_id`) — account-auth plan P2 (docs/plans/account-auth-plan-2026-07-11.md). One row per durable account; provider identities hang off it via `linked_identities`. Managed by `backend/accounts.py` (`find_or_create_account`, `bind_sleeper_user`, `delete_user_data`).

| Column | Type | Notes |
|---|---|---|
| `account_id` | str PK | Opaque hex id (`secrets.token_hex(16)`) |
| `sleeper_user_id` | str | Bound Sleeper source — NULL until first bind (account-only users, P2.6, stay NULL and work under the derived `acct_<account_id>` key; synthetic keys are never bound here). Binding is **sticky**: never silently rebound; a conflicting bind attempt is refused (see `bind_sleeper_user`) |
| `created_at` | str | ISO UTC |
| `email` | str | Plaintext, normalized lower/trim — **dark behind `auth.email_capture` (default off)**; per [email-capture spec](business/product/2026-07-17-email-capture-spec.md). NULL until the flag + capture UI + privacy-policy flip ship together. Deleted with the row (`delete_user_data`) |
| `email_source` | str | `'apple'` \| `'user'` — how the address arrived |
| `email_consent_at` | str | ISO UTC, stamped at capture (consent to product updates + research outreach) |
| `email_unsubscribed_at` | str | ISO UTC — set on unsubscribe/STOP; never send when set |

---

## `linked_identities`

One row per provider identity. Keyed on the provider's stable `sub` claim — **never** on email (Apple only returns email on first authorization).

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | autoincrement |
| `account_id` | str, not null | → `accounts.account_id` |
| `provider` | str, not null | `'apple'` / `'google'` |
| `provider_subject` | str, not null | Provider's stable `sub`; unique per provider (`uq_linked_identity`) |
| `email_hash` | str | SHA-256 hex of the normalized provider email; raw email is never stored |
| `linked_at` | str | ISO UTC |

---

## `sessions`

**Teardown 06-03 P3 (W3B), flag `auth.persistent_sessions`.** Durable layer under `server.py`'s in-memory session dict. Rows exist **only for verified sessions** (Sleeper-JWT proof or Apple/Google anchor) — username-only unverified sessions deliberately stay memory-only so their 4h idle TTL + restart loss keeps bounding the impersonation/squatting window. On a memory miss the server rebuilds the live session from this row (rolling 90-day idle expiry, enforced at read time and purged by the 5-min cleanup loop). Rows are deleted on sign-out, account deletion, `acct_*`→Sleeper working-key migration (link-sleeper), test-user teardown, and when `/api/session/init` re-points a token at a different user. Flag off: no rows are written or read.

| Column | Type | Notes |
|---|---|---|
| `token_hash` | str PK | **SHA-256 hex of the bearer token** — the raw token is never stored (a DB leak must not yield live credentials) |
| `user_id` | str, not null | Sleeper user id or `acct_<account_id>` working key. Indexed (`ix_sessions_user`) for the delete-all-for-user eviction paths |
| `account_id` | str | → `accounts.account_id` when the session is account-anchored |
| `verified_via` | str | `'sleeper'` / `'apple'` / `'google'` — re-stamped onto the rebuilt session |
| `account_only` | int | 0/1 — 1 = `acct_*` session with no Sleeper source (rebuilds as the empty-sentinel-league account session) |
| `username` | str | Snapshot for rebuild; falls back to the `users` profile when null |
| `display_name` | str | Snapshot for rebuild |
| `created_at` | str, not null | ISO UTC |
| `last_seen_at` | str, not null | ISO UTC — heartbeat-refreshed (throttled to ≥10 min between writes); drives the rolling 90d expiry |

---

## `shared_packages`

**Teardown S7 PRD-01 follow-up (W3B), flag `growth.share_landing`.** Landing objects for arbitrary shared trade packages (`POST /api/share/package` → `/s/p/<short_id>` + `/og/p/<short_id>.png`) — calculator builds and liked-but-unmatched trades, which have no `trade_matches` row to share. **Retention:** rows are kept indefinitely (share links shouldn't rot); `created_at` is recorded so a future sweep can prune. **Privacy note for the operator:** the landing page is public-by-URL and shows only the player ids the sharer chose; `user_id` is stored server-side for rate limiting/abuse tracing and is never rendered.

| Column | Type | Notes |
|---|---|---|
| `short_id` | str PK | URL token (`secrets.token_urlsafe(6)`, 8 chars) |
| `user_id` | str, not null | Sharer. Indexed (`ix_shared_packages_user`) — feeds the 20/hour rate limit |
| `give_ids` | text, not null | JSON `list[str]` of player ids (≤5) |
| `receive_ids` | text, not null | JSON `list[str]` of player ids (≤5) |
| `created_at` | str, not null | ISO UTC |

---

## `notification_prefs`

Per-user push notification preferences. Buckets (`trade_matches` / `weekly_digest` / `reengagement`) map kinds → user-facing toggle in `get_pref_bucket()` in the push dispatcher.

| Column | Type | Notes |
|---|---|---|
| `user_id` | str PK | |
| `trade_matches` | int | 0/1, default 1 |
| `weekly_digest` | int | 0/1, default 1 |
| `reengagement` | int | 0/1, default 1 — served/persisted as **0** for users with no stored pref while `notif.reengagement_default_off` is on (teardown 05-04a: primer consent covers only transactional matches) |
| `quiet_hours_enabled` | int | 0/1, default 1 |
| `tz` | str | IANA, e.g. `America/New_York` (the default). While `notif.tz_sync` is on, session-init/register-device adopt the device's `X-User-TZ` header when the stored value is still the default and the header is a valid IANA tz; an explicit non-default value is never overwritten (teardown 05-01) |
| `updated_at` | str | |

---

## `notification_events_log`

Append-only log of pushes actually sent. Used for dedup ("don't send same kind twice in 1/30d") without scanning `user_events`.

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `user_id` | str | |
| `kind` | str | e.g. `new_match`, `winback_dormant` |
| `dedup_key` | str | e.g. `match_id`, week-stamp |
| `sent_at` | str | |

Index: `(user_id, kind, sent_at)`.

---

## `notification_queue`

Pushes deferred by quiet hours land here. The 8am cron tick collapses per-user rows into one summary push and clears them.

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `user_id` | str, indexed | |
| `kind` | str | |
| `title`, `body` | str | |
| `data_json` | JSON text | original push payload |
| `dedup_key` | str | from `_send_typed_push` |
| `queued_at` | str | |
| `deliver_after` | str | ISO UTC timestamp when eligible |

---

## `app_feedback`

In-app feedback notes captured via the mobile FeedbackSheet and POSTed to `/api/feedback`. The mobile client keeps a local AsyncStorage copy too; this is the canonical record.

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | server-side autoincrement |
| `client_id` | str UNIQUE | mobile's local id; load-bearing dedup key for retries |
| `user_id` | str, nullable | nullable — anonymous submission allowed |
| `username` | str | denormalized snapshot from session at submit time |
| `screen` | str, not null | e.g. `Trades` / `Tiers` / `Rank/Trios`; auto-filled by FAB, user-editable |
| `severity` | str, not null | `'bug'` / `'polish'` / `'idea'` — see cross-client-invariants.md |
| `text` | text, not null | the feedback content, 1..2000 chars |
| `app_version` | str | from `X-App-Version` header |
| `platform` | str | `ios` / `android` |
| `device_type` | str | from `X-Device` (`iphone` / `ipad` / `macos`) |
| `os_version` | str | from `X-OS-Version` |
| `client_created_at` | str | ISO timestamp from client (when user tapped Save) |
| `created_at` | str, not null | ISO timestamp from server (canonical) |
| `status` | str, nullable | operator-set lifecycle status; NULL reads as `'new'`. Vocabulary `new/planned/in_progress/fixed/shipped/declined` — see cross-client-invariants.md |
| `status_updated_at` | str, nullable | ISO timestamp of the last status change |

Indexes: `idx_app_feedback_created_at`, `idx_app_feedback_user_id`.

---

## `bad_trade_flags`

"This is a bad trade" flags from the TradesHome swipe deck (feedback #85) — an engine-quality feedback loop, distinct from a pass (not interested): a flag means "the engine got this one wrong". Written by `POST /api/trades/flag`; reviewed by the operator via `GET /api/trades/flags/admin` to iterate on the trade-generation logic. Each row snapshots the card's package, counterparty, and engine telemetry at flag time (pulled from the live in-memory card when `trade_id` still resolves, else from client-echoed fallback values).

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | server-side autoincrement |
| `dedupe_key` | str UNIQUE | `user\|league\|sorted(give)\|sorted(receive)` — one flag per user per package; idempotent-insert key (same pattern as `app_feedback.client_id`) |
| `user_id` | str, not null | the flagger |
| `username` | str | denormalized snapshot from session at flag time |
| `league_id` | str, not null | |
| `target_user_id` | str | counterparty on the card |
| `target_username` | str | denormalized snapshot |
| `give_player_ids` | JSON text, not null | flagger's give side |
| `receive_player_ids` | JSON text, not null | flagger's receive side |
| `scoring_format` | str | `'1qb_ppr'` / `'sf_tep'` — resolved server-side from the session |
| `trade_id` | str | ephemeral card id, correlation only (deck ids don't survive restarts) |
| `mismatch_score` | float, nullable | engine telemetry at flag time |
| `fairness_score` | float, nullable | 0–1 |
| `composite_score` | float, nullable | |
| `need_fit` | float, nullable | 0–1 (FB-96); NULL when flag off / not stamped |
| `partner_fit` | float, nullable | 0–1 (FB-47); NULL when not stamped |
| `basis` | str, nullable | `'divergence'` / `'consensus'` |
| `reason` | text, nullable | optional user free-text, ≤ 500 chars |
| `created_at` | str, not null | ISO timestamp from server (canonical) |

Indexes: `idx_bad_trade_flags_created_at`.

---

## Monetization platform foundation

Tables added 2026-07-17 (docs/plans/monetization/00-platform-foundation.md §2.1). All ship dark — no route writes them until `monetize.*` flags flip; the manual-grant admin routes can write dormant rows at any time. Managed by `backend/entitlements.py`.

## `entitlements`

Single source of truth for paid access. Writers: billing webhook projector, referral/group-unlock reward granting, manual-grant admin routes — never client receipts. Resolution is read-time (`expires_at` compared at query time).

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | autoincrement |
| `user_id` | str, not null, indexed | Working key (sleeper id or `acct_*`) |
| `account_id` | str, indexed | `accounts.account_id` when known — grants survive Sleeper re-links (resolution checks both) |
| `entitlement` | str, not null | `'pro'` \| `'ad_free'` (ads plan HLD §4) |
| `source` | str, not null | `apple_iap` \| `stripe` \| `founder_iap` \| `season_pass_iap` \| `promo_referral` \| `promo_group_unlock` \| `manual_grant` \| `trial` \| `rankset_purchase` |
| `product_id` | str | Store SKU (`ftf_pro_annual`, `ftf_season_pass_2026`, `ftf_founder`, …) |
| `status` | str, not null | `active` (default) \| `expired` \| `revoked` \| `refunded` — revoke/refund flip status, never delete |
| `starts_at` / `expires_at` | str | ISO UTC; `expires_at` NULL = perpetual (founder, manual perpetual) |
| `granted_by` | str | `'operator'` on manual grants; webhook event id otherwise |
| `note` | str | Operator note on manual grants |
| `metadata` | JSON text | Store payloads (original_transaction_id, stripe sub id, referral id) |
| `created_at` / `updated_at` | str | ISO UTC |

## `subscription_events`

Append-only billing ledger — every RevenueCat/Stripe webhook lands verbatim before projection. `event_id` UNIQUE (`uq_subscription_event`) = idempotency on provider retries.

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `source` | str, not null | `revenuecat` \| `stripe` \| `app_store_notification` |
| `event_type` | str, not null | `INITIAL_PURCHASE`, `RENEWAL`, `EXPIRATION`, `REFUND`, `checkout.session.completed`, … |
| `user_id` / `account_id` / `product_id` | str | As carried by the event (Stripe: from Checkout `metadata`) |
| `event_id` | str UNIQUE | Provider event id |
| `payload` | JSON text, not null | Raw event, never trimmed |
| `occurred_at` | str, not null | Provider timestamp (fallback: receipt time) |
| `processed_at` | str | NULL until the projector ran |
| `process_error` | str | `'ignored: unhandled event_type …'` for consciously-skipped types |

## `referrals`

Give-get program state (foundation §5). Fraud controls are structural: `uq_referral_pair` = one reward per unique referred user ever; league co-membership + activation gating enforced by the (future) reward writer.

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `referrer_user_id` | str, not null, indexed | |
| `referred_user_id` | str, indexed | NULL until invitee identified |
| `league_id` | str, not null | The shared Sleeper league |
| `invite_token` | str UNIQUE | Carried by share-card deep links (`/join/<token>`) |
| `status` | str, not null | `pending` → `joined` → `activated` → `rewarded` \| `rejected` \| `expired` |
| `qualifying_event` | str | e.g. `'matchups_completed>=25'` |
| `reward_entitlement_id` | int | → `entitlements.id` |
| `created_at` / `joined_at` / `activated_at` / `rewarded_at` | str | Lifecycle timestamps |

## `affiliate_clicks`

Outbound affiliate click ledger; `subid` (UNIQUE) joins partner payout CSVs back to placement/user cohort. No PII in subids. Reconciliation columns written by `scripts/affiliate_reconcile.py` (affiliate LLD §7).

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `user_id` | str, indexed | NULL for DNT/anonymous clicks |
| `partner` | str, not null | `underdog` \| `draftkings` \| `fanduel` \| `fanatics` \| `caesars` \| … |
| `placement` | str, not null | `web_bestball_card`, `web_offers_hub`, `ext_player_overlay`, `ios_bestball_card`, … |
| `subid` | str UNIQUE | Passed to the partner link |
| `clicked_at` | str, not null | |
| `converted_at` / `payout_cents` / `reconciled_at` | str / int / str | Reconciliation write-back (nullable) |

## `rank_sets`

Rankings-marketplace sets (docs/business/product/2026-07-17-rankings-marketplace-plan.md). Format-agnostic by schema: `set_type` declares the benchmark family. Published versions are immutable — re-publishing bumps `version`.

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `owner_user_id` | str, not null, indexed | Contributor's working key |
| `owner_type` | str, not null | `'user'` (default) \| `'publisher'` |
| `set_type` | str, not null, indexed | `dynasty` (default) \| `rookie` \| `redraft` \| `bestball` — extended types behind `ranks.set_types_extended` |
| `scoring_format` | str, not null | `'1qb_ppr'` \| `'sf_tep'` (matches `member_rankings`) |
| `title` / `description` | str / text | |
| `version` | int, not null | Default 1; bumped per publish |
| `visibility` | str, not null | `private` (default) \| `published` \| `delisted` |
| `price_credits` | int | NULL = free / not for sale |
| `published_at` / `created_at` / `updated_at` | str | ISO UTC |

## `rank_set_entries`

One row per (set, version, player). `uq_rank_set_entry` on the triple.

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `rank_set_id` / `version` | int, not null | Composite-indexed (`ix_rank_set_entries_set`) |
| `player_id` | str, not null | `players.player_id`; picks use the draft-pick pseudo-player ids |
| `rank` | int, not null | Canonical ordering |
| `elo` | float | Optional — present when exported from a live Elo board |

## `rank_set_adoptions`

One row per adoption event (plan §Adoption mechanics). Adoption is per-league so a superflex set can't seed a 1QB league.

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `rank_set_id` / `version` | int, not null | |
| `user_id` | str, not null, indexed | |
| `league_id` | str, not null | |
| `mode` | str, not null | `seed` \| `replace` \| `track` |
| `entitlement_id` | int | → `entitlements.id`; NULL for free adoptions |
| `adopted_at` | str, not null | |

## `accuracy_scores`

Quarterly accuracy-scoring output (plan §Accuracy engine). One row per (snapshot, benchmark, horizon); `uq_accuracy_score` on (`user_id`,`rank_set_id`,`snapshot_at`,`benchmark`,`horizon`). Badge tiers derive from rolling windows in the scoring job — never stored denormalized here.

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `rank_set_id` | int | NULL for passive user-board scores |
| `user_id` | str, not null, indexed | Board owner (passive) or set owner |
| `set_type` / `scoring_format` | str, not null | |
| `snapshot_at` | str, not null | Lock timestamp of the scored board |
| `benchmark` | str, not null | `production` \| `market` \| `rookie_tiers` |
| `horizon` | str, not null | `'13wk'` \| `'1yr'` \| `'2yr'` \| `'season'` |
| `raw_score` | float | Benchmark-native (lower = better for gap metrics; per-job docs) |
| `peer_zscore` / `peer_percentile` | float | Peer-relative within the scored window / 0–100 |
| `sample_weight` | float | Relevance-weighted assets scored (min-sample gating input) |
| `scored_at` | str, not null | |

---

## Experiment engine tables (analytics platform P3)

`backend/experiments.py` + `backend/analytics_stats.py`. Append-only except `experiments.status`. Gated on `experiments.engine`.

### `experiment_layers`
Per-layer bucketing salt. `layer` PK ∈ `onboarding|ranking|trades_ui|engine|growth`; `salt` = `HMAC(EXPERIMENT_SALT_KEY, layer)` in prod (deterministic constant off-prod); `created_at`. Seeded once by `_seed_experiment_layers` — **never rotate a stored salt** (reshuffles every bucket in the layer).

### `experiments`
PK `(key, version)`. `layer`, `status` (draft|running|paused|stopped|decided), `unit_type` (account|device), `hypothesis`, `bucket_start`/`bucket_end` (half-open in-layer claim, 0..10000), `targeting_json`, `variants_json` (`[{name, weight_bp, model_overlay?, client_config?}]`, weights sum 10000), `primary_metric` (program-plan catalog), `guardrails_json` (PFO five auto-attached), `exposure_surface`, `scope_json` (FR-32 stamp scope), `mde`/`alpha`/`power`, `override_underpowered`, timestamps, `decision`/`decision_rationale`/`decided_at`. Edits to a running experiment mint a new version (`revise`).

### `experiment_assignments`
PK `(unit_id, experiment_key, version)`, conflict-ignore. `variant`, `assigned_at`, `context_json`. **Audit only** — the variant is always re-derivable from the deterministic two-stage hash (layer bucket + version-keyed variant bucket); concurrent first evals race benignly.

### `experiment_transitions`
Append-only status-change log: `id` PK, `experiment_key`, `version`, `from_status`/`to_status`, `actor`, `reason`, `at`.

### `experiment_metric_snapshots`
Daily rollup per `(experiment_key, version, variant, metric_key, window)`: `n` (exposed units), `numerator`/`denominator` (proportion), `mean`/`m2` (continuous, Welford), `computed_at`. On-request at beta scale; cron-ready for Postgres.
