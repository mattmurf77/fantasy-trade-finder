# 18. Trade push notifications

> Tier 1 · #18 (+ #88 coverage-push adjunct) · NEW · Effort M · Sources: FPT (wire/push retention model), FTF (existing push + cron plumbing)

## Summary

Discovery products die when discovery only happens on app-open. FPTrack's entire retention engine is push ("wires", injury/starter alerts); FTF's equivalents are higher-value because the engine is personal: **"new mutual-gain trade found in {league}"** from scheduled engine runs, **"{league-mate} updated their rankings — your divergence angles changed,"** and **value movers on rostered players**. The strategic shift: today `/api/trades/generate` runs only when a user asks; this item makes the engine run on a schedule and tell the user when — and only when — it found something genuinely good.

The plumbing is unusually far along, which is why this is M not L. `backend/server.py` already has a typed push dispatcher (`_send_typed_push`) with per-bucket prefs, frequency caps (`_NOTIF_FREQ_CAPS`), per-event dedup (`_NOTIF_DEDUP_CAPS`), quiet-hours queueing with an 8am bundled summary, and a CRON_SECRET-protected `/api/cron/{realtime,hourly,daily}-tick` family driven by Render cron; mobile has `expo-notifications`, `usePushNotifications`, device registration, and a prefs API (`/api/notifications/prefs`). What's new: a scheduled engine-run tick, three notification kinds with a **quality threshold** so pushes stay rare and good, and prefs extended from three global buckets to **per-type × per-league** granularity. Restraint is the product requirement: one great trade push a week builds the habit; three mediocre ones a day kills permissions.

## PRD

### Problem & user story

> As a user, I want FTF to work while I'm not looking — run the engine in my leagues on a schedule and ping me only when there's a trade worth my attention, a divergence shift worth exploiting, or a meaningful value move on my roster.

### Goals / Non-goals

**Goals**
- Scheduled engine runs per (user, league) without user action, on existing cron infrastructure.
- Three new push types: `trade_found` (quality-gated), `divergence_shift` (league-mate ranking activity changed the user's angles — includes #88's coverage/social-proof variant), `value_mover` (rostered-player consensus moves).
- Prefs: per-type toggles + per-league mutes, layered on the existing prefs surface. Quiet defaults — conservative caps on, quiet hours respected (all existing machinery).
- Push payloads deep-link to the exact card/screen.

