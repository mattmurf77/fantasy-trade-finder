# Agent 01 — Mobile API client layer (`mobile/src/api/`)

## Scope & method

This audit covers the mobile API client layer only — `mobile/src/api/`
(`client.ts`, `auth.ts`, `sleeper.ts`, `trades.ts`, `league.ts`, `rankings.ts`,
`feedback.ts`, plus the in-dir helpers `flags.ts`, `notifications.ts`,
`leaderboard.ts`). Method: static reading of every file in the directory and the
direct callers that define the player + trade fetch paths
(`mobile/App.tsx`, `mobile/src/state/useSession.ts`,
`mobile/src/screens/SignInScreen.tsx`, `mobile/src/screens/TradesScreen.tsx`),
plus **measured** read-only `curl` timings against the live Render backend
(`https://fantasy-trade-finder.onrender.com`) for the endpoints this layer
calls — `/api/sleeper/players`, `/api/sleeper/players/warm`,
`/api/feature-flags`, `/api/tier-config`, `/api/session/ping`. All `curl`
calls were GET only; nothing was mutated. RICE-P scores use the repo's
`templates/scoring-criteria.md`; each observation cites `path:line`. Findings
focus on the user-reported pain (player + trade render latency): request
waterfalls, the `initLeagueSession` sequencing, `warmPlayerCache` usage,
compression, dedup/coalescing, and retry/timeout config.

Headline measured facts that several observations lean on:
- `/api/sleeper/players` full payload = **4,837,423 B uncompressed, 7.48 s**;
  with `Accept-Encoding: gzip` it is **676,415 B, 1.03 s** (≈86% smaller).
- `/api/sleeper/players/warm` = **25 B**; warm dyno **0.20–0.86 s**, first hit
  on a sleeping dyno **4.85 s** (cold-start tax).
- The client wrapper sets `Accept: application/json` but **no
  `Accept-Encoding`** (`client.ts:136–140`); the server advertises
  `vary: Accept-Encoding` and gzips when asked.

---

## OBS-API-01 — `warmPlayerCache()` is fired twice on the cold-start path (boot + first league pick)

- **Area:** API client / data-fetching
- **Severity:** P2
- **Status:** observed
- **Evidence type:** measured

### What happens today
`warmPlayerCache()` is called at app boot in `mobile/App.tsx:51` (inside the
`Promise.all([bootstrap(), loadFlags(), fetchTierConfig(), warmPlayerCache()…])`
splash fan-out), and then called **again** inside `initLeagueSession` on every
league pick / switch / connect — `mobile/src/api/auth.ts:117`. Both hit the same
server-side process cache via `GET /api/sleeper/players/warm`
(`mobile/src/api/sleeper.ts:47`). For a returning user whose dyno is already
warm, boot warms the cache and then the first league pick warms it a second time
within seconds.

### Why it's slow / costly
Redundant request. The warm endpoint is cheap (25 B body), so this is not a
payload problem — it is a wasted round trip plus, on a cold free-tier dyno,
wasted contention against the single worker that is also trying to serve the
roster/users fetches and `session_init`. The boot-time warm in `App.tsx:51`
already removes the "Player database not cached" hard error that the
`auth.ts:117` call was originally added to prevent (see the comment at
`auth.ts:106–113`), so on the normal launch→pick flow the second warm is pure
overhead. It only earns its keep in the narrow case where the dyno cold-starts
*between* boot and the league pick.

### Evidence
- `mobile/App.tsx:44–53` — boot `Promise.all` includes
  `warmPlayerCache().catch(() => {})`.
- `mobile/src/api/auth.ts:114–123` — `initLeagueSession` runs
  `warmPlayerCache()` inside its own `Promise.all` on every call.
- Measured: two back-to-back warm calls returned `0.197 s` then `0.233 s`
  (warm dyno) — i.e. the second call is a full ~0.2 s RTT that returns the
  same 25 B and does no useful work when the cache is already hot.
- The warm leg is already parallelized with rosters/users in
  `auth.ts:114–123`, so on a warm dyno it is hidden behind those two; the cost
  surfaces as worker contention only when the dyno is cold (TTFB measured at
  `4.85 s` on first hit).

