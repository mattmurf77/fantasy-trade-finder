# docs/integrations/

Per-external-service API references — what FTF actually calls on each third-party
platform, verified against the code (not the vendor's docs, which for ESPN's
unofficial API don't exist). Written for the instrumentation program: each file
gives an instrumentation build agent the endpoint list, auth model, payload
shapes, error modes, call frequency, and a safe-to-log / must-redact split so
logging can be added without guessing at what a call site actually does.

This was conceived as a sibling to a `docs/references/<site>/<api-name>/` tree (see `docs/CLAUDE.md`) — **that tree was never populated and does not exist**; this folder is the only live home for integration references,
which holds raw reverse-engineered wire-shape notes; files here are the
consumer-facing distillation — one file per external service, organized around
"what do we call and why," not around capturing a single verification session.

| File | Service |
|---|---|
| [sleeper.md](sleeper.md) | Sleeper — REST v1, undocumented GraphQL, WebView JWT capture, restricted-beta weekly projections |
| [espn.md](espn.md) | ESPN Fantasy Football unofficial v3 API (`lm-api-reads.fantasy.espn.com`) — league linking, roster import, standings-derived draft order |
| [mfl.md](mfl.md) | MyFantasyLeague — official export API + authenticated login flow |
| [dynastyprocess.md](dynastyprocess.md) | DynastyProcess consensus-values CSVs (GitHub) — Elo seeds, pick slot prices, player-id crosswalk; also documents the adjacent KTC scrape |
| [nflverse.md](nflverse.md) | nflverse/nfldata NFL schedule CSV (GitHub) — bye-week derivation for the EVALUATED #169 bye-multiplier (`backend/outlook/bye_weeks.py`); also used for independently certified byes in the default-off Win Now forecast adapter |
| [anthropic.md](anthropic.md) | Anthropic Claude API — smart matchup selection |
| [expo-push.md](expo-push.md) | Expo push-notification relay (`exp.host`) |

Surfaces without a dedicated file (covered by the instrumentation layer below
all the same): the KeepTradeCut scrape (same module as DynastyProcess —
`backend/data_loader.py`, see dynastyprocess.md §Related), Fleaflicker
(`backend/fleaflicker_service.py`), and Apple/Google sign-in verification
(JWKS + Apple token endpoint, `backend/accounts.py`).

Keep current: when a call site is added, removed, or its shape changes, update
the relevant file in the same change.

## Instrumentation layer (flag `obs.api_events`, 2026-08-09)

The build these docs seeded is live: `backend/api_observability.py` captures
**every outbound call in the table above** plus **every inbound `/api/*`
request** as structured events in the existing analytics store (`user_events`),
so failures are diagnosable from stored data without a manual session.

**What's captured.**

* **Outbound (`api_call` events)** — one wrapper idiom
  (`observe_call(service, endpoint, …)`) around every egress chokepoint:
  `server._sleeper_get` (REST), `sleeper_write._post_graphql` (GraphQL), the
  three documented bypass sites (`trade_block_service.fetch_league_players` /
  `_fetch_rosters`, `sleeper_trades_service.fetch_week_transactions`),
  `espn_service.fetch_league` + `fetch_crosswalk`, `mfl_service` (`login`,
  `fetch_my_leagues`, `_fetch_one`, `resolve_host`), `fleaflicker_service._get`,
  the DynastyProcess/KTC fetches in `data_loader`, both Anthropic
  `messages.create` sites, `server._send_expo_push`, and `accounts._fetch_jwks`
  / `_apple_form_post`. Per call: service, endpoint **class** (route template —
  never a raw URL; ids ride in properties), method, status, latency ms,
  response size, error class + the service's closed error-kind enum, retry
  flag, and the per-service safe context each doc's §instrumentation-guidance
  allows (ESPN cookie-shape booleans `s2_encoded`/`swid_braced`, `league_id`,
  MFL host/export type, DP row counts, Anthropic token counts + prompt class,
  Expo batch size).
* **Inbound (`api_request` events)** — Flask after_request/teardown hooks:
  route pattern, method, status, latency, resolved session user (props only),
  and the JSON `error` code on 4xx/5xx. Excluded: non-`/api/` paths (static
  assets) and `POST /api/events` (the ingest route never observes itself).

**Redaction is structural, not aspirational.** The MUST-REDACT rules in each
service doc are enforced three ways in `api_observability`: a prop-spec
allowlist (`analytics_taxonomy.OBS_EVENT_PROPS` — unknown keys stripped), a
key-substring denylist (token/cookie/secret/authorization/…), and value-shape
scrubbing (JWT/bearer/long-percent-encoded shapes). Tests pin that a cookie or
JWT value never appears anywhere in a stored event
(`backend/tests/test_api_observability.py`).

**Volume policy.** Errors (4xx/5xx, exceptions, timeouts) are always captured
in full. Successes are 1-in-N counter-sampled per endpoint class
(`model_config obs_success_sample_n`, default 10 — change live via
`PUT /api/admin/config/obs_success_sample_n`); each sampled row carries
`sample_n` so reports rescale honestly (`est_calls = Σ sample_n + errors`).

**Retention.** Rows older than `FTF_OBS_RETENTION_DAYS` (default 30) are
purged by `api_observability.purge_observability_events()`, riding the
server's existing `_cleanup_loop`. Storage rows are written through
`db.ingest_engine` (the 150 ms-lock-budget analytics engine) under the
constant `user_id="system:api"`, and both event types are NON_INTENT in
`analytics_queries` — they can never leak into DAU/retention metrics.

**How to query.** `GET /api/admin/analytics/apihealth` (X-Cron-Secret; see
`docs/api-reference.md`): per-day/service/endpoint failure rates + latency
percentiles, `recent_failures`, `slowest`; `?service=espn&start=<today>&end=<today>`
answers "show me all failed ESPN calls today" in one request.

**Kill switch.** Flag `obs.api_events` (ships ON in `config/features.json`).
Off ⇒ zero event writes, zero overhead beyond a flag check, byte-identical
responses. Full config surface: `docs/config-reference.md`.
