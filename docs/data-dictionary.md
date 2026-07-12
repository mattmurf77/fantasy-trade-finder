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
| `platform` | str | `'espn'` for ESPN-imported leagues (flag `espn.link`); NULL reads as `'sleeper'`. For ESPN rows the PK column holds the numeric **ESPN** league id — the plan chose a platform column over magic-prefix ids ([plan §2](plans/espn-league-linking-plan-2026-07-11.md)) |
| `espn_season` | int | ESPN `seasonId` used at import — the re-sync key (`/api/espn/import`). NULL for non-ESPN rows |
| `espn_auth` | str | `'public'` / `'cookie'` — how the league was read; `'cookie'` re-syncs decrypt the importer's `espn_credentials` row |
| `espn_my_team_id` | int | The linking user's ESPN team id — binds their `league_members` row to their real FTF `user_id` across re-syncs |
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

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `league_id` | str | |
| `user_id` | str | Real FTF id, or synthetic `espn:` id for ESPN counterparties |
| `username`, `display_name` | str | |
| `roster_data` | JSON text | |
| `updated_at` | str | |

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
| `consensus_elo` | float | seed Elo at snapshot time |
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

## `wrapped_events`

Silent event stream powering "Fantasy Trade Wrapped" recap. `event_type` ∈ `swipe | trade_match | trade_accepted | trade_declined | tier_save | ranking_reorder | league_sync`.

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

Indexes: `(user_id, occurred_at)`, `(event_type, occurred_at)`.

**event_type taxonomy:**
- Session: `signup`, `login`, `logout`, `app_open`
- Ranking: `trio_swipe`, `tier_save`, `ranking_complete_first_time`, `ranking_method_changed`
- Trade: `match_viewed`, `match_swiped`, `trade_proposed`, `counter_sent`, `trade_accepted`, `trade_declined`, `trade_ratified`
- Engagement: `push_sent`, `push_opened`, `notif_pref_changed`, `league_synced`, `wrapped_viewed`

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

## `notification_prefs`

Per-user push notification preferences. Buckets (`trade_matches` / `weekly_digest` / `reengagement`) map kinds → user-facing toggle in `get_pref_bucket()` in the push dispatcher.

| Column | Type | Notes |
|---|---|---|
| `user_id` | str PK | |
| `trade_matches` | int | 0/1, default 1 |
| `weekly_digest` | int | 0/1, default 1 |
| `reengagement` | int | 0/1, default 1 |
| `quiet_hours_enabled` | int | 0/1, default 1 |
| `tz` | str | IANA, e.g. `America/New_York` |
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
