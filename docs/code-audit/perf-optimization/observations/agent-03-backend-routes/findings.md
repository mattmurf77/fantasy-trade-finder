# Agent 03 — Backend HTTP Routes / Serialization — Findings

## Scope & method

**Scope.** Route handlers in `backend/server.py`, focused on the player, trade,
rankings, and matches endpoints: `/api/sleeper/players`,
`/api/sleeper/players/warm`, `/api/trades/generate`, `/api/trades/status`,
`/api/trades/matches`, `/api/trades/matches/all`, `/api/trades/awaiting`,
`/api/rankings`, `/api/session/init`, `/api/trio`. The audit looks at the
**route/serialization boundary** — payload shape, payload size, compression,
caching, and synchronous work on the request thread. Data-layer internals
(query plans, indexes) are Agent 04's job; N+1 patterns visible from the
handler are noted and cross-referenced.

**Method.**
- Static read of `backend/server.py` (6863 lines) and the serializers
  `player_to_dict` (`:1240`), `ranked_player_to_dict` (`:1263`),
  `trade_card_to_dict` (`:2654`), plus `_load_sleeper_cache` (`:336`),
  `_require_session` (`:855`), the `before_request` middleware (`:971`),
  `_ensure_universal_pools` (`:743`), and `session_init` (`:4431`).
- Live read-only measurement against `https://fantasy-trade-finder.onrender.com`
  using `curl -s -o /dev/null -w "size=%{size_download} ttfb=%{time_starttransfer} total=%{time_total}"`
  and `-D -` header dumps with `Accept-Encoding` variations. **No POST / no
  mutation.** The backend was warm for all timings below (a cold-dyno wake on
  `/api/session/ping` returned in ~2.5 s before measurement).

**Key live measurements (warm dyno):**

| Endpoint | Accept-Encoding | code | wire bytes | ttfb | total |
|---|---|---:|---:|---:|---:|
| `/api/sleeper/players` | (none/default) | 200 | 4,837,423 | 0.76 s | 3.94 s |
| `/api/sleeper/players` | `identity` | 200 | 4,837,423 | 0.58 s | 2.63 s |
| `/api/sleeper/players` | `gzip, br` | 200 | 676,415 | 0.86 s | 2.17 s |
| `/api/sleeper/players` | `gzip` | 200 | ~662,700 | 0.77 s | 1.26–2.18 s |
| `/api/feature-flags` | `gzip` | 200 | 343 | 0.23 s | 0.23 s |
| `/api/rankings` (no session) | — | 401 | 87 | — | 0.21 s |
| `/api/trio` (no session) | — | 401 | — | — | 0.19 s |
| `/api/trades/matches/all` (no session) | — | 401 | — | — | 0.20 s |

**Header findings:** every `/api/sleeper/players` response carried
`cf-cache-status: DYNAMIC` (Cloudflare is **not** edge-caching it) and
`x-render-origin-server: gunicorn`. With `Accept-Encoding: identity` the origin
returned the **full 4.84 MB uncompressed** — i.e. compression is done by
Cloudflare's edge (`server: cloudflare`, `content-encoding: br`), **not** by
Flask/gunicorn. No `ETag`, `Last-Modified`, or `Cache-Control` on any data
endpoint (those headers appear only on `/og/*` and `/s/*` social routes,
`server.py:5997`, `:6094`). `render.yaml:13` runs gunicorn with `--workers 1`.

The auth-gated endpoints (`/api/rankings`, `/api/trio`, `/api/trades/*`,
`/api/session/init`) return 401 without a valid `X-Session-Token`, so their
payload sizes/timings could not be measured live; those observations rest on
static analysis (Confidence ≤ 80%) with the serialization cost reasoned from
code.

---

## OBS-ROUTE-01 — `/api/sleeper/players` ships the raw 53-field Sleeper object (4.8 MB) instead of the ~10 fields clients render

- **Area:** backend routes / serialization
- **Severity:** P1
- **Status:** observed
- **Evidence type:** measured