### Recommendation(s)
- **Option A (preferred):** Coalesce to a single boot-time warm and make the
  `initLeagueSession` warm conditional — skip it if a warm has already
  succeeded this process-lifetime, or gate it behind a module-level
  "warmed-once" flag in `sleeper.ts`. Keeps cold-start protection for the
  rare boot→cold→pick window while removing the steady-state double call.
  Client-only, low risk.
- **Option B:** Remove the `auth.ts:117` warm entirely and rely solely on the
  boot warm + the backend's own error retry message. Simplest, but
  re-introduces the original hard-error risk if a dyno cold-starts after boot
  but before the first pick — not worth it for the ~0.2 s saved.

### RICE-P
| Reach | Impact | Confidence | Effort | **Score** |
|------:|-------:|-----------:|-------:|----------:|
| 8 | 0.5 | 80% | 1 | **3.2** |

- **Estimated latency delta:** warm dyno: −1 round trip on first league pick
  (~−0.2 s, hidden behind parallel rosters/users so user-invisible most of the
  time). Cold dyno: removes one of two concurrent warm requests competing for
  the single free-tier worker during the most contended moment of the session
  (the value is contention relief, not raw wall-clock).
- **Confidence note:** 80% — the duplicate call is unambiguous in code and the
  warm RTT is measured; the user-perceived gain is small because it is usually
  masked by parallelism, hence Impact 0.5.

### Related components
`mobile/App.tsx` (boot fan-out), `mobile/src/api/auth.ts` (`initLeagueSession`),
`mobile/src/api/sleeper.ts` (`warmPlayerCache`), backend
`/api/sleeper/players/warm`.

### Prerequisites / dependencies
None.

### Regression risk
Low. Must preserve the cold-start guarantee: if the "warmed-once" flag is set
but the backend process has since restarted (redeploy / dyno recycle), the next
`session_init` could hit the uncached error again. Mitigate by resetting the
flag on any `session_init` failure whose message matches "Player database not
cached", or simply keep Option A's flag per-app-launch and accept the rare
re-warm. Test: cold launch → pick league succeeds; warm relaunch → pick league
issues only one warm.

---

## OBS-API-02 — No `Accept-Encoding` header: large JSON bodies download uncompressed

- **Area:** API client / network
- **Severity:** P1
- **Status:** observed
- **Evidence type:** measured

### What happens today
The shared request wrapper builds headers as
`{ Accept: 'application/json', ..._CLIENT_HEADERS, ...opts.headers }`
(`mobile/src/api/client.ts:136–140`) and never sets `Accept-Encoding`. Whether
responses are compressed therefore depends entirely on the platform `fetch`
default. On the server side, `vary: Accept-Encoding` is advertised and gzip is
produced **only when the request asks for it** (measured below).

### Why it's slow / costly
The largest body this app can pull, `GET /api/sleeper/players`, is **4.84 MB
uncompressed vs 676 KB gzipped** — an 86% reduction. Measured wall-clock for
that endpoint was **7.48 s without gzip vs 1.03 s with `Accept-Encoding: gzip`**
on the same warm dyno. While the *mobile* client normally calls the lean
`/players/warm` variant (`sleeper.ts:47`) rather than the full route, several
other client calls return non-trivial JSON that benefits from compression
(rankings lists, `getRecentTrades`, `getAllMatches`, activity feed). If
React Native's `fetch` (Hermes/OkHttp on Android, NSURLSession on iOS) is not
transparently negotiating gzip — which is **not guaranteed** and is the exact
ambiguity this header removes — every one of those bodies is downloaded raw.
This is a low-effort, high-leverage change because it is one line in the one
wrapper every call funnels through.

### Evidence
- `mobile/src/api/client.ts:136–140` — header object; no `Accept-Encoding`.
- Measured `/api/sleeper/players`:
  - no gzip header: `time_total=7.477 s size=4,837,423 B`
  - `-H "Accept-Encoding: gzip, br"`: `time_total=1.035 s size=676,415 B`
