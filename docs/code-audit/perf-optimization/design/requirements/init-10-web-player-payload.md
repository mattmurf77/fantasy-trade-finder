# REQ — INIT-10: Web Player Payload (Rebind + Slim + Cache)

- **Initiative / Wave / Scope:** INIT-10 · Wave 2 · [W]
- **Source observations:** OBS-ROUTE-01, OBS-ROUTE-02, OBS-ROUTE-03, OBS-ROUTE-05, OBS-NET-05
- **Peak RICE-P:** 5.4 (OBS-ROUTE-01)

## Problem statement

The `/api/sleeper/players` route is bound to the wrong handler function
(`_ensure_sleeper_cache_populated` rather than the purpose-built `sleeper_players()`),
ships the raw 53-field Sleeper object for all 4,029 players (4.84 MB uncompressed),
carries no caching headers, and forces the single-worker origin to re-serialize
the full payload on every web-client load. The web client (`web/js/app.js`)
fetches the full body on every session while Cloudflare reports `cf-cache-status:
DYNAMIC`, meaning the edge is not caching it and no client can 304.

## User stories

- As a **web user**, I want player data to load quickly on first visit and
  instantly on subsequent visits, so that the trade-finder is responsive even on
  a slow connection.
- As a **developer**, I want the players route to be served by its intended
  handler with a clean field projection, so that future edits to the serialization
  path are applied to the correct function.
- As an **operator**, I want the origin to stop re-serializing 4.84 MB of JSON on
  every request so that the single free-tier gunicorn worker has headroom to serve
  concurrent ranking and trade requests.

> Note: this initiative is **web-weighted [W]**. Mobile clients call only the
> 25-byte `/api/sleeper/players/warm` endpoint and are unaffected by any change
> to the full-body route. None of the acceptance criteria below are expected to
> reduce mobile latency.

## Functional requirements

- **FR-1 (prerequisite — rebind):** Move the `@app.route("/api/sleeper/players")`
  decorator from `_ensure_sleeper_cache_populated` to `sleeper_players()` so the
  registered view function is the one with the cache-first path and error handling.
  Verify that the cold-cache populate side-effects (DB sync, ADP fetch) still fire
  on a cache miss (they are called from within `sleeper_players()` at `server.py:4404`).

- **FR-2 (slim payload):** Add a field-allowlist projection to the players route —
  extend or reuse `player_to_dict` (`server.py:1240`) to map each cached player to
  approximately 17 fields (id, name, position, team, age, years_exp, injury_status,
  search_rank, adp, depth-chart fields, height, weight). Strip at minimum:
  `espn_id`, `gsis_id`, `kalshi_id`, `oddsjam_id`, `opta_id`, `pandascore_id`,
  `sportradar_id`, `swish_id`, `stats_id`, `rotowire_id`, `rotoworld_id`,
  `fantasy_data_id`, `yahoo_id`, `hashtag`, `player_shard`, `search_first_name`,
  `search_full_name`, `search_last_name`, `birth_city`, `birth_country`,
  `birth_state`, `high_school`, `competitions`, `metadata`,
  `practice_description`, `practice_participation`, `news_updated`, `team_abbr`,
  `team_changed_at`. Before stripping any field, grep `web/js/app.js` for every
  field name to confirm it is not read by the web consumer.

- **FR-3 (HTTP caching):** Add a strong `ETag` (derived from the cache file mtime
  or a sync-version counter) and `Cache-Control: public, max-age=<~86400>` to the
  `/api/sleeper/players` response. Honor `If-None-Match` → return HTTP 304 when
  the ETag matches. The `max-age` must be aligned to the nightly Sleeper sync
  cadence so newly-synced players are not hidden beyond one refresh cycle.
  Bust the ETag on every successful `sync_players` / `needs_player_sync` cycle.

- **FR-4 (web parity):** Confirm `web/js/app.js` renders identically (all
  displayed fields present) with the slimmed payload before shipping. No change
  to the mobile warm endpoint (`/api/sleeper/players/warm`) or any mobile code.

## Acceptance criteria

- [ ] **AC-1 — Route rebind:** `GET /api/sleeper/players` is served by
  `sleeper_players()`. Verify by checking that a cold-cache hit still triggers
  the populate side-effects (DB sync) and that a warm-cache hit follows the
  cache-first path. No regression on the existing warm response path.

- [ ] **AC-2 — Field count:** A `GET /api/sleeper/players` response contains
  fewer than 20 fields per player object. The stripped fields listed in FR-2 are
  absent. No field currently read by `web/js/app.js` is missing.