**Non-goals**
- No email (that's #89's fallback) and no web push in v1 (mobile-first; web sees the same items in the in-app inbox).
- No new scheduler — Render cron hitting `/api/cron/*` remains the only trigger.
- `value_mover` v1 uses consensus/Elo-history data already available; richer movers wait for #57's daily snapshot job (flagged dependency, not built here).
- No offer-received push (depends on #11 V2 / #83).

### Functional requirements

- **FR1** New `POST /api/cron/engine-tick` (CRON_SECRET auth, same `_require_cron_auth()` pattern): selects eligible (user, league) pairs — push-registered users with `trade_finds` pref on, league not muted, last run > `engine_run_interval_hours` ago — and runs trade generation in bounded batches per tick.
- **FR2** Quality gate: a `trade_found` push fires only if the run's best *fresh* card (not previously pushed — dedup on a stable trade-shape hash) clears `push_min_composite` (model_config) **and** is `verdict.band != "lopsided"` against the user. At most one `trade_found` push per (user, league) per `trade_found_window_days` (default 3) via `_NOTIF_FREQ_CAPS`.
- **FR3** `divergence_shift`: fired from the existing ranking-submit path (not cron) when a league-mate's session materially changes shared divergence (threshold `divergence_shift_min`), e.g. "@brandon updated 30 rankings — 2 new trade angles in {league}." #88's variant ("a league-mate just ranked — your shared divergence map updated") is the same kind with coverage copy. Cap: 1 per (user, league) per 7 days.
- **FR4** `value_mover`: daily-tick scan of rostered players whose consensus value moved ≥ `value_mover_min_pct` in `value_mover_window_days`; bundled into one push per user ("3 of your players moved this week"). Cap: 1/7d.
- **FR5** Prefs API extends with two new buckets (`trade_finds`, `value_movers`) and per-league mutes; new kinds map into buckets via `NOTIF_KIND_TO_BUCKET` (`trade_found`→`trade_finds`, `divergence_shift`→`trade_finds`, `value_mover`→`value_movers`).
- **FR6** Defaults: `trade_finds` **on**, `value_movers` **off** (opt-in), quiet hours on (existing default). New users see one explainer row in the prefs screen, no extra permission prompts (priming flow exists in `usePushPriming`).
- **FR7** Tapping a `trade_found` push opens the trades deck scrolled to that card (cards persisted via the existing job-snapshot path so the deck survives until opened); `divergence_shift` opens league divergence view; `value_mover` opens trends.
- **FR8** All sends flow through `_send_typed_push` — buckets, caps, dedup, quiet hours, and `notification_events_log` come for free; every push also writes the in-app `notifications` inbox row.

### UX notes (per client)

- **Mobile** (primary): extend the existing notification-prefs screen (backed by `GET/PUT /api/notifications/prefs`, types in `mobile/src/shared/types.ts:NotificationPrefs`) with the two new toggles + a per-league mute list; route taps in `RootNav.tsx`'s existing notification-tap handler. Copy examples — `trade_found`: "🔁 New trade in Dynasty Degens — you get J. Jeanty, they get a WR they need. Both sides improve." `divergence_shift`: "📈 @brandon re-ranked — 2 new angles between you two."
- **Web**: in-app inbox (`/api/notifications`) shows the same items; prefs page mirrors toggles. No browser push v1.
- Tone follows the advocate voice; body always names the league and the payoff, never generic "check the app."

### Success metrics

- Push → open rate per kind (target: `trade_found` > the existing `new_match` open rate); opt-out/bucket-off rate (< 10% of receivers) and iOS permission-revoke rate as the restraint alarms.
- D7/D30 retention delta for push-on vs push-off cohorts (user_events).
- Pushed-card like-rate vs organic deck like-rate (quality-gate calibration, via engine-metrics #84).

### Acceptance criteria

- [ ] `engine-tick` runs bounded batches, is idempotent on re-invocation, and respects CRON_SECRET auth (verified with the secret from `secrets.local.env`).
- [ ] No user receives more than one `trade_found` per league per window; dedup hash prevents re-pushing the same trade shape across runs.
- [ ] Quality gate verified: forcing `push_min_composite` high → zero pushes; lowering → pushes resume.
- [ ] Quiet-hours queueing + 8am bundling works for the new kinds (existing `_summary_push` covers mixed bundles).
- [ ] Prefs toggles and league mutes round-trip on mobile; muted league never pushes any of the three kinds.
- [ ] Tap-through lands on the right card/screen from cold start.
- [ ] docs updated: api-reference.md (cron route, prefs body), data-dictionary.md (prefs columns + mutes table + run-log), config-reference.md (new model_config keys), runbook (Render cron schedule entry), cross-client-invariants.md (bucket enum strings).

## HLD

### Components touched

- `backend/server.py`: new cron route + kind constants + cap entries; ranking-submit hook for `divergence_shift`; extend prefs route allowlist.
- `backend/database.py`: `NOTIF_KIND_TO_BUCKET` additions, `notification_prefs` columns, `notification_league_mutes` + `engine_run_log` tables.
- `backend/trade_service.py`: callable headless run path (exists — `_run_trade_job` already runs in a daemon thread; engine-tick reuses it synchronously per pair with a batch budget).
- `mobile/src`: prefs screen, tap routing, types. `web/js`: prefs mirror.
- Render cron config (ops): add the engine-tick schedule (runbook entry).

### Data flow

Render cron → `POST /api/cron/engine-tick` → eligibility query (device_tokens ⋈ prefs ⋈ mutes ⋈ engine_run_log) → for each pair (budgeted, oldest-run first): generate → best fresh card → quality gate → `_send_typed_push("trade_found", …, dedup_key=shape_hash)` → existing prefs/cap/quiet-hours pipeline → Expo → tap → deep route. `divergence_shift` short-circuits this: it's event-driven off `/api/rank3`/submit, calling `_send_typed_push` directly for affected league-mates. `value_mover` rides the existing daily-tick.

### Flags & config interplay

- Flag `notif.engine_push` (default false) gates engine-tick eligibility entirely; `notif.value_movers` (default false) gates FR4 independently.
- `model_config`: `push_min_composite`, `engine_run_interval_hours` (24), `engine_tick_batch` (e.g. 25 pairs/tick), `trade_found_window_days` (3), `divergence_shift_min`, `value_mover_min_pct` (10), `value_mover_window_days` (7). All admin-tunable live.
- Interplay: #6's verdict gates push quality (FR2); #38's trade-of-the-day and #25's watchlist alerts later reuse the engine-tick + kinds framework; #13's gamification pushes stay in existing buckets.

## LLD

### API changes (routes + example payloads)

```
POST /api/cron/engine-tick        (X-Cron-Secret)
→ 200 { "ok": true, "pairs_scanned": 25, "runs": 25, "pushed": 3, "skipped_quality": 19, "skipped_cap": 3 }

PUT /api/notifications/prefs      (extended allowlist)
{ "trade_finds": 1, "value_movers": 0 }

PUT /api/notifications/league-mutes
{ "league_id": "112233", "muted": true }
GET /api/notifications/league-mutes → { "muted_league_ids": ["112233"] }
```

Push data payloads: `{"type":"trade_found","league_id":"…","trade_id":"…"}`, `{"type":"divergence_shift","league_id":"…","peer_user_id":"…"}`, `{"type":"value_mover","player_ids":[…]}`.

### Schema changes (SQLAlchemy Core, SQLite + Postgres)

- `notification_prefs`: add `trade_finds Integer` (default 1), `value_movers Integer` (default 0) via `_migrate_db()` idempotent ALTERs.
- New tables:

```python
notification_league_mutes_table = Table("notification_league_mutes", metadata,
    Column("user_id",   String, primary_key=True),
    Column("league_id", String, primary_key=True),
    Column("created_at", String, nullable=False),
)

engine_run_log_table = Table("engine_run_log", metadata,
    Column("id",          Integer, primary_key=True, autoincrement=True),
    Column("user_id",     String,  nullable=False),
    Column("league_id",   String,  nullable=False),
    Column("ran_at",      String,  nullable=False),
    Column("best_composite", Float),
    Column("pushed",      Integer, nullable=False),  # 0|1
    Column("push_dedup",  String),                   # trade-shape hash
    Index("ix_engine_run_user_league", "user_id", "league_id", "ran_at"),
)
```

### Client changes

- `mobile/src/shared/types.ts`: extend `NotificationPrefs`; prefs screen component adds toggles + mute list (league names from `/api/leagues`).
- `mobile/src/navigation/RootNav.tsx`: extend the tap handler (`onTapMatchNotification` pattern) with the three new `type` values.
- `web/js`: prefs section parity; inbox rendering already generic.
- Extension: none.

### Sleeper integration notes (read-only boundary)

None of the three kinds touches Sleeper beyond data FTF already syncs. Engine-tick runs may want fresher rosters; reuse the existing sync path and its cadence — do **not** add aggressive Sleeper polling for push freshness. An "offer received" push is explicitly out of scope until #83/#11-V2 settle pending-offer readability.

### Rollout

`notif.engine_push` default **false**. Order: ship schema + prefs UI dark → enable engine-tick for the operator account only (allowlist via model_config) → tune `push_min_composite` against real runs for a week → beta cohort → on. `notif.value_movers` follows separately once #57's history job exists or trends data proves sufficient. Add the Render cron entry (suggested: every 2h, batch-budgeted) at operator-only stage; record in runbook.md.

### Open questions

1. Engine-tick load on Render's instance (each run is a league scan): is `engine_tick_batch=25` per 2h tick safe on the current dyno, or does this force a worker split? Measure at operator-only stage.
2. Should `trade_found` quality-gate on percentile-vs-user's-own-history instead of a global composite floor? (Start global; revisit with engine-metrics data.)
3. Trade-shape hash definition (sorted asset ids + partner?) — must be stable across runs so dedup actually holds when rosters are unchanged.
4. Per-league mutes vs per-league×per-type: start league-wide mute (simpler mental model); split only if asked.
5. Does `divergence_shift` need cross-user privacy review (it reveals *that* a league-mate ranked, not what)? Believed fine — the league coverage screen already shows this — confirm.

## Dependencies & sequencing

- **Consumes #6** (verdict gate in FR2) and the v2/v3 engine as-is; no engine changes.
- **Wants #12 first** (Wave 4 order): a pushed trade should land on a card with a "Send in Sleeper" action.
- **Unlocks** #25 (watchlist alerts), #33 (movers digest), #38 (trade-of-the-day), #88 (built in here as a `divergence_shift` copy variant), #89 (email fallback mirrors the same items).
- **#57** (value-history snapshots) upgrades `value_mover` quality — file it as the explicit follow-up.