### What happens today
`/api/sleeper/players` returns the on-disk Sleeper cache **verbatim** via
`jsonify(cached)` (`server.py:4399–4404`). The cache is the filtered Sleeper
bulk dump (`_ensure_sleeper_cache_populated`, `server.py:4360–4365`), but the
filter only drops non-skill positions — it does **not** strip fields. Each of
the 4,029 player objects therefore carries **53 keys**, including a large set
of cross-provider ID fields and metadata no client renders:
`espn_id`, `gsis_id`, `kalshi_id`, `oddsjam_id`, `opta_id`, `pandascore_id`,
`sportradar_id`, `swish_id`, `stats_id`, `rotowire_id`, `rotoworld_id`,
`fantasy_data_id`, `yahoo_id`, `hashtag`, `player_shard`, `search_first_name`,
`search_full_name`, `search_last_name`, `birth_city/country/state`,
`high_school`, `competitions`, `metadata`, `practice_description`,
`practice_participation`, `news_updated`, `team_abbr`, `team_changed_at`, etc.
Measured live: `num players: 4029`, `num fields per player: 53`.

The app's own mobile-facing serializer `player_to_dict` (`server.py:1240–1260`)
emits only ~17 fields (and only the non-null extended ones) — proof that the
domain needs a small subset. This raw route bypasses that serializer entirely.

### Why it's slow / costly
Full-payload over-serialization. The wire payload is **4.84 MB uncompressed**
(measured: `size=4837423`). Even though the edge brotli-compresses it to
~660–676 KB, the **origin** still builds and serializes the full 4.8 MB dict on
**every** request (see OBS-ROUTE-03 — it is not edge-cached), and the client
still parses a multi-MB JSON document. Roughly 25+ of the 53 fields per player
are dead weight. The compressed size is dominated by the high-entropy ID
strings (`sportradar_id` UUIDs, `*_id` integers) that compress poorly.

### Evidence
- `server.py:4360–4365` — cache filter keeps all fields, only filters position.
- `server.py:4399–4404` — `return jsonify(cached)` ships the raw dict.
- Live: `curl … /api/sleeper/players` → `size=4837423` uncompressed;
  `gzip,br` → `676415`. Per-player field dump (live) shows 53 keys including
  ~13 external-provider ID fields the UI never shows.
- Contrast: `player_to_dict` (`server.py:1240`) — the deliberate client shape —
  is ~17 fields.

### Recommendation(s)
- **Option A (preferred):** add a slim projection for this route — map each
  cached player through a field-allowlist (reuse/extend `player_to_dict`'s key
  set: id, name, position, team, age, years_exp, injury_status, search_rank,
  adp, depth-chart, height/weight). Estimated payload drop to ~1.2–1.5 MB
  uncompressed / ~200–280 KB compressed (the ID/UUID fields are the bulk of the
  entropy). Web client (`web/js/app.js:661,792,2405`) is the only consumer of
  the full body; verify it doesn't read any stripped field before shipping.
  Effort: single file, one new projection + a per-player map. Risk: a client
  reading a now-absent field.