- Measured `/api/feature-flags` with `Accept-Encoding: gzip` returned
  `content-encoding: gzip` + `vary: Accept-Encoding` — confirms the server
  compresses on demand and keys cache on the header.

### Recommendation(s)
- **Option A (preferred):** Add `'Accept-Encoding': 'gzip'` to the default
  header block in `client.ts:136–140`. One line, every call benefits, server
  already supports it. Follows standard mobile-fetch guidance (see
  `../research/00-research-methodology.md`; a dedicated payload/compression note
  may be added under `../research/`). Note: on some RN engines the networking
  layer strips/overrides `Accept-Encoding` and handles gzip itself — in that
  case this is a harmless no-op, so there is no downside to setting it.
- **Option B:** Verify-then-act — add a one-off network trace (Flipper / Charles)
  on a real device to confirm whether RN already negotiates gzip before
  spending the line. Lower risk of "no-op change," but adds a measurement step;
  given Option A is costless, prefer A.

### RICE-P
| Reach | Impact | Confidence | Effort | **Score** |
|------:|-------:|-----------:|-------:|----------:|
| 6 | 2 | 50% | 0.5 | **12.0** |

- **Estimated latency delta:** up to **−6.4 s** on a full `/players` download
  (7.48 s → 1.03 s) if that path is ever exercised uncompressed; for the
  routinely-hit rankings/trades/matches list bodies, proportional savings on a
  cellular link where bytes dominate. If RN already negotiates gzip, delta is
  ~0 and the change is a safe no-op.
- **Confidence note:** 50% — the server-side win is **measured and large**, but
  Confidence is capped because whether the mobile runtime *already* sends
  `Accept-Encoding` is unverified on-device; a single device network trace would
  push this to 80–100% (and decide between A and "already fine").

### Related components
`mobile/src/api/client.ts` (header block) — affects every call, notably
`sleeper.ts` (`getLeagues`, `getLeagueRosters`), `rankings.ts` (`getRankings`),
`trades.ts` (`getRecentTrades`, `getAllMatches`), `league.ts` (activity/members).

### Prerequisites / dependencies
None. Independent of every other OBS here.

### Regression risk
Very low. The server already sets `vary: Accept-Encoding`, so caches stay
correct. Only risk is a runtime that double-decodes — not observed on standard
RN networking. Test a couple of list endpoints render identically after the
change.

---

## OBS-API-03 — Trade-status poll uses a fixed 1.5 s interval with no backoff or jitter

- **Area:** API client / data-fetching
- **Severity:** P2
- **Status:** observed
- **Evidence type:** static-analysis

### What happens today
After `generateTrades()` (`mobile/src/api/trades.ts:100`) returns a `running`
snapshot, `TradesScreen` polls `getTradeStatus(job.job_id)`
(`mobile/src/api/trades.ts:107`) on a constant `setInterval(tick, 1500)`
(`mobile/src/screens/TradesScreen.tsx:256`). The cadence is fixed from the first
tick to `status === 'complete'`, independent of how fast opponents are actually
completing. Each tick re-runs `normalizeJobSnapshot` →
`normalizeTradeCard` over the full cumulative card array (`trades.ts:84–96`).

### Why it's slow / costly
Classic constant-poll-without-backoff anti-pattern. The backend generates
trades per-opponent in a background thread; a long job (many opponents, cold
dyno) yields many polls that return an unchanged in-progress snapshot. On
cellular these are wasted radio wake-ups that contend with the very generation
job being awaited, and on a cold free-tier dyno the poll storm competes with the
single worker doing the generation. It does not slow the first card, but it
degrades the streaming-fill tail and burns battery/data. Each redundant poll
also re-normalizes the entire (growing) card list client-side
(`trades.ts:85`), a small but repeated CPU cost.

### Evidence
- `mobile/src/screens/TradesScreen.tsx:256` — `setInterval(tick, 1500)`, no
  dynamic interval; cleared only on complete/error/unmount
  (`TradesScreen.tsx:257–260`).
- `mobile/src/screens/TradesScreen.tsx:233–261` — the poll effect; `failures`
  counter exists for error capping but there is no success-side backoff.
