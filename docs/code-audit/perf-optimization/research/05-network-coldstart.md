# 05 — Network Optimization & Serverless Cold-Start Mitigation

## TL;DR

- **Enable gzip now** via `Flask-Compress` (one-line install, zero config change): shrinks the 4.8 MB player JSON payload by 70–90%, to roughly 480 KB–1.4 MB on the wire. This is the single highest-leverage action in this document.
- **Cold starts on Render free tier are 30–60 s and unavoidable** at rest; the only reliable mitigations are external warm-pings (UptimeRobot/cron every ≤10 min) or upgrading to a paid always-on dyno ($7/mo). No client-side trick eliminates the startup stall — the minimum residual with warm pings is ~0 s when pings land, but a ~25–60 s stall remains for the gap request (early morning, long weekend idle). Quantify honestly: a user who opens the app after a genuine 15+ min idle period will always see a blocking delay.
- **Payload minimization** (field trimming, ID-only list endpoints, `?fields=` sparse selection) complements compression and is especially valuable for slow cellular where even compressed bytes matter.
- **Request coalescing / batching**: replace sequential API calls with `Promise.all` or a single multi-entity endpoint to halve or better the number of sequential round-trips.
- **Connection reuse** (HTTP keep-alive, TLS session resumption, HTTP/2): eliminates 200–400 ms of per-request handshake tax on mobile LTE. Render's managed proxy supports HTTP/2; Gunicorn/Flask needs no change.
- **Skeleton screens + honest "waking up" copy** convert an unavoidable cold-start stall from an apparent freeze into a managed wait with clear user expectations.
- **CDN/edge for slow-changing data** (player database, avatars): moves egress off Render's free CPU budget and cuts latency for repeat reads without code changes.

---

## Why It Matters for FTF

FTF has a documented performance crisis along two axes:

1. **Payload size.** The player JSON is ~4.8 MB uncompressed. On a median US LTE connection (~30 Mbps down, ~60 ms RTT) that is ~1.3 s of pure transfer time per request. On weak 4G or wifi the tail is much worse. Without compression every cold session pays this cost before a single row renders.

2. **Cold-start stall.** FTF's Flask backend runs on Render's free tier, which spins the web service down after 15 minutes of inactivity. Measured wake times range from 25 s (best-case, lightweight app) to 50–60 s (realistic for a Flask + SQLAlchemy + Postgres boot). The first user action after any idle period hits this wall. Fantasy-football usage is bursty — waiver wire day, draft night — followed by days of silence, making cold starts frequent.

Together these produce a "first action brutally slow" UX pattern that degrades trust. The tactics below address both axes.

---

## Tactics

### 1. Response Compression (gzip / Brotli)