- **Option B:** keep the raw route but precompute a slim cache file once at sync
  time so the request thread serializes the already-trimmed dict (also helps
  OBS-ROUTE-03's re-serialize cost). Slightly more plumbing, larger win on
  origin CPU.
- **Option C (lowest effort, partial):** drop just the dead ID/search/birth/
  practice fields in the cache-write step (`server.py:4368–4369`) so the slim
  shape is shared by every consumer. Cuts ~40–50% with near-zero handler
  change; less precise than A.

### RICE-P
| Reach | Impact | Confidence | Effort | **Score** |
|------:|-------:|-----------:|-------:|----------:|
| 6 | 1 | 90% | 1 | **5.4** |

- **Estimated latency delta:** ~−1.0–1.5 s on the web cold-warm hop (4.8 MB →
  ~1.3 MB at the origin; ~660 KB → ~250 KB on the wire), plus a meaningful
  client-side JSON-parse reduction. Mobile is unaffected (it uses `/warm`), so
  Reach is web-weighted → 6.
- **Confidence note:** 90% — field bloat is measured and unambiguous; the only
  uncertainty is whether the web client silently consumes a stripped field
  (resolvable by grepping `web/js/app.js` for the field names before shipping).

### Related components
`server.py:4336` route, `_ensure_sleeper_cache_populated` (`:4337`),
`sleeper_players` (`:4392`, dead — see OBS-ROUTE-05), `player_to_dict` (`:1240`),
`web/js/app.js` (consumer), `docs/data-dictionary.md` (players shape).

### Prerequisites / dependencies
None. Independent of compression (OBS-ROUTE-02) and caching (OBS-ROUTE-03),
though it compounds with both.

### Regression risk
Medium-low. The web client is the live consumer; must confirm it doesn't read
`hashtag`, `team_abbr`, `search_*`, or any provider ID. No cross-client
invariant (tier colors / K-factors / ELO) touched — this is display data only.

---

## OBS-ROUTE-02 — Response compression is edge-only (Cloudflare); the Flask/gunicorn origin emits uncompressed bodies

- **Area:** backend routes / network boundary
- **Severity:** P2
- **Status:** observed
- **Evidence type:** measured

### What happens today
There is no `Flask-Compress` (or equivalent) in the app. Searched
`backend/` and `requirements*.txt` for `flask_compress` / `Compress(` /
`gzip` — **no matches** (the only `gzip` hit is an outbound Sleeper request
header at `server.py:5170`). The Flask app is created plainly at
`server.py:803` with no compression middleware and no `after_request` hook.
Live proof: with `Accept-Encoding: identity` the **origin** returns the full
4.84 MB (`size=4837423`, `x-render-origin-server: gunicorn`). The br/gzip we
observe on normal requests is applied by Cloudflare at the edge
(`server: cloudflare`, `content-encoding: br`).

### Why it's slow / costly
The compression that saves the wire bytes happens **outside** the origin, so:
(1) the origin still pays full serialization + full-body transfer cost to
Cloudflare on every request; (2) the app is **entirely dependent on Render's
Cloudflare edge** for compression — any path that doesn't go through it
(direct origin access, a future infra change, a non-CF CDN) drops to
uncompressed 4.8 MB. It also means the app cannot tune the gzip threshold or
choose what to compress. This is a latent risk more than a current
user-facing slowdown (the edge is currently doing the job), hence P2.

### Evidence
- `grep -rniE "flask_compress|Compress\(|gzip" backend/ requirements*.txt` →
  no compression library.
- `server.py:803` — `app = Flask(__name__, …)`, no compression config; no
  `@app.after_request` anywhere (grep returned none).
- Live: `Accept-Encoding: identity` → origin sends `size=4837423` uncompressed;
  `gzip,br` → `676415` with `server: cloudflare`.

### Recommendation(s)
- **Option A (preferred):** add `Flask-Compress` with a sensible
  `COMPRESS_MIN_SIZE` (~1–2 KB) and gzip/br levels. One dependency + a few
  lines at app init. Makes compression a property of the app, removes the
  edge-only dependency, and lets the origin send compressed bytes to Cloudflare
  (smaller origin→edge transfer). Low risk. **Note:** this overlaps with the
  edge — measure to avoid double-compress; configure CF passthrough or accept
  the origin handles it.
- **Option B:** do nothing at the app layer and instead **document** the
  reliance on Render/Cloudflare edge compression as an explicit infra
  invariant (runbook entry), and verify it's enabled. Zero code, zero risk, but
  leaves the latent dependency in place.

### RICE-P
| Reach | Impact | Confidence | Effort | **Score** |
|------:|-------:|-----------:|-------:|----------:|
| 6 | 0.5 | 80% | 0.5 | **4.8** |

- **Estimated latency delta:** near-zero **today** (edge already compresses for
  end users); the win is resilience + smaller origin→edge transfer. If edge
  compression ever lapses, this prevents a 4.8 MB → 660 KB (7×) regression.
- **Confidence note:** 80% — the absence of origin compression is measured; the
  user-facing latency gain is small *because the edge masks it*, so Impact 0.5.
  Raising it would require confirming whether origin→edge transfer is a
  measurable fraction of total (needs origin-side timing).

### Related components
`server.py:803` (app init), `render.yaml:13` (gunicorn), all large-payload
routes — primarily `/api/sleeper/players`.

### Prerequisites / dependencies
Coordinate with Cloudflare/Render edge to avoid redundant double-compression.

### Regression risk
Low. Must verify no double-compress (corrupt `content-encoding`) and that the
`Vary: Accept-Encoding` header stays correct.

---

## OBS-ROUTE-03 — `/api/sleeper/players` is re-serialized on every request — no ETag / Cache-Control / conditional-GET, and Cloudflare reports `DYNAMIC`

- **Area:** backend routes / caching
- **Severity:** P1
- **Status:** observed
- **Evidence type:** measured

### What happens today
The handler returns `jsonify(cached)` (`server.py:4399–4404`) with **no**
`ETag`, `Last-Modified`, or `Cache-Control` header. The only routes that set
`Cache-Control` are the social/OG image routes (`server.py:5997`, `:6094`,
`max-age=300`). Live, every `/api/sleeper/players` response carried
`cf-cache-status: DYNAMIC` across three consecutive requests — Cloudflare is
**not** caching it, so each request re-enters the origin, and Flask re-runs
`jsonify` on the 4,029-player / 53-field dict every time. The underlying data
changes at most once per daily Sleeper sync (`needs_player_sync`,
`server.py:4380`), so the payload is effectively static for ~24 h.

### Why it's slow / costly
Missing-cache + repeated-serialization anti-pattern. `jsonify` on a ~4.8 MB
dict is non-trivial CPU on a **single-worker** free dyno (`render.yaml:13`,
`--workers 1`): while it serializes, that one worker cannot service any other
request (trio, rankings, trade status polls). Because there's no ETag, a client
that already has the (rarely-changing) data still gets a full 4.8 MB body
re-sent instead of a 304. The web client warms this on **every** app load
(`web/js/app.js:661`), so the cost recurs per session with no reuse.

### Evidence
- `server.py:4399–4404` — `jsonify(cached)`, no headers.
- Live, 3× consecutive: `cf-cache-status: DYNAMIC` each time → no edge cache.
- `server.py:803` app init has no default cache headers; only `/og` + `/s`
  set `Cache-Control` (`:5997`, `:6094`).
- `render.yaml:13` — `--workers 1` → serialization blocks the sole worker.
- Repeated warm timings: total 1.26 s / 1.26 s / 2.18 s — variance consistent
  with origin re-work + single-worker contention, not a cached edge hit.

### Recommendation(s)
- **Option A (preferred):** add a strong `ETag` (hash of the cache file mtime or
  a sync version) + `Cache-Control: public, max-age=…` to the players route,
  and honor `If-None-Match` to return `304`. Lets Cloudflare cache it and lets
  clients skip re-download when unchanged. Pairs naturally with the daily sync
  cadence. Effort: small (one route + a conditional-GET check). Big repeat-hit
  win.
- **Option B:** precompute and cache the **serialized** JSON bytes (or the slim
  bytes from OBS-ROUTE-01) once per sync, and have the route return the
  prebuilt `Response` with the ETag. Removes per-request `jsonify` CPU entirely
  from the single worker. Slightly more code; best origin-CPU outcome.
- **Option C:** mark the route cacheable at the Render/Cloudflare layer
  (cache rule on the path with a short TTL). No app code, but couples behavior
  to infra config and still re-serializes on each cache-miss/expiry.

### RICE-P
| Reach | Impact | Confidence | Effort | **Score** |
|------:|-------:|-----------:|-------:|----------:|
| 6 | 1 | 85% | 1 | **5.1** |

- **Estimated latency delta:** repeat loads → ~−1–2 s when served as 304 / edge
  cache (full 4.8 MB origin trip avoided); also frees the single worker from
  repeated multi-MB `jsonify`, reducing contention on concurrent trio/rankings
  calls during a load. First-ever load unchanged.
- **Confidence note:** 85% — `DYNAMIC` and the missing headers are measured; the
  worker-contention magnitude on the free dyno is reasoned, not profiled
  (would need origin CPU timing to confirm). Combine with OBS-ROUTE-01 for the
  serialize-once win.

### Related components
`server.py:4336/4399` route, `render.yaml:13` (single worker), `web/js/app.js`
(per-load consumer), `needs_player_sync` (`:4380`), OBS-ROUTE-01 (slim payload),
OBS-ROUTE-02 (compression).

### Prerequisites / dependencies
None for Option A. Option B benefits from OBS-ROUTE-01's slim shape landing
first so the cached bytes are already trimmed.

### Regression risk
Low-medium. ETag must invalidate on the daily sync (tie it to the sync version
or file mtime) or clients could serve stale rosters. Test that a sync bumps the
ETag and a `If-None-Match` mismatch re-downloads.

---

## OBS-ROUTE-04 — `before_request` runs a synchronous DB write (`touch_user_activity`) on every authenticated request

- **Area:** backend routes / request middleware
- **Severity:** P2
- **Status:** observed
- **Evidence type:** static-analysis

### What happens today
`_stash_device_and_touch_activity` is registered `@app.before_request`
(`server.py:971`) and, for any request carrying a valid `X-Session-Token`,
calls `touch_user_activity(user_id, **info)` (`server.py:993`). That function
opens a transaction and runs a blocking `UPDATE users SET last_active_at=…`
(`database.py:929–935`) **synchronously, on the request thread, before the
handler runs** — on **every** authed call, including high-frequency ones like
`/api/trades/status` polling and every `/api/trio` fetch.

### Why it's slow / costly
Blocking write on the hot path. Every authed request pays a write-transaction
round-trip to Postgres (prod) before any business logic, regardless of whether
the endpoint is read-only. On the single-worker free dyno (`render.yaml:13`)
this serializes behind the DB for the full write latency. The
`/api/trades/status` poll loop (per the example in the audit templates, ~1.5 s
cadence) turns into a steady stream of `UPDATE users` writes purely to bump a
`last_active_at` timestamp — write amplification on the one column that almost
never needs sub-minute precision.

### Evidence
- `server.py:971–995` — `before_request` resolves the session and calls
  `touch_user_activity` unconditionally for authed requests.
- `database.py:907–937` — `touch_user_activity` opens `engine.begin()` and
  executes an `UPDATE` synchronously; not deferred or batched.
- `_device_info_from_request` (`server.py:963`) is cheap (header reads), so the
  cost is dominated by the DB write, not the parsing.
- Confirms a self-described intent ("on every authed API call",
  `database.py:914–916`) — it is by design, but unbounded in frequency.

### Recommendation(s)
- **Option A (preferred):** throttle the write — only `touch_user_activity` if
  `sess['last_active']` (already tracked in-session, e.g. `server.py:2788`) is
  older than N seconds (e.g. 60 s). Collapses a poll storm into ~1 write/min/user
  with no behavior change visible to anyone. Client-invisible, tiny change.
- **Option B:** move the write off the request thread (fire-and-forget to a
  small background queue / thread). Removes it from the critical path entirely
  but adds a worker and ordering concerns on the free tier.
- **Option C:** skip the touch on a known-hot read path (`/api/trades/status`)
  via an endpoint allowlist. Narrow, but targets the worst offender.

### RICE-P
| Reach | Impact | Confidence | Effort | **Score** |
|------:|-------:|-----------:|-------:|----------:|
| 8 | 0.5 | 70% | 0.5 | **5.6** |

- **Estimated latency delta:** −(one DB write round-trip) per authed request on
  the throttled-out path — order tens of ms each on Postgres, larger under
  single-worker contention; the bigger win is reduced write amplification and
  worker-occupancy during status polling.
- **Confidence note:** 70% — the synchronous write is certain from code, but the
  per-request latency it adds isn't measured (the endpoints are auth-gated; I
  could not time an authed request). A spike timing one authed call before/after
  would confirm Impact.

