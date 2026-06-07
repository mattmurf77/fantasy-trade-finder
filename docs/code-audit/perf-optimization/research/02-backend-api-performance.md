# 02 — Backend API Performance (Flask / Python)

> Research phase only. No code changes. All recommendations cite primary or strong secondary sources.

---

## TL;DR

- **Payload shaping is the single highest-leverage fix**: the 4.8 MB player endpoint can be reduced 73–95% by selecting only fields the mobile UI renders, at the SQL level — no new infrastructure required.
- **gzip via Flask-Compress is a one-line win** for all JSON endpoints above 500 bytes; on a single-worker constrained dyno, keep compression level at 6 and skip brotli to avoid CPU spikes.
- **Switch gunicorn sync → gthread** (workers=1, threads=4) immediately; the default sync worker does not support keep-alive, meaning every mobile request pays TCP setup cost.
- **ETag / Last-Modified conditional GET** can eliminate the payload entirely on cache-hits; TanStack Query does not handle 304s automatically on RN — the fetch wrapper must surface ETags and send `If-None-Match`.
- **orjson is a near-zero-risk 5–6× serialisation speedup** for the player endpoint that currently dominates response time.
- **Cursor pagination** (keyset) should replace offset pagination on any collection endpoint returning > 100 rows; offset scans grow linearly and can reach 8 s at row 200,000.
- **N+1 queries** in route handlers are the most common silent killer; `selectinload` / batch IN-clause patterns show documented 84% reduction in query time.
- **ASGI (Quart)** is a long-term option worth tracking but has non-trivial prerequisites (async-all-the-way-down); do not pursue until other tactics are exhausted.

---

## Why it matters for FTF

FTF's backend runs on Render free tier: one gunicorn worker, cold starts of 30–60 s after 15 min of inactivity, SQLite in dev / Postgres in prod. The mobile client (RN + TanStack Query) fetches players and trades on every core screen. Known pain points:

| Symptom | Root suspect |
|---|---|
| Player list feels sluggish | 4.8 MB JSON payload serialised by stdlib `json`, sync worker blocks on every request |
| Trade suggestions slow | Likely N+1 queries loading player data per trade leg |
| First load on cold dyno catastrophic | Render free-tier sleep; also no connection pooling benefit when the single worker is blocked |
| Mobile on cellular worse than WiFi | No compression, no conditional GET, no keep-alive (sync worker) |

Every tactic below is scored on the **Impact ladder** from `../templates/scoring-criteria.md`.

---

## Tactics

### 1. Payload shaping — sparse fieldsets / field selection

**What it is** — the server exposes a `?fields=` query parameter (or route convention) allowing clients to request only the columns they need. The field list is pushed all the way to the SQL `SELECT`, so unneeded columns are never fetched from the database.

**When to use it** — any endpoint where the full row schema has more columns than the mobile screen renders. The player endpoint (~4.8 MB) is the canonical example; the trade endpoint is a secondary candidate. Do NOT apply to small, stable, fully-consumed payloads.

**Expected impact** — **Massive (3)**. Primary-source benchmarks (oneuptime.com field-selection guide, 2026) measured: query time −73%, payload −95%, parse time −87%, memory −86% on a 15 KB → 800 B example. For a 4.8 MB payload the bandwidth saving alone is substantial: at 1 Mbps down (weak cellular), 4.8 MB takes ~38 s; a 95% reduction cuts that to ~2 s.

**RN/Flask applicability** — directly applicable with zero new libraries. In Flask (SQLAlchemy Core), pass an explicit column list to `select()`. Parse `request.args.get("fields")` in the route, split on commas, validate against an allowlist, then build the column clause. TanStack Query passes the `?fields=` param as part of the query key, ensuring the cache respects the field set.

**Cost / risk** — Low-to-medium effort. Allowlist validation is required to prevent accidental exposure of sensitive columns. Must add integration test for each endpoint that adopts it. Risk: if a client omits a field it later needs, it gets `undefined` — document the contract clearly.