- [ ] **AC-3 — Payload size:** The uncompressed response body is ≤ 1.5 MB
  (down from the measured 4.84 MB); the Cloudflare-compressed wire size is
  ≤ 300 KB (down from ~660–676 KB).

- [ ] **AC-4 — ETag / 304:** Two consecutive identical `GET /api/sleeper/players`
  requests: the second returns HTTP 304 when the `If-None-Match` header matches
  the ETag from the first response.

- [ ] **AC-5 — Edge caching:** After deploy, `cf-cache-status: HIT` is observed
  on the second `GET /api/sleeper/players` from the same region (confirming
  Cloudflare is caching the response, not reporting `DYNAMIC`).

- [ ] **AC-6 — ETag bust on sync:** After a nightly Sleeper sync completes, the
  ETag on `/api/sleeper/players` differs from the pre-sync value; a client that
  sends the old `If-None-Match` receives a full 200, not a 304.

- [ ] **AC-7 — Mobile unaffected:** No change to `/api/sleeper/players/warm`
  response, headers, or latency. Mobile cold-start and warm-path latencies are
  unchanged (this is display data only).

- [ ] **AC-8 — Web render parity:** The web app (`web/js/app.js`) renders
  player names, positions, teams, and all displayed metadata correctly using the
  slimmed payload. No JavaScript errors relating to missing player fields.

## Related components

- `backend/server.py:4336–4337` — mis-bound decorator (OBS-ROUTE-05)
- `backend/server.py:4392` — `sleeper_players()` dead function (OBS-ROUTE-05)
- `backend/server.py:4360–4365` — cache filter (position only, all 53 fields kept)
- `backend/server.py:4399–4404` — `jsonify(cached)`, no cache headers (OBS-ROUTE-01, OBS-ROUTE-03)
- `backend/server.py:1240` — `player_to_dict` (~17-field mobile serializer)
- `backend/server.py:4376–4387` — cold-cache side-effects (`sync_players`, ADP fetch)
- `web/js/app.js:661,792,2405` — web consumer of the full body (OBS-ROUTE-01)
- `render.yaml:13` — `--workers 1` (single-worker contention context)

## Prerequisite components / dependencies

- **FR-1 (rebind) must land before FR-2/FR-3.** Any field projection or cache
  header added to `_ensure_sleeper_cache_populated` will have no effect on the
  live route until the decorator is rebound. This is the sequencing constraint
  documented in the LLD cross-initiative table: `INIT-10/ROUTE-05 (rebind) ──before──► INIT-10 (slim, ETag)`.
- OBS-ROUTE-05 resolving (rebind) is Wave 1 scope (RICE-P 0.8) and is treated as
  the prerequisite step within this initiative.

## Non-functional requirements & invariants

- **Web-only scope:** This initiative does not reduce mobile latency. No mobile
  source file (`mobile/`) is modified. The improvement is measured at the web
  client and origin CPU only.
- **Display data only:** No ELO math, K-factors, tier-band thresholds, or
  per-format independence is touched by this initiative. The players route returns
  raw Sleeper metadata; no ranking invariant (`docs/cross-client-invariants.md`)
  applies.
- **TTL alignment:** `max-age` must not outlast the nightly Sleeper sync window.
  Newly drafted or traded players surfaced by a sync must be visible within one
  refresh cycle. Recommended: `max-age=82800` (23 h) or keyed to the actual sync
  timestamp.
- **Compression invariant:** The route already benefits from Cloudflare edge
  compression (OBS-ROUTE-02). Adding Flask-Compress at the origin is explicitly
  out of scope for this initiative (documented as an alternative / runbook item
  in INIT-15); the ETag and `Cache-Control` headers are sufficient to unlock edge
  caching without touching origin-side compression.
- **Rollback:** if the slim payload breaks a web field, the field allowlist can
  be widened without touching the ETag or caching logic. The rebind can be
  reverted independently of the slim/cache changes.
- **Single-worker risk:** on a `--workers 1` free dyno, the per-request `jsonify`
  call on 4.84 MB blocks the sole worker. Edge caching (AC-5) is the primary
  mitigation; once the edge serves hits, origin serialization is rare.

## Out of scope

- Flask-Compress / origin-side gzip (documented in INIT-15 runbook entry).
- Migrating the web client from the full endpoint to a separate slim endpoint
  (the slim projection is applied on the existing route).
- Mobile client changes of any kind.
- Pagination or streaming of the player list.
- Changes to `/api/sleeper/players/warm`.
- Changes to the `player_to_dict` shape used by other (non-player-list) routes.