### Related components
`server.py:971` (`before_request`), `database.py:907` (`touch_user_activity`),
every authed route; worst-case `/api/trades/status` (`server.py:2782`).

### Prerequisites / dependencies
None. Option A reuses the existing in-session `last_active` field.

### Regression risk
Low. `last_active_at` precision loosens to ~1 min — confirm no notification/
re-engagement query depends on sub-minute freshness (`record_event` already
writes precise rows for discrete actions, so the denorm column is a coarse
pointer per `database.py:914–918`).

---

## OBS-ROUTE-05 — `/api/sleeper/players` decorator is bound to the wrong function; `sleeper_players()` is dead code

- **Area:** backend routes / correctness-adjacent (serialization path)
- **Severity:** P3
- **Status:** observed
- **Evidence type:** static-analysis

### What happens today
`@app.route("/api/sleeper/players")` (`server.py:4336`) decorates
`_ensure_sleeper_cache_populated` (`server.py:4337`), **not** the purpose-built
`sleeper_players()` handler (`server.py:4392`). Because the decorator binds to
whatever function immediately follows it, the route's view function is
`_ensure_sleeper_cache_populated`, which **returns the raw cache dict** — Flask
then `jsonify`s the returned dict, so the endpoint still works, but via the
populate-helper's return value, and `sleeper_players()` (the function with the
cache-hit fast path and error handling) is **never registered or called**
(grep: `sleeper_players` is referenced only at its own def and in its own log
string, `server.py:4392/4406`).

