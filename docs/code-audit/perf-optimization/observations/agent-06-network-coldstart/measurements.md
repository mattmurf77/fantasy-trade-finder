# Network + Cold-Start — Raw Measurements

**Agent:** agent-06-network-coldstart
**Date:** 2026-06-07
**Base URL:** `https://fantasy-trade-finder.onrender.com`
**Tool:** `curl` (HTTP/2 via Cloudflare edge → Render gunicorn origin)
**Dyno state during run:** WARM (first probe TTFB ~0.26 s — the free-tier dyno
was already awake; a true cold start was NOT observed this session, see
"Cold-start note" below). All numbers below are therefore **warm-path** unless
labeled otherwise.

> Method: each endpoint hit 2–5× to smooth jitter. `size_download` is the
> *on-the-wire* byte count (post-compression when an encoding is negotiated).
> `ttfb` = `time_starttransfer`, `total` = `time_total`, seconds.

---

## 1. Edge infrastructure facts (from `-D -` response headers)

| Fact | Value | Source |
|---|---|---|
| Edge / CDN | `server: cloudflare` | response headers |
| Origin | `x-render-origin-server: gunicorn` | response headers |
| HTTP version negotiated | **HTTP/2** (`http_version=2`) | `-w %{http_version}` |
| HTTP/3 advertised | `alt-svc: h3=":443"; ma=86400` (available, not used by curl) | headers |
| Compression at edge | **Cloudflare compresses** when client sends `Accept-Encoding` | see §3 |
| `Vary: Accept-Encoding` | present (so encodings are cached separately) | headers |
| Edge caching of API JSON | **`cf-cache-status: DYNAMIC`** — NOT cached at edge | headers |
| Cache-Control / ETag / Expires on `/api/sleeper/players` | **absent** (no caching directives) | headers |
| Origin worker config | `gunicorn ... --workers 1 --timeout 120` | `render.yaml:13` |
| Render plan | `plan: free` (web service + DB) | `render.yaml` |

Connection reuse (HTTP/2 keep-alive) works: three sequential requests on one
curl handle → `num_connects=1` then `0`, `0`. TLS handshake (`time_appconnect`)
~0.06–0.15 s is paid once and amortized across requests on the same connection.

---

## 2. Warm-path endpoint table (no explicit `Accept-Encoding` — identity)

`curl -s -o /dev/null -w "..." "$BASE$ep"` — 3 runs each.

| Endpoint | http | size (B) | ttfb (s) | total (s) |
|---|---:|---:|---:|---:|
| `/api/feature-flags` | 200 | 711 | 0.264 / 0.238 / 0.196 | 0.264 / 0.239 / 0.196 |
| `/api/tier-config` | 200 | 1 440 | 0.262 / 0.234 / 0.234 | 0.263 / 0.234 / 0.234 |
| `/api/sleeper/players/warm` | 200 | 25 | 0.357 / 0.204 / 0.201 | 0.357 / 0.204 / 0.201 |
| `/api/sleeper/players` (full) | 200 | **4 837 423** | 0.593 / 1.041 | **4.593 / 3.706** |

`size=711` / `1440` for the small endpoints is the **uncompressed identity**
body — curl with no `Accept-Encoding` gets no compression and Cloudflare passes
the raw JSON through.

---

## 3. Compression A/B — `/api/sleeper/players` (the 4.84 MB payload)

Direct comparison, fresh connection each run.

| Encoding requested | Encoding returned | size (B) | total (s) (3 runs) |
|---|---|---:|---|
| *(none / identity)* | none | **4 837 423** | 7.034 / 2.535 / 3.311 |
| `Accept-Encoding: gzip` (iOS/Android default) | **gzip** | **662 603** | 1.023 / 1.373 / 1.313 |
| `Accept-Encoding: deflate` | none | 4 837 423 | 3.545 |
| `Accept-Encoding: gzip, br` | **br** | **676 415** | 2.154 / 0.970 / 1.290 |

