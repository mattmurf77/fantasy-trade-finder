# Data Dictionary

*Jump via the TOC — read sections, not the file.*

Source of truth: `backend/database.py`. Keep this file in sync when adding/changing tables or columns. DB: SQLite at `data/trade_finder.db` (overridable via `DATABASE_URL`). All tables defined as SQLAlchemy Core (`metadata`).


## Table of Contents

**Core / Users / Auth**

- [`users`](#users)
- [`leagues`](#leagues)
- [`league_members`](#league_members)
- [`accounts`](#accounts)
- [`linked_identities`](#linked_identities)
- [`sessions`](#sessions)
- [`identity_links`](#identity_links)
- [`device_tokens`](#device_tokens)
- [`sleeper_credentials`](#sleeper_credentials)
- [`espn_credentials`](#espn_credentials)
- [`mfl_credentials`](#mfl_credentials)

**Ranking / Boards**

- [`member_rankings`](#member_rankings)
- [`user_taste`](#user_taste)
- [`archetype_auditions`](#archetype_auditions)
- [`user_player_skips`](#user_player_skips)
- [`elo_history`](#elo_history)
- [`asset_preferences`](#asset_preferences)
- [`player_value_history`](#player_value_history)
- [`league_roster_history`](#league_roster_history)
- [`league_board_history`](#league_board_history)
- [`rank_sets`](#rank_sets)
- [`rank_set_entries`](#rank_set_entries)
- [`rank_set_adoptions`](#rank_set_adoptions)
- [`accuracy_scores`](#accuracy_scores)

**Trades / Deck**

- [`swipe_decisions`](#swipe_decisions)
- [`trade_decisions`](#trade_decisions)
- [`trade_block`](#trade_block)
- [`sleeper_trades`](#sleeper_trades)
- [`trade_matches`](#trade_matches)
- [`trade_impressions`](#trade_impressions)
- [`deck_impressions`](#deck_impressions)
- [`deck_outcomes`](#deck_outcomes)
- [`trade_pass_reasons`](#trade_pass_reasons)
- [`deck_candidate_sets`](#deck_candidate_sets)
- [`suggestion_trade_links`](#suggestion_trade_links)
- [`bakeoff_runs`](#bakeoff_runs)
- [`deck_suppressions`](#deck_suppressions)
- [`deck_fatigue_resets`](#deck_fatigue_resets)
- [`deck_replenish_log`](#deck_replenish_log)
- [`bad_trade_flags`](#bad_trade_flags)

**Players / Drafts / Picks**

- [`players`](#players)
- [`league_preferences`](#league_preferences)
- [`draft_picks`](#draft_picks)
  - [The containment rule (W3 M-A, ADR-010) — read this before adding a reader](#the-containment-rule-w3-m-a-adr-010-read-this-before-adding-a-reader)
- [`recorded_picks`](#recorded_picks)
- [`mock_drafts`](#mock_drafts)

**Feedback / Ops**

- [`notifications`](#notifications)
- [`notification_prefs`](#notification_prefs)
- [`notification_events_log`](#notification_events_log)
- [`notification_queue`](#notification_queue)
- [`app_feedback`](#app_feedback)

**Analytics / Experiments**

- [`model_config`](#model_config)
- [`wrapped_events` — **FROZEN (analytics P0 cutover)**](#wrapped_events-frozen-analytics-p0-cutover)
- [`user_events`](#user_events)
- [Experiment engine tables (analytics platform P3)](#experiment-engine-tables-analytics-platform-p3)
  - [`experiment_layers`](#experiment_layers)
  - [`experiments`](#experiments)
  - [`experiment_assignments`](#experiment_assignments)
  - [`experiment_transitions`](#experiment_transitions)
  - [`experiment_metric_snapshots`](#experiment_metric_snapshots)
  - [`analytics_segments`](#analytics_segments)

**Monetization / Sharing**

- [Monetization platform foundation](#monetization-platform-foundation)
- [`entitlements`](#entitlements)
- [`subscription_events`](#subscription_events)
- [`referrals`](#referrals)
- [`affiliate_clicks`](#affiliate_clicks)
- [`shared_packages`](#shared_packages)

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
| `ranking_method` | str | `null` / `'trio'` / `'manual'` / `'tiers'` / **`'anchor'`** (2026-07-10, Pick Anchor wizard) / **`'quickset'`** (#119, 2026-07-12) — all five accepted by `POST /api/ranking-method` (canonical list: `database.RANKING_METHODS`, mirrored in [cross-client-invariants § Ranking method strings](cross-client-invariants.md#ranking-method-strings)). **Write semantics (P0-1, 2026-08-11) — the column is unchanged; who writes it is not.** It is now written **implicitly at first use** by four save routes — `/api/tiers/save` (`'tiers'`/`'quickset'`), `/api/rank3` (`'trio'`), `/api/rankings/reorder` (`'manual'`), `/api/anchor/save` (`'anchor'`) — via `database.set_ranking_method_if_unset`, a single conditional `UPDATE`. **First-use wins** (last-use-wins can re-lock a user, since `get_rankings_progress`'s unlock rule is method-dependent); the one exception is `'anchor'`, which a completeness-marking tiers/quickset save may overwrite (`allow_over=("anchor",)`) because `'anchor'` can never satisfy any unlock branch. **Subset boards write nothing:** rookie-scope tier saves, `via:'rookie_ranks'` reorders and `via:'draft_room'` anchors. **One-time backfill:** `database.backfill_ranking_method_from_tiers()` runs inside `_migrate_db()` at every Flask boot and tags the pre-fix cohort — `ranking_method` NULL/empty **and** all four of QB/RB/WR/TE saved in `tiers_saved` for ≥1 scoring format — as **`'quickset'`** (a labelling assumption: which flow they actually used is not recoverable). Users with a *partial* tier board are excluded so the method switch can never re-lock them. Idempotent by predicate, chunked at 500, never raises. It also **pre-seeds `unlocked_formats`** with every qualifying format — that is fan-out suppression, not cosmetics (see that column). Ops detail: [runbook § Quick Set unlock backfill](runbook.md) |
| `tiers_saved` | JSON text | Per-format: `{"1qb_ppr": ["RB","WR"], "sf_tep": []}` |
| `tier_overrides` | JSON text | Per-format: `{"1qb_ppr": {pid: elo}, "sf_tep": {pid: elo}}`. Values are raw Elo — tier keys are never stored, so neither the 2026-07-11 pick-value tier-ladder migration nor the 2026-07-12 8-tier revision (#117) needed **any data pass**: existing overrides re-bucket through the new `tier_config.json` band walk on read. **Sibling key `__pre_rookie_scope__` (rookie-draft M2, 2026-08-06):** a one-time snapshot of the whole blob, `{v:1, taken_at, reason, formats:{fmt:{pid:elo}}}`, taken before the user's first rookie-**scoped** tier save. This column is wholesale-overwritten with no history and a scoped save writes only part of the board, so the snapshot is the recovery path ([runbook § Rookie-scope board restore](runbook.md); API `take_/load_/restore_tier_override_snapshot`). **Preservation rule — load-bearing:** `_parse_per_format_json` deliberately narrows to `SCORING_FORMATS`, so any writer that round-trips this column MUST merge non-format keys back via `_parse_extra_keys` (`{**extras, **all_overrides}`, extras first so a format key can never be shadowed) or it silently deletes them. `reset_user_rankings` sets the column to NULL and therefore drops the snapshot with the board — correct, but it means the restore path does not survive a self-service reset. **Sibling key `__override_at__` (F2, 2026-08-18):** `{fmt: {pid: iso8601}}` — when each override was written, so a ranking swipe recorded *after* a pin can release it (`ranking_service._pin_release`, knob `pin_unpin_on_newer_swipe`). Deliberately a sibling key rather than changing the per-format value shape to `{pid: {elo, at}}`: no migration, no risk to `load_tier_overrides`' float cast, and every existing reader of the column (`og_image`, `accounts`, the snapshot/restore path) is untouched. Written by `save_tier_overrides(..., stamps=)` (omitting `stamps` preserves what is stored, and the map is always pruned to pids present in `overrides`); read by `load_tier_override_stamps`. A pid with an override but **no** stamp is a **legacy pin** — 2,735 such entries existed across 5 users at ship — and `pin_legacy_at_epoch` decides whether it is permanent (default) or releasable. `restore_tier_overrides_from_snapshot` clears the restored format's stamps, since the snapshot predates F2 and holds no write times. |
| `invited_by` | str | Referrer's Sleeper username |
| `unlocked_formats` | JSON text | Formats the user has unlocked Trade Finder in. Monotonic floor — an entry is never removed, so a method change can never subtract an unlock. **P0-1 backfill pre-seed (2026-08-11):** `backfill_ranking_method_from_tiers()` writes the qualifying formats here in the *same* `UPDATE` that sets `ranking_method`. This is **fan-out suppression, not cosmetics** — the unlock ladder fires a push when a format transitions from locked to unlocked, and the backfill flips a whole cohort at once; pre-seeding means the transition has already happened by the time anything reads it, so no retroactive notification burst is sent. Permanent consequence: those users never get the "Trade Finder unlocked" push for the format they were backfilled into |
| `anchor_scale` | JSON text | Per-format pick-value scale (1.5.4 #111): `{"1qb_ppr": 3, "sf_tep": 2}` — "a top-tier asset is worth N firsts" (N ∈ 2/3/4). Absent key = default 4 since the #117 re-derivation (2026-07-12; = the plain `m × base` anchor math). Stored values keep their semantics across the re-derivation — only the neutral point moved. Read/written by `load_anchor_scale` / `save_anchor_scale` via `/api/anchor/scale`. |
| `last_active_at` | str | denormalized from `user_events` for hot reads |
| `last_login_at` | str | |
| `last_rank_at` | str | Bumped by every rank-class event in `_EVENT_TO_USER_COL`: `trio_swipe`, `tier_save`, `ranking_complete_first_time`, and since the #152 residual fix also `anchor_answered` + `ranking_reorder` (notification-nudge gating undercounted anchor-wizard/manual-board users before) |
| `current_streak` | int | Daily ranking streak, advanced by `_recompute_streak_on_rank_event()` on `_RANK_STREAK_EVENTS`. **Stored value only rewrites on the next rank event** — readers (`get_user_streak`, streak leaderboard) compute the *effective* streak, reporting 0 when `last_rank_local_date` is >1 day behind local today (#152 residual) |
| `longest_streak` | int | High-water mark; never decays |
| `last_rank_local_date` | str | `YYYY-MM-DD` of the last rank in the **user's local-day frame** (`last_rank_tz`), so DST shifts and travel don't reset |
| `last_rank_tz` | str | IANA tz (`X-User-TZ` header) the date above was written in; also the read-side decay frame (UTC fallback when null/invalid) |
| `last_match_seen_at` | str | |
| `last_trade_proposed_at` | str | |
| `last_push_sent_at` | str | |
| `signup_at` | str | |
| `events_count` | int | |
| `last_device_type`, `last_os_version`, `last_app_version` | str | most recent client snapshot |
| `verified_at` | str | ISO — when this user record was last proven controlled (account-auth plan P1/P2) |
| `verified_via` | str | `'sleeper'` / `'apple'` / `'google'` — the proof source; NULL = never verified (username-only) |
| `profile_public` | int | Public-profile opt-in (teardown 06-04, flag `profiles.user_toggle`): 1 = user opted into `/u/<username>` exposure; NULL/0 = private. Checked by the public profile routes IN ADDITION to the global `profiles.public_pages` flag; managed via GET/PUT `/api/profile/visibility` |
| `stud_tax_mode` | str | #214/#215 — per-user stud-tax mode: `'market'` (retuned default; NULL/unknown reads as market) / `'heavy'` (pre-#214 legacy adjustment math) / `'off'` (no crown premium or package-depth discount). Managed via GET/PUT `/api/settings/stud-tax`; read by `trade_service.stud_tax_mode_for_user` for `/api/trade/evaluate` + deck generation |
| `pick_pricing_mode` | str | **M6b** (flag `trade.slot_pricing`) — per-user draft-pick pricing mode: `'tier_ladder'` (**default**; NULL/unknown reads as tier_ladder — today's shipped ladder, `pick_values.pick_pool_value`) / `'market_slots'` (DynastyProcess's published per-slot market curve, `pick_values.market_pick_pool_value`). Managed via GET/PUT `/api/settings/pick-pricing` (404 while the flag is off); read by `trade_service.pick_pricing_mode_for_user` and applied at READ time by `pick_values.priced_pool_value` in `_owned_pick_assets` + `/api/trade/evaluate`. **It never rewrites `draft_picks.pool_value`** — that column is league-shared, so a per-user mode that wrote it would reprice leaguemates |

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
| `platform_future_picks` | text (JSON) | MFL/Fleaflicker `futureDraftPicks` stored **raw** (`[{franchise_id,year,round,original_owner}]`). Written at link/import by `upsert_platform_league`, and — for MFL since #207/#228 parity — **refreshed on the draft-status refresh cadence** by `server._refresh_mfl_future_picks` via the narrow `set_platform_future_picks` setter (never wiped when the export is unavailable). Normalized into `draft_picks` by `server._sync_mfl_owned_picks` since #158, so it **is** engine-visible through that store |
| `draft_status` | str | #207 rookie-draft verdict for the league's CURRENT season: `'drafted'` / `'not_drafted'` / `'unknown'`. NULL = never checked. Written by `server._refresh_league_draft_status` (`backend/draft_status.py` decides); read by `/api/rankings` + `/api/trio` to year-tag the generic pick rungs. **Fail-safe: anything but `'drafted'` shows current-year picks** |
| `draft_status_confidence` | str | `'high'` (platform-authoritative: Sleeper `complete`+`last_picked`, MFL `made==total`) / `'medium'` (roster heuristic, or a platform/roster conflict) / `'low'` (abstained). Recorded for diagnosis; the serialization path gates on the verdict only |
| `draft_status_checked_at` | str | ISO UTC of the last check — stamped even for `'unknown'` so a persistently flaking league backs off. Drives the asymmetric cheap-skip TTLs in `server._DRAFT_STATUS_TTL_SECONDS` (drafted 12 h, not_drafted 3 h, unknown 1 h) |
| `pick_assignment_settings` | text (JSON) | **W3 M-A (ADR-010)**, flag `picks.assign` — `{rounds:int, order_type:'linear'\|'snake', order:[user_id, …]}`. **NUMBERING ONLY.** Ownership is never stored here — it lives one row per slot in `draft_picks`. `order` is the round-1 pick sequence and `order_type` the shape; both change slot numbers and **never** who owns a pick, which is what makes the toggle safe to flip at any time. NULL = never configured (defaults: 4 rounds, linear, members sorted by `user_id`). Accessors: `load_pick_assignment_settings` / `save_pick_assignment_settings` |
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
| `retracted_at` | str, nullable | ISO UTC; NULL = live like (#318 awaiting-dismiss). Set (never cleared) by `POST /api/trades/awaiting/dismiss` on every like row sharing the dismissed trade's `(league_id, give-set, receive-set)` key. Retracted rows are invisible to `load_awaiting_trades` / `load_recent_league_likes` / `check_for_match`, but stay visible to swipe-Elo history, impressions joins and the past-decisions deck suppression (deliberate). A re-like writes a fresh NULL row — the revive path. Additive boot migration; existing rows backfill NULL. |

Indexes: `ix_trade_dec_user_league_decision` on `(user_id, league_id, decision)` — `check_for_match` fires on every "like" swipe filtering on these three columns; also serves the write-time replay guard below.

**Duplicate rows are legal, and there is deliberately no unique constraint.** Two distinct kinds of duplicate on `(user_id, league_id, trade_id)` are correct behaviour: the #318 **revive path** (like → retract → re-like writes a fresh `retracted_at IS NULL` row), and a **genuine re-decision** of a card a deck regeneration re-served. A unique index over that triple would break both, and could not be created against the live table in any case.

**Write-time replay guard (G-049).** `save_trade_decision()` is idempotent over a short window and returns `True` when it wrote a row, `False` when it recognised a replay and skipped one. It suppresses only the narrow signature of a double-POST: a still-**live** row for the same `(user_id, league_id, trade_id, decision)` with a byte-identical give/receive payload, written less than `database.TRADE_DECISION_DEDUPE_SECONDS` (10 s) ago. Everything else is written, so no decision the user made is dropped; an unparseable `created_at` fails **open**. The window is sized from prod (2026-08-18): true double-writes were at most 0.200 s apart, the closest legitimate re-decision 147.7 s — nothing in between.

`save_trade_swipes()` **must be skipped on a `False` return** — both route call sites (`swipe_trade`, `_apply_reasoned_pass`) do. `swipe_decisions` stores no trade or league identity, so this return value is the only place a downstream writer can learn that a swipe was a replay; ignoring it re-applies `trade_k_pass` twice.

`RankingService.record_trade_signal()` is **deliberately not gated** on it (D-073). It fires before the DB write in both routes and appends to an in-memory list that `replay_from_db` rebuilds from `swipe_decisions` at every `session_init` — derived state, never persisted — so a replay's doubled signal lasts one session and then heals. Gating it would tie in-session board movement to DB reachability, trading a bounded 2x overcount for an unbounded 0x undercount whenever the persist block (best-effort by design) fails. `check_for_match` is likewise ungated: a replayed like must still surface a mutual match.

The guard is not a distributed lock — two genuinely simultaneous requests on separate workers can still both write.

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

## `sleeper_trades`

Market-data readiness (operator directive 2026-07-26; PRD #43 Phase-1 data foundation / backlog #26) — **executed Sleeper league trades, captured raw**. Source: the documented public v1 endpoint `GET /league/<id>/transactions/<week>`, swept over legs 1–18 by `backend/sleeper_trades_service.sync_league_trades` during `session_init`'s background daemon (flag `market.trade_capture`, Sleeper numeric league ids only, best-effort). Only `type="trade"` + `status="complete"` rows are stored. Capture ONLY — no scoring, no aggregation, no UI; this table exists so a future observed-market model (PRD #43 Phases 2–3) and league-specific market signals have raw material accumulating from today. Also populated by the operator-run backfill `scripts/backfill_sleeper_trades.py` (2026-08-16), which additionally walks each league's `previous_league_id` chain — so `league_id` here may be a prior-season Sleeper league that has no row in `leagues`.

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `transaction_id` | str | Sleeper transaction id — idempotency key |
| `league_id` | str | indexed (`ix_sleeper_trades_league`) |
| `week` | int, nullable | Sleeper `leg` |
| `traded_at` | str, nullable | ISO UTC from `status_updated` (epoch ms) |
| `synced_at` | str | ISO UTC capture time |
| `roster_ids` | text | JSON: participating roster_ids |
| `adds` | text | JSON: `{player_id: receiving roster_id}` |
| `drops` | text | JSON: `{player_id: sending roster_id}` |
| `draft_picks` | text | JSON: traded pick objects (season/round/owners) |
| `waiver_budget` | text | JSON: FAAB transfers inside the trade |
| `raw` | text | JSON: **full Sleeper transaction payload** — source of truth; normalized columns are a convenience projection |

Constraint: `uq_sleeper_trade_txid` on `transaction_id`. Append-only: `record_sleeper_trades` skips already-stored ids (a completed trade never mutates; the first-captured raw payload is kept), so re-sweeps are free. Read via `load_sleeper_trades(league_id)` — the future read seam for League Trade History / observed-market derivation. Retention: keep forever (trades are the dataset).

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

## `deck_impressions`

TikTok-discovery **F1 signal spine** (flag `deck.signal_v2`, `docs/plans/tiktok-discovery/prds/F1-signal-foundation.md`). One row per card in the **final served deck order**, written once per completed generation job by `server._log_deck_signal_impressions` (→ `save_deck_impressions`), **only when the flag is on**. Additive: `trade_impressions` keeps writing unchanged. Demo league excluded. The row's `impression_id` is returned per card in `/api/trades/generate` + `/status` snapshots and echoed back by flag-on clients so `deck_outcomes` rows join to it.

| Column | Type | Notes |
|---|---|---|
| `impression_id` | str PK | uuid4 hex, minted at serve time |
| `user_id` | str | user the deck was served to |
| `league_id` | str | |
| `deck_job_id` | str | generation job id (`_trade_jobs`) |
| `card_index` | int | 0 = top card, final served order |
| `trade_hash` | str | sha256[:16] of sorted give ids \| sorted receive ids \| partner |
| `features_json` | JSON text | **frozen at serve time** — shape, basis, likes_you, lane, give/receive positions, values + 500-wide value bands, `involves_pick`, `partner_user_id`, surplus margin (mismatch), fairness, need/partner fit, fit_premium, aggression_variant, relaxed, plus board-state-at-serve: `ranked_player_count`, `last_board_update_at`, `user_value_basis` (`personal`/`consensus`); `deck_source` only on F10 cron-pre-generated decks; `taste_attrs` (F5, only while `deck.taste_vectors` is on) — the card's frozen taste-attribute keys consumed by `user_taste` updates; `wildcard: true` + `wildcard_pool_size` + `wildcard_provenance` (`taste_tercile`/`low_data_arm`/`uniform`/`audition`) only on the F7 exploration wildcard (flag `deck.exploration`); `first_deck: true` (F9, only while `deck.first_session` is on) on every card of a user's FIRST deck for the league — `first_session_like_position` = MIN(`card_index`) over like outcomes joined to these rows |
| `propensity` | float NOT NULL | the Thompson multiplier **actually applied** to this card's sort key (`0.5 + beta draw`, in (0.5, 1.5)); `1.0` when ordering was off (deterministic serve). **F7 exception:** on a wildcard row (features_json `wildcard: true`) this is instead `exploration_rate × 1/wildcard_pool_size` — the uniform-draw probability that REPLACES the Thompson multiplier (the wildcard never entered the ordering draw) |
| `base_score` | float | `composite_score` before presentation multipliers |
| `final_score` | float | ordering key after Thompson/diversity multipliers (= base when ordering off) |
| `archetype` | str | lane label when stamped (`window`/`value`), else null |
| `shape_bucket` | str | `"1x1"`, `"2x1"`, … (the Thompson arm) |
| `served_at` | str | ISO UTC |
| `centerpiece_id` | str | **F3** (flag `deck.fatigue`) — highest-consensus asset in the package (deterministic tie-break by id), the per-item fatigue key. Stamped only while `deck.fatigue` is on; NULL on pre-F3 / flag-off rows |
| `is_ghost` | int | **suggestion.telemetry** (all five columns below: stamped only while the flag is on; NULL on flag-off / pre-telemetry rows; `docs/plans/matchmaking-engine/telemetry-scope.md`) — 1 = ghost suggestion: deterministically withheld from display (per league × ISO week × `trade_hash`, ~1-in-`ghost_holdout_one_in`), fully logged, **never rendered** — it appears in no job snapshot and can never receive a `deck_outcomes` row, so outcome-joined reads ignore ghosts naturally. Ghost rows' `card_index` is the **would-have-been** rank in the pre-withhold order; served rows keep true served positions (0..n-1 contiguous) |
| `policy_version` | str | serving-policy id, e.g. `v3+ts.div.fat@r1` — engine version + active ordering-layer flags + `suggestion_telemetry.POLICY_REV`. The OPE attribution key |
| `candidate_set_id` | str | soft reference → `deck_candidate_sets.candidate_set_id` (the action set this card was chosen from) |
| `candidate_set_size` | int | denormalized `deck_candidate_sets.size` |
| `assets_json` | JSON text | `{"give": [asset ids], "receive": [asset ids]}` — the first-class asset bundle (`trade_hash` can't be inverted); what the executed-trade matcher compares against `sleeper_trades` |
| `model_arm` | str | **trade.bakeoff** (both columns below: stamped only while the flag is on; NULL on flag-off / pre-bake-off rows; `docs/plans/three-model-bakeoff/scope-phase3.md`) — the arm that PRODUCED this card: `baseline` \| `current` \| `gen_v2`. **Denormalized** from `policy_version` (which also carries it as `<policy>/bo:<arm>`) so no query has to parse a string. NULL on a served card no arm produced — a likes-you injection — which is the honest answer, not a gap. Written on **every** row of a bake-off deck (never conditionally): `save_deck_impressions` inserts the batch with `executemany`, which compiles the statement from the FIRST row's keys, so a deck led by an unattributed card would otherwise silently drop attribution for the whole deck |
| `group_key` | str | **trade.bakeoff** (this and the two below: deck composition, operator decision 2026-08-18, `docs/plans/three-model-bakeoff/scope-composition.md`) — which **group**'s quota this card filled: `current_divergence` \| `current_consensus` \| `gen_v2` on the default roster. A group is (arm, basis), quota'd 5 value / 5 outlook, and the groups — not the arms — are what interleave. NULL when no group produced the served deck: a likes-you injection, a dark-mode deck (arm B's own list in arm B's own order, so those cards filled nobody's quota), or a run with `bakeoff_group_size` = 0 |
| `group_rank` | int | **trade.bakeoff** — 0-based rank inside that group's composed list. Distinct from `arm_rank` (rank in the arm's own FULL ranked list — the generator's opinion) and from `card_index` (deck position). The three answer different questions and all three are recorded; none is derivable from the others |
| `lane_slot` | str | **trade.bakeoff** — which quota slot the card took: `value` \| `outlook` \| `fill`. `fill` means it took a residual slot its own lane did not earn — only reachable under `bakeoff_fill_policy` = 1, or when the lane axis is undefined for the deck (`groups_json[key].lane_split_active: false`). **Lane reallocation (D-086) never produces `fill`:** a value card that took a slot the outlook lane could not use is stamped `value`, because it is a value-lane card in a value slot — the group's value quota grew, no card crossed lanes. Read `groups_json[key].realloc` for how many slots moved. The flag is what stops an analysis mistaking a value-lane backfill for a card that genuinely filled an outlook quota. The card's own `basis` and `lane` are already on `features_json` (and `lane` on the `archetype` column), so no field is duplicated here |
| `trade_intent` | str | **trade.bakeoff** — the EFFECTIVE #172 intent lens this card was filtered under: `consolidate` \| `tier_up` \| `tier_down`, or NULL for an unfiltered deck. Like `fairness_threshold` this was persisted **nowhere** before, and like it the requested and effective values genuinely diverge: `_generate_trades_impl` resolves the request to `None` whenever `trades.intent_modes` is off (a client that sent `consolidate` was served an unfiltered deck), the route already drops anything outside the three modes, and `_filter_by_trade_intent` is a POST-generation filter. **Why it exists:** the user-facing trade settings stay visible during the bake-off (operator decision 2026-08-18 — testers are briefed verbally instead), so a tester can switch the intent chip mid-test and shift every group's basis/lane mix, and without this the shift would be invisible in the data. Same every-row write rule as the columns above |
| `fairness_threshold` | float | **trade.bakeoff** — the consensus fairness bar this card ACTUALLY had to clear. The client sends a per-request value (0.75 fairness toggle on / 0.50 off) which the engine then composes **per card**: a `relaxed` card (#189, reachable on an organic deck via the user's acquire/trade-away preferences) rides `min(requested, relaxed_fairness_threshold)`; a `divergence` card rides `min(…, fairness_floor_divergence)` (both members have real boards, so the consensus check is an extreme-case veto only); a `consensus` card keeps the full bar. NULL on an arm `gen_v2` card — `trade_gen_v2` takes no `fairness_threshold` at all, its bar is the `gen2_*` dual-board ε stack — which is the honest answer, not missing data. **Why it exists:** before this the value was persisted nowhere (`docs/reviews/2026-08-18-trade-logic-archaeology.md`), so a per-arm comparison spanning sessions with different client settings compared arms AND thresholds at once with nothing in the data to separate them. Same every-row write rule as the two columns above |
| `arm_rank` | int | the card's **0-based rank within its own arm's ranked list** — never its deck position (that is `card_index`). The pair `(model_arm, arm_rank, card_index)` is what separates model quality from deck-position effects: `arm_rank` is what the model thought, `card_index` is where the interleaver put it |

`features_json` additionally carries `also_proposed_by` (list of arm names) on a bake-off card that ANOTHER arm also proposed — the duplicate ledger. Credit is first-picker, so the trade appears once; agreement is recorded rather than discarded.

Indexes: `ix_deck_impressions_user_league` on `(user_id, league_id)`; `ix_deck_impressions_job` on `deck_job_id`.

---

## `deck_outcomes`

F1 labels, **append-only**, joined to `deck_impressions` by `impression_id` (soft reference, no FK — late/duplicate labels legal, rows never mutated). Written by `server._save_deck_outcome_safe` from: `/api/trades/swipe` (`like`/`pass` + dwell/engagement fields), `/api/trades/flag` (`not_interested`), `/api/trades/propose` (`propose`), and the `/api/events` side-channel (`deck_card_viewed` → `viewed` — client fires it after a card is front-of-deck ≥500 ms — and `swipe_undone` → `undo`). An undo **appends alongside** whatever the original outcome was. All writes require flag `deck.signal_v2` on AND a client-supplied `impression_id`; absent either, zero rows (old clients unaffected).

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | autoincrement |
| `impression_id` | str | `deck_impressions.impression_id` |
| `action` | str | `viewed` \| `like` \| `pass` \| `not_interested` \| `propose` \| `undo` (enum enforced in `save_deck_outcome`) |
| `dwell_ms` | int | card fronted → disposition, paused on app background, capped 120 s client-side |
| `detail_expanded` | int | 0/1/NULL — opened player menu / swap sheet / keep-side on the card |
| `calc_opened` | int | 0/1/NULL — edit-in-calculator (#190) from the card |
| `acted_at` | str | ISO UTC (server clock) |

Indexes: `ix_deck_outcomes_impression` on `impression_id`.

---

## `trade_pass_reasons`

Decline-reason capture (flag `feedback.decline_reasons`, `docs/plans/decline-reason-capture/SPEC.md`) — **one UPSERT row per passed card**, keyed on `impression_id` (soft reference to `deck_impressions`, no FK, house style). Written only by `POST /api/trades/pass-reason`, gated by that flag alone (operator decision 2026-08-17: ships to all users; SPEC §5's tester-allowlist scoping is superseded).

The three tiles (Value · Fit · Neither) replace the card's ✕, so **tapping a tile IS the pass** — one gesture writes the disposition and the layer-1 reason together. The disposition itself still lands in `deck_outcomes` as `action='pass'` exactly as the ✕ wrote it; this table is the *reason*, not the disposition.

**Why upsert, when its `deck_outcomes` sibling is append-only:** every tap commits on its own and no tap may lose an earlier one (SPEC §3), so the row grows in place — layer 1 → layer 2 → free text. `deck_outcomes` could not host this: its rows are never mutated by contract, it holds several rows per impression, and it has no unique key to upsert on. Only the fields a given call supplies are written, so a layer-2 tap cannot blank layer 1.

**`impression_id` is never required** (operator decision 2026-08-17): a client that sends none — `deck.signal_v2` off, or a legacy card — must still be recorded, never refused. When one IS sent it is **validated before it becomes a key** (the 2026-08-14 ownership rule): an id that names no impression, or belongs to another user, degrades to the same per-user surrogate `local:<user_id>:<trade_id>`, so the answer is never lost and the write never lands in another user's key space. `key_source` records which path a row took — only `impression` rows join the F1 spine and are usable for off-policy evaluation.

| Column | Type | Notes |
|---|---|---|
| `impression_id` | str PK | `deck_impressions.impression_id`, or `local:<user_id>:<trade_id>` when unvalidatable |
| `user_id` | str | the passing user (session-resolved, never a body field) |
| `league_id` | str | league the card belonged to |
| `trade_id` | str | the card's per-deck uuid4 prefix |
| `key_source` | str | `impression` \| `local` — whether the PK is a real `deck_impressions` id or the degraded surrogate. Stored explicitly rather than inferred from the key's prefix, which is the kind of implicit encoding that rots. Never rewritten by a later tap: the key a row was minted under is a fact about the row |
| `reason` | str | layer-1 code: `value` \| `fit` \| `other`. A layer-2-first write derives it from the detail's parent |
| `detail` | str | layer-2 code: `value_giving` \| `value_getting` \| `value_other` \| `fit_outlook` \| `fit_new_weakness` \| `fit_duplicate` \| `fit_other` \| `other_player_keep` \| `other_player_avoid` \| `other_text`. **NULL is a first-class answer** — the user stopped at layer 1, which is the signal that that tile's options are wrong or missing |
| `free_text` | text | the user's own words, ≤500 chars, trimmed. **Stored here and nowhere else** — never an analytics property (SPEC §3.4); `trade_pass_layer2` carries only the boolean `has_free_text` |
| `switched_from` | str | the prior layer-1 reason when the user moved to another tile, else NULL. Derived server-side from the stored row, never taken from the client. A stored `detail` is deliberately **kept** across a switch (a refinement, not a reset) |
| `elo_signal_at` | str | ISO UTC of the Elo write this pass produced, or NULL when the reason suppressed it (SPEC §4). Doubles as the once-only guard: the write is claimed with `UPDATE … WHERE elo_signal_at IS NULL`, so no retry or re-tap double-counts a pass into ranking math |
| `created_at` | str | ISO UTC — the tap that passed the card |
| `updated_at` | str | ISO UTC — the most recent tap |

Indexes: `ix_trade_pass_reasons_user_league` on `(user_id, league_id)`.

**Player preference under "Neither" (SPEC §2a, D-080, 2026-08-19):** `other_player_keep` ("won't trade one of my players") and `other_player_avoid` ("don't want one of their players") joined the enum when the "Neither" tile — 47% of the first production burst, free text only — gained structured options. They are **two codes on purpose**: `keep` is a give-side keep-list signal and `avoid` a receive-side avoid-list signal, and those are different engine fixes. `detail` is a free-form `String` column, so this needed **no migration and no backfill** — the vocabulary lives in `database.PASS_REASON_LAYER2`. **Analysis caveat:** `other_text` did not change meaning but it did change *population* — before 2026-08-19 it was every "Neither" answer, after it is only the ones the two player codes did not absorb. Cohort any before/after `other_text` comparison on that date.

**Elo consequence (SPEC §4, model_config knob `pass_reason_elo_suppression`, default 1.0 = ON):** with the knob on, only `value_giving` keeps the pass's Elo write — it is the one answer that actually asserts "my side is worth more". `value_getting` would *invert* the signal; every `fit_*`, every `other*`, and every layer-1-only answer makes no valuation claim at all. Because layer-1-only always suppresses, a `value_giving` write lands at the **layer-2 tap**, not the tile tap. Knob at 0.0 ⇒ every reasoned pass writes Elo at the tile tap, exactly as today's ✕ does. Switching away from `value_giving` after the fact does **not** retract the signal (there is no negative-K correction path on this route) — it only cannot write a second one.

---

## `deck_candidate_sets`

**suggestion.telemetry** counterfactual layer (`docs/plans/matchmaking-engine/telemetry-scope.md`, D-scope-6) — one row per completed generation job **while the flag is on**: the full action set the serving policy chose from at ordering time — the post-gate pre-withhold deck (served + ghost cards) plus the untrimmed F7 exploration over-generation pool. Written by `server._log_deck_signal_impressions` (→ `save_deck_candidate_set`); soft-referenced from `deck_impressions.candidate_set_id` (no FK, house style). This is the "way to reconstruct the candidate set" the OPE literature requires — impossible to backfill, hence logged from day one.

| Column | Type | Notes |
|---|---|---|
| `candidate_set_id` | str PK | uuid4 hex |
| `deck_job_id` | str | generation job id (`_trade_jobs`) |
| `user_id` | str | user the deck was generated for |
| `league_id` | str | |
| `size` | int | member count (= `deck_impressions.candidate_set_size`) |
| `set_hash` | str | sha256[:16] over the sorted member `trade_hash`es — cheap same-set comparator across jobs |
| `candidates_json` | JSON text | `[{trade_hash, partner, give, receive, base_score, in_deck}]` — `in_deck` false only for exploration-pool members that were generated but trimmed before serving |
| `created_at` | str | ISO UTC |

Indexes: `ix_deck_candidate_sets_user_league` on `(user_id, league_id)`.

---

## `suggestion_trade_links`

**suggestion.telemetry** executed-trade tagging — one row per captured `sleeper_trades` transaction examined by the matcher (`suggestion_telemetry.match_league_trades`, hooked after every `sync_league_trades` pass in `session_init`'s background daemon; idempotent on `transaction_id`, so every sync retries any leftovers). Similarity rule (D-scope-5, glossary "Suggestion-trade match"): same unordered manager pair, `served_at ≤ traded_at ≤ served_at + suggestion_match_lookback_days`, direction-aligned asset tokens (players by id; owned picks → `pick:{season}:r{round}:{orig_roster}`; generic picks relax to round-only pairing); **exact** = both sides fully pair, **partial** = overlap ≥ `suggestion_match_min_overlap` with ≥1 match per side; best candidate = exact > overlap > recency. Only telemetry-era impressions (non-NULL `assets_json`) are matchable. Multi-team / unresolvable trades keep a row with `match_type` NULL so the ratio denominator stays honest. Rows can also be written by the operator-run retro backfill (`scripts/backfill_suggestion_links.py`, 2026-08-16): it covers pre-telemetry trades only (the live matcher owns the telemetry era) and marks its matches `retro_exact` — exact serve-time trade_hash identity, the only semantics possible without historical `assets_json`.

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | autoincrement |
| `transaction_id` | str UNIQUE | `sleeper_trades.transaction_id` |
| `league_id` | str | |
| `was_recommended` | int | 1 iff a **rendered** (non-ghost) suggestion matched — per-league ratio `SUM(was_recommended)/COUNT(*)` is the always-on endorsement dashboard (`GET /api/admin/suggestion-telemetry/ratio`) |
| `matched_impression_id` | str | best non-ghost match (soft ref → `deck_impressions`) |
| `match_type` | str | `exact` \| `partial` \| `retro_exact` (backfill) \| NULL |
| `overlap_score` | float | matched-token share of the larger asset set (1.0 on exact/retro_exact) |
| `ghost_impression_id` | str | best **ghost** match — the incrementality read: a withheld suggestion that executed anyway |
| `ghost_match_type` | str | `exact` \| `partial` \| `retro_exact` (backfill) \| NULL |
| `ghost_overlap_score` | float | |
| `traded_at` | str | ISO UTC (from the Sleeper transaction) |
| `computed_at` | str | ISO UTC |

Indexes: `ix_suggestion_trade_links_league` on `league_id`; unique `uq_suggestion_link_txid` on `transaction_id`.

---

## `bakeoff_runs`

**trade.bakeoff** three-model bake-off run ledger (`docs/plans/three-model-bakeoff/PLAN.md` §5, scope block `scope-phase3.md`) — **one row per organic trade job while the flag is on**, the per-JOB half of the record; the per-CARD half rides `deck_impressions.model_arm` / `.arm_rank`. Written best-effort by `server._run_trade_job` (→ `save_bakeoff_run`) after the deck is assembled; a failure here never fails the job. Written for **every** run including a superseded one — this is a RUN ledger, and the empty-arm/cost questions it answers are just as valid for a deck nobody saw.

| Column | Type | Notes |
|---|---|---|
| `run_id` | str PK | uuid4 hex |
| `deck_job_id` | str | `_trade_jobs` job id — joins to `deck_impressions.deck_job_id` |
| `user_id` | str | |
| `league_id` | str | |
| `arm_order` | JSON text | the team-draft rotation this deck used. Since the 2026-08-18 composition decision the participants are **groups**, e.g. `["gen_v2","current_divergence","current_consensus"]`; with `bakeoff_group_size` = 0 they are arms, e.g. `["current","gen_v2","baseline"]`. The column name is kept because that is what it has always stored. Randomised **per deck**, seeded on `league_id` + ISO week — stable for a league within a week (so a re-run reproduces the deck) and rotating between weeks (so no arm is permanently in slot 3) |
| `served_arm` | str | `current` during Phase-4 dark validation (three arms generated and logged, ONE served); NULL once interleaved serving is lit |
| `deck_size` | int | cards in the **interleaved** deck (30 at the default composition: three groups of ten, less any group that served short) — computed and logged even in dark mode, where it is not what got served |
| `total_ms` | int | wall clock for all three generations (they run sequentially on one thread) |
| `groups_json` | JSON text | `{group_key: {arm, basis, quota, filled, short, realloc, pool, composed, served, lane_split_active}}` — the deck-composition accounting (operator decision 2026-08-18, `scope-composition.md`). **`short` is why this column exists:** the per-(group, lane) UNDER-FILL, e.g. `{"value": 0, "outlook": 3}`. `window` is **24.7%** of live supply (measured, 18 runs / 527 cards on 2026-08-19: `current_consensus` 28.1%, `gen_v2` 16.2%, `current_divergence` **0%**), so no group can find five outlook cards reliably — whether an arm can produce outlook-basis ideas *at all* is one of the findings this test is for, and it is invisible if a backfill hides it. `pool` is the supply the group had to draw on (`{value, window, (none)}`); `filled` what it managed (`{value, outlook, fill}`); `realloc` (`{value, outlook}`, D-086) how many slots each lane absorbed from the other lane's unfillable quota, drawn from its own bucket — which is why a lane's `filled` count can exceed its `quota` while `short` still reports the full under-fill against the nominal ask; `composed` / `served` the list length before and after the draft's duplicate suppression. `lane_split_active` is **false** when no card in the pool carried a lane at all — the outlook axis is undefined for that deck (user has no window direction, or `trade.lanes` is off) so the split went inert rather than serving an empty group. `{}` when `bakeoff_group_size` = 0 kills composition. Written in dark mode too: measuring under-fill before Phase 5 lights interleaved serving is exactly what dark validation is for |
| `arms_json` | JSON text | `{arm: {cards, gen_ms, empty, forfeits, served, error, fairness_threshold, trade_intent}}`. `empty` is the numerator of the empty-arm rate (PLAN.md §3.2 — arm `gen_v2` is divergence-only and expected to under-produce; that is **data**, never an error). `forfeits` counts rotation slots the arm could not fill. `served` counts cards the draft credited to it. `error` is non-NULL only when the arm raised — a raising arm is recorded and forfeits, it never fails the job |

| `groups_json` | JSON text | `{group_key: {arm, basis, quota, filled, short, pool, composed, served, lane_split_active}}` — the deck-composition accounting (operator decision 2026-08-18, `scope-composition.md`). **`short` is why this column exists:** the per-(group, lane) UNDER-FILL, e.g. `{"value": 0, "outlook": 3}`. `window` is only ~19% of live divergence supply, so the divergence groups routinely cannot find five outlook cards, and arm `gen_v2`'s lane mix has never been observed at all — whether an arm can produce outlook-basis divergence ideas *at all* is one of the findings this test is for, and it is invisible if a backfill hides it. `pool` is the supply the group had to draw on (`{value, window, (none)}`); `filled` what it managed (`{value, outlook, fill}`); `composed` / `served` the list length before and after the draft's duplicate suppression. `lane_split_active` is **false** when no card in the pool carried a lane at all — the outlook axis is undefined for that deck (user has no window direction, or `trade.lanes` is off) so the split went inert rather than serving an empty group. `{}` when `bakeoff_group_size` = 0 kills composition. Written in dark mode too: measuring under-fill before Phase 5 lights interleaved serving is exactly what dark validation is for |
| `arms_json` | JSON text | `{arm: {cards, gen_ms, empty, forfeits, served, error, fairness_threshold, trade_intent, diagnostics}}`. `empty` is the numerator of the empty-arm rate (PLAN.md §3.2 — arm `gen_v2` is divergence-only and expected to under-produce; that is **data**, never an error). `forfeits` counts rotation slots the arm could not fill. `served` counts cards the draft credited to it. `error` is non-NULL only when the arm raised — a raising arm is recorded and forfeits, it never fails the job. `diagnostics` (D-087, 2026-08-19) is the arm's **per-stage kill counts** — `{}` for the engine arms, and for arm `gen_v2` `GenerationReport.kill_counts()` (`S0_boarded_opponents`, `S0_unranked_opponents`, `S1_no_board_overlap`, `S1_no_centerpiece`, `S2_considered`, `S3a_composition`, `S3a_net_cap`, `S3a_pick_band`, `S3b_feasibility`, `S3c_dual_board_ir`, `S3d_fairness_band`, `S4_survivors`, `S6_emitted`, `starvation_reason`) plus the post-generation `S7_intent_filter` / `S7_headliner_cap` / `S7_served_to_deck` counts `bakeoff_runner.gen_v2_cards` applies itself. `starvation_reason` is non-NULL only when the batch never ENUMERATED a candidate (`no_boarded_opponents` / `no_board_overlap` / `no_divergence`) — the three causes that were indistinguishable while `cards: 0` was the only signal |
| `config_json` | JSON text | `{"base": <arm `current`'s effective `trade_service` config>, "arm_delta": {arm: {keys that differ}}}`, snapshotted **inside each arm's own context** (so arm A's reflects `MODEL_A_PROFILE`). `model_config` has no `updated_at`, so a knob's change date is otherwise unknowable after the fact and the whole experiment rests on knowing which configuration produced each card. Stored whole rather than hashed — a fingerprint would say the config changed without saying to what. ~5 KB base plus a handful of delta keys; arm C's delta is empty. Deliberately **not** a config-versioning system: one snapshot per run, no history, no dedup |
| `agreement_json` | JSON text | `{"armA+armB": n}` — served cards both arms proposed (first picker credited, the loser recorded). High `baseline+current` means the 2026-08-16 fixes changed little; `current+gen_v2` is the interesting number for a future blend |
| `created_at` | str | ISO UTC |

Indexes: `ix_bakeoff_runs_league` on `league_id`; `ix_bakeoff_runs_job` on `deck_job_id`.

**"Was this comparison clean?"** — the question PLAN.md §6 needs answered before any per-arm rate is quoted. Two gates the client can move under you (the fairness toggle and the #172 intent chip) and both stay visible to testers, so both are checked. One `GROUP BY`, no archaeology:

```sql
SELECT model_arm,
       group_key,
       COUNT(DISTINCT fairness_threshold) AS thresholds,
       COUNT(DISTINCT trade_intent)       AS intents,
       COUNT(*)                           AS impressions
FROM deck_impressions
WHERE model_arm IS NOT NULL
GROUP BY model_arm, group_key;
```

More than one distinct threshold — or intent — within the population being compared means the arms differ in admission bar as well as in model, and the comparison must be sliced by that column (or restricted to one value) before it means anything. Pinned by `test_bakeoff_serving.py::test_comparison_clean_query_answers_itself_from_the_table`, which executes exactly this query so it cannot rot into documentation-only.

**Grouping by `(model_arm, group_key)`, not by `model_arm` alone, is deliberate.** The three groups are not three arms:

- **Groups 1 vs 3 is the head-to-head.** `current_divergence` vs `gen_v2` — both divergence, both ten cards, both quota'd 5 value / 5 outlook, interleaved together in one rotation with position balanced across decks. This is the arm comparison. Pair within user; slice by threshold and intent.
- **Group 2 is a consensus reference slice with no arm-C counterpart.** Arm `gen_v2` is divergence-only *by construction*, so no consensus arm-C card exists or ever will. `current_consensus` says how consensus supply performs against divergence supply **within arm `current`**, and it keeps the deck realistic. Reading `current` vs `gen_v2` across all three groups silently compares arm `current`'s consensus cards against arm `gen_v2`'s divergence cards and blames the difference on the model.

**Per-(group, lane) under-fill** — the other first-class read, from `groups_json`:

```sql
SELECT json_extract(g.value, '$.arm')             AS arm,
       g.key                                      AS group_key,
       AVG(json_extract(g.value, '$.short.value'))   AS value_slots_missed,
       AVG(json_extract(g.value, '$.short.outlook')) AS outlook_slots_missed,
       COUNT(*)                                   AS runs
FROM bakeoff_runs r, json_each(r.groups_json) g
GROUP BY g.key;
```

(SQLite form; on Postgres use `jsonb_each` / `->>`.) A group that never fills its outlook quota is a finding about that arm's supply, not a bug — which is precisely why the default fill policy leaves the hole rather than topping it up.

---

## `deck_suppressions`

TikTok-discovery **F3 fatigue & durable suppression** (flag `deck.fatigue`, `docs/plans/tiktok-discovery/prds/F3-fatigue-suppression.md`). One row per decline / proposal-kill: near-duplicates (same centerpiece + same shape bucket + package value within ±`fatigue_decline_value_band`) are removed from that user's decks until `expires_at`, after which the row grants exactly **one** low-exposure retest card; a `pass` on the retest re-arms the row (resolved lazily at the next generation — the swipe path stays write-free). Written by `save_deck_suppression` from the disposition route's decline hook (re-declaring a live concept refreshes its window instead of inserting a duplicate). Soft pass-fatigue is **not** stored here — it is derived on read from `deck_impressions ⨝ deck_outcomes`.

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | autoincrement |
| `user_id` | str | the suppressed user's deck |
| `league_id` | str | |
| `centerpiece_id` | str | highest-consensus asset in the declined package |
| `shape_bucket` | str | `"1x1"`, `"2x1"`, … |
| `package_value` | float | consensus give+receive value at decline time (per-player `elo_to_value` over seed Elos); NULL ⇒ the ±band test is skipped (centerpiece+shape decide) |
| `declined_at` | str | ISO UTC |
| `expires_at` | str | `declined_at` + `fatigue_decline_suppress_days` |
| `retested_at` | str | when the ONE post-window retest card was served (NULL until then) |
| `retest_trade_hash` | str | F1 `trade_hash` of the served retest card |
| `lifted_at` | str | the user's "Undo" (`POST /api/trades/suppressions/undo`); a lifted row is permanently inert |
| `created_at` | str | ISO UTC |

Indexes: `ix_deck_suppressions_user_league` on `(user_id, league_id)`.

---

## `deck_fatigue_resets`

F3 "Refresh my deck" marker — one row per (user, league). Soft-fatigue reads (`load_deck_fatigue_events`) ignore viewed/pass events before `reset_at`; decline suppressions, not-interested and untouchables are unaffected. Written by `set_deck_fatigue_reset` from `POST /api/trades/generate` with `refresh_fatigue: true` (flag-gated).

| Column | Type | Notes |
|---|---|---|
| `user_id` | str PK (composite) | |
| `league_id` | str PK (composite) | |
| `reset_at` | str | ISO UTC of the latest refresh |

---

## `deck_replenish_log`

TikTok-discovery **F10 deck replenishment** (flag `deck.replenishment`, `docs/plans/tiktok-discovery/prds/F10-deck-replenishment.md`). One row per (user, league, ISO week) the weekly replenishment pass inside `/api/cron/daily-tick` pre-generated a deck for. The unique constraint is the idempotency gate: re-running the tick in the same week skips both regeneration and the `deck_replenished` push (hard 1/week/league cap).

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | autoincrement |
| `user_id` | str | recipient |
| `league_id` | str | league the deck was generated for |
| `iso_week` | str | e.g. `2026-W30` |
| `deck_size` | int | cards in the pre-generated deck (0 = generated empty, no push sent) |
| `expired_count` | int | prior-deck cards past the 7-day `TradeCard` expiry that dropped from the new deck (only mentioned in push copy when > 0) |
| `created_at` | str | ISO UTC |

Unique: `uq_deck_replenish_week` on `(user_id, league_id, iso_week)`.

---

## `user_taste`

TikTok-discovery **F5 trade-taste vectors** (flag `deck.taste_vectors`, `docs/plans/tiktok-discovery/prds/F5-taste-vectors.md`). Per-user decayed attribute-preference weights — the Monolith long/short interest split without embeddings. One lazily-created row per (user, attribute key), updated synchronously on every F1 `deck_outcomes` write (`w[a] ← w[a]·exp(−Δt/τ) + r(action)`, attrs read from the impression's frozen `features_json.taste_attrs`) and GC'd on read/update when **both** decayed weights fall below `taste_epsilon` — so the table stays bounded per user by the attribute-space cardinality (~50 fixed keys + one per league-mate + priors). Rows whose `attr` carries the `prior:` prefix hold the **board-derived prior** (2026-07-26 PRD amendment): rewritten wholesale by `replace_user_taste_prior` on every board save (rank3, tiers/save, copy-from-format, anchor/save, rankings/reorder), never touched by outcome updates, folded into the effective long vector at read time. User-scoped by design (no `league_id`): taste follows the manager; partner attrs are global user ids. All math lives in `backend/taste_service.py`.

| Column | Type | Notes |
|---|---|---|
| `user_id` | str PK (composite) | |
| `attr` | str PK (composite) | attribute key, e.g. `recvpos:RB`, `pick:premium`, `partner:<user_id>`, `prior:cpos:PICK` |
| `w_short` | float | short-interest weight (τ = `taste_tau_short_days`, 21d); always 0 on `prior:` rows |
| `w_long` | float | long-interest weight (τ = `taste_tau_long_days`, 180d); carries the prior mass on `prior:` rows |
| `updated_at` | str | ISO UTC of the last decay+reward write — the lazy-decay anchor |

---

## `archetype_auditions`

TikTok-discovery **F7 exploration slots & archetype audition** (flag `deck.exploration`, `docs/plans/tiktok-discovery/prds/F7-exploration-slots.md`). One **global** row per archetype label (`deck_impressions.archetype` — lane today): the follower-blind staged pool. New/low-data archetypes (all-time viewed < `audition_min_views`, and not one of the established lanes `window`/`value`, which are grandfathered straight to `general`) enter `test` and serve ONLY via wildcard slots across all users; at `viewed_impressions ≥ audition_min_views` they **graduate** to `general` when like-rate ≥ `audition_like_rate_frac` × the global base rate, else **retire** for `audition_retire_days` (excluded from decks and wildcard draws), then re-enter `test` with a fresh window. State machine is evaluated **lazily at wildcard-draw time** by `server._audition_statuses` (no cron); counts refresh from `deck_impressions ⨝ deck_outcomes` (viewed-gated — likes counted only on viewed impressions). `entered_at`/`retired_at` double as the transition log.

| Column | Type | Notes |
|---|---|---|
| `archetype` | str PK | archetype label (lane today, e.g. `window`, `value`) |
| `status` | str | `test` \| `general` \| `retired` |
| `viewed_impressions` | int | viewed count in the CURRENT audition window (since `entered_at`) |
| `likes` | int | liked-and-viewed count in the current window |
| `entered_at` | str | ISO UTC — current window start |
| `retired_at` | str | ISO UTC — set while `status='retired'`; re-audition unlocks at `retired_at + audition_retire_days` |

---

## `players`

Canonical player reference, synced from Sleeper bulk payload (skill positions, Active or prospects). Re-synced if empty or `last_synced` > 24h.

**Freshness (rookie-draft M0, 2026-08-06).** That 24 h gate only ever re-read the on-disk cache, which itself had no refresh path — so the table could sit five months stale without anything noticing. `POST /api/cron/players-refresh` now re-fetches the Sleeper dump daily and calls `sync_players` **directly**, bypassing `needs_player_sync()` (the data is known-new and the gate would skip it); `sync_players` stamps `last_synced` itself. Every value below — `rookie_year`, `team`, `years_exp` — is only as true as the last refresh, which is why THE rookie predicate is freshness-sensitive rather than merely correct. See [runbook.md § Player-cache refresh](runbook.md).

| Column | Type | Notes |
|---|---|---|
| `player_id` | str PK | |
| `full_name`, `first_name`, `last_name` | str | |
| `position` | str | QB / RB / WR / TE |
| `team` | str | abbr or null (FA) |
| `age`, `birth_date` | int / str | |
| `years_exp` | int | 0=rookie, null=prospect. Counts **accrued** NFL seasons, so it is NOT a draft-class field (a 2023 UDFA who spent two years on practice squads reads 1) |
| `rookie_year` | str | `"YYYY"` draft class from Sleeper's `metadata.rookie_year` (#207) — the exact class field `years_exp` isn't. NULL when Sleeper omits it (camp bodies / UDFAs) or serves the bogus `"0"`; readers then fall back to `years_exp == 0 AND team IS NOT NULL`. That pair IS the single pinned rookie predicate — [cross-client-invariants.md § Rookie predicate](cross-client-invariants.md) — reachable **only** through `load_rookie_player_ids(season)` (SQL mirror of `draft_status.is_rookie_row`) or, for the exact-year question the class-load monitor asks, `count_rookie_class_rows(season)`. Do not hand-roll a third rule: `load_rookies` was exactly that and has been rebased. No rows exist for a class until Sleeper loads it ~late April |
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
| `season`, `round` | int | **`season` is BOUNDED by the league's pick horizon (#355, flag `picks.league_horizon`).** It is *not* `current_season … current_season + 3`: a league carries exactly `draft_status.PICK_HORIZON_CLASSES` (3) consecutive rookie classes **anchored to the first class that has not yet been drafted**, so the window ROLLS when a draft completes (pre-draft 2026 league ⇒ 2026-2028; once its draft reads `complete` ⇒ 2027-2029). Derived by `draft_status.pick_horizon()`. A season the platform itself reports a traded pick for widens the window (existence proof, capped at `PICK_HORIZON_MAX_CLASSES`). Flag off ⇒ the historical fixed `seasons_ahead` window. |
| `owner_user_id`, `owner_username` | str | current owner |
| `original_roster_id`, `original_user_id`, `original_username` | str | |
| `is_traded` | int | 1 if ownership changed |
| `pick_value` | float | `compute_pick_value()` output at sync time, on the **0–100 round-tier scale** (mid-1st ≈ 67.5), NOT the 0–10000 player value space. Kept for **pick-share** ratios (`_user_pick_share`, outlook seeds). The LEGACY engine bridges it via `elo_to_value(1200 + 6·pick_value)` in `trade_service.dynasty_value`; the v2/v3 engine instead reads Elo maps primed with `1200 + 6·pick_value` per injected pick (`server._pick_asset_elos`, #185). |
| `pool_value` | float | **#158** — pick value on the **engine/calculator scale** (`elo_to_value` units), = `pick_pool_value(round, years_out)` = the generic-ladder **Mid**-tier value of the round, year-discounted (0.85/yr) in value space. `years_out=0` equals the generic "Mid <round>" pool pick exactly. This is what the calculator + suggestions price on (distinct from the legacy `pick_value`). Shared ladder lives in `backend/pick_values.py`. |
| `platform` | str | **#158** — the **LEAGUE's** provenance: `'sleeper'` \| `'mfl'` \| `'espn'`. ⚠️ **This column's rule CHANGED in W3 (ADR-010).** It used to read "ESPN never writes rows (players-only)"; ESPN rows now exist, written by a league's own members. `platform` says where the league lives; `source` (below) says who asserted the row. They answer different questions and both are load-bearing — the two engine guards read `platform`, the containment reads `source`. |
| `source` | str | **W3 M-A (ADR-010)** — the **ROW's** provenance. `NULL` or `'platform'` = platform-written; `'user'` = a league member asserted it. **Every pre-W3 row is NULL and NO BACKFILL RUNS.** |
| `assigned_by` | str | W3 — FTF `user_id` of the last editor (`'user'` rows only). |
| `assigned_at` | str | W3 — ISO-8601 UTC, and **also the optimistic-concurrency token**: `PUT /api/league/pick-assignments/<pick_id>` carries the value it read and the UPDATE's WHERE clause compares it. `NULL` on a never-assigned row. |
| `synced_at` | str | |

**Sync (revived #158):** `sync_draft_picks()` (Sleeper: pristine grid × traded-picks overlay) runs on the **session_init background daemon** per league; MFL picks normalize into the same table via `server._sync_mfl_owned_picks()` at link/import. Both gated on `picks.owned_sync` (default off). Delete+bulk-insert per league via `replace_draft_picks()`. `rounds` comes from Sleeper `settings.draft_rounds` (was hard-coded 3, which dropped 4th-round picks in 4-round leagues).

**Pick horizon (#355, 2026-08-19, flag `picks.league_horizon`).** The pristine grid spans the league's REAL horizon, not a fixed offset from `current_season` — see the `season` row above. The old fixed window invented a 4th class for exactly the **pre-draft** leagues (post-draft ones were already correct, because #228's current-season exclusion shifted their anchor by one), and 12.8% of served cards ended up offering a 2029 pick that did not exist. Because this is a **replace**-sync, no migration is needed in either direction: stale out-of-horizon rows are deleted on the league's next sync, and flipping the flag off rebuilds them. MFL is unaffected — it enumerates the real `futureDraftPicks` export rather than synthesising a grid.

### The containment rule (W3 M-A, ADR-010) — read this before adding a reader

`load_draft_picks(league_id, owner_user_id=None, source='platform', include_contested=False)` **defaults to platform-only**, and `NULL` reads as platform. So every read site written before W3 returns byte-identical rows in byte-identical order, for every league and every provenance mix, with no backfill. **That default IS the containment**, not a table split.

- `'platform'` (default) → `source IS NULL OR source = 'platform'`
- `'user'` → `source = 'user'`
- `'any'` → no source predicate

When the result *can* contain user rows and `include_contested` is False, **contested** and **orphaned** slots are dropped by a **row filter**. Nulling `pool_value` instead is forbidden: `server._power_picks_by_owner` re-derives a price from a NULL `pool_value`, so nulling would silently re-price the very row the rule withholds.

There are exactly **seven** read sites (`_roster_eveners`, `_user_pick_share`, `_run_trade_job`, `_trade_evaluate_impl`, `get_league_picks`, `_owned_pick_assets`, `_power_picks_by_owner`) and an AST test in `backend/tests/test_pick_assignment.py` enumerates them. An **eighth** — or one of the seven dropping its opt-in — **fails the test**; that is deliberate, not an obstacle to route around.

**W3 M-C (2026-08-08, flag `picks.assign_tradeable`)** opted all seven in together. Each now passes `source=server._pick_read_source()`, which is `'platform'` with the flag off (the shipped default, so the paragraph above still describes the shipped state) and `'any'` with it on. A read site passing a **literal** `PICK_SOURCE_ANY` would ignore the kill switch and is failed by its own AST test. Only the assignment surface (`seed_pick_grid`, `_assignment_slots`, `_assignment_grid`, `pick_assignment_put_route`) may name a literal provenance. `database.has_assigned_picks(league_id)` is the memoised "does this league hold any asserted row" probe behind M-C's engine guard and `picks_supported`; it is invalidated by the same hook as the contested cache and **fails closed**.

`replace_draft_picks(league_id, rows, preserve_source=None)` scopes its DELETE to one provenance: a writer only ever deletes rows it could have written. Platform callers keep the default; only W3's assignment projection passes `'user'`.

`pick_id` has exactly one constructor — `database.make_pick_id()`. Round is unpadded, so a `pick_id` is **not** lexicographically sortable. Its unique key has no provenance dimension, so one slot cannot hold both a platform row and an asserted one; the seeder skips such a slot (the platform wins).

---

## `recorded_picks`

**W3 M-D (2026-08-08, flag `draft.manual_picks`, ADR-010)** — the live offline-draft feed. An off-platform rookie draft (the only shape ESPN's has, per the operator ruling that ESPN has no rookie-draft concept) leaves no platform object to read, so this table is the only record that a pick happened. It projects into `GET /api/draft/board`'s ESPN branch `picks[]` and **nowhere else** — it never writes `draft_picks`, never sets `leagues.draft_status*`, and never marks a draft complete.

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `league_id` | str | |
| `season`, `round`, `slot` | int | `slot` = 1-based position in `settings.order` (the M-A assignment grid's numbering), not a platform value |
| `overall` | int | **1-based, league-wide pick number.** ⚠️ Legitimate **only here** — it must never leak onto a `draft_picks` row, whose grain is `(league, season, round, original_roster)` and whose `pick_id` format cannot express a slot. `backend/tests/test_recorded_picks.py`'s D18 tests pin this both structurally (AST — the write functions below never reference `draft_picks_table`) and behaviorally (a full recording batch leaves every `draft_picks` row byte-unchanged) |
| `picking_team_id` | str | `league_members.user_id` on the clock. Client-supplied, **defaulted from the M-A assignment grid's owner for that slot** (recording is "confirm, not select") but editable when the grid was wrong. Nullable — orphaned/never-assigned slots may still be recorded with no team |
| `player_id` | str, not null | OUR id space (the same space `players.player_id` and every other client-facing player id use) |
| `recorded_by` | str, not null | FTF `user_id` of the recorder. **Any linked league member may record — no designated-recorder role** |
| `event_id` | str | The client offline-queue's uuid (`mobile/src/api/_queue.ts`'s `uuidv4()`). Stored for audit and for matching a `rejected[i]` entry back to a queue item — **not** the uniqueness key, since two devices recording the same physical pick will not share a uuid |
| `recorded_at` | str | ISO-8601 UTC, **server time** (`client_ts` in the request is untrusted and not stored) |
| `voided_at` | str | Nullable. `IS NULL` = live. **Undo is non-destructive — never a DELETE.** Set by `POST /api/league/recorded-picks/void`; a later `record_draft_picks` call at the same slot resets it back to `NULL` (re-recording a voided pick is how you reverse an undo) |

**Unique constraint `uq_recorded_pick_slot` on `(league_id, season, overall)`** — this triple is the offline-queue's idempotency key (plan §6.5), **not** `event_id`. A replayed batch (the client's retry-on-reconnect path) produces `deduped`, never a duplicate row. There is deliberately no partial unique index on `voided_at IS NULL`: a correction is an UPDATE in place, not a void-then-insert, so exactly one row exists per physical slot forever (dialect-portable across SQLite/Postgres, mirroring the reasoning `mock_drafts` already documents for its own one-active-row rule).

**Write surface — exactly three functions, all in `backend/database.py`:**

- `record_draft_picks(league_id, season, rows, recorded_by)` — idempotent batch. Per row: no existing row at `(league_id, season, overall)` → insert (`accepted`); existing live row, same `player_id` → `deduped`; existing live row, different `player_id` → UPDATE in place (`accepted`, a correction); existing **voided** row, any `player_id` → UPDATE in place (`accepted`, revives it). Validated before any write: `round`/`slot`/`overall` positive ints bounded against the league's stored `pick_assignment_settings` when one exists (`slot_out_of_range`); `player_id` must resolve via `load_players_by_ids` (`unknown_player`); a non-empty `picking_team_id` must be a current `league_members` row (`not_in_league`). A batch never partially corrupts the table — every row is independently classified before the write executes, and rejected rows never touch the DB.
- `void_recorded_pick(league_id, season, overall, actor)` — `SET voided_at = now() WHERE … AND voided_at IS NULL`. Never a DELETE.
- `load_recorded_picks(league_id, season)` — live rows only (`voided_at IS NULL`), ordered by `overall`. This is what the board route reads and passes into `draft_board_service.assigned_board(..., recorded=…)`.

**Routes:** `POST /api/league/recorded-picks` (batch; response `{accepted, deduped, rejected:[{index, reason}]}` — the **same reconciliation shape** `mobile/src/api/events.ts` already parses) and `POST /api/league/recorded-picks/void`. Both gated on `draft.manual_picks`; flag off ⇒ 404 `feature_disabled` before any session work, and `GET /api/draft/board`'s ESPN branch does not even read the table — the flag gates the **read**, not just the writes, so a row left over from a flag that was flipped on and back off can never leak into a flag-off board (verified in `backend/tests/test_recorded_picks.py`).

**Board wiring:** `draft_board_service._recorded_picks_projection()` maps live rows to the identical `picks[]` shape every other platform's board renders (`round`, `pick_no` = `overall`, `slot`, `player_id`, `name`, `position`, `team`, `picked_by_user_id`, `picked_at`). `assigned_board`'s `drafted` set (fed to `_undrafted`) is derived from this projection, so a recorded player disappears from `undrafted[]` through the same code path Sleeper/MFL boards use — **one renderer, no second source of truth**. `state` becomes `live` once ≥1 pick is recorded and `complete` once every `order[]` slot has one.

**See also:** `docs/runbook.md` § Pick-recording queue integrity for the client offline-queue's zero-tolerance contract.

---

## `notifications`

In-app bell inbox. **Not a push mirror** — `_send_typed_push` has never written a row here, and rows are written beside a push at the call site, never inside the dispatcher (see `docs/cross-client-invariants.md` § Notification type strings for why, and `living-memory/LLD.md`).

Nine `type` values, a cross-client enum: `trade_match`, `trade_accepted`, `trade_declined`, `referral_joined`, `league_member_joined`, `league_member_unlocked_trades`, `match_expiring`, `deck_replenished`, `counter_offer`.

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `user_id` | str | |
| `type` | str | cross-client enum — see above |
| `title`, `body` | str | |
| `metadata_json` | JSON text | type-specific context (default `"{}"`). `match_id` is the idempotency key for `match_expiring`; `league_id` + `joined_count` + `new_usernames` carry the `league_member_joined` coalescing state |
| `is_read` | int | 0=unread, 1=read |
| `created_at` | str | |
| `dismissed_at` | str \| NULL | ISO UTC when the user cleared the row; **NULL = live**. `get_notifications` filters non-NULL out of both legs. Distinct from `is_read` on purpose — "I have seen this" and "I am done with this" are different facts. Rows are never deleted: they are the only history this surface has |

**Read shape:** `get_notifications` returns ALL live unread + the most recent 20 live read, `created_at DESC`. Ordering is recency-only — there is no priority or expiry column, by decision (GD-3). An unread row therefore never ages out.

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

Daily **consensus** value snapshots (backlog #57 / player profiles #17). `elo_history` logs each user's *personal* Elo; this table logs the market side — one row per universal-pool player per scoring format per day, written by `POST /api/cron/value-snapshot` **plus a fallback guard on `POST /api/cron/hourly-tick`** (market-data readiness 2026-07-26: if today's UTC date is missing rows for any scoring format, the hourly tick writes the snapshot via the shared `server._write_daily_value_snapshots`; `database.value_snapshot_formats_for` is the cheap presence check). Both writers share the `uq_value_snapshot` upsert, so they can never duplicate. The DynastyProcess-seeded universal pool is rebuilt from the live CSV on every boot, so yesterday's consensus numbers are otherwise unrecoverable; this is pure retention so value-history charts, the movers digest (#33), and Wrapped (#46) have history to draw on.

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

**Index (ADR-011, 2026-08-14):** `ix_pvh_format_date` on `(scoring_format, snapshot_date)` — the recap's league-wide query (`WHERE scoring_format = ? AND snapshot_date IN (…)`) had no leading-column match against `uq_value_snapshot` (which leads with `player_id`) and would full-scan.

---

## `league_roster_history`

Append-only **ownership-side** snapshots (ADR-011, #46 Wrapped P0) — `player_value_history` logs the market side daily; this logs who held which roster, weekly. The half `league_members.roster_data` was overwriting on every sync. Written by three triggers through one precedence-aware upsert (`upsert_roster_snapshots`): on-sync (beside the two `league_members` writers, own transaction after theirs commits), the `daily-tick` weekday-gated sweep (server-side fetch, all four platforms — YR-8), and `POST /api/cron/roster-snapshot`. Flag `market.roster_history` gates the writes, never the table.

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `league_id` | str | |
| `team_key` | str | **The platform-native team slot, never derived from a user id** (SWID rotates): `sleeper:<lid>.r<roster_id>` / `espn:<lid>.t<team_id>` / `mfl:<lid>.f<franchise_id>` / `fleaflicker:<lid>.t<team_id>`. Weak fallback `sleeper:<lid>.u<user_id>` when the roster map is unavailable |
| `team_key_quality` | str | `'strong'` \| `'weak'` — the recap declines to chart weak-keyed teams rather than fragmenting them silently |
| `platform` | str | `sleeper` \| `espn` \| `mfl` \| `fleaflicker` |
| `owner_user_id` | str, nullable | **Re-stampable attribute, never part of the key** — resolved forward at link time (`restamp_roster_history_owner`); synthetic member ids are stored as NULL |
| `scoring_format` | str | one format per league (`leagues.default_scoring`) |
| `period_key` | str | ISO-week bucket label, **ISO week-numbering year** (`'2026-W33'`; 2025-12-29 ⇒ `'2026-W01'`) — never an instant |
| `period_kind` | str | `'week'` today; `'day'` reserved |
| `snapshot_date` / `snapshot_at` | str | `"YYYY-MM-DD"` (the pvh join key) / ISO UTC instant |
| `player_ids` | JSON text | sorted array — the input of record |
| `starter_ids` | JSON text, nullable | the platform-**set** lineup (the fact; the optimal lineup is an analysis, computed at read time) |
| `pick_ids` | JSON text, nullable | `draft_picks.pick_id`s, uncontested/unorphaned only |
| `pick_ids_excluded` | JSON text, nullable | slots this team asserted that the contested/orphaned filter withheld — non-empty ⇒ recap suppresses pick flow for the league |
| `pick_source` | str, nullable | `'platform'` \| `'user'` \| `'mixed'` (ADR-010: `'user'` is never rendered as fact) |
| `roster_hash` | str | 16-hex set-semantics hash; suppresses EXTRA intra-week sync writes only — **never the weekly write** |
| `changed_from_prev` | int, nullable | 0/1 vs the team's previous period; NULL = first observation |
| `player_count` / `valued_player_count` | int | coverage pair — K/DEF/deep-bench ids have no pvh row, ever |
| `team_value` | float, nullable | `compute_power_rankings` consensus-basis players total. **NULL, never 0, when nothing prices.** Renderers grey NULL or `valued < 0.8 × count`, never interpolate |
| `team_value_picks` | float, nullable | pick capital, separate pipeline (pool_value) |
| `value_basis_date` | str, nullable | the pvh `snapshot_date` actually used (nearest ≤) |
| `in_season` | int, nullable | NULL in P0 |
| `source` | str | `'sync'` \| `'weekly'` \| `'backfill'` — **precedence, not recency**: weekly outranks sync. Doubles as the rollback lever and the cron liveness detector |

Constraint: `uq_roster_snapshot` on `(league_id, team_key, scoring_format, period_key)`. Indexes: `ix_lrh_team_period`, `ix_lrh_league_period`, `ix_lrh_owner_period`. Volume: ~240 rows/league-season. Retention: one policy with `player_value_history` (ADR-011).

---

## `league_board_history`

Weekly **complete** board snapshots per member (C5/C6, YR-3 — ADR-011). Deliberately not a fork of `elo_history`, which stays as the event log: changed-only writes cannot rebuild a board at date D, it has no uniqueness constraint, and row-per-player weekly is ~270× these rows. Read accessors (P3) must take a caller identity and assert league membership; there is no public-URL read path (the surviving half of D-P1-12).

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `user_id` / `league_id` / `scoring_format` | str | |
| `period_key` / `snapshot_date` / `snapshot_at` | str | as `league_roster_history` |
| `elos` | JSON text | `{player_id: round(elo,1)}` — the whole board |
| `player_count` | int | |
| `board_updated_at` | str, nullable | `member_rankings.updated_at` at capture — distinguishes "re-ranked this week" from "re-snapshotted an unchanged board"; "Your calls" is built on exactly that distinction |
| `source` | str | `'sync'` \| `'weekly'` \| `'backfill'` |

Constraint: `uq_board_snapshot` on `(user_id, league_id, scoring_format, period_key)`. Indexes: `ix_lbh_league_period`, `ix_lbh_user_period`.

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
- Ranking: `trio_swipe`, `tier_save` (streak event since the P0 cutover; `props.via` ∈ `tiers`/`quickset`), `ranking_complete_first_time`, `ranking_method_changed`, `ranking_reorder` (streak event since #152), `anchor_answered` (streak event since #152), `quickset_completed` (`position, players_placed, duration_ms, skipped`), `quickrank_completed` (`position, players_ranked, duration_ms, skipped`), `swipe` (cutover twin of the legacy wrapped writer: `count, scoring_format`). Streak-qualifying set = `_RANK_STREAK_EVENTS` in `backend/database.py`: `trio_swipe`, `tier_save`, `ranking_complete_first_time`, `anchor_answered`, `ranking_reorder` — also the event set the "Ranks" leaderboard counts.
- Trade: `match_viewed`, `match_swiped`, `trade_proposed`, `counter_sent`, `trade_accepted`, `trade_declined`, `trade_ratified`, `trade_match` (cutover twin: `match_id, partner_id, give, receive`), `trades_generated` (`count, gen_ms, engine_version, lanes`), `calc_trade_evaluated` (`verdict, asset_count, mode` — WAT north-star input; fires for pre-auth `device:` identities too), **`sleeper_send_succeeded`** (P0-7, 2026-08-11 — `give_n, receive_n, pick_n, from_deck, transaction_id`; `source:"api"`, `league_id` set; fired by `_record_send_success` on a successful `POST /api/trades/propose`. **Server-fired only** — it is the north-star SEND leg (`WAT_LIVE`, funnel stage 8, `FEATURE_VERTICALS["send_in_sleeper"]`) and a client-forgeable success would sit next to `trade_ratified`. The counterparty's user id deliberately never rides in props. Its two siblings `sleeper_send_attempted` / `sleeper_send_failed` are **client**-fired and, like every client event, are documented via `analytics_taxonomy.py` + the [P0-7 addendum](business/analytics/2026-08-11-p0-7-addendum.md) rather than in this list — the same treatment `guide_*` and `draft_room_*` got)
- Engagement: `push_sent`, `push_opened`, `notif_pref_changed`, `league_synced`, `wrapped_viewed`, `feedback_submitted`, `asset_pref_added`, `asset_pref_removed`
- API observability (flag `obs.api_events`, `backend/api_observability.py`): `api_call` (one outbound external HTTP call) and `api_request` (one inbound `/api/*` request). Written under the constant `user_id = 'system:api'` (never a real user; the session user rides in `props.user` on inbound rows), `platform = 'server'`, `screen` = `{service}.{endpoint}` / route pattern. Prop specs: `OBS_EVENT_PROPS` in `backend/analytics_taxonomy.py`. Successes are 1-in-N sampled (`props.sample_n`); errors always full. Aged out after `FTF_OBS_RETENTION_DAYS` (default 30) — the only `user_events` rows with a retention purge.
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
| `verified_at` | str | ISO UTC of the last live authenticated ESPN read that PROVED this pair (credential-honesty fix, 2026-08-12). Means EXACTLY ONE THING: the **server** observed a successful **authenticated** read using this pair — never "the client captured cookies", "the user looked signed in", or "ESPN answered 200". Stamped by both `/api/espn/link` store paths; the credential-only path proves it via `server._espn_verify_credential` (authenticated read of a linked private league, else a fan-profile probe that returned account data — result asserted, not just exception-free). **Identity binding (#321, 2026-08-16):** since this release the stamp additionally implies the pair's SWID passed the membership assertion (owns the caller's bound team, or the check was conclusively inconclusive — zero-false-reject posture); a conclusive mismatch discovered later (team-binding step, re-sync) NULLs the stamp in place (`clear_espn_credential_verification`, row kept). **One-time invalidation migration (2026-08-16, `_evict_prerelease_espn_verified_stamps`):** every stamp `< 2026-08-17T06:00:00+00:00` (the release cutoff) was nulled at deploy — **no pre-identity-binding stamp is identity-trustworthy** — so NULL now also means "evicted pending an identity-bound re-sign-in", not only "never proven". NULL → `GET /api/espn/link` reports not connected. **Do not widen:** a device-reported "looks connected" signal needs its own column |
| `created_at`, `updated_at` | str | |

Interim home; folds into the auth epic's `linked_sources` when that lands.

---

## `mfl_credentials`

MFL authenticated linking (#177, `mfl.auth_link`). Encrypted MFL session cookies — one row per FTF `user_id` who signed in via `POST /api/mfl/auth-link`. The user's **password is never stored** (transient, single MFL login call); what's kept is the `MFL_USER_ID` cookie MFL returns. Written by `upsert_mfl_credential`; read/deleted by `get_mfl_credential` / `delete_mfl_credential`. Crypto reuses `backend/sleeper_write.py`'s Fernet helpers (same `SLEEPER_TOKEN_KEY`); if the key is absent the route falls back to session-only storage and this table stays empty.

| Column | Type | Notes |
|---|---|---|
| `user_id` | str PK | FTF user_id (one MFL link per user) |
| `mfl_username` | str | MFL login handle — identifier only (for "connected as" display), not a secret |
| `cookie_encrypted` | text | **Fernet ciphertext** of `MFL_USER_ID=<value>` — never plaintext, never logged |
| `year` | int | Season the cookie was minted for |
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

## `mock_drafts`

FTF-native mock-draft state (draft-extensions W2, [plan](plans/draft-extensions/plan.md) §5 / [lld](plans/draft-extensions/lld.md) §3.3). One row per simulation. A resumable simulation is genuinely stateful — in-memory state dies on a Render spin-down, which is a real event on the free plan — so this is the wave's only new table. Written by `backend/database.py`'s four `*_mock_draft` helpers; every rule lives in `backend/mock_draft_service.py`.

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `user_id` | str, not null | Owner. Every read/write helper is owner-scoped — a row is invisible to anyone else |
| `league_id` | str, not null | Indexed with `user_id` (`ix_mock_drafts_user_league`) |
| `season` | int, not null | |
| `status` | str, not null, `server_default 'active'` | `active` \| `complete` \| `abandoned` |
| `settings` | text (JSON), not null | `{rounds, type, teams, order[], order_source, ownership_source, slots[], ownership{}, personas{}, user_owner_id, lineup_slots[], scoring_format, noise{bpa_prob, reach_decay, max_reach}}`. **Everything the mock needs is snapshotted here at create** — which is what makes "zero platform egress after creation" structural. `ownership` is frozen at create so a mid-mock `draft_picks` resync cannot shift picks under the user; `noise` is frozen so retuning `model_config` cannot change an in-flight mock. `ownership_source` (#328) = create-time provenance of the traded-pick overlay, `platform` \| `user` \| `partial` \| `none` — present on rows written since #328 only; older rows have no key and echo `null` (read-time convention, no backfill) |
| `picks` | text (JSON), not null, `server_default '[]'` | Append-only `[{pick_no, round, slot, roster_id, player_id, by}]`, `by` ∈ `user`\|`cpu` |
| `rng_seed` | int, not null | Per-pick RNG is `Random(rng_seed * 10007 + pick_no)` — a pure function of `(seed, pick_no)`, never of call order, so a resumed mock replays byte-identically |
| `created_at` / `updated_at` | str | ISO-8601 UTC |

**No unique constraint, deliberately.** "One active mock per user per league" is enforced in application code inside `create_mock_draft`'s transaction (abandon-then-insert). `UniqueConstraint(user_id, league_id, status)` would also block a second *abandoned* row, and the partial unique index that fixes that is dialect-divergent across SQLite/Postgres.

**`server_default`, not Python `default`** (the `referrals` precedent), so a raw-SQL insert cannot produce NULL.

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

### `analytics_segments`
Saved analytics cohorts (Fullstory-style Segments). `id` PK, `name` (unique), `definition_json`, `created_at`. The definition is a **closed grammar** (`did` / `did_not` / `platform` / `min_events`) evaluated live per query window by `analytics_queries.evaluate_segment` — every operand maps to a code-controlled SQL fragment, so a segment can never inject SQL. Unknown ops/events/platforms raise `BadParam` → 400.