### Why it's slow / costly
Not a latency cost per se, but it's the reason OBS-ROUTE-01/03 land where they
do: the live serialization path is `_ensure_sleeper_cache_populated`'s return,
which has no cache-hit short-circuit logging and (more importantly) runs the DB
sync side-effects inline (`server.py:4376–4387`) on a cache-miss request — the
first cold caller pays `sync_players` + ADP fetch on the request thread before
the 4.8 MB body is returned. The intended `sleeper_players()` had a cleaner
cache-first path. Any future fix to the players serialization must edit the
**actually-bound** function, or it will have no effect.

### Evidence
- `server.py:4336–4337` — decorator immediately precedes
  `def _ensure_sleeper_cache_populated`.
- `server.py:4392` — `def sleeper_players()` has no decorator above it (the next
  decorator, `server.py:4414`, belongs to `sleeper_players_warm`).
- `grep -n "sleeper_players\b"` → only `:4392` (def) and `:4406` (its own log).

### Recommendation(s)
- **Option A (preferred):** rebind the route to `sleeper_players()` (move the
  decorator) so the registered handler is the one with the cache-first path and
  error handling, then apply OBS-ROUTE-01/03 there. Removes inline cold-sync
  from the body-return path. Trivial, but verify behavior parity first.
- **Option B:** if the current binding is intentional, delete the dead
  `sleeper_players()` to avoid confusing future edits, and document that the
  route is the populate-helper. Lowest risk, no behavior change.