**Compression ratio:** 4.84 MB → ~662 KB gzip (**86% smaller**) / ~676 KB
brotli. (Brotli on-the-wire is marginally larger here than gzip only because
Cloudflare's br quality vs gzip level differ for this body; both ≈86% off.)
**Time saved:** identity ~2.5–7.0 s → compressed ~1.0–2.2 s.

Notable: `deflate` is **not** honored by Cloudflare for this response (returns
identity). Only `gzip` and `br` trigger compression.

### Origin still serializes the full body (compression is edge-side)
TTFB barely moves between identity and gzip (`ttfb` identity 0.69 s vs gzip
1.09 s), confirming the **origin (gunicorn) serializes the full ~4.84 MB JSON
on every request** — Cloudflare compresses it at the edge afterward. The origin
CPU + memory cost of `jsonify(cached)` over ~7 600 players is paid regardless of
the client's encoding.

---

## 4. Compression on the small first-paint endpoints (`gzip, br`)

`curl -H "Accept-Encoding: gzip, br" -D -`

| Endpoint | content-encoding | content-length (B) | total (s) |
|---|---|---:|---:|
| `/api/feature-flags` | br | 331 | 0.372 |
| `/api/tier-config` | br | 202 | 0.248 |
| `/api/sleeper/players/warm` | br | 29 | 0.200 |
| `/api/profile/<u>` (404 sample) | br | 26 | 0.220 |

These bodies are already tiny; compression saves only a few hundred bytes and
total time is dominated by the ~0.2 s edge↔origin round-trip, not payload.

---

## 5. Authenticated first-paint GETs (no token — rejection latency)

The brief forbids POST/mutation, so a real session token could not be minted.
These were hit **without** a token to (a) confirm they are session-gated and
(b) measure the 401 round-trip cost. The *authed* payload sizes are characterized
from code, not measured.

| Endpoint | http | size (B) | total (s) |
|---|---:|---:|---:|
| `/api/rankings?position=QB` | 401 | 79 | 0.246 |
| `/api/trio?position=QB` | 401 | 79 | 0.199 |
| `/api/rankings/progress` | 401 | 79 | 0.292 |
| `/api/me/streak` | 401 | 79 | 0.210 |

All four return `401` with a 79-byte error body → confirmed session-gated
(`_require_session` in `backend/server.py`). These are the real first-paint
data calls once a token exists (`RankScreen.tsx:77/84/91`,
`TabNav.tsx:174` prefetch, `RootNav.tsx:77`).

---

## 6. Cold-start note (evidence by absence + code)

A true 30–60 s cold wake was **not** triggered this session — the dyno answered
the first probe in 0.26 s, i.e. it was already warm. That itself is a data
point: the dyno had been hit recently. Cold-start cost is reasoned from code +
infra (see findings OBS-NET-02 / OBS-NET-03):

- `render.yaml` has **no `disk:` mount** → the container filesystem is
  ephemeral on the free tier.
- `data/` is **gitignored** (`.gitignore:8`) and the cache file
  `data/.sleeper_players_cache.json` (5 068 172 B locally) is **NOT committed**
  (`git ls-files` → no match).
- Therefore on a cold container the in-memory `_sleeper_cache` is `None` AND the
  disk file is absent → the first `/api/sleeper/players/warm`
  (`backend/server.py:4414`) falls into `_ensure_sleeper_cache_populated()`
  (`server.py:4337`) which does a **synchronous ~5 MB fetch from
  `api.sleeper.app` with a 45 s timeout** (`server.py:4350-4355`) plus a
  `sync_players` DB write (`server.py:4378-4387`).
- `--workers 1` (`render.yaml:13`) means that one in-flight cold fetch blocks
  the single worker.

So the cold-start tax = Render dyno wake (30–60 s documented) **plus** a
first-request ~5 MB upstream Sleeper fetch + DB sync, serialized on one worker.
