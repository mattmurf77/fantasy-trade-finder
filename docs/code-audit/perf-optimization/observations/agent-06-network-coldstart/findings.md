# Network + Cold-Start + Critical-Path-to-First-Paint — Findings

**Agent:** agent-06-network-coldstart

## Scope & method

This audit covers the **on-the-wire + boot critical path** for player/trade
data: payload sizes / TTFB / total time for the key GET endpoints (with and
without compression), Render free-tier cold-start behavior, the mobile boot
sequence up to first player/trade paint, and connection reuse / HTTP version.

**Method.** Read-only `curl` against the live backend
(`https://fantasy-trade-finder.onrender.com`) — no POST, no mutation, no code
edits. Each endpoint hit 2–5× to smooth jitter; response headers captured with
`-D -`; compression negotiated via `Accept-Encoding`. Authenticated endpoints
could not be measured with a real token (no POST allowed) so their payloads are
characterized from code. Static analysis of `mobile/App.tsx`,
`mobile/src/navigation/RootNav.tsx`, `mobile/src/api/auth.ts`,
`mobile/src/api/client.ts`, `mobile/src/api/sleeper.ts`, and
`backend/server.py`. **Raw numbers in `measurements.md` (same folder).**

**Dyno state caveat.** The free-tier dyno was already warm during the run
(first probe TTFB 0.26 s), so a live 30–60 s cold wake was not captured. Cold
findings are reasoned from infra config + code with Confidence set accordingly.

---

## OBS-NET-01 — Cold-start serves first player fetch from upstream Sleeper, not a baked cache

- **Area:** network / cold-start / backend
- **Severity:** P1
- **Status:** observed
- **Evidence type:** static-analysis (+ measured warm baseline)

### What happens today
The Sleeper player cache has three tiers: in-memory `_sleeper_cache`
(`backend/server.py:333`), an on-disk file
`data/.sleeper_players_cache.json` (`server.py:332`), and a live fetch from
`api.sleeper.app`. On a cold container both memory and disk are empty:
`data/` is gitignored (`.gitignore:8`) and the 5 MB cache file is **not
committed** (`git ls-files` returns no match), and `render.yaml` declares **no
`disk:` mount** so the filesystem is ephemeral on the free tier. The first
`/api/sleeper/players/warm` (`server.py:4414`) therefore enters
`_ensure_sleeper_cache_populated()` (`server.py:4337`), which does a
**synchronous `urlopen(...)` of ~5 MB from `api.sleeper.app` with a 45 s
timeout** (`server.py:4350-4355`) followed by a `sync_players` DB write
(`server.py:4378-4387`).

### Why it's slow / costly
This is a **cold-start on the critical path**. The mobile app fires
`warmPlayerCache()` from boot (`App.tsx:51`) AND again in `initLeagueSession`
(`auth.ts:114-123`) — and `session/init` hard-fails with `"Player database not
cached"` (`server.py:4475-4476`) if the cache isn't populated. So the first
real user after a dyno sleep pays: Render dyno wake (30–60 s documented) **plus**
a ~5 MB upstream fetch + DB sync, all serialized on `--workers 1`
(`render.yaml:13`). The single worker is blocked for the duration.

### Evidence
- `git ls-files | grep sleeper_players_cache` → no match (not committed).
- `.gitignore:8` → `data/` ignored; local file is 5 068 172 B.
- `render.yaml` → no `disk:` block; `plan: free`; `--workers 1`.
- `server.py:4350-4355` → `urlopen(..., timeout=45)` for the ~5 MB payload.
- Warm baseline (cache present): `/api/sleeper/players/warm` total ~0.20–0.59 s
  (measurements §2/§4) — so the entire cold tax is the population path, not the
  warm response.