- **What it is** — HTTP content negotiation: server compresses the response body before sending; client decompresses on receipt. gzip is the universal baseline; Brotli achieves ~5–15% better compression than gzip for text at the cost of higher CPU.
- **When to use it** — For any text-based response ≥1 KB. Specifically: JSON player data, trade payloads, API list endpoints. Do NOT compress already-compressed data (JPEG, PNG, pre-gzipped assets).
- **Expected impact** — gzip reduces typical JSON 65–79% (benchmark: 1,258 KB → 262 KB, 79.4% reduction, −165 ms average latency on that payload). Brotli adds a further ~5–10% size reduction. For FTF's 4.8 MB player payload: gzip → ~960 KB–1.4 MB; Brotli → ~720 KB–1.1 MB. Impact label: **Massive** (>2 s saved on a cold wire transfer for cellular users).
- **RN/Flask applicability** — `Flask-Compress` (`pip install flask-compress`) wraps the Flask app in two lines. It auto-detects `Accept-Encoding` and applies gzip or Brotli. No Gunicorn changes needed. RN's `fetch` sends `Accept-Encoding: gzip, deflate, br` by default; the decompression is transparent at the OS/HTTP layer.
- **Cost / risk** — Adds CPU per compressed response (~2 ms overhead per request, per the Istio benchmark). On Render's free-tier single instance this is acceptable for infrequent requests but becomes a bottleneck under heavy concurrent load. Set a minimum size threshold (e.g., 1,000 bytes; `Flask-Compress` default is 500 bytes) to skip compressing tiny responses. Brotli at level 11 is slow; levels 4–6 provide 80–90% of the size gain with fraction of the CPU cost.
- **Sources** — [Flask-Compress PyPI](https://pypi.org/project/Flask-Compress/); [Brotli vs GZIP — DebugBear](https://www.debugbear.com/blog/http-compression-gzip-brotli); [79% reduction with gzip — Vijay Gupta, Medium](https://medium.com/@vijayrauniyar1818/how-we-reduced-api-response-size-by-79-with-istio-gzip-compression-f57cfdd7cfd9); [ZSTD vs Brotli vs GZIP — koder.ai](https://koder.ai/blog/zstd-vs-brotli-vs-gzip-api-compression)

---

### 2. Payload Minimization (field trimming, sparse fieldsets, ID-only lists)

- **What it is** — Returning only fields the client needs for a given view. Variants: (a) hardcoded lean DTOs per endpoint ("list" vs "detail"), (b) `?fields=id,name,position,team` sparse selection per JSON:API convention, (c) ID-only list responses where the client has a local cache.
- **When to use it** — List endpoints (e.g., `/players`) that return many rows with many fields per row. Do NOT use when the client genuinely needs all fields (e.g., trade analysis that requires every stat attribute).
- **Expected impact** — Varies by payload shape. If the player record carries 40 fields but the tiers screen needs only 8, a lean endpoint shrinks the response to ~20% of its current size before compression is even applied. Combined with gzip, a 4.8 MB payload could drop to ~100–200 KB. Impact label: **High** (~1–2 s saved; depends on how many fields are currently unused by the mobile client).
- **RN/Flask applicability** — Flask: add `?fields=` query param handling in the route, filter SQLAlchemy `select()` columns. RN: pass the param in TanStack Query's `queryFn`. No new library needed. Alternatively, create a dedicated `/players/slim` endpoint with a fixed lean schema.
- **Cost / risk** — Low-risk if using hardcoded slim endpoints. Query-param sparse fieldsets require server-side validation to prevent field enumeration. Client must gracefully handle missing fields if a future response changes shape.
- **Sources** — [Sparse Fieldsets — Jan Bajena, Medium](https://bajena3.medium.com/decrease-load-on-your-json-apis-by-using-sparse-fieldsets-3e2c9491dc16); [Sparse Fieldsets — drupalize.me](https://drupalize.me/tutorial/jsonapi-sparse-fieldsets); [Mobile API Best Practices — talkthinkdo.com](https://talkthinkdo.com/guides/api-and-integration/mobile-api-best-practices/)

---

### 3. Delta / Diff Payloads (since-timestamp sync)

- **What it is** — Client sends its last-known sync token or `updated_after` timestamp; server returns only records changed since then. Standard form: `GET /players?updated_after=<ISO8601>`.
- **When to use it** — Warm-session refreshes after the full data is already cached locally (TanStack Query `staleTime` expired). Not suitable for first-load when the cache is cold.
- **Expected impact** — After the initial cold fetch, refresh calls return tens of records rather than thousands. On a typical week, player data changes (injuries, news, ownership) touch <5% of the roster. Impact label: **High** for warm sessions; **Minimal** for cold sessions (no change to first-load).
- **RN/Flask applicability** — Flask: add `updated_after` filter to player query. SQLAlchemy: `where(Player.updated_at > updated_after)`. RN: store last-fetched timestamp in Zustand/AsyncStorage, pass as query param. TanStack Query `refetchOnWindowFocus` and background refresh benefit directly.
- **Cost / risk** — Requires an `updated_at` column on all synced tables (already standard practice). Cache invalidation logic must be correct — missed updates are silent data bugs. Needs a periodic full-refresh fallback (e.g., once daily).
- **Sources** — [Optimizing JSON Payloads — zigpoll.com](https://www.zigpoll.com/content/how-can-the-frontend-team-optimize-the-json-payload-to-improve-api-response-time-and-reduce-the-load-on-our-backend-servers); [Mobile API Best Practices — talkthinkdo.com](https://talkthinkdo.com/guides/api-and-integration/mobile-api-best-practices/)

---

### 4. HTTP Keep-Alive & TLS Session Resumption

- **What it is** — Keep-alive: the TCP connection is held open across multiple requests (HTTP/1.1 default). TLS session resumption: on reconnect, the TLS session ticket is reused, skipping the full certificate exchange. Together they eliminate 200–400 ms of handshake overhead per new request on mobile.
- **When to use it** — Always. These are baseline behaviors for modern HTTP stacks; the question is whether they are correctly configured, not whether to enable them.
- **Expected impact** — On a 4G LTE network (60–80 ms RTT), TLS 1.2 requires ~240 ms handshake overhead (3 RTTs); TLS 1.3 reduces this to ~120 ms (2 RTTs); TLS 1.3 0-RTT resumption cuts it to ~0 ms on resumed connections. Impact label: **Medium–High** for sequential requests (first request still pays; subsequent requests in the same session are free). Actual saving per resumed request: 120–240 ms.
- **RN/Flask applicability** — Render's proxy (nginx/envoy-based) handles TLS termination and session tickets automatically. Gunicorn and Flask are behind the proxy; no changes needed. RN's `fetch` (via the underlying platform HTTP stack) reuses connections by default. To verify: enable `Accept-Encoding` response headers and check `Connection: keep-alive` in network logs.
- **Cost / risk** — Zero configuration cost. Risk: keep-alive connection pooling can exhaust server file descriptors under high concurrency, but not a concern on a free-tier single dyno with low traffic.
- **Sources** — [HTTP Keep-Alive — USAVPS](https://usavps.com/blog/http-keep-alive/); [TLS Session Resumption — oneuptime.com](https://oneuptime.com/blog/post/2026-03-20-tls-session-resumption-faster-https/view); [TLS Handshake Latency — systemoverflow.com](https://www.systemoverflow.com/learn/networking-protocols/tls-ssl/tls-handshake-performance-rtt-impact-and-termination-strategies)

---

### 5. HTTP/2 Multiplexing

- **What it is** — HTTP/2 allows multiple concurrent request/response streams over a single TCP+TLS connection. Eliminates the HTTP/1.1 need for multiple parallel connections; also compresses headers with HPACK.
- **When to use it** — When the client makes several concurrent requests to the same origin (e.g., parallel fetches for players + trades + leagues on boot).
- **Expected impact** — On mobile networks with high RTT, HTTP/2 shows ~60% latency improvement over HTTP/1.1 for multi-resource loads. p95 TTFB drop of ~0.9 s observed in a case study (2.8 s → 1.9 s). Impact label: **High** for boot sequences with ≥3 parallel requests. **Caveat:** on high-loss mobile networks, TCP head-of-line blocking can eliminate or reverse the gain (one packet loss stalls all streams). HTTP/3/QUIC solves this but is not available on Render free tier.
- **RN/Flask applicability** — Render's proxy supports HTTP/2 end-to-end. RN's `fetch` supports HTTP/2 natively. Flask/Gunicorn speak HTTP/1.1 to the proxy only; the client-facing H2 termination is done by Render's proxy. No code change needed; benefit is automatic.
- **Cost / risk** — Zero for FTF. Monitoring: if you observe degraded p95 on cellular connections, consider whether HTTP/3 (not available on free tier) would help.
- **Sources** — [HTTP/2 vs HTTP/1.1 performance — webhosting.de](https://webhosting.de/en/http2-multiplexing-vs-http11-performance-background-optimization/); [HTTP evolution — Medium, Koushik Das](https://medium.com/@dasbabai2017/http-1-1-vs-http-2-vs-http-3-the-evolution-of-web-connections-ed90b45432a8)

---

### 6. Request Batching & Coalescing

- **What it is** — Combining multiple independent API calls into a single HTTP request, or firing them concurrently with `Promise.all` instead of sequentially. At the server level: a `/batch` endpoint accepts an array of sub-requests.
- **When to use it** — Boot sequence where the app needs players + leagues + trades + flags in one session initialization. Do NOT batch requests that are logically sequential (e.g., auth → then use token → then fetch user data).
- **Expected impact** — Replacing 4 sequential round-trips (each ~200–400 ms on mobile) with 1 concurrent bundle saves 600–1,200 ms. Impact label: **High** if sequential waterfalls exist today. If already using `Promise.all` the gain is zero; if using `await` chains it can be transformative.
- **RN/Flask applicability** — RN: audit `useEffect` hooks and `queryFn` chains for sequential `await` patterns; replace with `Promise.all([fetchA(), fetchB()])`. TanStack Query v5 `useQueries` fires multiple queries concurrently. Flask: a `/boot` aggregate endpoint can return player snapshot + league list + feature flags in a single response, eliminating 3 round-trips.
- **Cost / risk** — Low risk for `Promise.all` refactors. A batch endpoint adds server-side complexity and a fat response that must be structured carefully. Failure modes: one sub-request failure should not abort the entire batch (partial success pattern).
- **Sources** — [Request Batching in React — Better Programming](https://betterprogramming.pub/request-batching-in-react-b8fd0656b28b); [Optimising React Native 2026 — addjam.com](https://addjam.com/blog/2026-02-25/optimising-react-native-performance-real-world-lessons/)

---

### 7. Render Free-Tier Cold Starts: Causes & Honest Assessment

- **What it is** — Render's free web service tier automatically spins the dyno down after 15 minutes of inactivity. The next inbound request triggers a full OS-level container boot: Python interpreter, Flask app, SQLAlchemy pool, connection to managed Postgres. Measured wake times: 25 s (best case, simple app) to 50–60 s (realistic for Flask + Postgres) with some user reports of 2–3 min under heavier boot paths.
- **The honest limit** — No client-side technique eliminates the server boot time. Skeleton screens, optimistic UI, and "waking up" copy reduce user distress but cannot change the physical timeline. The server must complete initialization before returning a byte. This is a **hard lower bound** of ~25 s residual for the first request on a cold dyno. The only way to eliminate the delay is to prevent the cold start from happening.
- **Impact label** — **Massive** (P0 severity): >30 s blocking stall on every session after 15 min idle. For a bursty app like FTF this is the majority of first interactions on any given day.
- **Sources** — [Render free tier cold start — Sam Kiel blog](https://blog.samkiel.dev/your-render-free-tier-is-not-broken-its-just-cold); [Fix Render cold start — Saurav, Medium](https://medium.com/@sauravhldr/fix-render-com-free-tier-slow-initial-load-cold-start-problem-using-free-options-and-easy-steps-c0b6c7af8276); [Render community thread](https://render.discourse.group/t/do-web-services-on-a-free-tier-go-to-sleep-after-some-time-inactive/3303)

---

### 8. Cold-Start Mitigation: External Warm Pings / Keep-Alive Pings

- **What it is** — An external HTTP monitoring service (UptimeRobot, BetterUptime, GitHub Actions cron, a Railway cron worker) pings a lightweight `/health` endpoint on a schedule shorter than Render's 15-minute idle threshold. As long as pings arrive before the 15-minute window closes, the dyno never sleeps.
- **When to use it** — When actual user traffic is too sparse to keep the dyno warm naturally, and upgrading to a paid tier is not yet justified.
- **Expected impact** — Eliminates cold starts during periods when pings are firing. Residual risk: if pings pause (service outage, free-tier rate limits), the next genuine user request hits a cold start. On UptimeRobot free tier (minimum interval: 5 minutes), cold starts are possible after a ≥15-min gap — i.e., if the monitoring service misses 3 consecutive checks. With a 10-minute ping interval there is a ≤5-minute window during which a cold start can still occur. **Quantified residual: ~25–60 s stall for the first request in any genuine 15+ min idle window.** Impact label: **Massive** (eliminates the stall for >90% of sessions in a low-traffic app with regular background pings).
- **RN/Flask applicability** — Flask: add `GET /health` returning `{"status": "ok"}` with no DB call (or a trivially lightweight DB ping). Register UptimeRobot to hit this endpoint every 5–10 minutes. RN boot sequence can also issue a fire-and-forget `/health` ping at app launch to start warming the server while the splash screen shows.
- **Cost / risk** — Free (UptimeRobot free tier: 50 monitors). Risk: the warm ping costs ~1 req every 5–10 min; on Render free tier this contributes to the 750 hr/mo free usage (negligible). It does NOT eliminate cold starts caused by app restarts (e.g., Render redeploying).
- **Sources** — [UptimeRobot approach — Sam Kiel blog](https://blog.samkiel.dev/your-render-free-tier-is-not-broken-its-just-cold); [Keep free app alive — Sergei Liski, Medium](https://sergeiliski.medium.com/how-to-run-a-full-time-app-on-renders-free-tier-without-it-sleeping-bec26776d0b9); [Keep Render alive 24/7 — Prajwal MD, Medium](https://medium.com/@prajju.18gryphon/keep-your-render-free-apps-alive-24-7-41aa85d71256)

---

### 9. Client-Side Warm-Up Ping at Boot

- **What it is** — The RN app fires a fire-and-forget `fetch('/health')` as one of its very first actions (during splash screen, before navigation state resolves). This starts the server waking up a few hundred milliseconds earlier than the first real data request.
- **When to use it** — As a complement to external warm pings, not a replacement. Most valuable when the app boot sequence itself has 500–1,000 ms of JS initialization before the first API call.
- **Expected impact** — Reduces cold-start wall time visible to the user by the amount of time the app itself spends initializing before the first real request. Typically saves 500–1,500 ms of the stall. **Does not eliminate the cold start** — if the server needs 30 s to boot and the app takes 1 s to initialize, the user still waits ~29 s. Impact label: **Low** in isolation; **Medium** combined with other loading UX.
- **RN/Flask applicability** — One `fetch()` call in the root component's `useEffect` or in the Expo router's `_layout.tsx`. The health endpoint must be zero-cost (no DB query).
- **Cost / risk** — ~0.5 person-days. Risk: adds one extra request per session; trivial.
- **Sources** — [Conquering Cold Starts — DEV.to](https://dev.to/vaib/conquering-cold-starts-strategies-for-high-performance-serverless-applications-59eg); [Serverless Cold Starts — movestax.com](https://www.movestax.com/post/7-cold-start-mitigation-techniques-for-serverless-apps)

---

### 10. The Honest Fix: Paid Always-On Dyno

- **What it is** — Render's paid tier ($7/month for the Starter plan as of 2025–2026) disables sleep. The service runs continuously; there are no cold starts from idling.
- **When to use it** — Whenever FTF has real users who experience the cold-start stall as a trust-breaking moment. This is not a technical mitigation — it is the architecturally correct solution.
- **Expected impact** — Eliminates all idle-induced cold starts. Warm-path response time returns to normal (sub-second for cached queries). Residual cold starts still occur on deploys. Impact label: **Massive** (removes the P0 completely).
- **Cost / risk** — $7/month. Risk: zero for app behavior; only financial.
- **Sources** — [Render pricing — community thread](https://community.render.com/t/options-bridging-free-tier-and-20-mo-to-avoid-service-sleeping/12233); [Render review 2025 — workflowautomation.net](https://workflowautomation.net/reviews/render)

---

### 11. Perceived Performance: Skeleton Screens & Honest Status Copy

- **What it is** — Skeleton screens are placeholder UI components (grey boxes in the shape of cards, lists, names) shown while real data loads. "Honest status copy" is an explicit UI message like "Server is waking up — usually ~30 s" rather than a generic spinner.
- **When to use it** — During any operation with a known >500 ms wait. Specifically: cold-start boot, first player-list fetch, trade-deck load.
- **Expected impact** — Studies (Facebook, Nielsen Norman Group) show users perceive skeleton-loaded content as loading up to 50% faster than spinner-only loading, even when wall-clock time is identical. For cold starts specifically, explicit status copy significantly reduces abandonment vs. a frozen UI. Impact label: **Medium** on perceived performance (actual latency unchanged).
- **RN/Flask applicability** — `react-native-auto-skeleton` auto-generates skeletons from existing component layouts (zero config, Fabric/New Architecture compatible). Alternatively, `moti` or `react-native-skeleton-placeholder` for custom shapes. The "waking up" copy can be a timed `useEffect` that changes the loading message after 5 s.
- **Cost / risk** — 0.5–1 person-days per screen. Risk: skeleton must match the shape of actual content or it causes a jarring layout shift on reveal.
- **Sources** — [Skeleton Loading in React Native — oneuptime.com](https://oneuptime.com/blog/post/2026-01-15-react-native-skeleton-loading/view); [The Illusion of Speed — Ray Roman, Medium](https://medium.com/gronda/the-illusion-of-speed-loading-states-with-react-1c676ccce484); [Skeleton screens UX — freeCodeCamp](https://www.freecodecamp.org/news/how-to-use-skeleton-screens-to-improve-perceived-website-performance/)

---

### 12. Progressive / Lazy Hydration

- **What it is** — On cold boot, return a minimal "shell" response first (e.g., top-50 players by ADP), then stream or lazy-fetch the remaining players in background pages. The user can interact with the shell while the rest loads.
- **When to use it** — When the cold player payload is unavoidable and skeleton screens alone are insufficient. Also useful on Render cold start: the server can stream early rows before finishing the full query.
- **Expected impact** — Time-to-interactive drops to the latency of the first page of data. If first 50 players return in 800 ms and the remaining 3,000 arrive over the next 3 s, the user is unblocked immediately. Impact label: **High** for first-load UX.
- **RN/Flask applicability** — Flask: add `?page=1&limit=50` pagination to the player endpoint. RN: TanStack Query `useInfiniteQuery` fetches subsequent pages as the list scrolls. Boot sequence fetches page 1 eagerly; remaining pages fetch lazily.
- **Cost / risk** — 1–2 person-days (pagination logic + client infinite scroll). Risk: requires server-side cursor or offset pagination, which must be stable under concurrent writes.
- **Sources** — [Conquering Cold Starts — DEV.to](https://dev.to/vaib/conquering-cold-starts-strategies-for-high-performance-serverless-applications-59eg); [Mobile API Best Practices — talkthinkdo.com](https://talkthinkdo.com/guides/api-and-integration/mobile-api-best-practices/)

---

### 13. CDN / Edge Caching for Static and Slow-Changing Data

- **What it is** — Serve assets (player avatars, static images, the Sleeper player universe JSON) from a CDN edge node close to the user instead of from the Render origin. Popular options: Cloudflare CDN (free tier), Cloudinary (images + transformations), AWS CloudFront.
- **When to use it** — For assets that change infrequently (player photos: once per season; Sleeper player universe JSON: weekly). Do NOT use for user-specific or real-time data.
- **Expected impact** — For repeat loads of the player avatar grid, CDN cache hits are served in ~5–20 ms (edge) vs. 300–800 ms (origin over mobile). Offloads egress bandwidth from Render's free tier. Impact label: **High** for images and static JSON; **Minimal** for dynamic trade data.
- **RN/Flask applicability** — RN: point avatar `Image` src at a CDN URL instead of the Flask origin. Flask: add `Cache-Control: public, max-age=604800` headers to the player JSON endpoint; put Cloudflare in front (free). The Render CDN feature request thread confirms Render does not natively offer CDN-backed static hosting on the free tier, making an external CDN necessary.
- **Cost / risk** — Cloudflare free tier has no egress fees for CDN. Cloudinary free tier: 25 credits/month. Risk: stale cache for time-sensitive player data must be handled with short TTLs or cache busting.
- **Sources** — [CDN for static assets on Render — Render feedback](https://feedback.render.com/features/p/cdn-for-static-assets-in-backend-apps); [React Native image caching — oneuptime.com](https://oneuptime.com/blog/post/2026-01-15-react-native-image-caching/view); [CDN configuration guide — jamesrossjr.com](https://www.jamesrossjr.com/blog/cdn-configuration-guide)

---

### 14. Measuring Real Network Timing

- **What it is** — Using `curl -w` format strings to decompose request latency into DNS, TCP connect, TLS handshake, server processing (TTFB), and total transfer time. Identifies which phase is the bottleneck before optimizing.
- **When to use it** — Before and after each optimization to verify gains are real and attribute latency correctly. Run against the Render production URL from multiple network conditions (wifi, hotspot-tethered LTE).
- **Recommended curl one-liner:**
  ```bash
  curl -o /dev/null -s -w \
    "DNS:            %{time_namelookup}s\n\
  TCP Connect:    %{time_connect}s\n\
  TLS Handshake:  %{time_appconnect}s\n\
  Pre-Transfer:   %{time_pretransfer}s\n\
  TTFB:           %{time_starttransfer}s\n\
  Total:          %{time_total}s\n\
  Payload:        %{size_download} bytes\n" \
    https://your-render-app.onrender.com/api/players
  ```
  `time_starttransfer` = TTFB (server processing + all setup). `time_total - time_starttransfer` = transfer time. Cold vs. warm: run immediately after a 20-minute idle, then again 5 minutes later.
- **RN applicability** — In-app: use the `fetch` `response.headers` timestamp combined with `performance.now()` around the fetch call. React Native Flipper's Network plugin shows per-request timing in the Flipper desktop app. Metro + React DevTools profiler for JS-thread cost.
- **Sources** — [Timing with cURL — Cloudflare blog](https://blog.cloudflare.com/a-question-of-timing/); [TTFB with curl — makandracards.com](https://makandracards.com/operations/528263-measure-http-connection-times-ttfb-curl); [curl time-spent — vianneyfaivre.com](https://vianneyfaivre.com/tech/curl-time-spent-network-backend)

---

## Impact Ladder Summary

| Tactic | Impact Label | Reach | Est. Latency Delta |
|---|---|---|---|
| Enable gzip compression | **Massive** | Every session (player fetch) | −3–4 s on cold cellular for 4.8 MB payload |
| Paid always-on dyno | **Massive** | Every session after idle | −25–60 s cold-start stall (eliminated) |
| External warm ping (UptimeRobot) | **Massive** | ~90% of sessions | −25–60 s for most sessions; ~60 s residual for gap sessions |
| Payload minimization (slim endpoint) | **High** | Every session | −1–3 s depending on field reduction |
| Request batching / coalescing | **High** | Every boot sequence | −600–1,200 ms for sequential waterfalls |
| Lazy hydration / pagination | **High** | First-load experience | Time-to-interactive −2–4 s |
| HTTP/2 multiplexing | **High** | Parallel-request paths | −0.9 s p95 on multi-request boot |
| CDN for avatars / static JSON | **High** | Player list views | −300–800 ms per image on repeat loads |
| Delta sync (since-timestamp) | **High** (warm), **Minimal** (cold) | Warm refresh sessions | −1–2 s on warm refresh |
| Skeleton screens + status copy | **Medium** (perceived) | Every data-loading screen | Perceived −30–50% wait; actual 0 ms |
| TLS session resumption | **Medium** | Sequential requests, same session | −120–240 ms per resumed connection |
| Client-side warm ping at boot | **Low** | Cold-start sessions | −500–1,500 ms of stall (partial overlap with server boot) |

---

## Anti-patterns to Flag in the Audit

The following patterns should be grepped or searched for directly in the codebase audit:

- **Missing compression middleware** — grep `server.py` for `Flask-Compress` import; if absent, compression is disabled. The full 4.8 MB player JSON is sent uncompressed on every request.
- **Sequential `await` chains in boot sequence** — grep `mobile/` for `await fetch` or `await query` patterns inside `useEffect` that are not wrapped in `Promise.all`. Each one adds a full RTT + server time serial penalty.
- **`/players` endpoint returning all fields for all players** — grep routes for `/players` and examine the `SELECT` or ORM query. If it selects `*` or all columns, there is no lean path for the mobile client.
- **No `Cache-Control` headers on slow-changing endpoints** — curl the `/players` endpoint and check `Cache-Control` response header. Absence means every client fetches fresh on every mount even if the data is hours old.
- **No `/health` endpoint** — grep `server.py` for a health/ping route. Absence means no external warm pinger can safely hit the server, and deploy-readiness checks are blind.
- **Blocking spinner on cold start with no copy change** — grep mobile screens for loading state rendering. If the cold-start state shows only a generic spinner with no timeout-triggered copy change, user experience is opaque.
- **Avatar images loaded from Render origin** — grep for `Image` sources pointing to `onrender.com` or the Flask `/` origin. These should be CDN-backed.
- **`Accept-Encoding` not sent** — In any custom fetch wrapper in `mobile/`, check that no code explicitly strips the `Accept-Encoding` header. Native fetch sends it by default; custom headers objects that don't spread defaults can lose it.
- **All 4.8 MB fetched again on every app foreground** — grep for `staleTime` in TanStack Query config. If `staleTime` is 0 (default), the full player payload is re-fetched every time the app comes to foreground. This is addressed in the data-fetching research doc but is also a direct network cost.

---

## Recommended Defaults for FTF

These are opinionated, immediately actionable defaults:

| Setting | Recommended Value | Rationale |
|---|---|---|
| `Flask-Compress` min size threshold | `1000` bytes | Skip tiny JSON responses; compress all player/trade payloads |
| `Flask-Compress` Brotli level | `4` (or gzip-only to start) | Level 4 gives ~90% of max compression at <10% of level 11 CPU cost; gzip is simpler and universal |
| Warm ping interval | `10 minutes` (UptimeRobot) | Safely inside the 15-min Render idle window; 5 min is more reliable but uses more free monitor quota |
| `/health` endpoint DB behavior | No DB call (return `{"ok": true}` only) | Keeps the ping lightweight; a DB-calling health check can itself trigger a slow cold path |
| Client boot warm ping | Fire-and-forget in `_layout.tsx` before navigation ready | Starts server warm-up while JS bundle initializes |
| Skeleton screen timeout-copy | Show "Server is waking up (~30 s)…" after `5 s` with no response | Honest; prevents user from assuming the app crashed |
| Player endpoint pagination | `?page=1&limit=50` default, `useInfiniteQuery` | Unblocks the UI within 800 ms; remaining players stream in |
| `Cache-Control` on `/players` | `public, max-age=3600, stale-while-revalidate=86400` | 1-hour fresh window; client can use stale data for up to 24 h while revalidating in background |
| Avatar CDN | Cloudflare free tier in front of Render; or Cloudinary | Removes avatar egress from Render CPU budget |
| Compression threshold for enabling | Any response body ≥ 1 KB | Below 1 KB, compression overhead exceeds savings |
| Measurement cadence | `curl -w` timing script before + after each optimization | Verify every change; distinguish TTFB from transfer time |

**On the cold start residual:** even with external warm pings at 10-minute intervals and a client-side boot ping, the worst-case residual is a ~25–60 s blocking stall for the first user request after a genuine ≥15-min idle window (e.g., an early morning first open). The only way to reduce this residual to zero is the paid always-on dyno. All other mitigations reduce the probability and UX impact of the cold start but do not eliminate it.

---

## Open Questions / Needs Measurement

1. **Actual compressed size of the player payload** — Run `curl --compressed` against the production Render endpoint and measure `Content-Length` before and after enabling `Flask-Compress`. The 4.8 MB figure is unconfirmed compressed.
2. **Field utilization audit** — Which fields of the player record does the mobile Tiers screen actually render? A payload audit (log the response, count accessed fields) will size the opportunity for a slim endpoint.
3. **Sequential waterfall count on boot** — Instrument the RN app with `performance.now()` around each boot fetch to measure how many round-trips are sequential today.
4. **Render cold-start timing for this specific app** — The reported 25–60 s range varies by app complexity. FTF's Flask + SQLAlchemy + Postgres connection needs direct measurement: `curl -w %{time_starttransfer}` against a cold dyno (after 20-min idle).
5. **TLS termination point** — Confirm whether Render's proxy terminates TLS 1.3 and enables 0-RTT tickets. This determines the effective per-connection saving from session resumption.
6. **HTTP/2 confirmed active** — Run `curl --http2 -v` against the Render URL and verify `< HTTP/2` in the response. If Render's proxy is HTTP/1.1 to the client, the multiplexing benefit is absent.
7. **UptimeRobot reliability under Render's 750 hr/mo cap** — Confirm whether continuous warm pings push the free tier over 750 hr/mo at scale (they should not, but confirm).