### RICE-P
| Reach | Impact | Confidence | Effort | **Score** |
|------:|-------:|-----------:|-------:|----------:|
| 1 | 0.5 | 80% | 0.5 | **0.8** |

- **Estimated latency delta:** negligible in the warm/steady state; on a
  cold-cache first hit, Option A could remove the inline `sync_players` + ADP
  fetch from the response path (seconds, but reach = 1, a rare edge path).
- **Confidence note:** 80% — the mis-binding is clear from code; impact is small
  and mostly hygiene/correctness-of-future-edits. Primary value is flagging
  *where* OBS-ROUTE-01/03 fixes must be applied.

### Related components
`server.py:4336` route, `_ensure_sleeper_cache_populated` (`:4337`),
`sleeper_players` (`:4392`, dead), `sync_players` / `_fetch_sleeper_adp`
(inline side-effects, `:4378–4387`).

### Prerequisites / dependencies
Should be resolved **before** implementing OBS-ROUTE-01/03 so those edits land
on the correct function.

### Regression risk
Low-medium. Rebinding changes which function serves the route — must confirm
the cache-miss/populate side-effects (DB sync) still fire on a cold start
(today they run inside `_ensure_sleeper_cache_populated`, which `sleeper_players`
calls anyway at `:4404`). Behavior parity test on a cold cache required.

---

## OBS-ROUTE-06 — `session_init` does a full synchronous pool + dual-service rebuild on the request thread on every user change / cold login

- **Area:** backend routes / request-thread work
- **Severity:** P1
- **Status:** observed
- **Evidence type:** static-analysis

### What happens today
`POST /api/session/init` (`server.py:4431`) synchronously, on the request
thread, does: `_ensure_universal_pools()` for **both** scoring formats
(`server.py:4478`, builds player lists + seed maps from the 4 k-player cache and
per-format DP/ELO consensus data, `:768–773`); builds opponent + DB
`LeagueMember`s (`:4494–4547`); and, when the user changed or it's a cold
session (`need_rebuild`, `:4567`), builds **two** `RankingService` instances —
each of which loads swipe history from the DB and **replays every historical
swipe** (`replay_from_db`, `server.py:4598–4601`) plus loads tier overrides
(`:4630`). It then builds **two** `TradeService` instances and loads 7 days of
trade decisions (`:4673–4690`). The whole thing must complete before the
response returns, and `/api/trio` can't run until it does (`server.py:4642–4643`
comment: "Result is required before /api/trio can run, so we block").