### Recommendation(s)
- **Option A (preferred):** bake a recent `data/.sleeper_players_cache.json`
  into the deploy image — commit a snapshot (or have `build.sh` fetch it once at
  build time, `build.sh` currently only `pip install` + `mkdir -p data`). Then a
  cold container reads the cache from disk (`_load_sleeper_cache`, `server.py:336`)
  in milliseconds instead of a 5 MB upstream round-trip. Removes the per-cold
  upstream fetch from the user's critical path. Low effort, no schema change.
  Trade-off: the baked cache can go stale between deploys — pair with the
  existing nightly refresh path / cron so freshness is maintained.
- **Option B:** keep the runtime fetch but make it **async / non-blocking** so
  `session/init` doesn't hard-fail on a cold cache — return a "warming" state and
  let the client poll. Larger change, doesn't remove the latency, only hides it.
- **Option C:** add a small Render **persistent disk** so the runtime-fetched
  cache survives dyno restarts within a deploy. Costs money (free tier has no
  disk) and still pays the fetch once per deploy.

### RICE-P
| Reach | Impact | Confidence | Effort | **Score** |
|------:|-------:|-----------:|-------:|----------:|
| 4 | 3 | 80% | 1 | **9.6** |

- **Estimated latency delta:** on a cold dyno, removes a ~5 MB upstream Sleeper
  fetch (+45 s worst-case timeout, typ. 2–5 s) + DB sync from the first
  league-pick / boot. Cold-start dyno wake (30–60 s) itself is unchanged by this
  fix, but the *additional* cache-population stall is removed.
- **Confidence note:** 80% — code path and infra are unambiguous (static), but
  the exact cold fetch duration wasn't measured (dyno was warm). A live cold-hit
  timing would push this to 100%.

### Related components
`backend/server.py` (`_ensure_sleeper_cache_populated`, `sleeper_players_warm`,
`session_init`), `build.sh`, `render.yaml`, `mobile/src/api/auth.ts`,
`mobile/App.tsx`.

### Prerequisites / dependencies
None for Option A (commit a snapshot or extend `build.sh`). Option C requires an
infra/billing change.

### Regression risk
Low. A baked cache must contain the same QB/RB/WR/TE-filtered shape the runtime
path writes (`server.py:4360-4365`); a stale snapshot only affects newly-added
rookies until the next refresh — no ELO/tier-band invariant is touched.

---

## OBS-NET-02 — No `Accept-Encoding` set by the mobile client; relies on platform default (br never used)

- **Area:** network / API client
- **Severity:** P3
- **Status:** observed
- **Evidence type:** measured

### What happens today
The mobile fetch wrapper (`mobile/src/api/client.ts:136-147`) sets `Accept`,
`Content-Type`, and the `X-*` client headers but **never sets
`Accept-Encoding`** (grep of `mobile/src/` for `Accept-Encoding` → no match).
On iOS, RN's `fetch` (NSURLSession) and on Android (OkHttp) **auto-inject
`Accept-Encoding: gzip` and transparently decompress** — so gzip *is* obtained
for free, but **brotli is never requested** (only the native default `gzip` is
advertised).

### Why it's slow / costly
Measured: Cloudflare honors `gzip` and `br` but **not** `deflate`
(measurements §3). For the only large body, `/api/sleeper/players`, gzip gives
4.84 MB → ~662 KB and br → ~676 KB — both ~86% off, near-identical here, so the
missing brotli costs essentially nothing for *this* payload. **The mobile client
does not even fetch that body** — it uses the 25-byte `/warm` variant
(`sleeper.ts:47`, only call site). All mobile JSON bodies on the first-paint
path are already tiny (≤ ~1.5 KB, measurements §2/§4), so compression of any
flavor saves only a few hundred bytes. This is essentially a non-issue for
mobile today; flagged for completeness and because the **web** client (which
*does* download the 4.84 MB body) benefits materially from the edge gzip it
already gets by default.

### Evidence
- `grep -rn "Accept-Encoding" mobile/src/` → empty.
- `client.ts:136-147` — header block, no encoding header.
- measurements §3 — gzip 662 603 B vs identity 4 837 423 B; deflate not honored.
- `sleeper.ts:43-49` — mobile only ever calls `/api/sleeper/players/warm`.