- `mobile/src/api/trades.ts:84–96` — every poll response is fully
  re-normalized, including already-seen cards.
- Measured `/api/feature-flags` baseline RTT ~0.2 s warm; a status poll is a
  comparable cheap dict read, so on a 12 s job at 1.5 s cadence that is ~8
  requests, the majority no-change.

### Recommendation(s)
- **Option A (preferred):** Exponential backoff with cap + jitter — start
  ~800 ms, ×1.5 per *unchanged* tick (detect via `opponents_done` not
  advancing), cap ~4 s, reset to 800 ms when `opponents_done` increases.
  Collapses the no-change tail while keeping early responsiveness. Client-only;
  lives in `TradesScreen.tsx`. (This mirrors the pattern in
  `templates/recommendation-example.md`.)
- **Option B:** Move the job to server-sent events / long-poll so the client
  blocks until the next card is ready. Better UX but adds a streaming endpoint
  and free-tier worker-occupancy concerns — defer unless A is insufficient.

### RICE-P
| Reach | Impact | Confidence | Effort | **Score** |
|------:|-------:|-----------:|-------:|----------:|
| 6 | 0.5 | 80% | 1 | **2.4** |

- **Estimated latency delta:** no change to first-card latency; ~60–75% fewer
  status requests per job, smoother fill on cellular, less worker contention on
  a cold dyno (saves hundreds of ms on the contended tail). Note this lives
  primarily in `TradesScreen.tsx` (a screen, not the api dir) — flagged here
  because the poll target (`getTradeStatus`) is in scope and the api-layer
  normalizer amplifies the cost.
- **Confidence note:** 80% — anti-pattern is unambiguous in code; user-perceived
  gain is modest and partly battery/contention, hence Impact 0.5.

### Related components
`mobile/src/screens/TradesScreen.tsx` (poll loop), `mobile/src/api/trades.ts`
(`getTradeStatus`, `normalizeJobSnapshot`), backend `/api/trades/status`.

### Prerequisites / dependencies
None for Option A.

### Regression risk
Low. Ensure backoff resets on progress so the final card is not delayed up to
the cap. Test a multi-opponent job fills to completion and the
`running → complete` transition still fires.

---

## OBS-API-04 — No request timeout: a hung Render dyno blocks the UI indefinitely

- **Area:** API client / network
- **Severity:** P1
- **Status:** observed
- **Evidence type:** static-analysis

### What happens today
`apiRequest` calls `fetch(url, { method, headers, body, signal: opts.signal })`
(`mobile/src/api/client.ts:149–159`) with no timeout. The only abort path is a
caller-supplied `opts.signal` (used by TanStack Query for cancellation,
`client.ts:126–127`). Direct callers that do not pass a signal — e.g.
`signIn` (`auth.ts:25`), `initLeagueSession`'s `sessionInit` (`auth.ts:151`),
`startDemoSession` (`auth.ts:230`), `resolveSmartStart` (`auth.ts:201`) — have
no time bound at all.

### Why it's slow / costly
On the free Render dyno, `session_init` is explicitly documented as the slow leg
at **5–10 s** (`mobile/src/api/auth.ts:98–99`), and a cold-started dyno was
measured at **4.85 s TTFB just to answer the trivial warm endpoint**. If a dyno
is mid-cold-start or wedged, a `fetch` with no timeout hangs until the OS
socket timeout (often 60–120 s+), leaving the user on a spinner with no error
and no retry affordance — the worst-feeling latency failure. This is a
"perceived infinite latency" hole on exactly the auth/league-pick path that is
the entry to players and trades.

### Evidence
- `mobile/src/api/client.ts:149–159` — `fetch` with `signal: opts.signal`
  only; no `AbortController` + timer, no per-request deadline.
