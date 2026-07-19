# Tracking Plan v2 — Full-Funnel Event Taxonomy & Instrumentation Spec

**Role:** an-data-architect · **Date:** 2026-07-17 · **Status:** Spec (nothing here is built until routed)
**Lineage:** v1 = the server-fired taxonomy in `backend/database.py:582-592` (~12 live event types). This v2 extends that lineage — same table, same `record_event()` writer, additive columns only. No parallel system.

## Question & context

The operator wants best-in-class product analytics: a step-by-step UX waterfall (conversion per step), time-per-action / think time, bottleneck and churn diagnosis, crash visibility, and a foundation that supports concurrent A/B + multivariate testing with attribute targeting. This spec defines **what rows must exist** for all of that. Metric formulas live in the companion program plan (`2026-07-17-analytics-program-plan.md`); experiment mechanics in `2026-07-17-experimentation-framework.md`.

## Current instrumentation audit (2026-07-17)

**Exists and fires (user_events, server-side):** `trio_swipe`, `ranking_complete_first_time`, `trade_proposed`/`match_swiped` (swipe route, incl. `aggression_variant` prop), `match_viewed`, `match_dismissed`, `trade_accepted`/`trade_declined`, `trade_ratified`, `asset_pref_added/removed`, `signup`/`app_open` (session init), `push_sent`, `notif_pref_changed`. Dual-writes `users` hot columns; device/OS/app-version snapshots come from `X-Device`/`X-OS-Version`/`X-App-Version` headers.

**Documented but dark (declared in taxonomy, never fired):** `login`, `logout`, `counter_sent`, `push_opened`, `wrapped_viewed`, `ranking_method_changed`, `league_synced`.

**Fired to the wrong table:** `tier_save`, `league_sync`, `swipe`, `trade_match`, `ranking_reorder` go only to `wrapped_events` — a write-only legacy stream no UI or query consumes.

**Completely dark zones:**
- Everything client-side: install/first-open, screen views, the entire pre-signin funnel (sign-in attempts/failures, league picker), tap-level interactions, dwell/decision time, `push_opened`, client errors/crashes.
- All web and extension usage (their API calls land as `source:"api"` with device headers only from mobile).
- Experimentation: no assignment/exposure records beyond the one `aggression_variant` swipe prop.

**Identity:** join key is `users.sleeper_user_id`; durable anchor is `accounts.account_id` (`acct_…`) via `linked_identities`. No stable device ID exists → pre-signin behavior is currently unattributable.

## Options considered (collection path)

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **A. Third-party SDK (Amplitude/Mixpanel/Firebase)** | Dashboards, funnels, cohorting free out of the box; stats tooling | New App Store privacy-label disclosures; data leaves our control (cuts against the read-privacy auth posture); free tiers cap or expire; experiment targeting still needs our backend; another vendor pre-revenue | **Killed** — dashboard convenience doesn't outweigh privacy posture + vendor lock at beta scale |
| **B. Self-hosted OSS (PostHog CE)** | First-party + full featureset | A second service to run on Render, Postgres requirement now, ops burden for a solo operator | **Killed for now** — revisit at >5k MAU if dashboard build cost bites |
| **C. Extend first-party `user_events` + batched `POST /api/events` + admin dashboards** | One lineage; zero new vendors; privacy story unchanged; experiments join natively on the same keys; SQLite→Postgres path already proven | We build funnels/dashboards ourselves; client batching/offline queue is our code | **Chosen** |

One carve-out: **crash reporting** (native crashes never reach a JS event queue). Recommend Sentry (free tier, `sentry-expo`) as the only third-party — flagged as a Decision below. JS-level errors are covered first-party by `client_error`.

## Spec

### S1. Envelope — additive columns on `user_events`

Nullable, so v1 rows and v1 call sites are untouched:

| Column | Type | Purpose |
|---|---|---|
| `event_id` | String, UNIQUE (nullable) | Client-generated UUID → idempotent retries, dedup |
| `device_id` | String, indexed | Stable per-install anon ID (`dev_` + UUID, Keychain/localStorage) — pre-signin attribution |
| `platform` | String | `ios` / `web` / `extension` / `server` |
| `screen` | String | Screen/view the event fired from |
| `client_ts` | String | Client wall-clock ISO; `occurred_at` stays server receive time (clock-skew guard: trust `occurred_at` for ordering, `client_ts` for intra-session deltas) |
| `experiments` | Text (JSON) | Compact `{exp_key: variant}` snapshot of active assignments at event time — makes every event self-serve analyzable per variant |

New table `identity_links` (`device_id`, `sleeper_user_id`, `account_id`, `linked_at`): written on every successful sign-in; stitches pre-auth device rows to the user. Pre-auth events store `user_id = 'device:<device_id>'` (satisfies NOT NULL; queries resolve through `identity_links`).

`wrapped_events`: **freeze** (stop writes once its five event types fire to `user_events`; keep table as history). One system, one lineage.