### Recommendation(s)
- **Option A (preferred):** no action for mobile — the platform default already
  yields gzip and the large payload isn't on the mobile path. Document the
  reliance on platform-default gzip so a future custom networking layer (e.g.
  swapping to a lib that strips the default header) doesn't silently regress to
  identity. Zero effort.
- **Option B:** explicitly set `Accept-Encoding: gzip, br` in `client.ts` to
  request brotli too — only worthwhile if/when the client starts pulling a large
  body. Marginal benefit now (~14 KB on the web payload, none on mobile).

### RICE-P
| Reach | Impact | Confidence | Effort | **Score** |
|------:|-------:|-----------:|-------:|----------:|
| 10 | 0.25 | 100% | 0.5 | **5.0** |

- **Estimated latency delta:** ~0 ms on mobile today (large body not fetched;
  gzip already auto-applied). Up to ~−10–15 KB / a few ms only if a future large
  body is pulled and br is explicitly requested.
- **Confidence note:** 100% — directly measured. Impact 0.25 because the only
  payload that would benefit isn't on the mobile critical path.

### Related components
`mobile/src/api/client.ts`, `mobile/src/api/sleeper.ts`, web `app.js`
(consumes the full payload — out of this agent's lane, see CROSS-REF).

### Prerequisites / dependencies
None.

### Regression risk
None for Option A. Option B: confirm the platform still decompresses correctly
when `br` is advertised (NSURLSession handles gzip natively but not always br —
test on-device before relying on it).

---

## OBS-NET-03 — Boot fires 4 cold network calls in parallel but first paint still waits on `setBooted`

- **Area:** network / critical-path / RN
- **Severity:** P2
- **Status:** observed
- **Evidence type:** static-analysis (+ measured warm timings)

### What happens today
`App.tsx:47-54` runs `Promise.all([bootstrap(), loadFlags(), fetchTierConfig(),
warmPlayerCache()])` and only flips `setBooted(true)` in `.finally()`. While
`!booted`, `RootNav` renders a bare `<ActivityIndicator>` splash
(`RootNav.tsx:96-102`) — **nothing is shown until all four settle**.
`bootstrap()` is local-only (AsyncStorage + SecureStore reads, `useSession.ts:96-113`)
and `loadFlags()` hydrates from cache first (`useFeatureFlags.ts:27-37`), so those
are fast. But `fetchTierConfig()` and `warmPlayerCache()` are **network** calls,
and on a cold dyno `warmPlayerCache()` is the 30–60 s + 5 MB-fetch path of
OBS-NET-01.

### Why it's slow / costly
`Promise.all` settles on the **slowest** leg. The two slow legs
(`fetchTierConfig`, `warmPlayerCache`) are already best-effort —
`fetchTierConfig` swallows errors and falls back to seeded bands (`App.tsx:35-42`),
`warmPlayerCache` is fire-and-forget (`App.tsx:51` `.catch(() => {})`). Yet the
splash is gated on **all four** resolving. On a cold dyno, the splash can hang
for the full wake + fetch even though the local session restore (the only thing
needed to route to SignIn/LeaguePicker/Main) finished in milliseconds. The user
stares at a spinner waiting on a warm-cache side-effect that the *first screen*
doesn't need.

### Evidence
- `App.tsx:47-54` — single `Promise.all([...]).finally(() => setBooted(true))`.
- `RootNav.tsx:96-102` — `if (!booted) return <ActivityIndicator/>`; routing
  decision at `RootNav.tsx:108-112` needs only `user`/`league`/`hasToken` from
  the local-only `bootstrap()`.
- Warm timings: `/api/tier-config` ~0.22 s, `/api/sleeper/players/warm`
  ~0.20–0.59 s (measurements §2/§4) — negligible warm, but cold = OBS-NET-01.
- `bootstrap()` is local I/O only (`useSession.ts:96-113`); `loadFlags()`
  hydrates from cache synchronously-ish (`useFeatureFlags.ts:27-37`).

### Recommendation(s)
- **Option A (preferred):** gate `setBooted` on **only** the local-state legs
  (`bootstrap()` + the cache-hydrate inside `loadFlags()`), and let
  `fetchTierConfig()` + `warmPlayerCache()` run as detached fire-and-forget
  (they already tolerate failure and have fallbacks). The app paints the
  SignIn/LeaguePicker/Main shell immediately; the warm ping continues in the
  background warming the dyno for the first real action. Client-only change in
  `App.tsx`. Trade-off: tier bands briefly use seeded fallback until
  `fetchTierConfig` lands — already the documented failure behavior, so no new
  risk.
- **Option B:** keep `Promise.all` but add a timeout race (e.g. `setBooted`
  after `max(local, 1500 ms)`), so a slow network leg can't hold the splash past
  a budget. Simpler but arbitrary; Option A is cleaner.

### RICE-P
| Reach | Impact | Confidence | Effort | **Score** |
|------:|-------:|-----------:|-------:|----------:|
| 10 | 2 | 80% | 1 | **16.0** |

- **Estimated latency delta:** warm ≈ −0.2–0.6 s to first shell paint; **cold:
  removes the entire dyno-wake + 5 MB-fetch stall (tens of seconds) from the
  splash** — the user reaches SignIn/Main immediately while the warm ping runs
  behind it. Pairs with OBS-NET-01 (which shortens the warm ping itself).
- **Confidence note:** 80% — the gating is unambiguous in code; the warm-leg
  cost is small, so the headline win is the cold case, which is reasoned not
  measured (dyno was warm).

### Related components
`mobile/App.tsx`, `mobile/src/navigation/RootNav.tsx`,
`mobile/src/state/useSession.ts`, `mobile/src/state/useFeatureFlags.ts`,
`mobile/src/api/rankings.ts` (`getTierConfig`), `mobile/src/api/sleeper.ts`
(`warmPlayerCache`).

### Prerequisites / dependencies
None. Synergistic with OBS-NET-01 (baked cache makes the background warm ping
cheap too).

### Regression risk
Low. Must confirm tier-band consumers (`utils/tierBands`) behave with seeded
fallback for the brief window before `fetchTierConfig` resolves — this is
already the documented network-failure path (`App.tsx:35-42`). No ELO / K-factor
/ enum invariant is touched.

---

## OBS-NET-04 — `initLeagueSession` runs roster + users + warm in parallel, then a serial 5–10 s `session/init`

- **Area:** network / critical-path-to-first-trade
- **Severity:** P1
- **Status:** observed
- **Evidence type:** static-analysis

### What happens today
First trade/player paint after a league pick goes through
`initLeagueSession` (`auth.ts:101-162`). It correctly parallelizes the three
prerequisite GETs — `getLeagueRosters`, `getLeagueUsers`, `warmPlayerCache`
(`auth.ts:114-123`) — then **serially awaits** `sessionInit(...)`
(`auth.ts:151`), which the code comments themselves flag as "the slow leg (5–10 s
on Render's free tier when rebuilding rosters + members)" (`auth.ts:97-99`). Only
after `session/init` returns does `setLeague` fire and the app navigate to Main
(`RootNav.tsx:177` → `useSession.switchLeague`/picker flow). The user sees a
spinner the entire time.

### Why it's slow / costly
`session/init` (`server.py:4431`) rebuilds the universal ranking pool for both
scoring formats and the league member set on the **single** gunicorn worker
(`render.yaml:13`). It is a **hard serial dependency** before *any* trade or
ranking screen has data. On a cold dyno it also transitively depends on the
player cache being warm (OBS-NET-01) — and it hard-errors if not
(`server.py:4475-4476`). The three parallel prefetches help, but they finish fast
(rosters/users are small Sleeper proxies); the dominant cost is the
`session/init` POST itself, which is unavoidably on the path.

### Evidence
- `auth.ts:114-123` — `Promise.all([rosters, users, warm])` (good parallelism).
- `auth.ts:151` — `await sessionInit(...)` serial after the Promise.all.
- `auth.ts:97-99` — in-code note: "sessionInit is the slow leg (5–10s on
  Render's free tier)".
- `server.py:4470-4491` — universal pool rebuild for both formats inside the POST.
- `server.py:4475-4476` — hard 400 if player cache absent.
- Could not time directly (POST not permitted by audit rules).

### Recommendation(s)
- **Option A (preferred):** **paint an optimistic / skeleton Main shell as soon
  as the league is picked**, before `session/init` resolves, and stream the
  ranking/trade data in when the token lands (the first-paint queries at
  `RankScreen.tsx:77` / `TabNav.tsx:174` already use TanStack Query and would
  adopt the data on arrival). Moves the 5–10 s off the *visible* blocking path
  and onto a progress indicator inside a real screen. Client-side; no backend
  change. Trade-off: must handle the `session/init` failure case gracefully from
  inside Main rather than the picker.
- **Option B:** profile and slim `session/init` — e.g. build only the *active*
  scoring format's pool synchronously and defer the other format
  (`server.py:4482-4488` builds both). Backend change, needs care around the
  format-switch path; larger effort, real latency win.
- **Option C:** depends on OBS-NET-01 — a baked cache removes the cold-path
  player-fetch that can pile onto `session/init` on a cold dyno.

### RICE-P
| Reach | Impact | Confidence | Effort | **Score** |
|------:|-------:|-----------:|-------:|----------:|
| 8 | 2 | 50% | 2 | **4.0** |

- **Estimated latency delta:** Option A moves a 5–10 s blocking spinner into a
  populated, scrollable shell — perceived first-paint drops from ~5–10 s to
  near-instant; data fills ~5–10 s later. Option B could cut the real
  `session/init` time materially (build one format not two) but needs measurement.
- **Confidence note:** 50% — the 5–10 s figure is the codebase's own estimate,
  not measured here (POST disallowed). A timed `session/init` would raise this.

### Related components
`mobile/src/api/auth.ts` (`initLeagueSession`, `sessionInit`),
`mobile/src/navigation/RootNav.tsx`, `mobile/src/state/useSession.ts`
(`switchLeague`), `backend/server.py` (`session_init`, `_ensure_universal_pools`).

### Prerequisites / dependencies
Option C of OBS-NET-01 helps the cold case. Option B needs a backend profiling
spike first.

### Regression risk
Medium for Option A — an optimistic shell must not let the user act on stale/
empty trade data before `session/init` lands; gate interactive actions on
`hasToken`. Option B risks the inactive-format rankings being empty until first
switch — must lazy-build correctly to preserve per-format ELO independence
(cross-client invariant: 1QB-PPR vs SF-TEP are independent rank sets).

---

## OBS-NET-05 — Player JSON is `cf-cache-status: DYNAMIC` with no Cache-Control; origin re-serializes 4.84 MB every hit

- **Area:** network / backend / caching
- **Severity:** P2
- **Status:** observed
- **Evidence type:** measured

### What happens today
`/api/sleeper/players` returns `cf-cache-status: DYNAMIC` and carries **no
`Cache-Control`, `ETag`, or `Expires`** headers (measurements §1/§3). Cloudflare
compresses it at the edge but does **not** cache it — two sequential hits both
report `DYNAMIC`. The Flask route does a plain `jsonify(cached)`
(`server.py:4402`) with no caching directives. TTFB stays ~0.6–1.0 s across
encodings, confirming the origin **re-serializes the full ~4.84 MB JSON on every
request** (compression is edge-side only).

### Why it's slow / costly
This body is effectively static between nightly cache refreshes, yet every
web-client request (and every cold-cache mobile `/warm`, which shares
`_ensure_sleeper_cache_populated`) makes the single `--workers 1` origin
serialize the full dictionary. With edge caching + an `ETag`, Cloudflare could
serve the compressed body without ever touching the origin, and clients could
`304` on revalidation. Note: mobile is largely insulated (it uses `/warm`), so
the direct beneficiary is the **web** client and origin CPU/headroom on the free
tier — relevant cross-cutting infra, partly outside this agent's mobile lane
(CROSS-REF below).

### Evidence
- measurements §1 — `cf-cache-status: DYNAMIC`; no `Cache-Control`/`ETag`/`Expires`.
- measurements §3 — TTFB ~0.6–1.0 s identical across encodings → full origin
  serialization each hit.
- `server.py:4392-4407` (`sleeper_players`) — `jsonify(cached)`, no cache headers.

### Recommendation(s)
- **Option A (preferred):** add `Cache-Control: public, max-age=<window>` +
  an `ETag` (hash of the cache file mtime/content) to the `/api/sleeper/players`
  response so Cloudflare edge-caches the compressed body and clients can `304`.
  Backend-only, a few lines on the route. Trade-off: pick a TTL aligned with the
  nightly Sleeper refresh so newly-synced players aren't hidden too long.
- **Option B:** add a hash/version query-param the web client bumps on refresh
  so the URL itself is cache-keyed — more moving parts, defer.

### RICE-P
| Reach | Impact | Confidence | Effort | **Score** |
|------:|-------:|-----------:|-------:|----------:|
| 2 | 1 | 80% | 1 | **1.6** |

- **Estimated latency delta:** web full-payload fetch ~1.0–2.5 s → near-edge-RTT
  (~0.1–0.3 s) on a cache hit; removes repeated 4.84 MB origin serialization from
  the single free-tier worker. ~0 direct mobile latency (mobile uses `/warm`).
- **Confidence note:** 80% — headers and route are measured/static; the realized
  edge hit-rate depends on Cloudflare's free-tier cache eligibility for a JSON
  `Cache-Control` response, which should be honored but warrants a post-deploy
  `cf-cache-status: HIT` check.

### Related components
`backend/server.py` (`sleeper_players`, `_load_sleeper_cache`), web `app.js`
(consumer), Cloudflare edge config.

### Prerequisites / dependencies
None. Complementary to OBS-NET-01 (cache freshness model).

### Regression risk
Low–medium. Too long a TTL hides newly-added rookies on web until expiry; align
the `max-age` with the nightly refresh and bust on sync. No ELO/tier invariant
touched (this is raw Sleeper metadata, not ranking math).

---

## Top 3 by RICE-P

| Rank | OBS | Score | Severity | One-line |
|---:|---|---:|---|---|
| 1 | **OBS-NET-03** | **16.0** | P2 | Splash is gated on all 4 boot promises incl. the network warm ping — paint the shell on local-state only and detach the network legs. |
| 2 | **OBS-NET-01** | **9.6** | P1 | Cold dyno fetches the 5 MB player cache from upstream Sleeper (no committed/baked cache, ephemeral disk) on the first user's critical path — bake the cache into the image. |
| 3 | **OBS-NET-02** | **5.0** | P3 | Client never sets `Accept-Encoding`; relies on platform-default gzip (br never requested) — non-issue for mobile today (uses 25-byte `/warm`), documented for safety. |

> OBS-NET-04 (RICE-P 4.0, P1) and OBS-NET-05 (1.6, P2) follow. Note OBS-NET-04 is
> higher *severity* (P1) than #3 but lower RICE-P due to lower confidence
> (5–10 s figure unmeasured) and higher effort — exactly the "P1 but not
> top-RICE" case the scoring guide calls out.

---

## CROSS-REF (outside this agent's mobile-network lane — route to synthesis)

- **Web client** downloads the full 4.84 MB `/api/sleeper/players` body
  (`sleeper.ts:44` comment: "Web client keeps /api/sleeper/players because it
  consumes the body"). OBS-NET-05's edge-caching + OBS-NET-02's br all primarily
  benefit **web**; a web-focused agent should own the web-side fetch/caching.
- **`--workers 1`** on gunicorn (`render.yaml:13`) is a single-worker contention
  bottleneck under any concurrent cold-cache fetch / `session/init` — a backend/
  infra agent should weigh `--workers 2` vs free-tier memory limits.