### Why it's slow / costly
Expensive synchronous bootstrap on the critical login path. This is the single
heaviest blocking handler in the audited set: pool construction over ~4 k
players ×2 formats, DB reads for swipes/overrides/trade-decisions, and a full
swipe **replay** (which re-applies ELO math per historical swipe — cost grows
with the user's ranking history). It runs on the single free-tier worker
(`render.yaml:13`), and on a cold dyno it stacks on top of the cold-start +
first `/warm` cache hydration. The format service builds are already
parallelized across 2 threads (`server.py:4645–4659`), which helps, but the
pool build, member assembly, and trade-service loop remain serial, and the
**whole request blocks** the app boot before the first trio can render.

### Evidence
- `server.py:4474–4478` — `_load_sleeper_cache()` + `_ensure_universal_pools()`
  inline; `:768–773` builds per-format pools over the full cache.
- `server.py:4569–4659` — `need_rebuild` path builds 2 `RankingService`s, each
  doing `load_swipe_decisions` + `replay_from_db` (`:4598–4601`) +
  `load_tier_overrides` (`:4630`).
- `server.py:4683–4690` — builds 2 `TradeService`s, loads 7-day trade decisions
  (`:4673–4679`).
- `server.py:4642–4643` — explicit "block on completion … required before
  `/api/trio`".
- Could not measure live (auth/body required; observation-only, no POST).

### Recommendation(s)
- **Option A (preferred):** keep `session_init` returning a minimal "session
  ready" payload but defer the **trade-service** build + 7-day decision load
  (`server.py:4683–4690`) off the critical path — they're only needed when the
  user opens Trades, not for the first trio. Rankings services + pool stay
  (trio needs them). Shrinks the blocking section. Medium effort, client-visible
  only if Trades is opened before the deferred build finishes (guard with the
  existing job/lock pattern).
- **Option B:** cache the universal pools across users (they're user-independent
  — `server.py:4470–4473` notes pools are constant) so a warm process skips pool
  rebuild entirely; `_ensure_universal_pools` is already idempotent (`:751`), so
  confirm it's truly built once per process and not paying repeat cost.
- **Option C:** make the swipe `replay_from_db` incremental/snapshotted so a
  returning user doesn't replay full history each login (store a materialized
  ELO snapshot, replay only deltas). Larger effort; biggest win for heavy-history
  users. Coordinate with Agent 04 (data layer) — partly out of route scope.

### RICE-P
| Reach | Impact | Confidence | Effort | **Score** |
|------:|-------:|-----------:|-------:|----------:|
| 8 | 2 | 60% | 3 | **3.2** |

- **Estimated latency delta:** Option A could remove the trade-service build +
  7-day decision load from the login blocking path (estimate a few hundred ms to
  ~1 s, more on a cold dyno / heavy-history user). Needs measurement to confirm
  the split.
- **Confidence note:** 60% — the synchronous, blocking, replay-heavy structure
  is clear from code, but the actual wall-time (and how much is pool vs replay
  vs trade-svc) is unmeasured because the endpoint requires a POST + auth, which
  this audit cannot do. A profiled `session_init` would raise this sharply.

### Related components
`server.py:4431` (`session_init`), `_ensure_universal_pools` (`:743`),
`RankingService.replay_from_db`, `TradeService`, `load_swipe_decisions` /
`load_tier_overrides` / `load_trade_decisions` (data layer — Agent 04 overlap),
`/api/trio` (downstream blocked consumer).

### Prerequisites / dependencies
Option C depends on a snapshot/materialization change in the data/ranking layer
(coordinate with Agent 04). Options A/B are route-local.

### Regression risk
Medium. Deferring the trade-service build risks a race where Trades is opened
before it's ready — must reuse the existing lock/job pattern and fall back to a
synchronous build if accessed early. No ELO/tier invariant changes as long as
replay semantics are preserved (Option C must reproduce identical ELO — the
`replay_from_db` ordering and K-factors are a cross-client invariant per
`docs/cross-client-invariants.md`).

---

## OBS-ROUTE-07 — `/api/trades/matches` (single-league) enriches names per-match from session state; fine today, but unlike its sibling it has no batch guard if it ever sources from the DB

- **Area:** backend routes / serialization (N+1 watch)
- **Severity:** P3
- **Status:** observed
- **Evidence type:** static-analysis

### What happens today
`/api/trades/matches` (`server.py:3044`) enriches each match's give/receive
player names from the in-memory **session** `players` dict
(`players_dict = {p.id: p for p in g_players}`, `server.py:3065`) — an O(1)
in-memory lookup per id, no DB hit. By contrast, the sibling routes
`/api/trades/matches/all` (`:3094`) and `/api/trades/awaiting` (`:3194`) were
explicitly refactored to **batch** their enrichment with two `IN`-clause queries
(`server.py:3130–3172`, `:3227–3258`) precisely to avoid an N+1 against the
players/leagues tables, because cross-league matches reference players outside
the active session pool.

