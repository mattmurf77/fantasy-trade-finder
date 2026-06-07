# 03 — Multi-Tier Caching Strategies

> **Stack scope:** React Native (Expo SDK 54, Hermes, new arch) + TanStack Query v5 + Zustand
> (AsyncStorage persistence) on client; Flask + in-memory player cache + SQLite/Postgres on
> server; Render free-tier web service (no CDN today).

---

## TL;DR

- **Set `staleTime ≥ 5 min` on the TanStack Query client** — the default of 0 causes every
  component mount to re-fetch even when nothing has changed; player/trade data changes at most
  hourly.
- **Add persisted query cache (MMKV + `PersistQueryClientProvider`)** — cold-launch paint goes
  from a loading spinner + slow network call to instant stale data displayed while background
  revalidation runs; single highest ROI client-side win.
- **Upgrade the Flask in-memory player cache to a warm-on-boot, background-refresh pattern** —
  the current cold cache on dyno restart forces the first real user request to absorb the full
  Sleeper API payload fetch; a background thread pre-loads it at startup.
- **Add `buster`-keyed selective per-query persistence** using
  `experimental_createQueryPersister` so player-DB queries persist across relaunches while
  per-user trade/ranking queries are excluded.
- **HTTP `ETag` + `Cache-Control: max-age` on `/api/players`** is a near-zero-effort tier that
  eliminates repeat full downloads when data has not changed; implement before Redis.
- **Redis (Upstash free tier) is worth adding** once FTF scales past one Render instance or
  adds a background job worker — the primary benefit is surviving dyno restarts with a warm
  cache, not raw speed.
- **CDN edge caching is gated behind a paid Render plan** — not available today, but serving
  the player DB JSON as a Render Static Site is a free workaround for the semi-static payload.

---

## Why it matters for FTF

FTF's two biggest latency offenders are both data-fetch problems:

1. **The player database payload** — described elsewhere in this audit as ~4.8 MB, fetched from
   Sleeper or a derived endpoint on the Flask server. Slow-changing (roster moves happen daily
   at most; names/positions almost never). Ideal cache candidate.
2. **The Render free-tier cold start** — free web services sleep after 15 minutes of
   inactivity. The first request after a sleep triggers a process restart **plus** the
   in-memory player cache is empty, so the backend must re-hydrate from the DB or from Sleeper
   before it can respond. Users experience 15–30 s stalls.

A well-designed cache stack attacks both problems at every layer: client persistence
(instant paint on relaunch), server warm cache (no post-restart stall), and HTTP
revalidation (skip re-download when nothing changed).

---

## Tactics

### 1. TanStack Query `staleTime` / `gcTime` tuning

- **What it is** — `staleTime` is the window during which cached data is considered fresh; no
  re-fetch is triggered on component mount or window focus. `gcTime` (formerly `cacheTime`)
  is how long an *inactive* (no subscribers) cache entry is kept in memory before GC.
  Default `staleTime = 0` means every mount triggers a background re-fetch. Default
  `gcTime = 5 min`.
- **When to use it** — Always set explicit values; the defaults optimize for correctness over
  performance. Tune per query key, not just globally.
- **Expected impact** — **High (I = 2)**. Eliminates redundant re-fetches on navigation between
  screens. On cellular, each saved player-DB request is ~0.5–2 s.
- **RN/Flask applicability** — Zero new dependencies. Set in `QueryClient` constructor's
  `defaultOptions`:
  ```ts
  new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 5 * 60 * 1000,   // 5 min — players/trades rarely change mid-session
        gcTime:    24 * 60 * 60 * 1000, // 24 h — keep memory resident if persisted cache
        retry: 3,
        refetchOnReconnect: true,
        networkMode: 'offlineFirst',
      },
    },
  })
  ```
  Override per query: trades should use `staleTime: 60_000` (1 min, user-volatile);
  player DB can use `staleTime: 30 * 60 * 1000` (30 min).
- **Cost / risk** — Users can see stale data up to `staleTime`. Mitigate with explicit
  `invalidateQueries` after mutations (trade submission, Elo ranking save).