- `mobile/src/api/auth.ts:98–99` — comment: "sessionInit is the slow leg
  (5–10 s on Render's free tier)" — the exact call most exposed to a hang.
- Measured cold warm-endpoint TTFB `4.85 s`; full `/players` `7.48 s` — a
  wedged dyno can blow far past these with no client ceiling.

### Recommendation(s)
- **Option A (preferred):** Add a default timeout in `apiRequest` via an
  internal `AbortController` (e.g. 15 s GET / 30 s for the known-slow
  `session/init` + `trades/generate`), composed with any caller `signal`. On
  timeout, throw a typed `ApiError` the UI can render as "Server is waking up —
  retry." Bounds every call in one place. Low risk, client-only.
- **Option B:** Add timeout only at the few un-signalled call sites
  (`signIn`, `sessionInit`, demo, parse-url). Smaller blast radius but leaves
  future callers unprotected and duplicates logic — prefer A.

### RICE-P
| Reach | Impact | Confidence | Effort | **Score** |
|------:|-------:|-----------:|-------:|----------:|
| 4 | 2 | 50% | 1 | **4.0** |

- **Estimated latency delta:** in the failure case, replaces a 60–120 s+ dead
  spinner with a bounded ~15–30 s timeout + actionable retry — i.e. caps
  worst-case perceived latency and restores user control. No change on the
  happy path. Reach 4 because true hangs are occasional (cold/wedged dyno), not
  every session.
- **Confidence note:** 50% — the missing-timeout code path is certain
  (static), but the *frequency* of real hangs (vs the dyno simply being slow but
  eventually responding) is unmeasured; raising it needs production timing
  telemetry on `session/init`.

### Related components
`mobile/src/api/client.ts` (`apiRequest`/`fetch`), all un-signalled callers in
`auth.ts`, plus `trades.ts` `generateTrades`. Backend `/api/session/init`.

### Prerequisites / dependencies
None. Pairs naturally with OBS-API-05 (retry) but is independent.

### Regression risk
Medium-low. A too-aggressive timeout on `session/init` could abort a legitimately
slow-but-progressing cold-start request and force a retry into another
cold-start. Mitigate by giving the known-slow endpoints a generous deadline
(≥30 s) distinct from the default. Test a cold-dyno league pick still completes
within the deadline.

---

## OBS-API-05 — No retry/coalescing in the wrapper; transient 5xx/cold-start failures surface as hard errors

- **Area:** API client / network
- **Severity:** P2
- **Status:** observed
- **Evidence type:** static-analysis

### What happens today
`apiRequest` does exactly one `fetch` and throws `ApiError` on any non-OK
status (`mobile/src/api/client.ts:171–178`). There is no retry, no
single-flight de-duplication, and no coalescing of identical concurrent GETs.
Each public function is a thin one-shot wrapper around `api.get/post`
(e.g. `sleeper.ts:28–41`, `trades.ts:107–122`, `rankings.ts:96–99`). Any
caller-side retry/dedup is delegated entirely to TanStack Query, but several
hot calls bypass Query and run imperatively: `initLeagueSession` →
`getLeagueRosters` + `getLeagueUsers` + `warmPlayerCache` + `sessionInit`
(`auth.ts:114–161`), and `SignInScreen`'s `getLeagues` prefetch
(`SignInScreen.tsx:132`).

### Why it's slow / costly
On a cold free-tier dyno the **first** request after sleep commonly returns
slowly or 5xx while gunicorn spins up (measured first-hit TTFB `4.85 s`; a
true cold start can 502/503 before that). With zero retry on the imperative
auth/league-pick path, a single transient cold-start failure throws straight to
the user's error UI, and the *only* recovery is a full manual re-tap — which
itself re-runs the whole `rosters + users + warm + init` sequence from scratch
rather than just the leg that failed. Lack of single-flight also means a
double-tap or a deep-link-during-tap can issue two concurrent
`getLeagues`/`session_init` sequences (the `switchLeague` guard at
`useSession.ts:147–166` covers league switch but not the initial
`LeaguePickerScreen` pick or the `SignInScreen` prefetch).

### Evidence
- `mobile/src/api/client.ts:149–178` — single `fetch`, throw on non-OK, no
  retry/backoff, no in-flight map.
- `mobile/src/api/auth.ts:114–161` — imperative multi-call sequence with no
  retry wrapper; a failure in any leg rejects the whole `initLeagueSession`.
- `mobile/src/screens/SignInScreen.tsx:131–136` — `getLeagues` prefetch in a
  bare try/catch, no retry.
- Measured cold first-hit `4.85 s` and the documented 5–10 s `session_init`
  (`auth.ts:98–99`) are exactly the windows where a transient 5xx is most
  likely.

### Recommendation(s)
- **Option A (preferred):** Add a small, opt-in retry-with-backoff to
  `apiRequest` for **idempotent GETs** on 502/503/504/network-error (e.g. 2
  retries, 400 ms → 1.2 s, jitter). Targets the cold-start 5xx window without
  re-trying mutations. Centralized, ~half a day. Reference
  `../research/00-research-methodology.md` (a cold-start/network note may be
  added under `../research/0X-*.md`).
- **Option B:** Add single-flight de-dup keyed by `method+url+body` so
  concurrent identical GETs share one promise (kills double-tap / deep-link
  races on `getLeagues`). Complementary to A; smaller, also client-only.
- **Option C:** Migrate the imperative `initLeagueSession` / `getLeagues`
  prefetch onto TanStack Query mutations/queries so they inherit Query's retry,
  dedup, and cancellation for free instead of re-implementing it in the wrapper.
  Larger refactor; best long-term but more surface area.

### RICE-P
| Reach | Impact | Confidence | Effort | **Score** |
|------:|-------:|-----------:|-------:|----------:|
| 4 | 1 | 50% | 2 | **2.0** |

- **Estimated latency delta:** on a cold-start 5xx, an automatic GET retry
  turns a hard error + full manual re-tap (user-time cost of several seconds
  plus re-running the whole sequence) into a transparent ~0.4–1.2 s retry that
  usually succeeds on the now-warm dyno. No change on the happy path. Reach 4:
  the bad case is per cold-start, not per session.
- **Confidence note:** 50% — the missing retry/dedup is certain in code; the
  rate of transient cold-start 5xx (vs slow-but-200) is unmeasured, so the
  realized benefit is a reasoned estimate. Backend cold-start telemetry would
  raise it.

### Related components
`mobile/src/api/client.ts` (`apiRequest`), `mobile/src/api/auth.ts`
(`initLeagueSession`), `mobile/src/api/sleeper.ts` (`getLeagues`),
`mobile/src/screens/SignInScreen.tsx`, `mobile/src/state/useSession.ts`
(`switchLeague` guard). Backend cold-start behavior (network agent area).

### Prerequisites / dependencies
None hard. Coordinate with OBS-API-04 (timeout) so retry deadlines compose
sanely. Retry must stay GET-only to avoid double-mutating
(`swipeTrade`, `saveTiers`, `sessionInit`).

### Regression risk
Medium. Retrying anything non-idempotent risks duplicate writes — strictly gate
retry on GET. Confirm `session/init` (a POST) is **excluded** from auto-retry so
a partially-applied init isn't re-sent. Test cold-dyno league pick recovers
without a duplicate session.

---

## OBS-API-06 — `getNewPartners` triggers a second full activity-feed fetch instead of reusing the first

- **Area:** API client / data-fetching
- **Severity:** P3
- **Status:** observed
- **Evidence type:** static-analysis

### What happens today
`getNewPartners(leagueId)` (`mobile/src/api/league.ts:282–303`) derives its
result by calling `getActivityFeed(leagueId, 50)` (`league.ts:287`), which is a
full `GET /api/league/activity?league_id=…&limit=50` round trip
(`league.ts:178–205`). The League tab already renders the activity feed itself
(typically via its own `getActivityFeed(leagueId, 20)` query). So when both the
activity feed and the "new partners" banner are shown, the activity data is
fetched **twice** — once at limit 20 for the feed, once at limit 50 for the
partners derivation — with no shared cache between them at the api layer.

### Why it's slow / costly
Redundant network fetch of the same underlying resource, differing only by
`limit`. The two calls cannot share a TanStack Query cache entry because their
query keys differ by limit, and `getNewPartners` re-fetches rather than deriving
from an already-loaded larger window. It is a secondary path (League tab, not
the player/trade critical path), so impact is bounded, but it is a clean
double-fetch.

### Evidence
- `mobile/src/api/league.ts:287` — `const { events } = await
  getActivityFeed(leagueId, 50);` inside `getNewPartners`.
- `mobile/src/api/league.ts:178–205` — `getActivityFeed` is a full network GET;
  no memoization.
- The function's own comment (`league.ts:275–281`) notes there is "no dedicated
  backend route" and it derives client-side from the feed — confirming the
  double-fetch is intentional-but-unoptimized.

### Recommendation(s)
- **Option A (preferred):** Have the League screen fetch the activity feed once
  at the larger limit (50) and derive *both* the feed view and the new-partners
  banner from that single cached result client-side, dropping the second
  network call. Coordinates at the screen/query layer; api function can expose a
  pure `derivePartnersFromEvents(events)` helper. Low effort, removes one GET.
- **Option B:** Leave as-is but lengthen `getNewPartners`' staleTime so the
  extra fetch is rare. Cheaper to ship, but still double-fetches on first paint.

### RICE-P
| Reach | Impact | Confidence | Effort | **Score** |
|------:|-------:|-----------:|-------:|----------:|
| 2 | 0.5 | 80% | 1 | **0.8** |

- **Estimated latency delta:** −1 activity-feed round trip when the League tab
  shows both the feed and the partners banner (~−0.2–0.5 s of redundant network
  on that tab; off the player/trade critical path). Activity feed is a small
  body so the saving is the RTT, not bytes.
- **Confidence note:** 80% — the double-call is explicit in code; impact is low
  because it is a secondary tab and the body is small, hence Impact 0.5 / Reach 2.

### Related components
`mobile/src/api/league.ts` (`getNewPartners`, `getActivityFeed`), the League
screen that renders both, backend `/api/league/activity`.

### Prerequisites / dependencies
None. Best done alongside whatever screen-level query owns the activity feed.

### Regression risk
Low. The partners derivation must still see a wide-enough window (≥50) so a
returning user doesn't miss older unlocks — keep the single fetch at limit 50,
not 20. Verify the banner still surfaces older `unlock` events after the merge.

---

## Top 3 by RICE-P

| Rank | OBS | Title | Severity | RICE-P | Est. latency delta |
|-----:|-----|-------|:--------:|-------:|--------------------|
| 1 | OBS-API-02 | Add `Accept-Encoding: gzip` to the shared wrapper | P1 | **12.0** | up to −6.4 s on full `/players`; proportional on rankings/trades/matches lists (or safe no-op if RN already negotiates gzip) |
| 2 | OBS-API-04 | Add a default request timeout to `apiRequest` | P1 | **4.0** | caps worst-case from 60–120 s+ dead spinner to a bounded ~15–30 s + retry on a hung/cold dyno |
| 3 | OBS-API-01 | De-duplicate the double `warmPlayerCache()` (boot + league pick) | P2 | **3.2** | −1 round trip (~−0.2 s) on first league pick; cold-dyno worker-contention relief |

---

## CROSS-REF (outside this agent's lane — route to the right agent)

- **Backend gzip / payload (agent-03/04):** `/api/sleeper/players` serializes
  **4.84 MB uncompressed**; gzip cuts it to 676 KB. The client-side fix
  (OBS-API-02) only helps if the server keeps compressing on demand — worth a
  backend check that gzip is enabled for *all* large JSON routes, not just the
  ones that happened to compress in my sample.
- **Cold-start (agent-06):** measured **4.85 s TTFB** on the first warm-endpoint
  hit after sleep, and documented **5–10 s `session_init`** on free tier. The
  client mitigations here (boot warm-ping, timeout, GET retry) are band-aids;
  the root cause is the sleeping free dyno — belongs to the network/cold-start
  agent.
- **TanStack Query staleTime/key design (agent-02):** the imperative
  `initLeagueSession` / `getLeagues` prefetch and the `getNewPartners`
  double-fetch (OBS-API-06) would both be cleaner as Query-managed entries;
  cache-key + staleTime strategy is the data-fetching/cache agent's lane.
