# API observability — status

> Operator-directed program (no feedback item number): "Any external API call
> (or internal to the backend) should be logged with appropriate request and
> response details captured." Spec corpus: `docs/integrations/` (per-service
> instrumentation-guidance sections, binding) + `docs/api-reference.md`.

**Status: BUILT (2026-08-09)** — flag `obs.api_events` ships **ON**. Branch
`worktree-agent-aacd51e33f5ad4223`; core module `backend/api_observability.py`;
tests `backend/tests/test_api_observability.py` (23).

## What shipped

Two capture layers into the existing analytics store (`user_events`), as
server-fired events registered in `backend/analytics_taxonomy.py`
(`OBS_EVENT_PROPS` prop specs, enforced at write time):

1. **Outbound (`api_call`)** — one wrapper idiom (`observe_call`) around every
   external egress chokepoint. Coverage:

   | Service | Chokepoint(s) wrapped | Bypass sites routed |
   |---|---|---|
   | sleeper (REST) | `server._sleeper_get` | `trade_block_service._fetch_rosters`, `sleeper_trades_service.fetch_week_transactions` |
   | sleeper (GraphQL) | `sleeper_write._post_graphql` | `trade_block_service.fetch_league_players` |
   | espn | `espn_service.fetch_league` | — |
   | mfl | `mfl_service._fetch_one` (exports #4–#9), `login`, `fetch_my_leagues`, `resolve_host` | — |
   | fleaflicker | `fleaflicker_service._get` | — |
   | dynastyprocess | `data_loader` values-players + values.csv fetches, `espn_service.fetch_crosswalk` | — |
   | ktc | `data_loader._fetch_ktc_html` | — |
   | anthropic | both `messages.create` sites in `smart_matchup_generator` (token counts + prompt class) | — |
   | expo_push | `server._send_expo_push` (per chunk) | — |
   | apple / google | `accounts._fetch_jwks`, `accounts._apple_form_post` | — |

   Captured per call: service, endpoint **class** (route template, never raw
   URLs — ids ride in properties), method, status, latency ms, response bytes,
   error class + per-service error-kind enum, retry flag, and the doc-approved
   safe context (ESPN `s2_encoded`/`swid_braced` shape booleans, `league_id`,
   MFL host/export type, DP row counts, Anthropic token counts).

2. **Inbound (`api_request`)** — Flask before/after_request + teardown hooks in
   `server.py`: route PATTERN (never raw path), method, status, latency,
   resolved session user (props only; the row's `user_id` is always
   `system:api`), JSON error code on 4xx/5xx. Excluded: non-`/api/` paths and
   `POST /api/events` (no self-observation).

**Redaction** (docs' MUST-REDACT rules, enforced structurally): prop-spec
allowlist strip + key-substring denylist + value-shape scrub (JWT / bearer /
long percent-encoded). Tests pin that a cookie/JWT value appears nowhere in
any stored event. Test-injected `_opener` seams and the Sleeper fixture mode
are NOT instrumented (no phantom events from hermetic runs).

**Query surface**: `GET /api/admin/analytics/apihealth` (X-Cron-Secret) —
per-day/service/endpoint failure rate + p50/p95 latency, `recent_failures`
(newest 100), `slowest` (top 20), `?service=<name>` filter. "All failed ESPN
calls today" = `?start=<today>&end=<today>&service=espn`.

**Failure isolation**: every event write goes through one sink that catches
everything and prints to stderr; a poisoned store demonstrably breaks neither
an outbound call nor an inbound request (pinned by tests).

## Volume + retention decisions — for operator sign-off

These defaults are live; each has a no-deploy lever.

| Decision | Default | Lever |
|---|---|---|
| Success sampling | **1-in-10** per endpoint class (deterministic counter; sampled rows carry `sample_n` for honest rescaling). **Errors always captured in full.** | `model_config obs_success_sample_n` via `PUT /api/admin/config/obs_success_sample_n` (60 s cache); `1` = record everything |
| Retention window | **30 days**, purged via the existing `_cleanup_loop` (throttled to one DELETE per 6 h) | env `FTF_OBS_RETENTION_DAYS` (0 = keep forever) |
| Kill switch | Capture **ON** | flag `obs.api_events` (features.json / `FTF_FLAGS`) |
| Storage engine | `db.ingest_engine` (150 ms lock budget — observability sheds before it ever stalls product writes) | — (design) |

**Projected volume at current usage** (operator + a handful of TestFlight
testers; ~2–5 k inbound requests/day observed class, plus outbound bursts of
~25–45 Sleeper/DP calls per session-init and daily cron sweeps): successes
/10 + full errors ≈ **300–800 rows/day**, ~0.3–0.5 KB/row ⇒ **< 0.5 MB/day,
≤ ~15 MB steady-state at the 30 d window** — no disk risk on Render's free
tier. If usage 10×es, the same math holds at ~5 MB/day; the first lever to
pull is `obs_success_sample_n` (10 → 50), not the retention window (errors
are the diagnostic payload and are unsampled).

**Caveat accepted**: failure *rates* are estimates on sampled successes
(`est_calls = Σ sample_n + errors`); error *counts* are exact. The apihealth
report says so in its `caveats` envelope on every response.

## Verification

* Baseline before build: `python3 -m pytest backend/tests -q` → **2086 passed,
  1 skipped**.
* After build: **2109 passed, 1 skipped** (+23 in
  `test_api_observability.py`: per-service wrapper capture incl. redaction
  assertions, inbound hooks + exclusions, sampling, kill-switch zero-writes,
  poisoned-store isolation, retention purge, apihealth report + service
  filter).
* No mobile/web/extension changes — backend + docs only.

## Follow-ups (not blocking)

* Expo `DeviceNotRegistered` receipt parsing (expo-push.md flags it) — the
  transport is now instrumented, but Expo's per-token response body is still
  unparsed, so stale tokens aren't pruned.
* ESPN `derive_espn_draft_order` refusal-reason signal (espn.md §4.4) — a
  non-HTTP "refusal" class the wrapper deliberately doesn't cover.
* Client-side-only blind spots listed in sleeper.md §6.3 (WebView load,
  Keychain outcomes, deep-link hand-offs) need client events, not backend
  wrappers.