### S2. Ingestion — `POST /api/events`

- Batch of ≤50 envelopes `{event_id, event_type, client_ts, screen, props, session_id, seq}` *(amended 2026-07-17, approved — `seq` is a per-session monotonic counter starting at 1; per-session gap analysis is the only mechanism that makes event loss measurable rather than assumed, PRD FR-10/SM-2)*; auth via session token when present, else `device_id` (pre-auth). Server stamps identity, device headers, `experiments` snapshot *(scoped per the amended framework §D4 — funnel-stage + in-experiment-scope events, not every row)*.
- Client SDK module per client (`mobile/src/api/events.ts`, `web/js/events.js`, extension background): in-memory queue → flush every 10 s / 20 events / on background; AsyncStorage/localStorage persistence for offline; drop-oldest at 500 queued; fire-and-forget (analytics must never block or break product UX — mirror `record_event()`'s swallow-errors contract).
- Session semantics: client-generated `session_id` (UUID), rotated after 30 min inactivity or cold start. All client events carry it (today only signup/app_open do).
- Rate limit per device (e.g. 600 events/hr) + allowlist of known `event_type`s; unknown types logged + dropped (schema discipline).

### S3. Event taxonomy v2 (additions; naming = `object_action`, snake_case, past tense)

**Lifecycle / navigation (client):**

| Event | Fires | Key props |
|---|---|---|
| `app_opened` | cold/warm foreground | `launch_type`, `from_push`, `push_kind` |
| `app_backgrounded` | background | `session_ms`, `screens_viewed` |
| `screen_viewed` | every screen/view mount, all 3 clients | `screen`, `prev_screen`, `tab` |
| `client_error` | JS error boundary / caught fatal | `screen`, `error_kind`, `message` (scrubbed+truncated 200), `fatal` |

**Pre-auth funnel (client):** `signin_attempted` (`method`: apple/sleeper/last_user/demo, `has_league_url`), `signin_succeeded`, `signin_failed` (`method`, `error_code`), `league_selected` (`league_index`, `league_count`, `platform`), `espn_link_started/completed/failed`, `demo_entered`.

**Ranking (mostly server, at existing routes):** `rank_method_selected` (client; `method`, `is_first_time`), `ranking_method_changed` (server — light up at `/api/ranking-method`, closes a documented-dark gap), `tier_save` (server → move to `user_events`; `position`, `changed_count`, `via`: tiers/quickset), `quickset_completed` + `quickrank_completed` (server at save; `position`, `players_placed`, `duration_ms`, `skipped`), `anchor_answered` (server; `player_id`, `pick_value`, `skipped`), `ranking_reorder` (server → move to `user_events`; `moves_count`), `trio_swipe` (existing; **add client-passed `decision_ms` + `input_kind`** — think-time gold, `swipe.gesture_audit` already captures gestures client-side).

**Trades (client dwell + server truth):** `find_trades_tapped` (client), `trades_generated` (server; `count`, `gen_ms`, `engine_version`, `lanes`), `trade_card_viewed` (client; `trade_id`, `card_index`, `lane`), existing swipe events **+ client-passed `dwell_ms`**, `trade_card_edited` (`action`: add/change/remove), `trade_flagged` (`reason`), `sleeper_send_attempted/succeeded/failed`, `match_opened` (client, per-match — `match_viewed` is list-level), calculator: `calc_opened` (`mode`), `calc_trade_evaluated` (server; `verdict`, `asset_count`), `calc_shared`, `calc_cleared`.

**Leagues / engagement:** `league_synced` (server at `upsert_league` → `user_events`), `league_summary_viewed` (`basis`), `free_agents_viewed` (`pos_filter`), `league_switched`, `invite_sent` (`channel`), `push_opened` (client; `kind`, `dedup_key` — closes the push loop against `push_sent`), `feedback_submitted` (server at `POST /api/feedback`; `severity`, `screen`), `identity_linked` (`provider`), `account_verified`, `account_deleted`.

**Extension:** `ext_signed_in`, `ext_pills_injected` (throttled 1/page-kind/day; `page_kind`, `count`), `ext_refresh_tapped`.

**Experimentation:** `experiment_exposed` (`experiment_key`, `variant`, `layer`) — fired once per user×experiment per session at first render of the varied surface (contract detail in the experimentation framework doc).

Rollout order: **server-fired first** (no app-store release: `tier_save`, `league_synced`, `ranking_method_changed`, `ranking_reorder`, `feedback_submitted`, quickset/quickrank/anchor saves) → mobile SDK + client events (needs TestFlight build) → web → extension.

### S4. PII & data-quality rules

- **Never in `props`:** emails, raw names, Sleeper JWTs/tokens, push tokens, device serial/IDFA, free-text user input (feedback note text stays in `feedback`, only `severity`/`screen` in events). `client_error.message` scrubbed (regex-strip emails/tokens) and truncated.
- Allowed identifiers: `sleeper_user_id`, `account_id`, `device_id` (all pseudonymous), player/league IDs.
- `account_deleted` triggers event anonymization: rewrite that user's `user_events.user_id`/`device_id` to a tombstone hash (keeps aggregates, honors deletion — matches privacy.html retention promises; legal-privacy to confirm).
- Timestamps UTC ISO; timezone only via existing `X-User-TZ`.
- Default-deny: new event types or props require a tracking-plan PR to this doc's lineage.
- Retention: raw events indefinitely at beta scale; revisit at 1M rows (rollup + prune plan pre-written in LLD).

## Doc updates required (when built)

- `docs/data-dictionary.md`: `user_events` new columns, `identity_links`, experiment tables; taxonomy sync (also fix current drift: `match_dismissed`, `asset_pref_*` fired-but-undocumented).
- `docs/api-reference.md`: `POST /api/events`, experiment/flag endpoints.
- `docs/config-reference.md`: new flags (`analytics.client_events`, etc.), env keys.
- `docs/cross-client-invariants.md`: event names + envelope are now a cross-client contract.
- `docs/architecture.md` + ADR for first-party-analytics decision.

## Decisions needed

1. **Sentry for native crash reporting** (only third-party in the stack; free tier) — recommend **yes**; JS-level errors covered first-party either way.
2. **Freeze `wrapped_events`** once its five event types land in `user_events` — recommend yes.
3. Confirm event anonymization-on-delete satisfies the privacy policy as written (route to legal-privacy).

## Handoffs

- Metric formulas over these events → an-funnel (companion doc, same date).
- Experiment assignment/exposure contract → experimentation framework doc.
- Build: backend endpoint + schema → eng-backend; mobile SDK → eng-mobile; web/extension → eng-web / eng-integrations; QA of event firing (Maestro-driven event assertions) → eng-qa. Sequenced via the analytics-platform PRD/HLD/LLD in `docs/plans/analytics-platform/`.

## Addendum 2026-07-17 — §S3 taxonomy additions (onboarding & conversion plan)

Added at backend build time (eng-backend, same date) to the client-event allowlist (`ALLOWED_CLIENT_EVENTS`, `backend/server.py`), covering the instrumentation the onboarding redesign needs (`docs/plans/onboarding-conversion/plan.md` — items 7/8 prompts, share rider, v2.1 guided layer, item 9 deck-exhausted routing). All client-fired via `POST /api/events`:

| Event | Fires | Key props |
|---|---|---|
| `apple_prompt_shown` / `apple_prompt_accepted` / `apple_prompt_declined` / `apple_prompt_dismissed` | item 8 save-moment Apple prompt lifecycle | `trigger_moment` |
| `quickset_prompt_shown` / `quickset_prompt_accepted` / `quickset_prompt_snoozed` | item 7 inline QuickSet prompt card | `screen`, `position` |
| `trade_card_shared` | item 8 rider — native share sheet on a liked card (user-initiated) | `trade_id`, `channel` |
| `coach_mark_shown` / `coach_mark_dismissed` | v2.1 guided layer (≤4 marks) | `mark_key` |
| `celebration_shown` | v2.1 celebration beats | `beat_key` |
| `deck_exhausted_viewed` | item 9 — deck-exhausted state that routes to trio entry | `lane`, `cards_seen` |

Also built same date (server-fired, §S3 rollout order "server-fired first"): `ranking_method_changed`, `tier_save` (now in `user_events`, props `position`/`changed_count`/`via` — `wrapped_events` write still on, freeze pending Decision 2), `ranking_reorder` (props `moves_count`), `anchor_answered` (props `player_id`/`pick_value`/`skipped`), `feedback_submitted` (props `severity`/`screen`, attributed submissions only, no note text), `league_synced` (props `league_id`/`platform`). Envelope columns, `identity_links`, and `POST /api/events` per §S1/§S2 are live behind `analytics.client_events`.

---

## Addendum 2026-07-19 — observability events + geo column

| Event | Props | Source | Purpose |
|---|---|---|---|
| `api_request_failed` | `route` (normalized: query stripped, digit runs → `:id`), `method`, `status` (0 = network/timeout), `ms`, `timeout` | `client.ts` wrapper (every failed `apiRequest`; excludes `/api/events` recursion + caller aborts) | Universal silent-API-failure detection per screen/route |
| `screen_left` | `screen`, `dwell_ms`, `reason` (`nav` \| `background`) | `RootNav` (nav-away + app-background) | Real dwell time incl. the truncated-last-screen case |

Envelope addition: `user_events.country` — ISO-3166 alpha-2 from CDN geo header only (`CF-IPCountry` / `X-Country-Code`), never raw IP (FR-47 posture). NULL on bare Render; populates automatically if a CDN fronts the service. Device/app characteristic joins (`device_type`, `os_version`, `app_version`) were already stamped per row at ingest — no change needed.