**Source(s)** — [OneUptime: How to Implement API Field Selection (2026)](https://oneuptime.com/blog/post/2026-01-30-api-field-selection/view); [flask-rest-jsonapi sparse fieldsets](https://flask-rest-jsonapi.readthedocs.io/en/latest/sparse_fieldsets.html); [JSON:API sparse fieldsets spec](https://www.jsonapi.net/usage/reading/sparse-fieldset-selection.html)

---

### 2. Response compression — gzip via Flask-Compress

**What it is** — Flask-Compress wraps every response matching a MIME-type list and compresses the body, setting `Content-Encoding` automatically. Checks the client's `Accept-Encoding` header.

**When to use it** — any JSON or HTML response above the minimum-size threshold (default 500 bytes; Zuplo recommends 1 024 bytes as a more conservative choice). Do NOT compress binary/already-compressed formats (JPEG, PNG, gzip archives). Do NOT compress at high CPU levels on a constrained single-worker dyno.

**Expected impact** — **High (2)** for the player and trade endpoints. JSON typically compresses 70–85% with gzip. A 4.8 MB payload → ~720 KB at gzip level 6. On 1 Mbps cellular: 4.8 MB = 38 s; 720 KB = 5.8 s — a 32-second improvement even before field selection is applied. After field selection reduces the payload to ~240 KB, gzip takes it to ~36 KB (< 0.3 s on cellular).

**gzip vs brotli on a constrained dyno** — Brotli achieves a slightly higher compression ratio but at "moderate to high" CPU cost vs gzip's "low" CPU cost ([Zuplo compression guide](https://zuplo.com/learning-center/implementing-data-compression-in-rest-apis-with-gzip-and-brotli)). On a single-worker Render free-tier dyno, the extra CPU per request risks raising p95/p99 latency for concurrent requests. **Recommendation: use gzip at level 6; disable brotli (`COMPRESS_BR_LEVEL` removed from the algorithm list) until the service is on a paid, multi-worker instance.** Flask-Compress defaults: `COMPRESS_LEVEL=6`, `COMPRESS_MIN_SIZE=500`, priority order `['zstd', 'br', 'gzip', 'deflate']` — override to `['gzip']` for safety on free tier.

**RN/Flask applicability** — `pip install Flask-Compress`, two lines of config. TanStack Query's underlying `fetch` and React Native's network layer both send `Accept-Encoding: gzip` by default on modern RN; no client change required.

**Cost / risk** — Effort: **0.5** (one-liner). Risk: streaming responses + gzip can have edge cases with Flask-Compress; test the streaming player endpoint separately. `WSGI_MIDDLEWARES` compatibility with compression has known quirks in debug mode.

**Source(s)** — [Flask-Compress PyPI](https://pypi.org/project/Flask-Compress/); [Zuplo gzip vs brotli guide](https://zuplo.com/learning-center/implementing-data-compression-in-rest-apis-with-gzip-and-brotli); [OneUptime API compression config (2026)](https://oneuptime.com/blog/post/2026-01-24-configure-api-compression/view)

---

### 3. Pagination — cursor (keyset) vs offset for large collections

**What it is** — **Offset pagination** (`LIMIT n OFFSET k`) scans and discards the first k rows. **Cursor/keyset pagination** uses a stable column value (e.g., `id > last_seen_id`) as the filter, so the DB uses the index directly with no scan.

**When to use it** — any collection endpoint returning > ~50 rows should be paginated. Cursor/keyset is preferred over offset when:
- The collection is large (> 1 000 rows)
- The client scrolls continuously (not random-page-jump UI)
- Real-time inserts make offset pages unstable ("page shear")

Offset is acceptable when the total count and random-access navigation are required (admin UIs, search results with page-number links).

**Expected impact** — **Massive (3)** for a 4.8 MB all-players endpoint. Benchmarks ([DesignGurus pagination guide](https://designgurus.substack.com/p/api-pagination-guide-cursor-vs-offset)): offset at page 10,000 (OFFSET 199,980) = 8,200 ms; cursor equivalent = ~8 ms. For a SQLite dev instance with ~500 players the gain is proportionally smaller but still meaningful. The real FTF win is eliminating the 4.8 MB single-shot dump entirely.

**RN/Flask applicability** — Flask route adds `?cursor=<last_id>&limit=50`. SQLAlchemy Core: `select(players).where(players.c.id > cursor_id).limit(page_size)`. TanStack Query supports `useInfiniteQuery` with `getNextPageParam` extracting the next cursor from the response envelope — this is the idiomatic RN integration.

**Cost / risk** — Effort: **2** (Flask route change + RN `useInfiniteQuery` migration). Risk: cursor-based pagination requires a stable sort key with an index; ensure `players.id` (or `players.sleeper_id`) has an index. Cannot expose total-count header without a separate `COUNT(*)` query.

**Source(s)** — [Medium: API Pagination — Cursors, Limit-Offset, Timestamp](https://medium.com/@anupamk36/api-pagination-cursors-limit-offset-timestamp-pagination-data-shuffling-and-beyond-32636fc006af); [flask-sqlalchemy pagination issue #518](https://github.com/pallets-eco/flask-sqlalchemy/issues/518)

---

### 4. HTTP caching — ETag / Last-Modified / Cache-Control / conditional GET (304)

**What it is** — The server includes an `ETag` (hash of the response body) or `Last-Modified` (timestamp) header. On subsequent requests the client sends `If-None-Match` / `If-Modified-Since`; if data has not changed the server responds `304 Not Modified` with no body.

**When to use it** — read-heavy endpoints whose data changes infrequently relative to how often clients poll them. The player roster changes at most a few times per week; ETags would make the polling free after the first load. Trade suggestions change when the user's ratings change — also a good candidate. Do NOT apply to endpoints that produce unique responses per user and per request (e.g., random matchup selection).

**Expected impact** — **Massive (3)** on cache-hit sessions. A 304 response saves the entire payload download (4.8 MB → ~400 bytes) and most of the server work if the ETag check short-circuits the DB query. Latency delta on a warm cache-hit over cellular: 38 s → ~0.1 s.

**TanStack Query and 304s** — Critical caveat: TanStack Query does **not** automatically surface HTTP 304 responses to the application layer on React Native ([GitHub discussion #4454](https://github.com/TanStack/query/discussions/4454)). The browser handles 304s transparently in a browser context; on RN the fetch wrapper must manually read `ETag` from the response headers, store it (e.g., AsyncStorage or a Zustand slice), and inject `If-None-Match` on subsequent fetches. The query function must then check for `304` status and return the cached data unchanged. This integration is non-trivial.

**Flask implementation** — Use `flask.make_response()` with `response.set_etag(hashlib.md5(data).hexdigest())` and call `response.make_conditional(request)` which handles the 304 short-circuit automatically. For `Last-Modified`, set `response.last_modified = row.updated_at`. Reference: [Poespas Flask conditional caching guide (2024)](https://blog.poespas.me/posts/2024/08/09/flask-caching-with-conditional-get-headers/); [flask-rest-api ETag docs](https://flask-rest-api.readthedocs.io/en/stable/etag.html).

**Cost / risk** — Effort: **2** server-side, **3** including RN integration (ETag storage and injection). Risk: if the ETag is computed from the serialised response, it still requires serializing — decouple the ETag from a DB `updated_at` timestamp to short-circuit the query entirely.

**Source(s)** — [BugFactory: HTTP Caching with Last-Modified](https://bugfactory.io/articles/http-caching-with-last-modified-and-if-modified-since-headers/); [TanStack Query 304 discussion](https://github.com/TanStack/query/discussions/4454); [Zuplo: Optimizing REST APIs with Conditional Requests](https://zuplo.com/learning-center/optimizing-rest-apis-with-conditional-requests-and-etags)

---

### 5. Connection reuse — HTTP keep-alive, gunicorn worker/thread config

**What it is** — TCP connection setup (3-way handshake + TLS) adds 50–200 ms on mobile networks. HTTP keep-alive reuses the same TCP connection for multiple requests. Gunicorn's default **sync worker** does not support keep-alive; each response closes the connection.

**When to use it** — always. There is no scenario where closing every connection is preferable for a mobile API.

**Gunicorn configuration for single-worker Render free tier:**

| Setting | Default (sync) | Recommended |
|---|---|---|
| `worker_class` | `sync` | `gthread` |
| `workers` | 1 | 1 (free tier RAM limit) |
| `threads` | 1 | 4 |
| `keepalive` | 2 | 5 |

`gthread` with `threads=4` gives 4 concurrent requests on one worker, enables keep-alive, and uses less RAM than spawning 4 worker processes. Gunicorn docs explicitly state: "the sync worker does not support persistent connections — each connection is closed after response has been sent."

**Why it matters on mobile** — mobile radios (LTE/5G) pay higher per-connection overhead than desktop WiFi. Eliminating the setup cost per request is especially valuable for the typical FTF usage pattern: open app → fetch league → fetch players → fetch trades (3 sequential requests that could share one connection with keep-alive).

**Expected impact** — **High (2)**. Latency delta: 50–150 ms saved per request on cellular by reusing an existing connection vs establishing a new one. For a 3-request boot sequence: 150–450 ms total.

**Cost / risk** — Effort: **0.5** (gunicorn config change, one line in `Procfile` or `gunicorn.conf.py`). Risk: `gthread` increases memory per request slightly; on Render free tier (512 MB RAM) 4 threads is safe given typical Flask route memory usage.

**Source(s)** — [Gunicorn Design docs](https://gunicorn.org/design/); [Medium: Gunicorn 3 means of concurrency](https://medium.com/building-the-system/gunicorn-3-means-of-concurrency-efbb547674b7); [Medium: Uvicorn/Gunicorn tweaks](https://medium.com/@connect.hashblock/8-uvicorn-gunicorn-tweaks-that-make-fastapi-fly-c34bd1c187c5)

---

### 6. JSON serialisation cost — orjson vs ujson vs stdlib json

**What it is** — Python's stdlib `json.dumps` is a pure-Python implementation. `ujson` is a C extension (~3× faster). `orjson` is a Rust + SIMD extension (~5–6× faster) that also returns `bytes` directly, skipping the UTF-8 encoding step that a web server would otherwise do separately.

**When to use it** — when serialisation is a measurable fraction of endpoint latency. For the 4.8 MB player endpoint this is highly likely. For small payloads (< 1 KB) the gain is negligible and stdlib is simpler.

**Expected impact** — **High (2)** for the player endpoint. Concrete benchmark ([dollardhingra.com, 3M iterations](https://dollardhingra.com/blog/python-json-benchmarking/)): stdlib = 12.5 s, ujson = 4.4 s, orjson = 2.3 s. For a 4.8 MB payload, serialisation alone could dominate CPU time on a single-threaded worker; orjson cuts it by 80%. Note: ujson is in maintenance-only mode (per PyPI) — skip directly to orjson.

**Flask integration** — override `app.json_provider_class` with a custom provider using `orjson.dumps`. `orjson.dumps` returns `bytes`, not `str`; pass directly to `Response(data, mimetype="application/json")` to skip the extra encode. Reference: [DEV.to: Turbocharging Flask with orjson](https://dev.to/deepak_mishra_35863517037/turbocharging-flask-high-performance-serialization-with-orjson-4an3).

**Cost / risk** — Effort: **1** (one custom JSON provider class, one `pip install orjson`). Risk: orjson is stricter than stdlib — it rejects non-serialisable types (e.g., custom ORM objects) that stdlib's default encoder would silently convert to strings. All routes must be tested to confirm they produce valid output. orjson does not support circular references.

**Source(s)** — [dollardhingra.com benchmarks](https://dollardhingra.com/blog/python-json-benchmarking/); [pythonspeed.com: Choosing a faster JSON library](https://pythonspeed.com/articles/faster-json-library/); [DEV.to: orjson Flask integration](https://dev.to/deepak_mishra_35863517037/turbocharging-flask-high-performance-serialization-with-orjson-4an3)

---

### 7. Avoiding N+1 in route handlers — batch / IN-clause patterns

**What it is** — an N+1 query occurs when a route fetches a list of N entities then issues one query per entity to load related data, resulting in N+1 round-trips to the DB. For trade suggestions that include player details, this pattern means O(players_per_trade × trades_shown) queries per request.

**When to use it** — any handler that iterates a collection and accesses a relationship. In FTF this is most likely in `trade_service.py` when building trade objects that include player names/stats, and in any endpoint that serialises `Trade.give_players` + `Trade.receive_players`.

**Expected impact** — **Massive (3)** if N+1 exists on the trade endpoint. Documented real-world benchmark ([abhishekrath.substack.com](https://abhishekrath.substack.com/p/the-n1-query-problem)): 1 300 ms → 200 ms (84% reduction) by switching from lazy-loaded N+1 to `selectinload`.

**SQLAlchemy Core patterns:**
- For ORM relationships: use `selectinload(Trade.players)` — issues one additional `SELECT ... WHERE player_id IN (...)` query instead of N queries.
- For SQLAlchemy Core (which FTF uses): collect all needed IDs in the first query, then `select(players).where(players.c.id.in_(id_list))` in a second query. Avoid the ORM lazy-load trap by never accessing a relationship attribute inside a `for` loop without pre-loading.
- `bulk_save_objects` / batch INSERT replaces per-row INSERTs for write paths.

**Cost / risk** — Effort: **1–2** per endpoint (must audit each handler). Risk: incorrect eager loading can over-fetch in the other direction (Cartesian products with `joinedload` on multiple collections). Prefer `selectinload` over `joinedload` for collections.

**Source(s)** — [Medium: Optimizing SQLAlchemy Queries in Flask](https://medium.com/@yashwanthnandam/optimizing-sqlalchemy-queries-in-flask-05d0caeec501); [abhishekrath: N+1 SQLAlchemy pitfalls and fixes](https://abhishekrath.substack.com/p/the-n1-query-problem); [SQLServerCentral: N+1 comprehensive guide](https://www.sqlservercentral.com/articles/how-to-avoid-n1-queries-comprehensive-guide-and-python-code-examples)

---

### 8. Streaming responses / chunked transfer for large payloads

**What it is** — instead of buffering the entire response in memory before sending, Flask uses a Python generator with `yield` to push chunks as they are produced. The HTTP `Transfer-Encoding: chunked` header signals the client not to wait for `Content-Length`. The client can begin parsing and rendering before the full payload arrives.

**When to use it** — large responses (> ~500 KB) where the client can render progressively. For FTF: the player list could yield players in batches of 50, allowing the RN `FlatList` to begin rendering the first items while the rest arrive. Also useful if players are being fetched from Sleeper API in pages on the backend — stream as each page is fetched rather than buffering all pages.

**When NOT to use it** — when the client requires the full dataset before rendering (e.g., trade scoring that requires all player values simultaneously). Do not use streaming if compression middleware may be incompatible (Flask-Compress does not support gzip for streaming by default — gzip is excluded from `COMPRESS_STREAMING_ALGORITHMS`).

**Expected impact** — **Medium (1)** for perceived performance (TTFB improvement; first items visible sooner) but **Low (0.5)** for total transfer time. The main win is user-perceived speed, not raw throughput.

**Flask implementation** — `return stream_with_context(generate())` where `generate()` yields NDJSON lines (one JSON object per line, `\n`-delimited). Client splits chunks on `\n` to parse each object. ([Flask streaming docs](https://flask.palletsprojects.com/en/stable/patterns/streaming/))

**Cost / risk** — Effort: **2**. Risk: Headers cannot be changed after streaming starts (set `Content-Type` before yielding). The `request` context is not available inside the generator unless wrapped in `stream_with_context`. Some WSGI middlewares break streaming. RN's `fetch` API returns a `ReadableStream`; consuming NDJSON requires a custom streaming consumer (not supported by TanStack Query out of the box — would need a custom `queryFn`).

**Source(s)** — [Flask streaming docs (3.1.x)](https://flask.palletsprojects.com/en/stable/patterns/streaming/); [lvngd.com: Streaming with Flask and Fetch](https://lvngd.com/blog/streaming-data-flask-and-fetch-streams-api/); [blog.pamelafox.org: Fetching JSON over streaming HTTP (2023)](http://blog.pamelafox.org/2023/08/fetching-json-over-streaming-http.html)

---

### 9. ASGI vs WSGI — async Flask (Quart) for I/O-bound endpoints

**What it is** — WSGI assumes one request occupies one worker for its entire duration. If a handler spends 195 ms of its 200 ms waiting on a DB query, the worker is blocked for all 200 ms. ASGI (via `async`/`await`) parks coroutines during I/O waits and serves other requests in the meantime. Quart is a drop-in ASGI reimplementation of Flask with an identical API surface.

**When to use it** — when the backend makes many concurrent external I/O calls (multiple Sleeper API fetches, multiple DB queries that could run in parallel) and the sync worker concurrency (gthread threads) is saturated. A real-world case study ([super.com engineering, Medium](https://medium.com/super/how-we-optimized-service-performance-using-the-python-quart-asgi-framework-and-reduced-costs-by-1362dc365a0)) showed 150 → 300+ RPS and 90% cost reduction after migrating to Quart for a service making 40+ parallel external calls per request. FTF's trade endpoint may benefit if it fans out to Sleeper.

**When NOT to use it** — when the stack is not fully async. "ASGI can be faster only if you've written your application as async from the framework to the backend." Every dependency must be async: `asyncpg` instead of `psycopg2`, `httpx` instead of `requests`, async SQLAlchemy sessions. Any synchronous call blocks the event loop for all concurrent requests — this is worse than WSGI with threads. For FTF's SQLite dev / Postgres prod setup, the migration cost is substantial.

**Expected impact** — **High (2)** if FTF's trade endpoint makes multiple I/O calls per request. **Minimal (0.25)** if handlers are sequential and I/O is mostly single DB queries, since gthread already handles that case.

**Flask → Quart migration** — replace `from flask import Flask` with `from quart import Quart`; add `async`/`await` to route handlers; replace `requests` with `httpx`; replace `psycopg2` with `asyncpg` or SQLAlchemy async engine. Serve with `hypercorn` or `uvicorn` instead of gunicorn.

**Feasibility for FTF (current state)** — **Low near-term**. Prerequisites: async SQLAlchemy Core queries, async Sleeper client, full test coverage before migration. Recommend as a Phase 2 item after the synchronous optimisations are complete.

**Source(s)** — [super.com: Quart migration 90% cost reduction](https://medium.com/super/how-we-optimized-service-performance-using-the-python-quart-asgi-framework-and-reduced-costs-by-1362dc365a0); [tonybaloney.github.io: Fine-tuning WSGI and ASGI](https://tonybaloney.github.io/posts/fine-tuning-wsgi-and-asgi-applications.html); [LAAC: Should you use asyncio?](https://www.laac.dev/blog/should-you-use-asyncio-next-python-web-application/); [DEV.to: Quart vs FastAPI vs Flask-SocketIO](https://dev.to/deepak_mishra_35863517037/modern-alternatives-flask-socketio-vs-fastapi-and-quart-5gh6)

---

## Impact ladder summary

| # | Tactic | Impact label | Notes |
|---|---|---|---|
| 1 | Sparse fieldsets / field selection | **Massive** | Push field list to SQL |
| 4 | ETag conditional GET (cache-hit path) | **Massive** | Needs RN fetch-wrapper integration |
| 7 | Eliminate N+1 queries | **Massive** | If N+1 confirmed in trade handler |
| 3 | Cursor pagination (replaces all-at-once dump) | **Massive** | Eliminates the large single fetch |
| 2 | gzip compression (Flask-Compress) | **High** | Level 6, gzip only on free tier |
| 5 | Keep-alive via gthread worker | **High** | Removes TCP setup cost per request |
| 6 | orjson serialisation | **High** | ~5× faster for large payloads |
| 9 | ASGI / Quart migration | **High** (conditional) | Only if I/O parallelism is the bottleneck |
| 8 | Streaming / chunked transfer | **Medium** | Perceived perf; harder RN integration |

---

## Anti-patterns to flag in the audit

- **`json.dumps` in route handlers** — grep: `import json` in `backend/server.py` or `trade_service.py`; any `json.dumps(` call in a route context. Replace with orjson.
- **`SELECT *` or full-table fetch** — grep: `.all()` or `select(players)` without a `.where()` clause returning large result sets. Flag if no field-level column list is passed.
- **Loop-inside-route accessing relationships** — grep for `for … in result:` followed by attribute access (`.give_players`, `.receive_players`, `.player_stats`) without a preceding `selectinload` or IN-clause batch fetch.
- **`OFFSET`-based pagination** — grep: `.offset(` in `server.py` or `trade_service.py`. Verify offset value is bounded; flag if unbounded or if collection can exceed 500 rows.
- **Missing `Cache-Control` / `ETag` headers on read endpoints** — grep: routes decorated with `@app.route(… methods=["GET"])` that do not set `response.cache_control` or `response.set_etag`. All read endpoints returning slowly-changing data should have headers.
- **Sync gunicorn worker** — grep: `Procfile` or `gunicorn.conf.py` for absence of `-k gthread` or `--worker-class gthread`. Default `sync` worker = no keep-alive.
- **`requests` library inside route handlers** (blocking I/O) — grep: `import requests` in `backend/`; any `requests.get(` in a route handler that runs synchronously in the gunicorn worker thread.
- **Uncompressed large responses** — if `Flask-Compress` is absent from `requirements.txt`, flag all endpoints returning JSON > 1 KB.
- **Sleeper API calls inside the hot path without caching** — grep: any HTTP call to `api.sleeper.app` in a route handler that is not wrapped in a cache layer. Sleeper player data is near-static and should be pre-fetched or cached.

---

## Recommended defaults for FTF

| Setting | Recommendation | Rationale |
|---|---|---|
| **Compression** | Flask-Compress, `COMPRESS_MIMETYPES = ["application/json"]`, `COMPRESS_LEVEL = 6`, `COMPRESS_MIN_SIZE = 1024`, algorithm list = `["gzip"]` | Gzip only on free tier to avoid brotli CPU spikes; 1 KB threshold skips tiny health-check responses |
| **Gunicorn worker class** | `gthread`, `workers=1`, `threads=4`, `keepalive=5` | Free-tier single-worker; gthread enables keep-alive; 4 threads handles concurrent mobile requests |
| **JSON serialiser** | `orjson` via custom Flask `JSONProvider` | ~5× faster for the player payload; zero new infrastructure |
| **Player endpoint pagination** | Cursor keyset, `limit=50` default, max `limit=200` | Eliminates the 4.8 MB dump; cursor on `players.sleeper_id` (indexed) |
| **Field selection** | `?fields=` query param, validated against allowlist; default set = fields rendered by `PlayerCard` component | Start with the player list endpoint; extend to trades |
| **ETag strategy** | Derive ETag from `MAX(updated_at)` of queried rows; store in DB not computed from response body | Allows DB short-circuit before serialisation; avoid full-payload hash |
| **Cache-Control** | `Cache-Control: max-age=300, stale-while-revalidate=600` on player and league endpoints | Players change infrequently; 5-min fresh, 10-min stale serves mobile revalidation well |
| **N+1 audit** | Run `SQLALCHEMY_ECHO=True` and inspect the trade endpoint in dev; confirm no per-trade player query | Baseline measurement before and after applying `selectinload` |
| **orjson strictness guard** | Wrap the JSON provider in a try/except; fall back to stdlib for non-serialisable types | Prevents silent 500 during migration |

---

## Open questions / needs measurement

1. **What fraction of the 4.8 MB is redundant fields?** Audit `PlayerCard` / `TradeCard` to enumerate all fields actually rendered. The 95% payload-reduction benchmark assumes a 15 KB → 800 B example; FTF's ratio may differ.
2. **Is the player endpoint latency dominated by serialisation or by the DB fetch?** Add `time.perf_counter()` around `db.execute(select(players))` and `json.dumps(result)` separately to know where to focus.
3. **Does the trade endpoint have N+1?** Enable `SQLALCHEMY_ECHO=True` on a trades request and count the queries. If > 5 queries for 10 trades, N+1 is confirmed.
4. **What is the actual Render cold-start latency today?** Measure with a cron-ping or `curl --trace-time` from an external host. Cold starts on free tier are documented at 30–60 s; confirm whether the warm-ping boot endpoint (#57) has resolved this.
5. **Does TanStack Query on RN auto-send `If-None-Match`?** Confirm with a network trace (Charles Proxy or Metro debugger) whether the current fetch wrapper preserves ETags at all. If not, the ETag tactic requires a custom fetch wrapper before it has any effect.
6. **Is gzip already applied at the Render load balancer level?** Render may apply gzip upstream; if so, Flask-Compress would double-compress. Confirm with `curl -H "Accept-Encoding: gzip" -I <endpoint>` and check response headers.
7. **SQLite WAL mode** — with multiple gthread threads sharing one DB connection, WAL mode prevents write-locks from blocking reads. Measure read/write contention before and after enabling `PRAGMA journal_mode=WAL`.