- **Impact ladder** — **High**
- **Sources** — [TanStack Query important defaults](https://tanstack.com/query/latest/docs/framework/react/guides/important-defaults);
  [understanding staleTime vs gcTime](https://medium.com/@bloodturtle/understanding-staletime-vs-gctime-in-tanstack-query-e9928d3e41d4);
  [RN TanStack Query guide 2026](https://oneuptime.com/blog/post/2026-01-15-react-native-tanstack-query/view)

---

### 2. Query-key design and selective invalidation

- **What it is** — Query keys are the cache namespace. Hierarchical key factories
  (`['players', leagueId]`, `['trades', leagueId, userId]`) allow `invalidateQueries`
  to surgically bust one sub-tree without evicting unrelated data.
- **When to use it** — Any time a mutation changes server state. Avoid `invalidateQueries([])`
  (nukes everything).
- **Expected impact** — **Medium (I = 1)**. Prevents over-fetching after trade submission or
  tier save; stops cascading re-renders on screens that weren't affected.
- **RN/Flask applicability** — Pure client-side pattern. Recommended factory structure for FTF:
  ```ts
  export const playerKeys = {
    all:    () => ['players'] as const,
    league: (leagueId: string) => ['players', leagueId] as const,
  }
  export const tradeKeys = {
    all:    () => ['trades'] as const,
    league: (leagueId: string) => ['trades', leagueId] as const,
    user:   (leagueId: string, userId: string) => ['trades', leagueId, userId] as const,
  }
  export const rankingKeys = {
    user: (leagueId: string, userId: string) => ['rankings', leagueId, userId] as const,
  }
  ```
  After a trade mutation: `queryClient.invalidateQueries({ queryKey: tradeKeys.league(lid) })`.
  After tier save: `queryClient.invalidateQueries({ queryKey: rankingKeys.user(lid, uid) })`.
- **Cost / risk** — Low. Requires discipline: every mutation must call the right invalidation.
  Typos in ad-hoc string keys are silent bugs — factory functions prevent this.
- **Impact ladder** — **Medium**
- **Sources** — [TanStack Query invalidation docs](https://tanstack.com/query/v5/docs/framework/react/guides/query-invalidation);
  [Managing query keys for cache invalidation](https://www.wisp.blog/blog/managing-query-keys-for-cache-invalidation-in-react-query);
  [best pattern for Tanstack Query in big apps](https://dev.to/ignasave/we-kept-breaking-cache-invalidation-in-tanstack-query-so-we-stopped-managing-it-manually-47k2)

---

### 3. Persisted / offline client cache (AsyncStorage or MMKV)

- **What it is** — `PersistQueryClientProvider` (from `@tanstack/react-query-persist-client`)
  serializes the dehydrated query cache to a persistent storage backend on write, and
  rehydrates it before any queries begin fetching on the next app launch. The app renders
  previously-cached data *immediately* without a network round-trip; stale data is shown while
  the background revalidation completes.
- **When to use it** — Always for a mobile app with slow data sources. Especially critical for
  FTF where the player DB fetch is expensive. Do NOT persist per-user sensitive data
  (tokens, ranking deliberations) without encryption.
- **Expected impact** — **Massive (I = 3)**. Cold launch goes from blank/spinner + 2–30 s
  fetch to instant render of stale data, with fresh data arriving in background. Eliminates
  the perceived cold-start stall entirely for repeat users.
- **RN/Flask applicability** — Requires `@tanstack/query-async-storage-persister` +
  `@tanstack/react-query-persist-client`. Storage options:
  - **AsyncStorage** — available today (already used by Zustand), no new dep, ~10–30x slower
    than MMKV for reads/writes but adequate for cache sizes under 1 MB.
  - **MMKV** (`react-native-mmkv`) — ~30x faster than AsyncStorage via JSI + memory-mapping,
    synchronous reads. Preferred for FTF given the ~4.8 MB player blob.
    MMKV requires a native build (no Expo Go support without dev client).

  Critical configuration: set `gcTime` on the `QueryClient` to match or exceed the persister's
  `maxAge` (default 24 h). If `gcTime < maxAge`, rehydrated entries are immediately GC'd.

  Use `experimental_createQueryPersister` (per-query granularity) rather than the whole-client
  persister to persist only `playerKeys.all()` and skip volatile `tradeKeys` and `rankingKeys`.
  The `buster` option lets you invalidate the whole disk cache on a server-side data migration.

- **Cost / risk** — Medium complexity. Pitfalls: serialization of non-JSON types; stale blobs
  surviving across schema migrations (mitigate with `buster`); MMKV native build requirement
  adds Expo dev-client step. Max persisted payload is limited by device storage and AsyncStorage
  2 MB key limit — use MMKV to escape this limit.
- **Impact ladder** — **Massive**
- **Sources** — [persistQueryClient v5 docs](https://tanstack.com/query/v5/docs/framework/react/plugins/persistQueryClient);
  [createAsyncStoragePersister docs](https://tanstack.com/query/v4/docs/framework/react/plugins/createAsyncStoragePersister);
  [experimental_createQueryPersister docs](https://tanstack.com/query/latest/docs/framework/react/plugins/createPersister);
  [MMKV + React Query wrapper](https://github.com/mrousavy/react-native-mmkv/blob/main/docs/WRAPPER_REACT_QUERY.md);
  [MMKV vs AsyncStorage benchmarks](https://github.com/mrousavy/StorageBenchmark);
  [MMKV 30x faster claim](https://github.com/mrousavy/react-native-mmkv)

---

### 4. Server-side in-memory cache (process cache, TTL, warm-on-boot)

- **What it is** — A dict/`cachetools.TTLCache` in the Flask process holding expensive-to-fetch
  data (the Sleeper player DB, league rosters) so repeated requests within the TTL window are
  served from RAM without a DB or HTTP round-trip.
- **When to use it** — Always on single-instance deployments. The current FTF implementation
  already does this for players, but is **fragile**: the cache is empty after dyno restart or
  the first request after sleep.
- **Expected impact** — **Massive (I = 3)**. A warm cache turns the ~4.8 MB Sleeper payload
  from a 15–30 s cold-fetch into a <50 ms memory read. The warm-on-boot pattern eliminates the
  post-restart stall entirely.
- **RN/Flask applicability** — Flask + `cachetools` or `Flask-Caching` with `SimpleCache`
  backend. Warm-on-boot pattern:
  ```python
  # run.py or application factory
  import threading
  def _warm_cache():
      with app.app_context():
          player_service.load_players()   # populates module-level TTLCache
  threading.Thread(target=_warm_cache, daemon=True).start()
  ```
  Set TTL to 6–12 h for the player DB (Sleeper publishes updates once daily). Use
  `cachetools.TTLCache` with `maxsize` to bound memory use.

  **Fragility on Render free tier:** Render free web services restart after 15 min of
  inactivity. The warm-on-boot thread fires at restart, but the user who *triggered* the
  restart (the waking request) still waits for the initial DB load. Combine with the
  HTTP-layer stale-while-revalidate approach (Tactic 6) so the client can serve persisted
  data to the user while the server warms.

- **Cost / risk** — Not thread-safe if using a plain dict. Use `threading.Lock` or
  `cachetools.LRUCache`/`TTLCache` which have internal locks. Memory-resident cache is lost
  on process restart — acceptable for FTF; not acceptable if cache contains user-derived
  computed state that is expensive to recompute.
- **Impact ladder** — **Massive**
- **Sources** — [Flask-Caching docs](https://flask-caching.readthedocs.io/en/latest/);
  [Flask background thread pattern](https://vmois.dev/python-flask-background-thread/);
  [flask-refresh-cache stale-while-revalidate](https://github.com/thatjimmi/flask-refresh-cache);
  [Heroku Flask Memcache guide](https://devcenter.heroku.com/articles/flask-memcache)

---

### 5. Shared cache across instances (Redis / managed KV)

- **What it is** — An external key-value store (Redis, MMKV-on-server, or a managed service
  like Upstash) accessible to all server processes. Cache entries survive individual process
  restarts. Required for horizontal scale (multiple Render instances or background workers).
- **When to use it** — When any of these are true: (a) more than one Render instance,
  (b) a background job worker needs to share cached state with the web server,
  (c) the cost of a cold cache on dyno restart is unacceptable and the warm-on-boot thread
  isn't fast enough.
- **Expected impact** — **High (I = 2)** for dyno-restart resilience; **Medium (I = 1)** for
  single-instance FTF today. The Render free tier runs one instance — Redis buys
  restart-resilience, not scale.
- **RN/Flask applicability** — **Upstash Redis free tier** (10 K commands/day, 256 MB) is the
  lowest-friction path for FTF: HTTP-based Redis API, no persistent connection required,
  works with Render free tier. Use `Flask-Caching` with `RedisCache` backend or `redis-py`.
  Swap `SimpleCache` → `RedisCache` in `config.py`; zero application logic changes needed
  if using `Flask-Caching` decorators.

  **Prerequisite:** Upstash account + `REDIS_URL` env var in Render dashboard.

- **Cost / risk** — Adds external service dependency; cache misses from Redis unavailability
  must fall back to DB reads gracefully. Upstash free tier is read-heavy friendly (10 K
  commands/day ≈ ~7 read commands/minute — adequate for player DB reads). Exceeding free tier
  is $0.20 / 100 K commands. **Not worth Redis complexity for FTF today if the warm-on-boot
  pattern (Tactic 4) + HTTP caching (Tactic 6) are in place.**
- **Impact ladder** — **High** (when dyno restarts are frequent); **Medium** (steady state)
- **Sources** — [Upstash Redis pricing](https://upstash.com/pricing/redis);
  [Flask + Redis caching guide](https://dwickyferi.medium.com/supercharging-your-flask-api-performance-a-complete-guide-to-redis-caching-implementation-6f1fd1892adf);
  [large-scale API caching with Flask and Redis 2025](https://blog.poespas.me/posts/2025/03/02/handling-large-scale-api-caching-with-flask-and-redis/)

---

### 6. CDN / edge caching for semi-static data (player DB)

- **What it is** — A CDN node geographically near the client caches the response to
  `/api/players` so that subsequent requests from that region are served from the edge rather
  than the origin Flask server on Render.
- **When to use it** — For data that is large, slow to generate, and changes infrequently.
  The FTF player DB payload is the ideal candidate.
- **Expected impact** — **High (I = 2)** when the CDN hit rate is high (warm); **Massive (I = 3)**
  if it can eliminate dyno-wake round-trips for the largest payload.
- **RN/Flask applicability** — **Render free tier does NOT include edge caching for web
  services.** It is available only for paid Render tiers. Two free alternatives:

  1. **Render Static Site workaround** — Export the player DB as a JSON file during a nightly
     build step, upload to a Render Static Site (free, CDN-backed). The RN client fetches from
     the static CDN URL. TTL is implicitly one build cycle (24 h). Requires a build pipeline
     to regenerate the JSON; adds complexity.
  2. **Cloudflare CDN proxy** — Point FTF's custom domain through Cloudflare's free tier.
     Cloudflare caches `Cache-Control: public, max-age=...` responses at its edge for free,
     including on the free plan for cacheable content. Adds DNS management step.

- **Cost / risk** — Static Site workaround: coupling between data pipeline and static hosting;
  stale player data if build fails. Cloudflare: DNS change, need to ensure HTTPS pass-through.
  **Both are medium-complexity prerequisites; defer until Tactic 6 (HTTP caching) is done first.**
- **Impact ladder** — **High** (with paid Render or Cloudflare); **Medium** (static-site workaround)
- **Sources** — [Render edge caching docs](https://render.com/docs/web-service-caching);
  [Render static sites docs](https://render.com/docs/static-sites);
  [CDN for static assets feature request](https://feedback.render.com/features/p/cdn-for-static-assets-in-backend-apps)

---

### 7. HTTP-layer caching (ETag / Cache-Control / stale-while-revalidate)

- **What it is** — Standard HTTP response headers that instruct the client (and any intermediate
  proxies or CDNs) how long to treat a response as fresh, and how to check for staleness without
  a full re-download.
  - `Cache-Control: public, max-age=3600` — client caches for 1 h, no request needed.
  - `Cache-Control: public, max-age=300, stale-while-revalidate=60` — serve stale for 60 s
    while fetching fresh in background (RFC 5861, supported by all major browsers).
  - `ETag: "v42"` + `If-None-Match: "v42"` — server returns `304 Not Modified` (no body)
    if data has not changed; saves bandwidth for large payloads.
- **When to use it** — On every cacheable GET endpoint. For FTF: `/api/players`, `/api/leagues`,
  and any roster/schedule data. Do NOT apply to user-specific or session-specific endpoints
  without `Cache-Control: private`.
- **Expected impact** — **High (I = 2)** for the player DB (saves re-downloading 4.8 MB on
  every warm relaunch); **Medium (I = 1)** for smaller endpoints. ETag + 304 reduces cellular
  data usage substantially.
- **RN/Flask applicability** — Flask + Werkzeug make this straightforward:
  ```python
  from flask import make_response
  import hashlib, json

  @app.route('/api/players')
  def get_players():
      data = player_service.get_cached_players()
      body = json.dumps(data)
      etag = hashlib.md5(body.encode()).hexdigest()
      if request.headers.get('If-None-Match') == etag:
          return '', 304
      resp = make_response(body)
      resp.headers['ETag'] = etag
      resp.headers['Cache-Control'] = 'public, max-age=3600, stale-while-revalidate=300'
      resp.headers['Content-Type'] = 'application/json'
      return resp
  ```
  TanStack Query does not automatically send `If-None-Match` headers — the native `fetch` API
  does when the browser cache is involved. In React Native, this must be wired manually via
  a custom `queryFn` that passes the stored ETag or via a middleware like Axios with interceptors.
  For the first iteration, `Cache-Control: max-age` alone (no ETag) is sufficient and requires
  zero client changes.
- **Cost / risk** — Very low for `Cache-Control` alone (server-only, 1–2 lines per endpoint).
  ETag requires storing/comparing hashes; risk of stale ETags if data changes without hash
  change (mitigate by hashing actual payload content, not a version number).
- **Impact ladder** — **High**
- **Sources** — [Caching best practices in REST API design](https://www.speakeasy.com/api-design/caching);
  [Optimizing REST APIs with ETags](https://zuplo.com/learning-center/optimizing-rest-apis-with-conditional-requests-and-etags);
  [stale-while-revalidate on web.dev](https://web.dev/articles/stale-while-revalidate);
  [RFC 5861](https://httpwg.org/specs/rfc5861.html);
  [Cache-Control MDN](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control)

---

### 8. Cache invalidation patterns

- **What it is** — The strategy that determines when cached data is replaced. Four main patterns:

  | Pattern | Mechanism | FTF applicability |
  |---|---|---|
  | **TTL expiry** | Entry expires after fixed duration | Primary strategy for player DB (6–12 h), trade results (1–5 min) |
  | **Write-through** | Cache updated atomically with DB write | Rankings/tier saves — update cache and DB together |
  | **Cache-aside (lazy)** | Delete on write, re-populate on next read | Trade mutations — delete `tradeKeys` on submission |
  | **Event-based** | External event triggers invalidation | Future: Sleeper webhook → invalidate player cache |

- **When to use it** — TTL for everything by default. Layer event-based invalidation only for
  data where staleness would cause user-visible errors (e.g., a trade proposed for a player
  who was just dropped).
- **Expected impact** — Getting invalidation wrong has negative impact: either stale data (bad
  UX) or over-invalidation (kills cache hit rate). Correct invalidation is a **prerequisite**
  for any caching strategy.
- **RN/Flask applicability** — Client: TanStack Query `invalidateQueries` on mutation
  success/error callbacks. Server: set TTLs in `cachetools.TTLCache`; call `cache.pop(key)`
  on write operations. No event bus needed for FTF's current scale.
- **Cost / risk** — TTL jitter is critical to prevent synchronized expiry across many users
  hitting the server simultaneously after a cache warm. Add 5–10% random jitter:
  `ttl = base_ttl * (1 + random.uniform(-0.1, 0.1))`.
- **Impact ladder** — **Massive** (getting it wrong) / **Medium** (incremental improvement
  over already-correct TTLs)
- **Sources** — [Cache invalidation strategies](https://codelit.io/blog/caching-invalidation-strategies);
  [TTL vs stale-while-revalidate](https://systemdesignschool.io/fundamentals/cache-invalidation);
  [cache invalidation guide](https://scopeforged.com/blog/cache-invalidation-strategies)

---

### 9. Cache-key design and cache-stampede prevention

- **What it is** — A **cache stampede** (thundering herd) occurs when a popular cache entry
  expires and many concurrent requests simultaneously find a cache miss and all hammer the
  backend to recompute/re-fetch. On Render's free tier this compounds with cold-start latency:
  after a dyno wake, *all* requests arrive before the warm-on-boot thread finishes, creating a
  mini-stampede on the Sleeper API.
- **When to use it** — Any hot, expensive-to-compute cache entry with a TTL. FTF's player DB
  entry is the primary risk.
- **Prevention strategies:**
  1. **Request coalescing (single-flight)** — In Flask, use a `threading.Event` or `asyncio.Lock`
     so only one thread recomputes the player cache while others wait and then share the result.
     ```python
     _player_cache_lock = threading.Lock()
     def get_players_cached():
         if PLAYER_CACHE.get('data'):
             return PLAYER_CACHE['data']
         with _player_cache_lock:   # second check inside lock
             if PLAYER_CACHE.get('data'):
                 return PLAYER_CACHE['data']
             data = fetch_from_sleeper()
             PLAYER_CACHE['data'] = data
             return data
     ```
  2. **TTL jitter** — Randomize TTL by ±10% to prevent synchronized expiry across multiple
     client sessions or server restarts.
  3. **Stale-while-revalidate on the server** — Serve the stale entry immediately while
     a background thread refreshes it. The `flask-refresh-cache` library implements this
     pattern for Flask.
  4. **Cache warm-on-boot** — Eliminates the cold cache entirely by pre-populating before
     the first user request arrives (see Tactic 4).
- **Expected impact** — **High (I = 2)**. Without coalescing, a dyno wake under moderate
  traffic can generate 5–20 simultaneous Sleeper API calls, risking rate-limiting.
- **RN/Flask applicability** — The double-checked lock pattern above is idiomatic Python.
  `cachetools.TTLCache` is not thread-safe by default — wrap with `cachetools.LRUCache` +
  `threading.Lock` or use `cachetools.cached` with a `lock` parameter.
- **Cost / risk** — Low effort (single lock), high value. Risk: deadlock if the fetch itself
  throws inside the lock — always use try/finally or a context manager.
- **Impact ladder** — **High**
- **Sources** — [Cache stampede prevention](https://oneuptime.com/blog/post/2026-01-21-redis-cache-stampede/view);
  [single-flight pattern 2026](https://1xapi.com/blog/nodejs-cache-stampede-single-flight-pattern-2026);
  [thundering herd solutions](https://howtech.substack.com/p/thundering-herd-problem-cache-stampede)

---

### 10. What data is cacheable in FTF

| Data | Change frequency | Volatility | Recommended cache | TTL |
|---|---|---|---|---|
| **Player DB** (names, positions, teams) | Daily at most (Sleeper publishes once/day) | Very low | Server in-memory + HTTP Cache-Control + client persist | Server: 12 h; HTTP: 1 h `max-age`, 5 min `stale-while-revalidate`; Client: `staleTime` 30 min, persisted 24 h |
| **League rosters** | Waiver wire / trades — multiple times per day | Low-medium | Server in-memory with shorter TTL; client `staleTime` | Server: 15 min; Client: 5 min |
| **Trade results** (`/api/trades`) | Per-user, computed on demand | High (per user) | Client only (`staleTime` 60 s, no persistence); server: no cache | Client: 60 s `staleTime`, not persisted |
| **Rankings / Elo scores** | Per user, updated after each matchup | High (per user) | Client only (`staleTime` 60 s, no persistence) | Client: 60 s, not persisted |
| **Session / auth tokens** | Per session | N/A | Secure storage (expo-secure-store), not query cache | Session TTL |
| **Feature flags** | Near-static (config deploy) | Very low | Server in-memory; client `staleTime` | Server: indefinite until redeploy; Client: 10 min |

---

## Anti-patterns to flag in the audit

- `staleTime` not set (or set to `0`) at the `QueryClient` default level — every component
  mount triggers a background re-fetch; grep for `new QueryClient({` missing `staleTime` in
  `defaultOptions`.
- `gcTime` left at the 5-minute default while persistence is enabled — rehydrated entries are
  immediately garbage-collected; grep for `PersistQueryClientProvider` without matching `gcTime`.
- Query keys as ad-hoc string literals (`useQuery({ queryKey: ['players'] })` scattered across
  files) rather than factory functions — silent invalidation mismatches; grep for `queryKey:`
  outside a dedicated keys file.
- `invalidateQueries([])` or `invalidateQueries()` with no key filter — busts the entire cache
  on any mutation; grep for `invalidateQueries()` with empty/no arguments.
- `refetchOnWindowFocus: true` (the default) on a React Native app — window focus events
  behave differently on mobile (app foreground) and may cause spurious re-fetches; should be
  explicitly set to `false` or `'always'` with intent.
- Plain Python dict used as Flask cache without a lock — race condition under concurrent
  requests; grep for module-level `{}` used as a cache dict in `server.py` or services.
- `cachetools.TTLCache` used without a `threading.Lock` — TTLCache is not thread-safe;
  grep for `TTLCache` not wrapped with `lock=`.
- `Cache-Control` absent from player/league API responses — every RN fetch downloads full
  payload; grep for Flask route handlers on `/api/players` missing `resp.headers['Cache-Control']`.
- No `buster` / version string on the persisted query cache — a server-side data migration
  (e.g., player ID format change) won't invalidate stale client caches; grep for
  `PersistQueryClientProvider` missing a `buster` prop.
- Persisting trade or ranking query keys to disk — per-user volatile data stored in
  plaintext on device; grep for `tradeKeys` or `rankingKeys` inside `dehydrateOptions.shouldDehydrateQuery`.
- Server-side cache warming not present in `run.py` or the application factory — the first
  request after a dyno restart absorbs the full Sleeper fetch latency; grep for any
  pre-population call in `create_app()` or `run.py`.

---

## Recommended defaults for FTF

### Client (React Native / TanStack Query)

```ts
// QueryClient — global defaults
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime:            5 * 60 * 1000,         // 5 min global default
      gcTime:               24 * 60 * 60 * 1000,   // 24 h — must match persister maxAge
      retry:                3,
      refetchOnWindowFocus: false,                  // RN: use AppState listener instead
      refetchOnReconnect:   true,
      networkMode:          'offlineFirst',
    },
  },
})

// Per-query overrides
useQuery({ queryKey: playerKeys.league(leagueId), staleTime: 30 * 60 * 1000 })  // 30 min
useQuery({ queryKey: tradeKeys.user(lid, uid),    staleTime: 60 * 1000 })        // 1 min
useQuery({ queryKey: rankingKeys.user(lid, uid),  staleTime: 60 * 1000 })        // 1 min
```

**Persistence layer:**
- Use `experimental_createQueryPersister` (per-query) rather than `persistQueryClient`
  (whole-cache) so only `playerKeys` is persisted.
- Storage: **MMKV** via the `react-native-mmkv` wrapper (requires dev client / EAS build).
  Fall back to AsyncStorage if Expo Go compatibility is required during development.
- `maxAge`: 24 h (matches `gcTime`).
- `buster`: tie to the Sleeper player DB schema version or a deploy-time env var.
- Do not persist `tradeKeys`, `rankingKeys`, or any auth-adjacent queries.

### Server (Flask)

```python
# Cache configuration
PLAYER_CACHE_TTL  = 12 * 3600          # 12 h — aligns with Sleeper's daily publish cadence
ROSTER_CACHE_TTL  = 15 * 60            # 15 min
TTL_JITTER_FACTOR = 0.1                # ±10% jitter on all TTLs

# Warm on boot (in application factory or run.py)
threading.Thread(target=_warm_player_cache, daemon=True).start()

# HTTP headers on /api/players
Cache-Control: public, max-age=3600, stale-while-revalidate=300
ETag: <MD5 of response body>   # implement after max-age is confirmed working
```

**Redis / external cache:** Defer until FTF adds a second Render instance or a background
worker. When added, use Upstash free tier; swap `SimpleCache` → `RedisCache` in
Flask-Caching config with no application logic changes.

**CDN:** Not available on Render free tier for web services. Evaluate after paid tier upgrade
or implement Cloudflare free-tier proxy for the custom domain.

---

## Open questions / needs measurement

1. **What is the actual cold-cache fetch time?** The "15–30 s stall" is an estimate; a timed
   `curl` against a sleeping Render dyno will give the exact number to benchmark against.
2. **What is the AsyncStorage read time for the serialized player blob?** At ~4.8 MB, AsyncStorage
   may introduce a 200–500 ms read delay that MMKV would reduce to <20 ms — needs measurement
   on target device to confirm whether MMKV is required or AsyncStorage suffices.
3. **Are trade and ranking results actually per-user, or shared across users of the same league?**
   If trade recommendations are league-wide (same for all members), they become cacheable at a
   higher hit rate and warrant server-side caching.
4. **How often does the Sleeper player DB actually change?** If changes cluster to NFL
   transaction windows (waiver days, trade deadlines), TTL-based invalidation can be tightened
   to those windows for higher freshness without extra invalidation infrastructure.
5. **Is `refetchOnWindowFocus` currently causing spurious re-fetches on the Trades or Tiers
   screen?** Check with React Query DevTools or network inspector on a device — app foreground
   events may be triggering unnecessary player DB re-fetches every time the user switches apps.