### Why it's slow / costly
**No current cost** — the single-league route's lookups are in-memory, so this
is *not* an N+1 today. It's flagged as a latent inconsistency: the single-league
handler relies on `g_players` containing every referenced player id (true while
matches are within the active league), whereas its siblings deliberately hit the
DB in batch. If a future change lets `/api/trades/matches` reference an id
outside `g_players` (e.g. a roster the session pool trimmed), the
`if pid in players_dict` guard (`server.py:3071–3074`) silently drops the name
rather than falling back — a correctness gap, not a perf one. Recording it so
synthesis can route it.

### Evidence
- `server.py:3065` — `players_dict` built from session `g_players` (in-memory).
- `server.py:3068–3075` — per-match list comprehensions guarded by
  `if pid in players_dict` (drops unknown ids silently).
- Contrast: `server.py:3130–3172` (matches/all) and `:3250–3258` (awaiting) —
  batched `IN`-clause enrichment against `players_table`/`leagues_table`.

### Recommendation(s)
- **Option A (preferred):** leave as-is for performance (in-memory is optimal);
  add a one-line note that the silent-drop guard could hide a missing name. No
  perf change. Lowest effort.
- **Option B:** for consistency with the siblings, fall back to a batched DB
  lookup only for ids missing from `g_players` (preserves the in-memory fast
  path, closes the silent-drop gap). Small effort; pays off only if the session
  pool ever stops being a superset of single-league match players.

### RICE-P
| Reach | Impact | Confidence | Effort | **Score** |
|------:|-------:|-----------:|-------:|----------:|
| 6 | 0.25 | 50% | 1 | **0.75** |

- **Estimated latency delta:** ~0 today (in-memory lookups). The value is
  correctness/robustness, not latency.
- **Confidence note:** 50% — it is firmly *not* a perf problem now; flagged only
  so synthesis is aware the three matches endpoints diverge in their enrichment
  strategy.

### Related components
`server.py:3044` (`get_trade_matches`), `:3094` (`matches/all`), `:3194`
(`awaiting`), `load_matches`, `players_table`.

### Prerequisites / dependencies
None.

### Regression risk
Low. Option B adds a conditional DB read only on a cache-miss id; must keep the
in-memory fast path for the common case.

---

## Top 3 by RICE-P

1. **OBS-ROUTE-04 — throttle the per-request `touch_user_activity` write** —
   RICE-P **5.6** (P2). Trivial (0.5d), highest reach (every authed request),
   removes a synchronous DB write from the hot path / poll loops.
2. **OBS-ROUTE-01 — slim the `/api/sleeper/players` payload (53→~17 fields)** —
   RICE-P **5.4** (P1). Measured 4.8 MB → est. ~1.3 MB at origin; cuts wire
   bytes + client parse on the web load path. Single-file change.
3. **OBS-ROUTE-03 — add ETag / Cache-Control / conditional-GET to players** —
   RICE-P **5.1** (P1). Stops re-serializing a near-static 4.8 MB dict on the
   single worker every request; enables 304s and edge caching
   (`cf-cache-status: DYNAMIC` today).

> Note: OBS-ROUTE-06 (`session_init` rebuild) is P1 with high Impact (2) but
> scores 3.2 due to large Effort (3) and unmeasured Confidence (60%) — a
> profiling spike on an authed `session_init` would likely raise it into the top
> tier and is worth doing early.

---

## CROSS-REF (outside route-layer scope — route to other agents)

- **Agent 04 (data/DB):** `RankingService.replay_from_db` re-applies full swipe
  history on every cold `session_init` (`server.py:4598–4601`) — a materialized
  ELO snapshot would cut login cost for heavy-history users. Also
  `_fetch_sleeper_adp` + `sync_players` run **inline** on a cold-cache
  `/api/sleeper/players` request (`server.py:4376–4387`) — DB sync on the
  request thread.
- **Agent 06 (network / cold-start):** single gunicorn worker (`render.yaml:13`,
  `--workers 1`) means any multi-MB `jsonify` (players) or blocking handler
  (`session_init`) stalls all concurrent requests; free-dyno cold start stacks
  on top. Compression is edge-only (OBS-ROUTE-02) — confirm Render/Cloudflare
  edge compression is a guaranteed invariant.
- **Agent 01 (API client) / Agent 02 (data-fetching cache):** web client warms
  the full 4.8 MB `/api/sleeper/players` on every load (`web/js/app.js:661,
  792, 2405`) while mobile correctly uses `/api/sleeper/players/warm`
  (`mobile/src/api/sleeper.ts:48`) — consider migrating web to a slim/cached
  variant once OBS-ROUTE-01/03 land.
